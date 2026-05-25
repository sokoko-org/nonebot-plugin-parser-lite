"""Parser 基类定义"""

from abc import ABC
import asyncio
from collections.abc import Callable, Coroutine, Sequence
from re import Match, Pattern, compile
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypeVar, cast, final
from typing_extensions import ParamSpec, Unpack

from anyio import Path
from httpx import AsyncClient

from ..config import pconfig as pconfig
from ..constants import ANDROID_HEADER, COMMON_HEADER, COMMON_TIMEOUT, IOS_HEADER
from ..constants import PlatformEnum as PlatformEnum
from ..download import DOWNLOADER as DOWNLOADER
from ..download.task import DownloadTaskWrapper
from ..exception import DownloadException as DownloadException
from ..exception import DurationLimitException as DurationLimitException
from ..exception import ParseException as ParseException
from ..exception import SizeLimitException as SizeLimitException
from ..exception import TipException as TipException
from ..exception import ZeroSizeException as ZeroSizeException
from .creator import (
    VideoDownloadFunc,
    create_audio,
    create_author,
    create_comment,
    create_graphic,
    create_image,
    create_images,
    create_live_photo,
    create_stats,
    create_sticker,
    create_video,
    create_videos,
)
from .data import (
    Author,
    Comment,
    MediaContent,
    ParseResult,
    ParseResultKwargs,
    Platform,
    Stats,
)

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T", bound="BaseParser")
HandlerFunc = Callable[[T, Match[str]], Coroutine[Any, Any, ParseResult]]
KeyPatterns = list[tuple[str, Pattern[str]]]

_KEY_PATTERNS = "_key_patterns"


