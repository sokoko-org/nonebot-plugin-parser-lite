from typing import ClassVar, TypeVar

from msgspec.json import Decoder

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
from .news import decoder as newsDecoder
from .post import decoder as postDecoder

T = TypeVar("T")


class WMPVPParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.WMPVP, display_name="完美世界电竞"
    )

    async def fetch(self, decoder: Decoder[T], url: str, params: dict | None = None):
        if params is None:
            params = {}
        resp = await self.httpx.get(url, params=params)
        if not resp.is_success:
            raise ParseException(f"请求失败: {resp.status_code} - {resp.text}")
        return decoder.decode(resp.content)

    # 帖子
    # https://news.wmpvp.com/community-detail.html?id=375290247
    # https://news.wmpvp.com/community-detail.html?id=376026294
    # https://news.wmpvp.com/community-pcDetail.html?id=375290247
    @handle("news.wmpvp.com/community-detail.html", params={"id": {"as_int": True}})
    @handle("news.wmpvp.com/community-pcDetail.html", params={"id": {"as_int": True}})
    async def parse_post(self, searched: MatchWithParams):
        post_id = searched["id"]
        post = (
            await self.fetch(
                decoder=postDecoder,
                url="https://appengine.wmpvp.com/steamcn/community/post/getPostById",
                params={"postId": post_id},
            )
        ).result.post
        try:
            comment_data = await self.fetch(
                decoder=commentDecoder,
                url="https://gwapi.pwesports.cn/appuser/community/comment/getCommentList",
                params={
                    "entityId": post_id,
                    "entityType": 11,
                    "pageNum": 1,
                    "pageSize": pconfig.max_comments,
                    "sort": 4,
                    "type": 1,
                    "onlyOwner": False,
                    "ratingType": 0,
                },
            )
            comments = comment_data.comments
        except Exception:
            logger.exception("获取帖子评论失败")
            comments = []
        return self.result(
            author=post.author,
            content=post.content,
            comments=comments,
            stats=post.stats,
            title=post.title,
            timestamp=post.timestamp,
            url=post.postUrl,
        )

    # 资讯
    # https://news.wmpvp.com/news.html?id=301077&gameTypeStr=2
    @handle(
        "news.wmpvp.com/news.html",
        params={"id": {"as_int": True}, "gameTypeStr": {"as_int": True}},
    )
    async def parse_news(self, searched: MatchWithParams):
        news_id = searched["id"]
        gameTypeStr = searched["gameTypeStr"]
        news = (
            await self.fetch(
                decoder=newsDecoder,
                url="https://appactivity.wmpvp.com/steamcn/app/news/getAppNewsById",
                params={"gameType": gameTypeStr, "newsId": news_id},
            )
        ).result.news
        try:
            comment_data = await self.fetch(
                decoder=commentDecoder,
                url="https://gwapi.pwesports.cn/appuser/community/comment/getCommentList",
                params={
                    "entityId": news_id,
                    "entityType": 2,
                    "pageNum": 1,
                    "pageSize": pconfig.max_comments,
                    "sort": 4,
                    "type": 1,
                    "onlyOwner": False,
                    "ratingType": 0,
                },
            )
            comments = comment_data.comments
        except Exception:
            logger.exception("获取新闻评论失败")
            comments = []
        return self.result(
            author=news.author,
            content=news.content,
            comments=comments,
            stats=news.stats,
            title=news.title,
            timestamp=news.timestamp,
            url=news.url,
        )
