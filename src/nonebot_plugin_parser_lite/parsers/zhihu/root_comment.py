import re

from bs4 import BeautifulSoup
from msgspec import Struct, field
from msgspec.json import Decoder

from ...utils.format import replace_placeholder_to_sticker

ZHIHU_PATTERN = re.compile(r"\[(?P<name>[^]]+[a-zA-Z])\]")


class Counts(Struct):
    total_counts: int
    collapsed_counts: int
    """被折叠评论数"""


class Tag(Struct):
    type: str
    text: str
    color: str
    """hex"""


class Author(Struct):
    id: str
    url_token: str
    avatar_url: str
    url: str
    gender: int
    headline: str
    name: str


class Comment(Struct):
    id: str
    raw_content: str = field(name="content")
    hot: bool
    created_time: int
    url: str
    """api"""
    reply_root_comment_id: str
    reply_comment_id: str
    like_count: int
    child_comment_count: int
    comment_tag: list[Tag]
    author: Author

    @property
    def content(self):
        return replace_placeholder_to_sticker(
            BeautifulSoup(self.raw_content, "html.parser").get_text("\n"),
            ZHIHU_PATTERN,
            "zhihu",
        )

    @property
    def ip_info(self):
        return next(
            (tag.text for tag in self.comment_tag if tag.type == "ip_info"), None
        )


class RootComment(Struct):
    counts: Counts
    data: list[Comment]


decoder = Decoder(RootComment)
