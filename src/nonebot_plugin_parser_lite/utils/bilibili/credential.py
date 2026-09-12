import time
import urllib.parse

from anyio import Path
import ujson

from .client import HTTP_CLIENT
from .exceptions import BiliHelperException, CookiesRefreshException
from .sign import enc_sign


class Credential:
    """
    凭证类，用于各种请求操作的验证

    所有的凭证都是可选的，除非你想要一些需要登录才能看的内容
    """

    def __init__(
        self,
        *,
        sessdata: str,
        bili_jct: str,
        dedeuserid: str,
        mid: int | str,
        access_token: str,
        refresh_token: str,
        expires_at: float,
        **kwargs
    ) -> None:
        """
        :param sessdata: SESSDATA cookie
        :param bili_jct: _description_
        :param dedeuserid: DedeUserID cookie
        :param mid: 用户 UID
        :param refresh_token: 刷新用
        :param access_token: access token
        :param expires_at: 凭证过期时间戳
        """
        self.sessdata = sessdata if "%" in sessdata else urllib.parse.quote(sessdata)
        self.bili_jct = bili_jct
        self.dedeuserid = dedeuserid
        self.mid = int(mid)
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at

    def get_cookies(self) -> dict[str, str]:
        """
        获取请求 Cookies 字典

        :return: 请求 Cookies 字典
        """
        return {
            "SESSDATA": self.sessdata,
            "bili_jct": self.bili_jct,
            "DedeUserID": self.dedeuserid,
        }

    def has_sessdata(self) -> bool:
        return bool(self.sessdata)

    def has_bili_jct(self) -> bool:
        return bool(self.bili_jct)

    def raise_for_no_sessdata(self) -> None:
        if not self.has_sessdata():
            raise BiliHelperException("no sessdata provided")

    def raise_for_no_bili_jct(self) -> None:
        if not self.has_bili_jct():
            raise BiliHelperException("no bili_jct provided")

    def check_refresh(self) -> bool:
        """
        检查是否需要刷新 cookies

        :return: cookies 是否需要刷新
        """
        return bool(self.expires_at and time.time() >= self.expires_at)

    async def refresh(self) -> None:
        """
        刷新 cookies
        """
        resp = (
            await HTTP_CLIENT.post(
                "https://passport.bilibili.com/api/v2/oauth2/refresh_token",
                params=enc_sign(
                    {
                        "access_key": self.access_token,
                        "refresh_token": self.refresh_token,
                        "ts": int(time.time()),
                    }
                ),
            )
        ).json()
        if resp["code"] != 0:
            raise CookiesRefreshException(resp)
        cookies = {
            cookie["name"]: cookie["value"]
            for cookie in resp["data"]["cookie_info"]["cookies"]
        }
        token_info = resp["data"]["token_info"]
        new_cred = Credential(
            sessdata=cookies["SESSDATA"],
            bili_jct=cookies["bili_jct"],
            dedeuserid=cookies["DedeUserID"],
            mid=token_info["mid"],
            access_token=token_info["access_token"],
            refresh_token=token_info["refresh_token"],
            expires_at=time.time() + token_info["expires_in"],
        )
        self.__dict__.update(new_cred.__dict__)

    @staticmethod
    async def from_file(file_path: Path) -> "Credential":
        """
        从json文件重建 Credential

        :param file_path: 文件路径
        :return: 凭证类
        """
        return Credential(**ujson.loads(await file_path.read_bytes()))

    async def save_file(self, file_path: Path) -> None:
        """
        保存凭证到 json 文件

        :param file_path: 文件路径
        """
        credential_data = {
            "sessdata": self.sessdata,
            "bili_jct": self.bili_jct,
            "dedeuserid": self.dedeuserid,
            "mid": self.mid,
            "refresh_token": self.refresh_token,
            "access_token": self.access_token,
            "expires_at": self.expires_at,
        }

        await file_path.write_text(
            ujson.dumps(credential_data, ensure_ascii=False), encoding="utf-8"
        )
