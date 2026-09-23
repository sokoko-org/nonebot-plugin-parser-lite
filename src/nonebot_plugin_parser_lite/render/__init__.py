import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from itertools import chain
import re
from typing import Any, ClassVar, Literal
import uuid

from anyio import Path
from jinja2 import Environment, FileSystemLoader
from nonebot import logger
from nonebot_plugin_htmlrender import get_new_page
from PIL import Image

from ..config import _nickname, gconfig, pconfig
from ..data import (
    AudioContent,
    GraphicContent,
    ImageContent,
    LinkContent,
    LivePhotoContent,
    MediaContent,
    ParseResult,
    PollContent,
    QuoteContent,
    StickerContent,
    VideoContent,
)
from ..exception import (
    DownloadException,
    SizeLimitException,
)
from ..helper import ForwardNodeInner, UniHelper, UniMessage
from ..utils.cache import CacheManager
from ..utils.ffmpeg import FFmpeg
from .context import PLACEHOLDER_IMAGE, ThemeData, build_theme_data, safe_src
from .theme import ThemeDefinition, ThemeManager

__all__ = ["PLACEHOLDER_IMAGE", "ThemeData", "ThemeManager", "safe_src"]

SPLIT_THRESHOLD = pconfig.forward_text_threshold
"""单段文本拆分阈值"""
MAX_FORWARD_TEXT_LEN = 30000
"""单个 forward 文本总长上限"""
MAX_FORWARD_NODES = 90
"""单个 forward 节点数上限"""

IS_DEBUG = gconfig.log_level in ["DEBUG", "TRACE", 10, 5]
RENDER_TEMPLATE_VERSION = "20260923"

Theme = Literal["light", "dark"]
TEXT_SPLIT_PUNCTUATION = frozenset("。！？!?；;，,、…")


def get_theme() -> Theme:
    """根据配置的白天时间范围返回当前主题"""
    start, end = pconfig.day_range_minutes
    now = datetime.now()
    current = now.hour * 60 + now.minute
    if start == end:
        # 为什么会有极夜
        in_day = False
    elif start < end:
        in_day = start <= current < end
    else:
        in_day = current >= start or current < end
    return "light" if in_day else "dark"


def _find_text_split_end(text: str, start: int, max_len: int) -> int:
    """返回下一段的结束索引，优先落在标点之后"""
    end = min(start + max_len, len(text))
    if end == len(text):
        return end
    return next(
        (
            index + 1
            for index in range(end - 1, start - 1, -1)
            if text[index] in TEXT_SPLIT_PUNCTUATION
        ),
        end,
    )


def split_text_by_length_with_punct(text: str, max_len: int) -> list[str]:
    """按长度切分文本，优先在标点符号处断句

    规则：
    1. 遍历文本，当前段长度超过 max_len 时：
       - 尝试在当前段中最后一个标点符号后断句；
       - 若找不到合适标点，则在 max_len 处硬切
    2. 支持中英文常用标点

    :param text: 原始文本
    :param max_len: 每段最大长度
    :return: 切分后的文本段列表
    """
    if max_len <= 0 or len(text) <= max_len:
        return [text]

    result: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = _find_text_split_end(text, start, max_len)
        result.append(text[start:end])
        start = end

    return result


@dataclass(slots=True)
class _ForwardTextPart:
    text: str
    protected: bool = False


@dataclass(slots=True)
class _ForwardText:
    """保留块边界的待拆分转发文本"""

    author_name: str
    parts: list[_ForwardTextPart]
    include_author: bool = True
    text_length: int = field(init=False)

    def __post_init__(self) -> None:
        self.text_length = len(self.prefix) + sum(len(part.text) for part in self.parts)

    @property
    def prefix(self) -> str:
        return f"{self.author_name}：" if self.include_author else ""

    @property
    def text(self) -> str:
        return f"{self.prefix}{''.join(part.text for part in self.parts)}"

    def split(self, max_len: int) -> list[str]:
        if max_len <= 0 or self.text_length <= max_len:
            return [self.text]

        prefix = self.prefix
        chunks: list[str] = []
        current = prefix

        def flush() -> None:
            nonlocal current
            if current:
                chunks.append(current)
                current = ""

        for part in self.parts:
            if part.protected:
                # 受保护块可以超过软拆分阈值，但不会在块内部切开
                if (
                    current
                    and current != prefix
                    and len(current) + len(part.text) > max_len
                ):
                    flush()
                current += part.text
                continue

            start = 0
            part_length = len(part.text)
            while start < part_length:
                room = max_len - len(current)
                if room <= 0:
                    flush()
                    room = max_len
                if part_length - start <= room:
                    current += part.text[start:]
                    break
                end = _find_text_split_end(part.text, start, room)
                current += part.text[start:end]
                start = end
                flush()

        flush()
        return chunks


