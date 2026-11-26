from datetime import date, datetime, time, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, patch

from anyio import Path
from matcher_test_support import (
    CURRENT_GROUP,
    command_context,
    patched_pipeline,
    search,
    session,
)
from nonebot.matcher import current_event
from nonebot_plugin_alconna import Image, Match, UniMessage
from PIL import Image as PILImage
import pytest
import pytest_asyncio

from nonebot_plugin_parser_lite import matchers, stats
from nonebot_plugin_parser_lite.exception import TipException
from nonebot_plugin_parser_lite.matchers import stats as stats_matcher
from nonebot_plugin_parser_lite.render import stats as stats_render

GROUP_KEY = f"QQClient_GROUP_{CURRENT_GROUP}"
TAPTAP_URL = "https://www.taptap.cn/moment/123"


@pytest.fixture
def no_font_download(monkeypatch):
    """渲染会在后台从 npm 下载兜底 emoji 字体；记为不可用，直接用系统字族"""
    from nonebot_plugin_parser_lite.render import fonts

    monkeypatch.setitem(fonts._FONTS, "twitter", None)


@pytest_asyncio.fixture
async def store(monkeypatch, tmp_path):
    instance = stats.ParseStats(Path(tmp_path) / "stats.db")
    monkeypatch.setattr(stats, "STATS", instance)
    monkeypatch.setattr(matchers, "STATS", instance)
    yield instance
    await instance.aclose()


@pytest.fixture
def pipeline(monkeypatch, store):
    with patched_pipeline(monkeypatch, stats=store) as stubs:
        yield stubs


@pytest.mark.asyncio
async def test_records_persist_and_aggregate(store, tmp_path):
    await store.record("bilibili", "g1", success=True)
    await store.record("bilibili", "g1", success=True)
    await store.record("bilibili", "g2", success=False)
    await store.record("douyin", "g1", success=True)

    # 新实例读取同一文件，验证已落盘
    summary = await stats.ParseStats(Path(tmp_path) / "stats.db").query(7)
    assert (summary.total.success, summary.total.failure) == (3, 1)
    assert list(summary.platforms) == ["bilibili", "douyin"]
    assert summary.platforms["bilibili"].total == 3
    assert summary.platforms["bilibili"].failure == 1
    assert list(summary.targets) == ["g1", "g2"]

    # 独立版记录的 target 为空，不作为会话参与排行
    await store.record("bilibili", success=True)
    assert list((await store.query(7)).targets) == ["g1", "g2"]

    only_g2 = await store.query(7, "g2")
    assert only_g2.total.total == 1
    assert list(only_g2.platforms) == ["bilibili"]


@pytest.mark.asyncio
async def test_query_respects_day_window(store):
    today = date.today()
    await store.record(
        "bilibili",
        "g1",
        success=True,
        at=datetime.combine(today - timedelta(days=10), time(12)),
    )
    await store.record("douyin", "g1", success=True)

    recent = await store.query(7)
    assert list(recent.platforms) == ["douyin"]
    assert recent.since == today - timedelta(days=6)
    assert len(recent.daily) == 7
    assert recent.daily[today].total == 1
    assert sum(count.total for count in recent.daily.values()) == 1
    assert (await store.query(11)).total.total == 2
    assert (await store.query(1)).total.total == 1
    with pytest.raises(ValueError, match="大于 0"):
        await store.query(0)


@pytest.mark.asyncio
async def test_hourly_buckets_use_local_time_and_day_edges(store):
    today = date.today()
    midnight = datetime.combine(today, time.min)
    await store.record("bilibili", "g1", success=True, at=midnight)
    await store.record("bilibili", "g1", success=False, at=midnight.replace(hour=9))
    await store.record(
        "douyin", "g1", success=True, at=midnight.replace(hour=9, minute=59)
    )
    await store.record(
        "douyin", "g1", success=True, at=midnight.replace(hour=23, minute=59)
    )
    # 昨天 23:59 不属于 query(1)
    await store.record("douyin", "g1", success=True, at=midnight - timedelta(minutes=1))

    summary = await store.query(1)
    assert summary.total.total == 4
    assert len(summary.hourly) == 24
    assert summary.hourly[0].success == 1
    assert (summary.hourly[9].success, summary.hourly[9].failure) == (1, 1)
    assert summary.hourly[23].total == 1
    assert sum(count.total for count in summary.hourly.values()) == 4
    assert (await store.query(2)).hourly[23].total == 2


