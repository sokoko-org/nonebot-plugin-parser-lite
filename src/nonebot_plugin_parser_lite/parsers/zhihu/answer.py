from msgspec import Struct, field
from msgspec.json import Decoder

from .util import parse_rich_content


class Author(Struct):
    avatar_url: str
    headline: str
    """个性签名"""
    id: str
    name: str
    url: str
    """用户信息api地址"""
    url_token: str
    gender: int
    """性别.1男,0女"""


class Question(Struct):
    created: int
    id: str
    """问题id"""
    title: str
    updated_time: int
    url: str
    """问题信息api地址"""


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


class Answer(Struct):
    author: Author
    """回答者信息"""
    content: str
    """html"""
    comment_count: int
    """评论数"""
    created_time: int
    updated_time: int
    id: str
    """回答ID"""
    question: Question
    """问题信息"""
    reaction: Reaction
    """表态相关信息"""
    voteup_count: int
    """'赞同'数"""
    thanks_count: int
    """点'心'数"""
    ip_info: str | None = field(default=None)

    async def get_content(self):
        return await parse_rich_content(self.content, "answer")


decoder = Decoder(Answer)
