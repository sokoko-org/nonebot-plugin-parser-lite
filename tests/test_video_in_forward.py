import asyncio
from collections.abc import Iterator
from pathlib import Path as SyncPath
from typing import Any

from anyio import Path
import nonebot

nonebot.init()
assert nonebot.load_plugin("nonebot_plugin_parser_lite") is not None

from nonebot_plugin_alconna.uniseg import File, Image, Text, Video

from nonebot_plugin_parser_lite.config import pconfig
from nonebot_plugin_parser_lite.constants import PlatformEnum
from nonebot_plugin_parser_lite.data import Author, ParseResult, Platform, VideoContent
from nonebot_plugin_parser_lite.helper import ForwardNodeInner, UniHelper
from nonebot_plugin_parser_lite.render import Renderer


class ResolvedPathTask:
    def __init__(self, path: Path):
        self.path = path

    def __await__(self) -> Iterator[Any]:
        async def resolve() -> Path:
            return self.path

        return resolve().__await__()


def make_result(tmp_path: SyncPath) -> ParseResult:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    cover_path = tmp_path / "cover.png"
    cover_path.write_bytes(b"cover")
    video = VideoContent(
        path_task=ResolvedPathTask(Path(video_path)),  # type: ignore[arg-type]
        cover=ResolvedPathTask(Path(cover_path)),  # type: ignore[arg-type]
    )
    return ParseResult(
        platform=Platform(PlatformEnum.BILIBILI, "哔哩哔哩"),
        author=Author("tester"),
        url="https://example.com/video",
        content=[video],
    )


def capture_forward_nodes(monkeypatch) -> list[list[ForwardNodeInner]]:
    captured: list[list[ForwardNodeInner]] = []

    def construct(segments: list[ForwardNodeInner], user_id=None):
        captured.append(list(segments))
        return Text("forward")

    monkeypatch.setattr(UniHelper, "construct_forward_message", construct)
    return captured


async def collect_messages(result: ParseResult):
    return [message async for message in Renderer().send_content(result)]


def test_video_is_sent_separately_by_default(tmp_path, monkeypatch):
    result = make_result(tmp_path)
    captured = capture_forward_nodes(monkeypatch)
    monkeypatch.setattr(pconfig, "plite_video_in_forward", False)
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", True)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", False)

    messages = asyncio.run(collect_messages(result))

    assert len(messages) == 2
    assert any(isinstance(segment, Video) for segment in messages[0])
    assert len(captured) == 1
    assert len(captured[0]) == 1
    assert isinstance(captured[0][0], Image)


def test_video_is_appended_after_cover_in_forward(tmp_path, monkeypatch):
    result = make_result(tmp_path)
    captured = capture_forward_nodes(monkeypatch)
    monkeypatch.setattr(pconfig, "plite_video_in_forward", True)
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", False)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", False)

    messages = asyncio.run(collect_messages(result))

    assert len(messages) == 1
    assert len(captured) == 1
    assert len(captured[0]) == 2
    assert isinstance(captured[0][0], Image)
    assert isinstance(captured[0][1], Video)


def test_uploaded_video_is_appended_as_file(tmp_path, monkeypatch):
    result = make_result(tmp_path)
    captured = capture_forward_nodes(monkeypatch)
    monkeypatch.setattr(pconfig, "plite_video_in_forward", True)
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", False)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", True)

    messages = asyncio.run(collect_messages(result))

    assert len(messages) == 1
    assert len(captured) == 1
    assert len(captured[0]) == 2
    assert isinstance(captured[0][0], Image)
    assert isinstance(captured[0][1], File)
