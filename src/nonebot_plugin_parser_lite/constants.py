from enum import Enum
from typing import Final

from httpx import Timeout

COMMON_HEADER: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
    )
}

IOS_HEADER: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.6 Mobile/15E148 Safari/604.1 Edg/132.0.0.0"
    )
}

ANDROID_HEADER: Final[dict[str, str]] = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 15; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/132.0.0.0 Mobile Safari/537.36 Edg/132.0.0.0"
    )
}

COMMON_TIMEOUT: Final[Timeout] = Timeout(connect=15.0, read=20.0, write=10.0, pool=10.0)

DOWNLOAD_TIMEOUT: Final[Timeout] = Timeout(
    connect=15.0, read=240.0, write=10.0, pool=10.0
)


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
    TOUTIAO = "toutiao"
    TIEBA = "tieba"
    ZHIHU = "zhihu"
    DUITANG = "duitang"
    HEYBOX = "heybox"
    LOFTER = "lofter"
    BUFF = "buff"

    def __str__(self) -> str:
        return self.value


EMOJI_MAP: Final[dict[str, tuple[str, str]]] = {
    "fail": ("10060", "❌"),
    "resolving": ("38", "🔨"),
    "done": ("148", "🍼"),
}
