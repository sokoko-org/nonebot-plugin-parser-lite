"""抖音媒体构建的离线测试：视频多线路下载器与图集 Live Photo 回归。"""

from typing import Any

import pytest
from render_test_support import ROOT  # noqa: F401  初始化插件包导入环境

from nonebot_plugin_parser_lite.data import (
    ImageContent,
    LivePhotoContent,
    VideoContent,
)
from nonebot_plugin_parser_lite.download.task import DownloadTaskWrapper
from nonebot_plugin_parser_lite.parsers.douyin import aweme as aweme_module
from nonebot_plugin_parser_lite.parsers.douyin.aweme import (
    Addr,
    Author,
    Aweme,
    DouyinVideoDownloader,
    Image,
    ShareInfo,
    Statistics,
    UrlList,
    Video,
)

CDN_LINES = [
    "https://v5-dy-ov-experiment.zjcdn.com/1.mp4",
    "https://v5-hl-mly-ov.zjcdn.com/2.mp4",
    "https://www.douyin.com/aweme/v1/play/?video_id=v0300",
]
DOUYIN_HEADERS = {"Referer": "https://www.douyin.com/"}


def make_video() -> Video:
    return Video(
        cover=UrlList(url_list=["https://cdn.example/cover.jpg"]),
        duration=3000,
        play_addr=Addr(uri="v0300fg10000daucag7og65uer1lq6ug", url_list=list(CDN_LINES)),
    )


def make_aweme(
    *,
    images: list[Image] | None = None,
    video: Video | None = None,
) -> Aweme:
    return Aweme(
        aweme_id="7691239726275202330",
        author=Author(
            uid="1",
            nickname="测试作者",
            avatar_thumb=UrlList(url_list=["https://cdn.example/avatar.jpg"]),
        ),
        share_info=ShareInfo(share_desc="视频", share_desc_info="#视频#正文"),
        statistics=Statistics(),
        create_time=0,
        share_url="https://www.douyin.com/video/7691239726275202330",
        region="CN",
        images=images,
        video=video,
    )


def test_live_photo_builds_live_photo_content() -> None:
    """图集里的 Live Photo 必须构建成 LivePhotoContent（而不是误用 Creator.video）。"""
    live = Image(
        url_list=["https://cdn.example/img1.jpg"],
        uri="img-1",
        clip_type=1,
        video=make_video(),
    )

    content = make_aweme(images=[live]).content

    live_items = [item for item in content if isinstance(item, LivePhotoContent)]
    assert len(live_items) == 1
    task = live_items[0].path_task
    assert isinstance(task, DownloadTaskWrapper)
    assert task.url == CDN_LINES[0]
    assert task.ext_headers == DOUYIN_HEADERS
    assert live_items[0].loop == 3


def test_plain_image_builds_image_content() -> None:
    plain = Image(url_list=["https://cdn.example/img2.jpg"], uri="img-2", clip_type=2)

    content = make_aweme(images=[plain]).content

    assert any(isinstance(item, ImageContent) for item in content)
    assert not any(isinstance(item, LivePhotoContent) for item in content)


def test_video_builds_video_content_with_downloader() -> None:
    content = make_aweme(video=make_video()).content

    video_items = [item for item in content if isinstance(item, VideoContent)]
    assert len(video_items) == 1
    task = video_items[0].path_task
    assert isinstance(task, DownloadTaskWrapper)
    assert task.url == CDN_LINES[0]
    assert video_items[0].duration == 3


@pytest.mark.asyncio
async def test_douyin_video_downloader_rotates_all_lines(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_download_video(**kwargs: Any) -> str:
        calls.append(kwargs)
        return "/tmp/fake-video.mp4"

    monkeypatch.setattr(
        aweme_module.DOWNLOADER, "download_video", fake_download_video
    )

    downloader = DouyinVideoDownloader(list(CDN_LINES), DOUYIN_HEADERS, "douyin:123:456")
    await downloader()

    assert calls[0]["url"] == CDN_LINES[0]
    assert calls[0]["fallback_urls"] == CDN_LINES[1:]
    assert calls[0]["retry_http_statuses"] == frozenset({460})
    assert calls[0]["ext_headers"] == DOUYIN_HEADERS


def test_douyin_video_downloader_ignores_empty_urls() -> None:
    downloader = DouyinVideoDownloader(["", "https://cdn.example/only.mp4"], None, "douyin:1223:456")

    assert downloader.url_list == ["https://cdn.example/only.mp4"]
    assert downloader.url == "https://cdn.example/only.mp4"
