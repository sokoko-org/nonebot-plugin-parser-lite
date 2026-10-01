from nonebot_plugin_alconna.uniseg import Image, Reference, UniMessage, Video
import pytest
from render_test_support import Renderer, UniHelper, make_result, pconfig

from nonebot_plugin_parser_lite.data import ImageContent, QuoteContent
from nonebot_plugin_parser_lite.delivery import build_text_fallback
from nonebot_plugin_parser_lite.utils.message import MAX_FORWARD_TEXT_LEN, split_message


@pytest.fixture
def message_layout(monkeypatch):
    construct = UniHelper.construct_forward_message
    monkeypatch.setattr(
        UniHelper,
        "construct_forward_message",
        lambda segments: construct(segments, user_id="123"),
    )
    monkeypatch.setattr(pconfig, "plite_video_in_forward", False)


def contents(message):
    if isinstance(message[0], Reference):
        return [UniMessage(node.content) for node in message[0].children]
    return [message]


@pytest.mark.asyncio
@pytest.mark.parametrize("forward", [True, False])
async def test_title_and_repost_boundaries(message_layout, monkeypatch, forward):
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", forward)
    result = make_result()
    result.title = "标题"
    result.content = ["正文"]
    result.repost = make_result()
    result.repost.content = ["原文"]
    messages = [msg async for msg in Renderer().send_content(result)]
    assert len(messages) == 1
    texts = [msg.extract_plain_text() for msg in contents(messages[0])]
    if forward:
        assert texts == ["标题", "tester：正文", ">>>>>原帖<<<<<", "tester：原文"]
    else:
        assert texts == ["标题\ntester：正文\n>>>>>原帖<<<<<\ntester：原文"]


