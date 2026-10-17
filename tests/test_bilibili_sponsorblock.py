"""B 站空降：标注查询、区间换算，以及下载完成后产出成片。

这块是平台特有能力，只被 bilibili 解析器调用；通用倍速在 test_media_speedup.py。
"""

import pytest
import render_test_support as support

from nonebot_plugin_parser_lite.parsers.bilibili import sponsorblock
from nonebot_plugin_parser_lite.parsers.bilibili.sponsorblock import (
    _iter_segment_dicts,
    _normalize_ranges,
    _parse_segment,
    fetch_segments,
    skip_for_video,
    skip_ranges,
)

ROW = {"segment": [1.0, 5.0], "category": "sponsor", "actionType": "skip"}


def row(start, end, category="sponsor", action="skip", recorded=600.0):
    return {"segment": [start, end], "category": category, "actionType": action, "videoDuration": recorded}


class _Response:
    def __init__(self, status_code=200, payload=None, raw="not json"):
        self.status_code = status_code
        self._payload = payload
        self._raw = raw

    def json(self):
        if self._payload is None:
            raise ValueError(self._raw)
        return self._payload


class _Client:
    """替掉统一下载客户端，不发网络请求"""

    def __init__(self, response: _Response, error: Exception | None = None):
        self.response = response
        self.error = error
        self.requests: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url, *, params=None, headers=None):
        self.requests.append((url, params or {}))
        if self.error is not None:
            raise self.error
        return self.response


# --------------------------------------------------------------------------
# 返回体解析


def test_parser_accepts_both_documented_shapes():
    flat = [ROW]
    grouped = [{"videoID": "BV1", "segments": [row(2, 9, "intro", "mute")]}]
    assert _iter_segment_dicts(flat) == [ROW]
    parsed = _parse_segment(_iter_segment_dicts(grouped)[0])
    assert parsed is not None
    assert (parsed.start, parsed.end, parsed.action_type) == (2.0, 9.0, "mute")
    # 分类与 actionType 大小写不敏感
    assert _parse_segment(row(1, 2, "Sponsor", "Skip")).category == "sponsor"


@pytest.mark.parametrize(
    "entry",
    [
        {},
        {"segment": [1.0], "category": "sponsor", "actionType": "skip"},
        {"segment": ["a", "b"], "category": "sponsor", "actionType": "skip"},
        {"segment": [5.0, 1.0], "category": "sponsor", "actionType": "skip"},
        {"segment": [-5.0, 1.0], "category": "sponsor", "actionType": "skip"},
        {"segment": [1.0, 2.0], "actionType": "skip"},
        {"segment": [1.0, 2.0], "category": "sponsor"},
    ],
)
def test_malformed_segment_is_rejected(entry):
    assert _parse_segment(entry) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client",
    [
        _Client(_Response(404)),
        _Client(_Response(400)),
        _Client(_Response(200, payload=None)),
        _Client(_Response(200, payload={"unexpected": "object"})),
        _Client(_Response(200, payload=[{"segment": ["x", "y"]}]), None),
    ],
)
async def test_fetch_degrades_to_empty(monkeypatch, client):
    monkeypatch.setattr(sponsorblock.DOWNLOADER, "client", client)
    assert await fetch_segments("https://bsbsb.top", "BV1", "9", ["sponsor"]) == []


@pytest.mark.asyncio
async def test_fetch_swallows_transport_errors(monkeypatch):
    client = _Client(_Response(), error=OSError("connection reset"))
    monkeypatch.setattr(sponsorblock.DOWNLOADER, "client", client)
    assert await fetch_segments("https://bsbsb.top", "BV1", "9", ["sponsor"]) == []


# --------------------------------------------------------------------------
# 区间换算


def test_normalize_ranges_clamps_sorts_and_merges():
    merged = _normalize_ranges(
        [
            (500.0, 520.0),
            (100.0, 160.0),
            (150.0, 180.0),
            (-10.0, 20.0),
            (590.0, 900.0),
        ],
        600.0,
    )
    assert merged == ((0.0, 20.0), (100.0, 180.0), (500.0, 520.0), (590.0, 600.0))


async def _skip_rows(monkeypatch, rows, duration=600.0):
    client = _Client(_Response(200, rows))
    monkeypatch.setattr(sponsorblock.DOWNLOADER, "client", client)
    return await skip_ranges("https://x.top", ["sponsor", "intro"], "BV1", "9", duration)


