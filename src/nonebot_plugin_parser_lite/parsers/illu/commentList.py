from __future__ import annotations

from datetime import datetime

from msgspec import Struct, field
from msgspec.json import Decoder

from .models import User


class Comment(Struct):
    author: User
    likeCount: int
    content: str
    objectId: str
    createdAt: str
    subCommentList: list[Comment] = field(default_factory=list)
    subCommentCount: int = field(default=0)

    @property
    def timestamp(self) -> int:
        dt = datetime.strptime(self.createdAt, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp())


class CommentList(Struct):
    msg: str
    results: list[Comment] = field(default_factory=list)


decoder = Decoder(CommentList)
