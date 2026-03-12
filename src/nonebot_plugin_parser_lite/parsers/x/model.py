from datetime import datetime, timezone
import re

from msgspec import Struct

from ..data import MediaContent
from ..creator import create_image, create_video

_TCO_RE = re.compile(r"\s*https://t\.co/\w+")
_INVALID_CHARS_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")


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


class Media(Struct):
    type: str
    """媒体类型，例如 'photo' / 'video' / 'animated_gif'"""
    media_url_https: str
    """图片 / 视频封面链接"""
    video_info: VideoInfo | None = None
    """视频信息，仅 type 为 video/animated_gif 时存在"""


class ExtendedEntities(Struct):
    meida: list[Media]


class UserLegacy(Struct):
    created_at: str
    """注册时间"""
    description: str
    """用户简介"""
    name: str
    """用户昵称"""
    screen_name: str
    """用户名"""
    followers_count: int
    """粉丝数"""
    profile_image_url_https: str

    @property
    def avatar_url(self):
        return self.profile_image_url_https.replace("_normal", "_bigger")


class TweetLegacy(Struct):
    bookmark_count: int
    """收藏数"""
    favorite_count: int
    """点赞数"""
    retweet_count: int
    """转发数"""
    reply_count: int
    """评论数"""
    full_text: str
    """推文内容"""
    created_at: str
    """utc时间戳字符串，例如'"Fri Feb 20 16:33:16 +0000 2026'"""
    extended_entities: ExtendedEntities | None = None

    @property
    def medias(self) -> list[MediaContent]:
        """返回所有媒体的资源"""
        if not self.extended_entities or not self.extended_entities.meida:
            return []

        medias: list[MediaContent] = []

        for media in self.extended_entities.meida:
            # 图片：直接用 media_url_https
            if media.type == "photo":
                medias.append(create_image(url=media.media_url_https))
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
                        create_video(url_or_task=best, cover_url=media.media_url_https)
                    )

        return medias

    @property
    def text(self) -> str:
        """去掉 t.co 短链接和非法字符的推文内容"""
        text = _TCO_RE.sub("", self.full_text)
        text = _INVALID_CHARS_RE.sub("", text)
        return text

    @property
    def time_utc(self) -> int:
        """创建时间的 UTC Unix 时间戳（秒）"""
        # 示例格式: "Fri Feb 20 16:33:16 +0000 2026"
        dt = datetime.strptime(self.created_at, "%a %b %d %H:%M:%S %z %Y")
        # 标准 UTC 时间戳
        return int(dt.astimezone(timezone.utc).timestamp())

    @property
    def time_local(self) -> int:
        """创建时间的本地 Unix 时间戳（秒）"""
        dt_utc = datetime.strptime(self.created_at, "%a %b %d %H:%M:%S %z %Y")
        dt_local = dt_utc.astimezone()
        return int(dt_local.timestamp())


class UserData(Struct):
    legacy: UserLegacy


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
    quoted_status_result: "TweetResult | None" = None
    """引用推文"""


class TweetResult(Struct):
    result: Tweet
