"""
抖音 API URL 构建器

该类下的方法只会返回拼接好参数后的 URL 地址，需要手动请求该地址以获取数据。
缺少 `a_bogus` 参数，请自行生成拼接。
"""

from __future__ import annotations

import re
from typing import Any

from .sign import douyinSign


def _extract_browser_version(user_agent: str | None = None) -> str:
    """
    从 User-Agent 中提取浏览器版本信息

    :param user_agent: 用户代理字符串
    :return: 浏览器版本号，默认为 125.0.0.0
    """
    if not user_agent:
        return "125.0.0.0"

    if chrome_match := re.search(r"Chrome/(\d+\.\d+\.\d+\.\d+)", user_agent):
        return chrome_match[1]

    edge_match = re.search(r"Edg/(\d+\.\d+\.\d+\.\d+)", user_agent)
    return edge_match[1] if edge_match else "125.0.0.0"


def _build_query_string(params: dict[str, Any]) -> str:
    """
    将参数对象转换为 URL 查询字符串
    """
    from urllib.parse import quote_plus

    parts = [
        f"{key}={quote_plus(str(value))}"
        for key, value in params.items()
        if value is not None
    ]
    return "&".join(parts)


# 等价于 TS 中的：const fp = douyinSign.VerifyFpManager()
_fp = douyinSign.VerifyFpManager()


class DouyinAPI:
    """
    抖音 API URL 构建类

    提供所有抖音 API 的 URL 构建方法
    """

    def __init__(self, user_agent: str | None = None) -> None:
        """
        :param user_agent: 用户代理字符串，用于提取浏览器版本信息
        """
        self.browser_version = _extract_browser_version(user_agent)

    def get_base_params(self) -> dict[str, Any]:
        """
        获取通用的基础参数
        """
        return {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "pc_client_type": "1",
            "cookie_enabled": "true",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": self.browser_version,
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": self.browser_version,
            "os_name": "Windows",
            "os_version": "10",
            "cpu_core_num": "16",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "msToken": douyinSign.Mstoken(184),
            "verifyFp": _fp,
            "fp": _fp,
        }

    # === 下方的方法签名使用简单的参数，等价于 TS 里 data.xxx 的访问 ===

    def get_work_detail(self, aweme_id: str) -> str:
        """
        获取视频或图集数据

        :param aweme_id: 视频或图集 ID
        """
        base_url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
        params: dict[str, Any] = {
            **self.get_base_params(),
            "aweme_id": aweme_id,
            "update_version_code": "170400",
            "version_code": "190500",
            "version_name": "19.5.0",
            "screen_width": "2328",
            "screen_height": "1310",
            "round_trip_time": "150",
            "webid": "7351848354471872041",
        }
        return f"{base_url}?{_build_query_string(params)}"

    def get_comments(self, aweme_id: str, cursor: int = 0, number: int = 5) -> str:
        """
        获取评论数据

        :param aweme_id: 视频或图集 ID
        :param cursor: 游标
        :param number: 数量
        """
        base_url = "https://www.douyin.com/aweme/v1/web/comment/list/"
        params: dict[str, Any] = {
            **self.get_base_params(),
            "aweme_id": aweme_id,
            "cursor": cursor,
            "count": number,
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
        return f"{base_url}?{_build_query_string(params)}"

    def get_comment_replies(
        self, aweme_id: str, comment_id: str, cursor: int = 0, number: int = 5
    ) -> str:
        """
        获取二级评论数据

        :param aweme_id: 视频或图集 ID
        :param comment_id: 评论 ID
        :param cursor: 游标
        :param number: 数量
        """
        base_url = "https://www-hj.douyin.com/aweme/v1/web/comment/list/reply/"
        params: dict[str, Any] = {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "item_id": aweme_id,
            "comment_id": comment_id,
            "cut_version": "1",
            "cursor": cursor,
            "count": number,
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
            "browser_version": self.browser_version,
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": self.browser_version,
            "os_name": "Windows",
            "os_version": "10",
            "cpu_core_num": "16",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "50",
            "webid": "7487210762873685515",
            "verifyFp": _fp,
            "fp": _fp,
        }
        return f"{base_url}?{_build_query_string(params)}"


def create_douyin_api_urls(user_agent: str | None = None) -> DouyinAPI:
    """
    创建 DouyinAPI 实例的工厂函数
    """
    return DouyinAPI(user_agent)


# 默认实例（使用默认浏览器版本 125.0.0.0）
douyin_api_urls = DouyinAPI()
