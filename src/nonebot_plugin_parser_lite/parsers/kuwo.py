from typing import ClassVar

from .base import (
    BaseParser,
    ContentItem,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)


# ref https://kw-api.cenguigui.cn/
class KuWoParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.KUWO, display_name="酷我音乐"
    )

    @handle("kuwo.cn", r"play_detail/(\d+)")
    async def _parse_kuwo_share(self, searched: MatchWithParams):
        """解析酷我音乐分享链接"""
        rid = searched[1]

        resp = await self.httpx.get(
            "https://parse-api.sokoko.org/api/kuwo/songs/",
            params={"music_id ": rid, "quality": "320k"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data["code"] != 200:
            raise ParseException(f"酷我音乐接口返回错误: {data}")
        music_data = data["data"]
        audio_url = music_data["download_url"]
        if not audio_url.startswith("http"):
            raise ParseException("无效音乐URL")
        duration = music_data["duration_seconds"]
        audio_content = self.create_audio(
            url=audio_url,
            duration=duration,
            cache_key=f"kuwo:{rid}",
        )
        dis_dura = audio_content.display_duration

        contents: list[ContentItem] = []
        if cover_url := music_data["cover"]:
            contents.append(self.create_image(cover_url, need_send=False))

        contents.append(audio_content)
        quality = music_data["quality"]["name"]

        extra = {
            "album": music_data["album"],
            "info": f"时长: {dis_dura} | {quality}",
            "lyric": music_data["lyric"],
            "type": "audio",
            "type_tag": "音乐",
            "type_icon": "fa-music",
        }

        return self.result(
            title=music_data["title"],
            author=self.create_author(
                name=music_data["artist"], avatar_url=music_data["artist_pic"]
            ),
            url=f"https://www.kuwo.cn/play_detail/{rid}",
            content=contents,
            extra=extra,
        )
