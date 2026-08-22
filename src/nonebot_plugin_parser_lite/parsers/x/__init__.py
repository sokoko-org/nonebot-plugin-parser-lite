from typing import Any, ClassVar

from msgspec import convert

from ...data import Comment
from ...utils.format import format_num
from ..base import (
    DOWNLOADER,
    BaseParser,
    ContentItem,
    MatchWithParams,
    ParseException,
    ParseResult,
    Platform,
    PlatformEnum,
    handle,
)
from .model import Tweet, TweetCard, TweetEntry
from .util import parse_link_card


def _get_tweet_result(item: dict) -> dict | None:
    item_content = item.get("itemContent")
    if not isinstance(item_content, dict):
        return None
    if item_content.get("__typename") != "TimelineTweet":
        return None

    tweet_results = item_content.get("tweet_results") or {}
    result = tweet_results.get("result") or {}
    if result.get("__typename") not in {"Tweet", "TweetWithVisibilityResults"}:
        return None
    return tweet_results


def _iter_timeline_tweet_results(node: dict):
    """提取 TimelineItem 和 TimelineModule.items 中的 Tweet。"""
    if tweet_result := _get_tweet_result(node):
        yield tweet_result
        return

    content = node.get("content")
    if isinstance(content, dict):
        yield from _iter_timeline_tweet_results(content)

    for item in node.get("items", []):
        if isinstance(item, dict):
            yield from _iter_timeline_tweet_results(item)

    item = node.get("item")
    if isinstance(item, dict):
        yield from _iter_timeline_tweet_results(item)


def _get_rest_id(result: dict) -> str | None:
    """兼容 Tweet / TweetWithVisibilityResults，取出真实 tweet 的 rest_id."""
    typename = result.get("__typename")
    if typename == "Tweet":
        return result.get("rest_id")
    if typename == "TweetWithVisibilityResults":
        inner = result.get("tweet") or {}
        return inner.get("rest_id")
    return None


def _get_tweet_legacy(result: dict) -> dict[str, Any]:
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = result.get("tweet") or {}
    return result.get("legacy") or {}


class XParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.X, display_name="X")

    def __init__(self):
        super().__init__()
        self.headers.update(
            {"Host": "easycomment.ai", "Content-Type": "application/json"}
        )

    def _get_link_card(self, card: TweetCard | None) -> ContentItem | None:
        """将 X 的 unified_card 或传统 binding_values 转换为链接卡片"""
        if link_card := parse_link_card(card):
            return self.create_link(
                url=link_card.url,
                title=link_card.title,
                site_name=link_card.site_name,
                description=link_card.description,
                preview_url=link_card.preview_url,
                cache_key=f"x:link:{link_card.url}",
            )
        return None

    def _build_content(self, tweet: Tweet) -> list[ContentItem]:
        content: list[ContentItem] = [tweet.text]
        content.extend(tweet.legacy.medias)
        if article_cover := tweet.article_cover_url:
            content.append(
                self.create_image(
                    url=article_cover,
                    cache_key=f"x:article-cover:{tweet.rest_id}",
                )
            )
        if link_card := self._get_link_card(tweet.card):
            content.append(link_card)
        return content

    def _build_comment(self, raw: TweetEntry):
        tweet = raw.result.as_tweet
        user = tweet.core.user_results.result
        legacy = tweet.legacy
        return self.create_comment(
            author=self.create_author(
                name=user.core.name,
                avatar_url=user.avatar_url,
                description=user.legacy.description,
                id=user.core.screen_name,
            ),
            content=self._build_content(tweet),
            timestamp=legacy.time_local,
            stats=self.create_stats(
                like_count=format_num(legacy.favorite_count),
                comment_count=format_num(legacy.reply_count),
            ),
        )

    def _build_comments(
        self,
        root_id: str,
        tweet_map: dict[str, dict],
    ) -> list[Comment]:
        comments: dict[str, Comment] = {}
        parents: dict[str, str] = {}
        for rest_id, tweet_results in tweet_map.items():
            if rest_id == root_id:
                continue
            result = tweet_results.get("result") or {}
            parent_id: str | None = _get_tweet_legacy(result).get(
                "in_reply_to_status_id_str"
            )
            if not parent_id:
                continue
            comments[rest_id] = self._build_comment(convert(tweet_results, TweetEntry))
            parents[rest_id] = parent_id

        roots: list[Comment] = []
        for rest_id, comment in comments.items():
            parent_id = parents[rest_id]
            parent = comments.get(parent_id)
            if parent is not None:
                parent.replies.append(comment)
            elif parent_id == root_id:
                roots.append(comment)
        return roots

    def collect_data(self, raw: TweetEntry, is_repost: bool = False) -> ParseResult:
        tweet = raw.result.as_tweet
        legacy = tweet.legacy

        content = self._build_content(tweet)

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

    @handle("twitter.com", r"twitter.com/[0-9-a-zA-Z_]{1,20}/status/([0-9]+)")
    @handle("x.com", r"x.com/[0-9-a-zA-Z_]{1,20}/status/([0-9]+)")
    async def _parse(self, searched: MatchWithParams) -> ParseResult:
        tweet_id = searched[1]

        response = await DOWNLOADER.client.post(
            "https://easycomment.ai/api/twitter/v1/free/get-tweet-detail",
            json={"pid": tweet_id},
            headers=self.headers,
            use_curl_cffi=True,
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
            for tweet_results in _iter_timeline_tweet_results(entry):
                result = tweet_results.get("result") or {}
                rest_id = _get_rest_id(result)
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
        result = self.collect_data(tweet)
        result.comments = self._build_comments(tweet_id, tweet_map)
        return result
