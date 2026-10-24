from unittest.mock import AsyncMock

import pytest
import render_test_support as support

from nonebot_plugin_parser_lite.data import Author, Platform, VideoContent
from nonebot_plugin_parser_lite.download import DOWNLOADER
from nonebot_plugin_parser_lite.parsers.base import BaseParser, handle


@pytest.mark.asyncio
async def test_repost_media_follows_the_outer_author(tmp_path, monkeypatch):
    monkeypatch.setattr(
        support.pconfig,
        "plite_media_speedup_rules",
        ["bilibili:123456:1.5", "bilibili:777:2.0"],
    )
    monkeypatch.setattr(BaseParser, "_registry", [])
    monkeypatch.setattr(Platform, "get_logo_path", AsyncMock(return_value=None))
    monkeypatch.setattr(DOWNLOADER, "head_size", AsyncMock(return_value=1024))
    source = support.ResolvedPathTask(tmp_path / "video.mp4")

    class OfflineParser(BaseParser):
        platform = Platform(support.PlatformEnum.BILIBILI, "哔哩哔哩")

        @handle("example.com", r"https://example\.com/video")
        async def parse_video(self, searched):
            return self.result(
                author=Author("outer", id="123456"),
                url=searched.url,
                content=[VideoContent(path_task=source, duration=60)],  # type: ignore[arg-type]
                repost=self.result(
                    author=Author("inner", id="777"),
                    url="https://example.com/repost",
                    content=[VideoContent(path_task=source, duration=120)],  # type: ignore[arg-type]
                ),
            )

    parser = OfflineParser()
    try:
        keyword, searched = parser.search_url("https://example.com/video")
        result = await parser.parse(keyword, searched)
    finally:
        await parser.aclose()

    data = await support.build_theme_data(
        result,
        color_scheme="light",
        theme_id="default",
        bot_name="bot",
        max_comments=0,
        append_qrcode=False,
    )

    outer = data["post"]["content"][0]
    inner = data["post"]["repost"]["content"][0]
    assert (outer["duration"], outer["speedup"]) == ("0:40", "1.5x")
    assert (inner["duration"], inner["speedup"]) == ("1:20", "1.5x")
