"""Text-only parsing pipeline for the standalone build."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from importlib import import_module
from typing import Any, Self, overload

from .config import pconfig
from .constants import MatchWithParams
from .data import ParseResult
from .exception import ParseException
from .parsers.base import BaseParser
from .utils.common import LimitedSizeDict
from .utils.log import logger
from .utils.scheduler import scheduler

_RESULT_CACHE = LimitedSizeDict[str, ParseResult](max_size=50)
_CACHE_JOB_ID = "parser-clean-local-cache"


def clear_result_cache() -> None:
    _RESULT_CACHE.clear()


async def _clean_runtime_cache() -> None:
    from .utils.cache import CacheManager

    try:
        await CacheManager.clean_expired()
    except Exception:
        logger.exception("清理缓存文件时发生异常")
    clear_result_cache()


def _ensure_runtime_started() -> None:
    scheduler.add_job(
        _clean_runtime_cache,
        seconds=2 * 60 * 60,
        id=_CACHE_JOB_ID,
    )


async def shutdown_runtime() -> None:
    from .download import DOWNLOADER
    from .utils.browser import BrowserManager

    await scheduler.shutdown()
    await BrowserManager.quit()
    await DOWNLOADER.aclose()
    clear_result_cache()


class ParseStep(str, Enum):
    MATCH = "match"
    PARSE = "parse"
    RESOLVE = "resolve"
    RENDER = "render"


@dataclass(frozen=True, slots=True)
class MatchResult:
    text: str
    keyword: str
    searched: MatchWithParams
    parser_type: type[BaseParser]

    @property
    def url(self) -> str:
        return self.searched.url

    @property
    def params(self) -> dict[str, str]:
        return self.searched.params.copy()

    @property
    def cache_key(self) -> str:
        return f"{self.keyword}:{self.searched.cache_key}"


class Parser:
    """Run the parser pipeline with all platforms or an explicit subset."""

    def __init__(self, parser_types: Sequence[type[BaseParser]] | None = None):
        self._parser_types = tuple(parser_types) if parser_types is not None else None
        self._instances: dict[type[BaseParser], BaseParser] = {}

    def _types(self) -> tuple[type[BaseParser], ...]:
        if self._parser_types is None:
            parsers = import_module(".parsers", __package__)
            parsers.load_all()
            disabled = set(pconfig.disabled_platforms)
            self._parser_types = tuple(
                parser_type
                for parser_type in BaseParser.get_all_subclass()
                if parser_type.platform.name not in disabled
            )
        return self._parser_types

    def match(self, text: str) -> MatchResult:
        if not isinstance(text, str):
            raise TypeError(f"text must be str, got {type(text).__name__}")
        if not text.strip():
            raise ParseException("解析文本不能为空")

        patterns = sorted(
            (
                (keyword, pattern, rules, parser_type)
                for parser_type in self._types()
                for keyword, pattern, rules in parser_type._key_patterns
            ),
            key=lambda item: -len(item[0]),
        )
        for keyword, pattern, rules, parser_type in patterns:
            if keyword not in text:
                continue
            matched = pattern.search(text)
            if matched is None:
                continue
            searched = MatchWithParams(matched)
            searched.param_rules = rules
            if parser_type._match_param_rules(searched, rules):
                return MatchResult(text, keyword, searched, parser_type)
        raise ParseException("文本中没有可解析的内容")

    def _instance(self, parser_type: type[BaseParser]) -> BaseParser:
        if parser_type not in self._instances:
            self._instances[parser_type] = parser_type()
        return self._instances[parser_type]

    @overload
    async def parse(
        self, text: str, *, until: ParseStep = ParseStep.PARSE
    ) -> ParseResult: ...

    @overload
    async def parse(self, text: str, *, until: str) -> Any: ...

    async def parse(
        self, text: str, *, until: ParseStep | str = ParseStep.PARSE
    ) -> Any:
        _ensure_runtime_started()
        step = ParseStep(until)
        matched = self.match(text)
        if step is ParseStep.MATCH:
            return matched

        result = _RESULT_CACHE.get(matched.cache_key)
        if result is None:
            parser = self._instance(matched.parser_type)
            result = await parser.parse(matched.keyword, matched.searched)
            _RESULT_CACHE[matched.cache_key] = result
        else:
            logger.debug("命中解析结果缓存: %s", matched.cache_key)
        if step is ParseStep.PARSE:
            return result

        from .render import RENDERER

        if step is ParseStep.RESOLVE:
            return await RENDERER.resolve_parse_result(result)
        return await RENDERER.render_image(result)

    async def aclose(self) -> None:
        for parser in self._instances.values():
            await parser.aclose()
        self._instances.clear()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()


def match(
    text: str, parser_types: Sequence[type[BaseParser]] | None = None
) -> MatchResult:
    return Parser(parser_types).match(text)


async def parse(
    text: str,
    *,
    until: ParseStep | str = ParseStep.PARSE,
    parser_types: Sequence[type[BaseParser]] | None = None,
) -> Any:
    async with Parser(parser_types) as parser:
        return await parser.parse(text, until=until)
