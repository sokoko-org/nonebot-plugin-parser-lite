from typing import Any, Literal, TypedDict
from pathlib import Path
from datetime import datetime
from dataclasses import field, dataclass
from collections.abc import Sequence

from ..utils.ffmpeg import FFmpeg

from ..download.task import DownloadTaskWrapper


def repr_path_task(path_task: DownloadTaskWrapper[Path]) -> str:
    return f"url={path_task.url!r}"


@dataclass(repr=False, slots=True)
class MediaContent:
    path_task: DownloadTaskWrapper[Path]
    need_send: bool = field(default=True, init=False)
    """是否发送"""

    async def get_path(self) -> Path:
        return await self.path_task

    def __repr__(self) -> str:
        prefix = self.__class__.__name__
        return f"{prefix}({repr_path_task(self.path_task)})"


@dataclass(repr=False, slots=True)
class AudioContent(MediaContent):
    """音频内容"""

    duration: float = 0.0


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
    bgm: DownloadTaskWrapper[Path] | None = None
    """iPhone Live Photo 背景音乐"""

    async def get_base(self) -> Path:
        """获取 iPhone Live Photo 底图"""
        return await self.base_image

    async def get_live(self) -> Path:
        """获取 iPhone Live Photo 视频"""

        bgm = await self.bgm if self.bgm else None
        return await FFmpeg.merge_to_live_mp4(
            await self.base_image, await self.path_task, bgm
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

    name: str
    """ 平台名称 """
    display_name: str
    """ 平台显示名称 """


@dataclass(repr=False, slots=True)
class Author:
    """作者信息"""

    name: str
    """作者名称"""
    id: str | None = None
    """作者id"""
    avatar: DownloadTaskWrapper[Path] | None = None
    """作者头像 URL 或本地路径"""
    description: str | None = None
    """作者个性签名等"""

    async def get_avatar_path(self) -> Path | None:
        return None if self.avatar is None else await self.avatar


@dataclass(repr=False, slots=True)
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

    def __repr__(self) -> str:
        prefix = self.__class__.__name__
        return (
            f"{prefix}(view_count={self.view_count}, like_count={self.like_count}, "
            f"collect_count={self.collect_count}, share_count={self.share_count}, "
            f"comment_count={self.comment_count}, extra={self.extra})"
        )


@dataclass(repr=False, slots=True)
class Comment:
    """评论信息"""

    author: Author
    """作者信息"""
    content: Sequence[MediaContent | str | None]
    """评论内容，可以是文本或媒体对象"""
    timestamp: int | None
    """发布时间戳，单位秒"""
    stats: Stats = field(default_factory=Stats)
    """统计信息"""
    location: str | None = None
    """位置信息，可选"""
    replies: list["Comment"] = field(default_factory=list)
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
class ParseResult:
    """完整的解析结果"""

    platform: Platform
    """平台信息"""
    author: Author
    """作者信息"""
    title: str | None = None
    """标题"""
    timestamp: int | None = None
    """发布时间戳, 秒"""
    url: str | None = None
    """来源链接"""
    content: Sequence[MediaContent | str | None] = field(default_factory=list)
    """资源/文本内容"""
    stats: Stats = field(default_factory=Stats)
    """统计信息"""
    comments: list[Comment] = field(default_factory=list)
    """评论列表"""
    ai_summary: str | None = None
    """AI摘要"""
    extra: dict[str, Any] = field(default_factory=dict)
    """额外信息"""
    repost: "ParseResult | None" = None
    """转发的内容"""
    render_image: Path | None = None
    """渲染图片"""

    @property
    def display_url(self) -> str | None:
        return f"链接: {self.url}" if self.url else None

    @property
    def repost_display_url(self) -> str | None:
        return f"原帖: {self.repost.url}" if self.repost and self.repost.url else None

    @property
    def extra_info(self) -> str | None:
        return self.extra.get("info")

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
            f"comments: {self.comments}, "
            f"extra: {self.extra}, "
            f"repost: {self.repost}, "
            f"render_image: {self.render_image.name if self.render_image else 'None'}"
        )


class ParseResultKwargs(TypedDict, total=False):
    title: str | None
    """标题"""
    content: Sequence[MediaContent | str | None]
    """资源/文本内容"""
    timestamp: int | None
    """发布时间戳, 秒"""
    url: str | None
    """来源链接"""
    author: Author
    """作者信息"""
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
