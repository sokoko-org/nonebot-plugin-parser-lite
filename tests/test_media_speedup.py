"""上传前倍速：规则配置、写在内容上、渲染与发送读同一个值。

倍速是平台无关的通用能力；按标注裁切是 B 站特有的，用例在
test_bilibili_sponsorblock.py。
"""

import asyncio
from pathlib import Path

from anyio import Path as AnyPath
from jinja2 import Environment, FileSystemLoader
import pytest
import render_test_support as support
from render_test_support import ROOT, ResolvedPathTask, ThemeManager

from nonebot_plugin_parser_lite.config import parse_media_speedup_rules
from nonebot_plugin_parser_lite.constants import PlatformEnum
from nonebot_plugin_parser_lite.data import (
    AudioContent,
    Author,
    ParseResult,
    Platform,
    VideoContent,
)
from nonebot_plugin_parser_lite.exception import SizeLimitException
from nonebot_plugin_parser_lite.utils.cache import CacheManager
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
    cont = cls(path_task=ResolvedPathTask(source), duration=duration)
    return cont


# --------------------------------------------------------------------------
# 规则配置


def test_rule_grammar_is_platform_colon_id_colon_ratio():
    assert parse_media_speedup_rules(
        ["bilibili:123456:1.25", " douyin : abc : 2 ", "bilibili:777:0.5"]
    ) == {
        (PlatformEnum.BILIBILI, "123456"): 1.25,
        (PlatformEnum.DOUYIN, "abc"): 2.0,
        (PlatformEnum.BILIBILI, "777"): 0.5,
    }


@pytest.mark.parametrize(
    "raw",
    [
        "bilibili",
        "bilibili:123456",
        "bilibili::1.25",
        "bilibili:123456:",
        "bilibili:123456:x",
        "bilibili:123456:1.25:9",
        "nosuchplatform:1:1.25",
    ],
)
def test_malformed_rule_is_rejected(raw):
    with pytest.raises(ValueError, match="变速规则"):
        parse_media_speedup_rules([raw])


def test_later_rule_wins_and_ratio_is_not_capped():
    rules = parse_media_speedup_rules(["bilibili:1:1.2", "bilibili:1:1.5", "bilibili:1:100"])
    assert rules[(PlatformEnum.BILIBILI, "1")] == 100.0


# --------------------------------------------------------------------------
# 写到内容上


@pytest.mark.asyncio
async def test_rule_matches_platform_and_author(tmp_path, monkeypatch):
    monkeypatch.setattr(
        support.pconfig, "plite_media_speedup_rules", ["bilibili:123456:1.5"]
    )
    video = make_media(VideoContent, tmp_path, "v.mp4")
    audio = make_media(AudioContent, tmp_path, "a.mp3")
    apply_media_speedup(make_result(contents=[video, audio]))
    assert (video.speedup, audio.speedup) == (1.5, 1.5)


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


# --------------------------------------------------------------------------
# 展示换算


@pytest.mark.parametrize("cls", [VideoContent, AudioContent])
def test_display_duration_divides_the_speedup(cls, tmp_path):
    cont = make_media(cls, tmp_path, "m.mp4", duration=120.0)
    assert cont.display_duration == "2:00"
    cont.speedup = 2.0
    assert cont.display_duration == "1:00"
    assert cont.duration == 120.0, "时长要由倍速换算，不能就地改写"


@pytest.mark.parametrize("cls", [VideoContent, AudioContent])
def test_display_size_is_marked_as_an_estimate(cls, tmp_path):
    cont = make_media(cls, tmp_path, "m.mp4", duration=120.0)
    cont._size_bytes = 2048
    assert asyncio.run(cont.get_display_size()) == "2.00KB"
    cont.speedup = 2.0
    assert asyncio.run(cont.get_display_size()) == "~1.00KB"


def test_digest_keeps_the_plain_speed(tmp_path):
    """1 倍速也要写进摘要，键的构成才不随命中与否变化"""
    cont = make_media(VideoContent, tmp_path, "v.mp4")
    assert speedup_digest(make_result(contents=[cont])) == "1.00x"
    cont.speedup = 1.25
    assert speedup_digest(make_result(contents=[cont])) == "1.25x"


# --------------------------------------------------------------------------
# get_path 是唯一的执行点


@pytest.mark.asyncio
async def test_get_path_returns_source_when_no_speedup(tmp_path, monkeypatch):
    async def always(cls):
        return True

    called: list[int] = []

    async def spy(cls, *args, **kwargs):
        called.append(1)
        return AnyPath(tmp_path / "product.mp4")

    # 把 ffmpeg 说成可用，才能证明「不变速就直接发原片」是倍速判断挡住的
    monkeypatch.setattr(FFmpeg, "is_available", classmethod(always))
    monkeypatch.setattr(FFmpeg, "edit_video", classmethod(spy))

    cont = make_media(VideoContent, tmp_path, "video.mp4")
    assert await cont.get_path() == await cont.path_task
    assert called == []


