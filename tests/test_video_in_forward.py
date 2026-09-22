from collections.abc import Iterator
from pathlib import Path as SyncPath
import sys
import tempfile
from types import ModuleType
from typing import Any

import nonebot
import pytest

ROOT = SyncPath(__file__).parents[1]
SOURCE = ROOT / "src" / "nonebot_plugin_parser_lite"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# Load render as a unit under test without running the plugin entrypoint or
# requiring localstore/htmlrender to initialize their application state.
nonebot.init()
_store_tempdir = tempfile.TemporaryDirectory(prefix="parser-lite-render-test-")
store_root = SyncPath(_store_tempdir.name)
localstore = ModuleType("nonebot_plugin_localstore")
localstore.get_plugin_cache_dir = lambda: store_root / "cache"  # type: ignore[attr-defined]
localstore.get_plugin_config_dir = lambda: store_root / "config"  # type: ignore[attr-defined]
localstore.get_plugin_data_dir = lambda: store_root / "data"  # type: ignore[attr-defined]
sys.modules[localstore.__name__] = localstore

htmlrender = ModuleType("nonebot_plugin_htmlrender")
htmlrender.get_new_page = None  # type: ignore[attr-defined]
sys.modules[htmlrender.__name__] = htmlrender

parser_package = ModuleType("nonebot_plugin_parser_lite")
parser_package.__path__ = [str(SOURCE)]
parser_package.__package__ = parser_package.__name__
sys.modules[parser_package.__name__] = parser_package

from nonebot_plugin_alconna.uniseg import File, Image, Reference, Video

from nonebot_plugin_parser_lite.config import pconfig
from nonebot_plugin_parser_lite.constants import PlatformEnum
from nonebot_plugin_parser_lite.data import Author, ParseResult, Platform, VideoContent
from nonebot_plugin_parser_lite.helper import ForwardNodeInner, UniHelper
from nonebot_plugin_parser_lite.render import Renderer


class ResolvedPathTask:
    def __init__(self, path: SyncPath):
        self.path = path
        self.url = str(path)
        self.ext_headers = {}
        self.use_curl_cffi = False

    def __await__(self) -> Iterator[Any]:
        async def resolve() -> SyncPath:
            return self.path

        return resolve().__await__()


def make_result() -> ParseResult:
    video = VideoContent(
        path_task=ResolvedPathTask(SyncPath("video.mp4")),  # type: ignore[arg-type]
        cover=ResolvedPathTask(SyncPath("cover.png")),  # type: ignore[arg-type]
    )
    return ParseResult(
        platform=Platform(PlatformEnum.BILIBILI, "哔哩哔哩"),
        author=Author("tester"),
        url="https://example.com/video",
        content=[video],
    )


@pytest.fixture
def fake_media_segments(monkeypatch):
    async def image_segment(file):
        return Image(raw=b"cover")

    async def video_segment(file, thumbnail=None):
        return Video(raw=b"video")

    async def file_segment(file, display_name=None):
        return File(raw=b"video", name=display_name or "video.mp4")

    monkeypatch.setattr(UniHelper, "img_seg", image_segment)
    monkeypatch.setattr(UniHelper, "video_seg", video_segment)
    monkeypatch.setattr(UniHelper, "file_seg", file_segment)


def capture_forward_nodes(monkeypatch) -> list[list[ForwardNodeInner]]:
    captured: list[list[ForwardNodeInner]] = []

    def construct(segments: list[ForwardNodeInner], user_id=None):
        captured.append(list(segments))
        return Reference(nodes=[])

    monkeypatch.setattr(UniHelper, "construct_forward_message", construct)
    return captured


@pytest.mark.asyncio
async def test_video_is_sent_separately_by_default(
    monkeypatch, fake_media_segments
):
    result = make_result()
    captured = capture_forward_nodes(monkeypatch)
    monkeypatch.setattr(pconfig, "plite_video_in_forward", False)
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", True)
    monkeypatch.setattr(pconfig, "plite_need_upload", False)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", False)

    messages = [message async for message in Renderer().send_content(result)]

    assert len(messages) == 2
    assert any(isinstance(segment, Video) for segment in messages[0])
    assert len(captured) == 1
    assert len(captured[0]) == 1
    assert isinstance(captured[0][0], Image)


@pytest.mark.asyncio
async def test_video_is_appended_after_cover_in_forward(
    monkeypatch, fake_media_segments
):
    result = make_result()
    captured = capture_forward_nodes(monkeypatch)
    monkeypatch.setattr(pconfig, "plite_video_in_forward", True)
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", False)
    monkeypatch.setattr(pconfig, "plite_need_upload", False)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", False)

    messages = [message async for message in Renderer().send_content(result)]

    assert len(messages) == 1
    assert len(captured) == 1
    assert len(captured[0]) == 2
    assert isinstance(captured[0][0], Image)
    assert isinstance(captured[0][1], Video)


@pytest.mark.asyncio
async def test_uploaded_video_is_appended_as_file(
    monkeypatch, fake_media_segments
):
    result = make_result()
    captured = capture_forward_nodes(monkeypatch)
    monkeypatch.setattr(pconfig, "plite_video_in_forward", True)
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", False)
    monkeypatch.setattr(pconfig, "plite_need_upload", False)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", True)

    messages = [message async for message in Renderer().send_content(result)]

    assert len(messages) == 1
    assert len(captured) == 1
    assert len(captured[0]) == 2
    assert isinstance(captured[0][0], Image)
    assert isinstance(captured[0][1], File)
