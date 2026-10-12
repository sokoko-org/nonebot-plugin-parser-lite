from typing import ClassVar

from anyio import Path

from ...download import DOWNLOADER
from ..base import (
    BaseParser,
    ContentItem,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .decrypt import decrypt_qqmusic_file


class QQMusicDecrypter:
    def __init__(self, url: str, mid: str, ekey: str):
        self.url = url
        self.ekey = ekey
        self.mid = mid

    async def __call__(self) -> Path:
        f = await DOWNLOADER.download_audio(
            url=self.url,
            cache_key=f"qqmusic:{self.mid}",
            cache_variant="source",
        )
        return await decrypt_qqmusic_file(f, self.ekey) if self.ekey else f


class QQMusicParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.QQMUSIC, display_name="QQ音乐"
    )

    # https://y.qq.com/n/ryqq_v2/songDetail/0039MnYb0qxYhV
    # https://i2.y.qq.com/n3/other/pages/playsong/index.html?ADTAG=ryqq.songDetail&songmid=0039MnYb0qxYhV&songid=0&songtype=0
    @handle("y.qq.com", r"songDetail/(?P<songmid>[0-9a-zA-Z]+)")
    @handle("y.qq.com", params={"songmid": {}, "ADTAG": {"equals": "ryqq.songDetail"}})
    async def _parse_qqmusic_share(self, searched: MatchWithParams):
        mid = searched["songmid"]

        resp = await self.httpx.get(
            "https://parse-api.sokoko.org/api/qq/song",
            params={"music_id": mid, "quality": "high"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data["code"] != 200:
            raise ParseException(f"接口返回错误: {data}")
        music_data = data["data"]
        audio_url = music_data["download_url"]
        if not audio_url.startswith("http"):
            raise ParseException("无效音乐URL")
        duration = music_data["duration_seconds"]
        audio_content = self.create_audio(
            url_or_task=QQMusicDecrypter(audio_url, mid, music_data["ekey"]),
            duration=duration,
        )
        dis_dura = audio_content.display_duration

        contents: list[ContentItem] = []
        if cover_url := music_data["cover"]:
            contents.append(self.create_image(cover_url, need_send=False))

        contents.append(audio_content)
        if lyric := music_data["lyric"]:
            contents.append(lyric)
        quality = music_data["quality"]["name"]

        extra = {
            "album": music_data["album"],
            "info": f"时长: {dis_dura} | {quality}",
            "type": "audio",
            "type_tag": "音乐",
        }

        return self.result(
            title=music_data["title"],
            author=self.create_author(
                name=music_data["artist"], avatar_url=music_data["artist_pic"]
            ),
            url=f"https://y.qq.com/n/ryqq_v2/songDetail/{mid}",
            content=contents,
            extra=extra,
        )
