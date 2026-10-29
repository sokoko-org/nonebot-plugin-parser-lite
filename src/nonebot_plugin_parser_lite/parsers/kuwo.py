import asyncio
from decimal import ROUND_HALF_UP, Decimal
from itertools import chain, islice
from typing import ClassVar

from nonebot import logger

from ..utils.format import format_num
from .base import (
    BaseParser,
    Comment,
    ContentItem,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
    pconfig,
)


class KuWoParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.KUWO, display_name="酷我音乐"
    )

    async def fetch_comments(self, rid: str) -> list[Comment]:
        if not pconfig.max_comments:
            return []
        try:
            response = await self.httpx.get(
                "https://ncomment.kuwo.cn/com.s",
                params={
                    "f": "web",
                    "type": "get_rec_comment",
                    "isadd": "1",
                    "aapiver": "1",
                    "uid": "",
                    "digest": "15",
                    "sid": rid,
                    "start": "0",
                    "count": pconfig.max_comments,
                },
            )
            response.raise_for_status()
            data = response.json()
            if data["code"] != "200":
                raise ParseException(f"酷我音乐评论接口返回错误: {data}")
            comments = chain(
                data["top_comments"], data["hot_comments"], data["comments"]
            )
            return [
                self._to_comment(comment)
                for comment in islice(comments, pconfig.max_comments)
            ]
        except Exception as e:
            logger.warning(f"酷我音乐评论获取失败: {e}")
            return []

    def _to_comment(self, data: dict) -> Comment:
        comment = self.create_comment(
            author=self.create_author(
                name=data["u_name"], avatar_url=data["u_pic"], id=data["u_id"]
            ),
            content=[data["msg"]],
            timestamp=int(data["time"]),
            stats=self.create_stats(
                like_count=format_num(int(data["like_num"])),
                comment_count=format_num(data.get("child_comment_count", 0)),
            ),
        )
        for reply in data.get("child_comments", [])[:5]:
            comment.add_reply(self._to_comment(reply))
        return comment

    async def fetch_info(self, rid: str) -> dict:
        response = await self.httpx.get(
            "http://datacenter.kuwo.cn/d.c",
            params={
                "resenc": "utf8",
                "corp": "kuwo",
                "ids": rid,
                "source": "kwplayer_ar_10.8.6.1_40.apk",
                "cmd": "query",
                "cmkey": "plist_pl2012",
                "ft": "music",
            },
        )
        response.raise_for_status()
        if songs := response.json():
            return songs[0]
        else:
            raise ParseException(f"未找到酷我音乐歌曲: {rid}")

    async def fetch_audio(self, rid: str) -> tuple[str, str]:
        for bitrate in (320, 192, 128):
            response = await self.httpx.get(
                "http://mobi.kuwo.cn/mobi.s",
                params={
                    "type": "convert_url_with_sign",
                    "br": f"{bitrate}kmp3",
                    "user": "0",
                    "priority": "bitrate",
                    "surl": "1",
                    "source": "kwplayer_ar_5.1.0.0_B_jiakong_vh.apk",
                    "rid": rid,
                    "f": "web",
                },
            )
            response.raise_for_status()
            data = response.json()
            data = data.get("data", data)
            audio_url = data.get("url") or data.get("purl") or data.get("surl")
            if not audio_url:
                continue
            if audio_url.startswith("//"):
                audio_url = f"https:{audio_url}"
            if audio_url.startswith(("http://", "https://")):
                return audio_url, f"MP3 {bitrate}K"
        raise ParseException("无法获取酷我音乐音频下载地址")

    async def fetch_lyric(self, rid: str) -> str:
        response = await self.httpx.get(
            "https://kuwo.cn/openapi/v1/www/lyric/getlyric",
            params={"musicId": rid},
        )
        response.raise_for_status()
        data = response.json()
        if data["code"] != 200:
            raise ParseException(f"酷我音乐歌词接口返回错误: {data}")
        lines = []
        for row in data["data"]["lrclist"]:
            centiseconds = int(
                (Decimal(str(row["time"])) * 100).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            minutes, remainder = divmod(centiseconds, 6000)
            seconds, fraction = divmod(remainder, 100)
            text = " ".join(row["lineLyric"].split())
            lines.append(f"[{minutes:02d}:{seconds:02d}.{fraction:02d}]{text}")
        return "\n".join(lines)

    @handle("kuwo.cn", r"play_detail/(\d+)")
    async def _parse_kuwo_share(self, searched: MatchWithParams):
        """解析酷我音乐分享链接"""
        rid = searched[1]

        music_data, (audio_url, quality), lyric, comments = await asyncio.gather(
            self.fetch_info(rid),
            self.fetch_audio(rid),
            self.fetch_lyric(rid),
            self.fetch_comments(rid),
        )
        audio_content = self.create_audio(
            url_or_task=audio_url,
            duration=int(music_data["duration"]),
            cache_key=f"kuwo:{rid}",
        )
        dis_dura = audio_content.display_duration

        contents: list[ContentItem] = []
        if cover_url := music_data["albumpic"]:
            contents.append(self.create_image(cover_url, need_send=False))

        contents.append(audio_content)
        if lyric:
            contents.append(lyric)

        extra = {
            "album": music_data["album"],
            "info": f"时长: {dis_dura} | {quality}",
        }

        return self.result(
            title=music_data["name"],
            author=self.create_author(
                name=music_data["artist"], avatar_url=music_data["artistPic"]
            ),
            url=f"https://www.kuwo.cn/play_detail/{rid}",
            content=contents,
            comments=comments,
            extra=extra,
        )
