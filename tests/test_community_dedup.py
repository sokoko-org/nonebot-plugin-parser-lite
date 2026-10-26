import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from nonebot.matcher import current_event
from nonebot_plugin_uninfo import Scene, SceneType, Session, SupportScope, User
import pytest
from render_test_support import ROOT  # noqa: F401

from nonebot_plugin_parser_lite import matchers
from nonebot_plugin_parser_lite.matchers import community_dedup as cooldown
from nonebot_plugin_parser_lite.matchers.rule import SearchResult
from nonebot_plugin_parser_lite.parsers.bilibili import BilibiliParser
from nonebot_plugin_parser_lite.parsers.ds import DsParser
from nonebot_plugin_parser_lite.parsers.taptap import TapTapParser


def session(target="20001", user="10001", *, private=False):
    return Session(
        self_id="30001",
        adapter="OneBot V11",
        scope=SupportScope.qq_client,
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

    async def content(*_args, **_kwargs):
        yield "body"

    monkeypatch.setattr(
        matchers, "community_parse_dedup", cooldown.CommunityParseDeduplicator()
    )
    monkeypatch.setattr(
        matchers,
        "_KEYWORD_CLASS_MAP",
        {
            keyword: parser
            for parser in (TapTapParser, DsParser, BilibiliParser)
            for keyword, _pattern, _params in parser._key_patterns
        },
    )
    monkeypatch.setattr(matchers, "_get_or_parse_result", parsed)
    monkeypatch.setattr(matchers.RENDERER, "render_messages", rendered)
    monkeypatch.setattr(matchers.RENDERER, "send_content", content)
    monkeypatch.setattr(matchers, "send_with_media_fallback", sent)
    monkeypatch.setattr(matchers.UniHelper, "message_reaction", AsyncMock())
    monkeypatch.setattr(matchers.pconfig, "plite_lazy_download", False)
    monkeypatch.setattr(matchers.pconfig, "plite_summary_in_forward", False)
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_minutes", 30)
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_platforms", None)
    token = current_event.set(object()) # pyright: ignore[reportArgumentType]
    yield SimpleNamespace(parsed=parsed, sent=sent)
    current_event.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            "https://www.taptap.cn/moment/123?share=first",
            "https://www.taptap.cn/explore/123?share=second",
        ),
        (
            "https://ds.163.com/feed/abc123?share=first",
            "https://ds.163.com/article/abc123?share=second",
        ),
    ],
)
async def test_same_group_members_and_url_variants_share_one_window(
    pipeline, first, second
):
    await matchers.parser_handler(session(), search(first))
    await matchers.parser_handler(session(user="10002"), search(second))
    pipeline.parsed.assert_awaited_once()
    assert pipeline.sent.await_count == 2
    await matchers.parser_handler(session("20002"), search(second))
    await matchers.parser_handler(session("10001", private=True), search(second))
    await matchers.parser_handler(
        session("10002", user="10002", private=True), search(second)
    )
    assert pipeline.parsed.await_count == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes", [0, 30])
async def test_inflight_duplicates_wait_silently_for_success(
    pipeline, monkeypatch, minutes
):
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
    followers = [
        asyncio.create_task(matchers.parser_handler(session(user=str(i)), sr))
        for i in range(20)
    ]
    await asyncio.sleep(0)
    assert pipeline.parsed.await_count == 1
    finish.set()
    await asyncio.gather(first, *followers)
    pipeline.parsed.assert_awaited_once()
    assert pipeline.sent.await_count == 2


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
    followers = [
        asyncio.create_task(matchers.parser_handler(session(user=str(i)), sr))
        for i in range(20)
    ]
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
    followers = [
        asyncio.create_task(matchers.parser_handler(session(user=str(i)), sr))
        for i in range(20)
    ]
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
async def test_cooldown_expires_from_success_without_extending_on_duplicates(
    pipeline, monkeypatch
):
    clock = [100.0]
    monkeypatch.setattr(cooldown, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    async def parse(_sr):
        clock[0] = 200
        return object()

    pipeline.parsed.side_effect = parse
    sr = search("https://www.taptap.cn/moment/123")
    await matchers.parser_handler(session(), sr)
    clock[0] = 1999
    await matchers.parser_handler(session(), sr)
    assert pipeline.sent.await_count == 2
    clock[0] = 2000
    await matchers.parser_handler(session(), sr)
    assert pipeline.parsed.await_count == 2
    assert pipeline.sent.await_count == 4


@pytest.mark.asyncio
async def test_cancelling_a_waiter_does_not_cancel_owner_or_other_waiters(pipeline):
    started, finish = asyncio.Event(), asyncio.Event()

    async def parse(_sr):
        started.set()
        await finish.wait()
        return object()

    pipeline.parsed.side_effect = parse
    sr = search("https://www.taptap.cn/moment/123")
    owner = asyncio.create_task(matchers.parser_handler(session(), sr))
    await started.wait()
    cancelled = asyncio.create_task(matchers.parser_handler(session(user="10002"), sr))
    remaining = asyncio.create_task(matchers.parser_handler(session(user="10003"), sr))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    finish.set()
    await asyncio.gather(owner, remaining)
    pipeline.parsed.assert_awaited_once()
    assert pipeline.sent.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("concurrent", [False, True])
async def test_lazy_duplicates_register_each_member_without_resending(
    pipeline, monkeypatch, concurrent
):
    monkeypatch.setattr(matchers.pconfig, "plite_lazy_download", True)
    monkeypatch.setattr(matchers.pconfig, "plite_lazy_download_tip", False)
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
        follower = asyncio.create_task(matchers.parser_handler(second_session, sr))
        await asyncio.sleep(0)
        finish.set()
        await asyncio.gather(first, follower)
        for member in (first_session, second_session):
            key = manager.session_key(member)
            assert await manager.claim(key) is result
            await manager.release(key)
        pipeline.parsed.assert_awaited_once()
        pipeline.sent.assert_awaited_once()
    finally:
        tasks = list(manager.TIMEOUT_TASKS)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platforms", "parser", "url", "count"),
    [
        (None, BilibiliParser, "https://www.bilibili.com/video/BV1xx411c7mD", 1),
        (["taptap", "ds"], TapTapParser, "https://www.taptap.cn/moment/123", 1),
        (
            ["taptap", "ds"],
            BilibiliParser,
            "https://www.bilibili.com/video/BV1xx411c7mD",
            2,
        ),
        (
            ["bilibili"],
            BilibiliParser,
            "https://www.bilibili.com/video/BV1xx411c7mD",
            1,
        ),
        ([], TapTapParser, "https://www.taptap.cn/moment/123", 2),
    ],
)
async def test_cooldown_applies_only_to_selected_platforms(
    pipeline, monkeypatch, platforms, parser, url, count
):
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_platforms", platforms)
    sr = search(url, parser)
    await matchers.parser_handler(session(), sr)
    await matchers.parser_handler(session(user="10002"), sr)
    assert pipeline.parsed.await_count == count
    assert pipeline.sent.await_count == count * 2


@pytest.mark.asyncio
async def test_excluded_platforms_bypass_inflight_deduplication(pipeline, monkeypatch):
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_platforms", ["taptap"])
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
async def test_zero_minutes_allows_completed_repeats(pipeline, monkeypatch):
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_minutes", 0)
    sr = search("https://www.bilibili.com/video/BV1xx411c7mD", BilibiliParser)
    await matchers.parser_handler(session(), sr)
    await matchers.parser_handler(session(), sr)
    assert pipeline.parsed.await_count == 2
