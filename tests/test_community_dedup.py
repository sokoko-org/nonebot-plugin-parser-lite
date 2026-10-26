import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from nonebot import get_plugin_config
from nonebot.matcher import current_event
from nonebot_plugin_uninfo import Scene, SceneType, Session, SupportScope, User
import pytest
from render_test_support import ROOT  # noqa: F401

from nonebot_plugin_parser_lite import matchers
from nonebot_plugin_parser_lite.config import Config
from nonebot_plugin_parser_lite.matchers import community_dedup as cooldown
from nonebot_plugin_parser_lite.matchers.rule import SearchResult
from nonebot_plugin_parser_lite.parsers.bilibili import BilibiliParser
from nonebot_plugin_parser_lite.parsers.douyin import DouyinParser
from nonebot_plugin_parser_lite.parsers.ds import DsParser
from nonebot_plugin_parser_lite.parsers.kuaishou import KuaiShouParser
from nonebot_plugin_parser_lite.parsers.netease import NCMParser
from nonebot_plugin_parser_lite.parsers.taptap import TapTapParser
from nonebot_plugin_parser_lite.parsers.weibo import WeiBoParser


def session(target="20001", user="10001", *, private=False):
    return Session(
        self_id="30001", adapter="OneBot V11", scope=SupportScope.qq_client,
        scene=Scene(target, SceneType.PRIVATE if private else SceneType.GROUP),
        user=User(user),
    )


def search(url, parser=None):
    if parser is None:
        parser = TapTapParser if "taptap.cn" in url else DsParser
    keyword, searched = parser.search_url(url)
    return SearchResult(url, keyword, searched)


@pytest.fixture
def pipeline(monkeypatch):
    parsed = AsyncMock(return_value=object())
    rendered = AsyncMock(return_value="summary")
    sent = AsyncMock()
    reactions = AsyncMock()

    async def content(*_args, **_kwargs):
        yield "body"

    monkeypatch.setattr(matchers, "community_parse_dedup", cooldown.CommunityParseDeduplicator())
    monkeypatch.setattr(matchers, "_KEYWORD_CLASS_MAP", {
        keyword: parser
        for parser in (TapTapParser, DsParser, BilibiliParser, DouyinParser, KuaiShouParser, NCMParser, WeiBoParser)
        for keyword, _pattern, _params in parser._key_patterns
    })
    monkeypatch.setattr(matchers, "_get_or_parse_result", parsed)
    monkeypatch.setattr(matchers.RENDERER, "render_messages", rendered)
    monkeypatch.setattr(matchers.RENDERER, "send_content", content)
    monkeypatch.setattr(matchers, "send_with_media_fallback", sent)
    monkeypatch.setattr(matchers.UniHelper, "message_reaction", reactions)
    monkeypatch.setattr(matchers.pconfig, "plite_lazy_download", False)
    monkeypatch.setattr(matchers.pconfig, "plite_summary_in_forward", False)
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_minutes", 30)
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_platforms", None)
    token = current_event.set(object())
    yield SimpleNamespace(parsed=parsed, rendered=rendered, sent=sent, reactions=reactions)
    current_event.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(("first", "second"), [
    ("https://www.taptap.cn/moment/123?share=first", "https://www.taptap.cn/explore/123?share=second"),
    ("https://ds.163.com/feed/abc123?share=first", "https://ds.163.com/article/abc123?share=second"),
])
async def test_same_group_members_and_url_variants_share_one_window(pipeline, first, second):
    await matchers.parser_handler(session(), search(first))
    await matchers.parser_handler(session(user="10002"), search(second))
    pipeline.parsed.assert_awaited_once()
    pipeline.rendered.assert_awaited_once()
    assert pipeline.sent.await_count == 2
    assert pipeline.reactions.await_count == 2
    await matchers.parser_handler(session("20002"), search(second))
    await matchers.parser_handler(session("10001", private=True), search(second))
    await matchers.parser_handler(session("10002", user="10002", private=True), search(second))
    assert pipeline.parsed.await_count == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes", [0, 30])
