from msgspec import Struct, field
from bs4 import BeautifulSoup as soup
from ..creator import create_image
from .util import format_sticker
from msgspec.json import Decoder


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
            *([create_image(pic) for pic in self.picArr] if self.picArr else []),
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
