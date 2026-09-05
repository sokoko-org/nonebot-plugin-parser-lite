import time
from typing import Any

from msgspec import Struct, convert

from .client import (
    API_CHANNEL,
    API_LOCALE,
    API_STATISTICS,
    BUILD,
    ENVIRONMENT,
    HTTP_CLIENT,
    MOBI_APP,
    PLATFORM,
)
from .credential import Credential
from .exceptions import BiliHelperException
from .sign import enc_sign


class UserInfo(Struct):
    """``x/v2/space`` 返回的用户基础资料"""

    mid: str
    name: str
    face: str
    sign: str


async def get_user_info(
    mid: int,
    credential: Credential | None = None,
) -> UserInfo:
    """获取用户资料"""
    params = enc_sign(
        {
            "build": BUILD,
            "c_locale": API_LOCALE.replace("_", "-"),
            "channel": API_CHANNEL,
            "mobi_app": MOBI_APP,
            "platform": PLATFORM,
            "s_locale": API_LOCALE.replace("_", "-"),
            "statistics": API_STATISTICS,
            "ts": int(time.time()),
            "vmid": mid,
        }
    )
    response = await HTTP_CLIENT.get(
        url="https://app.bilibili.com/x/v2/space",
        params=params,
        headers={"app-key": MOBI_APP, "env": ENVIRONMENT},
        cookies=credential.get_cookies() if credential else None,
    )
    result = response.json()
    if result["code"] != 0:
        raise BiliHelperException(result)
    return convert(result["data"]["card"], UserInfo)


async def get_black_list(
    credential: Credential,
    page_size: int = 50,
    page_index: int = 1,
) -> dict[str, Any]:
    """
    获取用户黑名单，要求登录

    :param credential: 凭证
    :param page_size: 每页项数, defaults to 50, max to 50
    :param page_index: 页面, defaults to 1
    :raises BiliHelperError: 页码不合法
    :raises BiliHelperError: api返回错误
    :return: 黑名单数据
    """
    if page_index <= 0:
        raise BiliHelperException("page_index 必须大于或等于 1")
    result = (
        await HTTP_CLIENT.get(
            url="https://api.bilibili.com/x/relation/blacks",
            params={"ps": page_size, "pn": page_index},
            cookies=credential.get_cookies(),
        )
    ).json()
    if result["code"] != 0:
        raise BiliHelperException(result)
    return result["data"]
