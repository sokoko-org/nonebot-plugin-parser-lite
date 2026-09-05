from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, TypedDict

from anyio import Path

from .constants import STICKER_CDN, PlatformEnum
from .download import DOWNLOADER
from .download.task import DownloadTaskWrapper
from .utils.cache import CacheManager
from .utils.ffmpeg import FFmpeg


def repr_path_task(path_task: DownloadTaskWrapper[Path]) -> str:
    return f"url={path_task.url!r}"


@dataclass(repr=False, slots=True)
class MediaContent:
    path_task: DownloadTaskWrapper[Path]
    need_send: bool = field(default=True, init=False)
    """是否发送"""

    # 以字节为单位的文件大小缓存
    _size_bytes: int | None = field(default=None, init=False, repr=False)

    async def get_path(self) -> Path:
        """
        获取媒体文件路径

        :raise ZeroSizeException:  文件大小为零
        :raise SizeLimitException: 文件大小超过限制
        """
        return await self.path_task

    @staticmethod
    def _format_size(size_bytes: int | None) -> str:
        """将字节大小格式化为可读字符串（KB / MB / GB）"""
        if not size_bytes or size_bytes <= 0:
            return "未知大小"

        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        idx = 0
        while size >= 1024 and idx < len(units) - 1:
            size /= 1024.0
            idx += 1
        # 保留 2 位小数
        return f"{size:.2f}{units[idx]}"

    async def get_display_size(self) -> str:
        """获取媒体文件大小"""
        if self._size_bytes is None:
            try:
                self._size_bytes = await DOWNLOADER.head_size(
                    url=self.path_task.url,
                    ext_headers=self.path_task.ext_headers,
                    use_curl_cffi=self.path_task.use_curl_cffi,
                )
            except Exception:
                # HEAD 失败时不抛出，避免影响主流程
                self._size_bytes = None

        return self._format_size(self._size_bytes)

    def __repr__(self) -> str:
        prefix = self.__class__.__name__
        return f"{prefix}({repr_path_task(self.path_task)})"


@dataclass(repr=False, slots=True)
class AudioContent(MediaContent):
    """音频内容"""

    duration: float = 0.0

    @property
    def display_duration(self) -> str:
        try:
            total_seconds = int(self.duration)
            if total_seconds <= 0:
                return "0:00"

            minutes, seconds = divmod(total_seconds, 60)
            if minutes < 60:
                return f"{minutes}:{seconds:02d}"

            hours, minutes = divmod(minutes, 60)
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        except (TypeError, ValueError):
            return "NaN"


@dataclass(repr=False, slots=True)
class VideoContent(MediaContent):
    """视频内容"""

    cover: DownloadTaskWrapper[Path] | None = None
    """视频封面"""
    duration: float = 0.0
    """时长 单位: 秒"""

    async def get_cover_path(self) -> Path | None:
        return None if self.cover is None else await self.cover

    @property
    def display_duration(self) -> str:
        try:
            total_seconds = int(self.duration)
            if total_seconds <= 0:
                return "0:00"

            minutes, seconds = divmod(total_seconds, 60)
            if minutes < 60:
                return f"{minutes}:{seconds:02d}"

            hours, minutes = divmod(minutes, 60)
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        except (TypeError, ValueError):
            return "NaN"


@dataclass(repr=False, slots=True)
class ImageContent(MediaContent):
    """图片内容"""

    pass


@dataclass(repr=False, slots=True)
class GraphicContent(MediaContent):
    """图片，此图片不参与九宫格"""

    alt: str | None = None
    """图片描述 渲染时居中显示"""


@dataclass(repr=False, slots=True)
class StickerContent(MediaContent):
    """贴纸内容"""

    size: Literal["small", "medium"] = "medium"
    """贴纸大小
            - small: 比文字大一点
            - medium: 文字大小的两倍大一点
    """
    desc: str | None = None
    """贴纸描述"""


