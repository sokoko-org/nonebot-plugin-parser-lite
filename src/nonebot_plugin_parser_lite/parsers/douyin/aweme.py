from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from markdown import markdown as render_markdown
from msgspec import Struct, field
import ujson

from ...creator import ContentItem, Creator
from ...data import AudioContent, ImageContent, LivePhotoContent, VideoContent
from ...download import DOWNLOADER
from ...utils.format import append_html_text, iter_html


class Addr(Struct):
    uri: str
    url_list: list[str] = field(default_factory=list)

    @property
    def file_id(self) -> str | None:
        try:
            wrapped_url = self.url_list[-1]
            return parse_qs(urlparse(wrapped_url).query).get("file_id", [])[0]
        except Exception:
            return None

    @property
    def url(self) -> str:
        if file_id := self.file_id:
            return f"https://aweme.snssdk.com/aweme/v1/play/?video_id={self.uri}&file_id={file_id}"
        return f"https://aweme.snssdk.com/aweme/v1/play/?video_id={self.uri}"


DOUYIN_RETRYABLE_HTTP_STATUSES = frozenset({460})
"""抖音 CDN 会按出口位置拒绝访问（HTTP 460，Overseas traffic refused），可换线路重试"""


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

    def download(self, cache_key: str | None, *, cache_variant: str | None = None):
        return DOWNLOADER.download_video(
            url=self.play_addr.url_list[0],
            fallback_urls=self.play_addr.url_list[1:],
            retry_http_statuses=DOUYIN_RETRYABLE_HTTP_STATUSES,
            ext_headers={"Referer": "https://www.douyin.com/"},
            cache_key=cache_key,
            cache_variant=cache_variant,
        )

    def to_content(self, cache_key: str) -> VideoContent:
        return Creator.video(
            url_or_task=self.download(cache_key),
            cover_url=(self.cover_original_scale or self.cover).url_list[-1],
            duration=self.duration // 1000,
            cache_key=cache_key,
            ext_headers={"Referer": "https://www.douyin.com/"},
        )

    def to_live_photo(
        self, cache_key: str | None, bgm_url: str | None
    ) -> LivePhotoContent:
        return Creator.live_photo(
            video_url=self.download(cache_key, cache_variant="motion"),
            image_url=self.cover.url_list[-1],
            bgm_url=bgm_url,
            cache_key=cache_key,
            ext_headers={"Referer": "https://www.douyin.com/"},
            loop=3,
        )


class Image(Struct):
    url_list: list[str]
    uri: str = field(default="")
    clip_type: int | None = field(default=None)
    """=2 or None 是普通图片"""
    video: Video | None = field(default=None)
    """Live Photo 视频"""

    def to_content(
        self, aweme_id: str, bgm_url: str | None
    ) -> ImageContent | LivePhotoContent | None:
        cache_key = f"douyin:{aweme_id}:{self.uri}" if self.uri else None
        if self.clip_type in (None, 2):
            return Creator.image(
                url=self.url_list[-1],
                cache_key=cache_key,
                ext_headers={"Referer": "https://www.douyin.com/"},
            )
        return self.video.to_live_photo(cache_key, bgm_url) if self.video else None


class MusicPlayUrl(Struct):
    uri: str


class Music(Struct):
    duration: int
    mid: str
    play_url: MusicPlayUrl
    extra: str
    is_original_sound: bool

    @property
    def url(self) -> str | None:
        if self.is_original_sound:
            return None
        if self.play_url.uri:
            return self.play_url.uri
        return ujson.loads(self.extra).get("original_song_url")

    def to_content(self, url: str) -> AudioContent:
        return Creator.audio(
            url_or_task=url,
            duration=self.duration,
            cache_key=f"douyin:{self.mid}",
            ext_headers={"Referer": "https://www.douyin.com/"},
        )


class ShareInfo(Struct):
    share_desc: str
    share_desc_info: str

    @property
    def text(self) -> str:
        return self.share_desc_info.replace(f"#{self.share_desc}#", "", 1)


class ArticleInfo(Struct):
    article_id: str
    article_content: str
    article_title: str | None = None

    @property
    def content(self) -> list[ContentItem]:
        article = ujson.loads(self.article_content)
        markdown = article["markdown"]
        content: list[ContentItem] = []
        soup = BeautifulSoup(render_markdown(markdown), "html.parser")
        buffer: list[str] = []
        for element in iter_html(soup):
            if isinstance(element, str):
                buffer.append(element)
            else:
                append_html_text(content, buffer)
                buffer.clear()
                image_url = str(element["src"]).split(maxsplit=1)[0]
                content.append(
                    Creator.image(
                        url=image_url,
                        cache_key=(
                            f"douyin:{self.article_id}:{urlparse(image_url).path}"
                        ),
                        ext_headers={"Referer": "https://www.douyin.com/"},
                    )
                )
        append_html_text(content, buffer)
        return content


class Aweme(Struct):
    aweme_id: str
    author: Author
    share_info: ShareInfo
    statistics: Statistics
    create_time: int
    share_url: str
    region: str
    images: list[Image] | None = None
    music: Music | None = None
    video: Video | None = None
    article_info: ArticleInfo | None = None

    @property
    def title(self) -> str | None:
        return self.article_info.article_title if self.article_info else None

    @property
    def content(self) -> list[ContentItem]:
        if self.article_info:
            return self.article_info.content
        music_url = self.music.url if self.music else None
        return [
            self.share_info.text,
            *self._music_content(music_url),
            *self._visual_content(music_url),
        ]

    def _music_content(self, url: str | None) -> list[ContentItem]:
        return [] if not self.music or not url else [self.music.to_content(url)]

    def _visual_content(self, music_url: str | None) -> list[ContentItem]:
        if not self.images:
            return (
                [self.video.to_content(f"douyin:{self.aweme_id}")] if self.video else []
            )
        content: list[ContentItem] = []
        for image in self.images:
            if (item := image.to_content(self.aweme_id, music_url)) is not None:
                content.append(item)
        return content

    @property
    def stats(self) -> Statistics:
        return self.statistics


class Response(Struct):
    aweme_detail: Aweme
