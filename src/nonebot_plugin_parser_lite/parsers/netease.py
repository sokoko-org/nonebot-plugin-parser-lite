import contextlib
from typing import ClassVar
from urllib.parse import urlparse

from ..exception import ParseException, TipException
from .base import (
    BaseParser,
    ContentItem,
    MatchWithParams,
    Platform,
    PlatformEnum,
    handle,
)

SONG_DETAIL = "https://music.163.com/api/song/detail"
SONG_LYRIC = "https://music.163.com/api/song/lyric"
OUTER_AUDIO = "https://music.163.com/song/media/outer/url"


class NCMParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.NETEASE, display_name="网易云音乐"
    )

    @handle("163cn.tv", r"https?://[^\s]*?163cn\.tv/[a-zA-Z0-9]+")
    async def _parse_163cn(self, searched: MatchWithParams):
        return await self.parse_with_redirect(searched[0])

    @handle("music.163.com", params={"id": {"as_int": True}})
    @handle("music.163.com", r"song/(?P<id>\d+)")
    async def _parse_netease(self, searched: MatchWithParams):
        ncm_id = searched["id"]
        detail = await self.httpx.get(SONG_DETAIL, params={"ids": f"[{ncm_id}]"})
        detail.raise_for_status()
        info = detail.json()
        code = info.get("code")
        if code != 200:
            raise ParseException(f"网易云歌曲详情接口返回 code={code}")
        songs = info.get("songs") or []
        if not songs:
            raise TipException("网易云音乐没有查到这首歌，歌单和专辑链接暂不支持解析")
        song = songs[0]

        title = song.get("name") or "未知"
        artist = (
            "、".join(name for item in song.get("artists") or [] if (name := item.get("name")))
            or "未知歌手"
        )
        duration = float(song.get("duration") or 0) / 1000

        # 匿名可用的音源只有这条外链，只有 302 落在 /404 才是真的没有音源
        outer = await self.httpx.get(
            OUTER_AUDIO, params={"id": f"{ncm_id}.mp3"}, follow_redirects=False
        )
        location = outer.headers.get("location") or ""
        if not outer.is_redirect or not location:
            raise ParseException(f"网易云音频外链接口没有音源跳转: {outer.status_code}")
        audio_url = str(outer.url.join(location))
        if urlparse(audio_url).path.rstrip("/") == "/404":
            if song.get("fee"):
                raise TipException("网易云音乐该歌曲需要 VIP 或付费，取不到整曲音源")
            raise TipException("网易云音乐没有可播放的音频源，可能受版权限制")

        lyric = ""
        with contextlib.suppress(Exception):
            lyric_resp = await self.httpx.get(
                SONG_LYRIC, params={"id": ncm_id, "lv": "-1", "kv": "-1", "tv": "-1"}
            )
            lyric_resp.raise_for_status()
            lyric = (lyric_resp.json().get("lrc") or {}).get("lyric") or ""

        contents: list[ContentItem] = []
        audio = self.create_audio(
            audio_url,
            duration=duration,
            cache_key=f"netease:{ncm_id}",
        )
        contents.append(audio)

        if cover_url := (song.get("album") or {}).get("picUrl"):
            contents.append(self.create_image(cover_url))
        if lyric:
            contents.append(lyric)

        extra = {"info": f"大小: {await audio.get_display_size()}"}

        return self.result(
            title=title,
            author=self.create_author(name=artist),
            url=f"https://music.163.com/song/{ncm_id}",
            content=contents,
            extra=extra,
        )
