import re
from typing import ClassVar
from msgspec import convert
from nonebot import logger

from .reply import Reply
from .feed import Feed

from ..base import (
    BaseParser,
    PlatformEnum,
    handle,
    Platform,
    ParseResult,
    ParseException,
)
from ...utils.format import format_num

NEXT_DATA = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>\s*(.*?)\s*</script>',
    re.IGNORECASE | re.DOTALL,
)


class CoolapkParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.COOLAPK, display_name="酷安"
    )

    @handle("coolapk1s.com/feed/", r"coolapk1s\.com/feed/(?P<feed_id>\d+)")
    @handle("www.coolapk.com/feed/", r"www\.coolapk\.com/feed/(?P<feed_id>\d+)")
    @handle("coolapk.com/feed/", r"coolapk\.com/feed/(?P<feed_id>\d+)")
    async def _parse(self, searched: re.Match[str]) -> ParseResult:
        feed_id = searched.group("feed_id")
        response = await self.httpx.get(f"https://www.coolapk1s.com/feed/{feed_id}")
        response.raise_for_status()

        if matched := NEXT_DATA.search(response.text):
            next_data = convert(matched[1], Feed)
        else:
            raise ParseException(f"未找到酷安页面数据: {feed_id}")
        feed = next_data.props.pageProps

        comments = []
        try:
            response = await self.httpx.get(
                f"https://www.coolapk1s.com/reply/{feed_id}"
            )
            response.raise_for_status()
            if matched := NEXT_DATA.search(response.text):
                reply_data = convert(matched[1], Reply)
            else:
                reply_data = None

            if reply_data is not None:
                comments = [
                    self.create_comment(
                        author=self.create_author(
                            name=sc.username, avatar_url=sc.userAvatar
                        ),
                        content=sc.content,
                        timestamp=sc.dateline,
                        stats=self.create_stats(
                            like_count=format_num(sc.likenum),
                            comment_count=format_num(sc.replynum),
                        ),
                        replies=[
                            self.create_comment(
                                author=self.create_author(name=csc.username),
                                content=csc.content,
                                timestamp=csc.dateline,
                            )
                            for csc in sc.replyRows
                        ],
                    )
                    for sc in reply_data.props.pageProps.replies
                ]
        except Exception as e:
            logger.warning(f"酷安评论获取失败: {e}")

        return self.result(
            author=self.create_author(
                name=feed.feed.username, avatar_url=feed.feed.userAvatar
            ),
            content=feed.feed.content,
            timestamp=feed.feed.dateline,
            url=f"https://www.coolapk.com/feed/{feed_id}",
            ai_summary=feed.aiSummary,
            comments=comments,
        )
