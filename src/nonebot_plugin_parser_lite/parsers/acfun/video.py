from msgspec import Struct
from msgspec.json import Decoder

from ...utils.format import html_to_text


class User(Struct):
    name: str
    headUrl: str
    gender: int
    fanCountValue: int
    followingCountValue: int
    ipLocation: str
    id: str


class cdnUrl(Struct):
    url: str


class PlayInfo(Struct):
    qualityLabel: str
    fps: int
    playUrls: list[str]
    cdnUrls: list[cdnUrl]


class CurrentVideoInfo(Struct):
    playInfos: list[PlayInfo]
    fileName: str
    id: str


class VideoInfo(Struct, kw_only=True):
    title: str
    description: str | None
    createTimeMillis: int
    user: User
    currentVideoInfo: CurrentVideoInfo
    coverUrl: str
    viewCount: int
    bananaCount: int
    commentCount: int
    danmakuCount: int
    shareCount: int
    likeCount: int
    stowCount: int
    durationMillis: int

    @property
    def text(self) -> str:
        return f"简介: {html_to_text(self.description)}" if self.description else ""

    @property
    def timestamp(self) -> int:
        return self.createTimeMillis // 1000


decoder = Decoder(VideoInfo)
