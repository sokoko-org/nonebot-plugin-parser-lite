from __future__ import annotations

from datetime import datetime
import re

from bs4 import BeautifulSoup
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


class StatusesComment(Struct):
    created_at: str
    text: str
    "may html"
    id: str
    source: str
    user: User
    like_count: int = 0
    pic_infos: dict[str, Pic] | None = None
    comments: list[StatusesComment] | bool = field(default_factory=list)

    @property
    def replies(self):
        return self.comments if isinstance(self.comments, list) else []

    @property
    def plain_text(self) -> str:
        """Return the comment text with HTML stripped and emoji alt text preserved.

        If the comment is HTML, this replaces emoji `<img>` tags with their `alt`
        text and removes other markup, otherwise it returns the original text.
        """
        if "<" not in self.text or ">" not in self.text:
            return self.text

        try:
            soup = BeautifulSoup(self.text, "html.parser")
        except Exception:
            return self.text

        for img in soup.find_all("img"):
            if alt := img.get("alt"):
                img.replace_with(str(alt))
            else:
                img.decompose()

        result = soup.get_text(strip=True)
        return result or self.text

    @property
    def content(self):
        data = replace_placeholder_to_sticker(self.plain_text, WEIBO_PATTERN, "weibo")
        if self.pic_infos:
            data.extend(pic.content for pic in self.pic_infos.values())
        return data

    @property
    def timestamp(self) -> int:
        dt = datetime.strptime(self.created_at, "%a %b %d %H:%M:%S %z %Y")
        dt = dt.astimezone()
        return int(dt.timestamp())


class StatusesCommentData(Struct):
    data: list[StatusesComment]


class StatusesCommentWrapper(Struct):
    data: StatusesCommentData


decoder = Decoder(StatusesCommentWrapper)
