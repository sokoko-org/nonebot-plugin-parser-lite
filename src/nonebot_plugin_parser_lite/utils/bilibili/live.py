from typing import Any

from .client import CLIENT
from .credential import Credential
from .exceptions import BiliHelperException


class LiveRoom:
    """
    直播类，获取各种直播间的操作均在里边
    """

    def __init__(self, room_display_id: int, credential: Credential | None = None):
        """
        :param room_display_id: 房间展示 ID（即 URL 中的 ID）
        :param credential: 凭证, defaults to None
        """
        self.room_display_id = room_display_id
        self.credential: Credential = credential or Credential()

    async def get_room_info(self) -> dict[str, Any]:
        """
        获取直播间信息（标题，简介等）

        :return: 调用 API 返回的结果
        """
        result = (
            await CLIENT.get(
                url="https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom",
                params={"room_id": self.room_display_id},
                cookies=self.credential.get_cookies(),
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        return result["data"]
