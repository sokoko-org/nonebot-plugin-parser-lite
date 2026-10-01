"""合并转发媒体上传失败时，保留失败分包的文字与来源"""

from copy import deepcopy
from dataclasses import dataclass, replace
import re
from typing import cast

from nonebot import logger
from nonebot.exception import ActionFailed
from nonebot_plugin_alconna.uniseg import (
    CustomNode,
    Image,
    Reference,
    Segment,
    Text,
    UniMessage,
)
from nonebot_plugin_alconna.uniseg.segment import Media

from .config import pconfig
from .data import ParseResult
from .helper import media_role
from .utils.message import (
    MAX_FORWARD_NODES,
    MAX_FORWARD_TEXT_LEN,
    append_message_part,
    message_segments,
    pack_forward_nodes,
)

SPLIT_THRESHOLD = pconfig.forward_text_threshold


# 仅匹配协议端明确透传的媒体上传错误，不能仅凭 retcode 或普通超时降级
_UPLOAD_ERROR = re.compile(
    r"\bHTTP Upload failed with code \d+\b"
    r"|\brich media transfer failed\b"
    r"|\bHighway request timeout\b",
    re.IGNORECASE,
)
_ERROR_FIELDS = ("message", "wording", "msg")
_MEDIA_LABELS = {
    "image": "图片",
    "video": "视频",
    "audio": "音频",
    "voice": "语音",
    "file": "文件",
}


def is_media_upload_error(error: ActionFailed) -> bool:
    values = [getattr(error, key, None) for key in _ERROR_FIELDS]
    info = getattr(error, "info", None)
    if isinstance(info, dict):
        values.extend(info.get(key) for key in _ERROR_FIELDS)
    return any(
        isinstance(value, str) and _UPLOAD_ERROR.search(value) is not None
        for value in values
    )


def _copy_node(node: CustomNode, content: UniMessage) -> CustomNode:
    copied = replace(node, content=content)
    if getattr(node, "_parser_lite_fallback_notice", False):
        setattr(copied, "_parser_lite_fallback_notice", True)
    return copied


def _pack_nodes(nodes: list[CustomNode]) -> list[UniMessage]:
    return [
        UniMessage(Reference(nodes=packet))
        for packet in pack_forward_nodes(
            nodes,
            SPLIT_THRESHOLD,
            hard_limit=MAX_FORWARD_TEXT_LEN,
            max_nodes=MAX_FORWARD_NODES,
            copy_node=_copy_node,
        )
    ]


@dataclass(slots=True)
class _FallbackState:
    nodes: list[CustomNode]
    replaced_media: bool = False
    has_summary: bool = False


def _fallback_media(
    segment: Media, *, video_only: bool
) -> tuple[list[Segment], bool, bool]:
    role = media_role(segment)
    is_video = segment.type == "video" or role == "video"
    if video_only and not is_video:
        return [deepcopy(segment)], False, role == "summary"

    content: list[Segment] = []
    if video_only and not getattr(segment, "_parser_lite_cover_in_forward", False):
        thumbnail = getattr(segment, "thumbnail", None)
        if isinstance(thumbnail, Image):
            content.append(deepcopy(thumbnail))
    if role != "summary":
        label = "视频" if is_video else _MEDIA_LABELS.get(segment.type, "媒体")
        content.append(Text(f"[{label}已省略，请通过原链接查看]"))
    return content, True, False


def _fallback_node(
    node: CustomNode, *, video_only: bool
) -> tuple[CustomNode, bool, bool] | None:
    content = UniMessage()
    replaced_media = False
    has_summary = False
    previous_notice = False
    for segment in message_segments(node.content):
        if isinstance(segment, Text):
            append_message_part(content, deepcopy(segment), separate=previous_notice)
            previous_notice = False
            continue
        if not isinstance(segment, Media):
            return None
        parts, replaced, summary = _fallback_media(segment, video_only=video_only)
        for part in parts:
            notice = replaced and isinstance(part, Text)
            append_message_part(content, part, separate=previous_notice or notice)
            previous_notice = notice
        replaced_media |= replaced
        has_summary |= summary
    return replace(node, content=content), replaced_media, has_summary


