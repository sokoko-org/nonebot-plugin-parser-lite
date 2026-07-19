from typing import ClassVar

from msgspec import convert

from ..base import (
    BaseParser,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .model import Data


class DouBaoParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.DOUBAO, display_name="豆包"
    )

    # https://www.doubao.com/video-sharing?source_type=mobile&share_id=49939181380407810&video_id=v0369cg10004d9867lqljht6t4tvhh30
    @handle("www.doubao.com/video-sharing", params={"share_id": {}, "video_id": {}})
    async def _parse(self, searched: MatchWithParams):
        share_id = searched["share_id"]
        video_id = searched["video_id"]

        resp = await self.httpx.post(
            "https://www.doubao.com/creativity/share/get_video_share_info",
            json={
                "share_id": share_id,
                "vid": video_id,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data["code"] != 0:
            raise ParseException(f"豆包接口返回错误: {data}")
        result = convert(data["data"], type=Data)
        return self.result(
            author=self.create_author(
                name=result.user_info.nickname,
                id=str(result.user_info.user_id),
            ),
            url=f"https://www.doubao.com/video-sharing?share_id={share_id}&video_id={video_id}",
            content=[
                result.prompt,
                self.create_video(
                    url_or_task=result.play_info.main,
                    cover_url=result.play_info.poster_url,
                ),
            ],
        )
