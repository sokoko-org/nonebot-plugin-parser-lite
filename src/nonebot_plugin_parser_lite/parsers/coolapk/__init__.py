import re
from typing import ClassVar

from nonebot import logger

from ...utils.format import format_num
from ..base import (
    BaseParser,
    MatchWithParams,
    ParseException,
    ParseResult,
    Platform,
    PlatformEnum,
    handle,
)
from .feed import decoder as FeedDecoder
from .reply import decoder as ReplyDecoder

NEXT_DATA = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>\s*(.*?)\s*</script>',
    re.IGNORECASE | re.DOTALL,
)
# Ref https://github.com/ililaoban/nonebot-plugin-parser/blob/26e0631b9f13f4db8f3f33dd6d8bb7f803e688a2/src/nonebot_plugin_parser/parsers/coolapk.py


class CoolapkParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.COOLAPK, display_name="酷安"
    )

    @handle("coolapk1s.com/feed/", r"coolapk1s\.com/feed/(?P<feed_id>\d+)")
    @handle("www.coolapk.com/feed/", r"www\.coolapk\.com/feed/(?P<feed_id>\d+)")
    @handle("coolapk.com/feed/", r"coolapk\.com/feed/(?P<feed_id>\d+)")
    async def _parse(self, searched: MatchWithParams) -> ParseResult:
        feed_id = searched["feed_id"]
        response = await self.httpx.get(f"https://www.coolapk1s.com/feed/{feed_id}")
        response.raise_for_status()

        if matched := NEXT_DATA.search(response.text):
            next_data = FeedDecoder.decode(matched[1])
        else:
            raise ParseException(f"未找到酷安页面数据: {feed_id}")
        feed = next_data.props.pageProps

        comments = []
        try:
            response = await self.httpx.get(
                f"https://www.coolapk1s.com/reply/{feed_id}",
                headers={"referer": f"https://www.coolapk1s.com/feed/{feed_id}"},
            )
            response.raise_for_status()
            if matched := NEXT_DATA.search(response.text):
                reply_data = ReplyDecoder.decode(matched[1])
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
