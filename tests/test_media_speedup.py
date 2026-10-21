from pathlib import Path
from unittest.mock import AsyncMock

from anyio import Path as AnyPath
import pytest
import render_test_support as support

from nonebot_plugin_parser_lite.constants import PlatformEnum
from nonebot_plugin_parser_lite.data import (
    AudioContent,
    Author,
    GraphicContent,
    ImageContent,
    LivePhotoContent,
    ParseResult,
    Platform,
    StickerContent,
    VideoContent,
)
from nonebot_plugin_parser_lite.exception import SizeLimitException
from nonebot_plugin_parser_lite.utils.ffmpeg import FFmpeg
from nonebot_plugin_parser_lite.utils.media_edit import (
    apply_media_speedup,
    speedup_digest,
)


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
def test_malformed_rule_is_rejected(raw):
    with pytest.raises(ValueError, match="变速规则"):
        parse_media_speedup_rules([raw])


def test_later_rule_wins_and_ratio_is_not_capped():
    rules = parse_media_speedup_rules(
        ["bilibili:1:1.2", "bilibili:1:1.5", "bilibili:1:100"]
    )
    assert rules[(PlatformEnum.BILIBILI, "1")] == 100.0


# --------------------------------------------------------------------------
# 写到内容上


@pytest.mark.asyncio
async def test_rule_matches_platform_and_author(tmp_path, monkeypatch):
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

    apply_media_speedup(result)

    assert await media.get_path() == AnyPath(source)
    assert video.speedup == 1.5
    assert speedup_digest(result) == "1.50x"


@pytest.mark.asyncio
async def test_unmatched_author_clears_a_stale_speedup(tmp_path, monkeypatch):
    monkeypatch.setattr(
        support.pconfig, "plite_media_speedup_rules", ["bilibili:999:2.0"]
    )
    video = make_media(VideoContent, tmp_path, "v.mp4")
    video.speedup = 1.5
    result = make_result(author_id="123456", contents=[video])
    apply_media_speedup(result)
    # 结果对象跨消息缓存，重新解析没命中时必须清回 1.0
    assert video.speedup == 1.0


@pytest.mark.asyncio
async def test_repost_media_follows_the_outer_author(tmp_path, monkeypatch):
    """转发内容按外层结果的平台与作者命中规则，与 send_content 的遍历一致"""
    monkeypatch.setattr(
        support.pconfig, "plite_media_speedup_rules", ["bilibili:123456:1.5"]
    )
    inner = make_media(VideoContent, tmp_path, "inner.mp4")
    outer = make_media(VideoContent, tmp_path, "outer.mp4")
    result = make_result(contents=[outer], repost=make_result("777", [inner]))
    apply_media_speedup(result)
    assert (outer.speedup, inner.speedup) == (1.5, 1.5)


@pytest.mark.asyncio
async def test_unsent_media_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(
        support.pconfig, "plite_media_speedup_rules", ["bilibili:123456:1.5"]
    )
    video = make_media(VideoContent, tmp_path, "v.mp4")
    video.need_send = False
    result = make_result(contents=[video])
    apply_media_speedup(result)
    assert video.speedup == 1.0
    assert speedup_digest(result) == ""


@pytest.mark.asyncio
async def test_get_path_returns_source_when_no_speedup(tmp_path, monkeypatch):
    called: list[int] = []

    async def spy(cls, *args, **kwargs):
        called.append(1)
        return AnyPath(tmp_path / "product.mp4")

    monkeypatch.setattr(FFmpeg, "edit_video", classmethod(spy))

    cont = make_media(VideoContent, tmp_path, "video.mp4")
    assert await cont.get_path() == await cont.path_task
    assert speedup_digest(make_result(contents=[cont])) == "1.00x"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RuntimeError("ffmpeg 执行失败"), SizeLimitException(120.0)]
)
async def test_failure_falls_back_to_source_and_drops_speedup(
    tmp_path, monkeypatch, error
):

    async def failing(cls, *args, **kwargs):
        raise error

    monkeypatch.setattr(FFmpeg, "edit_video", classmethod(failing))

    cont = make_media(VideoContent, tmp_path, "video.mp4")
    cont.speedup = 1.25
    source = await cont.path_task
    assert await cont.get_path() == source
    # 退回原片后必须丢掉倍速，否则卡片继续按「已处理」显示时长与体积
    assert cont.speedup == 1.0
    assert cont.display_duration == "1:00"


@pytest.mark.asyncio
async def test_missing_ffmpeg_skips_speedup_and_drops_it(tmp_path, monkeypatch):

    called: list[int] = []

    async def spy(cls, *args, **kwargs):
        called.append(1)
        return AnyPath(tmp_path / "product.mp4")

    monkeypatch.setattr(FFmpeg, "edit_video", classmethod(spy))

    cont = make_media(VideoContent, tmp_path, "video.mp4")
    cont.speedup = 1.25
    assert await cont.get_path() == await cont.path_task
    assert called == [], "缺 ffmpeg 时不该调用转码"
    assert cont.speedup == 1.0
