from bs4 import BeautifulSoup as soup
from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from .util import format_sticker


class ReplyData(Struct):
    username: str
    dateline: int
    rusername: str
    """回复谁的这个评论"""
    message: str
    """需要解析表情 [强]"""
    picArr: list[str] | None = field(default=None)

    @property
    def content(self):
        return [
            *format_sticker(soup(self.message, "html.parser").get_text()),
            *([Creator.image(pic) for pic in self.picArr] if self.picArr else []),
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
    picArr: list[str] | None = field(default=None)
    replyRows: list[ReplyData] = field(default_factory=list)

    @property
    def content(self):
        return [
            *format_sticker(soup(self.message, "html.parser").get_text()),
            *([Creator.image(pic) for pic in self.picArr] if self.picArr else []),
        ]


class PageProps(Struct):
    replies: list[Comment] = field(default_factory=list)


class Props(Struct):
    pageProps: PageProps


class Reply(Struct):
    props: Props


decoder = Decoder(Reply)