# 重试装饰器
def retry(max_retries: int = 3, delay: float = 1.0):
    """
    通用重试装饰器

    :param max_retries: 最大重试次数
    :param delay: 初始重试延迟（秒）
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
def handle(keyword: str, pattern: str, max_retries: int = 1):
    """注册处理器装饰器"""

    def decorator(func: HandlerFunc[T]) -> HandlerFunc[T]:
        if not hasattr(func, _KEY_PATTERNS):
            setattr(func, _KEY_PATTERNS, [])

        key_patterns: KeyPatterns = getattr(func, _KEY_PATTERNS)
        key_patterns.append((keyword, compile(pattern)))

        # 应用重试装饰器
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
        self.httpx = AsyncClient(
            headers=self.headers, timeout=self.timeout, follow_redirects=True
        )

    async def aclose(self) -> None:
        """关闭底层 HTTP 客户端，释放连接等资源。"""
        await self.httpx.aclose()

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

    @final
    async def parse(self, keyword: str, searched: Match[str]) -> ParseResult:
        """解析 URL 提取信息

        :param keyword: 关键词
        :param searched: 正则表达式匹配对象，由平台对应的模式匹配得到

        :return: 解析结果

        :raise: 解析失败时抛出
        """
        return await self._handlers[keyword](self, searched)

    @retry(max_retries=3)
    async def parse_with_redirect(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> ParseResult:
        """先重定向再解析"""
        redirect_url = await self.get_final_url(url, headers=headers or self.headers)

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
    def result(
        cls,
        author: Author,
        url: str,
        content: Sequence[MediaContent | str],
        **kwargs: Unpack[ParseResultKwargs],
    ) -> ParseResult:
        """构建解析结果"""
        return ParseResult(
            platform=cls.platform, author=author, url=url, content=content, **kwargs
        )

    @staticmethod
    @retry(max_retries=3)
    async def get_final_url(
        url: str,
        headers: dict[str, str] | None = None,
    ) -> str:
        """获取最终重定向后的 URL"""
        response = await DOWNLOADER.head(url, ext_headers=headers)
        return str(response.url)

    def create_author(
        self,
        name: str,
        avatar_url: str | None = None,
        description: str | None = None,
        id: str | None = None,
        location: str | None = None,
    ):
        """
        创建作者对象

        :param name: 作者名称
        :param avatar_url: 作者头像 URL
        :param description: 作者描述
        :param id: 作者 ID
        :param location: 位置信息
        """

        return create_author(
            name=name,
            avatar_url=avatar_url,
            description=description,
            id=id,
            location=location,
        )

    def create_video(
        self,
        url_or_task: str | DownloadTaskWrapper[Path] | VideoDownloadFunc,
        cover_url: str | None = None,
        duration: float = 0.0,
        video_name: str | None = None,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
    ):
        """
        创建视频内容

        :param url: 视频 URL
        :param cover_url: 封面 URL
        :param duration: 视频时长
        :param video_name: 视频名称
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        """

        return create_video(
            url_or_task=url_or_task,
            cover_url=cover_url,
            duration=duration,
            video_name=video_name,
            need_send=need_send,
            ext_headers=ext_headers,
        )

    def create_videos(
        self,
        video_urls: list[str],
        ext_headers: dict[str, str] | None = None,
    ):
        """
        创建视频内容列表

        :param video_urls: 视频 URL 列表
        :param ext_headers: 额外请求头
        """

        return create_videos(video_urls=video_urls, ext_headers=ext_headers)

    def create_images(
        self,
        image_urls: list[str],
        ext_headers: dict[str, str] | None = None,
    ):
        """
        创建图片内容列表

        :param image_urls: 图片 URL 列表
        :param ext_headers: 额外请求头
        """

        return create_images(image_urls=image_urls, ext_headers=ext_headers)

    def create_image(
        self,
        url: str,
        img_name: str | None = None,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
    ):
        """
        创建图片内容

        :param url: 图片 URL
        :param img_name: 图片名称
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        """

        return create_image(
            url=url, img_name=img_name, need_send=need_send, ext_headers=ext_headers
        )

    def create_audio(
        self,
        url: str,
        duration: float = 0.0,
        audio_name: str | None = None,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
    ):
        """
        创建音频内容

        :param url: 音频 URL
        :param duration: 音频时长
        :param audio_name: 音频名称
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        """

        return create_audio(
            url=url,
            duration=duration,
            audio_name=audio_name,
            need_send=need_send,
            ext_headers=ext_headers,
        )

    def create_graphic(
        self,
        image_url: str,
        img_name: str | None = None,
        alt: str | None = None,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
    ):
        """
        图片,此图片不参与九宫格

        :param image_url: 图片 URL
        :param img_name: 图片名称
        :param alt: 图片描述
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        """

        return create_graphic(
            image_url=image_url,
            img_name=img_name,
            alt=alt,
            need_send=need_send,
            ext_headers=ext_headers,
        )

    def create_sticker(
        self,
        url: str,
        size: Literal["small", "medium"] = "medium",
        desc: str | None = None,
        ext_headers: dict[str, str] | None = None,
    ):
        """
        创建贴纸内容

        :param url: 贴纸图片链接
        :param size: 贴纸大小
            - small: 比文字大一点
            - medium: 文字大小的两倍大一点
        :param desc: 贴纸描述
        :param ext_headers: 额外请求头
        """

        return create_sticker(url=url, size=size, desc=desc, ext_headers=ext_headers)

    def create_live_photo(
        self,
        video_url: str,
        image_url: str,
        bgm_url: str | None = None,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
    ):
        """
        创建  iPhone Live Photo 内容

        :param video_url: iPhone Live Photo 变化过程视频
        :param image_url: iPhone Live Photo 底图
        :param bgm_url: iPhone Live Photo 背景音乐
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        """
        return create_live_photo(
            video_url=video_url,
            image_url=image_url,
            bgm_url=bgm_url,
            need_send=need_send,
            ext_headers=ext_headers,
        )

    def create_stats(
        self,
        view_count: str | None = None,
        like_count: str | None = None,
        collect_count: str | None = None,
        share_count: str | None = None,
        comment_count: str | None = None,
        extra: dict[str, Any] | None = None,
    ):
        """
        创建统计信息

        :param view_count: 浏览数
        :param like_count: 点赞数
        :param collect_count: 收藏数
        :param share_count: 分享数
        :param comment_count: 评论数
        :param extra: 额外的信息
        """
        return create_stats(
            view_count=view_count,
            like_count=like_count,
            collect_count=collect_count,
            share_count=share_count,
            comment_count=comment_count,
            extra=extra,
        )

    def create_comment(
        self,
        author: Author,
        content: Sequence[MediaContent | str | None],
        timestamp: int | None = None,
        stats: Stats | None = None,
        replies: list[Comment] | None = None,
        parent_author: Author | None = None,
    ):
        """
        创建评论内容

        :param author: 评论作者
        :param content: 评论内容
        :param timestamp: 评论时间戳
        :param stats: 评论统计信息
        :param replies: 评论回复
        :param parent_author: 评论的父级作者
        """

        return create_comment(
            author=author,
            content=content,
            timestamp=timestamp,
            stats=stats,
            replies=replies,
            parent_author=parent_author,
        )
