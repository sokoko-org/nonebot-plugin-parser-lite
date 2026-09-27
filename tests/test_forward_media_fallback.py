from copy import deepcopy
from types import SimpleNamespace

from anyio import Path
from nonebot.exception import ActionFailed, NetworkError
from nonebot_plugin_alconna.uniseg import (
    Audio,
    CustomNode,
    File,
    Image,
    Reference,
    RefNode,
    Text,
    UniMessage,
    Video,
    Voice,
)
import pytest
from render_test_support import Renderer, UniHelper, make_result, pconfig

from nonebot_plugin_parser_lite import delivery
from nonebot_plugin_parser_lite.delivery import (
    build_text_fallback,
    build_video_fallback,
    send_with_media_fallback,
)
from nonebot_plugin_parser_lite.helper import mark_media_role, media_role


class UploadFailed(ActionFailed):
    def __init__(self, message="HTTP Upload failed with code 102902"):
        super().__init__("test")
        self.message = message
        self.retcode = 500


class OneBotFailed(ActionFailed):
    def __init__(self, wording):
        super().__init__("test")
        self.info = {"retcode": 1200, "wording": wording}


def forward(*contents):
    return UniMessage(
        Reference(
            nodes=[
                CustomNode("42", "bot", content=UniMessage(content))
                for content in contents
            ]
        )
    )


def text_of(message):
    assert len(message) == 1
    assert isinstance(message[0], Reference)
    texts = []
    for node in message[0].children:
        assert isinstance(node, CustomNode)
        assert all(isinstance(segment, Text) for segment in node.content)
        texts.append(node.content.extract_plain_text()) # pyright: ignore[reportAttributeAccessIssue]
    return "\n".join(texts)


@pytest.mark.parametrize(
    ("media", "label"),
    [
        (Image(raw=b"image"), "图片"),
        (Video(raw=b"video"), "视频"),
        (Audio(raw=b"audio"), "音频"),
        (Voice(raw=b"voice"), "语音"),
        (File(raw=b"file", name="video.mp4"), "文件"),
    ],
)
def test_media_replaced_without_losing_text_or_source(media, label, monkeypatch):
    result = make_result()
    result.title = "作品标题"
    result.repost = make_result()
    result.repost.url = "https://example.com/original"
    monkeypatch.setattr(pconfig, "plite_append_url", False)
    message = forward(UniMessage.text("前文") + media + "说明文字", "后文")
    original = deepcopy(message)

    fallback = build_text_fallback(message, result)

    assert len(fallback) == 1
    text = text_of(fallback[0])
    assert f"{label}已省略" in text
    assert text.index("前文") < text.index("说明文字") < text.index("后文")
    assert "作品标题" in text
    assert "作者：tester" in text
    assert result.url in text
    assert result.repost.url in text
    assert message == original
    assert result.content[0].need_send # pyright: ignore[reportAttributeAccessIssue]
    assert all(node.uid == "42" for node in fallback[0][0].children)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        UploadFailed(),
        OneBotFailed("rich media transfer failed"),
        UploadFailed("[Highway] Highway request timeout (11s)"),
    ],
)
async def test_explicit_upload_failure_retries_only_failed_chunk(monkeypatch, error):
    result = make_result()
    messages = [forward("已发送"), forward(Image(raw=b"image")), forward("后续")]
    calls = []

    async def send(message, **kwargs):
        calls.append(deepcopy(message))
        if len(calls) == 3:
            assert kwargs == {"fallback": False}
        if message is messages[1]:
            # 模拟 exporter 修改原消息后才报错。
            message[0].children.clear()
            raise error

    monkeypatch.setattr(UniMessage, "send", send)
    for message in messages:
        await send_with_media_fallback(message, result)

    assert len(calls) == 4
    assert text_of(calls[0]) == "已发送"
    assert "图片已省略" in text_of(calls[2])
    assert text_of(calls[3]) == "后续"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        UploadFailed("permission denied"),
        UploadFailed("request timeout"),
        UploadFailed("retcode=500"),
        UploadFailed("102902"),
        OneBotFailed("请重试"),
        NetworkError("test"),
        RuntimeError("HTTP Upload failed with code 102902"),
    ],
)
async def test_other_failures_are_not_retried(monkeypatch, error):
    calls = []

    async def send(message, **kwargs):
        calls.append(message)
        raise error

    monkeypatch.setattr(UniMessage, "send", send)
    with pytest.raises(type(error)) as caught:
        await send_with_media_fallback(forward(Video(raw=b"video")), make_result())
    assert caught.value is error
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_failed_text_fallback_stops_and_preserves_original_error(monkeypatch):
    original_error = UploadFailed()
    fallback_error = UploadFailed("permission denied")
    calls = []

    async def send(message, **kwargs):
        calls.append(message)
        raise original_error if len(calls) == 1 else fallback_error

    monkeypatch.setattr(UniMessage, "send", send)
    with pytest.raises(UploadFailed) as caught:
        await send_with_media_fallback(forward(Video(raw=b"video")), make_result())
    assert caught.value is fallback_error
    assert fallback_error.__context__ is original_error
    assert len(calls) == 2
    text_of(calls[1])


