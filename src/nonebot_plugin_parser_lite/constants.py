from dataclasses import dataclass
from enum import StrEnum
import json
from re import Match, Pattern
from typing import Final, TypedDict, TypeVar, overload
from urllib.parse import parse_qs, urlparse

from httpx import Timeout

COMMON_HEADER: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
    )
}

QQ_HEADER: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 16; 2201123C Build/1450000) AppleWebKit/537.36"
        " (KHTML, like Gecko) Version/4.0 Chrome/121.0.6167.71 Safari/537.36 Mobile"
        " Safari/537.36 V1_AND_SQ_9.3.70_16410_YYB_D QQ/9.3.70.41925 AppId/537395443"
    )
}

COMMON_TIMEOUT: Final[Timeout] = Timeout(connect=15.0, read=20.0, write=10.0, pool=10.0)

DOWNLOAD_TIMEOUT: Final[Timeout] = Timeout(
    connect=15.0, read=240.0, write=10.0, pool=10.0
)

STICKER_CDN: Final[str] = "https://sticker.sokoko.org/assets/{platform}/{name}.webp"


class PlatformEnum(StrEnum):
    ACFUN = "acfun"
    BILIBILI = "bilibili"
    DOUYIN = "douyin"
    KUAISHOU = "kuaishou"
    KUGOU = "kugou"
    NETEASE = "netease"
    X = "x"
    WEIBO = "weibo"
    REDNOTE = "rednote"
    QSMUSIC = "qsmusic"
    KUWO = "kuwo"
    TIEBA = "tieba"
    ZHIHU = "zhihu"
    DUITANG = "duitang"
    HEYBOX = "heybox"
    LOFTER = "lofter"
    BUFF = "buff"
    COOLAPK = "coolapk"
    ILLU = "illu"
    HUPU = "hupu"
    MIYOUSHE = "miyoushe"
    DOUBAN = "douban"
    FIVEEPLAY = "5eplay"
    DOUBAO = "doubao"
    LINUXDO = "linuxdo"
    WMPVP = "wmpvp"
    ZLB = "zlb"
    TAPTAP = "taptap"
    DS = "ds"
    QQMUSIC = "qqmusic"

    def __str__(self) -> str:
        return self.value


EMOJI_MAP: Final[dict[str, tuple[str, str]]] = {
    "fail": ("10060", "❌"),
    "resolving": ("38", "🔨"),
    "done": ("148", "🍼"),
}
_TDefault = TypeVar("_TDefault")


class MatchWithParams:
    """在原有 re.Match 基础上，附带 URL 与解析好的 params，并挂载额外分组"""

    __slots__ = ("cache_key", "match", "params", "rule", "url")

    def __init__(self, match: Match[str], rule: "MatchRule"):
        self.rule = rule
        self.match = match
        self.url = match.group(0)
        parsed = urlparse(self.url)
        qs = parse_qs(parsed.query)
        # SPA hash routes may contain their own query, e.g. ``#/song?id=123``.
        fragment_qs = parse_qs(urlparse(parsed.fragment).query)
        qs.update(fragment_qs)
        # 只取第一个
        self.params: dict[str, str] = {k: v[0] for k, v in qs.items()}
        self.cache_key = ""

    def __getitem__(self, key) -> str:
        if isinstance(key, str) and (value := self.params.get(key)) is not None:
            return value
        return self.match[key]

    @overload
    def get(self, key: str) -> str | None: ...

    @overload
    def get(self, key: str, default: _TDefault) -> str | _TDefault: ...

    def get(self, key: str, default: _TDefault | None = None) -> str | _TDefault | None:
        try:
            value = self[key]
        except IndexError:
            return default
        return default if value is None else value

    @property
    def re(self):
        return self.match.re

    @property
    def string(self):
        return self.match.string


class ParamRule(TypedDict, total=False):
    """单个参数的匹配规则."""

    required: bool
    """是否必填，默认 True"""
    equals: str
    """必须等于该值"""
    default: str
    """默认值（required=False 时且未提供）"""
    as_int: bool
    """要求能解析为 int，仅做格式校验"""
    one_of: list[str]
    """必须在该集合内"""


ParamRules = dict[str, ParamRule]


@dataclass(frozen=True, slots=True)
class MatchRule:
    """处理器的匹配规则，统一准备参数和缓存键"""

    keyword: str
    pattern: Pattern[str]
    params: ParamRules
    handler_key: str

    def match(self, text: str) -> MatchWithParams | None:
        if self.keyword not in text or not (matched := self.pattern.search(text)):
            return None
        searched = MatchWithParams(matched, self)
        if not self._match_params(searched.params):
            return None
        searched.cache_key = self._cache_key(searched)
        return searched

    def _match_params(self, params: dict[str, str]) -> bool:
        for name, rule in self.params.items():
            value = params.get(name)
            if value is None and "default" in rule:
                value = params[name] = rule["default"]
            if value is None:
                if rule.get("required", True):
                    return False
                continue
            if "equals" in rule and value != rule["equals"]:
                return False
            if "one_of" in rule and value not in rule["one_of"]:
                return False
            if rule.get("as_int"):
                try:
                    int(value)
                except ValueError:
                    return False
        return True

    def _cache_key(self, searched: MatchWithParams) -> str:
        named_indexes = set(self.pattern.groupindex.values())
        values = {
            name: searched[name]
            for name, value in searched.match.groupdict().items()
            if value is not None
        }
        values |= (
            (str(index), value)
            for index, value in enumerate(searched.match.groups(), 1)
            if index not in named_indexes and value is not None
        )
        values |= (
            (name, searched.params[name])
            for name in self.params
            if name in searched.params
        )
        return json.dumps(
            (self.handler_key, values or searched.url),
            sort_keys=True,
            separators=(",", ":"),
        )
