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
    from .render.stats import render_stats_image
    from .stats import ParseRecord, ParseStatsSummary, query_records, query_stats

__version__ = "1.4.2rc4"

__all__ = [
    "Config",
    "MatchResult",
    "ParseRecord",
    "ParseStatsSummary",
    "ParseStep",
    "Parser",
    "RenderResult",
    "ThemeData",
    "clear_result_cache",
    "configure",
    "match",
    "parse",
    "query_records",
    "query_stats",
    "render_stats_image",
    "render_theme_data",
    "resolve_parse_result",
    "shutdown_runtime",
]

_EXPORTS = {
    "Config": (".config", "Config"),
    "configure": (".config", "configure"),
    "MatchResult": (".pipeline", "MatchResult"),
    "ParseRecord": (".stats", "ParseRecord"),
    "ParseStatsSummary": (".stats", "ParseStatsSummary"),
    "ParseStep": (".pipeline", "ParseStep"),
    "Parser": (".pipeline", "Parser"),
    "RenderResult": (".pipeline", "RenderResult"),
    "ThemeData": (".render", "ThemeData"),
    "clear_result_cache": (".pipeline", "clear_result_cache"),
    "match": (".pipeline", "match"),
    "parse": (".pipeline", "parse"),
    "query_records": (".stats", "query_records"),
    "query_stats": (".stats", "query_stats"),
    "render_stats_image": (".render.stats", "render_stats_image"),
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
