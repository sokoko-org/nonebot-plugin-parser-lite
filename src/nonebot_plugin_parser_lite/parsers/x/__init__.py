from typing import Any, ClassVar
import uuid

from msgspec import convert
from nonebot import logger
import ujson

from ...utils.cookie import ck2dict
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
    pconfig,
)
from .model import Tweet, TweetCard, TweetEntry
from .util import parse_link_card

V2_BEARER = (
    "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8x"
    "nZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
FEATURES = ujson.dumps(
    {
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "premium_content_api_read_enabled": False,
        "communities_web_enable_tweet_community_results_fetch": True,
        "c9s_tweet_anatomy_moderator_badge_enabled": True,
        "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
        "responsive_web_grok_analyze_post_followups_enabled": True,
        "rweb_cashtags_composer_attachment_enabled": True,
        "responsive_web_jetfuel_frame": True,
        "rweb_sports_post_context_enabled": True,
        "responsive_web_grok_share_attachment_enabled": True,
        "responsive_web_grok_annotations_enabled": True,
        "articles_preview_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "rweb_conversational_replies_downvote_enabled": False,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "content_disclosure_indicator_enabled": True,
        "content_disclosure_ai_generated_indicator_enabled": True,
        "responsive_web_grok_show_grok_translated_post": True,
        "responsive_web_grok_analysis_button_from_backend": True,
        "post_ctas_fetch_enabled": False,
        "rweb_cashtags_enabled": True,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": False,
        "profile_label_improvements_pcf_label_in_post_enabled": True,
        "responsive_web_profile_redirect_enabled": True,
        "rweb_tipjar_consumption_enabled": False,
        "verified_phone_label_enabled": False,
        "responsive_web_nested_quote_preview_enabled": False,
        "responsive_web_grok_image_annotation_enabled": True,
        "responsive_web_grok_imagine_annotation_enabled": True,
        "responsive_web_grok_community_note_auto_translation_is_enabled": True,
        "responsive_web_graphql_timeline_navigation_enabled": True,
    }
)
FIELD_TOGGLES = ujson.dumps(
    {
        "withArticleRichContentState": True,
        "withArticlePlainText": False,
        "withArticleSummaryText": True,
        "withArticleVoiceOver": True,
    }
)


class XParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.X, display_name="X")

    guestToken: Any | None = None
    guestTokenUses: int = 0
    cookies: dict | None = None

    def __init__(self):
        super().__init__()
        self.httpx.headers.update(
            {
                "Authorization": V2_BEARER,
            }
        )
        if ck := pconfig.x_ck:
            self.cookies = ck2dict(ck)

    async def ensure_guest_token(self) -> Any:
        if self.guestToken is None:
            r = await self.httpx.post(
                "https://api.x.com/1.1/guest/activate.json",
            )
            try:
                r.raise_for_status()
                self.guestToken = ujson.loads(r.content)["guest_token"]
            except Exception as e:
                raise ParseException(r.text) from e
            self.guestTokenUses = 0
        else:
            self.guestTokenUses += 1
            if self.guestTokenUses > 40:
                gtTemp = self.guestToken
                self.guestToken = None
                self.guestTokenUses = 0
                return gtTemp
        return self.guestToken

    async def getAuthHeaders(self) -> dict[str, Any]:
        csrfToken = str(uuid.uuid4()).replace("-", "")
        headers = {
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "zh-cn",
            "x-csrf-token": csrfToken,
        }
        if self.cookies:
            headers["Cookie"] = (
                f"auth_token={self.cookies['auth_token']}; ct0={csrfToken};"
            )
            headers["x-twitter-auth-type"] = "OAuth2Session"
        else:
            headers["x-guest-token"] = await self.ensure_guest_token()
        return headers

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
        content = tweet.content
        if link_card := self._get_link_card(tweet.card):
            content.append(link_card)
        return content

    async def collect_data(
        self, raw: TweetEntry, is_repost: bool = False
    ) -> ParseResult:
        tweet = raw.result.as_tweet
        legacy = tweet.legacy

        content = self._build_content(tweet)

        user = tweet.core.user_results.result

        repost = None
        repost_status = tweet.quoted_status_result or tweet.retweeted_status_result
        if not is_repost and repost_status:
            repost = await self.collect_data(repost_status, True)
        ai_summary = None
        if self.cookies:
            try:
                r = await self.httpx.post(
                    "https://api.x.com/2/grok/translation.json",
                    headers=await self.getAuthHeaders(),
                    json={
                        "content_type": "POST",
                        "id": tweet.rest_id,
                        "dst_lang": "zh",
                    },
                )
                r.raise_for_status()
                try:
                    ai_summary = r.json()["result"]["text"]
                except Exception:
                    logger.exception(f"翻译解析失败: {r.text}")
            except Exception:
                logger.exception("获取翻译失败")

        return self.result(
            content=content,
            title=tweet.title,
            timestamp=legacy.time_local,
            author=self.create_author(
                name=user.core.name,
                avatar_url=user.avatar_url,
                description=user.profile_bio.description,
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
            ai_summary=ai_summary,
        )

    @handle("twitter.com", r"twitter.com/[0-9-a-zA-Z_]{1,20}/status/([0-9]+)")
    @handle("x.com", r"x.com/[0-9-a-zA-Z_]{1,20}/status/([0-9]+)")
    async def _parse(self, searched: MatchWithParams) -> ParseResult:
        tweet_id = searched[1]

        response = await self.httpx.get(
            "https://x.com/i/api/graphql/Xl0tsHf4AzflMRjbw9e70A/TweetResultByRestId",
            params={
                "variables": ujson.dumps(
                    {
                        "tweetId": tweet_id,
                        "includePromotedContent": True,
                        "withBirdwatchNotes": True,
                        "withVoice": True,
                        "withCommunity": True,
                        "withV2Timeline": True,
                        "withQuickPromoteEligibilityTweetFields": True,
                    }
                ),
                "features": FEATURES,
                "fieldToggles": FIELD_TOGGLES,
            },
            headers=await self.getAuthHeaders(),
        )
        try:
            response.raise_for_status()
        except Exception as e:
            raise ParseException(response.text) from e
        res = response.json()

        tweet_result = (res.get("data") or {}).get("tweetResult") or {}
        if not tweet_result:
            raise ParseException(f"tweetResult not found: {tweet_result}")
        try:
            tweet = convert(tweet_result, TweetEntry)
        except Exception as e:
            logger.exception(f"fail to parse entry: {tweet_result}")
            raise ParseException("fail to parse entry") from e
        return await self.collect_data(tweet)
