from msgspec import Struct
from msgspec.json import Decoder


class Resolution(Struct):
    url: str
    definition: str
    bitrate: int
    size: int
    format: str
    lable: str
    codec: str


class Video(Struct):
    duration: int
    cover: str
    resolutions: list[Resolution]


class LinkCard(Struct):
    title: str
    origin_url: str


class CustomEmoticon(Struct):
    id: str
    url: str


class InsertObject(Struct):
    """大一统结构体：包含所有可能出现的单键对象。
    没有出现的键在反序列化时会自动赋值为 None。
    """

    vod: Video | None = None
    link_card: LinkCard | None = None
    image: str | None = None
    custom_emoticon: CustomEmoticon | None = None
    backup_text: str | None = None


class StructedContent(Struct):
    insert: InsertObject | str


def decode_structed_content(s: str) -> list[StructedContent]:
    return Decoder(list[StructedContent]).decode(s) if s.strip() else []
