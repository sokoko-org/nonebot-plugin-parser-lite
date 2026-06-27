from typing import ClassVar

from ...creator import Creator
from ...utils.format import format_num
from ..base import (
    BaseParser,
    MatchWithParams,
    Platform,
    PlatformEnum,
    handle,
)
from .bbs import decoder


class HupuParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.HUPU, display_name="虎扑")

    # 图文
    # https://m.hupu.com/bbs-share/639669147.html
    # https://bbs.hupu.com/639669147.html
    # https://m.hupu.com/bbs/639669147.html
    @handle("m.hupu.com/bbs", r"bbs/(?P<topic_id>\d+)(?:\.html)?")
    @handle("bbs.hupu.com", r"(?P<topic_id>\d+)(?:\.html)?")
    @handle("m.hupu.com/bbs-share", r"bbs-share/(?P<topic_id>\d+)(?:\.html)?")
    async def parse_bbs(self, searched: MatchWithParams):
        topic_id = searched["topic_id"]
        res = await self.httpx.get(
            f"https://m.hupu.com/api/v1/bbs-thread-frontend/{topic_id}"
        )
        data = decoder.decode(res.content).data
        bbs = data.t_detail
        return self.result(
            author=Creator.author(
                name=bbs.user.username,
                avatar_url=bbs.user.header,
                id=bbs.user.puid,
                location=bbs.via,
            ),
            content=bbs.content,
            comments=data.comments,
            stats=Creator.stats(
                view_count=format_num(int(bbs.hits)),
                like_count=format_num(int(bbs.lights)),
                comment_count=format_num(int(bbs.replies)),
            ),
            title=bbs.title,
            timestamp=bbs.timestamp,
            url=f"https://m.hupu.com/bbs/{bbs.tid}",
        )