@pytest.mark.asyncio
async def test_records_return_typed_events(store):
    base = datetime.combine(date.today(), time(8, 30, 15))
    await store.record("bilibili", "g1", success=True, at=base)
    await store.record("douyin", "g2", success=False, at=base + timedelta(hours=1))
    await store.record("bilibili", "g2", success=True, at=base + timedelta(hours=2))

    records = await store.records()
    assert await stats.query_records() == records
    assert [record.platform for record in records] == ["bilibili", "douyin", "bilibili"]
    first = records[0]
    assert isinstance(first, stats.ParseRecord)
    assert first.time.tzinfo is not None
    assert first.time.replace(tzinfo=None) == base
    assert first.timestamp == base.timestamp()
    assert (first.target, first.success) == ("g1", True)
    assert records[1].success is False

    window = await store.records(base + timedelta(hours=1), base + timedelta(hours=2))
    assert [record.platform for record in window] == ["douyin"]
    assert [r.platform for r in await store.records(target="g2")] == [
        "douyin",
        "bilibili",
    ]
    assert [r.target for r in await store.records(platform="bilibili")] == ["g1", "g2"]
    assert len(await store.records(limit=1)) == 1


@pytest.mark.asyncio
async def test_write_failure_is_logged_not_raised(store, monkeypatch):
    def broken(*_args, **_kwargs):
        raise OSError("disk failure")

    with monkeypatch.context() as patch_:
        patch_.setattr(stats.aiosqlite, "connect", broken)
        await store.record("bilibili", "g1", success=True)
    assert store._writer is None


async def run_stats(handler, *args, render=False):
    """调用命令处理函数，返回发送的消息和传给渲染器的统计（真实渲染时为 None）"""
    renderer = AsyncMock(return_value=("png", b"image"))
    stub = (
        patch.object(stats_matcher, "platform_names", return_value={})
        if render
        else patch.object(stats_matcher, "render_stats_image", renderer)
    )
    with patch.object(UniMessage, "send", autospec=True) as send, stub:
        await handler(*args)
    send.assert_awaited_once()
    summary = None if render else renderer.await_args.args[0]
    return send.call_args.args[0], summary


def days_arg(days=None):
    return Match(days, days is not None)


@pytest.mark.asyncio
async def test_command_scopes(store):
    await store.record("bilibili", GROUP_KEY, success=True)
    await store.record("douyin", "QQClient_GROUP_other", success=False)
    _, _, session_ = command_context(superuser=False)

    _, current = await run_stats(stats_matcher.handle_stats, session_, days_arg())
    assert (current.days, current.target) == (7, GROUP_KEY)
    assert current.total.total == 1

    _, full = await run_stats(stats_matcher.handle_global_stats, days_arg(30))
    assert (full.days, full.target) == (30, None)
    assert (full.total.total, full.total.failure) == (2, 1)
    assert full.targets["QQClient_GROUP_other"].failure == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [0, 31])
async def test_command_rejects_bad_days(store, monkeypatch, days):
    monkeypatch.setattr(stats_matcher.pconfig, "plite_stats_max_days", 30)
    with patch.object(UniMessage, "send", autospec=True) as send:
        await stats_matcher.handle_global_stats(days_arg(days))
    assert send.call_args.args[0].extract_plain_text() == "天数需在 1-30 之间"


def registered(handler):
    from nonebot.matcher import matchers as registry

    return next(
        matcher
        for group in registry.values()
        for matcher in group
        if any(dep.call is handler for dep in matcher.handlers)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "role", "allowed"),
    [
        (stats_matcher.handle_stats, "MEMBER", False),
        (stats_matcher.handle_stats, "ADMINISTRATOR", True),
        (stats_matcher.handle_global_stats, "ADMINISTRATOR", False),
    ],
)
async def test_command_permissions(store, handler, role, allowed):
    from nonebot.internal.params import DependencyCache
    from nonebot_plugin_uninfo import Member, Role, get_session

    bot, event, session_ = command_context(superuser=False)
    session_.member = Member(session_.user, roles=[Role(role)])
    cache = DependencyCache()
    cache.set_result(session_)
    permission = registered(handler).permission
    assert (
        await permission(bot, event, dependency_cache={get_session: cache}) is allowed
    )


