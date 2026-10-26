"""Process-local, time-limited cooldown for repeated parsing on all platforms."""

import asyncio
from collections import OrderedDict
from collections.abc import AsyncGenerator, Hashable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import time

from ..data import ParseResult
from .rule import SearchResult


@dataclass(slots=True)
class ParseAttempt:
    succeeded: bool = False
    result: "ParseResult | None" = None
    output_started: bool = False


@dataclass(slots=True)
class _ParseGroup:
    attempt: ParseAttempt = field(default_factory=ParseAttempt)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0
    attempts: int = 0


class CommunityParseDeduplicator:
    def __init__(self, *, window_seconds: float = 1800):
        self.window_seconds = window_seconds
        self._recent: OrderedDict[Hashable, tuple[float, ParseAttempt]] = OrderedDict()
        self._active: dict[Hashable, _ParseGroup] = {}

    @asynccontextmanager
    async def acquire(self, key: Hashable) -> AsyncGenerator[ParseAttempt | None]:
        now = time.monotonic()
        while (
            self._recent
            and next(iter(self._recent.values()))[0] + self.window_seconds <= now
        ):
            self._recent.popitem(last=False)
        if recent := self._recent.get(key):
            yield recent[1]
            return

        group = self._active.get(key)
        if group is None:
            group = self._active[key] = _ParseGroup()
        group.users += 1
        try:
            async with group.lock:
                attempt = group.attempt
                if attempt.succeeded:
                    yield attempt
                elif attempt.output_started or group.attempts == 2:
                    yield None
                else:
                    # One initial attempt and at most one handoff before output.
                    group.attempts += 1
                    yield attempt
        finally:
            group.users -= 1
            if not group.users:
                self._active.pop(key)


community_parse_dedup = CommunityParseDeduplicator()

_CONTENT_FIELDS = {
    "www.taptap.cn": ("taptap", "moment_id"),
    "ds.163.com": ("ds", "feed_id"),
}


def community_parse_key(target_key: str, sr: SearchResult) -> tuple[str, ...]:
    source_field = _CONTENT_FIELDS.get(sr.keyword.lower())
    if source_field is not None:
        source, field = source_field
        if content_id := sr.searched.get(field):
            # Canonical IDs fold moment/explore and feed/article URL variants.
            return source, target_key, str(content_id)
    return "parse", target_key, sr.cache_key
