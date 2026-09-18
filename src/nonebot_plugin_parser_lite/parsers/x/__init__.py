from time import monotonic
from typing import Any, ClassVar, Final
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
    "nZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
FEATURES: Final[str] = (
    '{"creator_subscriptions_tweet_preview_api_enabled":true,"premium_content_api_read_enabled":false,'
    '"communities_web_enable_tweet_community_results_fetch":true,"c9s_tweet_anatomy_moderator_badge_enabled":true,'
    '"responsive_web_grok_analyze_button_fetch_trends_enabled":false,"responsive_web_grok_analyze_post_followups_enabled":true,'
    '"rweb_cashtags_composer_attachment_enabled":true,"responsive_web_jetfuel_frame":true,"rweb_sports_post_context_enabled":true,'
    '"responsive_web_grok_share_attachment_enabled":true,"responsive_web_grok_annotations_enabled":true,"articles_preview_enabled":true,'
    '"responsive_web_edit_tweet_api_enabled":true,"rweb_conversational_replies_downvote_enabled":false,'
    '"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,'
    '"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":true,'
    '"content_disclosure_indicator_enabled":true,"content_disclosure_ai_generated_indicator_enabled":true,'
    '"responsive_web_grok_show_grok_translated_post":true,"responsive_web_grok_analysis_button_from_backend":true,'
    '"post_ctas_fetch_enabled":false,"rweb_cashtags_enabled":true,"freedom_of_speech_not_reach_fetch_enabled":true,'
    '"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,'
    '"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":false,'
    '"profile_label_improvements_pcf_label_in_post_enabled":true,"responsive_web_profile_redirect_enabled":true,'
    '"rweb_tipjar_consumption_enabled":false,"verified_phone_label_enabled":false,"responsive_web_nested_quote_preview_enabled":false,'
    '"responsive_web_grok_image_annotation_enabled":true,"responsive_web_grok_imagine_annotation_enabled":true,'
    '"responsive_web_grok_community_note_auto_translation_is_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true}'
)
FIELD_TOGGLES: Final[str] = (
    '{"withArticleRichContentState":true,"withArticlePlainText":false,"withArticleSummaryText":true,"withArticleVoiceOver":true}'
)


class XParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.X, display_name="X")
    guest_token_ttl: ClassVar[float] = 2 * 60 * 60

    def __init__(self):
        super().__init__()
        self.guestToken = None
        self.guestTokenCreatedAt = 0.0
        self.httpx.headers.update(
            {
                "Authorization": V2_BEARER,
            }
        )
        if ck := pconfig.x_ck:
            self.cookies = ck2dict(ck)
        else:
            self.cookies = None

    async def ensure_guest_token(self) -> str:
        """Return a guest token and refresh it after its two-hour TTL."""
        now = monotonic()
        if (
            self.guestToken is None
            or now - self.guestTokenCreatedAt >= self.guest_token_ttl
        ):
            r = await self.httpx.post(
                "https://api.x.com/1.1/guest/activate.json",
            )
            try:
                r.raise_for_status()
                guest_token = ujson.loads(r.content).get("guest_token")
                if not isinstance(guest_token, str) or not guest_token:
                    raise ValueError("guest_token missing")
                self.guestToken = guest_token
                self.guestTokenCreatedAt = monotonic()
            except Exception as e:
                raise ParseException(r.text) from e
        return self.guestToken

    async def getAuthHeaders(self) -> dict[str, Any]:
        csrf_token = (self.cookies or {}).get("ct0") or uuid.uuid4().hex
        headers = {
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "zh-cn",
            "x-csrf-token": csrf_token,
        }
        if self.cookies and self.cookies.get("auth_token"):
            headers["Cookie"] = (
                f"auth_token={self.cookies['auth_token']}; ct0={csrf_token};"
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
        if tweet.legacy.lang and tweet.legacy.lang != "zh":
            translation = tweet.grok_translated_post_with_availability
            if translation.is_available and translation.data:
                content.append(
                    self.create_quote(
                        text=translation.data.translation,
                        title=f"由 Grok 翻译自 {tweet.legacy.lang}",
                    )
                )
            elif tweet.is_translatable and self.cookies:
                try:
                    response = await self.httpx.post(
                        "https://api.x.com/2/grok/translation.json",
                        headers=await self.getAuthHeaders(),
                        json={
                            "content_type": "POST",
                            "id": tweet.rest_id,
                            "dst_lang": "zh",
                        },
                    )
                    response.raise_for_status()
                    try:
                        translated_text = response.json()["result"]["text"]
                        if not isinstance(translated_text, str) or not translated_text:
                            raise ValueError("translation text missing")
                        content.append(
                            self.create_quote(
                                text=translated_text,
                                title=f"由 Grok 翻译自 {tweet.legacy.lang}",
                            )
                        )
                    except Exception:
                        logger.exception(f"翻译解析失败: {response.text}")
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
        try:
            res = response.json()
        except Exception as e:
            raise ParseException("X API 返回了无效 JSON") from e
        if not isinstance(res, dict):
            raise ParseException("X API 返回了无效 JSON 对象")

        tweet_result = (res.get("data") or {}).get("tweetResult") or {}
        if not tweet_result:
            raise ParseException(f"tweetResult not found: {tweet_result}")
        try:
            tweet = convert(tweet_result, TweetEntry)
        except Exception as e:
            logger.exception(f"fail to parse entry: {tweet_result}")
            raise ParseException("fail to parse entry") from e
        return await self.collect_data(tweet)
