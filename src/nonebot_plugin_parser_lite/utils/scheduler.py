"""Small asyncio-native periodic task scheduler."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

from .log import logger


@dataclass(slots=True)
class _PeriodicJob:
    callback: Callable[[], Awaitable[None]]
    seconds: float
    task: asyncio.Task[None]


class PeriodicScheduler:
    def __init__(self) -> None:
        self._jobs: dict[str, _PeriodicJob] = {}

    @property
    def job_ids(self) -> tuple[str, ...]:
        return tuple(self._jobs)

    def add_job(
        self,
        callback: Callable[[], Awaitable[None]],
        *,
        seconds: float,
        id: str,
    ) -> None:
        current = self._jobs.get(id)
        if current is not None and not current.task.done():
            return
        loop = asyncio.get_running_loop()
        task = loop.create_task(self._run(id, callback, seconds), name=id)
        self._jobs[id] = _PeriodicJob(callback, seconds, task)
        logger.debug("已注册异步定时任务 %s，间隔 %.0f 秒", id, seconds)

    async def _run(
        self,
        job_id: str,
        callback: Callable[[], Awaitable[None]],
        seconds: float,
    ) -> None:
        while True:
            try:
                await asyncio.sleep(seconds)
                await callback()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("异步定时任务 %s 执行失败", job_id)

    async def shutdown(self) -> None:
        tasks = [job.task for job in self._jobs.values()]
        self._jobs.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task


scheduler = PeriodicScheduler()
