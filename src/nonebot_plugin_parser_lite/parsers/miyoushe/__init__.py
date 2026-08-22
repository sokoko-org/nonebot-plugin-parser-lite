from typing import ClassVar

from ...utils.log import logger
from ..base import BaseParser, MatchWithParams, Platform, PlatformEnum, handle, pconfig
from .comment import decoder as commentDecoder
from .post import decoder as postDecoder
from .ugc import decoder as ugcDecoder


class MiyousheParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.MIYOUSHE, display_name="米游社"
    )

    def __init__(self):
        super().__init__()
        self.httpx.headers.update({"Referer": "https://www.miyoushe.com/"})

    # https://m.miyoushe.com/zzz/#/article/76178399
    # https://m.miyoushe.com/zzz?channel=beta/#/article/76178399
    # https://m.miyoushe.com/zzz?channel=xiaomi/#/article/76036598
    # https://www.miyoushe.com/ys/article/75247726
    @handle(
        "miyoushe.com",
        r"article/(?P<post_id>\d+)",
    )
    async def _(self, searched: MatchWithParams):
        post_id = searched["post_id"]
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
                avatar_cache_key=f"miyoushe:{post.user.uid}",
            ),
            url=post.url,
            content=post.post.content,
            title=post.post.subject,
            stats=post.stats,
            timestamp=post.post.created_at,
            comments=comments,
        )

    @handle(
        "act.miyoushe.com/ys/ugc_community/mx",
        params={"id": {"as_int": True}, "region": {}},
    )
    async def parse_ugc(self, searched: MatchWithParams):
        ugc_id = searched["id"]
        region = searched["region"]
        res = await self.httpx.post(
            "https://bbs-api.miyoushe.com/community/ugc_community/web/api/level/full/info",
            json={
                "level_id": ugc_id,
                "region": region,
                "agg_req_list": [
                    {"api_name": "level_detail"},
                    {"api_name": "reply_card"},
                    {"api_name": "developer_info"},
                ],
            },
        )
        res.raise_for_status()
        ugc = ugcDecoder.decode(res.content).data.resp_map
        return self.result(
            author=ugc.author,
            content=ugc.content,
            title=ugc.title,
            stats=ugc.stats,
            comments=ugc.comments,
            url=f"https://act.miyoushe.com/ys/ugc_community/mx/#/pages/level-detail/index?id={ugc_id}&region={region}",
        )
