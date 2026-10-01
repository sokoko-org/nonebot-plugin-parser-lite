from collections.abc import Callable, Iterator, MutableSequence, Sequence
import re
from typing import Final, Literal
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag

from ..constants import STICKER_CDN
from ..creator import Creator
from ..data import ContentItem

DEFAULT_PLACEHOLDER_PATTERN: Final = re.compile(r"\[(?P<name>[^]]+)\]")
HTML_NEWLINE_TAGS: Final = frozenset(
    {"p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "hr"}
)


def replace_placeholder_to_sticker(
    text: str,
    placeholder_pattern: re.Pattern[str],
    platform: str,
    size_resolver: Callable[[str], Literal["small", "medium"]] | None = None,
) -> list[ContentItem]:
    """
    将包含表情占位符的文本拆分为文本与表情

    :param text: 可能包含表情占位符的原始文本，如 "你好[勤洗手]呀"
    :param placeholder_pattern: 用于匹配占位符的正则，需包含名为 "name" 的分组
    :param platform: 平台标识，用于拼接表情 CDN 路径
    :param size_resolver: 一个接收表情名称并返回 size 字符串的函数，例如
                          lambda name: "small" / "medium"
                          若为 None，则默认使用 "small"
    :return: 由普通文本和 ContentItem 组成的列表，顺序与原字符串一致
    """
    if not placeholder_pattern.search(text):
        return [text]

    result: list[ContentItem] = []
    last_pos = 0

    for match in placeholder_pattern.finditer(text):
        start, end = match.span()
        if start > last_pos:
            if plain := text[last_pos:start]:
                result.append(plain)

        if name := match["name"]:
            size = size_resolver(name) if size_resolver is not None else "small"
            result.append(
                Creator.sticker(
                    url=STICKER_CDN.format(platform=platform, name=name),
                    size=size,
                    desc=f"[{name}]",
                )
            )
        elif placeholder_text := text[start:end]:
            result.append(placeholder_text)
        last_pos = end

    # 最后剩余的纯文本
    if last_pos < len(text):
        if tail := text[last_pos:]:
            result.append(tail)

    return result


def is_inside(element: object, ancestor: Tag) -> bool:
    """按对象身份判断节点是否位于 ancestor 子树内

    bs4 的 ``in`` / ``==`` 按内容比较，会把子树外内容相同的节点误判为子孙
    """
    parent = getattr(element, "parent", None)
    while parent is not None:
        if parent is ancestor:
            return True
        parent = parent.parent
    return False


def format_num(num: int | None) -> str | None:
    """将数字格式化为 1.2万 的形式"""
    if num is None:
        return None
    return str(num) if num < 10000 else f"{num / 10000:.1f}万"


def clean_blank(value: str) -> str | None:
    """清理文本中的空白符号(包括换行)"""
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


class HtmlBreak(str):
    """区分 HTML 块边界与用户显式写出的 br。"""

    explicit: bool
    parent: Tag | None

    def __new__(cls, *, explicit: bool = False, parent: Tag | None = None):
        value = super().__new__(cls, "\n")
        value.explicit = explicit
        value.parent = parent
        return value


def html_boundary(tag: Tag) -> HtmlBreak:
    return HtmlBreak(explicit=tag.name == "br")


def iter_html_content(root: Tag) -> Iterator[PageElement | HtmlBreak]:
    """按文档顺序遍历，补出块的结束边界；保留父级供解析器跳过子树。"""
    stack = [(iter(root.children), root)]
    while stack:
        children, parent = stack[-1]
        try:
            element = next(children)
        except StopIteration:
            stack.pop()
            if parent is not root and parent.name in HTML_NEWLINE_TAGS:
                if parent.name not in {"br", "hr"}:
                    yield HtmlBreak(parent=parent)
            continue
        yield element
        if isinstance(element, Tag):
            stack.append((iter(element.children), element))


def normalize_html_text(parts: Sequence[str]) -> str:
    output: list[str] = []
    generated_boundary = False
    for part in parts:
        if isinstance(part, HtmlBreak):
            if part.explicit:
                if generated_boundary:
                    output.pop()
                output.append("\n")
                generated_boundary = False
            elif output and not output[-1].endswith("\n"):
                output.append("\n")
                generated_boundary = True
        elif part:
            output.append(part)
            generated_boundary = False
    if generated_boundary:
        output.pop()
    return "".join(output)


def append_html_text(
    result: MutableSequence[ContentItem], buffer: Sequence[str]
) -> None:
    """合并 HTML 文本：块边界去重，显式 br 保留。"""
    if normalized := normalize_html_text(buffer):
        result.append(normalized)


def html_to_text(root: BeautifulSoup | Tag | str) -> str:
    """按 HTML 标签语义提取文本"""
    parts: list[str] = []
    if isinstance(root, str):
        root = BeautifulSoup(root, "html.parser")
    for element in iter_html_content(root):
        if isinstance(element, HtmlBreak):
            parts.append(element)
        elif isinstance(element, Tag):
            if element.name in HTML_NEWLINE_TAGS:
                parts.append(html_boundary(element))
        elif isinstance(element, NavigableString):
            if text := clean_blank(str(element)):
                parts.append(text)
    return normalize_html_text(parts)


def anchor_text(element: Tag, base_url: str) -> str | None:
    """提取链接的显示文本和链接"""
    if element.find("img"):
        return None
    label = element.get_text(" ", strip=True)
    if not label:
        return None
    href = element.get("href")
    if not isinstance(href, str) or not href:
        return label
    if href.startswith("#"):
        return label

    url = urljoin(base_url, href)
    return f"{label} ({url})"


def replace_anchor_hrefs(root: BeautifulSoup | Tag, base_url: str) -> None:
    """将正文中的链接替换为 ``显示文本 (完整地址)``"""
    for element in root.find_all("a"):
        if text := anchor_text(element, base_url):
            element.replace_with(text)