@pytest.mark.asyncio
async def test_get_path_returns_the_sped_up_product(tmp_path, monkeypatch):
    async def always(cls):
        return True

    seen: dict[str, object] = {}

    async def spy(cls, input_path, **kwargs):
        seen.update(kwargs, input_path=input_path)
        product = tmp_path / "product.mp4"
        product.write_bytes(b"edited")
        return AnyPath(product)

    monkeypatch.setattr(FFmpeg, "is_available", classmethod(always))
    monkeypatch.setattr(FFmpeg, "edit_video", classmethod(spy))
    cont = make_media(VideoContent, tmp_path, "video.mp4")
    cont.speedup = 1.25
    source = await cont.path_task
    assert str(await cont.get_path()) == str(tmp_path / "product.mp4")
    assert seen["input_path"] == source
    assert seen["speed_ratio"] == 1.25


@pytest.mark.asyncio
async def test_audio_speedup_routes_to_the_audio_editor(tmp_path, monkeypatch):
    async def always(cls):
        return True

    async def video_editor(cls, *args, **kwargs):
        raise AssertionError("音频不该走视频编辑器")

    async def audio_editor(cls, input_path, **kwargs):
        return AnyPath(tmp_path / "product.mp3")

    monkeypatch.setattr(FFmpeg, "is_available", classmethod(always))
    monkeypatch.setattr(FFmpeg, "edit_video", classmethod(video_editor))
    monkeypatch.setattr(FFmpeg, "edit_audio", classmethod(audio_editor))

    cont = make_media(AudioContent, tmp_path, "audio.mp3")
    cont.speedup = 1.5
    assert str(await cont.get_path()) == str(tmp_path / "product.mp3")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RuntimeError("ffmpeg 执行失败"), SizeLimitException(120.0)]
)
async def test_failure_falls_back_to_source_and_drops_speedup(
    tmp_path, monkeypatch, error
):
    async def always(cls):
        return True

    async def failing(cls, *args, **kwargs):
        raise error

    monkeypatch.setattr(FFmpeg, "is_available", classmethod(always))
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
    async def never(cls):
        return False

    called: list[int] = []

    async def spy(cls, *args, **kwargs):
        called.append(1)
        return AnyPath(tmp_path / "product.mp4")

    monkeypatch.setattr(FFmpeg, "is_available", classmethod(never))
    monkeypatch.setattr(FFmpeg, "edit_video", classmethod(spy))

    cont = make_media(VideoContent, tmp_path, "video.mp4")
    cont.speedup = 1.25
    assert await cont.get_path() == await cont.path_task
    assert called == [], "缺 ffmpeg 时不该调用转码"
    assert cont.speedup == 1.0


# --------------------------------------------------------------------------
# 发送与卡片


def capture_segments(monkeypatch) -> list:
    seen: list = []

    async def img_seg(file):
        from nonebot_plugin_alconna.uniseg import Image

        return Image(raw=b"cover")

    async def video_seg(file, thumbnail=None):
        from nonebot_plugin_alconna.uniseg import Video

        seen.append(file)
        return Video(raw=b"video")

    async def file_seg(file, display_name=None):
        from nonebot_plugin_alconna.uniseg import File

        seen.append(file)
        return File(raw=b"video", name=display_name or "video.mp4")

    def construct(segments, user_id=None):
        from nonebot_plugin_alconna.uniseg import Reference

        return Reference(nodes=[])

    monkeypatch.setattr(support.UniHelper, "construct_forward_message", construct)
    monkeypatch.setattr(support.UniHelper, "img_seg", img_seg)
    monkeypatch.setattr(support.UniHelper, "video_seg", video_seg)
    monkeypatch.setattr(support.UniHelper, "file_seg", file_seg)
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize("need_upload", [False, True])
@pytest.mark.parametrize("in_forward", [False, True])
async def test_send_content_uses_the_sped_up_product(
    monkeypatch, tmp_path, need_upload, in_forward
):
    monkeypatch.setattr(support.pconfig, "plite_need_upload_video", need_upload)
    monkeypatch.setattr(support.pconfig, "plite_need_upload", False)
    monkeypatch.setattr(support.pconfig, "plite_video_in_forward", in_forward)
    monkeypatch.setattr(support.pconfig, "plite_need_forward_contents", False)

    async def always(cls):
        return True

    async def fake_retime(cls, input_path, **kwargs):
        product = tmp_path / "product.mp4"
        product.write_bytes(b"edited")
        return AnyPath(product)

    monkeypatch.setattr(FFmpeg, "is_available", classmethod(always))
    monkeypatch.setattr(FFmpeg, "edit_video", classmethod(fake_retime))

    seen = capture_segments(monkeypatch)
    cont = make_media(VideoContent, tmp_path, "video.mp4")
    cont.speedup = 1.25
    result = make_result(contents=[cont])

    messages = [message async for message in support.Renderer().send_content(result)]
    assert messages, "视频消息应当被产出"
    assert [str(path) for path in seen] == [str(tmp_path / "product.mp4")], (
        "消息段必须使用处理后的产物，而不是原片"
    )


