# TODO: 使用反代，允许国内直接下载推特视频媒体

from re import Match
from typing import ClassVar

from msgspec import convert

from ...utils.format import format_num


from .model import TweetResult

from ...utils.http_utils import get_async_client

from ..base import (
    BaseParser,
    PlatformEnum,
    handle,
    Platform,
    ParseResult,
    ParseException,
    MediaContent,
)


class XParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.X, display_name="X")

    def collect_data(self, tweet: TweetResult, is_repost: bool = False) -> ParseResult:
        result = tweet.result
        legacy = result.legacy

        content: list[MediaContent | str] = [legacy.text]
        content.extend(legacy.medias)

        user = result.core.user_results.result.legacy

        repost = None
        if not is_repost and result.quoted_status_result:
            repost = self.collect_data(result.quoted_status_result, True)

        return self.result(
            content=content,
            timestamp=legacy.time_local,
            author=self.create_author(
                name=f"{user.name} @{user.screen_name}",
                avatar_url=user.avatar_url,
                description=user.description,
                id=user.screen_name,
            ),
            stats=self.create_stats(
                view_count=format_num(int(result.views.count)),
                like_count=format_num(legacy.favorite_count),
                comment_count=format_num(legacy.reply_count),
                collect_count=format_num(legacy.bookmark_count),
            ),
            url=f"https://x.com/{user.screen_name}/status/{result.rest_id}",
            repost=repost,
        )

    @handle("twitter.com", r"twitter.com/[0-9-a-zA-Z_]{1,20}/status/([0-9]+)")
    @handle("x.com", r"x.com/[0-9-a-zA-Z_]{1,20}/status/([0-9]+)")
    async def _parse(self, searched: Match[str]) -> ParseResult:
        tweet_id = searched[1]

        async with get_async_client() as client:
            response = await client.post(
                "https://easycomment.ai/api/twitter/v1/free/get-tweet-detail",
                json={"pid": tweet_id},
            )
            response.raise_for_status()
            res = response.json()

        if res["code"] != 100000:
            raise ParseException(res["message"])

        tweet_raw = res["data"]["data"]["threaded_conversation_with_injections_v2"][
            "instructions"
        ][1]["entries"][0]["content"]["itemContent"]["tweet_results"]

        tweet = convert(tweet_raw, TweetResult)
        return self.collect_data(tweet)
