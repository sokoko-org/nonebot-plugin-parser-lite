from collections.abc import Callable, MutableSequence, Sequence
import re
from typing import Final, Literal
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

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


def format_num(num: int | None) -> str:
    """将数字格式化为 1.2万 的形式"""
    if num is None:
        return "-"
    return str(num) if num < 10000 else f"{num / 10000:.1f}万"


def clean_clank(value: str) -> str | None:
    """清理文本中的空白符号(包括换行)"""
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def append_html_text(
    result: MutableSequence[ContentItem], buffer: Sequence[str]
) -> None:
    """合并连续 HTML 文本，并保留标签产生的换行"""
    if not buffer:
        return
    if normalized := "".join(buffer).strip():
        result.append(normalized)


def html_to_text(root: BeautifulSoup | Tag) -> str:
    """按 HTML 标签语义提取文本"""
    parts: list[str] = []
    for element in root.descendants:
        if isinstance(element, Tag):
            if element.name in HTML_NEWLINE_TAGS:
                parts.append("\n")
        elif isinstance(element, NavigableString):
            if text := clean_clank(str(element)):
                parts.append(text)
    return "".join(parts).strip()


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
