import base64
from collections.abc import AsyncGenerator, Awaitable
import datetime
from io import BytesIO
from itertools import chain
import traceback
from typing import Any, ClassVar
import uuid

from anyio import Path
from nonebot import logger
from nonebot_plugin_htmlrender import template_to_pic
import qrcode

from ..config import _nickname, pconfig
from ..exception import (
    DownloadException,
    DurationLimitException,
    SizeLimitException,
)
from ..helper import ForwardNodeInner, UniHelper, UniMessage
from ..parsers.data import (
    AudioContent,
    GraphicContent,
    ImageContent,
    LivePhotoContent,
    MediaContent,
    ParseResult,
    StickerContent,
    VideoContent,
)

PLACEHOLDER_IMAGE = (
    "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)
SPLIT_THRESHOLD = pconfig.forward_text_threshold
"""单段文本拆分阈值"""
MAX_FORWARD_TEXT_LEN = 4500
"""单个 forward 文本总长上限"""
MAX_FORWARD_NODES = 90
"""单个 forward 节点数上限"""


def split_text_by_length_with_punct(text: str, max_len: int) -> list[str]:
    """按长度切分文本，优先在标点符号处断句。

    规则：
    1. 遍历文本，当前段长度超过 max_len 时：
       - 尝试在当前段中最后一个标点符号后断句；
       - 若找不到合适标点，则在 max_len 处硬切。
    2. 支持中英文常用标点。

    :param text: 原始文本
    :param max_len: 每段最大长度
    :return: 切分后的文本段列表
    """
    if max_len <= 0 or len(text) <= max_len:
        return [text]

    # 常见句末/停顿标点（中英文）
    puncts = "。！？!?；;，,、…"
    result: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        # 预算本段的理论结束位置
        end = min(start + max_len, length)
        segment = text[start:end]

        if end == length:
            # 已到末尾，直接收尾
            result.append(segment)
            break

        cut_pos = next(
            (i + 1 for i in range(len(segment) - 1, -1, -1) if segment[i] in puncts),
            -1,
        )
        if cut_pos <= 0:
            # 没找到合适标点，直接在 max_len 处切
            result.append(segment)
            start = end
        else:
            # 在标点后断句
            result.append(segment[:cut_pos])
            start += cut_pos

    return [seg for seg in result if seg]


async def safe_src(obj: Any, method: str = "get_path") -> str:
    """
    通用安全资源获取过滤器

    用法：
        {{ cont | safe_src }}                    # 默认调用 get_path()
        {{ cont | safe_src("get_base") }}        # 调用 get_base()
        {{ cont | safe_src("get_cover_path") }}  # 调用 get_cover_path()
        {{ author | safe_src("get_avatar_path") }} # 调用 get_avatar_path()
    """
    try:
        if not hasattr(obj, method):
            logger.warning(f"对象 {type(obj).__name__} 不存在方法 '{method}'")
            return PLACEHOLDER_IMAGE

        method_attr = getattr(obj, method)

        if not callable(method_attr):
            logger.warning(f"{type(obj).__name__} 的属性 '{method}' 不是可调用对象")
            return PLACEHOLDER_IMAGE

        call_result: Path | Awaitable[Path] = method_attr()  # type: ignore[assignment]

        src = await call_result if isinstance(call_result, Awaitable) else call_result
        return src.as_uri() if src else PLACEHOLDER_IMAGE
    except Exception as e:
        logger.warning(f"safe_src({method}) 处理 {type(obj).__name__} 时失败: {e}")
        return PLACEHOLDER_IMAGE


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
        except Exception:
            logger.error(f"获取图片路径失败: {traceback.format_exc()}")
            image_seg = None

        # 尝试直接发送图片
        msg = UniMessage(image_seg or "图片渲染失败")
        if pconfig.append_url:
            urls = (result.display_url, result.repost_display_url)
            msg += "\n".join(url for url in urls if url)
        return msg

    async def send_content(
        self, result: ParseResult
    ) -> AsyncGenerator[UniMessage[Any], None]:
        """发送媒体内容消息。

        将解析结果中的媒体内容拆分为：
        - 需要立即发送的音视频（逐条 yield）
        - 可合并转发的图文 / 图片（统一收集后一次发送）
        """
        failed_count = 0
        repost_medias = result.repost.content if result.repost else []
        media_contents = [
            cont
            for cont in chain(result.content, repost_medias)
            if isinstance(cont, MediaContent) and cont.need_send
        ]
        for cont in media_contents:
            # 先处理需要立即发送的音视频
            try:
                async for msg in self.__handle_immediate_media(cont):
                    yield msg
            except SizeLimitException as e:
                yield UniMessage(
                    f"设定的最大上传大小为 {pconfig.max_size}MB\n"
                    f"当前解析到的媒体大小为 {e.size}MB\n"
                    "媒体太大了~"
                )
                continue
            except DurationLimitException as e:
                yield UniMessage(
                    f"设定的最大时长为 {pconfig.duration_maximum}s\n"
                    f"当前解析到的媒体时长为 {e.duration}s\n"
                    "媒体太长了~"
                )
            except DownloadException:
                failed_count += 1
                continue

        # 2 构建图文 / 图片的转发列表（含主帖 + 转发，按顺序）
        ordered_segs = await self.__build_forward_segs(result)
        if ordered_segs:
            # 一次遍历：统计+长文本拆分
            processed_segs: list[ForwardNodeInner] = []
            total_plain_len = 0
            node_count = 0

            for seg in ordered_segs:
                node_count += 1
                if isinstance(seg, str):
                    seg_len = len(seg)
                    total_plain_len += seg_len
                    if seg_len > SPLIT_THRESHOLD:
                        parts = split_text_by_length_with_punct(seg, SPLIT_THRESHOLD)
                        for part in parts:
                            if not part:
                                continue
                            processed_segs.append(part)
                    else:
                        processed_segs.append(seg)
                else:
                    processed_segs.append(seg)

            # 是否需要合并转发：
            # 1) 配置项 need_forward_contents
            # 2) 纯文字部分超过阈值
            # 3) 节点数较多
            need_forward = (
                pconfig.need_forward_contents
                or total_plain_len > SPLIT_THRESHOLD
                or node_count > 4
            )

            if not need_forward:
                # 不走合并转发：直接按节点顺序发出
                yield UniMessage(processed_segs)
            else:
                # 需要合并转发：根据平台限制按文本长度 / 节点数分批构造 forward
                current_chunk: list[ForwardNodeInner] = []
                current_text_len = 0
                current_nodes = 0

                def flush_chunk() -> UniMessage[Any] | None:
                    nonlocal current_chunk, current_text_len, current_nodes
                    if not current_chunk:
                        return None
                    msg = UniMessage(UniHelper.construct_forward_message(current_chunk))
                    current_chunk.clear()
                    current_text_len = 0
                    current_nodes = 0
                    return msg

                for seg in processed_segs:
                    seg_text_len = len(seg) if isinstance(seg, str) else 0

                    # 如果加上当前节点会超出单个 forward 限制，则先 flush 当前 chunk
                    if current_chunk and (
                        current_text_len + seg_text_len > MAX_FORWARD_TEXT_LEN
                        or current_nodes + 1 > MAX_FORWARD_NODES
                    ):
                        msg = flush_chunk()
                        if msg is not None:
                            yield msg

                    current_chunk.append(seg)
                    current_text_len += seg_text_len
                    current_nodes += 1

                # 收尾：还有未发送的 chunk
                last_msg = flush_chunk()
                if last_msg is not None:
                    yield last_msg

        # 汇总下载失败信息
        if failed_count > 0:
            message = f"{failed_count} 项媒体下载失败"
            yield UniMessage(message)
            raise DownloadException(message)

    async def __handle_immediate_media(
        self, cont: MediaContent
    ) -> AsyncGenerator[UniMessage[Any], None]:
        """
        处理需要立即发送的音视频媒体，返回对应的消息段

        :raise ZeroSizeException: 资源大小为 0 时抛出
        :raise SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raise DurationLimitException: 媒体时长超过配置的最大限制时抛出
        :raise DownloadException: 重试多次仍失败时抛出
        """
        if not isinstance(cont, (VideoContent, AudioContent)):
            return
        if cont.duration > pconfig.duration_maximum:
            raise DurationLimitException(cont.duration)

        path = await cont.get_path()
        if (isinstance(cont, VideoContent) and pconfig.need_upload_video) or (
            not isinstance(cont, VideoContent)
            and isinstance(cont, AudioContent)
            and pconfig.need_upload_audio
        ):
            yield UniMessage(await UniHelper.file_seg(path))
        elif isinstance(cont, VideoContent):
            yield UniMessage(await UniHelper.video_seg(path))
        elif isinstance(cont, AudioContent):
            yield UniMessage(await UniHelper.record_seg(path))

    async def __build_forward_segs(
        self,
        result: ParseResult,
    ) -> list[ForwardNodeInner]:
        """根据当前内容和转发内容构造有序的转发段列表（文本 + 媒体，保持顺序）

        规则：
        - 主帖：
          - 文本片段按顺序聚合，输出 "作者：文本" 节点
          - 媒体片段（Image/Graphic/LivePhoto/Video 封面等）按出现顺序插入对应消息段
        - 如有转发：
          - 插入一条说明
          - 然后对转发 ParseResult 做同样处理
        """

        async def build_nodes(pr: ParseResult) -> list[ForwardNodeInner]:
            author_name = pr.author.name
            nodes: list[ForwardNodeInner] = []
            text_buffer: list[str] = []

            async def flush_text() -> None:
                nonlocal text_buffer
                if text_buffer:
                    text = "\n".join(text_buffer).strip()
                    if text:
                        nodes.append(f"{author_name}：{text}")
                    text_buffer = []

            async def append_media(cont: MediaContent) -> None:
                """将单个媒体内容转换为若干 ForwardNodeInner，并追加到 nodes"""
                try:
                    # 视频：使用封面图作为转发节点
                    if isinstance(cont, VideoContent):
                        path = await cont.get_cover_path()
                        if path:
                            nodes.append(await UniHelper.img_seg(path))
                        return

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
                            nodes.append(await UniHelper.video_seg(live_path))
                        else:
                            base_path = await cont.get_base()
                            live_path = await cont.get_path()
                            nodes.append(await UniHelper.img_seg(base_path))
                            nodes.append(await UniHelper.video_seg(live_path))
                        return
                except Exception as e:
                    # 统一当作媒体构建失败处理
                    logger.warning(f"构建转发媒体片段失败: {type(cont).__name__}: {e}")
                    nodes.append(f"[媒体加载失败：{type(cont).__name__}]")

            # 按 content 顺序遍历
            for item in pr.content:
                if isinstance(item, str):
                    # 文本：缓冲，遇到媒体或结束时 flush
                    if item:
                        text_buffer.append(item)
                elif isinstance(item, StickerContent):
                    text_buffer.append(item.desc or "[表情]")
                elif isinstance(item, MediaContent) and item.need_send:
                    # 媒体：先输出之前的文本，再输出媒体段
                    await flush_text()
                    await append_media(item)
                else:
                    # 其他类型暂不处理
                    continue

            # 收尾文本
            await flush_text()
            return nodes

        ordered: list[ForwardNodeInner] = []
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

    async def render_image(self, result: ParseResult) -> bytes:
        """使用 HTML 绘制通用社交媒体帖子卡片"""
        # 准备模板数据
        template_data = await self.resolve_parse_result(result)

        # 处理模板针对
        template_name = "default.html.jinja"
        if result.platform:
            # 音乐平台使用音乐模板
            music_platforms = ["kugou", "netease", "kuwo", "qsmusic"]
            platform_name = result.platform.name.lower()

            if platform_name in music_platforms:
                template_name = "music.html.jinja"
            else:
                # 其他平台使用各自的模板
                file_name = f"{platform_name}.html.jinja"
                if await (self.templates_dir / file_name).exists():
                    template_name = file_name

        # from jinja2 import FileSystemLoader, Environment

        # # 创建一个包加载器对象
        # env = Environment(
        #     loader=FileSystemLoader(self.templates_dir),
        #     enable_async=True,
        # )
        # env.filters["safe_src"] = safe_src
        # template = env.get_template(template_name)
        # # 渲染
        # with open(
        #     f"{self.templates_dir.parent.parent}/{datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')}.html",  # noqa: E501
        #     "w",
        #     encoding="utf8",
        # ) as f:
        #     f.write(
        #         await template.render_async(result=template_data)
        #     )

        return await template_to_pic(
            template_path=str(self.templates_dir),
            template_name=template_name,
            templates={
                "result": template_data,
            },
            pages={
                "viewport": {"width": 620, "height": 100},
                "base_url": f"file://{self.templates_dir}",
            },
            filters={"safe_src": safe_src},
            type="jpeg",
            quality=85,
        )

    async def resolve_parse_result(self, result: ParseResult) -> dict[str, Any]:
        """解析 ParseResult 为模板可用的字典数据"""

        data: dict[str, Any] = {
            "title": result.title,
            "formatted_datetime": result.formatted_datetime,
            "extra": result.extra,
            "platform": {
                "display_name": result.platform.display_name,
                "name": result.platform.name,
                "logo_path": await safe_src(result.platform, "get_logo_path"),
            },
            "content": result.content,
            "cover_path": await safe_src(result, "get_cover_path"),
            "stats": result.stats,
            "comments": result.comments[: pconfig.max_comments],
            "author": {
                "name": result.author.name,
                "id": result.author.id,
                "avatar_path": await safe_src(result.author, "get_avatar_path"),
            },
            "ai_summary": result.ai_summary,
            "rendering_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bot_name": _nickname,
        }

        if result.repost:
            data["repost"] = await self.resolve_parse_result(result.repost)

        if pconfig.append_qrcode:
            qr = qrcode.QRCode(
                version=1,
                error_correction=1,
                box_size=10,
                border=1,
            )
            qr.add_data(result.url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")  # pyright: ignore[reportCallIssue]
            buffer.seek(0)
            img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            data["qrcode_path"] = f"data:image/png;base64,{img_base64}"

        return data

    async def cache_or_render_image(self, result: ParseResult):
        """获取缓存图片（支持跨重启复用）

        以解析结果的 URL（或其他稳定字段）为 key，在 cache_dir 下生成稳定文件名：
        - 若文件已存在：直接使用，不再重新渲染
        - 若不存在：渲染并写入该文件
        """
        cache_key = result.url
        file_name = f"{uuid.uuid5(uuid.NAMESPACE_URL, cache_key)}.jpeg"
        image_path = pconfig.cache_dir / file_name
        if await image_path.exists():
            result.render_image = image_path
        else:
            image_raw = await self.render_image(result)
            await image_path.write_bytes(image_raw)
            result.render_image = image_path
            if pconfig.use_base64:
                return await UniHelper.img_seg(image_raw)
        if (await image_path.stat()).st_size >= 5 * 1024 * 1024:
            return await UniHelper.file_seg(image_path)

        return await UniHelper.img_seg(image_path)


RENDERER = Renderer()
