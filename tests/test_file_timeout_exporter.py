from types import SimpleNamespace

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.matcher import current_bot, current_event
from nonebot_plugin_alconna.uniseg import File, Reference, UniMessage
import pytest
from render_test_support import pconfig

from nonebot_plugin_parser_lite.delivery import send_with_media_fallback


@pytest.mark.asyncio
@pytest.mark.parametrize("private", [False, True])
@pytest.mark.parametrize("forward_id", [False, True])
async def test_file_timeout_reaches_onebot_upload_api(
    monkeypatch, tmp_path, private, forward_id
):
    calls = []

    async def call_api(bot, api, **data):
        calls.append((api, data))
        return {"message_id": 1}

    monkeypatch.setattr(Bot, "call_api", call_api)
    monkeypatch.setattr(pconfig, "plite_file_upload_timeout", 900)
    bot = Bot(SimpleNamespace(get_name=lambda: "OneBot V11"), "42")
    path = tmp_path / "file.mp4"
    path.write_bytes(b"file")
    message = UniMessage(File(path=path))
    if forward_id:
        message.append(Reference(id="existing-forward"))
    event_data = {
        "time": 0, "self_id": 42, "post_type": "message",
        "message_type": "private" if private else "group",
        "sub_type": "friend" if private else "normal",
        "user_id": 123, "message_id": 1, "message": "file",
        "original_message": "file", "raw_message": "file", "font": 0,
        "sender": {"user_id": 123, "nickname": "user"},
    }
    if not private:
        event_data["group_id"] = 123
    event_class = PrivateMessageEvent if private else GroupMessageEvent
    bot_token = current_bot.set(bot)
    event_token = current_event.set(event_class.model_validate(event_data))
    try:
        await send_with_media_fallback(message)
    finally:
        current_bot.reset(bot_token)
        current_event.reset(event_token)

    assert len(calls) == 1
    api, data = calls[0]
    assert api == ("upload_private_file" if private else "upload_group_file")
    assert data["_timeout"] == 900
    assert data["file"] == path.as_posix()
    assert data["name"] == "file.mp4"
