"""合并转发消息的文本切分与分包工具

将长文本按标点断句、把转发节点按平台的文本长度与节点数限制分批
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import TypeVar

from nonebot_plugin_alconna.uniseg import Text

from ..config import pconfig
from ..helper import ForwardNodeInner, UniMessage

SPLIT_THRESHOLD = pconfig.forward_text_threshold
"""单段文本拆分阈值"""
MAX_FORWARD_TEXT_LEN = 30000
"""单个 forward 文本总长上限"""
MAX_FORWARD_NODES = 90
"""单个 forward 节点数上限"""

TEXT_SPLIT_PUNCTUATION = frozenset("。！？!?；;，,、…")


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


ForwardItem = TypeVar("ForwardItem")


def split_forward_content(
    content: ForwardNodeInner | _ForwardText, max_len: int
) -> Sequence[ForwardNodeInner]:
    """按文字阈值拆分，混合消息保留各消息段的顺序"""
    if isinstance(content, _ForwardText):
        return content.split(max_len)
    if isinstance(content, str):
        return split_text_by_length_with_punct(content, max_len)
    message = UniMessage(content)
    if max_len <= 0 or len(message.extract_plain_text()) <= max_len:
        return [content]

    fragments: list[ForwardNodeInner] = []
    fragment = UniMessage()
    text_length = 0
    for segment in message:
        parts = (
            [
                Text(text)
                for text in split_text_by_length_with_punct(segment.text, max_len)
            ]
            if isinstance(segment, Text)
            else [segment]
        )
        for part in parts:
            length = len(part.text) if isinstance(part, Text) else 0
            if fragment and text_length + length > max_len:
                fragments.append(fragment)
                fragment = UniMessage()
                text_length = 0
            fragment.append(part)
            text_length += length
    if fragment:
        fragments.append(fragment)
    return fragments


def pack_forward_items(
    items: list[ForwardItem],
    content_of: Callable[[ForwardItem], ForwardNodeInner],
    with_content: Callable[[ForwardItem, ForwardNodeInner], ForwardItem],
) -> Iterator[list[ForwardItem]]:
    """统一清理节点首尾换行，并按文本长度和节点数分包"""
    chunk: list[ForwardItem] = []
    text_length = 0
    for item in items:
        content = content_of(item)
        if isinstance(content, str | UniMessage):
            cleaned = content.strip("\n")
            if not cleaned:
                continue
            if cleaned != content:
                item = with_content(item, cleaned)
            content = cleaned
        length = len(UniMessage(content).extract_plain_text())
        if chunk and (
            text_length + length > MAX_FORWARD_TEXT_LEN
            or len(chunk) >= MAX_FORWARD_NODES
        ):
            yield chunk
            chunk = []
            text_length = 0
        chunk.append(item)
        text_length += length
    if chunk:
        yield chunk

