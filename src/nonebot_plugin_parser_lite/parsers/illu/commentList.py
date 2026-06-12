from datetime import datetime

from msgspec import Struct, field
from msgspec.json import Decoder

from .models import User


class CommentObj(Struct):
    author: User
    likeCount: int
    content: str
    objectId: str
    createdAt: str
    subCommentList: list["CommentObj"] = field(default_factory=list)
    subCommentCount: int = field(default=0)

    @property
    def timestamp(self) -> int:
        dt = datetime.strptime(self.createdAt, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp())


class CommentList(Struct):
    msg: str
    results: list[CommentObj] = field(default_factory=list)


decoder = Decoder(CommentList)
