import asyncio
from collections.abc import AsyncGenerator
import contextlib
from dataclasses import dataclass, field
import json
import os
import time
from typing import ClassVar

from anyio import Path

from ..config import pconfig
from .common import safe_unlink
from .log import logger


@dataclass(frozen=True, slots=True)
class CachePolicy:
    subdir: str
    ttl_seconds: int


@dataclass(slots=True)
class CacheEntry:
    """内存里的缓存条目，覆盖业务可能查询的所有属性"""

    path: Path
    size_bytes: int
    last_hit: float = field(default_factory=time.time)
    extra: dict[str, object] = field(default_factory=dict)
    # 已经写回磁盘的 last_hit；clean_expired 用它判断是否需要 flush
    _persisted_hit: float = field(default=0.0, repr=False)

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()


def _sync_scan_tree(root: str) -> list[tuple[str, float]]:
    """递归枚举文件并一次性拿到 mtime"""
    stack: list[str] = [root]
    results: list[tuple[str, float]] = []
    while stack:
        try:
            scanner = os.scandir(stack.pop())
        except OSError:
            continue
        with scanner:
            for entry in scanner:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            mtime = entry.stat(follow_symlinks=False).st_mtime
                        except OSError:
                            mtime = 0.0
                        results.append((entry.path, mtime))
                except OSError:
                    continue
    return results


