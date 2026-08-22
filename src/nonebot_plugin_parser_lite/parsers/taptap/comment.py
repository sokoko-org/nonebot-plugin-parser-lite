from __future__ import annotations

from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import ContentItem, Creator
from ...data import Comment
from ...utils.format import format_num
from .share import Contents


class Author(Struct):
    id: int
    name: str
    avatar: str


class TComment(Struct):
    id_str: str
    created_time: int
    author: Author
    contents: Contents
    ups: int | None = None
    comments: int | None = None
    child_posts: list[TComment] | None = None

    @property
    def content(self) -> list[ContentItem]:
        return self.contents.content

    @property
    def stats(self):
        return Creator.stats(
            like_count=format_num(self.ups),
            comment_count=format_num(self.comments),
        )


class Data(Struct):
    comment_list: list[TComment] | None = field(name="list", default=None)


class Response(Struct):
    data: Data

    @property
    def comments(self) -> list[Comment]:
        if not self.data.comment_list:
            return []

        def to_author(tc: TComment):
            return Creator.author(
                id=str(tc.author.id),
                name=tc.author.name,
                avatar_url=tc.author.avatar,
                avatar_cache_key=f"taptap:{tc.author.id}",
            )

        def to_comment(tc: TComment):
            return Creator.comment(
                author=to_author(tc),
                content=tc.content,
                timestamp=tc.created_time,
                stats=tc.stats,
            )

        result: list[Comment] = []
        for c in self.data.comment_list:
            root = to_comment(c)
            if children := c.child_posts:
                for sc in children:
                    root.add_reply(to_comment(sc))
            result.append(root)
        return result


decoder = Decoder(Response)
