"""空降查询、时间轴规则，以及整片标签与跳过区间的下载行为"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import render_test_support as support

from nonebot_plugin_parser_lite.parsers import bilibili
from nonebot_plugin_parser_lite.parsers.bilibili import sponsorblock
from nonebot_plugin_parser_lite.parsers.bilibili.sponsorblock import SponsorBlock


def row(start, end, category="sponsor", action="skip", cid="9", recorded=600):
    return {
        "segment": [start, end],
        "category": category,
        "actionType": action,
        "cid": cid,
        "videoDuration": recorded,
    }


@pytest.fixture(autouse=True)
def sponsorblock_config(monkeypatch):
    monkeypatch.setattr(support.pconfig, "plite_bsb_api_base", "https://bsbsb.top")
    monkeypatch.setattr(support.pconfig, "plite_bsb_categories", ["sponsor", "intro"])


async def query_rows(monkeypatch, rows, duration=600):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=rows))
    ) as client:
        monkeypatch.setattr(sponsorblock.DOWNLOADER, "client", client)
        return await SponsorBlock.query("a", 9, duration)


@pytest.mark.asyncio
async def test_query_encodes_parameters_and_filters_by_cid_and_category(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                row(1, 5, "intro"),
                row(10, 20, recorded=0),
                row(15, 25),
                row(25, 30),
                row(-5, 5),
                row(50, 50),
                row(80, 70),
                row(590, 610),
                row(40, 50, action="mute"),
                row(30, 40, cid="10"),
                row(40, 50, category="filler"),
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(sponsorblock.DOWNLOADER, "client", client)
        result = await SponsorBlock.query("a", 9, 600)

    params = seen[0].url.params
    assert params["cid"] == "9"
    assert params.get_list("categories") == ['["sponsor","intro"]']
    assert params["actionTypes"] == '["skip","mute","full"]'
    assert result.cut_ranges == ((1, 5), (10, 30), (590, 600))
    assert result.mute_ranges == ((40, 50),)
    assert result.output_duration == 566


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "json", "transport"])
async def test_query_failure_leaves_the_original_timeline(monkeypatch, failure):
    def handler(request):
        if failure == "transport":
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(404 if failure == "http" else 200, text="not json")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(sponsorblock.DOWNLOADER, "client", client)
        result = await SponsorBlock.query("a", 9, 600)
    assert result.segments == ()
    assert result.output_duration == 600


@pytest.mark.asyncio
@pytest.mark.parametrize("api_base", [None, "https://bsbsb.top"])
async def test_disabled_configuration_does_not_query(monkeypatch, api_base):
    get = AsyncMock()
    monkeypatch.setattr(sponsorblock.DOWNLOADER, "client", SimpleNamespace(get=get))
    monkeypatch.setattr(support.pconfig, "plite_bsb_api_base", api_base)
    if api_base:
        monkeypatch.setattr(support.pconfig, "plite_bsb_categories", [])
    assert (await SponsorBlock.query("a", 9, 600)).segments == ()
    get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entries", "is_ad", "covers_all"),
    [
        (
            [{"segment": [0], "category": "sponsor", "actionType": "full", "cid": "9"}],
            True,
            False,
        ),
        ([row(0, 0, "selfpromo", "full")], True, False),
        ([row(0, 0, "music_offtopic", "full")], False, False),
        ([row(0, 350), row(300, 600)], True, True),
        ([row(0, 300), row(300, 600, "intro")], False, True),
        ([row(0.01, 599.99)], False, False),
    ],
)
async def test_full_ad_labels_and_full_skip_coverage_are_distinct(
    monkeypatch, entries, is_ad, covers_all
):
    monkeypatch.setattr(
        support.pconfig,
        "plite_bsb_categories",
        [
            "sponsor",
            "intro",
            "selfpromo",
            "music_offtopic",
        ],
    )
    result = await query_rows(monkeypatch, entries)
    assert result.is_full_video_ad is is_ad
    assert result.covers_entire_video is covers_all
    if covers_all:
        assert result.output_duration == 0


@pytest.fixture
def video_parser(monkeypatch):
    info = bilibili.view_pb2.ViewReply(bvid="BV17x411w7KC")
    info.arc.duration, info.arc.title, info.arc.desc = 900, "title", "视频简介"
    info.arc.author.name = "tester"
    page = info.pages.add().page
    page.cid, page.duration = 9, 120
    parser = bilibili.BilibiliParser.__new__(bilibili.BilibiliParser)
    parser.headers, parser._credential = {}, None
    video = SimpleNamespace(
        bvid=info.bvid, aid=170001, get_info=AsyncMock(return_value=info)
    )
    stream = SimpleNamespace(url="https://example.com/video", backup_url=[])
    monkeypatch.setattr(parser, "_get_video", AsyncMock(return_value=video))
    monkeypatch.setattr(parser, "raise_if_in_black_list", AsyncMock())
    monkeypatch.setattr(
        parser, "get_download_streams", AsyncMock(return_value=(stream, None))
    )
    monkeypatch.setattr(parser, "_fetch_comments", AsyncMock(return_value=[]))
    monkeypatch.setattr(bilibili.DOWNLOADER, "head_size", AsyncMock(return_value=None))
    return parser, info


@pytest.mark.asyncio
@pytest.mark.parametrize("page_num", [1, 2])
async def test_parser_uses_the_selected_page_duration(
    monkeypatch, video_parser, page_num
):
    parser, info = video_parser
    if page_num == 2:
        second = info.pages.add().page
        second.cid, second.duration = 10, 240
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=[row(0, 30), row(0, 60, cid="10")])
        )
    ) as client:
        monkeypatch.setattr(sponsorblock.DOWNLOADER, "client", client)
        result = await parser.parse_video(bvid=info.bvid, page_num=page_num)
    assert result.content[0].duration == 90 * page_num
    assert result.content[0].need_send
    assert result.content[1] == "视频简介"


@pytest.mark.asyncio
async def test_full_ad_label_adds_notice_and_keeps_video_downloadable(
    monkeypatch, tmp_path, video_parser
):
    parser, info = video_parser
    source = support.Path(tmp_path / "source.mp4")
    await source.write_bytes(b"video")
    monkeypatch.setattr(
        bilibili.DOWNLOADER, "download_video", AsyncMock(return_value=source)
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=[row(0, 0, action="full")])
        )
    ) as client:
        monkeypatch.setattr(sponsorblock.DOWNLOADER, "client", client)
        result = await parser.parse_video(bvid=info.bvid)

    video = result.content[0]
    assert video.need_send
    assert video.duration == 120
    assert result.content[1:] == ["视频简介", "\n\n[视频为推广内容]"]
    assert await video.get_path() == source


@pytest.mark.asyncio
@pytest.mark.parametrize("video_in_forward", [False, True])
@pytest.mark.parametrize(
    ("entry", "notice"),
    [
        (row(0, 120, category="intro"), "[空降标注覆盖整条视频，未下载]"),
    ],
)
async def test_skipped_video_renders_notice_and_cover_without_downloading(
    monkeypatch, tmp_path, video_parser, video_in_forward, entry, notice
):
    parser, info = video_parser
    download = AsyncMock(side_effect=AssertionError("不应下载视频"))
    monkeypatch.setattr(bilibili.DOWNLOADER, "download_video", download)
    monkeypatch.setattr(support.Platform, "get_logo_path", AsyncMock(return_value=None))
    monkeypatch.setattr(support.pconfig, "plite_video_in_forward", video_in_forward)
    monkeypatch.setattr(support.pconfig, "plite_need_forward_contents", False)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[entry]))
    ) as client:
        monkeypatch.setattr(sponsorblock.DOWNLOADER, "client", client)
        result = await parser.parse_video(bvid=info.bvid)

    video = result.content[0]
    assert not video.need_send
    assert result.content[1] == "视频简介"
    assert result.content[2].strip() == notice
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"cover")
    video.cover = support.ResolvedPathTask(cover)
    data = await support.build_theme_data(
        result,
        color_scheme="light",
        theme_id="default",
        bot_name="bot",
        max_comments=0,
        append_qrcode=False,
    )
    assert data["post"]["content"][0]["src"] == cover.as_uri()
    assert notice in data["post"]["content"][2]["text"]
    messages = [message async for message in support.Renderer().send_content(result)]
    assert notice in "".join(message.extract_plain_text() for message in messages)
    download.assert_not_awaited()
