from __future__ import annotations

from msgspec import Struct, field

from ...creator import Creator
from ...data import ContentItem


class Author(Struct):
    avatar: str
    ip_location: str
    nickname: str
    user_id: str


class Picture(Struct):
    icon_url: str
    is_emoji: bool
    name: str


class Comment(Struct):
    author: Author
    created_at: int
    message: str
    pictures: list[Picture]
    ups_num: int
    replies: list[Comment] = field(default_factory=list)

    @property
    def content(self) -> list[ContentItem]:
        """将原始 message + pictures 转为文本 + 媒体内容列表。"""
        contents: list[ContentItem] = []
        text = self.message or ""

        for pic in self.pictures:
            if pic.is_emoji:
                sticker = Creator.sticker(
                    url=pic.icon_url,
                    size="medium",
                    desc=pic.name,
                )
                contents.append(sticker)
                placeholder = f"[{pic.name}]"
                if placeholder in text:
                    text = text.replace(placeholder, "", 1)
            else:
                contents.append(Creator.image(pic.icon_url))

        if text:
            contents.insert(0, text)

        return contents


class Comments(Struct):
    comment_target_author_id: str
    """楼主id"""
    items: list[Comment]
