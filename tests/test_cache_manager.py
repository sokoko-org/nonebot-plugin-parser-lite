"""验证缓存管理器的关键行为"""

from __future__ import annotations

import asyncio
import time

import pytest
from render_test_support import SyncPath

from nonebot_plugin_parser_lite.utils import cache as cache_module
from nonebot_plugin_parser_lite.utils.cache import CacheManager


@pytest.fixture
def patched_cache_dir(tmp_path: SyncPath, monkeypatch: pytest.MonkeyPatch):
    """把插件缓存根目录指到临时目录，并清空锁状态与索引"""

    from anyio import Path

    class _Cfg:
        cache_dir = Path(tmp_path)

    monkeypatch.setattr(cache_module, "pconfig", _Cfg)
    CacheManager._write_locks.clear()
    CacheManager._index.clear()
    CacheManager._dirs_ready.clear()
    return tmp_path


@pytest.mark.asyncio
async def test_set_then_get_returns_entry(patched_cache_dir: SyncPath):
    """写入后同步 get 立即返回正确条目"""

    media_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
    base = media_dir / "hello"
    payload = base.with_suffix(".webp")
    data = b"x" * 1024
    await payload.write_bytes(data)
    await CacheManager.set_cached_file(base, payload, size_bytes=len(data))

    entry = CacheManager.get_cached_entry(base)
    assert entry is not None
    assert entry.path == payload
    assert entry.suffix == ".webp"
    assert entry.size_bytes == len(data)


@pytest.mark.asyncio
async def test_cache_miss_returns_none(patched_cache_dir: SyncPath):
    media_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
    assert CacheManager.get_cached_entry(media_dir / "nope") is None


@pytest.mark.asyncio
async def test_warmup_rebuilds_index_from_disk(patched_cache_dir: SyncPath):
    """重启后 warmup 应从磁盘恢复索引"""

    media_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
    base = media_dir / "survivor"
    payload = base.with_suffix(".mp4")
    await payload.write_bytes(b"video")
    await CacheManager.set_cached_file(base, payload, size_bytes=5)

    # 模拟重启
    CacheManager._index.clear()
    CacheManager._dirs_ready.clear()
    await CacheManager.ensure_dir(CacheManager.MEDIA)

    entry = CacheManager.get_cached_entry(base)
    assert entry is not None
    assert entry.size_bytes == 5


@pytest.mark.asyncio
async def test_orphan_meta_is_cleaned_on_warmup(patched_cache_dir: SyncPath):
    """payload 消失的 .meta 应在 warmup 阶段被清除"""

    media_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
    base = media_dir / "orphan"
    payload = base.with_suffix(".jpg")
    await payload.write_bytes(b"img")
    await CacheManager.set_cached_file(base, payload)
    await payload.unlink()

    CacheManager._index.clear()
    CacheManager._dirs_ready.clear()
    await CacheManager.ensure_dir(CacheManager.MEDIA)

    assert CacheManager.get_cached_entry(base) is None
    assert not await base.with_suffix(".meta").exists()


@pytest.mark.asyncio
async def test_expired_entry_is_cleaned_on_warmup(patched_cache_dir: SyncPath):
    """超过 TTL 的条目在 warmup 时直接清掉，不进入索引"""

    media_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
    base = media_dir / "old"
    payload = base.with_suffix(".jpg")
    await payload.write_bytes(b"img")
    await CacheManager.set_cached_file(base, payload)

    import os
    old = time.time() - 3 * 3600
    for suffix in (".jpg", ".meta"):
        os.utime(str(base.with_suffix(suffix)), (old, old))

    CacheManager._index.clear()
    CacheManager._dirs_ready.clear()
    await CacheManager.ensure_dir(CacheManager.MEDIA)

    assert CacheManager.get_cached_entry(base) is None
    assert not await base.with_suffix(".jpg").exists()
    assert not await base.with_suffix(".meta").exists()


@pytest.mark.asyncio
async def test_clean_expired_uses_last_hit(patched_cache_dir: SyncPath):
    """运行时清理按 last_hit 判定；命中后计时器重置"""

    media_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
    base = media_dir / "warm"
    payload = base.with_suffix(".jpg")
    await payload.write_bytes(b"img")
    await CacheManager.set_cached_file(base, payload)

    # 命中会刷新 last_hit
    assert CacheManager.get_cached_entry(base) is not None

    # 清理不应影响刚命中的条目
    await CacheManager.clean_expired()
    assert CacheManager.get_cached_entry(base) is not None

    # 把 last_hit 推到远古
    CacheManager._index[CacheManager.MEDIA][str(base)].last_hit = time.time() - 3 * 3600
    await CacheManager.clean_expired()
    assert CacheManager.get_cached_entry(base) is None
    assert not await payload.exists()


@pytest.mark.asyncio
async def test_write_lock_serializes_same_key():
    order: list[str] = []

    async def worker(name: str, delay: float) -> None:
        async with CacheManager.write_lock("same-key"):
            order.append(f"enter-{name}")
            await asyncio.sleep(delay)
            order.append(f"exit-{name}")

    await asyncio.gather(worker("a", 0.05), worker("b", 0.01))
    assert order[0].startswith("enter-")
    first = order[0].split("-", 1)[1]
    assert order[1] == f"exit-{first}"


@pytest.mark.asyncio
async def test_write_lock_releases_memory():
    async with CacheManager.write_lock("ephemeral"):
        pass
    assert "ephemeral" not in CacheManager._write_locks


@pytest.mark.asyncio
async def test_set_cached_file_persists_extra(patched_cache_dir: SyncPath):
    media_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
    base = media_dir / "extra"
    payload = base.with_suffix(".mp4")
    await payload.write_bytes(b"v")
    entry = await CacheManager.set_cached_file(
        base, payload, size_bytes=1, extra={"codec": "h264"}
    )
    assert entry.extra == {"codec": "h264"}

    # 重建索引后 extra 仍可读
    CacheManager._index.clear()
    CacheManager._dirs_ready.clear()
    await CacheManager.ensure_dir(CacheManager.MEDIA)
    rehydrated = CacheManager.get_cached_entry(base)
    assert rehydrated is not None
    assert rehydrated.extra.get("codec") == "h264"

