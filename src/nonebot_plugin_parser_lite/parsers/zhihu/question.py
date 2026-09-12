from msgspec import Struct
from msgspec.json import Decoder

from .util import parse_rich_content


class Author(Struct):
    id: str
    url_token: str
    name: str
    avatar_url: str
    headline: str
    url: str
    gender: int


class Question(Struct):
    title: str
    created: int
    updated_time: int
    url: str
    """api"""
    answer_count: int
    visit_count: int
    comment_count: int
    follower_count: int
    detail: str
    author: Author
    voteup_count: int

    async def get_content(self):
        return await parse_rich_content(self.detail, "question")


decoder = Decoder(Question)
