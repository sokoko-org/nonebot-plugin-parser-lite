from typing import ClassVar

from ..base import BaseParser, MatchWithParams, Platform, PlatformEnum, handle
from .post import decoder as postDecoder


class MiyousheParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.MIYOUSHE, display_name="米游社"
    )

    def __init__(self):
        super().__init__()
        self.httpx.headers.update({"Referer": "https://www.miyoushe.com/"})

    @handle("miyoushe.com", r"article/(?P<post_id>\d+)")
    async def _(self, searched: MatchWithParams):
        res = await self.httpx.get(
            "https://bbs-api.miyoushe.com/post/wapi/getPostFull",
            params={"post_id": searched["post_id"]},
        )
        res.raise_for_status()
        post = postDecoder.decode(res.content)
        return self.result(
            author=self.create_author(
                name=post.user.nickname,
                avatar_url=post.user.avatar_url,
                id=post.user.uid,
            ),
            url=post.share_info.origin_url,
            content=post.post.content,
            title=post.post.subject,
            stats=post.stats,
        )
