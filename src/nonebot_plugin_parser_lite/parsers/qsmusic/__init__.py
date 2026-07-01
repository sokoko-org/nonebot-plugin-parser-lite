import re
from typing import ClassVar

from ..base import (
    BaseParser,
    ContentItem,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .share import decoder as shareDecoder

ROUTER_DATA = re.compile(
    r"<script\s+async=\"\"\s+data-script-src=\"modern-inline\">_ROUTER_DATA\s*=\s*({[\s\S]*?});",
    flags=re.DOTALL,
)


class QSMusicParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.QSMUSIC, display_name="汽水音乐"
    )

    @handle("qishui.douyin.com", r"https?://[^\s]*?qishui\.douyin\.com/s/[a-zA-Z0-9]+/")
    async def _parse_qsmusic_share(self, searched: MatchWithParams):
        """解析汽水音乐分享链接"""
        share_url = searched[0]

        response = await self.httpx.get(share_url, headers=self.ios_headers)
        response.raise_for_status()
        html = response.text
        if matched := ROUTER_DATA.search(html):
            raw = matched[1]
        else:
            raise ParseException("未找到结构化数据")
        music_data = shareDecoder.decode(
            raw
        ).loaderData.track_page.audioWithLyricsOption
        contents: list[ContentItem] = [
            self.create_audio(
                music_data.url,
                duration=music_data.duration,
                audio_name=f"{music_data.trackName}.mp3",
            )
        ]
        extra = {
            "album": music_data.trackInfo.album.name,
            "lyric": music_data.lyrics,
            "type": "audio",
            "type_tag": "音乐",
            "type_icon": "fa-music",
        }

        return self.result(
            title=music_data.trackName,
            author=self.create_author(name=music_data.artistName),
            url=share_url,
            content=contents,
            extra=extra,
        )
