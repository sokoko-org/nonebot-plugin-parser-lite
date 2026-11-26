"""匹配器测试共用的会话、事件与解析流水线替身"""

from collections import OrderedDict
from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.matcher import current_event
from nonebot_plugin_uninfo import Scene, SceneType, Session, SupportScope, User
import pytest
from render_test_support import set_send_layout  # 同时初始化插件包导入环境

from nonebot_plugin_parser_lite import matchers
from nonebot_plugin_parser_lite.matchers import limit
from nonebot_plugin_parser_lite.matchers.rule import SearchResult
from nonebot_plugin_parser_lite.parsers.base import BaseParser
from nonebot_plugin_parser_lite.parsers.bilibili import BilibiliParser
from nonebot_plugin_parser_lite.parsers.ds import DsParser
from nonebot_plugin_parser_lite.parsers.registry import REGISTRY
from nonebot_plugin_parser_lite.parsers.taptap import TapTapParser

ADMIN_QQ = "10001"
CURRENT_GROUP = "20001"
TARGET_GROUP = "20002"
BOT_QQ = "30001"

__all__ = [
    "ADMIN_QQ",
    "BOT_QQ",
    "CURRENT_GROUP",
    "TARGET_GROUP",
    "command_context",
    "patched_pipeline",
    "search",
    "session",
]


def command_context(*, superuser=True, private=False):
    """构造 OneBot V11 的 (bot, event, session)，发送者为 ADMIN_QQ"""
    bot = Bot(
        SimpleNamespace(
            get_name=lambda: "OneBot V11",
            config=SimpleNamespace(superusers={ADMIN_QQ} if superuser else set()),
        ),  # pyright: ignore[reportArgumentType]
        BOT_QQ,
    )
    event_data = {
        "time": 1,
        "self_id": int(BOT_QQ),
        "post_type": "message",
        "message_type": "private" if private else "group",
        "sub_type": "friend" if private else "normal",
        "user_id": int(ADMIN_QQ),
        "message_id": 1,
        "font": 0,
        "message": [],
        "original_message": [],
        "raw_message": "",
        "to_me": True,
        "sender": {"user_id": int(ADMIN_QQ), "role": "admin"},
    }
    if not private:
        event_data["group_id"] = int(CURRENT_GROUP)
    event_class = PrivateMessageEvent if private else GroupMessageEvent
    event = event_class.model_validate(event_data)
    uninfo = Session(
        self_id=bot.self_id,
        adapter="OneBot V11",
        scope=SupportScope.qq_client,
        scene=Scene(
            ADMIN_QQ if private else CURRENT_GROUP,
            SceneType.PRIVATE if private else SceneType.GROUP,
        ),
        user=User(ADMIN_QQ),
    )
    return bot, event, uninfo


def session(target=CURRENT_GROUP, user=ADMIN_QQ, *, private=False) -> Session:
    return Session(
        self_id=BOT_QQ,
        adapter="OneBot V11",
        scope=SupportScope.qq_client,
        scene=Scene(target, SceneType.PRIVATE if private else SceneType.GROUP),
        user=User(user),
    )


def search(url: str, parser: type[BaseParser] | None = None) -> SearchResult:
    if parser is None:
        parser = TapTapParser if "taptap.cn" in url else DsParser
    keyword, searched = parser.search_url(url)
    return SearchResult(url, keyword, searched)


@contextmanager
def patched_pipeline(
    monkeypatch: pytest.MonkeyPatch, *, stats: Any = None
) -> Generator[SimpleNamespace]:
    """替换解析、渲染与发送，只保留 parser_handler 的调度逻辑

    :param stats: 解析统计实例；默认用 mock，避免写入共享数据目录
    """
    parsed = AsyncMock(return_value=object())
    rendered = AsyncMock(return_value="summary")
    sent = AsyncMock()

    async def content(*_args, **_kwargs):
        yield "body"

    monkeypatch.setattr(limit.ParseCooldown, "recent", OrderedDict())
    monkeypatch.setattr(limit.ParseCooldown, "active", {})
    monkeypatch.setattr(
        REGISTRY,
        "_keyword_class_map",
        {
            rule.keyword: parser
            for parser in (TapTapParser, DsParser, BilibiliParser)
            for rule in parser._key_patterns
        },
    )
    monkeypatch.setattr(REGISTRY, "_loaded", True)
    monkeypatch.setattr(matchers, "get_or_parse_result", parsed)
    monkeypatch.setattr(matchers.RENDERER, "render_messages", rendered)
    monkeypatch.setattr(matchers.RENDERER, "send_content", content)
    monkeypatch.setattr(matchers, "send_with_media_fallback", sent)
    monkeypatch.setattr(matchers.UniHelper, "message_reaction", AsyncMock())
    monkeypatch.setattr(matchers, "STATS", stats or SimpleNamespace(record=AsyncMock()))
    monkeypatch.setattr(matchers.pconfig, "plite_lazy_download", False)
    set_send_layout(monkeypatch)
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_minutes", 30)
    monkeypatch.setattr(matchers.pconfig, "plite_parse_dedup_platforms", None)
    token = current_event.set(object())  # pyright: ignore[reportArgumentType]
    try:
        yield SimpleNamespace(parsed=parsed, sent=sent)
    finally:
        current_event.reset(token)
