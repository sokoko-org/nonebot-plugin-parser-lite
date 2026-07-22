from msgspec import Struct
from msgspec.json import Decoder

from .util import weibo_long_html_to_raw


class LongData(Struct):
    longTextContent: str

    @property
    def raw(self) -> str:
        return weibo_long_html_to_raw(self.longTextContent)


class LongText(Struct):
    data: LongData


decoder = Decoder(LongText)
