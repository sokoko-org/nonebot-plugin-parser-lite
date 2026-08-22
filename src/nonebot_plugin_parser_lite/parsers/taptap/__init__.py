from typing import ClassVar

from ...utils.log import logger
from ..base import (
    BaseParser,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
    pconfig,
)
from .comment import decoder as commentDecoder
from .moment import decoder as momentDecoder
from .video import decoder as videoDecoder


class TapTapParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.TAPTAP, display_name="TapTap"
    )
    X_UA: ClassVar[str] = "V=1&PN=WebApp&LANG=zh_CN&VN_CODE=93&VN=0.1.0&LOC=CN&PLT=PC"

    def __init__(self):
        super().__init__()
        self.httpx.base_url = "https://www.taptap.cn"

    @handle("www.taptap.cn", r"moment/(?P<moment_id>\d+)")
    async def parse_moment(self, searched: MatchWithParams):
        moment_id = searched["moment_id"]
        resp = await self.httpx.get(
            "/webapiv2/moment/v3/detail",
            params={"id": moment_id, "X-UA": self.X_UA},
        )
        if not resp.is_success:
            raise ParseException(f"请求失败: {resp.status_code} - {resp.text}")
        moment = momentDecoder.decode(resp.content).data
        content = moment.content
        if video_id := moment.video_id:
            resp = await self.httpx.get(
                "/webapiv2/video-resource/v1/multi-get",
                params={"video_ids": video_id, "X-UA": self.X_UA},
            )
            if not resp.is_success:
                raise ParseException(
                    f"视频资源请求失败: {resp.status_code} - {resp.text}"
                )
            videos = videoDecoder.decode(resp.content).data
            content.extend(videos.content)
        try:
            resp = await self.httpx.get(
                "/webapiv2/moment-comment/v1/by-moment",
                params={
                    "moment_id": moment_id,
                    "X-UA": self.X_UA,
                    "sort": "rank",
                    "order": "desc",
                    "limit": pconfig.max_comments,
                },
            )

            comments = commentDecoder.decode(resp.content).comments
        except Exception:
            logger.exception("获取帖子评论失败")
            comments = []
        return self.result(
            author=moment.author,
            url=moment.url,
            title=moment.title,
            content=content,
            comments=comments,
            stats=moment.stats,
            timestamp=moment.timestamp,
        )
