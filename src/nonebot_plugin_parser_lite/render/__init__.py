import asyncio
from collections.abc import AsyncGenerator
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
from ..helper import ForwardNodeInner, UniHelper, UniMessage, mark_media_role
from ..utils.cache import CacheManager
from ..utils.ffmpeg import FFmpeg
from ..utils.message import (
    MAX_FORWARD_NODES as MAX_FORWARD_NODES,
)
from ..utils.message import (
    MAX_FORWARD_TEXT_LEN as MAX_FORWARD_TEXT_LEN,
)
from ..utils.message import (
    MessageText,
    TextPart,
    append_message_part,
    pack_forward_nodes,
)
from ..utils.message import (
    split_text_by_length_with_punct as split_text_by_length_with_punct,
)
from .context import PLACEHOLDER_IMAGE, ThemeData, build_theme_data, safe_src
from .theme import ThemeDefinition, ThemeManager

__all__ = ["PLACEHOLDER_IMAGE", "ThemeData", "ThemeManager", "safe_src"]

SPLIT_THRESHOLD = pconfig.forward_text_threshold
"""单段文本拆分阈值"""
IS_DEBUG = gconfig.log_level in ["DEBUG", "TRACE", 10, 5]
RENDER_TEMPLATE_VERSION = "20260923-1"

