from .client import CLIENT
from .credential import Credential
from .exceptions import BiliHelperException
from .opus import Opus
from .sign import encWbi, getWbiKeys


class Dynamic:
    """
    动态类
    """

    detail: dict | None = None
    __is_article: bool = False

    def __init__(self, dynamic_id: int, credential: Credential | None = None) -> None:
        self.dynamic_id = dynamic_id
        self.credential: Credential = credential or Credential()

    async def get_info(self) -> dict:
        """
        获取动态信息

        :return: 调用 API 返回的结果
        """
        if not self.detail:
            params = {
                "id": self.dynamic_id,
                "timezone_offset": -480,
                "platform": "web",
                "gaia_source": "main_web",
                "features": "itemOpusStyle,opusBigCover,onlyfansVote,endFooterHidden,decorationCard,onlyfansAssetsV2,ugcDelete",  # noqa: E501
                "web_location": "333.1368",
                "x-bili-device-req-json": '{"platform":"web","device":"pc"}',
                "x-bili-web-req-json": '{"spm_id":"333.1368"}',
            }
            result = (
                await CLIENT.get(
                    url="https://api.bilibili.com/x/polymer/web-dynamic/v1/detail",
                    params=encWbi(params, *(await getWbiKeys())),
                    cookies=self.credential.get_cookies(),
                )
            ).json()
            if result["code"] != 0:
                raise BiliHelperException(result)
            self.detail = result["data"]
            assert self.detail
            self.__is_article = self.detail["item"]["basic"]["comment_type"] == 12
        return self.detail

    async def is_article(self) -> bool:
        """
        判断动态是否为专栏发布动态

        :return: 是否为专栏
        """
        if self.detail is None:
            await self.get_info()
        return self.__is_article

    def turn_to_opus(self) -> Opus:
        """
        对图文动态，转换为图文

        :return: 图文对象
        """
        return Opus(opus_id=self.dynamic_id, credential=self.credential)
