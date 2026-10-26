"""Standalone social-media parser package.

The root module deliberately avoids importing every platform parser. Import a
platform module directly, or use ``Parser`` for lazy discovery.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import Config, configure
    from .pipeline import (
        MatchResult,
        Parser,
        ParseStep,
        RenderResult,
        clear_result_cache,
        match,
        parse,
        shutdown_runtime,
    )
    from .render import ThemeData, render_theme_data, resolve_parse_result

__version__ = "1.3.11rc2"

__all__ = [
    "Config",
    "MatchResult",
    "ParseStep",
    "Parser",
    "RenderResult",
    "ThemeData",
    "clear_result_cache",
    "configure",
    "match",
    "parse",
    "render_theme_data",
    "resolve_parse_result",
    "shutdown_runtime",
]

_EXPORTS = {
    "Config": (".config", "Config"),
    "configure": (".config", "configure"),
    "MatchResult": (".pipeline", "MatchResult"),
    "ParseStep": (".pipeline", "ParseStep"),
    "Parser": (".pipeline", "Parser"),
    "RenderResult": (".pipeline", "RenderResult"),
    "ThemeData": (".render", "ThemeData"),
    "clear_result_cache": (".pipeline", "clear_result_cache"),
    "match": (".pipeline", "match"),
    "parse": (".pipeline", "parse"),
    "render_theme_data": (".render", "render_theme_data"),
    "resolve_parse_result": (".render", "resolve_parse_result"),
    "shutdown_runtime": (".pipeline", "shutdown_runtime"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
