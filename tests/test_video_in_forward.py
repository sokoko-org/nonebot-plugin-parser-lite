from nonebot_plugin_alconna.uniseg import File, Image, Reference, Video
import pytest
from render_test_support import (
    ForwardNodeInner,
    Renderer,
    UniHelper,
    make_result,
    pconfig,
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
async def test_video_is_sent_separately_by_default(monkeypatch, fake_media_segments):
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
async def test_uploaded_video_is_appended_as_file(monkeypatch, fake_media_segments):
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
