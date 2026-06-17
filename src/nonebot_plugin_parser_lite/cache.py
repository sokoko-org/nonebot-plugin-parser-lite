import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
import time
from typing import ClassVar

from anyio import Path
from nonebot import logger

from .config import pconfig
from .utils.common import safe_unlink


@dataclass(frozen=True, slots=True)
class CachePolicy:
    """缓存目录策略。ttl_seconds 为 None 时默认不清理。"""

    subdir: str
    ttl_seconds: int | None


class CacheManager:
    """集中管理插件缓存目录与清理策略。"""

    MEDIA = "media"
    RENDER = "render"
    LOGO = "logo"
    STICKER = "sticker"
    LEGACY = "legacy"

    _POLICIES: ClassVar[dict[str, CachePolicy]] = {
        MEDIA: CachePolicy("media", 60 * 60),
        RENDER: CachePolicy("render", 60 * 60),
        LOGO: CachePolicy("logo", None),
        STICKER: CachePolicy("sticker", 60 * 60 * 24 * 14),
        LEGACY: CachePolicy("", 60 * 60),
    }
    _MANAGED_DIRS: ClassVar[set[str]] = {
        policy.subdir for policy in _POLICIES.values() if policy.subdir
    }

    @classmethod
    def cache_dir(cls, cache_type: str = MEDIA) -> Path:
        policy = cls._POLICIES.get(cache_type, cls._POLICIES[cls.MEDIA])
        return pconfig.cache_dir / policy.subdir if policy.subdir else pconfig.cache_dir

    @classmethod
    async def ensure_dir(cls, cache_type: str = MEDIA) -> Path:
        cache_dir = cls.cache_dir(cache_type)
        await cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    @classmethod
    async def iter_files(cls, path: Path) -> AsyncIterator[Path]:
        if not await path.exists():
            return
        async for item in path.iterdir():
            if await item.is_file():
                yield item
            elif await item.is_dir():
                async for child in cls.iter_files(item):
                    yield child

    @classmethod
    async def _collect_expired_files(
        cls, cache_type: str, now: float
    ) -> tuple[int, list[Path]]:
        policy = cls._POLICIES[cache_type]
        if policy.ttl_seconds is None:
            return 0, []

        cache_dir = cls.cache_dir(cache_type)
        total = 0
        expired: list[Path] = []
        async for file in cls.iter_files(cache_dir):
            total += 1
            try:
                mtime = (await file.stat()).st_mtime
            except OSError:
                expired.append(file)
                continue

            if now - mtime >= policy.ttl_seconds:
                expired.append(file)
        return total, expired

    @classmethod
    async def _collect_legacy_expired_files(cls, now: float) -> tuple[int, list[Path]]:
        policy = cls._POLICIES[cls.LEGACY]
        assert policy.ttl_seconds is not None

        total = 0
        expired: list[Path] = []
        if not await pconfig.cache_dir.exists():
            return total, expired

        async for item in pconfig.cache_dir.iterdir():
            if await item.is_dir():
                continue
            if not await item.is_file():
                continue

            total += 1
            try:
                mtime = (await item.stat()).st_mtime
            except OSError:
                expired.append(item)
                continue

            if now - mtime >= policy.ttl_seconds:
                expired.append(item)
        return total, expired

    @classmethod
    async def clean_expired(cls) -> None:
        now = time.time()
        cleanup_types = (cls.MEDIA, cls.RENDER, cls.LOGO, cls.STICKER)

        totals: dict[str, int] = {}
        expired_files: list[Path] = []
        for cache_type in cleanup_types:
            total, expired = await cls._collect_expired_files(cache_type, now)
            totals[cache_type] = total
            expired_files.extend(expired)

        legacy_total, legacy_expired = await cls._collect_legacy_expired_files(now)
        totals[cls.LEGACY] = legacy_total
        expired_files.extend(legacy_expired)

        if not expired_files:
            logger.info(
                "缓存清理完成，无过期文件；"
                + ", ".join(f"{name}={count}" for name, count in totals.items())
            )
            return

        await asyncio.gather(*(safe_unlink(file) for file in expired_files))
        logger.success(
            f"已清理 {len(expired_files)} 个过期缓存文件；"
            + ", ".join(f"{name}={count}" for name, count in totals.items())
        )
