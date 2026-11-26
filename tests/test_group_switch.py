from unittest.mock import AsyncMock, patch

from anyio import Path
from matcher_test_support import ADMIN_QQ, CURRENT_GROUP, TARGET_GROUP
from matcher_test_support import command_context as context
from nonebot.internal.params import DependencyCache
from nonebot.matcher import matchers
from nonebot_plugin_alconna import Match, UniMessage
from nonebot_plugin_uninfo import Member, Role, get_session
import pytest

from nonebot_plugin_parser_lite.matchers import filter as switches


@pytest.fixture
def switch_state(monkeypatch, tmp_path):
    monkeypatch.setattr(
        switches, "_DISABLED_TARGETS_PATH", Path(tmp_path / "disabled.json")
    )
    monkeypatch.setattr(switches, "_DISABLED_TARGETS_SET", set())


async def run_switch(argument="", *, enabled=False, **kwargs):
    bot, event, session = context(**kwargs)
    handler = switches.handle_enable if enabled else switches.handle_disable
    with patch.object(UniMessage, "send", autospec=True) as send:
        await handler(bot, event, session, Match(argument, bool(argument)))
    send.assert_awaited_once()
    assert send.call_args.kwargs == {"reply_to": True}
    return send.call_args.args[0].extract_plain_text(), session


@pytest.mark.asyncio
async def test_superuser_cross_group_persists_and_leaves_source_group_enabled(
    switch_state,
):
    message, source = await run_switch(TARGET_GROUP)
    assert TARGET_GROUP in message
    assert "已关闭" in message
    target = context()[2]
    target.scene.id = TARGET_GROUP
    assert switches.is_enabled(source)
    assert not switches.is_enabled(target)
    switches._DISABLED_TARGETS_SET.clear()
    await switches.init_disabled_targets()
    assert not switches.is_enabled(target)
    assert switches.is_enabled(source)
    message, _ = await run_switch(TARGET_GROUP)
    assert "无需重复关闭" in message


@pytest.mark.asyncio
async def test_group_admin_target_silently_falls_back_to_current_group(switch_state):
    # Handler validation; registered command permissions are checked separately.
    for target in (TARGET_GROUP, CURRENT_GROUP):
        message, source = await run_switch(target, superuser=False)
        assert message == f"QQClient_GROUP_{CURRENT_GROUP} 解析已关闭"
        assert not switches.is_enabled(source)
        assert switches._DISABLED_TARGETS_SET == {f"QQClient_GROUP_{CURRENT_GROUP}"}
        await run_switch(target, enabled=True, superuser=False)
    assert switches._DISABLED_TARGETS_SET == set()
    message, source = await run_switch(superuser=False)
    assert "解析已关闭" in message
    assert not switches.is_enabled(source)
    message, _ = await run_switch(enabled=True, superuser=False)
    assert "解析已开启" in message
    assert switches.is_enabled(source)


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [switches.handle_enable, switches.handle_disable])
@pytest.mark.parametrize(
    ("superuser", "role", "allowed"),
    [
        (False, "ADMINISTRATOR", True),
        (False, "OWNER", True),
        (False, "MEMBER", False),
        (True, "MEMBER", True),
    ],
)
async def test_registered_command_permission(handler, superuser, role, allowed):
    registered = next(
        matcher
        for group in matchers.values()
        for matcher in group
        if any(dependent.call is handler for dependent in matcher.handlers)
    )
    bot, event, session = context(superuser=superuser)
    session.member = Member(session.user, roles=[Role(role)])
    cached_session = DependencyCache()
    cached_session.set_result(session)
    assert (
        await registered.permission(
            bot, event, dependency_cache={get_session: cached_session}
        )
        is allowed
    )


@pytest.mark.asyncio
async def test_enable_target_only_and_prefixed_superuser_identity(switch_state):
    bot, event, session = context()
    bot.config.superusers = {f"onebot:{ADMIN_QQ}"}
    switches._DISABLED_TARGETS_SET.update(
        {f"QQClient_GROUP_{CURRENT_GROUP}", f"QQClient_GROUP_{TARGET_GROUP}"}
    )
    with patch.object(UniMessage, "send", autospec=True) as send:
        await switches.handle_enable(bot, event, session, Match(TARGET_GROUP, True))
    assert switches._DISABLED_TARGETS_SET == {f"QQClient_GROUP_{CURRENT_GROUP}"}
    assert TARGET_GROUP in send.call_args.args[0].extract_plain_text()


@pytest.mark.asyncio
async def test_private_superuser_controls_current_or_target_user(switch_state):
    message, source = await run_switch(private=True)
    assert "解析已关闭" in message
    assert not switches.is_enabled(source)
    assert not switches.is_enabled(context()[2])
    message, _ = await run_switch(TARGET_GROUP, private=True)
    assert TARGET_GROUP in message
    target_user = context()[2]
    target_user.user.id = TARGET_GROUP
    assert not switches.is_enabled(target_user)
    assert switches._DISABLED_TARGETS_SET == {
        f"QQClient_USER_{ADMIN_QQ}",
        f"QQClient_USER_{TARGET_GROUP}",
    }
    await run_switch(TARGET_GROUP, private=True, enabled=True)
    assert switches.is_enabled(target_user)
    assert not switches.is_enabled(source)
    assert switches._DISABLED_TARGETS_SET == {f"QQClient_USER_{ADMIN_QQ}"}
    await run_switch(private=True, enabled=True)
    assert not switches._DISABLED_TARGETS_SET

    await run_switch(private=True)
    switches._DISABLED_TARGETS_SET.clear()
    await switches.init_disabled_targets()
    assert not switches.is_enabled(source)
    assert not switches.is_enabled(context()[2])
    other_group = context()[2]
    other_group.scene.id = TARGET_GROUP
    assert not switches.is_enabled(other_group)
    other_user = context()[2]
    other_user.user.id = "10002"
    assert switches.is_enabled(other_user)
    await run_switch(private=True, enabled=True)
    assert switches.is_enabled(source)
    assert switches.is_enabled(other_group)


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("operation", ["write_text", "replace"])
async def test_failed_save_keeps_memory_and_disk_unchanged_and_can_retry(
    switch_state, monkeypatch, enabled, operation
):
    key = f"QQClient_GROUP_{TARGET_GROUP}"
    await switches.init_disabled_targets()
    await switches.set_target_enabled(key, enabled=not enabled)
    original = switches._DISABLED_TARGETS_SET.copy()
    saved = await switches._DISABLED_TARGETS_PATH.read_text(encoding="utf-8")
    with monkeypatch.context() as patch:
        patch.setattr(Path, operation, AsyncMock(side_effect=OSError("disk failure")))
        with pytest.raises(OSError, match="disk failure"):
            await switches.set_target_enabled(key, enabled=enabled)
    assert switches._DISABLED_TARGETS_SET == original
    assert await switches._DISABLED_TARGETS_PATH.read_text(encoding="utf-8") == saved
    assert not await switches._DISABLED_TARGETS_PATH.with_suffix(".json.tmp").exists()
    assert await switches.set_target_enabled(key, enabled=enabled)
    switches._DISABLED_TARGETS_SET.clear()
    await switches.init_disabled_targets()
    assert (key not in switches._DISABLED_TARGETS_SET) == enabled
