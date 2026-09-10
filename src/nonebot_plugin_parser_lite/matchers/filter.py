import asyncio
import json

from nonebot import get_driver, on_command
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot_plugin_uninfo import ADMIN, Uninfo

from ..config import pconfig

_DISABLED_GROUPS_PATH = pconfig.data_dir / "disabled_groups.json"
_DISABLED_GROUPS_SET: set[str] = set()
_DISABLED_GROUPS_LOCK = asyncio.Lock()


async def _write_disabled_groups() -> None:
    temp_path = _DISABLED_GROUPS_PATH.with_suffix(".json.tmp")
    try:
        await temp_path.write_text(
            json.dumps(sorted(_DISABLED_GROUPS_SET), ensure_ascii=False),
            encoding="utf-8",
        )
        await temp_path.replace(_DISABLED_GROUPS_PATH)
    finally:
        await temp_path.unlink(missing_ok=True)


async def load_or_initialize_set() -> set[str]:
    """加载或初始化关闭解析的名单"""
    if not await _DISABLED_GROUPS_PATH.exists():
        await _write_disabled_groups()
    return set(json.loads(await _DISABLED_GROUPS_PATH.read_text(encoding="utf-8")))


async def save_disabled_groups():
    """保存关闭解析的名单"""
    async with _DISABLED_GROUPS_LOCK:
        await _write_disabled_groups()


async def set_group_enabled(group_key: str, enabled: bool) -> bool:
    """原子更新群聊开关，返回状态是否发生变化。"""
    async with _DISABLED_GROUPS_LOCK:
        was_disabled = group_key in _DISABLED_GROUPS_SET
        if enabled:
            _DISABLED_GROUPS_SET.discard(group_key)
        else:
            _DISABLED_GROUPS_SET.add(group_key)
        changed = was_disabled == enabled
        if changed:
            await _write_disabled_groups()
        return changed


@get_driver().on_startup
async def init_disable_groups():
    """初始化关闭解析的名单"""
    global _DISABLED_GROUPS_SET
    _DISABLED_GROUPS_SET = await load_or_initialize_set()


# Rule
def is_enabled(session: Uninfo) -> bool:
    if f"{session.scope}_{session.user.id}" in pconfig.blacklist_users:
        # 黑名单用户，直接禁用
        return False
    if session.scene.is_private:
        return True
    # 群聊：看这个群 key 是否在关闭列表里
    return f"{session.scope}_{session.scene_path}" not in _DISABLED_GROUPS_SET


@on_command(
    "开启解析", rule=to_me(), permission=SUPERUSER | ADMIN(), block=True
).handle()
async def _(matcher: Matcher, session: Uninfo):
    """开启解析"""
    if session.scene.is_private:
        await matcher.finish("该命令仅用于群聊")
    group_key = f"{session.scope}_{session.scene_path}"
    if await set_group_enabled(group_key, enabled=True):
        await matcher.finish("解析已开启")
    else:
        await matcher.finish("解析已开启，无需重复开启")


@on_command(
    "关闭解析", rule=to_me(), permission=SUPERUSER | ADMIN(), block=True
).handle()
async def _(matcher: Matcher, session: Uninfo):
    """关闭解析"""
    if session.scene.is_private:
        await matcher.finish("该命令仅用于群聊")
    group_key = f"{session.scope}_{session.scene_path}"
    if await set_group_enabled(group_key, enabled=False):
        await matcher.finish("解析已关闭")
    else:
        await matcher.finish("解析已关闭，无需重复关闭")