class Renderer:
    """统一的渲染器，将解析结果转换为消息"""

    templates_dir: ClassVar[Path] = Path(__file__).parent / "templates"
    """模板目录"""

    async def render_messages(self, result: ParseResult) -> UniMessage[Any]:
        """渲染消息

        :param result: 解析结果
        """
        # 尝试获取图片路径，以便在直接发送失败时使用文件发送
        try:
            image_seg = await self.cache_or_render_image(result)
        except Exception as e:
            logger.exception(f"获取图片路径失败: {e!r}")
            image_seg = None

        # 尝试直接发送图片
        msg = UniMessage(image_seg or "图片渲染失败")
        if pconfig.append_url:
            urls = (result.display_url, result.repost_display_url)
            msg += "\n".join(url for url in urls if url)
        if pconfig.embed_url:
            if embed := result.embed_url:
                msg += "\n在线播放: " + embed
        return msg

    async def send_content(
        self, result: ParseResult
    ) -> AsyncGenerator[UniMessage[Any], None]:
        """发送媒体内容消息

        将解析结果中的媒体内容拆分为：
        - 需要立即发送的音视频（逐条 yield）或待合并转发的视频
        - 可合并转发的图文 / 图片（统一收集后一次发送）
        """
        failed_count = 0
        forward_video_segs: dict[int, ForwardNodeInner] = {}
        repost_medias = result.repost.content if result.repost else []
        media_contents = (
            cont
            for cont in chain(result.content, repost_medias)
            if isinstance(cont, MediaContent) and cont.need_send
        )
        for cont in media_contents:
            # 先处理需要立即发送的音视频，或准备待合并转发的视频节点
            try:
                if isinstance(cont, VideoContent) and pconfig.video_in_forward:
                    forward_video_segs[id(cont)] = await self.__build_video_seg(cont)
                    continue
                async for msg in self.__handle_immediate_media(cont):
                    yield msg
            except SizeLimitException:
                yield UniMessage(
                    f"媒体太大啦，还是去{result.platform.display_name}看看吧~"
                )
                continue
            except DownloadException as e:
                failed_count += 1
                logger.exception(f"{cont.__class__.__name__} 下载失败: {e!r}")
                continue

        # 2 构建图文 / 图片的转发列表（含主帖 + 转发，按顺序）
        ordered_segs = await self.__build_forward_segs(result, forward_video_segs)
        if ordered_segs:
            # 一次遍历：统计+长文本拆分
            processed_segs: list[ForwardNodeInner] = []
            total_plain_len = 0
            node_count = 0

            for seg in ordered_segs:
                node_count += 1
                if isinstance(seg, _ForwardText):
                    total_plain_len += seg.text_length
                    processed_segs.extend(seg.split(SPLIT_THRESHOLD))
                elif isinstance(seg, str):
                    seg_len = len(seg)
                    total_plain_len += seg_len
                    if seg_len > SPLIT_THRESHOLD:
                        processed_segs.extend(
                            split_text_by_length_with_punct(seg, SPLIT_THRESHOLD)
                        )
                    else:
                        processed_segs.append(seg)
                else:
                    processed_segs.append(seg)

            # 是否需要合并转发：
            # 1) 配置项 need_forward_contents
            # 2) 纯文字部分超过阈值
            # 3) 节点数较多
            # 4) 包含配置为合并转发的视频
            need_forward = (
                pconfig.need_forward_contents
                or total_plain_len > SPLIT_THRESHOLD
                or node_count > 4
                or bool(forward_video_segs)
            )

            if not need_forward:
                # 不走合并转发：直接按节点顺序发出
                yield UniMessage(processed_segs)
            else:
                # 需要合并转发：根据平台限制按文本长度 / 节点数分批构造 forward
                current_chunk: list[ForwardNodeInner] = []
                current_text_len = 0

                def flush_chunk() -> UniMessage[Any] | None:
                    nonlocal current_text_len
                    if not current_chunk:
                        return None
                    msg = UniMessage(UniHelper.construct_forward_message(current_chunk))
                    current_chunk.clear()
                    current_text_len = 0
                    return msg

                for seg in processed_segs:
                    seg_text_len = len(seg) if isinstance(seg, str) else 0

                    # 如果加上当前节点会超出单个 forward 限制，则先 flush 当前 chunk
                    if current_chunk and (
                        current_text_len + seg_text_len > MAX_FORWARD_TEXT_LEN
                        or len(current_chunk) >= MAX_FORWARD_NODES
                    ):
                        msg = flush_chunk()
                        if msg is not None:
                            yield msg

                    current_chunk.append(seg)
                    current_text_len += seg_text_len

                # 收尾：还有未发送的 chunk
                last_msg = flush_chunk()
                if last_msg is not None:
                    yield last_msg

        # 汇总下载失败信息
        if failed_count > 0:
            message = f"{failed_count} 项媒体下载失败"
            yield UniMessage(message)
            logger.warning(message)

    async def __handle_immediate_media(
        self, cont: MediaContent
    ) -> AsyncGenerator[UniMessage[Any], None]:
        """
        处理需要立即发送的音视频媒体，返回对应的消息段

        :raise ZeroSizeException: 资源大小为 0 时抛出
        :raise SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raise DownloadException: 重试多次仍失败时抛出
        """
        if not isinstance(cont, VideoContent | AudioContent):
            return
        path = await cont.get_path()
        if isinstance(cont, VideoContent):
            yield UniMessage(await self.__build_video_seg(cont, path))
        elif isinstance(cont, AudioContent) and pconfig.need_upload_audio:
            yield UniMessage(await UniHelper.file_seg(path))
        elif isinstance(cont, AudioContent):
            yield UniMessage(await UniHelper.record_seg(path))

    @staticmethod
    async def __build_video_seg(
        cont: VideoContent, path: Path | None = None
    ) -> ForwardNodeInner:
        """构建视频或视频文件消息段"""
        video_path = path or await cont.get_path()
        if pconfig.need_upload_video:
            return await UniHelper.file_seg(video_path)
        return await UniHelper.video_seg(
            file=video_path, thumbnail=await cont.get_cover_path()
        )

    async def __build_forward_segs(
        self,
        result: ParseResult,
        forward_video_segs: dict[int, ForwardNodeInner],
    ) -> list[ForwardNodeInner | _ForwardText]:
        """根据当前内容和转发内容构造有序的转发段列表（文本 + 媒体，保持顺序）

        规则：
        - 主帖：
          - 文本片段按顺序聚合，输出 "作者：文本" 节点
          - 媒体片段（Image/Graphic/LivePhoto/Video 封面等）按出现顺序插入对应消息段
        - 如有转发：
          - 插入一条说明
          - 然后对转发 ParseResult 做同样处理
        """

        async def build_nodes(pr: ParseResult) -> list[ForwardNodeInner | _ForwardText]:
            author_name = pr.author.name
            nodes: list[ForwardNodeInner | _ForwardText] = []
            text_buffer: list[_ForwardTextPart] = []
            author_prefix_pending = True
            if title := pr.title:
                nodes.append(
                    _ForwardText(author_name, [_ForwardTextPart(f"{title}\n")], False)
                )

            async def flush_text() -> None:
                nonlocal author_prefix_pending, text_buffer
                if text_buffer:
                    nodes.append(
                        _ForwardText(
                            author_name,
                            text_buffer,
                            include_author=author_prefix_pending,
                        )
                    )
                    author_prefix_pending = False
                    text_buffer = []

            def append_text(text: str) -> None:
                text_buffer.append(_ForwardTextPart(text))

            def append_text_block(text: str) -> None:
                """将块级文本加入当前文本段，并与相邻内容换行分隔"""
                if not text:
                    return
                if text_buffer and not text_buffer[-1].text.endswith("\n"):
                    append_text("\n")
                text_buffer.append(_ForwardTextPart(f"{text}\n", protected=True))

            async def append_media(cont: MediaContent) -> None:
                """将单个媒体内容转换为若干 ForwardNodeInner，并追加到 nodes"""
                # 视频：始终保留封面，并按配置追加视频本体。两者分别处理，
                # 避免封面构建失败时丢失已经准备好的视频节点。
                if isinstance(cont, VideoContent):
                    try:
                        path = await cont.get_cover_path()
                        if path:
                            nodes.append(await UniHelper.img_seg(file=path))
                    except Exception as e:
                        logger.warning(
                            f"构建转发媒体片段失败: {type(cont).__name__}: {e}"
                        )
                        nodes.append(f"[媒体加载失败：{type(cont).__name__}]")
                    video_seg = forward_video_segs.get(id(cont))
                    if video_seg is not None:
                        nodes.append(video_seg)
                    return

                try:
                    # 图片
                    if isinstance(cont, ImageContent):
                        path = await cont.get_path()
                        nodes.append(await UniHelper.img_seg(path))
                        return

                    # 图文：图片 + 可选文字说明
                    if isinstance(cont, GraphicContent):
                        path = await cont.get_path()
                        seg: ForwardNodeInner = await UniHelper.img_seg(path)
                        if cont.alt:
                            seg = seg + cont.alt
                        nodes.append(seg)
                        return

                    # Live Photo
                    if isinstance(cont, LivePhotoContent):
                        if pconfig.live_photo:
                            live_path = await cont.get_live()
                            nodes.append(
                                await UniHelper.video_seg(
                                    file=live_path, thumbnail=await cont.get_base()
                                )
                            )
                        else:
                            base_path = await cont.get_base()
                            live_path = await cont.get_path()
                            nodes.append(await UniHelper.img_seg(base_path))
                            nodes.append(
                                await UniHelper.video_seg(
                                    file=live_path, thumbnail=base_path
                                )
                            )
                        return
                except Exception as e:
                    # 统一当作媒体构建失败处理
                    logger.warning(f"构建转发媒体片段失败: {type(cont).__name__}: {e}")
                    nodes.append(f"[媒体加载失败：{type(cont).__name__}]")

            # 按 content 顺序遍历
            for item in pr.content:
                if isinstance(item, str):
                    # 文本：保留接口返回的空白和换行，段落边界由原始文本控制
                    append_text(item)
                elif isinstance(item, StickerContent):
                    append_text(item.desc or "[表情]")
                elif isinstance(item, MediaContent) and item.need_send:
                    # 媒体：先输出之前的文本，再输出媒体段
                    await flush_text()
                    await append_media(item)
                elif isinstance(item, LinkContent):
                    await flush_text()
                    if preview := await item.get_preview_path():
                        nodes.append(await UniHelper.img_seg(file=preview))
                    append_text(item.url)
                elif isinstance(item, QuoteContent):
                    quote_parts = [part for part in (item.title, item.text) if part]
                    if item.url:
                        quote_parts.append(item.url)
                    append_text_block("\n".join(quote_parts))
                elif isinstance(item, PollContent):
                    option_vote_total = item.option_vote_total
                    poll_parts = [f"【投票】{item.title or '投票'}"]
                    poll_parts.extend(
                        f"- {option.text}: {option.votes} 票 "
                        f"({item.option_percentage(option, option_vote_total):.1f}%)"
                        for option in item.options
                    )
                    status = ["已结束" if item.closed else "进行中"]
                    if item.multiple:
                        status.append("多选")
                    if item.total_voters is not None:
                        status.append(f"{item.total_voters} 人参与")
                    poll_parts.append(" · ".join(status))
                    append_text_block("\n".join(poll_parts))
                else:
                    # 其他类型暂不处理
                    continue

            # 收尾文本
            await flush_text()
            return nodes

        ordered: list[ForwardNodeInner | _ForwardText] = []
        # 1. 主帖节点
        ordered.extend(await build_nodes(result))
        # 2. 转发内容
        repost = result.repost
        if not repost:
            return ordered
        # 2.1 转发说明
        ordered.append(">>>>>原帖<<<<<")
        # 2.2 原帖节点
        ordered.extend(await build_nodes(repost))
        return ordered

    async def render_image(
        self,
        result: ParseResult,
        *,
        theme: Theme,
        theme_definition: ThemeDefinition | None = None,
    ) -> bytes:
        """使用选定主题绘制卡片"""
        selected_theme = theme_definition or await self._resolve_theme()
        template_data = await self.resolve_parse_result(
            result,
            color_scheme=theme,
            theme_id=selected_theme.id,
        )
        selected_template = await selected_theme.resolve_template(
            str(result.platform.name)
        )

        env = Environment(
            loader=FileSystemLoader(str(selected_template.root)),
            enable_async=True,
            autoescape=False,
        )
        template = env.get_template(selected_template.name)
        html = await template.render_async(data=template_data)
        html = await self._inject_fallback_icon_css(html)

        async with get_new_page(
            2,
            **{
                "viewport": {"width": 620, "height": 1000},
                "base_url": selected_template.base_url,
            },
        ) as page:
            page.on("console", lambda msg: logger.debug(f"浏览器控制台: {msg.text}"))
            await page.goto(selected_template.base_url)
            await page.set_content(html, wait_until="networkidle")
            height = await page.locator("main").evaluate(
                "el => Math.ceil(el.getBoundingClientRect().height)"
            )
            viewport_height = 1000
            # 分段滚动并截图。每段只包含当前视口，避免 full_page 的大位图限制
            segments: list[tuple[int, bytes]] = []
            offsets = list(range(0, max(height - viewport_height, 0), viewport_height))
            final_offset = max(height - viewport_height, 0)
            if not offsets or offsets[-1] != final_offset:
                offsets.append(final_offset)
            for offset in offsets:
                await page.evaluate("y => window.scrollTo(0, y)", offset)
                # 等待滚动位置生效，避免截到上一段内容
                await page.evaluate("() => new Promise(requestAnimationFrame)")
                segments.append(
                    (
                        offset,
                        await page.screenshot(
                            type="png", full_page=False, omit_background=True
                        ),
                    )
                )

        def stitch() -> bytes:
            images = [
                (offset, Image.open(BytesIO(segment)).convert("RGBA"))
                for offset, segment in segments
            ]
            try:
                scale = images[0][1].height / viewport_height
                output_height = round(height * scale)
                canvas = Image.new(
                    "RGBA", (images[0][1].width, output_height), (255, 255, 255, 0)
                )
                for index, (offset, image) in enumerate(images):
                    start = round(offset * scale)
                    end = (
                        output_height
                        if index + 1 == len(images)
                        else round(images[index + 1][0] * scale)
                    )
                    remaining = max(end - start, 0)
                    if remaining <= 0:
                        continue
                    part = image.crop((0, 0, image.width, min(image.height, remaining)))
                    canvas.paste(part, (0, start))
                output = BytesIO()
                canvas.save(output, format="PNG")
                return output.getvalue()
            finally:
                for _, image in images:
                    image.close()

        return await asyncio.to_thread(stitch)

    async def _resolve_theme(self) -> ThemeDefinition:
        return await ThemeManager(
            self.templates_dir,
            pconfig.theme_dirs,
        ).resolve(pconfig.render_theme)

    async def list_themes(self) -> list[ThemeDefinition]:
        """列出当前配置可用的主题"""
        return await ThemeManager(
            self.templates_dir,
            pconfig.theme_dirs,
        ).list_themes()

    async def _inject_fallback_icon_css(self, html: str) -> str:
        """把内置图标样式注入所有主题，供自定义样式覆盖前使用"""
        try:
            icon_css = await (self.templates_dir / "icon.css").read_text(
                encoding="utf-8"
            )
        except OSError as error:
            logger.warning(f"读取内置 icon.css 失败: {error!r}")
            return html

        style = (
            '<style data-parser-fallback="icon-css">\n'
            f"{icon_css}\n"
            "</style>"
        )
        head_match = re.search(r"<head\b[^>]*>", html, flags=re.IGNORECASE)
        if head_match is None:
            return style + html
        index = head_match.end()
        return f"{html[:index]}\n{style}{html[index:]}"

    async def resolve_parse_result(
        self,
        result: ParseResult,
        *,
        color_scheme: Theme | None = None,
        theme_id: str | None = None,
    ) -> ThemeData:
        """解析 ParseResult 为主题 API v1 数据"""
        selected_theme_id = theme_id or (await self._resolve_theme()).id
        return await build_theme_data(
            result,
            color_scheme=color_scheme or get_theme(),
            theme_id=selected_theme_id,
            bot_name=_nickname,
            max_comments=pconfig.max_comments,
            append_qrcode=pconfig.append_qrcode,
        )

    async def cache_or_render_image(self, result: ParseResult):
        """获取缓存图片（支持跨重启复用）

        以当前主题和解析结果 URL 为 key，在 cache_dir 下生成稳定文件名：
        - 若文件已存在：直接使用，不再重新渲染
        - 若不存在：渲染并写入该文件
        """
        theme = get_theme()
        selected_theme = await self._resolve_theme()
        cache_key = (
            f"{RENDER_TEMPLATE_VERSION}:{selected_theme.id}:"
            f"{selected_theme.version}:{theme}:{result.url}"
        )
        file_name = f"{uuid.uuid5(uuid.NAMESPACE_URL, cache_key)}.webp"
        cache_dir = await CacheManager.ensure_dir(CacheManager.RENDER)
        image_path = cache_dir / file_name
        logger.info(f"渲染主题: {selected_theme.name}")
        if not await image_path.exists():
            image_raw = await FFmpeg.png_to_webp(
                await self.render_image(
                    result,
                    theme=theme,
                    theme_definition=selected_theme,
                ),
            )
            temp_path = image_path.with_name(
                f".{image_path.stem}.{uuid.uuid4().hex}.tmp{image_path.suffix}"
            )
            try:
                await temp_path.write_bytes(image_raw)
                await temp_path.replace(image_path)
            finally:
                await temp_path.unlink(missing_ok=True)
        result.render_image = image_path
        if (await image_path.stat()).st_size >= 5 * 1024 * 1024:
            return await UniHelper.file_seg(image_path)

        return await UniHelper.img_seg(image_path)


RENDERER = Renderer()
