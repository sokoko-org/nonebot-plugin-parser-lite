from msgspec import Struct


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


class VideoStructed(Struct):
    vod: Video


class LinkCard(Struct):
    title: str
    origin_url: str


class LinkStructed(Struct):
    link_card: LinkCard


class ImageStructed(Struct):
    image: str


class CustomEmoticon(Struct):
    id: str
    url: str


class EmotionStructed(Struct):
    backup_text: str
    custom_emoticon: CustomEmoticon


class StructedContent(Struct):
    insert: str | VideoStructed | LinkStructed | ImageStructed | EmotionStructed