def _fallback_nodes(reference: Reference, *, video_only: bool) -> _FallbackState | None:
    state = _FallbackState(nodes=[])
    for node in reference.children:
        if not isinstance(node, CustomNode):
            return None
        # 二级降级重新生成说明，避免叠加上一层提示
        if getattr(node, "_parser_lite_fallback_notice", False):
            continue
        converted = _fallback_node(node, video_only=video_only)
        if converted is None:
            return None
        fallback_node, replaced, has_summary = converted
        state.replaced_media |= replaced
        state.has_summary |= has_summary
        if fallback_node.content:
            state.nodes.append(fallback_node)
    return state


def _fallback_context(
    nodes: list[CustomNode],
    result: ParseResult,
    *,
    video_only: bool,
    has_summary: bool,
) -> list[str]:
    existing = "\n".join(
        UniMessage(node.content).extract_plain_text() for node in nodes
    )
    context = [
        "媒体上传失败，已省略视频" if video_only else "媒体上传失败，已改为纯文字内容"
    ]
    for source in (result, result.repost):
        if source is None:
            continue
        if not has_summary:
            if source.title and source.title not in existing:
                context.append(source.title)
            if source.author.name not in existing:
                context.append(f"作者：{source.author.name}")
        if source.url not in existing:
            context.append(source.display_url)
        existing += "\n" + "\n".join(context)
    return context


def _build_fallback(
    message: UniMessage, result: ParseResult, *, video_only: bool
) -> list[UniMessage]:
    """按失败分包生成独立副本，未知节点保持原有异常处理"""
    if len(message) != 1 or not isinstance(message[0], Reference):
        return []
    reference = cast(Reference, message[0])
    if reference.id or not reference.children:
        return []
    state = _fallback_nodes(reference, video_only=video_only)
    if state is None or not state.replaced_media:
        return []

    context = _fallback_context(
        state.nodes,
        result,
        video_only=video_only,
        has_summary=state.has_summary,
    )
    notice = replace(reference.children[0], content=UniMessage.text("\n".join(context)))
    setattr(notice, "_parser_lite_fallback_notice", True)
    state.nodes.insert(0, notice)  # pyright: ignore[reportArgumentType]
    return _pack_nodes(state.nodes)


def build_text_fallback(message: UniMessage, result: ParseResult) -> list[UniMessage]:
    return _build_fallback(message, result, video_only=False)


def build_video_fallback(message: UniMessage, result: ParseResult) -> list[UniMessage]:
    return _build_fallback(message, result, video_only=True)


async def send_with_media_fallback(message: UniMessage, result: ParseResult):
    # exporter 可能修改消息，失败后只能从发送前的快照构造降级内容
    snapshot = (
        deepcopy(message)
        if len(message) == 1 and isinstance(message[0], Reference)
        else None
    )
    try:
        await message.send()
    except ActionFailed as error:
        if snapshot is None or not is_media_upload_error(error):
            raise
        logger.exception("合并转发媒体上传失败，开始降级失败分包")
        video_fallback = build_video_fallback(snapshot, result)
        if not video_fallback:
            text_fallback = build_text_fallback(snapshot, result)
            if not text_fallback:
                raise
            try:
                for packet in text_fallback:
                    await packet.send(fallback=False)
            except Exception:
                logger.exception("合并转发文字降级发送失败，停止重试")
                raise
            logger.warning("合并转发已降级为纯文字")
            return
        for packet in video_fallback:
            try:
                await deepcopy(packet).send(fallback=False)
            except ActionFailed as video_error:
                if not is_media_upload_error(video_error):
                    raise
                plain_packets = build_text_fallback(packet, result)
                if not plain_packets:
                    raise
                logger.exception("省略视频后仍发生媒体上传错误，降级该分包为纯文字")
                try:
                    for plain_packet in plain_packets:
                        await plain_packet.send(fallback=False)
                except Exception:
                    logger.exception("合并转发文字降级发送失败，停止重试")
                    raise
        logger.warning("合并转发降级发送完成")
