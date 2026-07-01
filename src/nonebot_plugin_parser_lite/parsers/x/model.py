from __future__ import annotations

from datetime import datetime

from msgspec import Struct, field

from ...creator import Creator
from ...data import ContentItem


class Views(Struct):
    count: str
    """浏览数"""


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


class Tweet(Struct):
    core: TweetCore
    legacy: TweetLegacy
    """原始推文"""
    views: Views
    rest_id: str
    """推文id"""
    quoted_status_result: TweetEntry | None = None
    """被引用推文(转发时说话了)"""
    retweeted_status_result: TweetEntry | None = None
    """被转发推文(直接转发啥都没说,正文RT @开头)"""


class TweetData(Struct):
    """两种结构的兼容层"""

    tweet: Tweet | None = None
    # 兼容直接就是 Tweet 的情况：core 字段是否存在
    core: TweetCore | None = None
    legacy: TweetLegacy | None = None
    views: Views | None = None
    rest_id: str | None = None
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
            quoted_status_result=self.quoted_status_result,
            retweeted_status_result=self.retweeted_status_result,
        )


class TweetEntry(Struct):
    result: TweetData
