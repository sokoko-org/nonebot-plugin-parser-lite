from typing import ClassVar

from ...utils.format import format_num
from ..base import (
    DOWNLOADER,
    BaseParser,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .video import decoder as videoDecoder

MKEY = (
    "AAHewK3eIAAyMjA2MDMyMjQAAhAAMEP1uwSG3TvhYAAAAO5fOOpIdKsH2h4IGsF6BlVwnGQA6_"
    "eLEvGiajzUp4_YthxOPC-hxcOpTk0SPSrxyhbdkmIwsXnF9PgS5ly8eQyjuXlcS7VpWG0QlK0HakVDamteMHNHIui0A8V4tmELqQ=="
)


class AcfunParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.ACFUN, display_name="ACFUN"
    )

    @handle("acfun.cn/v", r"(?:ac=|/ac)(?P<acid>[_\d]+)")
    async def _parse(self, searched: MatchWithParams):
        acid = searched["acid"]
        if "_" in acid:
            raise ParseException("暂不支持多p视频")

        resp = await self.httpx.get(
            "https://api-new.app.acfun.cn/rest/app/douga/info",
            params={"mkey": MKEY, "dougaId": acid},
        )
        if not resp.is_success:
            raise ParseException(resp.text)
        video_info = videoDecoder.decode(resp.content)
        author = self.create_author(
            name=video_info.user.name,
            avatar_url=video_info.user.headUrl,
            id=video_info.user.id,
            location=video_info.user.ipLocation,
            avatar_cache_key=f"acfun:{video_info.user.id}",
        )

        video_content = self.create_video(
            url_or_task=DOWNLOADER.download_m3u8_video(
                url=video_info.currentVideoInfo.playInfos[0].playUrls[-1],
                cache_key=f"acfun:{acid}",
            ),
            cover_url=video_info.coverUrl,
            duration=video_info.durationMillis // 1000,
            cache_key=f"acfun:{acid}",
        )
        video_content.is_dynamic_size = True

        return self.result(
            title=video_info.title,
            author=author,
            timestamp=video_info.timestamp,
            content=[video_info.text, video_content],
            stats=self.create_stats(
                view_count=format_num(video_info.viewCount),
                like_count=format_num(video_info.likeCount),
                collect_count=format_num(video_info.stowCount),
                share_count=format_num(video_info.shareCount),
                comment_count=format_num(video_info.commentCount),
                extra={
                    "banana": ("香蕉", format_num(video_info.bananaCount)),
                    "danmaku": ("弹幕", format_num(video_info.danmakuCount)),
                },
            ),
            url=f"https://www.acfun.cn/v/ac{acid}",
        )
