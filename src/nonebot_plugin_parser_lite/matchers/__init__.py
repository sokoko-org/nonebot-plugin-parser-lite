"""Compatibility exports for the standalone text pipeline."""

from ..pipeline import (
    MatchResult,
    Parser,
    ParseStep,
    clear_result_cache,
    match,
    parse,
)

__all__ = ["MatchResult", "ParseStep", "Parser", "clear_result_cache", "match", "parse"]
