from anyio import Path
from nonebot_plugin_alconna.uniseg import Reference, Text, UniMessage
import pytest
from render_test_support import Renderer, UniHelper, pconfig

from nonebot_plugin_parser_lite.constants import PlatformEnum
from nonebot_plugin_parser_lite.data import (
    Author,
    MediaContent,
    ParseResult,
    Platform,
    VideoContent,
)
from nonebot_plugin_parser_lite.download.task import DownloadTaskWrapper
from nonebot_plugin_parser_lite.exception import SizeLimitException

MIB = 1024 * 1024


@pytest.fixture
def media_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(pconfig, "plite_max_size", 1)
    counter = 0

    def make(size, known_size=None):
        nonlocal counter
        counter += 1
        file_path = tmp_path / f"media-{counter}.mp4"
        with file_path.open("wb") as file:
            file.truncate(size)
        path = Path(file_path)
        calls = []

        async def download():
            calls.append(path)
            return path

        task = DownloadTaskWrapper(
            func=download,
            args=(),
            kwargs={},
            url="https://example.com/video.mp4",
        )
        media = MediaContent(path_task=task)
        media._size_bytes = known_size
        return media, path, calls

    return make


@pytest.mark.asyncio
@pytest.mark.parametrize("known_size", [MIB + 1, 2 * MIB])
async def test_known_oversized_media_is_rejected_before_download(
    media_factory, known_size
):
    media, _, calls = media_factory(1, known_size)

    with pytest.raises(SizeLimitException):
        await media.get_path()

    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("known_size", [None, 0, MIB - 1, MIB])
@pytest.mark.parametrize("actual_size", [MIB - 1, MIB, MIB + 1])
async def test_actual_size_enforces_limit_after_download(
    media_factory, known_size, actual_size
):
    media, path, calls = media_factory(actual_size, known_size)

    if actual_size > MIB:
        with pytest.raises(SizeLimitException):
            await media.get_path()
    else:
        assert await media.get_path() == path

    assert calls == [path]
    assert media._size_bytes == actual_size


@pytest.mark.asyncio
async def test_reused_download_task_still_checks_actual_file_size(
    media_factory, tmp_path
):
    media, path, calls = media_factory(MIB)
    assert await media.get_path() == path
    with (tmp_path / path.name).open("wb") as file:
        file.truncate(MIB + 1)

    with pytest.raises(SizeLimitException):
        await media.get_path()

    assert calls == [path]
    assert media._size_bytes == MIB + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("video_in_forward", [False, True])
@pytest.mark.parametrize("with_summary", [False, True])
@pytest.mark.parametrize("known_size", [None, MIB + 1])
async def test_oversized_video_keeps_summary_and_sends_notice(
    media_factory, monkeypatch, video_in_forward, with_summary, known_size
):
    media, path, calls = media_factory(MIB + 1, known_size)
    video = VideoContent(path_task=media.path_task)
    video._size_bytes = known_size
    result = ParseResult(
        platform=Platform(PlatformEnum.BILIBILI, "哔哩哔哩"),
        author=Author("tester"),
        url="https://example.com/video",
        content=[video],
    )
    monkeypatch.setattr(pconfig, "plite_video_in_forward", video_in_forward)
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", False)
    construct = UniHelper.construct_forward_message
    monkeypatch.setattr(
        UniHelper,
        "construct_forward_message",
        lambda segments: construct(segments, user_id="123"),
    )
    summary = UniMessage(Text("summary")) if with_summary else None

    messages = [
        message
        async for message in Renderer().send_content(result, summary_node=summary)
    ]
    assert len(messages) == 1
    contents = (
        [UniMessage(node.content) for node in messages[0][0].children]
        if isinstance(messages[0][0], Reference)
        else messages
    )
    assert all(isinstance(segment, Text) for content in contents for segment in content)
    assert [content.extract_plain_text() for content in contents] == (
        (["summary"] if with_summary else []) + ["媒体太大啦，还是去哔哩哔哩看看吧~"]
    )
    assert calls == ([path] if known_size is None else [])
