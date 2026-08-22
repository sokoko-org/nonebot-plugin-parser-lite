from enum import IntEnum
import json
from typing import Any

from .client import CLIENT
from .credential import Credential
from .exceptions import BiliHelperException
from .sign import encWbi, getWbiKeys


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

    ONLY_HOT = 3
    """仅按热度"""
    ONLY_TIME = 2
    """仅按时间"""
    HOT_AND_TIME = 1
    """按时间和热度"""


async def get_comments(
    oid: int,
    type: CommentResourceType,
    order: OrderType = OrderType.ONLY_HOT,
    number: int = 20,
    pagination_str: str | None = None,
    credential: Credential | None = None,
) -> dict[str, Any]:
    """
    获取资源评论列表(wbi)

    :param oid: 资源 ID
    :param type_: 资源类枚举
    :param order: 	排序方式, defaults to OrderType.ONLY_HOT
    :param number: 获取数量, defaults to 20
    :param pagination_str: 翻页信息，用于懒加载分页 首次请求时不传，后续请求使用上次响应中的 data.cursor.pagination_reply.next_offset, defaults to None
    :param credential: 凭证, defaults to None
    :raises BiliHelperError: _description_
    :return: 调用 API 返回的结果, 未登录 3 , 登录 20, 现在不想写翻页
    """  # noqa: E501
    credential = credential or Credential()
    params = {
        "type": type.value,
        "oid": oid,
        "mode": order.value,
        "plat": 1,
        "seek_rpid": "",
        "number": number,
        "web_location": 1315875,
    }
    if pagination_str:
        params["pagination_str"] = json.dumps({"offset": pagination_str})
    else:
        params["pagination_str"] = json.dumps({"offset": ""})
    result = (
        await CLIENT.get(
            url="https://api.bilibili.com/x/v2/reply/wbi/main",
            params=encWbi(params, *(await getWbiKeys())),
            cookies=credential.get_cookies(),
        )
    ).json()
    if result["code"] != 0:
        raise BiliHelperException(result)
    return result["data"]
