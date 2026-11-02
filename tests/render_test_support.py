from collections.abc import Iterator
from pathlib import Path as SyncPath
import sys
import tempfile
from types import ModuleType
from typing import Any

from anyio import Path
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

parser_package = ModuleType("nonebot_plugin_parser_lite")
parser_package.__path__ = [str(SOURCE)]
parser_package.__package__ = parser_package.__name__
sys.modules[parser_package.__name__] = parser_package

from nonebot_plugin_alconna.uniseg import File, Image, Reference, Video

from nonebot_plugin_parser_lite.config import pconfig
from nonebot_plugin_parser_lite.constants import PlatformEnum, SendComponent
from nonebot_plugin_parser_lite.data import (
    Author,
    ImageContent,
    LivePhotoContent,
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
    "LivePhotoContent",
    "ParseResult",
    "Platform",
    "PlatformEnum",
    "Reference",
    "Renderer",
    "ResolvedPathTask",
    "SendComponent",
    "SyncPath",
    "ThemeManager",
    "UniHelper",
    "Video",
    "VideoContent",
    "build_theme_data",
    "make_result",
    "pconfig",
    "set_send_layout",
]


class ResolvedPathTask:
    def __init__(self, path: SyncPath | Path):
        self.path = Path(path)
        self.url = str(path)
        self.ext_headers = {}
        self.use_curl_cffi = False

    def __await__(self) -> Iterator[Any]:
        async def resolve() -> Path:
            return self.path

        return resolve().__await__()


def make_result() -> ParseResult:
    media_dir = SyncPath(tempfile.mkdtemp(prefix="media-", dir=store_root))
    video_path = media_dir / "video.mp4"
    cover_path = media_dir / "cover.png"
    video_path.write_bytes(b"video")
    cover_path.write_bytes(b"cover")
    video = VideoContent(
        path_task=ResolvedPathTask(video_path),  # type: ignore[arg-type]
        cover=ResolvedPathTask(cover_path),  # type: ignore[arg-type]
    )
    return ParseResult(
        platform=Platform(PlatformEnum.BILIBILI, "哔哩哔哩"),
        author=Author("tester"),
        url="https://example.com/video",
        content=[video],
    )


def set_send_layout(
    monkeypatch,
    *,
    video_in_forward: bool = False,
    content_in_forward: bool = True,
    summary_in_forward: bool = False,
    send_content: bool = True,
    send_cover: bool = True,
    send_url: bool = False,
    send_embed: bool = False,
) -> None:
    """按测试意图组装 send/forward 组件清单"""
    components = [SendComponent.CARD]
    if send_url:
        components.append(SendComponent.URL)
    if send_embed:
        components.append(SendComponent.EMBED)
    if send_content:
        components.append(SendComponent.CONTENT)
    if send_cover:
        components.append(SendComponent.COVER)
    components += [SendComponent.VIDEO, SendComponent.AUDIO]
    forward: list[SendComponent] = []
    if summary_in_forward:
        forward.append(SendComponent.CARD)
    if content_in_forward:
        forward += [SendComponent.CONTENT, SendComponent.COVER]
    if video_in_forward:
        forward.append(SendComponent.VIDEO)
    monkeypatch.setattr(pconfig, "plite_send_components", components)
    monkeypatch.setattr(pconfig, "plite_forward_components", forward)
