"""Parser 基类定义"""

import asyncio
from re import Match, Pattern, compile
from abc import ABC
from typing import TYPE_CHECKING, Any, Literal, TypeVar, ClassVar, cast
from asyncio import Task
from pathlib import Path
from collections.abc import Callable, Coroutine
from typing_extensions import Unpack, ParamSpec

P = ParamSpec("P")
R = TypeVar("R")
import os

from httpx import AsyncClient

from .data import (
    State,
    Author,
    Comment,
    Platform,
    ParseResult,
    AudioContent,
    ImageContent,
    MediaContent,
    VideoContent,
    StickerContent,
    GraphicsContent,
    ParseResultKwargs,
)
from ..utils import keep_zh_en_num
from ..config import pconfig as pconfig
from ..download import DOWNLOADER as DOWNLOADER
from ..constants import IOS_HEADER, COMMON_HEADER, ANDROID_HEADER, COMMON_TIMEOUT
from ..constants import DOWNLOAD_TIMEOUT as DOWNLOAD_TIMEOUT
from ..constants import PlatformEnum as PlatformEnum
from ..exception import TipException as TipException
from ..exception import ParseException as ParseException
from ..exception import DownloadException as DownloadException
from ..exception import ZeroSizeException as ZeroSizeException
from ..exception import SizeLimitException as SizeLimitException
from ..exception import DurationLimitException as DurationLimitException

T = TypeVar("T", bound="BaseParser")
HandlerFunc = Callable[[T, Match[str]], Coroutine[Any, Any, ParseResult]]
KeyPatterns = list[tuple[str, Pattern[str]]]

_KEY_PATTERNS = "_key_patterns"


# 重试装饰器
def retry(max_retries: int = 3, delay: float = 1.0):
    """
    通用重试装饰器

    Args:
        max_retries: 最大重试次数
        delay: 初始重试延迟（秒）
    """

    def decorator(
        func: Callable[P, Coroutine[Any, Any, R]],
    ) -> Callable[P, Coroutine[Any, Any, R]]:
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            retry_count = 0
            while retry_count <= max_retries:
                try:
                    return await func(*args, **kwargs)
                except Exception:
                    retry_count += 1
                    if retry_count > max_retries:
                        raise

                    # 指数退避
                    current_delay = delay * (2 ** (retry_count - 1))
                    await asyncio.sleep(current_delay)
            return await func(*args, **kwargs)  # 类型检查用，实际不会执行

        return wrapper

    return decorator


# 注册处理器装饰器
def handle(keyword: str, pattern: str, max_retries: int = 3):
    """注册处理器装饰器"""

    def decorator(func: HandlerFunc[T]) -> HandlerFunc[T]:
        if not hasattr(func, _KEY_PATTERNS):
            setattr(func, _KEY_PATTERNS, [])

        key_patterns: KeyPatterns = getattr(func, _KEY_PATTERNS)
        key_patterns.append((keyword, compile(pattern)))

        # 应用重试装饰器，但保留原始函数的_key_patterns属性
        # wrapped_func = retry(max_retries=max_retries)(func)
        wrapped_func = func
        # 取消重试，防止死号
        # 复制_key_patterns属性到包装函数
        setattr(wrapped_func, _KEY_PATTERNS, key_patterns)
        return wrapped_func

    return decorator


