from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src/nonebot_plugin_parser_lite/parsers/douban/util.py"
TEST_PACKAGE = "_parser_lite_douban_date_test"


def _package(name: str) -> ModuleType:
    package = ModuleType(name)
    package.__path__ = []
    sys.modules[name] = package
    return package


def _load_parse_date():
    _package(TEST_PACKAGE)
    _package(f"{TEST_PACKAGE}.parsers")
    _package(f"{TEST_PACKAGE}.parsers.douban")
    _package(f"{TEST_PACKAGE}.utils")

    creator = ModuleType(f"{TEST_PACKAGE}.creator")
    creator.Creator = object
    sys.modules[creator.__name__] = creator

    data = ModuleType(f"{TEST_PACKAGE}.data")
    data.ContentItem = object
    sys.modules[data.__name__] = data

    formatting = ModuleType(f"{TEST_PACKAGE}.utils.format")
    formatting.HTML_NEWLINE_TAGS = frozenset()
    formatting.anchor_text = lambda *_args: None
    formatting.append_html_text = lambda *_args: None
    formatting.clean_clank = lambda *_args: None
    sys.modules[formatting.__name__] = formatting

    module_name = f"{TEST_PACKAGE}.parsers.douban.util"
    spec = spec_from_file_location(module_name, SOURCE)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.parse_date


parse_date = _load_parse_date()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-01-08 01:01:49", "2026-01-08 01:01:49"),
        ("2026-09-17 20:54:08.010", "2026-09-17 20:54:08"),
        ("2026-09-17 20:54:08.010189", "2026-09-17 20:54:08"),
    ],
)
def test_parse_date_accepts_optional_fractional_seconds(
    value: str, expected: str
):
    expected_timestamp = int(
        datetime.strptime(expected, "%Y-%m-%d %H:%M:%S").timestamp()
    )
    assert parse_date(value) == expected_timestamp


def test_parse_date_rejects_invalid_value():
    with pytest.raises(ValueError, match="Invalid isoformat string"):
        parse_date("2026-09-17T20:54:08Z-invalid")