@pytest.mark.asyncio
async def test_ranges_are_split_by_action_type(monkeypatch):
    cuts, mutes, removed = await _skip_rows(
        monkeypatch,
        [
            row(0.0, 30.0, "sponsor", "skip"),
            row(60.0, 75.0, "intro", "mute"),
            row(90.0, 100.0, "sponsor", "full"),
            row(120.0, 130.0, "intro", "poi"),
        ],
    )
    assert cuts == ((0.0, 30.0),)
    assert mutes == ((60.0, 75.0),)
    assert removed == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_unselected_category_is_ignored(monkeypatch):
    """服务端可能返回同视频其他分类的标注，只处理白名单内的"""
    cuts, mutes, removed = await _skip_rows(
        monkeypatch, [row(0.0, 30.0, "filler", "skip")]
    )
    assert (cuts, mutes, removed) == ((), (), 0.0)


@pytest.mark.asyncio
async def test_staleness_is_checked_per_segment(monkeypatch):
    cuts, _, _ = await _skip_rows(
        monkeypatch,
        [
            row(10.0, 20.0, recorded=600.0),
            row(30.0, 40.0, recorded=520.0),
            row(50.0, 60.0, recorded=0.0),
        ],
    )
    # 第二条标注的是旧版本，误差超过 ±2 秒就丢弃
    assert cuts == ((10.0, 20.0), (50.0, 60.0))


@pytest.mark.asyncio
async def test_unknown_recorded_duration_is_not_falsified(monkeypatch):
    cuts, _, _ = await _skip_rows(monkeypatch, [{"segment": [10.0, 20.0], "category": "sponsor", "actionType": "skip"}])
    assert cuts == ((10.0, 20.0),)


@pytest.mark.asyncio
async def test_cuts_covering_the_whole_video_are_abandoned(monkeypatch):
    cuts, mutes, removed = await _skip_rows(monkeypatch, [row(0.0, 600.0)])
    assert cuts == ()
    assert mutes == ()
    assert removed == 0.0


@pytest.mark.asyncio
async def test_tiny_pieces_are_absorbed_by_the_planner(monkeypatch):
    """碎片阈值必须在 skip_ranges 里带上，而不只是纯函数里正确"""
    cuts, _, removed = await _skip_rows(
        monkeypatch, [row(10.0, 20.0), row(20.02, 30.0)]
    )
    assert cuts == ((10.0, 30.0),)
    assert removed == pytest.approx(20.0)


# --------------------------------------------------------------------------
# 解析阶段的入口：配置门控


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("api_base", "categories", "cid", "duration"),
    [
        (None, ["sponsor"], 9, 600.0),
        ("https://x.top", [], 9, 600.0),
        ("https://x.top", ["sponsor"], None, 600.0),
        ("https://x.top", ["sponsor"], 9, 0.0),
    ],
)
async def test_skip_is_disabled_without_config_or_identity(
    monkeypatch, api_base, categories, cid, duration
):
    async def never(*args, **kwargs):
        raise AssertionError("不该发起查询")

    monkeypatch.setattr(sponsorblock, "skip_ranges", never)
    monkeypatch.setattr(support.pconfig, "plite_bsb_api_base", api_base)
    monkeypatch.setattr(support.pconfig, "plite_bsb_categories", categories)
    assert await skip_for_video("BV1", cid, duration) == ((), (), 0.0)


@pytest.mark.asyncio
async def test_skip_for_video_passes_the_resolved_identity(monkeypatch):
    seen: list[tuple] = []

    async def spy(api_base, categories, bvid, cid, duration):
        seen.append((api_base, categories, bvid, cid, duration))
        return ((1.0, 2.0),), ((3.0, 4.0),), 1.0

    monkeypatch.setattr(sponsorblock, "skip_ranges", spy)
    monkeypatch.setattr(support.pconfig, "plite_bsb_api_base", "https://x.top")
    monkeypatch.setattr(support.pconfig, "plite_bsb_categories", ["sponsor"])

    cuts, mutes, removed = await skip_for_video("BV1", 9, 600.0)
    # cid 是整数，查询要拿到字符串形式
    assert seen == [("https://x.top", ["sponsor"], "BV1", "9", 600.0)]
    assert (cuts, mutes, removed) == (((1.0, 2.0),), ((3.0, 4.0),), 1.0)
