from collections.abc import Callable
import re
from typing import Final, Literal

from ..constants import STICKER_CDN
from ..creator import Creator
from ..data import ContentItem

DEFAULT_PLACEHOLDER_PATTERN: Final = re.compile(r"\[(?P<name>[^]]+)\]")


def replace_placeholder_to_sticker(
    text: str,
    placeholder_pattern: re.Pattern[str],
    platform: str,
    size_resolver: Callable[[str], Literal["small", "medium"]] | None = None,
) -> list[ContentItem]:
    """
    将包含表情占位符的文本拆分为文本与表情。

    :param text: 可能包含表情占位符的原始文本，如 "你好[勤洗手]呀"。
    :param placeholder_pattern: 用于匹配占位符的正则，需包含名为 "name" 的分组。
    :param platform: 平台标识，用于拼接表情 CDN 路径。
    :param size_resolver: 一个接收表情名称并返回 size 字符串的函数，例如
                          lambda name: "small" / "medium"
                          若为 None，则默认使用 "small"。
    :return: 由普通文本和 ContentItem 组成的列表，顺序与原字符串一致。
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
