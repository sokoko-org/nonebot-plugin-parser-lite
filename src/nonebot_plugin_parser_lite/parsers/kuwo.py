from typing import ClassVar

from ..data import ContentItem, Platform
from .base import (
    BaseParser,
    MatchWithParams,
    ParseException,
    PlatformEnum,
    handle,
)


def display_duration(duration: int) -> str:
    try:
        total_seconds = duration
        if total_seconds <= 0:
            return "0:00"

        minutes, seconds = divmod(total_seconds, 60)
        if minutes < 60:
            return f"{minutes}:{seconds:02d}"

        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    except (TypeError, ValueError):
        return "NaN"


# ref https://kw-api.cenguigui.cn/
class KuWoParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.KUWO, display_name="酷我音乐"
    )

    @handle("kuwo.cn", r"play_detail/(\d+)")
    async def _parse_kuwo_share(self, searched: MatchWithParams):
        """解析酷我音乐分享链接"""
        rid = searched[1]

        # 使用API解析
        resp = await self.httpx.get(
            "https://kw-api.cenguigui.cn/",
            params={"id": rid, "type": "song", "level": "exhigh", "format": "json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data["code"] != 200:
            raise ParseException(f"酷我音乐接口返回错误: {data.get('msg', '未知错误')}")
        music_data = data["data"]
        audio_url = music_data["url"]
        if not audio_url.startswith("http"):
            raise ParseException("无效音乐URL")
        duration = music_data["duration"]
        audio_name = f"{music_data['name']}-{music_data['artist']}.mp3"
        audio_content = self.create_audio(audio_url, duration, audio_name=audio_name)
        dis_dura = display_duration(music_data["duration"])

        contents: list[ContentItem] = []
        if cover_url := music_data.get("pic"):
            contents.append(self.create_image(cover_url, need_send=False))

        contents.append(audio_content)

        extra = {
            "album": music_data.get("album"),
            "info": f"时长: {dis_dura}",
            "lyric": music_data.get("lyric"),
            "type": "audio",
            "type_tag": "音乐",
            "type_icon": "fa-music",
        }

        return self.result(
            title=music_data["name"],
            author=self.create_author(name=music_data["artist"]),
            url=f"https://www.kuwo.cn/play_detail/{rid}",
            content=contents,
            extra=extra,
        )
