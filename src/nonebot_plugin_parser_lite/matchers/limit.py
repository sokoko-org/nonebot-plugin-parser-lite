import asyncio
from collections import OrderedDict
from collections.abc import AsyncGenerator, Hashable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import time
from typing import ClassVar

from ..config import pconfig
from ..data import ParseResult


@dataclass(slots=True)
class ParseState:
    succeeded: bool = False
    result: ParseResult | None = None
    output_started: bool = False


@dataclass(slots=True)
class PendingParse:
    state: ParseState = field(default_factory=ParseState)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0
    attempts: int = 0


class ParseCooldown:
    recent: ClassVar[OrderedDict[Hashable, tuple[float, ParseState]]] = OrderedDict()
    active: ClassVar[dict[Hashable, PendingParse]] = {}

    @classmethod
    @asynccontextmanager
    async def acquire(cls, key: Hashable) -> AsyncGenerator[ParseState | None]:

        window_seconds = pconfig.parse_dedup_minutes * 60
        now = time.monotonic()
        while cls.recent and next(iter(cls.recent.values()))[0] + window_seconds <= now:
            cls.recent.popitem(last=False)
        if recent := cls.recent.get(key):
            yield recent[1]
            return

        pending = cls.active.get(key)
        if pending is None:
            pending = cls.active[key] = PendingParse()
        pending.users += 1
        try:
            async with pending.lock:
                state = pending.state
                if state.succeeded:
                    yield state
                elif state.output_started or pending.attempts == 2:
                    yield None
                else:
                    pending.attempts += 1
                    try:
                        yield state
                    finally:
                        if (
                            state.succeeded and window_seconds > 0
                        ):  # sourcery skip: remove-redundant-if
                            cls.recent[key] = time.monotonic(), state
        finally:
            pending.users -= 1
            if not pending.users:
                cls.active.pop(key)
