from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from anyio import Path as AnyPath
import pytest
import render_test_support as support

from nonebot_plugin_parser_lite import matchers
from nonebot_plugin_parser_lite.constants import PlatformEnum
from nonebot_plugin_parser_lite.data import (
    Author,
    GraphicContent,
    ImageContent,
    LivePhotoContent,
    ParseResult,
    Platform,
    StickerContent,
    VideoContent,
)


@pytest.fixture
def parse_result(monkeypatch):
    monkeypatch.setattr(matchers, "_RESULT_CACHE", {})
    monkeypatch.setattr(matchers, "_PARSE_TASKS", {})

    async def parse(result):
        parser = SimpleNamespace(parse=AsyncMock(return_value=result))
        monkeypatch.setattr(matchers, "get_parser", lambda keyword: parser)
        search = SimpleNamespace(cache_key=result.url, keyword="test", searched=None)
        return await matchers._get_or_parse_result(search)

    return parse


def make_result(
    author_id: str = "123456",
    contents: list | None = None,
    platform: PlatformEnum = PlatformEnum.BILIBILI,
    repost: ParseResult | None = None,
) -> ParseResult:
    result = ParseResult(
        platform=Platform(platform, platform.value),
        author=Author("tester", id=author_id),
        url="https://example.com/video",
        content=list(contents or []),
    )
    result.repost = repost
    return result


def make_media(cls, tmp_path: Path, name: str, duration: float = 60.0):
    source = tmp_path / name
    source.write_bytes(b"source")
    return cls(path_task=support.ResolvedPathTask(source), duration=duration)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cls", [ImageContent, GraphicContent, StickerContent, LivePhotoContent]
)
async def test_other_media_has_no_speedup_interface(
    cls, tmp_path, monkeypatch, parse_result
):
    monkeypatch.setattr(
        support.pconfig, "plite_media_speedup_rules", ["bilibili:123456:1.5"]
    )
    source = tmp_path / "image.png"
    source.write_bytes(b"image")
    task = support.ResolvedPathTask(source)
    kwargs = {"base_image": task, "loop": 1} if cls is LivePhotoContent else {}
    media = cls(path_task=task, **kwargs)  # pyright: ignore[reportArgumentType]
    video = make_media(VideoContent, tmp_path, "video.mp4")
    result = make_result(contents=[media, video])

    await parse_result(result)

    assert await media.get_path() == AnyPath(source)
    assert video.speedup == 1.5


@pytest.mark.asyncio
async def test_unmatched_author_clears_a_stale_speedup(
    tmp_path, monkeypatch, parse_result
):
    monkeypatch.setattr(
        support.pconfig, "plite_media_speedup_rules", ["bilibili:999:2.0"]
    )
    video = make_media(VideoContent, tmp_path, "v.mp4")
    video.speedup = 1.5
    result = make_result(author_id="123456", contents=[video])
    await parse_result(result)
    assert video.speedup == 1.0


@pytest.mark.asyncio
async def test_repost_media_follows_the_outer_author(
    tmp_path, monkeypatch, parse_result
):
    """转发内容按外层结果的平台与作者命中规则，与 send_content 的遍历一致"""
    monkeypatch.setattr(
        support.pconfig, "plite_media_speedup_rules", ["bilibili:123456:1.5"]
    )
    inner = make_media(VideoContent, tmp_path, "inner.mp4")
    outer = make_media(VideoContent, tmp_path, "outer.mp4")
    result = make_result(contents=[outer], repost=make_result("777", [inner]))
    await parse_result(result)
    assert (outer.speedup, inner.speedup) == (1.5, 1.5)


@pytest.mark.asyncio
async def test_unsent_media_is_left_alone(tmp_path, monkeypatch, parse_result):
    monkeypatch.setattr(
        support.pconfig, "plite_media_speedup_rules", ["bilibili:123456:1.5"]
    )
    video = make_media(VideoContent, tmp_path, "v.mp4")
    video.need_send = False
    result = make_result(contents=[video])
    await parse_result(result)
    assert video.speedup == 1.0
