from msgspec import Struct, field

from ..creator import create_image

from ..data import MediaContent


class Author(Struct):
    avatar: str
    ip_location: str
    nickname: str
    user_id: str


class Picture(Struct):
    image_url: str
    is_emoji: bool


class Comment(Struct):
    author: Author
    created_at: int
    message: str
    pictures: list[Picture]
    ups_num: int
    replies: list["Comment"] = field(default_factory=list)

    @property
    def content(self) -> list[MediaContent | str]:
        return [self.message] + [create_image(pic.image_url) for pic in self.pictures]


class Comments(Struct):
    comment_target_author_id: str
    """楼主id"""
    items: list[Comment]
