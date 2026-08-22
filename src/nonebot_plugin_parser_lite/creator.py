from collections.abc import Coroutine
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable

from anyio import Path

from .config import pconfig as pconfig
from .data import (
    AudioContent,
    Author,
    Comment,
    ContentItem,
    GraphicContent,
    ImageContent,
    LinkContent,
    LivePhotoContent,
    MediaContent,
    PollContent,
    PollOption,
    QuoteContent,
    Stats,
    StickerContent,
    VideoContent,
)
from .download import DOWNLOADER
from .download.task import DownloadTaskWrapper
from .utils.cache import CacheManager

T = TypeVar("T", bound=MediaContent)


@runtime_checkable
class DownloadFunc(Protocol):
    """自定义下载函数协议：必须暴露 URL"""

    url: str
    ext_headers: dict[str, str] | None = None

    def __call__(self) -> Coroutine[Any, Any, Path]:
        raise NotImplementedError


def _with_need_send(obj: T, need_send: bool) -> T:
    obj.need_send = need_send
    return obj


class Creator:
    """ParseResult 相关数据对象工厂"""

    @staticmethod
    def author(
        name: str,
        avatar_url: str | None = None,
        description: str | None = None,
        id: str | None = None,
        location: str | None = None,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        avatar_cache_key: str | None = None,
    ):
        """
        创建作者对象

        :param name: 作者名称
        :param avatar_url: 作者头像 URL
        :param description: 作者描述
        :param id: 作者 ID
        :param location: 位置信息
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载头像
        :param avatar_cache_key: 头像的稳定缓存标识，为空时根据 URL 生成
        """

        avatar_task = (
            DOWNLOADER.download_img(
                url=avatar_url,
                cache_key=avatar_cache_key,
                cache_variant="avatar" if avatar_cache_key is not None else None,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
            if avatar_url
            else None
        )
        return Author(
            name=name,
            id=id,
            avatar=avatar_task,
            description=description,
            location=location,
        )

    @staticmethod
    def video(
        url_or_task: str | DownloadTaskWrapper[Path] | DownloadFunc,
        cover_url: str | None = None,
        duration: float = 0.0,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        cache_key: str | None = None,
    ):
        """
        创建视频内容,
        传入 `DownloadFunc` 时,
        会使用 `DownloadFunc` 的 `ext_headers` 而不是传入的.

        :param url_or_task: 视频 URL 或下载任务
        :param cover_url: 封面 URL
        :param duration: 视频时长
        :param cache_key: 稳定缓存标识，为空时根据各自 URL 生成
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载视频/封面
        """
        cover_task = None
        if cover_url:
            cover_task = DOWNLOADER.download_img(
                url=cover_url,
                cache_key=cache_key,
                cache_variant="cover" if cache_key is not None else None,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
        if isinstance(url_or_task, str):
            # 1) 传入 URL: 使用默认下载逻辑
            video_task = DOWNLOADER.download_video(
                url=url_or_task,
                cache_key=cache_key,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
        elif isinstance(url_or_task, DownloadTaskWrapper):
            # 2) 传入 DownloadTaskWrapper: 保持原样
            video_task = url_or_task
        elif isinstance(url_or_task, DownloadFunc):
            # 3) 传入下载函数: 自定义下载逻辑（不走 auto_task）
            download_func = url_or_task

            async def _runner() -> Path:
                return await download_func()

            # 这里手动构造一个 DownloadTaskWrapper，url 塞个占位描述字符串
            video_task = DownloadTaskWrapper(
                func=_runner,
                args=(),
                kwargs={},
                url=download_func.url,
                ext_headers=download_func.ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
        else:
            # 4) 传入了不受支持的类型：立即报错，避免 AttributeError
            raise TypeError(
                f"Creator.video 收到了不受支持的 url_or_task 类型: {type(url_or_task)},"
                "期望 str / DownloadTaskWrapper / DownloadFunc 协议对象"
            )
        return _with_need_send(
            VideoContent(path_task=video_task, cover=cover_task, duration=duration),
            need_send,
        )

    @staticmethod
    def videos(
        video_urls: list[str],
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        cache_keys: list[str | None] | None = None,
    ):
        """
        创建视频内容列表

        :param video_urls: 视频 URL 列表
        :param cache_keys: 与视频 URL 一一对应的稳定缓存标识
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        _cache_keys = cache_keys or [None] * len(video_urls)
        if len(_cache_keys) != len(video_urls):
            raise ValueError("cache_keys 与 video_urls 长度必须一致")
        return [
            Creator.video(
                url_or_task=url,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
                cache_key=cache_key,
            )
            for url, cache_key in zip(video_urls, _cache_keys, strict=True)
        ]

    @staticmethod
    def image(
        url: str,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        cache_key: str | None = None,
    ):
        """
        创建图片内容

        :param url: 图片 URL
        :param cache_key: 稳定缓存标识，为空时根据 URL 生成
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        task = DOWNLOADER.download_img(
            url=url,
            cache_key=cache_key,
            ext_headers=ext_headers,
            use_curl_cffi=use_curl_cffi,
        )

        return _with_need_send(ImageContent(path_task=task), need_send)

    @staticmethod
    def images(
        image_urls: list[str],
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        cache_keys: list[str | None] | None = None,
    ):
        """
        创建图片内容列表

        :param image_urls: 图片 URL 列表
        :param cache_keys: 与图片 URL 一一对应的稳定缓存标识
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        _cache_keys = cache_keys or [None] * len(image_urls)
        if len(_cache_keys) != len(image_urls):
            raise ValueError("cache_keys 与 image_urls 长度必须一致")
        return [
            Creator.image(
                url=url,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
                cache_key=cache_key,
            )
            for url, cache_key in zip(image_urls, _cache_keys, strict=True)
        ]

    @staticmethod
    def audio(
        url_or_task: str | DownloadTaskWrapper[Path] | DownloadFunc,
        duration: float = 0.0,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        cache_key: str | None = None,
    ):
        """
        创建音频内容,
        传入 `DownloadFunc` 时,
        会使用 `DownloadFunc` 的 `ext_headers` 而不是传入的.

        :param url_or_task: 音频 URL 或下载任务
        :param duration: 音频时长
        :param cache_key: 稳定缓存标识，为空时根据 URL 生成
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        if isinstance(url_or_task, str):
            # 1) 传入 URL: 使用默认下载逻辑
            audio_task = DOWNLOADER.download_audio(
                url=url_or_task,
                cache_key=cache_key,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
                convert_to_mp3=True,
            )
        elif isinstance(url_or_task, DownloadTaskWrapper):
            # 2) 传入 DownloadTaskWrapper: 保持原样
            audio_task = url_or_task
        elif isinstance(url_or_task, DownloadFunc):
            # 3) 传入下载函数: 自定义下载逻辑（不走 auto_task）
            download_func = url_or_task

            async def _runner() -> Path:
                return await download_func()

            # 这里手动构造一个 DownloadTaskWrapper，url 塞个占位描述字符串
            audio_task = DownloadTaskWrapper(
                func=_runner,
                args=(),
                kwargs={},
                url=download_func.url,
                ext_headers=download_func.ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
        else:
            # 4) 传入了不受支持的类型：立即报错，避免 AttributeError
            raise TypeError(
                f"Creator.audio 收到了不受支持的 url_or_task 类型: {type(url_or_task)},"
                "期望 str / DownloadTaskWrapper / DownloadFunc 协议对象"
            )

        return _with_need_send(
            AudioContent(path_task=audio_task, duration=duration), need_send
        )

    @staticmethod
    def graphic(
        url: str,
        alt: str | None = None,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        cache_key: str | None = None,
    ):
        """
        图片,此图片不参与九宫格且无高度限制

        :param url: 图片 URL
        :param cache_key: 稳定缓存标识，为空时根据 URL 生成
        :param alt: 图片描述
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        image_task = DOWNLOADER.download_img(
            url=url,
            cache_key=cache_key,
            ext_headers=ext_headers,
            use_curl_cffi=use_curl_cffi,
        )
        return _with_need_send(GraphicContent(path_task=image_task, alt=alt), need_send)

    @staticmethod
    def sticker(
        url: str,
        size: Literal["small", "medium"] = "medium",
        desc: str | None = None,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        cache_key: str | None = None,
    ):
        """
        创建贴纸内容

        :param url: 贴纸图片链接
        :param cache_key: 稳定缓存标识，为空时根据 URL 生成
        :param size: 贴纸大小
            - small: 比文字大一点
            - medium: 文字大小的两倍大一点
        :param desc: 贴纸描述
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        image_task = DOWNLOADER.download_img(
            url=url,
            cache_key=cache_key,
            ext_headers=ext_headers,
            cache_type=CacheManager.STICKER,
            use_curl_cffi=use_curl_cffi,
        )
        return StickerContent(path_task=image_task, size=size, desc=desc)

    @staticmethod
    def live_photo(
        video_url: str,
        image_url: str,
        bgm_url: str | None = None,
        loop: int = 1,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        cache_key: str | None = None,
    ):
        """
        创建  iPhone Live Photo 内容

        :param video_url: iPhone Live Photo 变化过程视频
        :param image_url: iPhone Live Photo 底图
        :param cache_key: 稳定缓存标识，为空时根据各自 URL 生成
        :param bgm_url: iPhone Live Photo 背景音乐
        :param loop: iPhone Live Photo 循环次数
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        video_task = DOWNLOADER.download_video(
            url=video_url,
            cache_key=cache_key,
            cache_variant="motion" if cache_key is not None else None,
            ext_headers=ext_headers,
            use_curl_cffi=use_curl_cffi,
        )
        image_task = DOWNLOADER.download_img(
            url=image_url,
            cache_key=cache_key,
            cache_variant="base" if cache_key is not None else None,
            ext_headers=ext_headers,
            use_curl_cffi=use_curl_cffi,
        )
        if bgm_url:
            bgm_task = DOWNLOADER.download_audio(
                url=bgm_url,
                cache_key=cache_key,
                cache_variant="bgm" if cache_key is not None else None,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
        else:
            bgm_task = None
        return _with_need_send(
            LivePhotoContent(
                path_task=video_task, base_image=image_task, loop=loop, bgm=bgm_task
            ),
            need_send,
        )

    @staticmethod
    def stats(
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
        if extra is None:
            extra = {}

        return Stats(
            view_count=view_count,
            like_count=like_count,
            collect_count=collect_count,
            share_count=share_count,
            comment_count=comment_count,
            extra=extra,
        )

    @staticmethod
    def comment(
        author: Author,
        content: list[ContentItem],
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
        :param location: 评论位置
        :param replies: 评论回复
        :param parent_author: 评论的父级作者
        :param download: 是否下载评论资源并发送
        """

        if replies is None:
            replies = []
        return Comment(
            author=author,
            content=content,
            timestamp=timestamp,
            stats=stats or Stats(),
            replies=replies,
            parent_author=parent_author,
        )

    @staticmethod
    def link(
        url: str,
        title: str | None = None,
        site_name: str | None = None,
        description: str | None = None,
        icon_url: str | None = None,
        preview_url: str | None = None,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        cache_key: str | None = None,
    ):
        """
        创建链接内容

        :param url: 链接地址
        :param title: 链接标题，为空时使用链接地址
        :param site_name: 来源站点名称
        :param description: 链接摘要
        :param icon_url: 来源站点图标 URL
        :param preview_url: 链接预览图 URL
        :param cache_key: 稳定缓存标识，为空时根据图片 URL 生成
        """
        if title is None:
            title = url
        icon = (
            DOWNLOADER.download_img(
                url=icon_url,
                cache_key=cache_key,
                cache_variant="link-icon" if cache_key is not None else None,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
            if icon_url
            else None
        )
        preview = (
            DOWNLOADER.download_img(
                url=preview_url,
                cache_key=cache_key,
                cache_variant="link-preview" if cache_key is not None else None,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
            if preview_url
            else None
        )
        return LinkContent(
            url=url,
            title=title,
            site_name=site_name,
            description=description,
            icon=icon,
            preview=preview,
        )

    @staticmethod
    def quote(
        text: str,
        title: str | None = None,
        url: str | None = None,
        icon_url: str | None = None,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        cache_key: str | None = None,
    ):
        """
        创建引用内容

        :param text: 引用正文
        :param title: 引用来源标题
        :param url: 引用来源链接
        :param icon_url: 引用来源图标或头像 URL
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        :param cache_key: 图标的稳定缓存标识，为空时根据 URL 生成
        """
        icon = (
            DOWNLOADER.download_img(
                url=icon_url,
                cache_key=cache_key,
                cache_variant="quote-icon" if cache_key is not None else None,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
            if icon_url
            else None
        )
        return QuoteContent(text=text, title=title, url=url, icon=icon)

    @staticmethod
    def poll(
        options: list[PollOption],
        title: str | None = None,
        total_votes: int | None = None,
        total_voters: int | None = None,
        multiple: bool = False,
        closed: bool = False,
        close_at: str | None = None,
    ):
        """
        创建平台无关的投票内容

        :param options: 投票选项列表
        :param title: 投票标题
        :param total_votes: 平台返回的总票数，多选时可能大于投票人数
        :param total_voters: 投票人数
        :param multiple: 是否允许多选
        :param closed: 投票是否已结束
        :param close_at: 投票结束时间，保留平台的原始表示
        """
        return PollContent(
            options=options,
            title=title,
            total_votes=total_votes,
            total_voters=total_voters,
            multiple=multiple,
            closed=closed,
            close_at=close_at,
        )