async def test_inflight_duplicates_wait_silently_for_success(pipeline, monkeypatch, minutes):
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_minutes", minutes)
    started, finish = asyncio.Event(), asyncio.Event()

    async def parse(_sr):
        started.set()
        await finish.wait()
        return object()

    pipeline.parsed.side_effect = parse
    sr = search("https://www.taptap.cn/moment/123")
    first = asyncio.create_task(matchers.parser_handler(session(), sr))
    await started.wait()
    followers = [asyncio.create_task(matchers.parser_handler(session(user=str(i)), sr)) for i in range(20)]
    await asyncio.sleep(0)
    assert pipeline.parsed.await_count == 1
    assert pipeline.reactions.await_count == 1
    finish.set()
    await asyncio.gather(first, *followers)
    pipeline.parsed.assert_awaited_once()
    assert pipeline.sent.await_count == 2
    assert pipeline.reactions.await_count == 2


@pytest.mark.asyncio
async def test_cancelled_owner_hands_off_to_one_waiter(pipeline):
    started, finish = asyncio.Event(), asyncio.Event()

    async def parse(_sr):
        started.set()
        await finish.wait()
        return object()

    pipeline.parsed.side_effect = parse
    sr = search("https://www.taptap.cn/moment/123")
    first = asyncio.create_task(matchers.parser_handler(session(), sr))
    await started.wait()
    followers = [asyncio.create_task(matchers.parser_handler(session(user=str(i)), sr)) for i in range(20)]
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    finish.set()
    await asyncio.gather(*followers)
    await matchers.parser_handler(session(), sr)
    assert pipeline.parsed.await_count == 2
    assert pipeline.sent.await_count == 2


@pytest.mark.asyncio
async def test_failed_waiter_retry_does_not_start_a_retry_chain(pipeline):
    started, finish = asyncio.Event(), asyncio.Event()

    async def fail(_sr):
        started.set()
        await finish.wait()
        raise RuntimeError("parse failed")

    pipeline.parsed.side_effect = fail
    sr = search("https://www.taptap.cn/moment/123")
    first = asyncio.create_task(matchers.parser_handler(session(), sr))
    await started.wait()
    followers = [asyncio.create_task(matchers.parser_handler(session(user=str(i)), sr)) for i in range(20)]
    await asyncio.sleep(0)
    finish.set()
    outcomes = await asyncio.gather(first, *followers, return_exceptions=True)
    assert sum(isinstance(outcome, RuntimeError) for outcome in outcomes) == 2
    assert pipeline.parsed.await_count == 2
    pipeline.sent.assert_not_awaited()

    pipeline.parsed.side_effect = None
    await matchers.parser_handler(session(), sr)
    assert pipeline.parsed.await_count == 3


@pytest.mark.asyncio
async def test_partial_output_failure_does_not_automatically_retry(pipeline):
    started, finish = asyncio.Event(), asyncio.Event()

    async def send(message, _result):
        if message == "body":
            started.set()
            await finish.wait()
            raise RuntimeError("body send failed")

    pipeline.sent.side_effect = send
    sr = search("https://www.taptap.cn/moment/123")
    first = asyncio.create_task(matchers.parser_handler(session(), sr))
    await started.wait()
    follower = asyncio.create_task(matchers.parser_handler(session(user="10002"), sr))
    await asyncio.sleep(0)
    finish.set()
    outcomes = await asyncio.gather(first, follower, return_exceptions=True)
    assert isinstance(outcomes[0], RuntimeError)
    assert outcomes[1] is None
    pipeline.parsed.assert_awaited_once()
    assert pipeline.sent.await_count == 2

    pipeline.sent.side_effect = None
    await matchers.parser_handler(session(), sr)
    assert pipeline.parsed.await_count == 2


@pytest.mark.asyncio
async def test_send_failure_does_not_start_success_window(pipeline):
    sr = search("https://www.taptap.cn/moment/123")
    pipeline.sent.side_effect = RuntimeError("send failed")
    with pytest.raises(RuntimeError):
        await matchers.parser_handler(session(), sr)
    pipeline.sent.side_effect = None
    await matchers.parser_handler(session(), sr)
    await matchers.parser_handler(session(), sr)
    assert pipeline.parsed.await_count == 2


