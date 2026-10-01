from datetime import datetime

import pytest
from render_test_support import ROOT  # noqa: F401 初始化公共插件测试环境

from nonebot_plugin_parser_lite.parsers.douban.util import parse_date


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-01-08 01:01:49", "2026-01-08 01:01:49"),
        ("2026-09-17 20:54:08.010", "2026-09-17 20:54:08"),
        ("2026-09-17 20:54:08.010189", "2026-09-17 20:54:08"),
    ],
)
def test_parse_date_accepts_optional_fractional_seconds(value: str, expected: str):
    expected_timestamp = int(
        datetime.strptime(expected, "%Y-%m-%d %H:%M:%S").timestamp()
    )
    assert parse_date(value) == expected_timestamp


def test_parse_date_rejects_invalid_value():
    with pytest.raises(ValueError, match="Invalid isoformat string"):
        parse_date("2026-09-17T20:54:08Z-invalid")
