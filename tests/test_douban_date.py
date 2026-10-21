from datetime import datetime

import pytest
from render_test_support import ROOT  # noqa: F401  初始化插件包导入环境

from nonebot_plugin_parser_lite.parsers.douban.util import (
    parse_date,
    parse_rich_content,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-01-08 01:01:49", datetime(2026, 1, 8, 1, 1, 49)),
        ("2026-09-17 20:54:08.010189", datetime(2026, 9, 17, 20, 54, 8)),
    ],
)
def test_parse_date_accepts_optional_fractional_seconds(value: str, expected: datetime):
    assert parse_date(value) == int(expected.timestamp())


def test_parse_rich_content_uses_real_html_formatting():
    result = parse_rich_content(
        '<p>正文 <a href="/subject/1">链接</a></p>'
        '<p><img src="https://img.example/cover.jpg"></p>'
    )
    assert result[0] == "正文 链接 (https://m.douban.com/subject/1)"
    assert result[1].path_task.url == "https://img.example/cover.jpg"  # pyright: ignore[reportAttributeAccessIssue]
