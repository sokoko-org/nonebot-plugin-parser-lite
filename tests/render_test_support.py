from collections.abc import Iterator
from pathlib import Path as SyncPath
import sys
import tempfile
from types import ModuleType
from typing import Any

import nonebot

ROOT = SyncPath(__file__).parents[1]
SOURCE = ROOT / "src" / "nonebot_plugin_parser_lite"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# Load render tests without initializing the plugin's real optional services.
nonebot.init()
_store_tempdir = tempfile.TemporaryDirectory(prefix="parser-lite-render-test-")
store_root = SyncPath(_store_tempdir.name)
localstore = ModuleType("nonebot_plugin_localstore")
localstore.get_plugin_cache_dir = lambda: store_root / "cache"  # type: ignore[attr-defined]
localstore.get_plugin_config_dir = lambda: store_root / "config"  # type: ignore[attr-defined]
localstore.get_plugin_data_dir = lambda: store_root / "data"  # type: ignore[attr-defined]
sys.modules[localstore.__name__] = localstore

htmlrender = ModuleType("nonebot_plugin_htmlrender")
htmlrender.get_new_page = None  # type: ignore[attr-defined]
sys.modules[htmlrender.__name__] = htmlrender

parser_package = ModuleType("nonebot_plugin_parser_lite")
parser_package.__path__ = [str(SOURCE)]
parser_package.__package__ = parser_package.__name__
sys.modules[parser_package.__name__] = parser_package

from nonebot_plugin_alconna.uniseg import File, Image, Reference, Video

from nonebot_plugin_parser_lite.config import pconfig
from nonebot_plugin_parser_lite.constants import PlatformEnum
from nonebot_plugin_parser_lite.data import (
    Author,
    ImageContent,
    ParseResult,
    Platform,
    VideoContent,
)
from nonebot_plugin_parser_lite.helper import (
    ForwardNodeInner,
    UniHelper,
)
from nonebot_plugin_parser_lite.render import Renderer
from nonebot_plugin_parser_lite.render.context import (
    build_theme_data,
)
from nonebot_plugin_parser_lite.render.theme import ThemeManager

__all__ = [
    "ROOT",
    "Author",
    "File",
    "ForwardNodeInner",
    "Image",
    "ImageContent",
    "ParseResult",
    "Platform",
    "PlatformEnum",
    "Reference",
    "Renderer",
    "ResolvedPathTask",
    "SyncPath",
    "ThemeManager",
    "UniHelper",
    "Video",
    "VideoContent",
    "build_theme_data",
    "make_result",
    "pconfig",
]


class ResolvedPathTask:
    def __init__(self, path: SyncPath):
        self.path = path
        self.url = str(path)
        self.ext_headers = {}
        self.use_curl_cffi = False

    def __await__(self) -> Iterator[Any]:
        async def resolve() -> SyncPath:
            return self.path

        return resolve().__await__()


def make_result() -> ParseResult:
    video = VideoContent(
        path_task=ResolvedPathTask(SyncPath("video.mp4")),  # type: ignore[arg-type]
        cover=ResolvedPathTask(SyncPath("cover.png")),  # type: ignore[arg-type]
    )
    return ParseResult(
        platform=Platform(PlatformEnum.BILIBILI, "哔哩哔哩"),
        author=Author("tester"),
        url="https://example.com/video",
        content=[video],
    )
