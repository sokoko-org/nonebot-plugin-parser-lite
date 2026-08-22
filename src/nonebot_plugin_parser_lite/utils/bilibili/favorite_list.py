from enum import Enum, IntEnum

from .client import CLIENT
from .credential import Credential
from .exceptions import BiliHelperException


class FavoriteListContentOrder(Enum):
    """
    收藏夹列表内容排序方式枚举。
    """

    MTIME = "mtime"
    """最近收藏"""
    VIEW = "view"
    """最多播放"""
    PUBTIME = "pubtime"
    """最新投稿"""


class SearchFavoriteListMode(IntEnum):
    """
    收藏夹搜索模式枚举
    """

    ONLY = 0
    """仅当前收藏夹"""
    ALL = 1
    """该用户所有收藏夹"""


async def get_video_favorite_list_content(
    media_id: int,
    page: int = 1,
    keyword: str | None = None,
    order: FavoriteListContentOrder = FavoriteListContentOrder.MTIME,
    tid: int = 0,
    mode: SearchFavoriteListMode = SearchFavoriteListMode.ONLY,
    credential: Credential | None = None,
) -> dict:
    """
    获取视频收藏夹列表内容，也可用于搜索收藏夹内容

    :param media_id: 收藏夹 ID
    :param page: 页码, defaults to 1
    :param keyword: 搜索关键词, defaults to None
    :param order: 排序方式, defaults to FavoriteListContentOrder.MTIME
    :param tid: 分区 ID, defaults to 0
    :param mode: _des搜索模式，默认仅当前收藏夹cription_, defaults to SearchFavoriteListMode.ONLY
    :param credential: Credential, defaults to None
    :raises BiliHelperError: _description_
    :return: _description_
    """  # noqa: E501
    params = {
        "media_id": media_id,
        "pn": page,
        "ps": 20,
        "order": order.value,
        "tid": tid,
        "type": mode.value,
        "platform": "web",
        "web_location": "333.1387",
    }

    if keyword is not None:
        params["keyword"] = keyword

    credential = credential or Credential()

    result = (
        await CLIENT.get(
            url="https://api.bilibili.com/x/v3/fav/resource/list",
            params=params,
            cookies=credential.get_cookies(),
        )
    ).json()
    if result["code"] != 0:
        raise BiliHelperException(result)
    return result["data"]