@dataclass(repr=False, slots=True)
class LivePhotoContent(MediaContent):
    """iPhone Live Photo 内容"""

    base_image: DownloadTaskWrapper[Path]
    """iPhone Live Photo 底图"""
    loop: int
    """循环次数"""
    bgm: DownloadTaskWrapper[Path] | None = None
    """iPhone Live Photo 背景音乐"""

    async def get_base(self) -> Path:
        """获取 iPhone Live Photo 底图"""
        return await self.base_image

    async def get_live(self) -> Path:
        """获取 iPhone Live Photo 视频"""

        bgm = await self.bgm if self.bgm else None
        return await FFmpeg.merge_to_live_mp4(
            image_path=await self.base_image,
            video_path=await self.path_task,
            bgm_path=bgm,
            loop=self.loop,
        )

    def __repr__(self) -> str:
        prefix = self.__class__.__name__
        return (
            f"{prefix}(video={self.path_task.url}, base_image={self.base_image.url}, "
            f"bgm={self.bgm.url if self.bgm else None})"
        )


@dataclass(slots=True)
class Platform:
    """平台信息"""

    name: PlatformEnum
    """ 平台名称 """
    display_name: str
    """ 平台显示名称 """

    async def get_logo_path(self) -> Path:
        return await DOWNLOADER.download_img(
            url=STICKER_CDN.format(platform="logo", name=self.name),
            cache_key=f"platform:{self.name}",
            cache_variant="logo",
            cache_type=CacheManager.LOGO,
        )


@dataclass(slots=True)
class Author:
    """作者信息"""

    name: str
    """作者名称"""
    id: str | None = None
    """作者id"""
    avatar: DownloadTaskWrapper[Path] | None = None
    """作者头像"""
    description: str | None = None
    """作者个性签名等"""
    location: str | None = None
    """位置信息"""

    async def get_avatar_path(self) -> Path | None:
        return None if self.avatar is None else await self.avatar


@dataclass(slots=True)
class Stats:
    """统计信息"""

    view_count: str | None = None
    """浏览数"""
    like_count: str | None = None
    """点赞数"""
    collect_count: str | None = None
    """收藏数"""
    share_count: str | None = None
    """分享数"""
    comment_count: str | None = None
    """评论数"""
    extra: dict[str, Any] = field(default_factory=dict)
    """额外信息, 比如弹幕数/硬币数"""


@dataclass(repr=False, slots=True)
class Comment:
    """评论信息"""

    author: Author
    """作者信息"""
    content: list[ContentItem]
    """评论内容，可以是文本或媒体对象"""
    timestamp: int | None
    """发布时间戳，单位秒"""
    stats: Stats = field(default_factory=Stats)
    """统计信息"""
    replies: list[Comment] = field(default_factory=list)
    """子评论列表"""
    parent_author: Author | None = None
    """父评论作者，用于渲染“回复 @xxx”，可选"""

    def add_reply(self, comment: "Comment", parent: Author | None = None):
        """添加子评论"""
        comment.parent_author = parent or self.author
        self.replies.append(comment)

    @property
    def formatted_datetime(self) -> str:
        """格式化时间戳"""
        if self.timestamp is None:
            return ""
        return datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")


@dataclass(repr=False, slots=True)
class LinkContent:
    """链接信息"""

    url: str
    """链接地址"""
    title: str
    """链接标题"""
    site_name: str | None = None
    """来源站点名称"""
    description: str | None = None
    """链接摘要"""
    icon: DownloadTaskWrapper[Path] | None = None
    """来源站点图标"""
    preview: DownloadTaskWrapper[Path] | None = None
    """链接预览图"""

    async def get_icon_path(self) -> Path | None:
        return None if self.icon is None else await self.icon

    async def get_preview_path(self) -> Path | None:
        return None if self.preview is None else await self.preview


@dataclass(repr=False, slots=True)
class QuoteContent:
    """引用内容"""

    text: str
    """引用正文"""
    title: str | None = None
    """引用来源标题"""
    url: str | None = None
    """引用来源链接"""
    icon: DownloadTaskWrapper[Path] | None = None
    """引用来源图标或头像"""

    async def get_icon_path(self) -> Path | None:
        return None if self.icon is None else await self.icon


