"""解析统计"""

import asyncio
from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from threading import Thread

import aiosqlite
from anyio import Path
from nonebot import logger

from .config import pconfig

STATS_FILENAME = "stats.db"
BUCKET_SECONDS = 15 * 60
"""聚合桶宽度，需整除所有时区偏移"""

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS parse_events ("
    "id INTEGER PRIMARY KEY, "
    "ts INTEGER NOT NULL, "
    "platform TEXT NOT NULL, "
    "target TEXT NOT NULL, "
    "success INTEGER NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_parse_events_ts "
    "ON parse_events (ts, platform, success, target)",
    "CREATE INDEX IF NOT EXISTS idx_parse_events_target "
    "ON parse_events (target, ts, platform, success)",
)
_INSERT = "INSERT INTO parse_events (ts, platform, target, success) VALUES (?, ?, ?, ?)"


@dataclass(frozen=True, slots=True)
class ParseRecord:
    """一次解析事件"""

    id: int
    time: datetime
    """解析时间，带本地时区"""
    platform: str
    target: str
    """会话标识，独立版为空字符串"""
    success: bool

    @property
    def timestamp(self) -> int:
        return int(self.time.timestamp())


@dataclass(slots=True)
class StatsCount:
    success: int = 0
    failure: int = 0

    @property
    def total(self) -> int:
        return self.success + self.failure

    def add(self, success: int, failure: int) -> None:
        self.success += success
        self.failure += failure


@dataclass(slots=True)
class ParseStatsSummary:
    """统计查询结果

    - ``platforms``/``targets`` 按总次数降序
    - ``daily`` 按日期升序，包含无记录的日期
    - ``hourly`` 为 0-23 时的分布，包含无记录的小时
    """

    days: int
    since: date
    until: date
    target: str | None
    total: StatsCount = field(default_factory=StatsCount)
    platforms: dict[str, StatsCount] = field(default_factory=dict)
    targets: dict[str, StatsCount] = field(default_factory=dict)
    daily: dict[date, StatsCount] = field(default_factory=dict)
    hourly: dict[int, StatsCount] = field(
        default_factory=lambda: {hour: StatsCount() for hour in range(24)}
    )


def _sorted_counts(counts: dict[str, StatsCount]) -> dict[str, StatsCount]:
    return dict(sorted(counts.items(), key=lambda item: (-item[1].total, item[0])))


def _to_counts(rows: Iterable[tuple[str, int, int]]) -> dict[str, StatsCount]:
    return _sorted_counts(
        {key: StatsCount(success, total - success) for key, success, total in rows}
    )


def _where(
    since: datetime | None,
    until: datetime | None,
    target: str | None,
    platform: str | None,
) -> tuple[str, list[int | str]]:
    clauses: list[str] = []
    params: list[int | str] = []
    if target is not None:
        clauses.append("target = ?")
        params.append(target)
    if since is not None:
        clauses.append("ts >= ?")
        params.append(int(since.timestamp()))
    if until is not None:
        clauses.append("ts < ?")
        params.append(int(until.timestamp()))
    if platform is not None:
        clauses.append("platform = ?")
        params.append(platform)
    return (f" WHERE {' AND '.join(clauses)}" if clauses else ""), params


def _daemonize(connection: aiosqlite.Connection) -> None:
    """长连接的工作线程设为守护线程，忘记关闭也不会卡住进程退出

    aiosqlite<0.20 的连接本身是 Thread，之后版本改为持有 ``_thread``
    """
    thread = connection if isinstance(connection, Thread) else None
    thread = thread or getattr(connection, "_thread", None)
    if isinstance(thread, Thread) and not thread.is_alive():
        thread.daemon = True


