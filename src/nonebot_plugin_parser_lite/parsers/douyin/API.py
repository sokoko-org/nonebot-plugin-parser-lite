import re
from typing import Any, Final, TypedDict
from urllib.parse import urlencode

from ..base import COMMON_HEADER
from .sign import douyinSign

_UA_VERSION_RE = re.compile(r"(?:Chrome|Edg)/(\d+\.\d+\.\d+\.\d+)")
_CHROME_MAJOR_VERSION_RE = re.compile(r"Chrome/(\d+)")
_EDGE_CLEAN_RE = re.compile(r"\s+Edg/[\d\.]+")


def extractBrowserVersion(user_agent: str | None = None) -> str:
    """
    UA 版本提取器

    :param user_agent: 原始 User-Agent 字符串
    :return: 捕获到的浏览器版本号，若未找到则返回默认的 '125.0.0.0'
    """
    if not user_agent:
        return "125.0.0.0"
    match = _UA_VERSION_RE.search(user_agent)

    return match.group(1) if match else "125.0.0.0"


def buildQueryString(params: dict[str, Any]) -> str:
    """
    URL 查询参数构建器

    :param params: 输入的参数字典
    :return: 归一化且编码完备的 URL Query 字符串
    """
    cleaned_params = {k: v for k, v in params.items() if v is not None}
    return urlencode(cleaned_params)


fp: Final[str] = douyinSign.VerifyFpManager()


class WorkDetail(TypedDict):
    aweme_id: int
    """作品id"""


class CommentsDetail(WorkDetail, total=False):
    cursor: int
    """偏移量"""
    number: int
    """获取数据数量"""


class RepliesDetail(CommentsDetail):
    comment_id: int
    """评论id"""


class DouyinAPI:
    browserVersion: str

    def __init__(self, ua: str):
        self.browserVersion = extractBrowserVersion(ua)

    def getBaseParams(self) -> dict[str, Any]:
        """获取通用的基础参数"""
        return {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "pc_client_type": "1",
            "cookie_enabled": "true",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": self.browserVersion,
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": self.browserVersion,
            "os_name": "Windows",
            "os_version": "10",
            "cpu_core_num": "16",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "msToken": douyinSign.Mstoken(184),
            "verifyFp": fp,
            "fp": fp,
        }

    def getWorkDetail(self, data: WorkDetail) -> str:
        """获取视频或图集数据"""
        baseUrl = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
        params = {
            **self.getBaseParams(),
            "aweme_id": data["aweme_id"],
            "update_version_code": "170400",
            "version_code": "190500",
            "version_name": "19.5.0",
            "screen_width": "2328",
            "screen_height": "1310",
            "round_trip_time": "150",
            "webid": "7351848354471872041",
        }
        return f"{baseUrl}?{buildQueryString(params)}"

    def getComments(self, data: CommentsDetail) -> str:
        """获取评论数据"""
        baseUrl = "https://www.douyin.com/aweme/v1/web/comment/list/"
        params = {
            **self.getBaseParams(),
            "aweme_id": data["aweme_id"],
            "cursor": data.get("cursor", 0),
            "count": data.get("number", 20),
            "item_type": "0",
            "insert_ids": "",
            "whale_cut_token": "",
            "cut_version": "1",
            "rcFT": "",
            "version_code": "170400",
            "version_name": "17.4.0",
            "screen_width": "1552",
            "screen_height": "970",
            "round_trip_time": "50",
        }
        return f"{baseUrl}?{buildQueryString(params)}"

    def getCommentReplies(self, data: RepliesDetail) -> str:
        """获取二级评论数据"""
        baseUrl = "https://www-hj.douyin.com/aweme/v1/web/comment/list/reply/"
        params = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "item_id": data["aweme_id"],
            "comment_id": data["comment_id"],
            "cut_version": "1",
            "cursor": data.get("cursor"),
            "count": data.get("number"),
            "item_type": "0",
            "update_version_code": "170400",
            "pc_client_type": "1",
            "pc_libra_divert": "Windows",
            "support_h265": "1",
            "support_dash": "1",
            "version_code": "170400",
            "version_name": "17.4.0",
            "cookie_enabled": "true",
            "screen_width": "1552",
            "screen_height": "970",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Edge",
            "browser_version": self.browserVersion,
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": self.browserVersion,
            "os_name": "Windows",
            "os_version": "10",
            "cpu_core_num": "16",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "50",
            "webid": "7487210762873685515",
            "verifyFp": fp,
            "fp": fp,
        }
        return f"{baseUrl}?{buildQueryString(params)}"


def generateSecChUa(user_agent: str) -> str:
    """
    Sec-Ch-Ua 生成器。

    :param user_agent: 原始 User-Agent 字符串
    :return: 标准 Sec-Ch-Ua 字符串
    """
    if not user_agent:
        chrome_version = "125"
    else:
        match = _CHROME_MAJOR_VERSION_RE.search(user_agent)
        chrome_version = match.group(1) if match else "125"

    return (
        f'"Not_A Brand";v="99", "Chromium";v="{chrome_version}", '
        f'"Google Chrome";v="{chrome_version}"'
    )


def getDouyinDefaultConfig(
    cookie: str = "", request_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    生成抖音平台默认的 httpx 请求配置字典

    :param cookie: 用户 Cookie 字符串
    :param request_config: 外部传入的自定义请求配置字典
    :return: kwargs 参数字典
    """
    if request_config is None:
        request_config = {}

    ext_headers = request_config.get("headers", {})

    raw_ua = ext_headers.get("User-Agent") or COMMON_HEADER["User-Agent"]

    finalUserAgent = _EDGE_CLEAN_RE.sub("", raw_ua)

    defHeaders = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Cookie": cookie.strip(),
        "Priority": "u=1, i",
        "Referer": "https://www.douyin.com/",
        "Sec-Ch-Ua": generateSecChUa(finalUserAgent),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": finalUserAgent,
    }

    return {
        "method": request_config.get("method", "GET"),
        "timeout": request_config.get("timeout", 10),
        **{
            k: v
            for k, v in request_config.items()
            if k not in ["headers", "method", "timeout"]
        },
        "headers": defHeaders | ext_headers,
    }
