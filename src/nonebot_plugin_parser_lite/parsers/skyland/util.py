from msgspec import Struct

from ...creator import ContentItem
from .sticker import replace_emoji, sticker_content


class TextValue(Struct):
    """纯文本载荷"""

    text: str = ""


class LinkValue(Struct):
    """链接载荷"""

    link: str = ""
    text: str = ""


class AtValue(Struct):
    """@用户载荷"""

    id: str = ""
    text: str = ""


class StickerValue(Struct):
    """表情/贴纸载荷"""

    id: str = ""
    text: str = ""


class PronunciationValue(Struct):
    """注音载荷"""

    content: str = ""


class InlineElement(Struct):
    """内联元素"""

    kind: str = ""
    text: TextValue | None = None
    link: LinkValue | None = None
    at: AtValue | None = None
    emoji: StickerValue | None = None
    sticker: StickerValue | None = None
    pronunciation: PronunciationValue | None = None

    @property
    def content(self) -> list[ContentItem]:
        """把单个内联元素渲染为内容片段"""
        match self.kind:
            case "text":
                if self.text and self.text.text:
                    return replace_emoji(self.text.text)
            case "link":
                if self.link:
                    # 站点渲染为纯链接，这里保留“文字 链接”的可读形式
                    text = self.link.text.strip()
                    if link := self.link.link:
                        return [f"{text} {link}" if text and text != link else link]
                    else:
                        return [text] if text else []
            case "at":
                if self.at and self.at.text:
                    return [f"@{self.at.text}"]
            case "emoji":
                # 文档里的 emoji 与 sticker 共用贴纸表
                if self.emoji and self.emoji.id:
                    return [sticker_content(self.emoji.id, self.emoji.text)]
            case "sticker":
                if self.sticker and self.sticker.id:
                    return [sticker_content(self.sticker.id, self.sticker.text)]
            case "pronunciation":
                if self.pronunciation and self.pronunciation.content:
                    return [self.pronunciation.content]
            case _:
                pass
        return []


def render_inline(elements: list[InlineElement] | None) -> list[ContentItem]:
    """渲染一组内联元素"""
    if not elements:
        return []
    content: list[ContentItem] = []
    for element in elements:
        content.extend(element.content)
    return content


def merge_text(content: list[ContentItem]) -> list[ContentItem]:
    """合并相邻纯文本片段并丢弃空白，减少渲染碎片"""
    merged: list[ContentItem] = []
    for item in content:
        if isinstance(item, str) and merged and isinstance(merged[-1], str):
            merged[-1] += item
        else:
            merged.append(item)
    return [item for item in merged if not isinstance(item, str) or item.strip()]
