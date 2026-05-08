from msgspec import Struct, field
from ..creator import create_image
from .util import format_sticker


class ReplyData(Struct):
    username: str
    dateline: int
    rusername: str
    """回复谁的这个评论"""
    message: str
    """需要解析表情 [强]"""
    picArr: list[str] = field(default_factory=list)

    @property
    def content(self):
        return [
            *format_sticker(self.message),
            *[create_image(pic) for pic in self.picArr],
        ]


class Comment(Struct):
    username: str
    userAvatar: str
    feedUid: int
    dateline: int
    likenum: int
    replynum: int
    message: str
    """需要解析表情 [强]"""
    picArr: list[str] = field(default_factory=list)
    replyRows: list[ReplyData] = field(default_factory=list)

    @property
    def content(self):
        return [
            *format_sticker(self.message),
            *[create_image(pic) for pic in self.picArr],
        ]


class PageProps(Struct):
    replies: list[Comment] = field(default_factory=list)


class Props(Struct):
    pageProps: PageProps


class Reply(Struct):
    props: Props
