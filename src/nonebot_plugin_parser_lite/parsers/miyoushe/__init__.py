from typing import ClassVar

from nonebot.log import logger

from ..base import BaseParser, MatchWithParams, Platform, PlatformEnum, handle, pconfig
from .comment import decoder as commentDecoder
from .post import decoder as postDecoder


class MiyousheParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.MIYOUSHE, display_name="米游社"
    )

    def __init__(self):
        super().__init__()
        self.httpx.headers.update({"Referer": "https://www.miyoushe.com/"})

    # https://m.miyoushe.com/zzz/#/article/76178399
    # https://m.miyoushe.com/zzz?channel=beta/#/article/76178399
    # https://www.miyoushe.com/ys/article/75247726
    @handle(
        "miyoushe.com",
        r"/(?P<forum>[a-zA-Z]+)(.*)/#/article/(?P<post_id>\d+)",
    )
    @handle(
        "miyoushe.com",
        r"/(?P<forum>[a-zA-Z]+)/article/(?P<post_id>\d+)",
    )
    async def _(self, searched: MatchWithParams):
        post_id = searched["post_id"]
        forum = searched["forum"]
        res = await self.httpx.get(
            "https://bbs-api.miyoushe.com/post/wapi/getPostFull",
            params={"post_id": post_id},
        )
        res.raise_for_status()
        post = postDecoder.decode(res.content)
        try:
            res = await self.httpx.get(
                "https://bbs-api.miyoushe.com/post/wapi/getPostReplies",
                params={
                    "post_id": post_id,
                    "is_hot": True,
                    "size": pconfig.max_comments,
                },
            )
            res.raise_for_status()
            comments = commentDecoder.decode(res.content).comments
        except Exception:
            logger.exception("获取帖子评论失败")
            comments = []
        return self.result(
            author=self.create_author(
                name=post.user.nickname,
                avatar_url=post.user.avatar_url,
                id=post.user.uid,
            ),
            url=f"https://m.miyoushe.com/{forum}/#/article/{post_id}",
            content=post.post.content,
            title=post.post.subject,
            stats=post.stats,
            timestamp=post.post.updated_at,
            comments=comments,
        )
