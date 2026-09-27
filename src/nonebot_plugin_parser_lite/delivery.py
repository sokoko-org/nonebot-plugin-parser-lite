"""合并转发媒体上传失败时，保留失败分包的文字与来源。"""

from dataclasses import replace
import re

from nonebot import logger
from nonebot.exception import ActionFailed
from nonebot_plugin_alconna.uniseg import CustomNode, Reference, Text, UniMessage
from nonebot_plugin_alconna.uniseg.segment import Media

from .data import ParseResult
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


def build_text_fallback(message: UniMessage, result: ParseResult) -> list[UniMessage]:
    """为一个本地构造的媒体合并分包建立独立副本，不修改原消息或解析缓存。

    不可读取的引用节点或未知消息段不做自动降级，以免静默丢失内容。
    """
    if len(message) != 1 or not isinstance(message[0], Reference):
        return []
    reference = message[0]
    if reference.id or not reference.children:
        return []

    nodes: list[CustomNode] = []
    has_media = False
    for node in reference.children:
        if not isinstance(node, CustomNode):
            return []
        if isinstance(node.content, str):
            text = node.content
        else:
            parts: list[str] = []
            for segment in node.content:
                if isinstance(segment, Text):
                    parts.append(segment.text)
                elif isinstance(segment, Media):
                    has_media = True
                    label = _MEDIA_LABELS.get(segment.type, "媒体")
                    name = f"：{segment.name[:200]}" if segment.name else ""
                    parts.append(f"[{label}未能发送{name}]")
                else:
                    return []
            text = "".join(parts)
        nodes.append(replace(node, content=UniMessage.text(text)))
    if not has_media:
        return []

    context = ["媒体发送失败，已改为文字内容，请通过原链接查看。"]
    for source in (result, result.repost):
        if source is None:
            continue
        if source.title:
            context.append(source.title)
        context.extend((f"作者：{source.author.name}", source.display_url))
    nodes.insert(0, replace(nodes[0], content=UniMessage.text("\n".join(context))))

    # 占位文字与来源提示也占用长度；重新分包时仍遵守原有转发限制。
    messages: list[UniMessage] = []
    chunk: list[CustomNode] = []
    text_length = 0
    split_limit = min(MAX_FORWARD_TEXT_LEN, max(1, SPLIT_THRESHOLD))
    for node in nodes:
        text = node.content.extract_plain_text()  # type: ignore[union-attr]
        for part in split_text_by_length_with_punct(text, split_limit):
            if chunk and (
                len(chunk) >= MAX_FORWARD_NODES
                or text_length + len(part) > MAX_FORWARD_TEXT_LEN
            ):
                messages.append(UniMessage(Reference(nodes=list(chunk))))
                chunk.clear()
                text_length = 0
            chunk.append(replace(node, content=UniMessage.text(part)))
            text_length += len(part)
    if chunk:
        messages.append(UniMessage(Reference(nodes=chunk)))
    return messages


async def send_with_media_fallback(message: UniMessage, result: ParseResult) -> None:
    # send/export 可能修改统一消息；必须在第一次发送前准备备用内容。
    fallback = build_text_fallback(message, result)
    try:
        await message.send()
    except ActionFailed as error:
        if not fallback or not is_media_upload_error(error):
            raise
        logger.exception("合并转发媒体上传失败，尝试发送该分包的纯文字内容")
        try:
            for text_message in fallback:
                # 不支持合并转发的平台应报错，禁止 UniSeg 自动拆成普通消息。
                await text_message.send(fallback=False)
        except Exception:
            logger.exception("合并转发文字降级发送失败，停止重试")
            raise
        logger.warning(f"合并转发已降级为纯文字，发送了 {len(fallback)} 个分包")
