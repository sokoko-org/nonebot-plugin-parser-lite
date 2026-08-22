from typing import Any

from .client import CLIENT
from .exceptions import BiliHelperException


class Bangumi:
    """剧集类"""

    def __init__(
        self,
        ep_id: int | str | None = None,
        season_id: int | str | None = None,
    ):
        """
        :param ep_id: 剧集epid, defaults to None
        :param season_id: 番剧ssid, defaults to None
        """
        self.ep_id = ep_id
        self.season_id = season_id

    async def get_info(self) -> dict[str, Any]:
        result = (
            await CLIENT.get(
                url="https://api.bilibili.com/pgc/view/web/season",
                params={"season_id": self.season_id, "ep_id": self.ep_id},
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        return result["result"]
