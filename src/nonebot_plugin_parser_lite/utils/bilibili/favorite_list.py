from typing import Any

from .client import HTTP_CLIENT
from .exceptions import BiliHelperException


async def get_video_favorite_list_content(
    media_id: int,
    page: int = 1,
    keyword: str = "",
) -> dict:
    """
    获取视频收藏夹列表内容，也可用于搜索收藏夹内容

    :param media_id: 收藏夹 ID
    :param page: 页码, defaults to 1
    :param keyword: 搜索关键词, defaults to ""
    :raises BiliHelperError: _description_
    :return: _description_
    """
    params: dict[str, Any] = {
        "media_id": media_id,
        "pn": page,
        "ps": 20,
    }
    if keyword:
        params["keyword"] = keyword

    result = (
        await HTTP_CLIENT.get(
            url="https://api.bilibili.com/x/v3/fav/resource/list",
            params=params,
        )
    ).json()
    if result["code"] != 0:
        raise BiliHelperException(result)
    return result["data"]
