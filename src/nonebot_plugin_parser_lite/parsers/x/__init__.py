from typing import ClassVar

from curl_cffi import AsyncSession
from msgspec import convert

from ...utils.format import format_num
from ..base import (
    BaseParser,
    ContentItem,
    MatchWithParams,
    ParseException,
    ParseResult,
    Platform,
    PlatformEnum,
    handle,
)
from .model import TweetEntry


class XParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.X, display_name="X")

    def __init__(self):
        super().__init__()
        self.session = AsyncSession(impersonate="chrome146")
        self.headers.update(
            {"Host": "easycomment.ai", "Content-Type": "application/json"}
        )

    def collect_data(self, raw: TweetEntry, is_repost: bool = False) -> ParseResult:
        tweet = raw.result.as_tweet
        legacy = tweet.legacy

        content: list[ContentItem] = [legacy.text]
        content.extend(legacy.medias)

        user = tweet.core.user_results.result

        repost = None
        repost_status = tweet.quoted_status_result or tweet.retweeted_status_result
        if not is_repost and repost_status:
            repost = self.collect_data(repost_status, True)

        return self.result(
            content=content,
            timestamp=legacy.time_local,
            author=self.create_author(
                name=user.core.name,
                avatar_url=user.avatar_url,
                description=user.legacy.description,
                id=user.core.screen_name,
            ),
            stats=self.create_stats(
                view_count=format_num(int(tweet.views.count)),
                like_count=format_num(legacy.favorite_count),
                comment_count=format_num(legacy.reply_count),
                collect_count=format_num(legacy.bookmark_count),
                share_count=format_num(legacy.quote_count + legacy.retweet_count),
            ),
            url=f"https://x.com/{user.core.screen_name}/status/{tweet.rest_id}",
            repost=repost,
        )

    def _get_timeline_tweet_result(self, entry: dict) -> dict | None:
        """
        从单个 entry 中提取 tweet_results.result
        (Tweet 或 TweetWithVisibilityResults)
        """
        content = entry.get("content")
        if not isinstance(content, dict):
            return None

        if (
            content.get("__typename") != "TimelineTimelineItem"
            or content.get("itemContent", {}).get("__typename") != "TimelineTweet"
        ):
            return None

        tweet_results = content["itemContent"].get("tweet_results") or {}
        result = tweet_results.get("result") or {}
        typename = result.get("__typename")
        if typename not in {"Tweet", "TweetWithVisibilityResults"}:
            return None
        return tweet_results

    @staticmethod
    def _get_rest_id(result: dict) -> str | None:
        """兼容 Tweet / TweetWithVisibilityResults，取出真实 tweet 的 rest_id."""
        typename = result.get("__typename")
        if typename == "Tweet":
            return result.get("rest_id")
        if typename == "TweetWithVisibilityResults":
            inner = result.get("tweet") or {}
            return inner.get("rest_id")
        return None

    @handle("twitter.com", r"twitter.com/[0-9-a-zA-Z_]{1,20}/status/([0-9]+)")
    @handle("x.com", r"x.com/[0-9-a-zA-Z_]{1,20}/status/([0-9]+)")
    async def _parse(self, searched: MatchWithParams) -> ParseResult:
        tweet_id = searched[1]

        response = await self.session.post(
            "https://easycomment.ai/api/twitter/v1/free/get-tweet-detail",
            json={"pid": tweet_id},
            headers=self.headers,
        )
        try:
            response.raise_for_status()
        except Exception as e:
            raise ParseException(response.text) from e
        res = response.json()

        if res["code"] != 100000:
            raise ParseException(res)

        entries = next(
            (
                instruction["entries"]
                for instruction in res["data"]["data"][
                    "threaded_conversation_with_injections_v2"
                ]["instructions"]
                if instruction["type"] == "TimelineAddEntries"
            ),
            None,
        )
        if entries is None:
            raise ParseException("TimelineAddEntries not found")

        # 所有 Tweet 的索引：rest_id -> tweet_results
        tweet_map: dict[str, dict] = {}
        # 当前链接对应的那条 tweet
        root_entry: dict | None = None

        for entry in entries:
            tweet_results = self._get_timeline_tweet_result(entry)
            if not tweet_results:
                continue

            result = tweet_results.get("result") or {}
            rest_id = self._get_rest_id(result)
            if not rest_id:
                continue

            tweet_map[rest_id] = tweet_results
            if rest_id == tweet_id:
                root_entry = tweet_results

        if root_entry is None:
            raise ParseException(f"Tweet {tweet_id} not found")

        root_result = root_entry.get("result") or {}
        legacy = root_result.get("legacy") or {}

        # 填上“父推文”作为 quoted_status_result，便于后面 collect_data 统一处理
        if "quoted_status_result" not in root_result:
            in_reply_to_id = legacy.get("in_reply_to_status_id_str") or legacy.get(
                "conversation_id_str"
            )
            if in_reply_to_id and in_reply_to_id != tweet_id:
                parent_entry = tweet_map.get(in_reply_to_id)
                if parent_entry is not None:
                    root_result["quoted_status_result"] = parent_entry

        tweet = convert(root_entry, TweetEntry)
        return self.collect_data(tweet)