@dataclass(slots=True)
class PollOption:
    """投票选项"""

    text: str
    """选项文本"""
    votes: int = 0
    """选项票数"""


@dataclass(slots=True)
class PollContent:
    """平台无关的投票内容"""

    options: list[PollOption]
    """投票选项"""
    title: str | None = None
    """投票标题"""
    total_votes: int | None = None
    """平台返回的总票数，多选时可能大于投票人数"""
    total_voters: int | None = None
    """投票人数"""
    multiple: bool = False
    """是否允许多选"""
    closed: bool = False
    """投票是否已结束"""
    close_at: str | None = None
    """投票结束时间，由平台保留原始表示"""

    @property
    def option_vote_total(self) -> int:
        """选项票数之和，用作各选项占比的分母"""
        return sum(max(option.votes, 0) for option in self.options)

    def option_percentage(
        self, option: PollOption, option_vote_total: int | None = None
    ) -> float:
        total = (
            self.option_vote_total if option_vote_total is None else option_vote_total
        )
        return max(option.votes, 0) / total * 100 if total else 0.0


@dataclass(repr=False, slots=True)
class ParseResult:
    """完整的解析结果"""

    platform: Platform
    """平台信息"""
    author: Author
    """作者信息"""
    url: str
    """来源链接"""
    content: list[ContentItem]
    """资源/文本内容"""
    title: str | None = field(default=None)
    """标题"""
    timestamp: int | None = field(default=None)
    """发布时间戳, 秒"""
    stats: Stats = field(default_factory=Stats)
    """统计信息"""
    comments: list[Comment] = field(default_factory=list)
    """评论列表"""
    ai_summary: str | None = field(default=None)
    """AI摘要"""
    embed_url: str | None = field(default=None)
    """嵌入播放链接"""
    extra: dict[str, Any] = field(default_factory=dict)
    """额外信息"""
    repost: ParseResult | None = field(default=None)
    """转发的内容"""
    render_image: Path | None = field(default=None)
    """渲染图片"""

    @property
    def display_url(self) -> str:
        return f"链接: {self.url}"

    @property
    def repost_display_url(self) -> str | None:
        return f"引帖: {self.repost.url}" if self.repost else None

    async def get_cover_path(self) -> Path | None:
        """获取封面路径"""
        # 先检查视频内容
        for cont in self.content:
            if isinstance(cont, VideoContent):
                return await cont.get_cover_path()
            elif isinstance(cont, (ImageContent, GraphicContent)):
                return await cont.get_path()
        return None

    @property
    def formatted_datetime(self) -> str:
        """格式化时间戳"""
        if self.timestamp is None:
            return ""
        return datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")

    def __repr__(self) -> str:
        return (
            f"platform: {self.platform.display_name}, "
            f"timestamp: {self.timestamp}, "
            f"title: {self.title}, "
            f"url: {self.url}, "
            f"author: {self.author}, "
            f"content: {self.content}, "
            f"stats: {self.stats}, "
            f"comments_len: {len(self.comments)}, "
            f"extra: {self.extra}, "
            f"repost: {self.repost}, "
            f"render_image: {self.render_image.name if self.render_image else 'None'}"
        )


class ParseResultKwargs(TypedDict, total=False):
    title: str | None
    """标题"""
    timestamp: int | None
    """发布时间戳, 秒"""
    extra: dict[str, Any]
    """额外信息"""
    repost: ParseResult | None
    """转发的内容"""
    stats: Stats
    """统计信息"""
    comments: list[Comment]
    """评论列表"""
    ai_summary: str | None
    """AI摘要"""
    embed_url: str | None
    """嵌入播放链接"""


ContentItem = (
    LinkContent
    | QuoteContent
    | PollContent
    | LivePhotoContent
    | StickerContent
    | GraphicContent
    | ImageContent
    | VideoContent
    | AudioContent
    | str
)
