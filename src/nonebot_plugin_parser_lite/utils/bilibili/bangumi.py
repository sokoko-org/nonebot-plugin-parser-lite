from time import time
from typing import Any

from .client import (
    API_CHANNEL,
    API_LOCALE,
    API_STATISTICS,
    BUILD,
    HTTP_CLIENT,
    MOBI_APP,
    PLATFORM,
    get_bilibili_headers,
)
from .exceptions import BiliHelperException
from .sign import enc_sign


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
        params: dict[str, str] = {
            "platform": PLATFORM,
            "channel": API_CHANNEL,
            "mobi_app": MOBI_APP,
            "statistics": API_STATISTICS,
            "build": str(BUILD),
            "c_locale": API_LOCALE,
            "s_locale": API_LOCALE,
            "ts": str(int(time())),
        }
        if self.season_id not in (None, ""):
            params["season_id"] = str(self.season_id)
        if self.ep_id not in (None, ""):
            params["ep_id"] = str(self.ep_id)

        params = enc_sign(params)
        headers = get_bilibili_headers()
        headers = {
            key: headers[key]
            for key in ("user-agent", "app-key", "env", "buvid")
        }
        result = (
            await HTTP_CLIENT.get(
                url="https://api.bilibili.com/pgc/view/v2/app/season",
                params=params,
                headers=headers,
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        return result["data"]