@pytest.mark.asyncio
@pytest.mark.parametrize("forward", [True, False])
async def test_quote_preserves_source_blank_lines(message_layout, monkeypatch, forward):
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", forward)
    result = make_result()
    result.content = ["正文\n\n", QuoteContent(text="引用"), "\n\n后文"]
    messages = [msg async for msg in Renderer().send_content(result)]
    assert [msg.extract_plain_text() for msg in contents(messages[0])] == [
        "tester：正文\n\n引用\n\n后文"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("forward", [True, False])
async def test_quote_adds_only_required_separators(
    message_layout, monkeypatch, forward
):
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", forward)
    result = make_result()
    result.content = ["正文", QuoteContent(text="引用"), "后文"]
    messages = [msg async for msg in Renderer().send_content(result)]
    assert contents(messages[0])[0].extract_plain_text() == "tester：正文\n引用\n后文"


@pytest.mark.asyncio
@pytest.mark.parametrize("forward", [True, False])
async def test_blank_media_gaps_do_not_consume_author_or_force_forward(
    message_layout, monkeypatch, forward
):
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", forward)
    image = make_result().content[0].cover
    result = make_result()
    result.content = [
        "\n",
        ImageContent(path_task=image),
        "\n\n",
        ImageContent(path_task=image),
        "正文",
    ]

    async def image_segment(file):
        return Image(raw=b"image")

    monkeypatch.setattr(UniHelper, "img_seg", image_segment)
    messages = [msg async for msg in Renderer().send_content(result)]
    assert len(messages) == 1
    assert isinstance(messages[0][0], Reference) is forward
    texts = [msg.extract_plain_text() for msg in contents(messages[0])]
    if forward:
        assert texts == ["", "", "tester：正文"]
    else:
        assert texts == ["\n\n\ntester：正文"]


@pytest.mark.asyncio
async def test_title_at_threshold_does_not_create_blank_node(
    message_layout, monkeypatch
):
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", True)
    monkeypatch.setattr("nonebot_plugin_parser_lite.render.SPLIT_THRESHOLD", 8)
    result = make_result()
    result.title = "标题" * 4
    result.content = []
    messages = [msg async for msg in Renderer().send_content(result)]
    assert [msg.extract_plain_text() for msg in contents(messages[0])] == [result.title]


@pytest.mark.asyncio
async def test_split_quote_uses_node_boundary(message_layout, monkeypatch):
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", True)
    monkeypatch.setattr("nonebot_plugin_parser_lite.render.SPLIT_THRESHOLD", 8)
    result = make_result()
    result.content = ["a", QuoteContent(text="引用"), "后文"]
    messages = [msg async for msg in Renderer().send_content(result)]
    assert [msg.extract_plain_text() for msg in contents(messages[0])] == [
        "tester：a",
        "引用\n后文",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("forward", [True, False])
async def test_whitespace_only_content_is_not_sent(
    message_layout, monkeypatch, forward
):
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", forward)
    result = make_result()
    result.content = ["", "\n\n", " "]
    assert [msg async for msg in Renderer().send_content(result)] == []


def test_split_retains_original_trailing_blank_lines():
    text = "abcdefgh\n\n"
    pieces = [msg.extract_plain_text() for msg in split_message(text, 8)]
    assert all(piece.strip() for piece in pieces)
    assert all(len(piece) <= MAX_FORWARD_TEXT_LEN for piece in pieces)
    assert "".join(pieces) == text


@pytest.mark.parametrize("mixed", [True, False])
def test_fallback_notices_use_content_boundaries(mixed):
    result = make_result()
    body = UniMessage([Video(raw=b"v"), Image(raw=b"i")])
    if mixed:
        body = "前文\n\n" + body + "\n\n后文"
    message = UniMessage(UniHelper.construct_forward_message([body], user_id="123"))
    packets = build_text_fallback(message, result)
    texts = [msg.extract_plain_text() for msg in contents(packets[0])]
    notices = "[视频已省略，请通过原链接查看]\n[图片已省略，请通过原链接查看]"
    assert texts[-1] == ("前文\n\n" + notices + "\n\n后文" if mixed else notices)


@pytest.mark.parametrize(
    "text", ["\n" * 8 + "abc", "abc" + "\n" * 8, "a" + "\n" * 40 + "b"]
)
def test_long_original_whitespace_is_preserved(text):
    messages = split_message(text, 8, 32)
    assert "".join(msg.extract_plain_text() for msg in messages) == text
    assert all(len(msg.extract_plain_text()) <= 32 for msg in messages)


def test_protected_block_keeps_trailing_source_whitespace():
    from nonebot_plugin_parser_lite.utils.message import MessageText, TextPart

    content = MessageText(
        "",
        [TextPart("12345678", block=True, keep_together=True), TextPart("\n")],
        False,
    )
    messages = split_message(content.to_message(), 8)
    assert [msg.extract_plain_text() for msg in messages] == ["12345678\n"]


@pytest.mark.asyncio
@pytest.mark.parametrize("threshold", [1000, 50000])
async def test_oversized_quote_obeys_platform_hard_limit(
    message_layout, monkeypatch, threshold
):
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", True)
    monkeypatch.setattr("nonebot_plugin_parser_lite.render.SPLIT_THRESHOLD", threshold)
    result = make_result()
    result.content = [QuoteContent(text="引用" * 16000)]
    messages = [msg async for msg in Renderer().send_content(result)]
    nodes = [node for packet in messages for node in packet[0].children]
    assert (
        "".join(node.content.extract_plain_text() for node in nodes)
        == "tester：" + "引用" * 16000
    )
    for packet in messages:
        assert len(packet[0].children) <= 90
        assert (
            sum(len(node.content.extract_plain_text()) for node in packet[0].children)
            <= 30000
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("forward", [True, False])
async def test_poll_image_and_text_positions(message_layout, monkeypatch, forward):
    from render_test_support import ResolvedPathTask, SyncPath

    from nonebot_plugin_parser_lite.data import PollContent, PollOption

    monkeypatch.setattr(pconfig, "plite_need_forward_contents", forward)
    poll = PollContent(
        title="选择",
        options=[
            PollOption("A", image=ResolvedPathTask(SyncPath("a.png"))),
            PollOption("B", image=ResolvedPathTask(SyncPath("b.png"))),
        ],
    )

    async def image_segment(file):
        return Image(raw=str(file).encode())

    monkeypatch.setattr(UniHelper, "img_seg", image_segment)
    result = make_result()
    result.content = ["前文\n\n", poll, "\n\n后文"]
    messages = [msg async for msg in Renderer().send_content(result)]
    segments = [segment for node in contents(messages[0]) for segment in node]
    images = [i for i, segment in enumerate(segments) if isinstance(segment, Image)]
    assert len(images) == 2
    assert segments[images[0]].raw == b"a.png"
    assert segments[images[1]].raw == b"b.png"
    assert (
        "".join(segment.text for segment in segments[: images[0]]) == "tester：前文\n\n"
    )
    after = "".join(segment.text for segment in segments[images[1] + 1 :])
    assert after.startswith("【投票】选择\n")
    assert after.endswith("进行中\n\n后文")


@pytest.mark.asyncio
async def test_fallback_preserves_quote_block_policy(message_layout, monkeypatch):
    monkeypatch.setattr(pconfig, "plite_need_forward_contents", True)
    monkeypatch.setattr("nonebot_plugin_parser_lite.render.SPLIT_THRESHOLD", 8)
    monkeypatch.setattr("nonebot_plugin_parser_lite.delivery.SPLIT_THRESHOLD", 8)
    result = make_result()
    result.content = [QuoteContent(text="引用" * 10), "\n"]
    messages = [msg async for msg in Renderer().send_content(result)]
    message = messages[0]
    node = message[0].children[0]
    node.content.append(Image(raw=b"i"))
    fallback = build_text_fallback(message, result)
    nodes = [node for packet in fallback for node in packet[0].children]
    quote_nodes = [
        node for node in nodes if "引用" in node.content.extract_plain_text()
    ]
    assert len(quote_nodes) == 1
    assert "引用" * 10 + "\n" in quote_nodes[0].content.extract_plain_text()


def test_text_styles_survive_common_splitter():
    from nonebot_plugin_alconna.uniseg import Text

    source = UniMessage(Text("abcdefgh", {(2, 7): ["bold"]}))
    pieces = split_message(source, 4, 8)
    assert [piece[0].styles for piece in pieces] == [
        {(2, 4): ["bold"]},
        {(0, 3): ["bold"]},
    ]
    assert source[0].text == "abcdefgh"
    assert source[0].styles == {(2, 7): ["bold"]}


def test_overlapping_styles_are_combined_after_clipping():
    from nonebot_plugin_alconna.uniseg import Text

    source = UniMessage(Text("abcdefgh", {(0, 8): ["bold"], (1, 7): ["italic"]}))
    pieces = split_message(source, 2, 8)
    assert pieces[1][0].text == "cd"
    assert pieces[1][0].styles == {(0, 2): ["bold", "italic"]}
    assert pieces[2][0].styles == {(0, 2): ["bold", "italic"]}
    assert source[0].styles == {(0, 8): ["bold"], (1, 7): ["italic"]}


@pytest.mark.parametrize("soft", [1, 3, 8])
def test_splitter_conserves_original_text_under_small_hard_limit(soft):
    from itertools import product

    for prefix, gap, suffix in product(
        ["", "a。", "abcdefghi"], ["", "\n", "\n" * 20, "   "], ["", "尾", "xyz"]
    ):
        source = prefix + gap + suffix
        messages = split_message(source, soft, 16)
        assert "".join(message.extract_plain_text() for message in messages) == source
        assert all(len(message.extract_plain_text()) <= 16 for message in messages)
