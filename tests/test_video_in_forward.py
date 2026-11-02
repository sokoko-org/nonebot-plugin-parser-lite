from nonebot_plugin_alconna.uniseg import (
    File,
    Image,
    Reference,
    Text,
    UniMessage,
    Video,
)
import pytest
from render_test_support import (
    ForwardNodeInner,
    ImageContent,
    LivePhotoContent,
    ParseResult,
    Platform,
    PlatformEnum,
    Renderer,
    ResolvedPathTask,
    UniHelper,
    make_result,
    pconfig,
    set_send_layout,
)


@pytest.fixture
def fake_media_segments(monkeypatch):
    async def image_segment(file):
        return Image(raw=b"cover")

    async def video_segment(file, thumbnail=None):
        return Video(
            raw=b"video",
            thumbnail=Image(raw=b"thumbnail") if thumbnail is not None else None,
        )

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
    set_send_layout(
        monkeypatch, video_in_forward=True, content_in_forward=False
    )
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
    set_send_layout(
        monkeypatch, video_in_forward=True, content_in_forward=False
    )
    monkeypatch.setattr(pconfig, "plite_need_upload", False)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", True)

    messages = [message async for message in Renderer().send_content(result)]

    assert len(messages) == 1
    assert len(captured) == 1
    assert len(captured[0]) == 2
    assert isinstance(captured[0][0], Image)
    assert isinstance(captured[0][1], File)


@pytest.mark.asyncio
async def test_summary_is_first_forward_node(monkeypatch, fake_media_segments):
    result = make_result()
    captured = capture_forward_nodes(monkeypatch)
    summary = UniMessage([Text("summary")])
    set_send_layout(
        monkeypatch, video_in_forward=True, content_in_forward=False
    )
    monkeypatch.setattr(pconfig, "plite_need_upload", False)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", False)

    messages = [
        message
        async for message in Renderer().send_content(result, summary_node=summary)
    ]

    assert len(messages) == 1
    assert len(captured) == 1
    assert captured[0][0] is summary
    assert isinstance(captured[0][1], Image)
    assert isinstance(captured[0][2], Video)


@pytest.mark.asyncio
async def test_summary_forces_forward_and_includes_deferred_video(
    monkeypatch, fake_media_segments
):
    result = make_result()
    captured = capture_forward_nodes(monkeypatch)
    summary = UniMessage([Text("summary")])
    set_send_layout(
        monkeypatch, video_in_forward=False, content_in_forward=False
    )
    monkeypatch.setattr(pconfig, "plite_need_upload", False)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", False)

    messages = [
        message
        async for message in Renderer().send_content(result, summary_node=summary)
    ]

    assert len(messages) == 1
    assert len(captured) == 1
    assert captured[0][0] is summary
    assert isinstance(captured[0][1], Image)
    deferred_video = captured[0][2]
    assert isinstance(deferred_video, UniMessage)
    assert any(isinstance(segment, Video) for segment in deferred_video)


@pytest.mark.asyncio
async def test_summary_keeps_deferred_media_in_content_order(
    monkeypatch, fake_media_segments, tmp_path
):
    result = make_result()
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image")
    result.content.append(ImageContent(ResolvedPathTask(image_path)))  # pyright: ignore[reportArgumentType]
    captured = capture_forward_nodes(monkeypatch)
    summary = UniMessage([Text("summary")])
    set_send_layout(
        monkeypatch, video_in_forward=False, content_in_forward=False
    )
    monkeypatch.setattr(pconfig, "plite_need_upload", False)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", False)

    messages = [
        message
        async for message in Renderer().send_content(result, summary_node=summary)
    ]

    assert len(messages) == 1
    assert len(captured) == 1
    assert captured[0][0] is summary
    assert isinstance(captured[0][1], Image)
    assert isinstance(captured[0][2], UniMessage)
    assert any(isinstance(segment, Video) for segment in captured[0][2])
    assert isinstance(captured[0][3], Image)


@pytest.mark.asyncio
async def test_title_node_has_no_trailing_newline_in_forward(
    monkeypatch, fake_media_segments
):
    result = make_result()
    result.title = "标题"
    result.content.append("正文\n\n   第二段\n")
    result.content.append("\n\n第三段\naa")
    captured = capture_forward_nodes(monkeypatch)
    set_send_layout(
        monkeypatch, video_in_forward=True, content_in_forward=False
    )
    monkeypatch.setattr(pconfig, "plite_need_upload", False)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", False)

    _ = [message async for message in Renderer().send_content(result)]

    assert len(captured) == 1
    assert captured[0][0] == "标题"
    assert isinstance(captured[0][1], Image)
    assert isinstance(captured[0][2], Video)
    assert captured[0][3] == "tester：正文\n\n   第二段\n\n\n第三段\naa"


@pytest.mark.asyncio
async def test_title_is_separated_from_text_in_single_message(
    monkeypatch, fake_media_segments
):
    result = make_result()
    result.title = "标题"
    result.content = ["正文\n\n", "   第二段\ngg"]
    set_send_layout(monkeypatch, video_in_forward=False, content_in_forward=False)

    messages = [message async for message in Renderer().send_content(result)]

    assert len(messages) == 1
    assert messages[0].extract_plain_text() == "标题\ntester：正文\n\n   第二段\ngg"


@pytest.mark.asyncio
async def test_video_thumbnail_dropped_when_cover_disabled(
    monkeypatch, fake_media_segments
):
    result = make_result()
    captured = capture_forward_nodes(monkeypatch)
    set_send_layout(
        monkeypatch, video_in_forward=True, content_in_forward=False, send_cover=False
    )
    monkeypatch.setattr(pconfig, "plite_need_upload", False)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", False)

    _ = [message async for message in Renderer().send_content(result)]

    assert len(captured) == 1
    video_seg = next(seg for seg in captured[0] if isinstance(seg, Video))
    assert video_seg.thumbnail is None


@pytest.mark.asyncio
async def test_live_photo_dropped_from_forward_when_content_disabled(
    monkeypatch, fake_media_segments, tmp_path
):
    base_path = tmp_path / "base.png"
    live_path = tmp_path / "live.mp4"
    base_path.write_bytes(b"base")
    live_path.write_bytes(b"live")
    live_photo = LivePhotoContent(
        path_task=ResolvedPathTask(live_path),  # pyright: ignore[reportArgumentType]
        base_image=ResolvedPathTask(base_path),  # pyright: ignore[reportArgumentType]
        loop=1,
    )
    result = ParseResult(
        platform=Platform(PlatformEnum.BILIBILI, "哔哩哔哩"),
        author=make_result().author,
        url="https://example.com/live",
        content=[live_photo],
    )
    captured = capture_forward_nodes(monkeypatch)
    summary = UniMessage([Text("summary")])
    set_send_layout(monkeypatch, send_content=False)
    monkeypatch.setattr(pconfig, "plite_live_photo", False)

    _ = [
        message
        async for message in Renderer().send_content(result, summary_node=summary)
    ]

    assert len(captured) == 1
    assert captured[0] == [summary]