class ParseStats:
    """解析统计"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._initialized: Path | None = None
        self._writer: aiosqlite.Connection | None = None
        self._writer_path: Path | None = None
        self._lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None

    @property
    def db_path(self) -> Path:
        return self._path or pconfig.data_dir / STATS_FILENAME

    def _get_lock(self) -> asyncio.Lock:
        # asyncio.Lock 绑定首次使用的事件循环；独立版可能多次 asyncio.run
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    async def _open(self, path: Path) -> aiosqlite.Connection:
        if self._initialized != path:
            await path.parent.mkdir(parents=True, exist_ok=True)
        pending = aiosqlite.connect(str(path), timeout=10)
        _daemonize(pending)
        connection = await pending
        try:
            await connection.execute("PRAGMA synchronous=NORMAL")
            if self._initialized != path:
                await connection.execute("PRAGMA journal_mode=WAL")
                for statement in _SCHEMA:
                    await connection.execute(statement)
                await connection.commit()
                self._initialized = path
        except BaseException:
            await connection.close()
            raise
        return connection

    @asynccontextmanager
    async def _reader(self) -> AsyncGenerator[aiosqlite.Connection]:
        connection = await self._open(self.db_path)
        try:
            yield connection
        finally:
            await connection.close()

    async def _get_writer(self) -> aiosqlite.Connection:
        path = self.db_path
        if self._writer is not None and self._writer_path != path:
            await self._close_writer()
        if self._writer is None:
            self._writer = await self._open(path)
            self._writer_path = path
        return self._writer

    async def _close_writer(self) -> None:
        writer, self._writer, self._writer_path = self._writer, None, None
        if writer is not None:
            await writer.close()

    async def aclose(self) -> None:
        """关闭写入长连接；之后再次记录会自动重新打开"""
        async with self._get_lock():
            await self._close_writer()

    async def record(
        self,
        platform: str,
        target: str = "",
        *,
        success: bool,
        at: datetime | None = None,
    ) -> None:
        """记录一次解析

        :param at: 解析时间，默认当前时间；无时区的时间视为本地时间
        """
        timestamp = int((at or datetime.now()).timestamp())
        row = timestamp, platform, target, int(success)
        try:
            async with self._get_lock():
                writer = await self._get_writer()
                try:
                    await writer.execute(_INSERT, row)
                    await writer.commit()
                except Exception:
                    # 连接可能已损坏，丢弃后下次重新打开
                    await self._close_writer()
                    raise
        except Exception as e:
            logger.exception(f"记录解析统计失败: {e!r}")

    async def records(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        *,
        target: str | None = None,
        platform: str | None = None,
        limit: int | None = None,
    ) -> list[ParseRecord]:
        """按时间升序返回 ``[since, until)`` 内的原始解析记录"""
        if not await self.db_path.exists():
            return []
        where, params = _where(since, until, target, platform)
        sql = (
            f"SELECT id, ts, platform, target, success FROM parse_events{where} "
            "ORDER BY ts, id"
        )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        async with self._reader() as connection:
            rows = await connection.execute_fetchall(sql, params)
        return [
            ParseRecord(
                id=row_id,
                time=datetime.fromtimestamp(ts).astimezone(),
                platform=row_platform,
                target=row_target,
                success=bool(success),
            )
            for row_id, ts, row_platform, row_target, success in rows
        ]

    async def query(
        self, days: int = 7, target: str | None = None
    ) -> ParseStatsSummary:
        """查询最近 ``days`` 天（含今天）的统计；``target`` 为空时统计全部会话"""
        if days < 1:
            raise ValueError("统计天数必须大于 0")
        until = date.today()
        since = until - timedelta(days=days - 1)
        summary = ParseStatsSummary(
            days=days,
            since=since,
            until=until,
            target=target,
            daily={since + timedelta(days=i): StatsCount() for i in range(days)},
        )
        if not await self.db_path.exists():
            return summary

        where, params = _where(
            datetime.combine(since, time.min),
            datetime.combine(until + timedelta(days=1), time.min),
            target,
            None,
        )
        tail = f" FROM parse_events{where} GROUP BY 1"
        aggregate = "SUM(success), COUNT(*)"
        async with self._reader() as connection:
            buckets = await connection.execute_fetchall(
                f"SELECT ts / {BUCKET_SECONDS}, {aggregate}{tail}",
                params,
            )
            platforms = await connection.execute_fetchall(
                f"SELECT platform, {aggregate}{tail}", params
            )
            targets = (
                await connection.execute_fetchall(
                    f"SELECT target, {aggregate}{tail}", params
                )
                if target is None
                else []
            )

        for bucket, success, total in buckets:
            moment = datetime.fromtimestamp(bucket * BUCKET_SECONDS)
            failure = total - success
            summary.total.add(success, failure)
            summary.hourly[moment.hour].add(success, failure)
            if (count := summary.daily.get(moment.date())) is not None:
                count.add(success, failure)
        summary.platforms = _to_counts(platforms)  # pyright: ignore[reportArgumentType]
        summary.targets = (
            _to_counts(targets)  # pyright: ignore[reportArgumentType]
            if target is None
            else (
                {target: StatsCount(summary.total.success, summary.total.failure)}
                if summary.total.total
                else {}
            )
        )
        return summary


STATS = ParseStats()
"""全局解析统计实例"""


async def query_stats(days: int = 7, target: str | None = None) -> ParseStatsSummary:
    """查询解析统计"""
    return await STATS.query(days, target)


async def query_records(
    since: datetime | None = None,
    until: datetime | None = None,
    *,
    target: str | None = None,
    platform: str | None = None,
    limit: int | None = None,
) -> list[ParseRecord]:
    """查询原始解析记录"""
    return await STATS.records(
        since, until, target=target, platform=platform, limit=limit
    )


async def close_stats() -> None:
    """关闭统计数据库连接"""
    await STATS.aclose()
