from .client import CLIENT
from .credential import Credential
from .exceptions import BiliHelperException
from .opus import Opus


class Article:
    """
    专栏类
    """

    dyn_str_id: str | None = None

    def __init__(self, cvid: int, credential: Credential | None = None):
        self.cvid = cvid
        self.credential: Credential = credential or Credential()

    async def get_dyn_id(self) -> int:
        """
        获取专栏动态id

        :return: dyn_str_id
        """
        if not self.dyn_str_id:
            result = (
                await CLIENT.get(
                    url="https://api.bilibili.com/x/article/view",
                    params={"id": self.cvid},
                    cookies=self.credential.get_cookies(),
                )
            ).json()
            if result["code"] != 0:
                raise BiliHelperException(result)
            self.dyn_str_id = result["data"]["dyn_str_id"]
            assert self.dyn_str_id
        return int(self.dyn_str_id)

    async def turn_to_opus(self) -> Opus:
        return Opus(
            opus_id=await self.get_dyn_id(),
            credential=self.credential,
        )
