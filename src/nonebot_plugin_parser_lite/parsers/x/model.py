from __future__ import annotations

from datetime import datetime

from msgspec import Struct, field

from ...creator import Creator
from ...data import ContentItem


class Views(Struct):
    count: str
    """浏览数"""


class CardImage(Struct):
    url: str = ""


class CardValue(Struct):
    string_value: str | None = None
    image_value: CardImage | None = None


class CardBindingValue(Struct):
    key: str = ""
    value: CardValue = field(default_factory=CardValue)


class CardLegacy(Struct):
    name: str = ""
    url: str = ""
    binding_values: list[CardBindingValue] = field(default_factory=list)


class TweetCard(Struct):
    legacy: CardLegacy | None = None


class UnifiedText(Struct):
    content: str = ""


class UnifiedComponentData(Struct):
    id: str | None = None
    destination: str | None = None
    title: UnifiedText | None = None
    subtitle: UnifiedText | None = None
    description: str | UnifiedText | None = None
    summary: str | UnifiedText | None = None


class UnifiedComponent(Struct):
    type: str = ""
    data: UnifiedComponentData = field(default_factory=UnifiedComponentData)


class UnifiedUrlData(Struct):
    url: str = ""
    vanity: str | None = None


class UnifiedDestinationData(Struct):
    url_data: UnifiedUrlData | None = None


class UnifiedDestination(Struct):
    type: str = ""
    data: UnifiedDestinationData = field(default_factory=UnifiedDestinationData)


class UnifiedMediaEntity(Struct):
    media_url_https: str = ""


class UnifiedCard(Struct):
    # X unified_card JSON uses string component IDs (for example, "media_1").
    components: list[str] = field(default_factory=list)
    component_objects: dict[str, UnifiedComponent] = field(default_factory=dict)
    destination_objects: dict[str, UnifiedDestination] = field(default_factory=dict)
    media_entities: dict[str, UnifiedMediaEntity] = field(default_factory=dict)


class VideoVariant(Struct):
    content_type: str
    """视频编码类型，如 'video/mp4' 或 'application/x-mpegURL'"""
    url: str
    """视频地址"""
    bitrate: int | None = None
    """码率，部分非 mp4 可能没有"""


class VideoInfo(Struct):
    variants: list[VideoVariant]
    duration_millis: int = field(default=0)
    """视频时长(ms)"""


class Media(Struct):
    type: str
    """媒体类型，例如 'photo' / 'video' / 'animated_gif'"""
    media_url_https: str
    """图片 / 视频封面链接"""
    video_info: VideoInfo | None = None
    """视频信息，仅 type 为 video/animated_gif 时存在"""


class ExtendedEntities(Struct):
    media: list[Media] = field(default_factory=list)


class UserLegacy(Struct):
    description: str
    """用户简介"""
    followers_count: int
    """粉丝数"""
    profile_banner_url: str = field(default="")
    """banner图片"""


class UserCore(Struct):
    name: str
    """用户昵称"""
    screen_name: str
    """用户名"""
    created_at: str
    """注册时间"""


class UserAvatar(Struct):
    image_url: str = field(
        default="https://abs.twimg.com/sticky/default_profile_images/default_profile_normal.png"
    )


class TweetLegacy(Struct):
    bookmark_count: int
    """收藏数"""
    favorite_count: int
    """点赞数"""
    retweet_count: int
    """转推数"""
    quote_count: int
    """引用数"""
    reply_count: int
    """评论数"""
    full_text: str
    """推文内容"""
    created_at: str
    """utc时间戳字符串，例如'"Fri Feb 20 16:33:16 +0000 2026'"""
    display_text_range: tuple[int, int]
    """推文文本内容范围"""
    possibly_sensitive: bool = field(default=False)
    """是否敏感内容"""
    extended_entities: ExtendedEntities | None = None

    @property
    def medias(self) -> list[ContentItem]:
        """返回所有媒体的资源"""
        if not self.extended_entities or not self.extended_entities.media:
            return []

        medias: list[ContentItem] = []

        for media in self.extended_entities.media:
            # 图片：直接用 media_url_https
            if media.type == "photo":
                medias.append(Creator.image(url=f"{media.media_url_https}:orig"))
                continue

            # 视频 / 动图：挑最高码率 mp4
            elif media.video_info:
                candidates: list[tuple[int, str]] = []
                for v in media.video_info.variants:
                    if v.content_type != "video/mp4":
                        continue
                    if v.bitrate is None:
                        continue
                    candidates.append((v.bitrate, v.url))
                if candidates:
                    # 当前 media 选一个最高码率的
                    _, best = max(candidates, key=lambda x: x[0])
                    medias.append(
                        Creator.video(
                            url_or_task=best,
                            cover_url=media.media_url_https,
                            duration=media.video_info.duration_millis // 1000,
                        )
                    )

        return medias

    @property
    def text(self) -> str:
        """推文内容"""
        return self.full_text[self.display_text_range[0] : self.display_text_range[1]]

    @property
    def time_local(self) -> int:
        """创建时间的本地 Unix 时间戳（秒）"""
        dt_utc = datetime.strptime(self.created_at, "%a %b %d %H:%M:%S %z %Y")
        dt_local = dt_utc.astimezone()
        return int(dt_local.timestamp())


