from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import ContentItem, Creator
from ...download import DOWNLOADER


class PlayUrl(Struct):
    url: str


class Info(Struct):
    duration: int


class RawCover(Struct):
    url: str


class Video(Struct):
    video_id: int
    play_url: PlayUrl
    info: Info
    raw_cover: RawCover


class Data(Struct):
    videos: list[Video] = field(name="list")

    @property
    def content(self) -> list[ContentItem]:
        return [
            Creator.video(
                url_or_task=DOWNLOADER.download_m3u8_video(
                    url=video.play_url.url,
                    cache_key=f"taptap:{video.video_id}",
                ),
                cover_url=video.raw_cover.url,
                duration=video.info.duration,
                cache_key=f"taptap:{video.video_id}",
            )
            for video in self.videos
        ]


class Response(Struct):
    data: Data


decoder = Decoder(Response)
