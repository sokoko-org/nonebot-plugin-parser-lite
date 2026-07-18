from enum import IntEnum
from typing import Any

from .client import CLIENT
from .credential import Credential
from .exceptions import BiliHelperException


class CommentResourceType(IntEnum):
    """
    资源类型枚举
    """

    VIDEO = 1
    """视频"""
    ARTICLE = 12
    """专栏"""
    DYNAMIC_DRAW = 11
    """画册（图文）"""
    DYNAMIC = 17
    """动态（画册也属于动态的一种，只不过画册还有一个专门的 ID）"""
    AUDIO = 14
    """音频"""
    AUDIO_LIST = 19
    """歌单"""
    CHEESE = 33
    """课程"""
    BLACK_ROOM = 6
    """小黑屋"""
    MANGA = 22
    """漫画"""
    ACTIVITY = 4
    """活动"""


class OrderType(IntEnum):
    """
    评论排序方式枚举
    """

    HOT = 2
    """按热度倒序"""
    LIKE = 1
    """按点赞数倒序"""
    TIME = 0
    """按发布时间倒序"""


async def get_comments(
    oid: int,
    type: CommentResourceType,
    page_index: int = 1,
    page_size: int = 7,
    nohot: bool = False,
    order: OrderType = OrderType.HOT,
    credential: Credential | None = None,
) -> dict[str, Any]:
    """
    获取资源评论列表

    :param oid: 资源 ID
    :param type_: 资源类枚举
    :param page_index: 页码, defaults to 1
    :param page_size: 每页项数, defaults to 7
    :param nohot: 是否不显示热评, defaults to False
    :param order: 	排序方式, defaults to OrderType.HOT
    :param credential: 凭证, defaults to None
    :raises BiliHelperError: _description_
    :return: 调用 API 返回的结果
    """
    if page_index <= 0:
        raise BiliHelperException("page_index 必须大于或等于 1")
    if page_size <= 0:
        raise BiliHelperException("page_size 必须大于或等于 1")
    page_size = min(page_size, 20)
    credential = credential or Credential()
    result = (
        await CLIENT.get(
            url="https://api.bilibili.com/x/v2/reply",
            params={
                "pn": page_index,
                "type": type.value,
                "oid": oid,
                "sort": order.value,
                "ps": page_size,
                "nohot": nohot,
            },
            cookies=credential.get_cookies(),
        )
    ).json()
    if result["code"] != 0:
        raise BiliHelperException(result)
    return result["data"]
