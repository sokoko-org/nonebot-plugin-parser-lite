from datetime import datetime, timezone
import re

from msgspec import Struct, field

from ..data import MediaContent
from ..creator import create_image, create_video

_TCO_RE = re.compile(r"\s*https://t\.co/\w+")
_INVALID_CHARS_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")


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

    @property
    def orig_url(self):
        return f"{self.media_url_https}:orig"


class User(Struct):
    id_str: str
    """用户id"""
    name: str
    """用户昵称"""
    screen_name: str
    """用户名"""
    profile_image_url_https: str
    is_blue_verified: bool = False
    """是否蓝标认证"""
    verified: bool = False
    """是否官方认证"""

    @property
    def avatar_url(self):
        return self.profile_image_url_https.replace("_normal", "_bigger")


class Tweet(Struct):
    favorite_count: int
    """点心数"""
    id_str: str
    """推文id"""
    created_at: str
    mediaDetails: list[Media]
    user: User
    full_text: str = field(name="text")
    quoted_tweet: "Tweet | None" = None
    """引用推文"""

    def _parse_created_at(self) -> datetime:
        """解析 ISO 8601 UTC 时间，如 '2026-03-12T14:02:40.000Z' 或 '2026-03-12T14:02:40Z'."""
        s = self.created_at
        if s.endswith("Z"):
            s = s[:-1]

        # 先尝试带毫秒
        try:
            dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f")
        except ValueError:
            # 再尝试不带毫秒
            dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")

        return dt.replace(tzinfo=timezone.utc)

    @property
    def time_utc(self) -> int:
        """创建时间的 UTC Unix 时间戳（秒）"""
        dt = self._parse_created_at()
        return int(dt.timestamp())

    @property
    def time_local(self) -> int:
        """创建时间的本地 Unix 时间戳（秒）"""
        dt_utc = self._parse_created_at()
        dt_local = dt_utc.astimezone()
        return int(dt_local.timestamp())

    @property
    def text(self) -> str:
        """去掉 t.co 短链接和非法字符的推文内容"""
        text = _TCO_RE.sub("", self.full_text)
        text = _INVALID_CHARS_RE.sub("", text)
        return text

    @property
    def medias(self) -> list[MediaContent]:
        """返回所有媒体的资源"""
        if not self.mediaDetails:
            return []

        medias: list[MediaContent] = []

        for media in self.mediaDetails:
            # 图片：直接用 media_url_https
            if media.type == "photo":
                medias.append(create_image(url=media.orig_url))
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
                        create_video(url_or_task=best, cover_url=media.orig_url)
                    )

        return medias
