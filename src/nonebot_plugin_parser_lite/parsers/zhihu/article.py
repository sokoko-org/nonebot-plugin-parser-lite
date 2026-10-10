from msgspec import Struct, field
from msgspec.json import Decoder

from .util import parse_rich_content


class Statistics(Struct):
    comment_count: int
    """评论数"""
    down_vote_count: int
    """'反对'数"""
    favorites: int
    """收藏数"""
    like_count: int
    """点'心'数"""
    up_vote_count: int
    """'赞同'数"""


class Reaction(Struct):
    statistics: Statistics


class Author(Struct):
    id: str
    uid: str
    url_token: str
    name: str
    headline: str
    avatar_url: str
    gender: int


class Article(Struct):
    id: str
    title: str
    content: str
    reaction: Reaction
    author: Author
    created: int
    updated: int
    ip_info: str | None = field(default=None)

    async def get_content(self):
        return await parse_rich_content(self.content, "article")


decoder = Decoder(Article)