Theme = Literal["light", "dark"]


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
        if image_seg is not None:
            mark_media_role(image_seg, "summary")
        msg = UniMessage(image_seg or "图片渲染失败")
        if pconfig.append_url:
            urls = (result.display_url, result.repost_display_url)
            msg += "\n".join(url for url in urls if url)
        if pconfig.embed_url:
            if embed := result.embed_url:
                msg += "\n在线播放: " + embed
        return msg

    async def send_content(
        self,
        result: ParseResult,
        summary_node: UniMessage[Any] | None = None,
    ) -> AsyncGenerator[UniMessage[Any], None]:
        """发送媒体内容消息

        将解析结果中的媒体内容拆分为：
        - 需要立即发送的音视频（逐条 yield）或待合并转发的视频
        - 可选的总结卡片（作为合并转发首节点）
        - 可合并转发的图文 / 图片（统一收集后一次发送）
        """
        failed_count = 0
        deferred_media_segs: dict[int, list[UniMessage[Any]]] = {}
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
                    if summary_node is None:
                        yield msg
                    else:
                        deferred_media_segs.setdefault(id(cont), []).append(msg)
            except SizeLimitException:
                message = UniMessage(
                    f"媒体太大啦，还是去{result.platform.display_name}看看吧~"
                )
                if summary_node is None:
                    yield message
                else:
                    deferred_media_segs.setdefault(id(cont), []).append(message)
                continue
            except DownloadException as e:
                failed_count += 1
                logger.exception(f"{cont.__class__.__name__} 下载失败: {e!r}")
                continue

        # 2 构建图文 / 图片的转发列表（含主帖 + 转发，按顺序）
        ordered_segs = await self.__build_forward_segs(
            result,
            forward_video_segs,
            deferred_media_segs,
        )
        if summary_node is not None:
            ordered_segs.insert(0, summary_node)
        effective_segs = [
            seg
            for seg in ordered_segs
            if not isinstance(seg, MessageText) or seg.text.strip()
        ]
        if effective_segs:
            total_plain_len = sum(
                len(seg.text)
                if isinstance(seg, MessageText)
                else len(UniMessage(seg).extract_plain_text())
                for seg in effective_segs
            )
            need_forward = (
                pconfig.need_forward_contents
                or total_plain_len > SPLIT_THRESHOLD
                or len(effective_segs) > 4
                or bool(forward_video_segs)
                or summary_node is not None
            )
            if not need_forward:
                message = UniMessage()
                previous_separate = False
                for seg in ordered_segs:
                    separate = isinstance(seg, MessageText) and seg.separate
                    append_message_part(
                        message,
                        seg.to_message() if isinstance(seg, MessageText) else seg,
                        separate=previous_separate or separate,
                    )
                    previous_separate = separate
                yield message
            else:
                segments = [
                    seg.to_message() if isinstance(seg, MessageText) else seg
                    for seg in effective_segs
                ]
                reference = UniHelper.construct_forward_message(segments)
                for nodes in pack_forward_nodes(reference.children, SPLIT_THRESHOLD):
                    yield UniMessage(type(reference)(nodes=nodes))

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
            segment = await UniHelper.file_seg(video_path)
            mark_media_role(segment, "video")
            return segment
        return await UniHelper.video_seg(
            file=video_path, thumbnail=await cont.get_cover_path()
        )

    @staticmethod
    def __format_quote(item: QuoteContent) -> str:
        parts = [part for part in (item.title, item.text) if part]
        if item.url:
            parts.append(item.url)
        return "\n".join(parts)

    @staticmethod
    def __format_poll(item: PollContent) -> str:
        option_vote_total = item.option_vote_total
        parts = [f"【投票】{item.title or '投票'}"]
        parts.extend(
            f"- {option.text}: {option.votes} 票 "
            f"({item.option_percentage(option, option_vote_total):.1f}%)"
            for option in item.options
        )
        status = ["已结束" if item.closed else "进行中"]
        if item.multiple:
            status.append("多选")
        if item.total_voters is not None:
            status.append(f"{item.total_voters} 人参与")
        if item.close_at:
            status.append(f"截止 {item.close_at}")
        parts.append(" · ".join(status))
        return "\n".join(parts)

    async def __append_forward_video(
        self,
        cont: VideoContent,
        nodes: list[ForwardNodeInner | MessageText],
        forward_video_segs: dict[int, ForwardNodeInner],
        deferred_media_segs: dict[int, list[UniMessage[Any]]],
    ) -> None:
        cover_in_forward = False
        try:
            path = await cont.get_cover_path()
            if path:
                nodes.append(await UniHelper.img_seg(file=path))
                cover_in_forward = True
        except Exception as e:
            logger.warning(f"构建转发媒体片段失败: {type(cont).__name__}: {e}")
            nodes.append(f"[媒体加载失败：{type(cont).__name__}]")

        video_seg = forward_video_segs.get(id(cont))
        if video_seg is not None:
            if cover_in_forward and getattr(video_seg, "thumbnail", None):
                setattr(video_seg, "_parser_lite_cover_in_forward", True)
            nodes.append(video_seg)
            return

        deferred_segs = deferred_media_segs.get(id(cont), ())
        if cover_in_forward:
            for deferred_seg in deferred_segs:
                for segment in deferred_seg:
                    if getattr(segment, "thumbnail", None):
                        setattr(segment, "_parser_lite_cover_in_forward", True)
        nodes.extend(deferred_segs)

    async def __append_forward_media(
        self,
        cont: MediaContent,
        nodes: list[ForwardNodeInner | MessageText],
        forward_video_segs: dict[int, ForwardNodeInner],
        deferred_media_segs: dict[int, list[UniMessage[Any]]],
    ) -> None:
        if isinstance(cont, VideoContent):
            await self.__append_forward_video(
                cont, nodes, forward_video_segs, deferred_media_segs
            )
            return

        if deferred_segs := deferred_media_segs.get(id(cont)):
            nodes.extend(deferred_segs)
            return

        try:
            if isinstance(cont, ImageContent):
                nodes.append(await UniHelper.img_seg(await cont.get_path()))
                return

            if isinstance(cont, GraphicContent):
                seg: ForwardNodeInner = await UniHelper.img_seg(await cont.get_path())
                if cont.alt:
                    seg = seg + cont.alt
                nodes.append(seg)
                return

            if isinstance(cont, LivePhotoContent):
                if pconfig.live_photo:
                    nodes.append(
                        await UniHelper.video_seg(
                            file=await cont.get_live(), thumbnail=await cont.get_base()
                        )
                    )
                    return

                base_path = await cont.get_base()
                nodes.append(await UniHelper.img_seg(base_path))
                video_seg = await UniHelper.video_seg(
                    file=await cont.get_path(), thumbnail=base_path
                )
                if getattr(video_seg, "thumbnail", None):
                    setattr(video_seg, "_parser_lite_cover_in_forward", True)
                nodes.append(video_seg)
        except Exception as e:
            logger.warning(f"构建转发媒体片段失败: {type(cont).__name__}: {e}")
            nodes.append(f"[媒体加载失败：{type(cont).__name__}]")

    async def __build_forward_segs(
        self,
        result: ParseResult,
        forward_video_segs: dict[int, ForwardNodeInner],
        deferred_media_segs: dict[int, list[UniMessage[Any]]],
    ) -> list[ForwardNodeInner | MessageText]:
        """根据当前内容和转发内容构造有序的转发段列表（文本 + 媒体，保持顺序）

        规则：
        - 主帖：
          - 文本片段按顺序聚合，输出 "作者：文本" 节点
          - 媒体片段（Image/Graphic/LivePhoto/Video 封面等）按出现顺序插入对应消息段
        - 如有转发：
          - 插入一条说明
          - 然后对转发 ParseResult 做同样处理
        """

        async def build_nodes(pr: ParseResult) -> list[ForwardNodeInner | MessageText]:
            author_name = pr.author.name
            nodes: list[ForwardNodeInner | MessageText] = []
            text_buffer: list[TextPart] = []
            author_prefix_pending = True
            if (title := pr.title) and title.strip():
                nodes.append(
                    MessageText(author_name, [TextPart(title)], False, separate=True)
                )

            async def flush_text() -> None:
                nonlocal author_prefix_pending, text_buffer
                if text_buffer:
                    has_text = any(part.text.strip() for part in text_buffer)
                    nodes.append(
                        MessageText(
                            author_name,
                            text_buffer,
                            include_author=author_prefix_pending and has_text,
                        )
                    )
                    if has_text:
                        author_prefix_pending = False
                    text_buffer = []

            def append_text_block(text: str) -> None:
                """将块级文本加入当前文本段，并与相邻内容换行分隔"""
                if not text:
                    return
                text_buffer.append(TextPart(text, block=True, keep_together=True))

            # 按 content 顺序遍历
            for item in pr.content:
                if isinstance(item, str):
                    # 文本：保留接口返回的空白和换行，段落边界由原始文本控制
                    text_buffer.append(TextPart(item))
                    continue
                if isinstance(item, StickerContent):
                    text_buffer.append(TextPart(item.desc or "[表情]"))
                    continue
                if isinstance(item, MediaContent):
                    if not item.need_send:
                        continue
                    await flush_text()
                    await self.__append_forward_media(
                        item, nodes, forward_video_segs, deferred_media_segs
                    )
                    continue
                if isinstance(item, LinkContent):
                    await flush_text()
                    if preview := await item.get_preview_path():
                        nodes.append(await UniHelper.img_seg(file=preview))
                    text_buffer.append(TextPart(item.url))
                    continue
                if isinstance(item, QuoteContent):
                    append_text_block(self.__format_quote(item))
                    continue
                if isinstance(item, PollContent):
                    if any(option.image is not None for option in item.options):
                        await flush_text()
                        for option in item.options:
                            try:
                                if path := await option.get_image_path():
                                    nodes.append(await UniHelper.img_seg(file=path))
                            except Exception as e:
                                logger.warning(f"投票选项图片获取失败: {e!r}")
                    append_text_block(self.__format_poll(item))

            # 收尾文本
            await flush_text()
            return nodes

        ordered: list[ForwardNodeInner | MessageText] = []
        # 1. 主帖节点
        ordered.extend(await build_nodes(result))
        # 2. 转发内容
        repost = result.repost
        if not repost:
            return ordered
        # 2.1 转发说明
        ordered.append(
            MessageText("", [TextPart(">>>>>原帖<<<<<")], False, separate=True)
        )
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

        style = f'<style data-parser-fallback="icon-css">\n{icon_css}\n</style>'
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
