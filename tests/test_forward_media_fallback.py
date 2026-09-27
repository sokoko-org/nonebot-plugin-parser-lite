from copy import deepcopy

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
    send_with_media_fallback,
)


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
        texts.append(node.content.extract_plain_text())
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
    assert f"{label}未能发送" in text
    assert text.index("前文") < text.index("说明文字") < text.index("后文")
    assert "作品标题" in text
    assert "作者：tester" in text
    assert result.url in text
    assert result.repost.url in text
    assert message == original
    assert result.content[0].need_send
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
    assert "图片未能发送" in text_of(calls[2])
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
async def test_summary_and_video_from_renderer_fall_back_inside_forward(monkeypatch):
    result = make_result()
    result.title = "实际渲染路径"
    monkeypatch.setattr(pconfig, "plite_video_in_forward", True)
    monkeypatch.setattr(pconfig, "plite_need_upload_video", False)
    monkeypatch.setattr(pconfig, "plite_need_upload", False)

    async def image_segment(file):
        return Image(raw=b"image")

    async def video_segment(file, thumbnail=None):
        return Video(raw=b"video")

    monkeypatch.setattr(UniHelper, "img_seg", image_segment)
    monkeypatch.setattr(UniHelper, "video_seg", video_segment)
    monkeypatch.setattr(
        UniHelper, "construct_forward_message", lambda segments: forward(*segments)[0]
    )
    calls = []

    async def send(message, **kwargs):
        calls.append(message)
        if len(calls) == 1:
            raise UploadFailed()

    monkeypatch.setattr(UniMessage, "send", send)
    summary = UniMessage(Image(raw=b"summary")) + result.display_url
    async for message in Renderer().send_content(result, summary_node=summary):
        await send_with_media_fallback(message, result)
    assert len(calls) == 2
    text = text_of(calls[1])
    assert "实际渲染路径" in text
    assert result.url in text
    assert "图片未能发送" in text
    assert "视频未能发送" in text


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
