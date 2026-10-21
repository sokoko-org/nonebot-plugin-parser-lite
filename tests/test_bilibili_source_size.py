from unittest.mock import AsyncMock

import pytest
from render_test_support import ROOT  # noqa: F401

from nonebot_plugin_parser_lite.parsers.bilibili.size import probe_source_size


@pytest.mark.asyncio
@pytest.mark.parametrize("primary", [None, RuntimeError("HTTP 403")])
async def test_probe_source_size_returns_backup_size(primary):
    probe = AsyncMock(side_effect=[primary, 320])
    assert await probe_source_size(("video-primary", "video-backup"), probe) == 320
