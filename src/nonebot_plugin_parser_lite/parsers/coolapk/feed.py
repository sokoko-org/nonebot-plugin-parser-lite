from bs4 import BeautifulSoup as soup
from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from .util import format_sticker


class FeedData(Struct):
    title: str
    username: str
    userAvatar: str
    dateline: int | None = field(default=None)
    message: str = field(default="")
    picArr: list[str] | None = field(default=None)

    @property
    def content(self):
        return [
            *format_sticker(soup(self.message, "html.parser").get_text()),
            *([Creator.image(pic) for pic in self.picArr] if self.picArr else []),
        ]


class PageProps(Struct):
    feed: FeedData
    id: str
    aiSummary: str | None = field(default=None)


class Props(Struct):
    pageProps: PageProps


class Feed(Struct):
    props: Props


decoder = Decoder(Feed)
