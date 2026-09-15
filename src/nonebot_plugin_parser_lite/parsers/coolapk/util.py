import re

from ...data import ContentItem
from ...utils.format import replace_placeholder_to_sticker

COOLAPK_PATTERN = re.compile(r"\[(?P<name>[^]]+)\]")


def format_sticker(text: str) -> list[ContentItem]:
    return replace_placeholder_to_sticker(
        text,
        COOLAPK_PATTERN,
        "coolapk",
    )
