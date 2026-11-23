import re
from typing import Final

from ...constants import STICKER_CDN
from ...creator import ContentItem, Creator
from ...utils.format import replace_placeholder_to_sticker

EMOJI_PATTERN: Final = re.compile("\\[\u200b(?P<name>.+?)\u200b\\]")
"""小表情占位符 `[\u200b点赞\u200b]`"""


def sticker_content(sticker_id: str, text: str | None = None) -> ContentItem:
    """构造大贴纸内容

    :param sticker_id: 贴纸 id，如 `paopaotuantuan-6__paopaotuantuan6_2`
    :param text: 贴纸的描述
    """
    desc = text or sticker_id.rpartition("__")[2] or sticker_id
    return Creator.sticker(
        url=STICKER_CDN.format(platform="skyland", name=sticker_id),
        size="medium",
        desc=f"[{desc}]",
        cache_key=f"skyland:{sticker_id}",
    )


def replace_emoji(text: str) -> list[ContentItem]:
    """把文本里的 `[\u200b标题\u200b]` 占位符替换为小表情贴纸

    :param text: 含占位符的原始文本
    """
    return replace_placeholder_to_sticker(text, EMOJI_PATTERN, "skyland")
