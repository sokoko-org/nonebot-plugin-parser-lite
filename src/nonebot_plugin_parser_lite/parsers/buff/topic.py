from msgspec import Struct, field

from ...creator import Creator
from ...data import ContentItem
from .share import ShareData


class UserInfo(Struct):
    avatar: str
    ip_location: str
    nickname: str
    user_id: str


class Picture(Struct):
    image_url: str
    is_emoji: bool


class Item(Struct):
    author_id: str
    text: str = field(name="content")
    pictures: list[Picture]
    publish_time: int
    """秒级时间戳"""
    replies: int
    ups_num: int
    share_data: ShareData

    @property
    def content(self) -> list[ContentItem]:
        return [self.text, *[Creator.image(pic.image_url) for pic in self.pictures]]


class Topic(Struct):
    user_infos: dict[str, UserInfo]
    items: list[Item]
