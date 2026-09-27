"""合并转发媒体上传失败时，保留失败分包的文字与来源。"""

from copy import deepcopy
from dataclasses import replace
import re

from nonebot import logger
from nonebot.exception import ActionFailed
from nonebot_plugin_alconna.uniseg import CustomNode, Reference, Text, UniMessage
from nonebot_plugin_alconna.uniseg.segment import Media

from .data import ParseResult
from .helper import media_role
from .render import (
    MAX_FORWARD_NODES,
    MAX_FORWARD_TEXT_LEN,
    SPLIT_THRESHOLD,
    split_text_by_length_with_punct,
)

# 仅匹配协议端明确透传的媒体上传错误，不能仅凭 retcode 或普通超时降级。
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
    """兼容直接错误字段及 OneBot 的 info 字段，不搜索请求内容或异常 repr。"""
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
    """新增的说明也计入长度，并保留混合图文节点的顺序。"""
    split_limit = min(MAX_FORWARD_TEXT_LEN, max(1, SPLIT_THRESHOLD))
    split_nodes: list[CustomNode] = []
    for node in nodes:
        content = UniMessage(node.content)
        fragment = UniMessage()
        length = 0
        for segment in content:
            parts = (
                [
                    Text(text)
                    for text in split_text_by_length_with_punct(
                        segment.text, split_limit
                    )
                ]
                if isinstance(segment, Text)
                else [segment]
            )
            for part in parts:
                part_length = len(part.text) if isinstance(part, Text) else 0
                if fragment and length + part_length > split_limit:
                    split_nodes.append(_copy_node(node, fragment))
                    fragment = UniMessage()
                    length = 0
                fragment.append(part)
                length += part_length
        if fragment:
            split_nodes.append(_copy_node(node, fragment))

    messages: list[UniMessage] = []
    chunk: list[CustomNode] = []
    length = 0
    for node in split_nodes:
        node_length = len(UniMessage(node.content).extract_plain_text())
        if chunk and (
            len(chunk) >= MAX_FORWARD_NODES
            or length + node_length > MAX_FORWARD_TEXT_LEN
        ):
            messages.append(UniMessage(Reference(nodes=list(chunk))))
            chunk.clear()
            length = 0
        chunk.append(node)
        length += node_length
    if chunk:
        messages.append(UniMessage(Reference(nodes=chunk)))
    return messages


def _build_fallback(
    message: UniMessage, result: ParseResult, *, video_only: bool
) -> list[UniMessage]:
    """按失败分包生成独立副本，未知节点保持原有异常处理。"""
    if len(message) != 1 or not isinstance(message[0], Reference):
        return []
    reference = message[0]
    if reference.id or not reference.children:
        return []

    nodes: list[CustomNode] = []
    replaced_media = False
    has_summary = False
    for node in reference.children:
        if not isinstance(node, CustomNode):
            return []
        # 二级降级重新生成说明，避免叠加上一层提示。
        if getattr(node, "_parser_lite_fallback_notice", False):
            continue
        content = UniMessage()
        for segment in UniMessage(node.content):
            if isinstance(segment, Text):
                content.append(deepcopy(segment))
            elif isinstance(segment, Media):
                role = media_role(segment)
                is_video = segment.type == "video" or role == "video"
                if video_only and not is_video:
                    content.append(deepcopy(segment))
                    has_summary |= role == "summary"
                    continue
                replaced_media = True
                if role != "summary":
                    label = (
                        "视频" if is_video else _MEDIA_LABELS.get(segment.type, "媒体")
                    )
                    content.append(Text(f"\n[{label}已省略，请通过原链接查看]\n"))
            else:
                return []
        if content:
            nodes.append(replace(node, content=content))
    if not replaced_media:
        return []

    existing = "\n".join(
        UniMessage(node.content).extract_plain_text() for node in nodes
    )
    context = [
        "媒体上传失败，已省略视频，保留其他内容。"
        if video_only
        else "媒体上传失败，已改为纯文字内容，请通过原链接查看。"
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
    notice = replace(reference.children[0], content=UniMessage.text("\n".join(context)))
    setattr(notice, "_parser_lite_fallback_notice", True)
    nodes.insert(0, notice)
    return _pack_nodes(nodes)


def build_text_fallback(message: UniMessage, result: ParseResult) -> list[UniMessage]:
    return _build_fallback(message, result, video_only=False)


def build_video_fallback(message: UniMessage, result: ParseResult) -> list[UniMessage]:
    return _build_fallback(message, result, video_only=True)


async def _send_text_fallback(messages: list[UniMessage]) -> None:
    try:
        for message in messages:
            await message.send(fallback=False)
    except Exception:
        logger.exception("合并转发文字降级发送失败，停止重试")
        raise
    logger.warning("合并转发已降级为纯文字")


async def send_with_media_fallback(message: UniMessage, result: ParseResult) -> None:
    # send/export 可能修改消息；预先准备两级副本，不复用发送过的对象。
    video_fallback = build_video_fallback(message, result)
    text_fallback = build_text_fallback(message, result)
    video_packets = [
        (packet, build_text_fallback(packet, result)) for packet in video_fallback
    ]
    try:
        await message.send()
    except ActionFailed as error:
        if not text_fallback or not is_media_upload_error(error):
            raise
        logger.exception("合并转发媒体上传失败，开始降级失败分包")
        if not video_packets:
            await _send_text_fallback(text_fallback)
            return
        for packet, plain_packets in video_packets:
            try:
                await packet.send(fallback=False)
            except ActionFailed as video_error:
                if not plain_packets or not is_media_upload_error(video_error):
                    raise
                logger.exception("省略视频后仍发生媒体上传错误，降级该分包为纯文字")
                await _send_text_fallback(plain_packets)
        logger.warning("合并转发降级发送完成")