class BaseParser:
    """所有平台 Parser 的抽象基类

    子类必须实现：
    - platform: 平台信息（包含名称和显示名称)
    """

    _registry: ClassVar[list[type["BaseParser"]]] = []
    """ 存储所有已注册的 Parser 类 """

    platform: ClassVar[Platform]
    """ 平台信息（包含名称和显示名称） """

    if TYPE_CHECKING:
        _key_patterns: ClassVar[KeyPatterns]
        _handlers: ClassVar[dict[str, HandlerFunc]]

    def __init__(self):
        self.headers = COMMON_HEADER.copy()
        self.ios_headers = IOS_HEADER.copy()
        self.android_headers = ANDROID_HEADER.copy()
        self.timeout = COMMON_TIMEOUT

    def __init_subclass__(cls, **kwargs):
        """自动注册子类到 _registry"""
        super().__init_subclass__(**kwargs)
        if ABC not in cls.__bases__:  # 跳过抽象类
            BaseParser._registry.append(cls)

        cls._handlers = {}
        cls._key_patterns = []

        # 获取所有被 handle 装饰的方法
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name)
            if callable(attr) and hasattr(attr, _KEY_PATTERNS):
                key_patterns: KeyPatterns = getattr(attr, _KEY_PATTERNS)
                handler = cast(HandlerFunc, attr)
                for keyword, pattern in key_patterns:
                    cls._handlers[keyword] = handler
                    cls._key_patterns.append((keyword, pattern))

        # 按关键字长度降序排序
        cls._key_patterns.sort(key=lambda x: -len(x[0]))

    @classmethod
    def get_all_subclass(cls) -> list[type["BaseParser"]]:
        """获取所有已注册的 Parser 类"""
        return cls._registry

    async def parse(self, keyword: str, searched: Match[str]) -> ParseResult:
        """解析 URL 提取信息

        Args:
            keyword: 关键词
            searched: 正则表达式匹配对象，由平台对应的模式匹配得到

        Returns:
            ParseResult: 解析结果

        Raises:
            ParseException: 解析失败时抛出
        """
        return await self._handlers[keyword](self, searched)

    @retry(max_retries=3)
    async def parse_with_redirect(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> ParseResult:
        """先重定向再解析"""
        redirect_url = await self.get_redirect_url(url, headers=headers or self.headers)

        if redirect_url == url:
            raise ParseException(f"无法重定向 URL: {url}")

        keyword, searched = self.search_url(redirect_url)
        return await self.parse(keyword, searched)

    @classmethod
    def search_url(cls, url: str) -> tuple[str, Match[str]]:
        """搜索 URL 匹配模式"""
        for keyword, pattern in cls._key_patterns:
            if keyword not in url:
                continue
            if searched := pattern.search(url):
                return keyword, searched
        raise ParseException(f"无法匹配 {url}")

    @classmethod
    def result(cls, **kwargs: Unpack[ParseResultKwargs]) -> ParseResult:
        """构建解析结果"""
        return ParseResult(platform=cls.platform, **kwargs)

    @staticmethod
    @retry(max_retries=3)
    async def get_redirect_url(
        url: str,
        headers: dict[str, str] | None = None,
    ) -> str:
        """获取重定向后的 URL, 单次重定向"""

        headers = headers or COMMON_HEADER.copy()
        async with AsyncClient(
            headers=headers,
            verify=False,
            follow_redirects=False,
            timeout=COMMON_TIMEOUT,
        ) as client:
            response = await client.get(url)
            if response.status_code >= 400:
                response.raise_for_status()
            return response.headers.get("Location", url)

    @staticmethod
    @retry(max_retries=3)
    async def get_final_url(
        url: str,
        headers: dict[str, str] | None = None,
    ) -> str:
        """获取重定向后的 URL, 允许多次重定向"""

        headers = headers or COMMON_HEADER.copy()
        async with AsyncClient(
            headers=headers,
            verify=False,
            follow_redirects=True,
            timeout=COMMON_TIMEOUT,
        ) as client:
            response = await client.get(url)
            if response.status_code >= 400:
                response.raise_for_status()
            return str(response.url)

    def create_author(
        self,
        name: str,
        avatar_url: str | None = None,
        description: str | None = None,
    ):
        """创建作者对象"""

        avatar_task = None
        if avatar_url:
            avatar_task = DOWNLOADER.download_img(avatar_url, ext_headers=self.headers)
        return Author(name=name, avatar=avatar_task, description=description)

    def create_video(
        self,
        url_or_task: str | Task[Path] | Callable[[], Coroutine[Any, Any, Path]],
        cover_url: str | None = None,
        duration: float = 0.0,
        video_name: str | None = None,
    ):
        """创建视频内容"""

        # 清理文件名，只保留安全字符
        if video_name:
            # 保留文件名中的后缀

            base_name, ext = os.path.splitext(video_name)
            cleaned_base = keep_zh_en_num(base_name)
            video_name = f"{cleaned_base}{ext}"

        cover_task = None
        if cover_url:
            cover_task = DOWNLOADER.download_img(cover_url, ext_headers=self.headers)
        if isinstance(url_or_task, str):
            url_or_task = DOWNLOADER.download_video(
                url_or_task, video_name=video_name, ext_headers=self.headers
            )

        return VideoContent(url_or_task, cover_task, duration)

    def create_videos(
        self,
        video_urls: list[str],
    ):
        """创建视频内容列表"""

        return [self.create_video(url) for url in video_urls]

    def create_images(
        self,
        image_urls: list[str],
    ):
        """创建图片内容列表"""

        return [self.create_image(url) for url in image_urls]

    def create_image(
        self,
        url_or_task: str | Task[Path],
    ):
        """创建图片内容"""

        if isinstance(url_or_task, str):
            url_or_task = DOWNLOADER.download_img(url_or_task, ext_headers=self.headers)

        return ImageContent(url_or_task)

    def create_audio(
        self,
        url_or_task: str | Task[Path],
        duration: float = 0.0,
        audio_name: str | None = None,
    ):
        """创建音频内容"""

        # 清理文件名，只保留安全字符
        if audio_name:
            # 保留文件名中的后缀

            base_name, ext = os.path.splitext(audio_name)
            cleaned_base = keep_zh_en_num(base_name)
            audio_name = f"{cleaned_base}{ext}"

        if isinstance(url_or_task, str):
            url_or_task = DOWNLOADER.download_audio(
                url_or_task, audio_name=audio_name, ext_headers=self.headers
            )

        return AudioContent(url_or_task, duration)

    def create_graphics(
        self,
        image_url: str,
        alt: str | None = None,
    ):
        """创建图文内容 图片不能为空 文字可空 渲染时文字在前 图片在后"""

        image_task = DOWNLOADER.download_img(image_url, ext_headers=self.headers)
        return GraphicsContent(image_task, alt)

    def create_sticker(
        self,
        url: str,
        size: Literal["small", "medium"] = "medium",
        desc: str | None = None,
    ):
        """
        创建贴纸内容

        :param url: 贴纸图片链接
        :param size: 贴纸大小
            - small: 比文字大一点
            - medium: 文字大小的两倍大一点
        """

        image_task = DOWNLOADER.download_img(url, ext_headers=self.headers)
        return StickerContent(image_task, size, desc)

    def create_state(
        self,
        view_count: int = 0,
        like_count: int = 0,
        collect_count: int = 0,
        share_count: int = 0,
        comment_count: int = 0,
        extra: dict[str, Any] | None = None,
    ):
        """创建统计信息"""
        if extra is None:
            extra = {}

        return State(
            view_count=view_count,
            like_count=like_count,
            collecte_count=collect_count,
            share_count=share_count,
            comment_count=comment_count,
            extra=extra,
        )

    def create_comment(
        self,
        author: Author,
        content: list[MediaContent | str | None],
        timestamp: int | None = None,
        state: State | None = None,
        location: str | None = None,
        replies: list[Comment] | None = None,
        parent_author: Author | None = None,
    ):
        """创建评论内容"""

        if replies is None:
            replies = []
        return Comment(
            author=author,
            content=content,
            timestamp=timestamp,
            state=state,
            location=location,
            replies=replies,
            parent_author=parent_author,
        )
