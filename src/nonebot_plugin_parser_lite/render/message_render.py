"""消息编排：将解析结果转换为可发送/合并转发的消息序列"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from anyio import Path
from nonebot import logger
from nonebot_plugin_alconna.uniseg import File, Image

from ..config import pconfig
from ..constants import SendComponent
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
from ..exception import DownloadException, SizeLimitException
from ..helper import ForwardNodeInner, UniHelper, UniMessage, mark_media_role
from .forward import (
    SPLIT_THRESHOLD,
    _ForwardText,
    _ForwardTextPart,
    pack_forward_items,
    split_forward_content,
)


@dataclass(slots=True)
class _SendState:
    """``send_content`` 遍历媒体时的累积状态"""

    failed_count: int = 0
    deferred_media_segs: dict[int, list[UniMessage[Any]]] = field(default_factory=dict)
    forward_video_segs: dict[int, ForwardNodeInner] = field(default_factory=dict)


class MessageRenderMixin:
    """提供解析结果到消息序列的编排能力"""

    if TYPE_CHECKING:
        # 由 ImageRenderMixin 提供，组合进 Renderer 后可用
        async def cache_or_render_image(
            self, result: ParseResult
        ) -> File | Image: ...

    async def render_messages(self, result: ParseResult) -> UniMessage[Any]:
        """按配置构建总结卡片和链接消息"""
        msg = UniMessage()
        components = pconfig.send_components
        if pconfig.card_delivery != "off":
            try:
                image_seg = await self.cache_or_render_image(result)
            except Exception as e:
                logger.exception(f"获取图片路径失败: {e!r}")
                image_seg = None
            if image_seg is not None:
                mark_media_role(image_seg, "summary")
            msg += image_seg or "图片渲染失败"
        if SendComponent.URL in components:
            urls = (result.display_url, result.repost_display_url)
            if links := "\n".join(url for url in urls if url):
                msg += links
        if SendComponent.EMBED in components and (embed := result.embed_url):
            msg += ("\n" if msg else "") + "在线播放: " + embed
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
        state = _SendState()
        async for message in self.__collect_media(result, summary_node, state):
            yield message

        ordered_segs = await self.__build_forward_segs(
            result, state.forward_video_segs, state.deferred_media_segs
        )
        if summary_node is not None:
            ordered_segs.insert(0, summary_node)
        for message in self.__pack_forward_messages(
            ordered_segs, state.forward_video_segs, summary_node
        ):
            yield message

        if state.failed_count > 0:
            message = f"{state.failed_count} 项媒体下载失败"
            yield UniMessage(message)
            logger.warning(message)

    async def __collect_media(
        self,
        result: ParseResult,
        summary_node: UniMessage[Any] | None,
        state: "_SendState",
    ) -> AsyncGenerator[UniMessage[Any], None]:
        """遍历媒体，立即发送的逐条 yield，待转发的收集进 state"""
        components = pconfig.send_components
        forward = pconfig.forward_components.intersection(components)

        def collect(cont: MediaContent, message: UniMessage[Any]) -> None:
            state.deferred_media_segs.setdefault(id(cont), []).append(message)

        for cont in result.iter_sendable_media():
            if isinstance(cont, VideoContent) and SendComponent.VIDEO not in components:
                continue
            if isinstance(cont, AudioContent) and SendComponent.AUDIO not in components:
                continue
            try:
                if (
                    isinstance(cont, VideoContent)
                    and SendComponent.VIDEO in forward
                ):
                    state.forward_video_segs[id(cont)] = await self.__build_video_seg(
                        cont
                    )
                    continue
                async for message in self.__handle_immediate_media(cont):
                    if summary_node is None:
                        yield message
                    else:
                        collect(cont, message)
            except SizeLimitException:
                message = UniMessage(
                    f"媒体太大啦，还是去{result.platform.display_name}看看吧~"
                )
                if summary_node is None:
                    yield message
                else:
                    collect(cont, message)
            except DownloadException as e:
                state.failed_count += 1
                logger.exception(f"{cont.__class__.__name__} 下载失败: {e!r}")

    def __pack_forward_messages(
        self,
        ordered_segs: list[ForwardNodeInner | _ForwardText],
        forward_video_segs: dict[int, ForwardNodeInner],
        summary_node: UniMessage[Any] | None,
    ) -> list[UniMessage[Any]]:
        """将有序段按长文本拆分，并视情况打包为合并转发消息"""
        if not ordered_segs:
            return []

        processed_segs: list[ForwardNodeInner] = []
        total_plain_len = 0
        for seg in ordered_segs:
            if isinstance(seg, _ForwardText):
                total_plain_len += seg.text_length
            elif isinstance(seg, str):
                total_plain_len += len(seg)
            processed_segs.extend(split_forward_content(seg, SPLIT_THRESHOLD))

        if not self.__need_forward(
            ordered_segs, total_plain_len, forward_video_segs, summary_node
        ):
            return [UniMessage(processed_segs)]

        # 需要合并转发：根据平台限制按文本长度 / 节点数分批构造 forward
        return [
            UniMessage(UniHelper.construct_forward_message(chunk))
            for chunk in pack_forward_items(
                processed_segs,
                content_of=lambda content: content,
                with_content=lambda _original, content: content,
            )
        ]

    @staticmethod
    def __need_forward(
        ordered_segs: list[ForwardNodeInner | _ForwardText],
        total_plain_len: int,
        forward_video_segs: dict[int, ForwardNodeInner],
        summary_node: UniMessage[Any] | None,
    ) -> bool:
        """判断是否需要合并转发

        满足任一条件即合并：
        - forward_components 含 content / cover（正文体进转发）
        - 纯文字部分超过阈值
        - 节点数较多
        - 包含 forward_components 指定并入转发的视频
        - 总结卡片指定为首节点
        """
        components = pconfig.send_components
        forward = pconfig.forward_components.intersection(components)
        body_in_forward = bool(forward & {SendComponent.CONTENT, SendComponent.COVER})
        return (
            body_in_forward
            or total_plain_len > SPLIT_THRESHOLD
            or len(ordered_segs) > 4
            or bool(forward_video_segs)
            or summary_node is not None
        )

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
        thumbnail = (
            await cont.get_cover_path()
            if SendComponent.COVER in pconfig.send_components
            else None
        )
        return await UniHelper.video_seg(file=video_path, thumbnail=thumbnail)

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
        nodes: list[ForwardNodeInner | _ForwardText],
        forward_video_segs: dict[int, ForwardNodeInner],
        deferred_media_segs: dict[int, list[UniMessage[Any]]],
    ) -> None:
        cover_in_forward = False
        if SendComponent.COVER in pconfig.send_components:
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
        nodes: list[ForwardNodeInner | _ForwardText],
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
                if SendComponent.CONTENT in pconfig.send_components:
                    nodes.append(await UniHelper.img_seg(await cont.get_path()))
                return

            if isinstance(cont, GraphicContent):
                if SendComponent.CONTENT not in pconfig.send_components:
                    return
                seg: ForwardNodeInner = await UniHelper.img_seg(await cont.get_path())
                if cont.alt:
                    seg = seg + cont.alt
                nodes.append(seg)
                return

            if isinstance(cont, LivePhotoContent):
                if SendComponent.CONTENT not in pconfig.send_components:
                    return
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
            send_text = SendComponent.CONTENT in pconfig.send_components
            if send_text and (title := pr.title):
                nodes.append(
                    _ForwardText(author_name, [_ForwardTextPart(f"{title}\n")], False)
                )

            async def flush_text() -> None:
                nonlocal author_prefix_pending, text_buffer
                if text_buffer and send_text:
                    nodes.append(
                        _ForwardText(
                            author_name,
                            text_buffer,
                            include_author=author_prefix_pending,
                        )
                    )
                    author_prefix_pending = False
                text_buffer = []

            def append_text_block(text: str) -> None:
                """将块级文本加入当前文本段，并与相邻内容换行分隔"""
                if not text:
                    return
                if text_buffer and not text_buffer[-1].text.endswith("\n"):
                    text_buffer.append(_ForwardTextPart("\n"))
                text_buffer.append(_ForwardTextPart(f"{text}\n", protected=True))

            # 按 content 顺序遍历
            for item in pr.content:
                if isinstance(item, MediaContent):
                    if not item.need_send:
                        continue
                    await flush_text()
                    await self.__append_forward_media(
                        item, nodes, forward_video_segs, deferred_media_segs
                    )
                    continue
                if not send_text:
                    continue
                if isinstance(item, str):
                    # 文本：保留接口返回的空白和换行，段落边界由原始文本控制
                    text_buffer.append(_ForwardTextPart(item))
                    continue
                if isinstance(item, StickerContent):
                    text_buffer.append(_ForwardTextPart(item.desc or "[表情]"))
                    continue
                if isinstance(item, LinkContent):
                    await flush_text()
                    if preview := await item.get_preview_path():
                        nodes.append(await UniHelper.img_seg(file=preview))
                    text_buffer.append(_ForwardTextPart(item.url))
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

        ordered: list[ForwardNodeInner | _ForwardText] = []
        # 1. 主帖节点
        ordered.extend(await build_nodes(result))
        # 2. 转发内容
        if result.repost and (repost_nodes := await build_nodes(result.repost)):
            ordered.append("原帖")
            ordered.extend(repost_nodes)
        return ordered