@pytest.mark.parametrize(
    "message",
    [
        UniMessage(Video(raw=b"video")),
        forward("纯文字"),
        UniMessage(Reference(id="remote")),
        UniMessage(Reference(nodes=[RefNode("remote")])),
    ],
)
def test_ineligible_messages_have_no_fallback(message):
    assert build_text_fallback(message, make_result()) == []


@pytest.mark.parametrize(("repeats", "length"), [(89, 2000), (89, 1)])
def test_notice_and_placeholders_respect_forward_limits(repeats, length):
    message = forward(*(["正文" * length] * repeats), Image(raw=b"image"))
    fallback = build_text_fallback(message, make_result())
    assert len(fallback) > 1
    for packet in fallback:
        text_of(packet)
        assert len(packet[0].children) <= 90
        assert (
            sum(len(n.content.extract_plain_text()) for n in packet[0].children)
            <= 30000
        )
    joined = "".join(text_of(packet) for packet in fallback)
    assert joined.count("正文") == length * repeats


def test_large_configured_split_threshold_cannot_exceed_forward_limit(monkeypatch):
    monkeypatch.setattr(delivery, "SPLIT_THRESHOLD", 50000)
    message = forward("字" * 31000, Image(raw=b"image"))
    packets = build_text_fallback(message, make_result())
    for packet in packets:
        text_of(packet)
        assert (
            sum(len(n.content.extract_plain_text()) for n in packet[0].children)
            <= 30000
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("as_file", "video_in_forward"),
    [(False, True), (True, True), (False, False)],
)
async def test_summary_and_video_from_renderer_fall_back_inside_forward(
    monkeypatch, as_file, video_in_forward
):
    result = make_result()
    result.title = "实际渲染路径"
    monkeypatch.setattr(pconfig, "plite_video_in_forward", video_in_forward)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", as_file)
    monkeypatch.setattr(pconfig, "plite_need_upload", False)

    async def image_segment(file):
        return Image(raw=b"image")

    async def video_segment(file, thumbnail=None):
        return Video(
            raw=b"video",
            thumbnail=Image(raw=b"thumbnail") if thumbnail is not None else None,
        )

    async def file_segment(file, display_name=None):
        return File(raw=b"video", name="video.mp4")

    async def cached_summary(self, result):
        return Image(raw=b"summary")

    monkeypatch.setattr(UniHelper, "img_seg", image_segment)
    monkeypatch.setattr(UniHelper, "video_seg", video_segment)
    monkeypatch.setattr(UniHelper, "file_seg", file_segment)
    monkeypatch.setattr(Renderer, "cache_or_render_image", cached_summary)
    monkeypatch.setattr(pconfig, "plite_append_url", True)
    monkeypatch.setattr(
        UniHelper, "construct_forward_message", lambda segments: forward(*segments)[0]
    )
    calls = []

    async def send(message, **kwargs):
        calls.append(message)
        if len(calls) == 1:
            raise UploadFailed()

    monkeypatch.setattr(UniMessage, "send", send)
    summary = await Renderer().render_messages(result)
    async for message in Renderer().send_content(result, summary_node=summary):
        await send_with_media_fallback(message, result)
    assert len(calls) == 2
    segments = [segment for node in calls[1][0].children for segment in node.content]
    images = [segment for segment in segments if isinstance(segment, Image)]
    assert [image.raw for image in images] == [b"summary", b"image"]
    assert not any(isinstance(segment, Video) for segment in segments)
    assert not any(isinstance(segment, File) for segment in segments)
    text = "".join(segment.text for segment in segments if isinstance(segment, Text))
    assert "实际渲染路径" in text
    assert result.url in text
    assert "图片已省略" not in text
    assert "视频已省略" in text


@pytest.mark.asyncio
async def test_successful_media_forward_is_sent_only_once(monkeypatch):
    message = forward(Image(raw=b"image"), Video(raw=b"video"))
    calls = []

    async def send(outgoing, **kwargs):
        calls.append(outgoing)

    monkeypatch.setattr(UniMessage, "send", send)
    await send_with_media_fallback(message, make_result())
    assert calls == [message]


