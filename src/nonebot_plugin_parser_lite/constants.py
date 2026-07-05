from enum import Enum, IntEnum
from re import Match
from typing import Any, Final, TypedDict
from urllib.parse import parse_qs, urlparse

from httpx import Timeout

COMMON_HEADER: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
    )
}

IOS_HEADER: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.6 Mobile/15E148 Safari/604.1 Edg/132.0.0.0"
    )
}

ANDROID_HEADER: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 15; SM-G998B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/132.0.0.0 Mobile Safari/537.36 Edg/132.0.0.0"
    )
}

COMMON_TIMEOUT: Final[Timeout] = Timeout(connect=15.0, read=20.0, write=10.0, pool=10.0)

DOWNLOAD_TIMEOUT: Final[Timeout] = Timeout(
    connect=15.0, read=240.0, write=10.0, pool=10.0
)

STICKER_CDN: Final[str] = "https://sticker.sokoko.org/assets/{platform}/{name}.webp"


class PlatformEnum(str, Enum):
    ACFUN = "acfun"
    BILIBILI = "bilibili"
    DOUYIN = "douyin"
    KUAISHOU = "kuaishou"
    KUGOU = "kugou"
    NETEASE = "netease"
    TIKTOK = "tiktok"
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

    def __str__(self) -> str:
        return self.value


EMOJI_MAP: Final[dict[str, tuple[str, str]]] = {
    "fail": ("10060", "❌"),
    "resolving": ("38", "🔨"),
    "done": ("148", "🍼"),
}


class BiliVideoQuality(IntEnum):
    """
    视频的视频流分辨率枚举

    :cvar _360P: 流畅 360P
    :cvar _480P: 清晰 480P
    :cvar _720P: 高清 720P60
    :cvar _1080P: 高清 1080P
    :cvar AI_REPAIR: 智能修复（人工智能修复画质）
    :cvar _1080P_PLUS: 高清 1080P 高码率
    :cvar _1080P_60: 高清 1080P 60 帧码率
    :cvar _4K: 超清 4K
    :cvar HDR: 真彩 HDR
    :cvar DOLBY: 杜比视界
    :cvar _8K: 超高清 8K
    """

    _360P = 16
    _480P = 32
    _720P = 64
    _1080P = 80
    AI_REPAIR = 100
    _1080P_PLUS = 112
    _1080P_60 = 116
    _4K = 120
    HDR = 125
    DOLBY = 126
    _8K = 127


class BiliVideoCodecs(str, Enum):
    """
    视频的视频流编码枚举

    :cvar HEV: HEVC(H.265)
    :cvar AVC: AVC(H.264)
    :cvar AV1: AV1
    :cvar UNKNOWN: 未知
    """

    HEV = "hev"
    AVC = "avc"
    AV1 = "av01"
    UNKNOWN = "unknown"

    @classmethod
    def from_codec(cls, codec: str) -> "BiliVideoCodecs":
        """根据返回的 codec 字符串推断枚举值"""
        codec = codec.lower()
        if any(k in codec for k in ("hev", "hvc1", "hev1")):
            return cls.HEV
        if any(k in codec for k in ("avc",)):
            return cls.AVC
        return cls.AV1 if any(k in codec for k in ("av1", "av01")) else cls.UNKNOWN


class BiliAudioQuality(IntEnum):
    """
    视频的音频流清晰度枚举

    :cvar _64K: 64K
    :cvar _132K: 132K
    :cvar _192K: 192K
    :cvar HI_RES: Hi-Res 无损
    :cvar DOLBY: 杜比全景声
    """

    _64K = 30216
    _132K = 30232
    DOLBY = 30250
    HI_RES = 30251
    _192K = 30280


class MatchWithParams:
    """在原有 re.Match 基础上，附带 URL 与解析好的 params，并挂载额外分组"""

    __slots__ = ("match", "param_rules", "params", "url")

    def __init__(self, match: Match[str]):
        self.match = match
        self.url = match.group(0)
        parsed = urlparse(self.url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        # 只取第一个
        self.params: dict[str, str] = {k: v[0] for k, v in qs.items()}
        self.param_rules: ParamRules = {}
        """当前匹配对应的 ParamRules（由 BaseParser / rule 填充）"""

    def __getitem__(self, key):
        if isinstance(key, str) and key in self.params:
            return self.params[key]
        return self.match[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.params[key] if key in self.params else default

    @property
    def re(self):
        return self.match.re

    @property
    def string(self):
        return self.match.string

    @property
    def cache_key(self) -> str:
        """
        用于结果缓存的 key：
        - 若没有 ParamRules：只使用原始 URL（与旧逻辑兼容）
        - 若有 ParamRules：URL + ParamRules 中提及的参数（按 key 排序）
        """
        base = self.url

        # 没有任何参数规则，保持与旧逻辑完全一致
        if not self.param_rules:
            return base

        # 只使用 ParamRules 中提到的参数
        keys = sorted(self.param_rules.keys())
        used_params = {k: self.params[k] for k in keys if k in self.params}

        # 没有实际值
        if not used_params:
            return base

        parts = [base.split("#", 1)[0]]  # 去掉 fragment
        param_str = "&".join(f"{k}={used_params[k]}" for k in sorted(used_params))
        parts.append(param_str)
        return "?".join(parts)


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
