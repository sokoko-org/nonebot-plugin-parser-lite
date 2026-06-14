import re
from typing import Literal

from msgspec import DecodeError, Struct
from msgspec.json import Decoder
from nonebot import logger
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.plugin.on import get_matcher_source
from nonebot.rule import Rule
from nonebot.typing import T_State
from nonebot_plugin_alconna.uniseg import Hyper, UniMsg
from nonebot_plugin_uninfo import Uninfo

from ..constants import MatchWithParams, ParamRules
from .filter import is_enabled

# 统一的状态键
PSR_SEARCHED_KEY: Literal["psr-searched"] = "psr-searched"


# 定义 JSON 卡片的数据结构
class MetaDetail(Struct):
    qqdocurl: str | None = None


class MetaNews(Struct):
    jumpUrl: str | None = None


class MetaMusic(Struct):
    jumpUrl: str | None = None


class Meta(Struct):
    detail_1: MetaDetail | None = None
    news: MetaNews | None = None
    music: MetaMusic | None = None


class RawData(Struct):
    meta: Meta | None = None


raw_decoder = Decoder(RawData)


class SearchResult:
    """匹配结果"""

    __slots__ = ("keyword", "searched", "text")

    def __init__(
        self,
        text: str,
        keyword: str,
        searched: MatchWithParams,
    ):
        self.text: str = text
        self.keyword: str = keyword
        self.searched: MatchWithParams = searched


class UrlSearchResult(SearchResult):
    """携带 URL 及其查询参数的匹配结果"""

    __slots__ = ()

    def __init__(self, text: str, keyword: str, searched: re.Match[str]):
        super().__init__(text, keyword, MatchWithParams(searched))

    @property
    def url(self) -> str:
        return self.searched.url

    @property
    def params(self) -> dict[str, str]:
        return self.searched.params


def Searched() -> SearchResult:
    """依赖注入，返回 SearchResult"""
    return Depends(_searched)


def _searched(state: T_State) -> SearchResult | None:
    """从 state 中提取匹配结果"""
    return state.get(PSR_SEARCHED_KEY)


def _extract_url(hyper: Hyper) -> str | None:
    """处理 JSON 类型的消息段，提取 URL

    :param json_seg: JSON 类型的消息段

    :return: 提取的 URL, 如果提取失败则返回 None
    """
    data = hyper.data
    raw_str: str | None = data.get("raw")

    if raw_str is None:
        return None

    try:
        raw = raw_decoder.decode(raw_str)
    except DecodeError:
        logger.exception(f"json 卡片解析失败: {raw_str}")
        return None

    if not raw.meta:
        return None

    meta, url = raw.meta, None

    if meta.detail_1:
        url = meta.detail_1.qqdocurl
    elif meta.news:
        url = meta.news.jumpUrl
    elif meta.music:
        url = meta.music.jumpUrl

    logger.debug(f"extract url[{url}] from raw#meta[{meta}]")
    return url


def _extract_text(message: UniMsg) -> str | None:
    """从消息中提取文本"""
    if hyper := next(iter(message.get(Hyper, 1)), None):
        return _extract_url(hyper)
    elif plain_text := message.extract_plain_text().strip():
        return plain_text
    return None


class KeyPatternList(list[tuple[str, re.Pattern[str], ParamRules]]):
    """(keyword, pattern, param_rules)

    param_rules: {param_name: 期望值 or True(仅要求存在)}
    """

    def __init__(
        self,
        *args: tuple[str, str | re.Pattern[str]]
        | tuple[str, str | re.Pattern[str], ParamRules],
    ):
        super().__init__()
        for item in args:
            if len(item) == 2:
                key, pattern = item
                param_rules: ParamRules = {}
            else:
                key, pattern, param_rules = item
            if isinstance(pattern, str):
                pattern = re.compile(pattern)
            self.append((key, pattern, param_rules))
        # 按 key 长 -> 短
        self.sort(key=lambda x: -len(x[0]))
        logger.debug(f"KeyWords: {[k for k, _, _ in self]}")


def _match_param_rules(params: dict[str, str], rules: ParamRules) -> bool:
    """根据 ParamRules 对已有的 params 做判断，并写默认值回去"""
    if not rules:
        return True

    for name, rule in rules.items():
        required = rule.get("required", True)
        value = params.get(name)

        if value is None and "default" in rule:
            value = rule["default"]
            params[name] = value

        if value is None:
            if required:
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


class KeywordRegexRule:
    """检查消息是否含有关键词, 有关键词进行正则匹配"""

    __slots__ = ("key_pattern_list",)

    def __init__(self, key_pattern_list: KeyPatternList):
        self.key_pattern_list = key_pattern_list

    def __repr__(self) -> str:
        return f"KeywordRegex(key_pattern_list={self.key_pattern_list})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, KeywordRegexRule)
            and self.key_pattern_list == other.key_pattern_list
        )

    def __hash__(self) -> int:
        sig = tuple((key, pattern.pattern) for key, pattern, _ in self.key_pattern_list)
        return hash(sig)

    async def __call__(self, message: UniMsg, state: T_State, sess: Uninfo) -> bool:

        text = _extract_text(message)
        if not text:
            return False
        for keyword, pattern, param_rules in self.key_pattern_list:
            if keyword not in text:
                continue
            if not (searched := pattern.search(text)):
                logger.debug(f"keyword '{keyword}' is in '{text}', but not matched")
                continue

            # 没有参数规则，也构造带 params 的 searched
            if not param_rules:
                mwp = MatchWithParams(searched)
                state[PSR_SEARCHED_KEY] = SearchResult(
                    text=text, keyword=keyword, searched=mwp
                )
                return True

            # 有参数规则，解析 URL 并检查
            url_sr = UrlSearchResult(text=text, keyword=keyword, searched=searched)
            url_sr.searched.param_rules = param_rules
            if _match_param_rules(url_sr.params, param_rules):
                state[PSR_SEARCHED_KEY] = url_sr
                return True

        return False


def keyword_regex(
    *args: tuple[str, str | re.Pattern[str]]
    | tuple[str, str | re.Pattern[str], ParamRules],
) -> Rule:
    return Rule(KeywordRegexRule(KeyPatternList(*args)))


def on_keyword_regex(
    *args: tuple[str, str | re.Pattern[str]]
    | tuple[str, str | re.Pattern[str], ParamRules],
    priority: int = 5,
) -> type[Matcher]:
    return Matcher.new(
        "message",
        is_enabled & keyword_regex(*args),
        priority=priority,
        block=True,
        source=get_matcher_source(1),
    )
