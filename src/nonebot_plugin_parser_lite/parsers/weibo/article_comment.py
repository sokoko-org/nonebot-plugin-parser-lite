import re

from msgspec import Struct
from msgspec.json import Decoder

from ...utils.format import replace_placeholder_to_sticker

WEIBO_PATTERN = re.compile(r"\[(?P<name>[^]]+)\]")


class UserInfo(Struct):
    id: int
    screen_name: str
    description: str
    profile_image_url: str


class ArticleComment(Struct):
    created_at_unix: int
    text: str
    user_info: UserInfo

    @property
    def content(self):
        return replace_placeholder_to_sticker(self.text, WEIBO_PATTERN, "weibo")


class ArticleCommentData(Struct):
    total_number: int
    comments: list[ArticleComment]


class ArticleCommentWrapper(Struct):
    data: ArticleCommentData


decoder = Decoder(ArticleCommentWrapper)