@pytest.mark.asyncio
async def test_expiry_is_fixed_from_success_without_evicting_unexpired_posts(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(cooldown, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    guard = cooldown.CommunityParseDeduplicator()
    async with guard.acquire("post") as attempt:
        clock[0] = 200
        attempt.succeeded = True
    clock[0] = 1999
    async with guard.acquire("post") as duplicate:
        assert duplicate.succeeded
    clock[0] = 2000
    async with guard.acquire("post") as retry:
        assert not retry.succeeded
        retry.succeeded = True
    for key in range(8193):
        async with guard.acquire(key) as attempt:
            attempt.succeeded = True
    async with guard.acquire("post") as duplicate:
        assert duplicate.succeeded
    clock[0] += 1800
    async with guard.acquire("new"):
        assert not guard._recent


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_succeeds", [False, True])
async def test_new_arrival_cannot_race_waiters_into_parallel_retries(retry_succeeds):
    guard = cooldown.CommunityParseDeduplicator(window_seconds=0)

    async def follow():
        async with guard.acquire("post") as attempt:
            assert attempt is None or attempt.succeeded
            return attempt

    async with guard.acquire("post"):
        follower = asyncio.create_task(follow())
        await asyncio.sleep(0)
    # Arrive before the already queued waiter resumes after the first failure.
    async with guard.acquire("post") as retry:
        await asyncio.sleep(0)
        assert not follower.done()
        retry.succeeded = retry_succeeds
    assert (await follower is retry) == retry_succeeds


@pytest.mark.asyncio
async def test_cancelling_a_waiter_does_not_cancel_owner_or_other_waiters():
    guard = cooldown.CommunityParseDeduplicator()

    async def follow():
        async with guard.acquire("post") as attempt:
            return attempt

    async with guard.acquire("post") as owner:
        cancelled = asyncio.create_task(follow())
        remaining = asyncio.create_task(follow())
        await asyncio.sleep(0)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        assert not remaining.done()
        owner.succeeded = True
    assert await remaining is owner


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrent", [False, True])
async def test_lazy_duplicates_register_each_member_without_resending(pipeline, monkeypatch, concurrent):
    monkeypatch.setattr(matchers.pconfig, "plite_lazy_download", True)
    monkeypatch.setattr(matchers.pconfig, "plite_lazy_download_tip", False)
    monkeypatch.setattr(matchers, "_RESULT_CACHE", {})
    manager = matchers.LazyManager
    monkeypatch.setattr(manager, "SESSIONS", {})
    monkeypatch.setattr(manager, "ACTIVE_USERS", set())
    monkeypatch.setattr(manager, "TIMEOUT_TASKS", set())
    monkeypatch.setattr(manager, "LOCK", asyncio.Lock())
    started, finish = asyncio.Event(), asyncio.Event()
    result = object()

    async def parse(_sr):
        started.set()
        await finish.wait()
        return result

    pipeline.parsed.side_effect = parse
    first_session, second_session = session(), session(user="10002")
    sr = search("https://www.taptap.cn/moment/123")
    try:
        first = asyncio.create_task(matchers.parser_handler(first_session, sr))
        await started.wait()
        if not concurrent:
            finish.set()
            await first
            matchers.clear_result_cache()
        follower = asyncio.create_task(matchers.parser_handler(second_session, sr))
        await asyncio.sleep(0)
        finish.set()
        await asyncio.gather(first, follower)
        for member in (first_session, second_session):
            key = manager.session_key(member)
            assert await manager.claim(key) is result
            await manager.release(key)
        pipeline.parsed.assert_awaited_once()
        pipeline.rendered.assert_awaited_once()
        pipeline.sent.assert_awaited_once()
        assert pipeline.reactions.await_count == 2
    finally:
        tasks = list(manager.TIMEOUT_TASKS)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(("parser", "url"), [
    (BilibiliParser, "https://www.bilibili.com/video/BV1xx411c7mD"),
    (DouyinParser, "https://www.douyin.com/video/123456789"),
    (KuaiShouParser, "https://v.kuaishou.com/abc123"),
    (NCMParser, "https://music.163.com/song?id=123456"),
    (WeiBoParser, "https://m.weibo.cn/status/123456789"),
])
async def test_other_platforms_share_the_configured_cooldown(pipeline, parser, url):
    sr = search(url, parser)
    await matchers.parser_handler(session(), sr)
    await matchers.parser_handler(session(user="10002"), sr)
    pipeline.parsed.assert_awaited_once()
    pipeline.rendered.assert_awaited_once()
    assert pipeline.sent.await_count == 2
    assert pipeline.reactions.await_count == 2
    await matchers.parser_handler(session("20002"), sr)
    await matchers.parser_handler(session("10001", private=True), sr)
    assert pipeline.parsed.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(("platforms", "parser", "url", "count"), [
    (["taptap", "ds"], TapTapParser, "https://www.taptap.cn/moment/123", 1),
    (["taptap", "ds"], DsParser, "https://ds.163.com/feed/abc123", 1),
    (["taptap", "ds"], BilibiliParser, "https://www.bilibili.com/video/BV1xx411c7mD", 2),
    (["bilibili"], BilibiliParser, "https://www.bilibili.com/video/BV1xx411c7mD", 1),
    (["bilibili"], BilibiliParser, "BV1xx411c7mD", 1),
    (["bilibili"], BilibiliParser, "https://b23.tv/abc123", 1),
    (["bilibili"], DouyinParser, "https://www.douyin.com/video/123456789", 2),
    ([], TapTapParser, "https://www.taptap.cn/moment/123", 2),
    ([], BilibiliParser, "https://www.bilibili.com/video/BV1xx411c7mD", 2),
])
async def test_cooldown_applies_only_to_selected_platforms(pipeline, monkeypatch, platforms, parser, url, count):
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_platforms", platforms)
    sr = search(url, parser)
    await matchers.parser_handler(session(), sr)
    await matchers.parser_handler(session(user="10002"), sr)
    assert pipeline.parsed.await_count == count
    assert pipeline.rendered.await_count == count
    assert pipeline.sent.await_count == count * 2
    assert pipeline.reactions.await_count == count * 2


@pytest.mark.asyncio
@pytest.mark.parametrize("platforms", [[], ["taptap"]])
async def test_excluded_platforms_bypass_inflight_deduplication(pipeline, monkeypatch, platforms):
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_platforms", platforms)
    started, finish = asyncio.Event(), asyncio.Event()

    async def parse(_sr):
        started.set()
        await finish.wait()
        return object()

    pipeline.parsed.side_effect = parse
    sr = search("https://www.bilibili.com/video/BV1xx411c7mD", BilibiliParser)
    first = asyncio.create_task(matchers.parser_handler(session(), sr))
    await started.wait()
    second = asyncio.create_task(matchers.parser_handler(session(user="10002"), sr))
    await asyncio.sleep(0)
    assert pipeline.parsed.await_count == 2
    finish.set()
    await asyncio.gather(first, second)
    assert pipeline.sent.await_count == 4


def test_unlisted_platforms_also_receive_a_cooldown_key():
    sr = SimpleNamespace(keyword="future.example.com", cache_key="future:post/123")
    assert cooldown.community_parse_key("QQClient_GROUP_1", sr) == (
        "parse", "QQClient_GROUP_1", "future:post/123",
    )


@pytest.mark.asyncio
async def test_distinct_content_and_bilibili_pages_are_not_suppressed(pipeline):
    for url in (
        "https://www.bilibili.com/video/BV1xx411c7mD?p=1",
        "https://www.bilibili.com/video/BV1xx411c7mD?p=2",
        "https://www.bilibili.com/video/BV1xx411c7mE?p=1",
    ):
        sr = search(url, BilibiliParser)
        await matchers.parser_handler(session(), sr)
        await matchers.parser_handler(session(user="10002"), sr)
    assert pipeline.parsed.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(("parser", "url"), [
    (DsParser, "https://ds.163.com/feed/abc123"),
    (BilibiliParser, "https://www.bilibili.com/video/BV1xx411c7mD"),
])
async def test_zero_minutes_allows_completed_repeats(pipeline, monkeypatch, parser, url):
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_minutes", 0)
    sr = search(url, parser)
    await matchers.parser_handler(session(), sr)
    await matchers.parser_handler(session(), sr)
    assert pipeline.parsed.await_count == 2


@pytest.mark.parametrize(("value", "expected"), [
    ("null", None),
    ("[]", []),
    ('["taptap", "ds"]', ["taptap", "ds"]),
    ('["bilibili"]', ["bilibili"]),
])
def test_plugin_loads_platform_selection_from_environment(monkeypatch, value, expected):
    monkeypatch.setenv("PLITE_PARSE_DEDUP_PLATFORMS", value)
    assert get_plugin_config(Config).parse_dedup_platforms == expected


def test_platform_selection_defaults_to_all_and_rejects_unknown_platforms():
    from pydantic import ValidationError

    assert Config().parse_dedup_platforms is None
    with pytest.raises(ValidationError):
        Config(plite_parse_dedup_platforms=["typo"])
