from urllib.parse import parse_qs, urlparse

from msgspec import Struct
from msgspec.json import Decoder

from ...creator import Creator
from ...data import ContentItem
from .sticker import replace_sticker


class Resolution(Struct):
    url: str
    definition: str
    bitrate: int
    size: int
    format: str
    label: str
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
    video: str | None = None


class StructedContent(Struct):
    insert: InsertObject | str


def decode_structed_content(s: str) -> list[StructedContent]:
    return Decoder(list[StructedContent]).decode(s) if s.strip() else []


def build_body(s: str):
    content: list[ContentItem] = []
    data = decode_structed_content(s)
    for item in data:
        ins = item.insert
        if isinstance(ins, str):
            if ins.strip():
                content.extend(replace_sticker(ins))
        elif v := ins.vod:
            content.append(
                Creator.video(
                    url_or_task=v.resolutions[0].url,
                    cover_url=v.cover,
                    duration=v.duration,
                )
            )
        elif link := ins.link_card:
            content.append(
                Creator.link(
                    text=link.title,
                    url=link.origin_url,
                )
            )
        elif url := ins.image:
            content.append(Creator.graphic(url=url))
        elif custom_emoticon := ins.custom_emoticon:
            content.append(
                Creator.sticker(
                    url=custom_emoticon.url,
                    desc=ins.backup_text,
                )
            )
        elif bili_iframe := ins.video:
            qs = parse_qs(urlparse(bili_iframe).query, keep_blank_values=True)
            if bvid := qs.get("bvid"):
                content.append(
                    Creator.link(
                        url=f"https://www.bilibili.com/video/{bvid[0]}", text=bvid[0]
                    )
                )

    return content
