from typing import Any, Literal, TypedDict
from asyncio import Task
from pathlib import Path
from datetime import datetime
from dataclasses import field, dataclass
from collections.abc import Callable, Sequence, Coroutine


def repr_path_task(
    path_task: Path | Task[Path] | Callable[[], Coroutine[Any, Any, Path]],
) -> str:
    if isinstance(path_task, Path):
        return f"path={path_task.name}"
    elif isinstance(path_task, Task):
        return f"task={path_task.get_name()}, done={path_task.done()}"
    else:
        return f"callable={path_task.__name__}"


@dataclass(repr=False, slots=True)
class MediaContent:
    path_task: Path | Task[Path] | Callable[[], Coroutine[Any, Any, Path]]

    async def get_path(self) -> Path:
        if isinstance(self.path_task, Path):
            pass
        elif isinstance(self.path_task, Task):
            self.path_task = await self.path_task
        else:
            # 执行可调用对象（coroutine function）
            self.path_task = await self.path_task()

        return self.path_task

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

    cover: Path | Task[Path] | None = None
    """视频封面"""
    duration: float = 0.0
    """时长 单位: 秒"""

    async def get_cover_path(self) -> Path | None:
        if self.cover is None:
            return None
        if isinstance(self.cover, Path):
            return self.cover
        self.cover = await self.cover
        return self.cover

    @property
    def display_duration(self) -> str:
        minutes, seconds = divmod(int(self.duration), 60)
        return f"时长: {minutes}:{seconds:02d}"


@dataclass(repr=False, slots=True)
class ImageContent(MediaContent):
    """图片内容"""

    pass


@dataclass(repr=False, slots=True)
class GraphicsContent(MediaContent):
    """图文内容 即不参与九宫格的图片"""

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
    avatar: Path | Task[Path] | None = None
    """作者头像 URL 或本地路径"""
    description: str | None = None
    """作者个性签名等"""

    async def get_avatar_path(self) -> Path | None:
        if self.avatar is None:
            return None
        if isinstance(self.avatar, Path):
            return self.avatar
        self.avatar = await self.avatar
        return self.avatar


@dataclass(repr=False, slots=True)
class State:
    """统计信息"""

    view_count: int = 0
    """浏览数"""
    like_count: int = 0
    """点赞数"""
    collecte_count: int = 0
    """收藏数"""
    share_count: int = 0
    """分享数"""
    comment_count: int = 0
    """评论数"""
    extra: dict[str, Any] = field(default_factory=dict)
    """额外信息, 比如弹幕数/硬币数"""


@dataclass(repr=False, slots=True)
class Comment:
    """评论信息"""

    author: Author
    """作者信息"""
    content: Sequence[MediaContent | str | None]
    """评论内容，可以是文本或媒体对象"""
    timestamp: int | None
    """发布时间戳，单位秒"""
    state: State | None = None
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
    def formatted_datetime(self) -> str | None:
        """格式化时间戳"""
        if self.timestamp is None:
            return None
        return datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")


@dataclass(repr=False, slots=True)
class ParseResult:
    """完整的解析结果"""

    platform: Platform
    """平台信息"""
    author: Author | None = None
    """作者信息"""
    title: str | None = None
    """标题"""
    timestamp: int | None = None
    """发布时间戳, 秒"""
    url: str | None = None
    """来源链接"""
    content: Sequence[MediaContent | str | None] = field(default_factory=list)
    """资源/文本内容"""
    state: State | None = None
    """统计信息"""
    comments: list[Comment] = field(default_factory=list)
    """评论列表"""
    extra: dict[str, Any] = field(default_factory=dict)
    """额外信息"""
    repost: "ParseResult | None" = None
    """转发的内容"""
    render_image: Path | None = None
    """渲染图片"""
    media_contents: list[MediaContent | Path] = field(default_factory=list)
    """延迟发送的媒体内容"""

    @property
    def display_url(self) -> str | None:
        return f"链接: {self.url}" if self.url else None

    @property
    def repost_display_url(self) -> str | None:
        return f"原帖: {self.repost.url}" if self.repost and self.repost.url else None

    @property
    def extra_info(self) -> str | None:
        return self.extra.get("info")

    @property
    async def cover_path(self) -> Path | None:
        """获取封面路径"""
        # 先检查视频内容
        for cont in self.content:
            if isinstance(cont, VideoContent):
                return await cont.get_cover_path()
            elif isinstance(cont, ImageContent):
                return await cont.get_path()

        # 如果没有视频和图片内容，使用默认图片
        default_image_path = (
            Path(__file__).parent.parent / "renders" / "resources" / "QIQI.jpg"
        )
        return default_image_path if default_image_path.exists() else None

    @property
    def formatted_datetime(self) -> str | None:
        """格式化时间戳"""
        if self.timestamp is None:
            return None
        return datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")

    def __repr__(self) -> str:
        return (
            f"platform: {self.platform.display_name}, "
            f"timestamp: {self.timestamp}, "
            f"title: {self.title}, "
            f"url: {self.url}, "
            f"author: {self.author}, "
            f"content: {self.content}, "
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
    author: Author | None
    """作者信息"""
    extra: dict[str, Any]
    """额外信息"""
    repost: ParseResult | None
    """转发的内容"""
