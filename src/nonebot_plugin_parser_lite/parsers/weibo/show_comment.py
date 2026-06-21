from __future__ import annotations

from datetime import datetime
import re

from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...utils.format import replace_placeholder_to_sticker

WEIBO_PATTERN = re.compile(r"\[(?P<name>[^]]+)\]")


class OriginalPic(Struct):
    url: str


class Pic(Struct):
    original: OriginalPic
    pic_id: str
    type: str
    """pic/livephoto"""
    video: str = ""
    """Live动图"""

    @property
    def content(self):
        if self.video:
            return Creator.live_photo(
                video_url=self.video,
                image_url=self.original.url,
                ext_headers={"Referer": "https://weibo.com/"},
            )
        return Creator.image(
            url=self.original.url, ext_headers={"Referer": "https://weibo.com/"}
        )


class User(Struct):
    id: int
    screen_name: str
    profile_image_url: str
    description: str


class TvComment(Struct):
    created_at: str
    text_raw: str
    id: str
    source: str
    user: User
    like_counts: int = 0
    pic_infos: dict[str, Pic] | None = None
    comments: list[TvComment] = field(default_factory=list)

    @property
    def content(self):
        data = replace_placeholder_to_sticker(self.text_raw, WEIBO_PATTERN, "weibo")
        if self.pic_infos:
            data.extend(pic.content for pic in self.pic_infos.values())
        return data

    @property
    def timestamp(self) -> int:
        dt = datetime.strptime(self.created_at, "%a %b %d %H:%M:%S %z %Y")
        dt = dt.astimezone()
        return int(dt.timestamp())


class TvCommentData(Struct):
    data: list[TvComment]


decoder = Decoder(TvCommentData)