@pytest.mark.asyncio
async def test_parser_handler_records_success_failure_and_dedup(pipeline, store):
    await matchers.parser_handler(session(), search(TAPTAP_URL))
    # 冷却窗口内重复链接不重复计数
    await matchers.parser_handler(session(user="10002"), search(TAPTAP_URL))

    pipeline.parsed.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        await matchers.parser_handler(session("20002"), search(TAPTAP_URL))

    pipeline.parsed.side_effect = TipException("请稍后再试")
    with patch.object(UniMessage, "send", AsyncMock()):
        await matchers.parser_handler(session("20003"), search(TAPTAP_URL))

    # 解析成功但发送失败，仍计为解析成功
    pipeline.parsed.side_effect = None
    pipeline.sent.side_effect = RuntimeError("send failed")
    with pytest.raises(RuntimeError):
        await matchers.parser_handler(session("20004"), search(TAPTAP_URL))

    summary = await store.query(1)
    assert (summary.total.success, summary.total.failure) == (2, 2)
    assert list(summary.platforms) == ["taptap"]
    assert summary.targets["QQClient_GROUP_20001"].success == 1
    assert summary.targets["QQClient_GROUP_20002"].failure == 1
    assert summary.targets["QQClient_GROUP_20003"].failure == 1
    assert current_event.get() is not None


@pytest.mark.asyncio
async def test_command_sends_rendered_image(store, no_font_download, monkeypatch):
    monkeypatch.setattr(stats_render.pconfig, "plite_render_format", "jpeg")
    await store.record("bilibili", GROUP_KEY, success=True)
    message, _ = await run_stats(
        stats_matcher.handle_global_stats, days_arg(30), render=True
    )
    images = message[Image]
    assert len(images) == 1
    with PILImage.open(BytesIO(images[0].raw_bytes)) as image:
        image.load()
        assert image.width == 1240


def test_stats_data_buckets_long_ranges_and_groups_tail(monkeypatch):
    monkeypatch.setattr(stats_render.pconfig, "plite_stats_top_targets", 10)
    today = date.today()
    since = today - timedelta(days=89)
    summary = stats.ParseStatsSummary(
        90,
        since,
        today,
        None,
        daily={since + timedelta(days=i): stats.StatsCount(i, 0) for i in range(90)},
        platforms={"bilibili": stats.StatsCount(5, 1)},
        targets={f"t{i}": stats.StatsCount(20 - i, 0) for i in range(13)},
    )
    data = stats_render.build_stats_data(
        summary, platform_names={"bilibili": "哔哩哔哩"}, color_scheme="dark"
    )
    assert data["schema_version"] == 1
    assert data["theme"] == "dark"
    assert data["meta"]["width"] == 620
    s = data["stats"]
    assert s["scope"] == {"global": True, "target": None, "label": "全部会话"}
    assert s["chart"]["bucket_days"] == 3
    assert s["chart"]["unit"] == "每柱 3 天"
    assert len(s["chart"]["bars"]) == 30
    assert max(bar["success_pct"] for bar in s["chart"]["bars"]) == 100
    assert s["chart"]["bars"][0]["start"] == since.isoformat()
    assert [item["hour"] for item in s["hourly"]] == list(range(24))
    assert s["platforms"][0] == {
        "id": "bilibili",
        "name": "哔哩哔哩",
        "total": 6,
        "success": 5,
        "failure": 1,
        "rate": 83.3,
        "success_pct": 83.33,
        "failure_pct": 16.67,
    }
    assert len(s["targets"]) == 11
    assert s["targets"][-1]["id"] is None
    assert s["targets"][-1]["name"] == "其他 3 项"
    assert s["peak"] == {"date": today.isoformat(), "total": 89}


@pytest.mark.asyncio
async def test_theme_can_override_stats_template(tmp_path, no_font_download):
    from anyio import Path as AsyncPath

    from nonebot_plugin_parser_lite.render.theme import (
        ThemeDefinition,
        ThemeManifest,
    )

    theme_root = tmp_path / "custom"
    theme_root.mkdir()
    builtin = AsyncPath(stats_render.TEMPLATES_DIR)
    plain = ThemeDefinition(
        ThemeManifest("plain", "Plain", "1"), AsyncPath(theme_root), builtin
    )
    selected = await plain.resolve_named_template(stats_render.STATS_TEMPLATE)
    assert selected.root == builtin

    (theme_root / "stats.html.jinja").write_text(
        "<html><body><main>{{ data.stats.total.total }}</main></body></html>",
        encoding="utf-8",
    )
    selected = await plain.resolve_named_template(stats_render.STATS_TEMPLATE)
    assert selected.root == AsyncPath(theme_root)

    today = date.today()
    summary = stats.ParseStatsSummary(
        1, today, today, None, total=stats.StatsCount(3, 0)
    )
    fmt, image = await stats_render.render_stats_image(
        summary, theme_definition=plain, image_format="jpeg"
    )
    assert fmt == "jpeg"
    with PILImage.open(BytesIO(image)) as img:
        assert img.width == 1240
