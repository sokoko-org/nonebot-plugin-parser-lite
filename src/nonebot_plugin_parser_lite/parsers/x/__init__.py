from re import Match
from typing import ClassVar

from msgspec import convert

from ...utils.format import format_num


from .model import TweetResult


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
        repost_status = result.quoted_status_result or result.retweeted_status_result
        if not is_repost and repost_status:
            repost = self.collect_data(repost_status, True)

        return self.result(
            content=content,
            timestamp=legacy.time_local,
            author=self.create_author(
                name=user.name,
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

        response = await self.httpx.post(
            "https://easycomment.ai/api/twitter/v1/free/get-tweet-detail",
            json={"tweet_id": tweet_id},
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
