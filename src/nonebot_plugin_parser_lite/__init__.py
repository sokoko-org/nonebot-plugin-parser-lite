"""Standalone social-media parser package.

The root module deliberately avoids importing every platform parser. Import a
platform module directly, or use ``Parser`` for lazy discovery.
"""

from importlib import import_module
from typing import Any

__version__ = "1.3.5"

__all__ = [
    "Config",
    "MatchResult",
    "ParseStep",
    "Parser",
    "clear_result_cache",
    "configure",
    "match",
    "parse",
    "shutdown_runtime",
]

_EXPORTS = {
    "Config": (".config", "Config"),
    "configure": (".config", "configure"),
    "MatchResult": (".pipeline", "MatchResult"),
    "ParseStep": (".pipeline", "ParseStep"),
    "Parser": (".pipeline", "Parser"),
    "clear_result_cache": (".pipeline", "clear_result_cache"),
    "match": (".pipeline", "match"),
    "parse": (".pipeline", "parse"),
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
