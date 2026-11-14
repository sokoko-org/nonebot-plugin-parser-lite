from datetime import datetime, timedelta, timezone
from itertools import chain, islice
from typing import ClassVar

from ..utils.format import format_num
from ..utils.log import logger
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


class MiguParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.MIGU, display_name="咪咕音乐"
    )

    async def fetch_comments(self, mid: str) -> list[Comment]:
        if not pconfig.max_comments:
            return []
        try:
            response = await self.httpx.get(
                "https://c.musicapp.migu.cn/MIGUM3.0/user/comment/stack/v1.0",
                params={
                    "resourceId": mid,
                    "resourceType": "2",
                    "pageSize": pconfig.max_comments,
                    "page": 1,
                },
            )
            response.raise_for_status()
            data = response.json()
            if data["code"] != "000000":
                raise ParseException(f"咪咕音乐评论接口返回错误: {data}")
            comments = chain(data["data"]["hotComments"], data["data"]["comments"])
            return [
                self._to_comment(comment)
                for comment in islice(comments, pconfig.max_comments)
            ]
        except Exception as e:
            logger.warning(f"咪咕音乐评论获取失败: {e}")
            return []

    def _to_comment(self, data: dict) -> Comment:
        user = data["user"]
        comment_time = data.get("commentTime") or data["replyTime"]
        timestamp = int(
            datetime.strptime(comment_time, "%Y-%m-%d %H:%M")
            .replace(tzinfo=timezone(timedelta(hours=8)))
            .timestamp()
        )
        comment = self.create_comment(
            author=self.create_author(
                name=user["nickName"], avatar_url=user["bigIcon"], id=user["userId"]
            ),
            content=[data.get("commentInfo", data.get("replyInfo", ""))],
            timestamp=timestamp,
            stats=self.create_stats(
                like_count=format_num(data.get("opNumItem", {}).get("thumbNum")),
                comment_count=format_num(data.get("replyTotalCount")),
            ),
        )
        for reply in data.get("replyComments", [])[:5]:
            parent = None
            if target_user := reply.get("targetUser"):
                parent = self.create_author(
                    name=target_user["nickName"],
                    avatar_url=target_user["bigIcon"],
                    id=target_user["userId"],
                )
            comment.add_reply(self._to_comment(reply), parent=parent)
        return comment

    @handle(
        "h5.nf.migu.cn/app/v4/p/share/song-new/index.html",
        params={"id": {"as_int": True}},
    )
    async def _parse_contentId(self, searched: MatchWithParams):
        return await self._parse(contentId=searched["id"])

    async def _parse(self, contentId: str):
        resp = await self.httpx.get(
            "https://parse-api.sokoko.org/api/qq/song",
            params={"ctid": contentId, "quality": "320k"},
        )
        data = resp.json()
        if data["code"] != 200:
            raise ParseException(f"接口返回错误: {data}")
        music_data = data["data"]
        mid = music_data["id"]
        audio_url = music_data["download_url"]
        if not audio_url.startswith("http"):
            raise ParseException("无效音乐URL")
        duration = music_data["duration_seconds"]
        audio_content = self.create_audio(
            url_or_task=audio_url, duration=duration, cache_key=f"migu:{mid}"
        )

        contents: list[ContentItem] = []
        if cover_url := music_data["cover"]:
            contents.append(self.create_image(cover_url, need_send=False))

        contents.append(audio_content)
        if lyric := music_data["lyric"]:
            contents.append(lyric)

        extra = {
            "album": music_data["album"],
        }

        return self.result(
            title=music_data["title"],
            author=self.create_author(
                name=music_data["artist"], avatar_url=music_data["artist_pic"]
            ),
            url=f"https://h5.nf.migu.cn/app/v4/p/share/song-new/index.html?id={mid}",
            content=contents,
            comments=await self.fetch_comments(mid),
            extra=extra,
        )
