from msgspec import Struct
from msgspec.json import Decoder


class LongData(Struct):
    isMarkdown: bool
    longTextContent_raw: str


class LongText(Struct):
    data: LongData


decoder = Decoder(LongText)