@pytest.mark.asyncio
async def test_upload_words_in_request_data_do_not_trigger_fallback(monkeypatch):
    error = OneBotFailed("permission denied")
    error.info["data"] = {"message": "HTTP Upload failed with code 102902"}
    calls = []

    async def send(message, **kwargs):
        calls.append(message)
        raise error

    monkeypatch.setattr(UniMessage, "send", send)
    with pytest.raises(OneBotFailed):
        await send_with_media_fallback(forward(Image(raw=b"image")), make_result())
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_video_then_text_fallback_keeps_images_until_second_failure(monkeypatch):
    result = make_result()
    result.title = "作品标题"
    summary = Image(raw=b"summary", name="secret-cache.webp")
    mark_media_role(summary, "summary")
    message = forward(
        UniMessage(summary) + result.display_url,
        result.title,
        Image(raw=b"cover", name="secret-cover.jfif"),
        Video(raw=b"video", name="secret-video.mp4"),
        "tester：正文",
    )
    original = deepcopy(message)
    calls = []

    async def send(outgoing, **kwargs):
        calls.append(deepcopy(outgoing))
        if len(calls) <= 2:
            outgoing[0].children.clear()
            raise UploadFailed()

    monkeypatch.setattr(UniMessage, "send", send)
    await send_with_media_fallback(message, result)
    assert len(calls) == 3
    assert calls[0] == original
    stage_one = [s for n in calls[1][0].children for s in n.content]
    assert sum(isinstance(s, Image) for s in stage_one) == 2
    assert not any(isinstance(s, Video) for s in stage_one)
    text = text_of(calls[2])
    assert text.count(result.title) == 1
    assert text.count(result.url) == 1
    assert text.count("媒体上传失败") == 1
    assert "图片已省略" in text
    assert "视频已省略" in text
    assert "secret-" not in text
    assert "保留其他内容" not in text


def test_video_file_role_preserves_unrelated_files():
    video = File(raw=b"video", name="video.mp4")
    mark_media_role(video, "video")
    attachment = File(raw=b"document", name="ordinary.mp4")
    message = forward(video, attachment, Image(raw=b"image"))
    fallback = build_video_fallback(message, make_result())
    segments = [s for n in fallback[0][0].children for s in n.content]
    assert [s.raw for s in segments if isinstance(s, File)] == [b"document"]
    assert any(isinstance(s, Image) for s in segments)
    assert video in message[0].children[0].content # pyright: ignore[reportAttributeAccessIssue, reportOperatorIssue]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [UploadFailed("permission denied"), NetworkError("test")]
)
async def test_non_media_error_in_video_fallback_stops(monkeypatch, error):
    calls = []

    async def send(message, **kwargs):
        calls.append(message)
        raise UploadFailed() if len(calls) == 1 else error

    monkeypatch.setattr(UniMessage, "send", send)
    with pytest.raises(type(error)) as caught:
        await send_with_media_fallback(
            forward(Image(raw=b"cover"), Video(raw=b"video")), make_result()
        )
    assert caught.value is error
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_split_video_fallback_does_not_resend_successful_packet(monkeypatch):
    monkeypatch.setattr(delivery, "MAX_FORWARD_NODES", 2)
    message = forward(Video(raw=b"video"), Image(raw=b"cover"), "末尾正文")
    calls = []

    async def send(outgoing, **kwargs):
        calls.append(deepcopy(outgoing))
        if len(calls) in {1, 3}:
            raise UploadFailed()

    monkeypatch.setattr(UniMessage, "send", send)
    await send_with_media_fallback(message, make_result())
    # 第一份省略视频的分包成功；第二份才需要变成文字。
    assert "视频已省略" in text_of(calls[1])
    for packet in calls[3:]:
        assert "视频已省略" not in text_of(packet)
    assert any("末尾正文" in text_of(packet) for packet in calls[3:])


@pytest.mark.asyncio
async def test_large_video_file_keeps_origin_without_exporting_metadata(monkeypatch):
    async def stat(path):
        return SimpleNamespace(st_size=101 * 1024 * 1024)

    monkeypatch.setattr(Path, "stat", stat)
    monkeypatch.setattr(pconfig, "plite_use_base64", False)
    segment = await UniHelper.video_seg(Path("large-live-photo.mp4"))
    assert isinstance(segment, File)
    assert media_role(deepcopy(segment)) == "video"
    assert "_parser_lite_media_role" not in segment.data
    assert "_parser_lite_media_role" not in segment.dump()


@pytest.mark.asyncio
async def test_third_media_error_is_terminal(monkeypatch):
    calls = []

    async def send(message, **kwargs):
        calls.append(deepcopy(message))
        raise UploadFailed()

    monkeypatch.setattr(UniMessage, "send", send)
    with pytest.raises(UploadFailed):
        await send_with_media_fallback(
            forward(Image(raw=b"cover"), Video(raw=b"video")), make_result()
        )
    assert len(calls) == 3
    text_of(calls[-1])
