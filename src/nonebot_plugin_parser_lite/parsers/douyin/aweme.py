from msgspec import Struct, field
import ujson

from ...creator import ContentItem, Creator


class Addr(Struct):
    uri: str

    @property
    def url(self) -> str:
        return f"https://aweme.snssdk.com/aweme/v1/play/?video_id={self.uri}&ratio=1080p&line=0"


class Statistics(Struct):
    comment_count: int = 0
    """评论数"""
    digg_count: int = 0
    """点赞数"""
    share_count: int = 0
    """分享数"""
    collect_count: int = 0
    """收藏数"""


class UrlList(Struct):
    url_list: list[str]


class Author(Struct):
    uid: str
    nickname: str
    avatar_thumb: UrlList
    """头像"""
    signature: str | None = None


class Video(Struct):
    cover: UrlList
    duration: int
    """视频时长(/1000)"""
    play_addr: Addr
    cover_original_scale: UrlList | None = None

    @property
    def url(self) -> str:
        return self.play_addr.url


class Image(Struct):
    url_list: list[str]
    uri: str = field(default="")
    clip_type: int | None = field(default=None)
    """=2 or None 是普通图片"""
    video: Video | None = field(default=None)
    """Live Photo 视频"""


class MusicPlayUrl(Struct):
    uri: str


class Music(Struct):
    duration: int
    mid: str
    play_url: MusicPlayUrl
    extra: str
    is_original_sound: bool


class ShareInfo(Struct):
    share_desc: str
    share_desc_info: str

    @property
    def text(self) -> str:
        return self.share_desc_info.replace(f"#{self.share_desc}#", "", 1)


class Aweme(Struct):
    aweme_id: str
    author: Author
    share_info: ShareInfo
    statistics: Statistics
    create_time: int
    share_url: str
    region: str
    is_slides: bool = field(default=False)
    images: list[Image] | None = field(default=None)
    music: Music | None = field(default=None)
    video: Video | None = field(default=None)

    @property
    def content(self) -> list[ContentItem]:
        content: list[ContentItem] = [self.share_info.text]
        aweme_cache_key = f"douyin:{self.aweme_id}"
        music_url: str | None = None
        if music := self.music:
            if not music.is_original_sound:
                if music.play_url.uri == "":
                    extra = ujson.loads(music.extra)
                    music_url = extra.get("original_song_url")
                else:
                    music_url = music.play_url.uri
                if music_url:
                    content.append(
                        Creator.audio(
                            url_or_task=music_url,
                            duration=music.duration,
                            cache_key=f"douyin:{music.mid}",
                            ext_headers={"Referer": "https://www.douyin.com/"},
                        )
                    )
        if self.images:
            for image in self.images:
                image_cache_key = (
                    f"{aweme_cache_key}:{image.uri}" if image.uri else None
                )
                if image.clip_type == 2 or image.clip_type is None:
                    content.append(
                        Creator.image(
                            url=image.url_list[-1],
                            cache_key=image_cache_key,
                            ext_headers={"Referer": "https://www.douyin.com/"},
                        )
                    )
                elif image_video := image.video:
                    content.append(
                        Creator.live_photo(
                            video_url=image_video.play_addr.url,
                            image_url=image_video.cover.url_list[-1],
                            bgm_url=music_url,
                            cache_key=image_cache_key,
                            ext_headers={"Referer": "https://www.douyin.com/"},
                            loop=3,
                        )
                    )
        elif video := self.video:
            content.append(
                Creator.video(
                    url_or_task=video.play_addr.url,
                    cover_url=video.cover_original_scale.url_list[-1]
                    if video.cover_original_scale
                    else video.cover.url_list[-1],
                    duration=video.duration // 1000,
                    cache_key=aweme_cache_key,
                    ext_headers={"Referer": "https://www.douyin.com/"},
                )
            )
        return content

    @property
    def stats(self) -> Statistics:
        return self.statistics


class Response(Struct):
    aweme_detail: Aweme