class UserData(Struct):
    legacy: UserLegacy
    is_blue_verified: bool
    """蓝标认证"""
    id: str
    """用户id"""
    rest_id: str
    """用户数字id"""
    core: UserCore
    avatar: UserAvatar = field(default_factory=UserAvatar)

    @property
    def avatar_url(self) -> str:
        """头像链接"""
        return self.avatar.image_url.replace("_normal", "_bigger")


class UserResult(Struct):
    result: UserData


class TweetCore(Struct):
    user_results: UserResult


class NoteTweetResult(Struct):
    text: str = ""


class NoteTweetResults(Struct):
    result: NoteTweetResult | None = None


class NoteTweet(Struct):
    note_tweet_results: NoteTweetResults | None = None


class ArticleMediaPreview(Struct):
    original_img_url: str = ""


class ArticleMediaVariant(Struct):
    content_type: str = ""
    url: str = ""
    bit_rate: int | None = None


class ArticleMediaInfo(Struct):
    original_img_url: str = ""
    preview_image: ArticleMediaPreview | None = None
    variants: list[ArticleMediaVariant] = field(default_factory=list)
    duration_millis: int = 0


class ArticleCoverMedia(Struct):
    media_info: ArticleMediaInfo | None = None


class TextEntityRange(Struct):
    key: int | str = 0
    length: int = 0
    offset: int = 0


class TextEntityMediaItem(Struct):
    mediaId: str | int = ""


class TextEntityData(Struct):
    mediaItems: list[TextEntityMediaItem] = field(default_factory=list)


class TextEntityValue(Struct):
    type: str = ""
    data: TextEntityData = field(default_factory=TextEntityData)


class TextEntityMap(Struct):
    key: str | int = ""
    value: TextEntityValue = field(default_factory=TextEntityValue)


class TextBlock(Struct):
    text: str = ""
    entityRanges: list[TextEntityRange] = field(default_factory=list)


class TextContentState(Struct):
    blocks: list[TextBlock] = field(default_factory=list)
    entityMap: list[TextEntityMap] | dict[str, TextEntityValue] = field(
        default_factory=list
    )


class ArticleMediaEntity(Struct):
    media_id: str | int = ""
    media_info: ArticleMediaInfo | None = None


class ArticleResult(Struct):
    title: str = ""
    preview_text: str = ""
    rest_id: str = ""
    cover_media: ArticleCoverMedia | None = None
    content_state: TextContentState | None = None
    media_entities: list[ArticleMediaEntity] = field(default_factory=list)


def _article_text(article: ArticleResult) -> str:
    content_state = article.content_state
    if content_state is None:
        return ""
    return "\n".join(block.text for block in content_state.blocks).strip()


def _article_entities(
    content_state: TextContentState,
) -> dict[str, TextEntityValue]:
    if isinstance(content_state.entityMap, dict):
        return {str(key): value for key, value in content_state.entityMap.items()}
    return {str(entity.key): entity.value for entity in content_state.entityMap}


def _article_media_entities_for_range(
    entity_range: TextEntityRange,
    entities: dict[str, TextEntityValue],
    media_by_id: dict[str, ArticleMediaEntity],
) -> list[ArticleMediaEntity]:
    entity = entities.get(str(entity_range.key))
    if entity is None or entity.type != "MEDIA":
        return []
    return [
        media_by_id[media_id]
        for item in entity.data.mediaItems
        if (media_id := str(item.mediaId)) in media_by_id
    ]


def _article_preview_url(media_info: ArticleMediaInfo) -> str | None:
    if media_info.preview_image and media_info.preview_image.original_img_url:
        return media_info.preview_image.original_img_url
    return media_info.original_img_url or None


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _utf16_offset_to_index(text: str, offset: int) -> int:
    """将 Draft.js 的 UTF-16 偏移量映射为 Python 字符串索引"""
    offset = max(offset, 0)
    code_units = 0
    for index, char in enumerate(text):
        if offset <= code_units:
            return index
        code_units += 2 if ord(char) > 0xFFFF else 1
    return len(text)


def _article_media_content(
    article: ArticleResult, media: ArticleMediaEntity
) -> ContentItem | None:
    media_info = media.media_info
    if media_info is None:
        return None

    variants = [
        variant
        for variant in media_info.variants
        if variant.content_type == "video/mp4" and variant.url
    ]
    cache_key = f"x:article-media:{article.rest_id}:{media.media_id}"
    if variants:
        video = max(variants, key=lambda variant: variant.bit_rate or 0)
        return Creator.video(
            url_or_task=video.url,
            cover_url=_article_preview_url(media_info),
            duration=media_info.duration_millis / 1000,
            cache_key=cache_key,
        )
    if image_url := media_info.original_img_url or _article_preview_url(media_info):
        return Creator.graphic(url=image_url, cache_key=cache_key)
    return None


