import re
from re import Match
from typing import ClassVar

from httpx import AsyncClient
from nonebot import logger

from ..base import (
    BaseParser,
    PlatformEnum,
    ParseException,
    handle,
    Platform,
    MediaContent,
)
from .share import decoder as shareDecoder

ROUTER_DATA = re.compile(
    r"<script\s+async=\"\"\s+data-script-src=\"modern-inline\">_ROUTER_DATA\s*=\s*({[\s\S]*?});",
    flags=re.DOTALL,
)


class QSMusicParser(BaseParser):
    # 平台信息
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.QSMUSIC, display_name="汽水音乐"
    )

    @handle("qishui.douyin.com", r"https?://[^\s]*?qishui\.douyin\.com/s/[a-zA-Z0-9]+/")
    async def _parse_qsmusic_share(self, searched: Match[str]):
        """解析汽水音乐分享链接"""
        share_url = searched.group(0)

        async with AsyncClient(
            follow_redirects=True, headers=self.ios_headers
        ) as client:
            response = await client.get(share_url)
            response.raise_for_status()
            html = response.text
        if matched := ROUTER_DATA.search(html):
            raw = matched[1]
        else:
            raise ParseException("未找到结构化数据")
        music_data = shareDecoder.decode(
            raw
        ).loaderData.track_page.audioWithLyricsOption
        contents: list[MediaContent] = [
            self.create_audio(
                music_data.url,
                duration=music_data.duration,
                audio_name=f"{music_data.trackName}.mp3",
            )
        ]
        text = f"专辑: {music_data.trackInfo.album.name}"
        text += f"\n歌词:\n{music_data.lyrics}"

        # 构建额外信息
        extra = {
            "lyric": text,
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