@pytest.mark.asyncio
async def test_send_content_falls_back_to_source_when_ffmpeg_is_missing(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(support.pconfig, "plite_need_upload_video", False)
    monkeypatch.setattr(support.pconfig, "plite_need_upload", False)
    monkeypatch.setattr(support.pconfig, "plite_video_in_forward", False)
    monkeypatch.setattr(support.pconfig, "plite_need_forward_contents", False)

    async def never(cls):
        return False

    monkeypatch.setattr(FFmpeg, "is_available", classmethod(never))

    seen = capture_segments(monkeypatch)
    cont = make_media(VideoContent, tmp_path, "video.mp4")
    cont.speedup = 1.25
    result = make_result(contents=[cont])

    async for _ in support.Renderer().send_content(result):
        pass
    assert [str(path) for path in seen] == [str(await cont.path_task)]


@pytest.mark.asyncio
async def test_card_cache_key_changes_with_the_speedup(monkeypatch, tmp_path):
    """卡片是按倍速换算出来的时长渲染的，倍速变了就必须换一张卡

    持久化的卡片缓存跨重启复用，键里若没有倍速标记，改了配置后老卡片会一直显示
    旧时长。
    """
    renders: list = []

    async def fake_render_image(self, result, **kwargs):
        renders.append(speedup_digest(result))
        return tmp_path / "raw.png"

    async def fake_compress(path):
        return b"IMAGE"

    render_dir = tmp_path / "render"

    async def fake_ensure_dir(cache_type=CacheManager.MEDIA):
        render_dir.mkdir(parents=True, exist_ok=True)
        return AnyPath(render_dir)

    monkeypatch.setattr(
        type(support.Renderer()), "render_image", fake_render_image, raising=True
    )
    monkeypatch.setattr(FFmpeg, "png_to_webp", staticmethod(fake_compress))
    monkeypatch.setattr(
        CacheManager,
        "ensure_dir",
        classmethod(
            lambda cls, cache_type=CacheManager.MEDIA: fake_ensure_dir(cache_type)
        ),
    )

    cont = make_media(VideoContent, tmp_path, "video.mp4")
    cont.speedup = 1.25
    result = make_result(contents=[cont])

    await support.Renderer().cache_or_render_image(result)
    await support.Renderer().cache_or_render_image(result)
    assert len(renders) == 1, "同一倍速应命中卡片缓存"

    cont.speedup = 1.5
    await support.Renderer().cache_or_render_image(result)
    assert len(renders) == 2, "倍速变化后必须重渲染卡片"

    cont.speedup = 1.0
    await support.Renderer().cache_or_render_image(result)
    assert len(renders) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", [VideoContent, AudioContent])
async def test_card_shows_a_speedup_label_next_to_the_duration(cls, tmp_path):
    """时长换算后看不出被加速过，卡片要单独给出倍速标签"""
    cont = make_media(cls, tmp_path, "m.mp4", duration=120.0)
    cont._size_bytes = 2048
    result = make_result(contents=[cont])

    async def card_data():
        return await support.build_theme_data(
            result,
            color_scheme="dark",
            theme_id="default",
            bot_name="bot",
            max_comments=5,
            append_qrcode=False,
        )

    cont.speedup = 1.25
    item = (await card_data())["post"]["content"][0]
    assert item["duration"] == "1:36"
    assert item["speedup"] == "1.25x"

    cont.speedup = 1.0
    assert (await card_data())["post"]["content"][0]["speedup"] is None

    cont.speedup = 1.25
    manager = ThemeManager(ROOT / "src/nonebot_plugin_parser_lite/render/templates", [])
    selected = await (await manager.resolve("default")).resolve_template("bilibili")
    env = Environment(
        loader=FileSystemLoader(str(selected.root)), enable_async=True, autoescape=False
    )
    html = await env.get_template(selected.name).render_async(data=await card_data())
    assert "<span>1:36</span>" in html
    assert "<span>1.25x</span>" in html
