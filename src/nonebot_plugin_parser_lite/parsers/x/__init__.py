from re import Match
from typing import ClassVar

from httpx import AsyncClient
from msgspec import convert

from ...utils.format import format_num
from ..base import BaseParser, MediaContent, ParseResult, Platform, PlatformEnum, handle
from .model import Tweet


class XParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.X, display_name="X")

    def collect_data(self, tweet: Tweet, is_repost: bool = False) -> ParseResult:
        """从 Tweet 模型构造 ParseResult，可递归处理转推内容。"""
        contents: list[MediaContent | str] = [tweet.text, *tweet.medias]
        user = tweet.user

        repost: ParseResult | None = None
        if not is_repost and tweet.quoted_tweet:
            repost = self.collect_data(tweet.quoted_tweet, is_repost=True)

        return self.result(
            content=contents,
            timestamp=tweet.time_local,
            author=self.create_author(
                name=f"{user.name} @{user.screen_name}",
                avatar_url=user.avatar_url,
                id=user.screen_name,
            ),
            stats=self.create_stats(
                like_count=format_num(tweet.favorite_count),
            ),
            url=f"https://x.com/{user.screen_name}/status/{tweet.id_str}",
            repost=repost,
        )

    @handle("t.co", r"t.co/\w+")
    async def _parse_t_co(self, searched: Match[str]):
        url = f"https://{searched[0]}"
        return await self.parse_with_redirect(url, self.headers)

    @handle("twitter.com", r"twitter.com/[0-9-a-zA-Z_]{1,20}/status/([0-9]+)")
    @handle("x.com", r"x.com/[0-9-a-zA-Z_]{1,20}/status/([0-9]+)")
    async def _parse(self, searched: Match[str]) -> ParseResult:
        tweet_id = searched[1]
        token_num = int(tweet_id) / 1e15
        token = str(token_num * 3.141592653589793).replace("0", "").replace(".", "")

        async with AsyncClient(headers=self.headers) as client:
            resp = await client.get(
                "https://cdn.syndication.twimg.com/tweet-result",
                params={"id": tweet_id, "token": token},
            )
            resp.raise_for_status()
            data = resp.json()

        tweet = convert(data, Tweet)
        return self.collect_data(tweet)
