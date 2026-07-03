from typing import ClassVar

from nonebot.log import logger

from ..base import BaseParser, MatchWithParams, Platform, PlatformEnum, handle, pconfig
from .comment import decoder as commentDecoder
from .post import decoder as postDecoder


class DoubanParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.DOUBAN, display_name="豆瓣"
    )

    # https://m.douban.com/group/topic/490753319
    @handle("douban.com/group/topic/", r"topic/(?P<topic_id>\d+)")
    async def _parse(self, searched: MatchWithParams):
        topic_id = searched["topic_id"]
        res = await self.httpx.get(
            f"https://m.douban.com/rexxar/api/v2/group/topic/{topic_id}"
        )
        res.raise_for_status()
        post = postDecoder.decode(res.content)
        try:
            res = await self.httpx.get(
                f"https://m.douban.com/rexxar/api/v2/group/topic/{topic_id}/comments",
                params={
                    "count": pconfig.max_comments,
                },
            )
            res.raise_for_status()
            comments = commentDecoder.decode(res.content).comment_list
        except Exception:
            logger.exception("获取帖子评论失败")
            comments = []
        return self.result(
            author=post.author_obj,
            url=post.url,
            title=post.title,
            content=post.content,
            stats=post.stats,
            comments=comments,
            timestamp=post.timestamp,
        )