def _sync_read_meta(meta_path: str) -> dict | None:
    try:
        with open(meta_path, encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _sync_write_meta(meta_path: str, payload: dict) -> bool:
    """原子写入 .meta。先写临时文件再 rename"""
    tmp = f"{meta_path}.part"
    try:
        with open(tmp, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, meta_path)
        return True
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        return False


# (file_path, mtime) 之于每个 .meta
_MetaRaw = tuple[str, float, dict]
# (file_path, mtime, size) 之于每个 payload
_PayloadRaw = tuple[str, float, int]


_RESERVED_META_KEYS = frozenset({"v", "suffix", "size", "last_hit"})


def _coerce_number(value: object, fallback: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback


def _entry_from_meta(meta: _MetaRaw, payload: _PayloadRaw) -> CacheEntry:
    _meta_path, meta_mtime, data = meta
    payload_path, payload_mtime, payload_size = payload
    extra = {k: v for k, v in data.items() if k not in _RESERVED_META_KEYS}
    # last_hit 取三源最大：JSON 显式值 / .meta mtime (周期 flush) / payload mtime
    stored_hit = _coerce_number(data.get("last_hit", 0), 0.0)
    disk_hit = max(stored_hit, meta_mtime, payload_mtime)
    return CacheEntry(
        path=Path(payload_path),
        size_bytes=int(_coerce_number(data.get("size", payload_size), payload_size)),
        last_hit=disk_hit,
        _persisted_hit=disk_hit,
        extra=extra,
    )


def _entry_from_payload(payload: _PayloadRaw) -> CacheEntry:
    payload_path, mtime, size = payload
    return CacheEntry(
        path=Path(payload_path), size_bytes=size, last_hit=mtime, _persisted_hit=mtime
    )


def _classify_files(
    root: str, ttl: int, now: float
) -> tuple[dict[str, _MetaRaw], dict[str, _PayloadRaw], list[str]]:
    """把目录下的文件分成 metas / payloads / 过期文件三类"""
    payloads: dict[str, _PayloadRaw] = {}
    metas: dict[str, _MetaRaw] = {}
    expired: list[str] = []

    for file_path, mtime in _sync_scan_tree(root):
        if file_path.endswith((".part", ".tmp")):
            if now - mtime >= ttl:
                expired.append(file_path)
            continue

        stem, dot, suffix = file_path.rpartition(".")
        if not dot:
            continue

        if suffix.lower() == "meta":
            data = _sync_read_meta(file_path)
            if data is None:
                expired.append(file_path)
            else:
                metas[stem] = (file_path, mtime, data)
        else:
            try:
                size = os.path.getsize(file_path)
            except OSError:
                size = 0
            payloads[stem] = (file_path, mtime, size)

    return metas, payloads, expired


def _sync_build_index(
    root: str, ttl: int, now: float
) -> tuple[dict[str, CacheEntry], list[str]]:
    """扫目录重建索引，返回 (条目, 过期文件列表)"""
    metas, payloads, expired = _classify_files(root, ttl, now)
    index: dict[str, CacheEntry] = {}

    for stem, meta in metas.items():
        payload = payloads.pop(stem, None)
        if payload is None:
            # 孤立 .meta，payload 已经消失
            expired.append(meta[0])
            continue
        candidate = _entry_from_meta(meta, payload)
        if now - candidate.last_hit >= ttl:
            expired.extend((meta[0], payload[0]))
            continue
        index[stem] = candidate

    # 没有 .meta 的裸 payload：过 TTL 清掉，否则建最小索引
    for stem, payload in payloads.items():
        if now - payload[1] >= ttl:
            expired.append(payload[0])
        else:
            index[stem] = _entry_from_payload(payload)

    return index, expired


class CacheManager:
    """集中管理插件缓存目录与清理策略；运行时读写走内存索引"""

    MEDIA = "media"
    RENDER = "render"
    LOGO = "logo"
    STICKER = "sticker"

    _POLICIES: ClassVar[dict[str, CachePolicy]] = {
        MEDIA: CachePolicy("media", 60 * 60 * 2),
        RENDER: CachePolicy("render", 60 * 60 * 2),
        LOGO: CachePolicy("logo", 60 * 60 * 24 * 30),
        STICKER: CachePolicy("sticker", 60 * 60 * 24 * 15),
    }

    _index: ClassVar[dict[str, dict[str, CacheEntry]]] = {}
    _dirs_ready: ClassVar[set[str]] = set()
    _write_locks: ClassVar[dict[str, asyncio.Lock]] = {}

    @classmethod
    def cache_dir(cls, cache_type: str = MEDIA) -> Path:
        policy = cls._POLICIES.get(cache_type, cls._POLICIES[cls.MEDIA])
        return pconfig.cache_dir / policy.subdir if policy.subdir else pconfig.cache_dir

    @classmethod
    async def ensure_dir(cls, cache_type: str = MEDIA) -> Path:
        cache_dir = cls.cache_dir(cache_type)
        if cache_type not in cls._dirs_ready:
            await cache_dir.mkdir(parents=True, exist_ok=True)
            await cls._warmup(cache_type)
            cls._dirs_ready.add(cache_type)
        return cache_dir

    @classmethod
    async def warmup_all(cls) -> None:
        """启动时主动预热所有已知缓存目录的索引"""
        for cache_type in cls._POLICIES:
            await cls.ensure_dir(cache_type)

    @classmethod
    async def _warmup(cls, cache_type: str) -> None:
        """扫描目录重建内存索引，并顺带删除过期文件"""
        policy = cls._POLICIES[cache_type]
        root = str(cls.cache_dir(cache_type))
        index, expired = await asyncio.to_thread(
            _sync_build_index, root, policy.ttl_seconds, time.time()
        )
        cls._index[cache_type] = index
        if expired:
            await asyncio.gather(*(safe_unlink(Path(path)) for path in expired))
        logger.info(
            f"缓存索引就绪 [{cache_type}]: entries={len(index)}, cleaned={len(expired)}"
        )

    @classmethod
    def _cache_type_of(cls, base_path: Path) -> str:
        """根据路径所在目录推断 cache_type"""
        parent = base_path.parent.name
        return next(
            (
                cache_type
                for cache_type, policy in cls._POLICIES.items()
                if policy.subdir == parent
            ),
            cls.MEDIA,
        )

    @classmethod
    def get_cached_entry(cls, base_path: Path) -> CacheEntry | None:
        """O(1) 内存查询"""
        index = cls._index.setdefault(cls._cache_type_of(base_path), {})
        entry = index.get(str(base_path))
        if entry is not None:
            entry.last_hit = time.time()
        return entry

    @classmethod
    async def set_cached_file(
        cls,
        base_path: Path,
        file_path: Path,
        *,
        size_bytes: int | None = None,
        extra: dict[str, object] | None = None,
    ) -> CacheEntry:
        """落盘 .meta 并更新内存索引"""
        if size_bytes is None:
            try:
                size_bytes = (await file_path.stat()).st_size
            except OSError:
                size_bytes = 0

        now = time.time()
        payload: dict[str, object] = {
            "v": 1,
            "suffix": file_path.suffix.lower(),
            "size": size_bytes,
            "last_hit": now,
        }
        if extra:
            payload |= {k: v for k, v in extra.items() if k not in _RESERVED_META_KEYS}

        meta_path = str(base_path.with_suffix(".meta"))
        if not await asyncio.to_thread(_sync_write_meta, meta_path, payload):
            logger.warning(f"写入缓存索引 {meta_path} 失败")

        entry = CacheEntry(
            path=file_path,
            size_bytes=size_bytes,
            last_hit=now,
            _persisted_hit=now,
            extra={k: v for k, v in extra.items() if k not in _RESERVED_META_KEYS}
            if extra
            else {},
        )
        cls._index.setdefault(cls._cache_type_of(base_path), {})[str(base_path)] = entry
        return entry

    @classmethod
    @contextlib.asynccontextmanager
    async def write_lock(cls, key: str) -> AsyncGenerator[None]:
        """按 key 加锁，防止同一产物被并发重复生产"""
        lock = cls._write_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            cls._write_locks[key] = lock
        try:
            async with lock:
                yield
        finally:
            if not lock.locked() and cls._write_locks.get(key) is lock:
                cls._write_locks.pop(key, None)

    @classmethod
    async def clean_expired(cls) -> None:
        """清理过期条目，刷新 dirty last_hit，回收游离 .part/.tmp"""
        now = time.time()
        totals: dict[str, int] = {}
        expired_paths: list[Path] = []
        expired_stems: list[tuple[str, str]] = []
        dirty: list[tuple[str, CacheEntry]] = []

        for cache_type, policy in cls._POLICIES.items():
            if cache_type not in cls._dirs_ready:
                continue
            index = cls._index.get(cache_type, {})
            totals[cache_type] = len(index)
            for stem, entry in index.items():
                if now - entry.last_hit >= policy.ttl_seconds:
                    expired_paths.extend((entry.path, Path(f"{stem}.meta")))
                    expired_stems.append((cache_type, stem))
                elif entry.last_hit - entry._persisted_hit >= policy.ttl_seconds / 4:
                    dirty.append((stem, entry))

        expired_paths.extend(
            await asyncio.to_thread(cls._collect_transient_leftovers, now)
        )

        for cache_type, stem in expired_stems:
            cls._index[cache_type].pop(stem, None)

        if dirty:
            await asyncio.to_thread(cls._flush_dirty_hits, dirty)

        if not expired_paths:
            logger.info(
                "缓存清理完成，无过期文件"
                + (f"; flushed={len(dirty)}" if dirty else "")
                + "; "
                + ", ".join(f"{name}={count}" for name, count in totals.items())
            )
            return

        await asyncio.gather(*(safe_unlink(path) for path in expired_paths))
        logger.success(
            f"已清理 {len(expired_stems)} 组缓存文件"
            + (f"; flushed={len(dirty)}" if dirty else "")
            + "; "
            + ", ".join(f"{name}={count}" for name, count in totals.items())
        )

    @staticmethod
    def _flush_dirty_hits(entries: list[tuple[str, "CacheEntry"]]) -> None:
        """批量把 last_hit 写入 .meta mtime（os.utime 不重写 JSON）"""
        for stem, entry in entries:
            with contextlib.suppress(OSError):
                os.utime(f"{stem}.meta", (entry.last_hit, entry.last_hit))
            entry._persisted_hit = entry.last_hit

    @classmethod
    def _collect_transient_leftovers(cls, now: float) -> list[Path]:
        """同步扫磁盘，返回过 TTL 的 .part/.tmp 文件"""
        leftovers: list[Path] = []
        for cache_type, policy in cls._POLICIES.items():
            if cache_type not in cls._dirs_ready:
                continue
            root = str(cls.cache_dir(cache_type))
            leftovers.extend(
                Path(file_path)
                for file_path, mtime in _sync_scan_tree(root)
                if file_path.endswith((".part", ".tmp"))
                and now - mtime >= policy.ttl_seconds
            )
        return leftovers
