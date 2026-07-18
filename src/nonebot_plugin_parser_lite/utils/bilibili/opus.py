from typing import Any

from .client import CLIENT
from .credential import Credential
from .exceptions import BiliHelperException


class Opus:
    """
    图文类
    """

    info: dict[str, Any] | None = None

    def __init__(self, opus_id: int, credential: Credential | None = None):
        self.opus_id = opus_id
        self.credential: Credential = credential or Credential()

    async def get_info(self):
        """
        获取图文基本信息

        :return: 调用 API 返回的结果
        """
        if not self.info:
            result = (
                await CLIENT.get(
                    url="https://api.bilibili.com/x/polymer/web-dynamic/v1/opus/detail",
                    params={
                        "timezone_offset": -480,
                        "id": self.opus_id,
                        "features": "onlyfansVote,onlyfansAssetsV2,decorationCard,htmlNewStyle,ugcDelete,editable,opusPrivateVisible",  # noqa: E501
                    },
                )
            ).json()
            if result["code"] != 0:
                raise BiliHelperException(result)
            self.info = result["data"]
            assert self.info
            if self.info.get("fallback"):
                raise BiliHelperException("传入的 opus_id 不正确")
        return self.info
