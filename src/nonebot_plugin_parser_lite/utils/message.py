"""保留原文空白，按内容边界组装消息，并统一执行转发限制。"""

from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace

from nonebot_plugin_alconna.uniseg import CustomNode, Segment, Text, UniMessage

MAX_FORWARD_TEXT_LEN = 30000
MAX_FORWARD_NODES = 90
TEXT_SPLIT_PUNCTUATION = frozenset("。！？!?；;，,、…")


def message_segments(part: str | Segment | UniMessage) -> list[Segment]:
    # UniMessage(existing) 会合并相邻 Text，丢失块的拆分策略。
    if isinstance(part, UniMessage):
        return list(part)
    return [Text(part)] if isinstance(part, str) else [part]


def needs_text_separator(left: str, right: str) -> bool:
    return bool(left and right) and not (
        left.endswith(("\n", "\r")) or right.startswith(("\n", "\r"))
    )


def append_message_part(
    message: UniMessage,
    part: str | Segment | UniMessage,
    *,
    separate: bool = False,
) -> None:
    incoming = message_segments(part)
    if not incoming:
        return
    if separate and message:
        left, right = message[-1], incoming[0]
        if isinstance(left, Text) and (
            needs_text_separator(left.text, right.text)
            if isinstance(right, Text)
            else not left.text.endswith(("\n", "\r"))
        ):
            message.append(layout_text("\n", separator=True))
    message.extend(incoming)


def layout_text(
    text: str, *, keep_together: bool = False, separator: bool = False
) -> Text:
    segment = Text(text)
    setattr(segment, "_parser_lite_keep_together", keep_together)
    setattr(segment, "_parser_lite_separator", separator)
    return segment


@dataclass(frozen=True, slots=True)
class TextPart:
    text: str
    block: bool = False
    keep_together: bool = False


@dataclass(frozen=True, slots=True)
class MessageText:
    author_name: str
    parts: Sequence[TextPart]
    include_author: bool = True
    separate: bool = False

    def to_message(self) -> UniMessage:
        message = UniMessage()
        if self.include_author:
            prefix = layout_text(f"{self.author_name}：")
            setattr(prefix, "_parser_lite_author_prefix", True)
            message.append(prefix)
        previous: TextPart | None = None
        for part in self.parts:
            if not part.text:
                continue
            append_message_part(
                message,
                layout_text(part.text, keep_together=part.keep_together),
                separate=bool(previous and (previous.block or part.block)),
            )
            previous = part
        return message

    @property
    def text(self) -> str:
        return self.to_message().extract_plain_text()


def _split_end(text: str, start: int, soft_room: int, hard_room: int) -> int:
    end = min(start + soft_room, len(text))
    if end < len(text):
        end = next(
            (
                i + 1
                for i in range(end - 1, start - 1, -1)
                if text[i] in TEXT_SPLIT_PUNCTUATION
            ),
            end,
        )
    # 原文空白附着于相邻内容，可超过软阈值，绝不超过平台硬上限。
    hard_end = min(start + hard_room, len(text))
    if end == hard_end and end < len(text) and text[end:].isspace():
        pivot = len(text[:end].rstrip()) - 1
        if pivot > start and len(text) - pivot <= hard_room:
            return pivot
    while end < hard_end and text[end].isspace():
        end += 1
    if not text[start:end].strip() and end < hard_end:
        end += 1
    return end


def split_message(
    content: str | Segment | UniMessage,
    soft_limit: int,
    hard_limit: int = MAX_FORWARD_TEXT_LEN,
) -> list[UniMessage]:
    """保留原文；块只因硬上限拆开，程序分隔不跨节点。

    原文空白无法与相邻内容一起放入硬上限时，保留空白片段而非静默丢弃。
    """
    soft_limit = min(max(1, soft_limit), hard_limit)
    messages: list[UniMessage] = []
    current = UniMessage()
    length = 0
    pending_separator: Text | None = None

    def flush() -> None:
        nonlocal current, length, pending_separator
        if current:
            messages.append(current)
        current = UniMessage()
        length = 0
        pending_separator = None

    for segment in message_segments(content):
        if not isinstance(segment, Text):
            if pending_separator is not None and current and length < hard_limit:
                current.append(pending_separator)
                length += len(pending_separator.text)
            pending_separator = None
            current.append(deepcopy(segment))
            continue
        if getattr(segment, "_parser_lite_separator", False):
            pending_separator = deepcopy(segment)
            continue
        if not segment.text:
            continue
        keep = getattr(segment, "_parser_lite_keep_together", False)
        prefix_only = bool(current) and all(
            getattr(part, "_parser_lite_author_prefix", False) for part in current
        )
        separator_length = len(pending_separator.text) if pending_separator else 0
        if (
            keep
            and current
            and not prefix_only
            and (length + separator_length + len(segment.text) > soft_limit)
        ):
            flush()
        elif pending_separator is not None and length + separator_length >= soft_limit:
            flush()
        if pending_separator is not None and current:
            current.append(pending_separator)
            length += separator_length
        pending_separator = None
        start = 0
        while start < len(segment.text):
            if length >= hard_limit:
                flush()
            if length >= soft_limit and not segment.text[start].isspace():
                if not (keep and (not current or prefix_only)):
                    flush()
            hard_room = hard_limit - length
            if keep and len(segment.text) - start <= hard_room:
                end = len(segment.text)
            else:
                room = hard_room if keep else max(1, soft_limit - length)
                end = _split_end(segment.text, start, min(room, hard_room), hard_room)
            piece = deepcopy(segment)
            piece.text = segment.text[start:end]
            piece.styles = {}
            for (left, right), styles in segment.styles.items():
                if left < end and right > start:
                    span = (max(left, start) - start, min(right, end) - start)
                    combined = piece.styles.setdefault(span, [])
                    combined.extend(style for style in styles if style not in combined)
            current.append(piece)
            length += end - start
            start = end
            prefix_only = False
    flush()
    return messages


def split_text_by_length_with_punct(text: str, max_len: int) -> list[str]:
    """严格按上限拆分原文，不丢弃空白；禁用限制时返回原文。"""
    if max_len <= 0:
        return [text]
    return [part.extract_plain_text() for part in split_message(text, max_len, max_len)]


def pack_forward_nodes(
    nodes: Sequence[CustomNode],
    soft_limit: int,
    *,
    hard_limit: int = MAX_FORWARD_TEXT_LEN,
    max_nodes: int = MAX_FORWARD_NODES,
    copy_node: Callable[[CustomNode, UniMessage], CustomNode] | None = None,
) -> list[list[CustomNode]]:
    """正常转发与降级共用的节点拆分、长度统计及分包。"""
    packets: list[list[CustomNode]] = []
    packet: list[CustomNode] = []
    length = 0
    for node in nodes:
        for content in split_message(node.content, soft_limit, hard_limit):
            size = len(content.extract_plain_text())
            if packet and (len(packet) >= max_nodes or length + size > hard_limit):
                packets.append(packet)
                packet, length = [], 0
            copied = (
                copy_node(node, content)
                if copy_node
                else replace(node, content=content)
            )
            packet.append(copied)
            length += size
    if packet:
        packets.append(packet)
    return packets
