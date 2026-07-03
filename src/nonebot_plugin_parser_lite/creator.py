from collections.abc import Coroutine, Sequence
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable

from anyio import Path

from .cache import CacheManager
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
    Stats,
    StickerContent,
    VideoContent,
)
from .download import DOWNLOADER
from .download.task import DownloadTaskWrapper

T = TypeVar("T", bound=MediaContent)


@runtime_checkable
class VideoDownloadFunc(Protocol):
    """自定义视频下载函数协议：必须暴露真实视频 URL。"""

    video_url: str
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
        """

        avatar_task = (
            DOWNLOADER.download_img(
                url=avatar_url,
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
        url_or_task: str | DownloadTaskWrapper[Path] | VideoDownloadFunc,
        cover_url: str | None = None,
        duration: float = 0.0,
        video_name: str | None = None,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ):
        """
        创建视频内容,
        传入 `VideoDownloadFunc` 时,
        会使用 `VideoDownloadFunc` 的 `ext_headers` 而不是传入的.
        这个问题会在后续版本进行修复

        :param url: 视频 URL
        :param cover_url: 封面 URL
        :param duration: 视频时长
        :param video_name: 视频名称
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载视频/封面
        """
        cover_task = None
        if cover_url:
            cover_task = DOWNLOADER.download_img(
                url=cover_url,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
        if isinstance(url_or_task, str):
            # 1) 传入 URL: 使用默认下载逻辑
            video_task = DOWNLOADER.download_video(
                url=url_or_task,
                video_name=video_name,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
        elif isinstance(url_or_task, DownloadTaskWrapper):
            # 2) 传入 DownloadTaskWrapper: 保持原样
            video_task = url_or_task
        elif isinstance(url_or_task, VideoDownloadFunc):
            # 3) 传入下载函数: 自定义下载逻辑（不走 auto_task）
            download_func = url_or_task

            async def _runner() -> Path:
                return await download_func()

            # 这里手动构造一个 DownloadTaskWrapper，url 塞个占位描述字符串
            video_task = DownloadTaskWrapper(
                func=_runner,
                args=(),
                kwargs={},
                url=download_func.video_url,
                ext_headers=download_func.ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
        else:
            # 4) 传入了不受支持的类型：立即报错，避免 AttributeError
            raise TypeError(
                f"Creator.video 收到了不受支持的 url_or_task 类型: {type(url_or_task)},"
                "期望 str / DownloadTaskWrapper / VideoDownloadFunc 协议对象"
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
    ):
        """
        创建视频内容列表

        :param video_urls: 视频 URL 列表
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        return [
            Creator.video(
                url_or_task=url,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
            for url in video_urls
        ]

    @staticmethod
    def image(
        url: str,
        img_name: str | None = None,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ):
        """
        创建图片内容

        :param url: 图片 URL
        :param img_name: 图片名称
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        task = DOWNLOADER.download_img(
            url=url,
            img_name=img_name,
            ext_headers=ext_headers,
            use_curl_cffi=use_curl_cffi,
        )

        return _with_need_send(ImageContent(path_task=task), need_send)

    @staticmethod
    def images(
        image_urls: list[str],
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ):
        """
        创建图片内容列表

        :param image_urls: 图片 URL 列表
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        return [
            Creator.image(
                url=url,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
            for url in image_urls
        ]

    @staticmethod
    def audio(
        url: str,
        duration: float = 0.0,
        audio_name: str | None = None,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ):
        """
        创建音频内容

        :param url: 音频 URL
        :param duration: 音频时长
        :param audio_name: 音频名称
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        task = DOWNLOADER.download_audio(
            url=url,
            audio_name=audio_name,
            ext_headers=ext_headers,
            use_curl_cffi=use_curl_cffi,
        )

        return _with_need_send(
            AudioContent(path_task=task, duration=duration), need_send
        )

    @staticmethod
    def graphic(
        url: str,
        img_name: str | None = None,
        alt: str | None = None,
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ):
        """
        图片,此图片不参与九宫格

        :param url: 图片 URL
        :param img_name: 图片名称
        :param alt: 图片描述
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        image_task = DOWNLOADER.download_img(
            url=url,
            img_name=img_name,
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
    ):
        """
        创建贴纸内容

        :param url: 贴纸图片链接
        :param size: 贴纸大小
            - small: 比文字大一点
            - medium: 文字大小的两倍大一点
        :param desc: 贴纸描述
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        image_task = DOWNLOADER.download_img(
            url=url,
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
        need_send: bool = True,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ):
        """
        创建  iPhone Live Photo 内容

        :param video_url: iPhone Live Photo 变化过程视频
        :param image_url: iPhone Live Photo 底图
        :param bgm_url: iPhone Live Photo 背景音乐
        :param need_send: 是否发送
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        """

        video_task = DOWNLOADER.download_video(
            url=video_url,
            ext_headers=ext_headers,
            use_curl_cffi=use_curl_cffi,
        )
        image_task = DOWNLOADER.download_img(
            url=image_url,
            ext_headers=ext_headers,
            use_curl_cffi=use_curl_cffi,
        )
        if bgm_url:
            bgm_task = DOWNLOADER.download_audio(
                url=bgm_url,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )
        else:
            bgm_task = None
        return _with_need_send(
            LivePhotoContent(video_task, image_task, bgm_task),
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
        content: Sequence[ContentItem],
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
    def link(url: str, text: str | None = None):
        """
        创建链接内容

        :param url: 链接地址
        :param text: 链接文本
        """
        if text is None:
            text = url
        return LinkContent(url=url, text=text)
