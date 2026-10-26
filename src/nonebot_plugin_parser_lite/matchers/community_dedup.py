"""Process-local, time-limited cooldown for repeated parsing on all platforms."""

import asyncio
from collections import OrderedDict
from collections.abc import AsyncIterator, Hashable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..data import ParseResult


@dataclass(slots=True)
class ParseAttempt:
    succeeded: bool = False
    result: "ParseResult | None" = None
    output_started: bool = False
    retry_claimed: bool = False
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    waiters: int = 0


class CommunityParseDeduplicator:
    def __init__(self, *, window_seconds: float = 1800):
        self.window_seconds = window_seconds
        self._recent: OrderedDict[Hashable, tuple[float, ParseAttempt]] = OrderedDict()
        self._active: dict[Hashable, ParseAttempt] = {}

    @asynccontextmanager
    async def acquire(self, key: Hashable) -> AsyncIterator[ParseAttempt | None]:
        now = time.monotonic()
        while self._recent and next(iter(self._recent.values()))[0] + self.window_seconds <= now:
            self._recent.popitem(last=False)
        if recent := self._recent.get(key):
            yield recent[1]
            return

        if attempt := self._active.get(key):
            attempt.waiters += 1
            try:
                # The elected retry clears the event before other waiters resume.
                while not attempt.finished.is_set():
                    await attempt.finished.wait()
                if attempt.succeeded:
                    yield attempt
                    return
                if attempt.retry_claimed or attempt.output_started:
                    yield None
                    return
                attempt.retry_claimed = True
                attempt.finished.clear()
            finally:
                attempt.waiters -= 1
                if not attempt.waiters and attempt.finished.is_set():
                    if self._active.get(key) is attempt:
                        self._active.pop(key)
        else:
            attempt = ParseAttempt()
            self._active[key] = attempt
        try:
            yield attempt
        finally:
            if attempt.succeeded and self.window_seconds > 0:
                self._recent[key] = time.monotonic(), attempt
            attempt.finished.set()
            # Keep a failed first attempt until a waiter can claim its single retry.
            if attempt.succeeded or attempt.output_started or attempt.retry_claimed or not attempt.waiters:
                if self._active.get(key) is attempt:
                    self._active.pop(key)


community_parse_dedup = CommunityParseDeduplicator()


def community_parse_key(target_key: str, search_result) -> tuple[str, ...]:
    fields = {
        "www.taptap.cn": ("taptap", "moment_id"),
        "ds.163.com": ("ds", "feed_id"),
    }
    source_field = fields.get(search_result.keyword.lower())
    if source_field is not None:
        source, field = source_field
        if content_id := search_result.searched.get(field):
            # Canonical IDs fold moment/explore and feed/article URL variants.
            return source, target_key, str(content_id)
    return "parse", target_key, search_result.cache_key
