from enum import Enum
from io import BytesIO
import time

import qrcode

from .client import HTTP_CLIENT
from .credential import Credential, get_buvid
from .exceptions import BiliHelperException
from .sign import enc_sign


class QrCodeLoginEvents(Enum):
    """
    二维码登录状态枚举
    """

    SCAN = "scan"
    """未扫描二维码"""
    CONF = "confirm"
    """未确认登录"""
    TIMEOUT = "timeout"
    """二维码过期"""
    DONE = "done"
    """成功"""


class QrCodeLogin:
    """
    二维码登录类

    支持网页端/TV端
    """

    def __init__(self) -> None:
        self.link: str = ""
        self.auth_code: str = ""
        self.credential: Credential | None = None

    def get_credential(self) -> Credential:
        """
        获取登录成功后得到的凭据

        :return: 凭证
        """
        if not self.credential:
            raise BiliHelperException("未登录")
        return self.credential

    async def generate_qrcode(self) -> bytes:
        """
        生成二维码
        """
        result = (
            await HTTP_CLIENT.post(
                url="https://passport.bilibili.com/x/passport-tv-login/qrcode/auth_code",
                params=enc_sign({"local_id": "0", "ts": int(time.time())}),
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        self.link = result["data"]["url"]
        self.auth_code = result["data"]["auth_code"]
        qr = qrcode.QRCode(
            version=1,
            error_correction=1,
            box_size=10,
            border=1,
        )
        qr.add_data(self.link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")  # pyright: ignore[reportCallIssue]
        buffer.seek(0)
        return buffer.getvalue()

    async def check_state(self) -> QrCodeLoginEvents:
        """
        检查二维码登录状态

        :return: 二维码登录状态
        """
        resp = await HTTP_CLIENT.post(
            url="https://passport.bilibili.com/x/passport-tv-login/qrcode/poll",
            params=enc_sign(
                {
                    "auth_code": self.auth_code,
                    "local_id": "0",
                    "ts": int(time.time()),
                }
            ),
        )
        result = resp.json()
        code = result["code"]
        if code == -3:
            raise BiliHelperException("API校验密匙错误")
        elif code == -400:
            raise BiliHelperException("请求错误")
        elif code == 0:
            data = result["data"]
            cookies = {
                cookie["name"]: cookie["value"]
                for cookie in data["cookie_info"]["cookies"]
            }
            buvid = await get_buvid()
            token_info = data["token_info"]
            self.credential = Credential(
                sessdata=cookies["SESSDATA"],
                bili_jct=cookies["bili_jct"],
                dedeuserid=cookies["DedeUserID"],
                mid=token_info["mid"],
                access_token=token_info["access_token"],
                refresh_token=token_info["refresh_token"],
                expires_at=time.time() + token_info["expires_in"],
                buvid3=buvid[0],
                buvid4=buvid[1],
            )
            return QrCodeLoginEvents.DONE
        elif code == 86038:
            return QrCodeLoginEvents.TIMEOUT
        elif code == 86039:
            return QrCodeLoginEvents.SCAN
        elif code == 86090:
            return QrCodeLoginEvents.CONF
        else:
            raise BiliHelperException("未知错误")
