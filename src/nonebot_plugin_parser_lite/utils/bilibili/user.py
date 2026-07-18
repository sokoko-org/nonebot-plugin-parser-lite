from typing import Any

from .client import CLIENT
from .credential import Credential
from .exceptions import BiliHelperException


async def get_black_list(
    page_size: int = 50, page_index: int = 1, credential: Credential | None = None
) -> dict[str, Any]:
    """
    获取用户黑名单，要求登录

    :param page_size: 每页项数, defaults to 50, max to 50
    :param page_index: 页面, defaults to 1
    :param credential: 凭证, defaults to None
    :raises BiliHelperError: 页码不合法
    :raises BiliHelperError: api返回错误
    :return: 黑名单数据
    """
    credential = credential or Credential()
    credential.raise_for_no_sessdata()
    if page_index <= 0:
        raise BiliHelperException("page_index 必须大于或等于 1")
    credential = credential or Credential()
    result = (
        await CLIENT.get(
            url="https://api.bilibili.com/x/v2/reply",
            params={"ps": page_size, "pn": page_index},
            cookies=credential.get_cookies(),
        )
    ).json()
    if result["code"] != 0:
        raise BiliHelperException(result)
    return result["data"]
