import json

from nonebot import get_driver, on_command
from nonebot.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot_plugin_uninfo import ADMIN, Uninfo

from ..config import pconfig

_DISABLED_GROUPS_PATH = pconfig.data_dir / "disabled_groups.json"
_DISABLED_GROUPS_SET: set[str] = set()


async def load_or_initialize_set() -> set[str]:
    """加载或初始化关闭解析的名单"""
    # 判断是否存在
    if not await _DISABLED_GROUPS_PATH.exists():
        await _DISABLED_GROUPS_PATH.write_text(json.dumps([]))
    return set(json.loads(await _DISABLED_GROUPS_PATH.read_text()))


async def save_disabled_groups():
    """保存关闭解析的名单"""
    await _DISABLED_GROUPS_PATH.write_text(json.dumps(list(_DISABLED_GROUPS_SET)))


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
    group_key = f"{session.scope}_{session.scene_path}"
    if group_key in _DISABLED_GROUPS_SET:
        _DISABLED_GROUPS_SET.remove(group_key)
        await save_disabled_groups()
        await matcher.finish("解析已开启")
    else:
        await matcher.finish("解析已开启，无需重复开启")


@on_command(
    "关闭解析", rule=to_me(), permission=SUPERUSER | ADMIN(), block=True
).handle()
async def _(matcher: Matcher, session: Uninfo):
    """关闭解析"""
    group_key = f"{session.scope}_{session.scene_path}"
    if group_key not in _DISABLED_GROUPS_SET:
        _DISABLED_GROUPS_SET.add(group_key)
        await save_disabled_groups()
        await matcher.finish("解析已关闭")
    else:
        await matcher.finish("解析已关闭，无需重复关闭")
