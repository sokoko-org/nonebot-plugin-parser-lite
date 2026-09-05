from typing import ClassVar, TypeVar

from msgspec import convert

from ...data import Comment
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
from .comment import Result as CommentResult
from .feed import Result as FeedResult

T = TypeVar("T")


class DsParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.DS, display_name="大神")

    async def fetch(self, url: str, model: type[T]) -> T:
        resp = await self.httpx.get(url)
        if not resp.is_success:
            raise ParseException(
                f"Failed to fetch {url}, status code: {resp.status_code}, "
                f"text: {resp.text}"
            )
        data = resp.json()
        if data["code"] != 200:
            raise ParseException(
                f"Failed to fetch {url}, code: {data['code']}, data: {data}"
            )
        return convert(data["result"], model)

    @staticmethod
    def _merge_comments(results: list[CommentResult]) -> list[Comment]:
        merged = CommentResult()
        for result in results:
            merged.feedComments.extend(result.feedComments)
            merged.featuredReplies.extend(result.featuredReplies)
            merged.userInfos.extend(result.userInfos)
        return merged.comment_list

    @handle("ds.163.com", r"article/(?P<feed_id>[A-Za-z0-9]+)")
    @handle("ds.163.com", r"feed/(?P<feed_id>[A-Za-z0-9]+)")
    async def parse_feed(self, searched: MatchWithParams):
        feed_id = searched["feed_id"]
        feed = await self.fetch(
            f"https://inf.ds.163.com/v1/web/feed/basic/facade?feedId={feed_id}",
            FeedResult,
        )
        sid = f"{feed.feed.uid}.{feed_id}"
        comment_results: list[CommentResult] = []

        try:
            handpicked = await self.fetch(
                "https://inf.ds.163.com/v1/web/comment/getCommentsByHandpicked"
                f"?sid={sid}&tier=1",
                CommentResult,
            )
            comment_results.append(handpicked)
        except Exception:
            logger.exception("获取大神精选评论失败")

        try:
            latest = await self.fetch(
                "https://inf.ds.163.com/v1/web/comment/page"
                f"?sid={sid}&tier=1&sortDirection=DESC"
                f"&count={pconfig.max_comments}",
                CommentResult,
            )
            comment_results.append(latest)
        except Exception:
            logger.exception("获取大神评论失败")

        return self.result(
            author=feed.author,
            url=f"https://ds.163.com/feed/{feed_id}",
            title=feed.feed.title,
            content=feed.feed.content,
            stats=feed.feed.stats,
            comments=self._merge_comments(comment_results),
            timestamp=feed.feed.timestamp,
        )