def _article_content(article: ArticleResult) -> list[ContentItem]:
    content_state = article.content_state
    if content_state is None:
        return [article.preview_text] if article.preview_text else []

    entities = _article_entities(content_state)
    media_by_id = {
        str(media.media_id): media
        for media in article.media_entities
        if media.media_id != ""
    }
    content: list[ContentItem] = []
    text = ""

    def flush_text() -> None:
        nonlocal text
        if text:
            content.append(text)
        text = ""

    for index, block in enumerate(content_state.blocks):
        if index and text:
            text += "\n"

        cursor = 0
        utf16_length = _utf16_length(block.text)
        for entity_range in sorted(
            block.entityRanges, key=lambda entity_range: entity_range.offset
        ):
            media_content = [
                content_item
                for media in _article_media_entities_for_range(
                    entity_range, entities, media_by_id
                )
                if (content_item := _article_media_content(article, media)) is not None
            ]
            if not media_content:
                continue

            start = min(max(entity_range.offset, cursor), utf16_length)
            end = min(
                max(entity_range.offset + entity_range.length, start),
                utf16_length,
            )
            text += block.text[
                _utf16_offset_to_index(block.text, cursor) : _utf16_offset_to_index(
                    block.text, start
                )
            ]
            flush_text()
            content.extend(media_content)
            cursor = end

        text += block.text[_utf16_offset_to_index(block.text, cursor) :]

    flush_text()
    return content or ([article.preview_text] if article.preview_text else [])


class ArticleResults(Struct):
    result: ArticleResult | None = None


class Article(Struct):
    article_results: ArticleResults | None = None


class Tweet(Struct):
    core: TweetCore
    legacy: TweetLegacy
    """原始推文"""
    views: Views
    rest_id: str
    """推文id"""
    card: TweetCard | None = None
    """推文链接卡片"""
    note_tweet: NoteTweet | None = None
    """长文本推文结构"""
    article: Article | None = None
    """X Article 结构，按普通正文处理"""
    quoted_status_result: TweetEntry | None = None
    """被引用推文(转发时说话了)"""
    retweeted_status_result: TweetEntry | None = None
    """被转发推文(直接转发啥都没说,正文RT @开头)"""

    def _text(self) -> str:
        """完整正文，优先使用 note_tweet / Article 内容"""
        note_results = self.note_tweet.note_tweet_results if self.note_tweet else None
        note_result = note_results.result if note_results else None
        if note_result and note_result.text:
            return note_result.text

        if article_result := self._get_article_result():
            if (
                article_text := _article_text(article_result)
                or article_result.preview_text
            ):
                return (
                    f"{self.legacy.text}\n\n{article_text}"
                    if self.legacy.text
                    else article_text
                )

        return self.legacy.text

    @property
    def content(self) -> list[ContentItem]:
        content: list[ContentItem] = []
        if article_cover := self._get_article_cover_url():
            content.append(
                Creator.graphic(
                    url=article_cover,
                    cache_key=f"x:article-cover:{self.rest_id}",
                )
            )

        article_result = self._get_article_result()
        article_content = _article_content(article_result) if article_result else []
        if article_content:
            if legacy_text := self.legacy.text:
                content.append(legacy_text)
            content.extend(article_content)
        elif text := self._text():
            content.append(text)

        content.extend(self.legacy.medias)
        return content

    @property
    def title(self) -> str | None:
        article_result = self._get_article_result()
        return article_result.title if article_result and article_result.title else None

    def _get_article_result(self) -> ArticleResult | None:
        article_results = self.article.article_results if self.article else None
        return article_results.result if article_results else None

    def _get_article_cover_url(self) -> str | None:
        """Article 封面"""
        result = self._get_article_result()
        cover_media = result.cover_media if result else None
        media_info = cover_media.media_info if cover_media else None
        if media_info and media_info.original_img_url:
            return media_info.original_img_url
        return None


class TweetData(Struct):
    """两种结构的兼容层"""

    tweet: Tweet | None = None
    # 兼容直接就是 Tweet 的情况：core 字段是否存在
    core: TweetCore | None = None
    legacy: TweetLegacy | None = None
    views: Views | None = None
    rest_id: str | None = None
    card: TweetCard | None = None
    note_tweet: NoteTweet | None = None
    article: Article | None = None
    quoted_status_result: TweetEntry | None = None
    retweeted_status_result: TweetEntry | None = None

    @property
    def as_tweet(self) -> Tweet:
        if self.tweet:
            return self.tweet
        # 兼容直接是 Tweet 的情况
        assert self.core is not None, "TweetData.core is missing"
        assert self.legacy is not None, "TweetData.legacy is missing"
        assert self.views is not None, "TweetData.views is missing"
        assert self.rest_id is not None, "TweetData.rest_id is missing"
        return Tweet(
            core=self.core,
            legacy=self.legacy,
            views=self.views,
            rest_id=self.rest_id,
            card=self.card,
            note_tweet=self.note_tweet,
            article=self.article,
            quoted_status_result=self.quoted_status_result,
            retweeted_status_result=self.retweeted_status_result,
        )


class TweetEntry(Struct):
    result: TweetData
