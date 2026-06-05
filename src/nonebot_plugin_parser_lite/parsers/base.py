"""Parser 基类定义"""

from abc import ABC
import asyncio
from collections.abc import Callable, Coroutine, Sequence
from re import Pattern, compile, escape
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    TypeVar,
    cast,
    final,
)
from typing_extensions import ParamSpec, Unpack

from anyio import Path
from httpx import AsyncClient

from ..config import pconfig as pconfig
from ..constants import (
    ANDROID_HEADER,
    COMMON_HEADER,
    COMMON_TIMEOUT,
    IOS_HEADER,
    MatchWithParams,
    ParamRules,
)
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


HandlerFunc = Callable[[T, MatchWithParams], Coroutine[Any, Any, ParseResult]]
KeyPatterns = list[tuple[str, Pattern[str], ParamRules]]

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
def handle(
    keyword: str,
    pattern: str | None = None,
    *,
    params: ParamRules | None = None,
):
    """注册处理器装饰器

    约定：
    - keyword: 必填，在 rule 里始终作为关键字用于初步判断 (`keyword in text`)
    - pattern: 可选，完整正则，用于匹配整段 URL 文本
    - params: 可选，ParamRules，用于基于 query 的补充筛选（required/equals/default/one_of/as_int 等）
    - pattern 与 params 至少要指定一个（可以同时存在）：
        - 只有 pattern：纯正则匹配，不看 query
        - 只有 params：regex 由 keyword 自动生成为 `https?://<keyword>[^\\s]*`
        - pattern + params：先用 pattern 过滤，再用 params 解析 URL 后进一步判断
    """  # noqa: E501

    if pattern is None and not params:
        raise ValueError("handle: pattern 和 params 至少要指定一个")

    # 确定基础 regex：
    # - 有 pattern 时：使用 pattern 作为完整正则
    # - 无 pattern 时：使用 keyword 作为 URL 前缀生成正则
    if pattern is not None:
        regex = pattern
    else:
        escaped = escape(keyword)
        regex = rf"https?://{escaped}[^\s]*"

    param_rules = params or {}

    def decorator(func: HandlerFunc[T]) -> HandlerFunc[T]:
        if not hasattr(func, _KEY_PATTERNS):
            setattr(func, _KEY_PATTERNS, [])

        key_patterns: KeyPatterns = getattr(func, _KEY_PATTERNS)
        key_patterns.append((keyword, compile(regex), param_rules))

        wrapped_func = func
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
        _handlers: ClassVar[dict[str, list[tuple[Pattern[str], HandlerFunc]]]]

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

        cls._handlers: dict[str, list[tuple[Pattern[str], HandlerFunc]]] = {}
        cls._key_patterns = []

        # 获取所有被 handle 装饰的方法
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name)
            if callable(attr) and hasattr(attr, _KEY_PATTERNS):
                key_patterns: KeyPatterns = getattr(attr, _KEY_PATTERNS)
                handler = cast(HandlerFunc, attr)
                for keyword, pattern, param_rules in key_patterns:
                    # 记录 keyword -> (pattern, handler) 列表（解析时只关心 pattern）
                    cls._handlers.setdefault(keyword, []).append((pattern, handler))
                    # _key_patterns 用于 matcher 注册，保留 param_rules
                    cls._key_patterns.append((keyword, pattern, param_rules))

        # 按关键字长度降序排序（search_url 仍然按原逻辑）
        cls._key_patterns.sort(key=lambda x: -len(x[0]))

    @classmethod
    def get_all_subclass(cls) -> list[type["BaseParser"]]:
        """获取所有已注册的 Parser 类"""
        return cls._registry

    @final
    async def parse(self, keyword: str, searched: MatchWithParams) -> ParseResult:
        """解析 URL 提取信息。

        :param keyword: 关键词
        :param searched: 正则表达式匹配对象，由平台对应的模式匹配得到
        :return: 解析结果
        :raise ParseException: 未找到匹配的 handler 时抛出
        """
        handlers = self._handlers.get(keyword)
        if not handlers:
            raise ParseException(f"未找到关键字 {keyword!r} 对应的 handler")

        text = searched.url
        for pattern, handler in handlers:
            # pattern 是当初 handle 时 compile 出来的正则
            # 这里用 search/fullmatch 都可以，search 更宽松
            if pattern.search(text):
                return await handler(self, searched)

        # 理论上不该走到这里，防御性错误
        raise ParseException(
            f"关键字 {keyword!r} 存在 handler 但无任何模式匹配 {text!r}"
        )

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
    def _match_param_rules(cls, mwp: MatchWithParams, rules: ParamRules) -> bool:
        """根据 ParamRules 检查并补充 mwp.params."""
        if not rules:
            return True

        for name, rule in rules.items():
            required = rule.get("required", True)
            value = mwp.params.get(name)

            # 默认值处理
            if value is None and "default" in rule:
                value = rule["default"]
                mwp.params[name] = value  # 写回，后续 handler 可以直接用

            if value is None:
                if required:
                    return False
                # 非必填且无值 -> 略过后续 equals/one_of/as_int 校验
                continue

            # equals
            if "equals" in rule and value != rule["equals"]:
                return False

            # one_of
            if "one_of" in rule and value not in rule["one_of"]:
                return False

            # as_int 仅做格式校验
            if rule.get("as_int"):
                try:
                    int(value)
                except ValueError:
                    return False

        return True

    @classmethod
    def search_url(cls, url: str) -> tuple[str, MatchWithParams]:
        """搜索 URL 匹配模式（支持基于 params 的筛选）"""
        for keyword, pattern, param_rules in cls._key_patterns:
            if keyword not in url:
                continue
            m = pattern.search(url)
            if not m:
                continue
            mwp = MatchWithParams(m)
            mwp.param_rules = param_rules
            if cls._match_param_rules(mwp, param_rules):
                return keyword, mwp
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
