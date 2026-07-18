from enum import Enum
from io import BytesIO

import qrcode

from .client import CLIENT
from .credential import Credential
from .exceptions import BiliHelperException


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
        """
        :param platform: 平台, defaults to QrCodeLoginChannel.WEB
        """
        self.__qr_link: str = ""
        self.__qr_key: str = ""
        self.__credential: Credential | None = None

    def get_credential(self) -> Credential:
        """
        获取登录成功后得到的凭据

        :return: 凭证
        """
        if not self.__credential:
            raise BiliHelperException("未登录")
        return self.__credential

    async def generate_qrcode(self) -> bytes:
        """
        生成二维码
        """
        result = (
            await CLIENT.get(
                url="https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                params={"source": "main-fe-header"},
                cookies=Credential().get_cookies(),
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        data = result["data"]
        self.__qr_link = data["url"]
        self.__qr_key = data["qrcode_key"]
        qr = qrcode.QRCode(
            version=1,
            error_correction=1,
            box_size=10,
            border=1,
        )
        qr.add_data(self.__qr_link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")  # pyright: ignore[reportCallIssue]
        buffer.seek(0)
        return buffer.getvalue()

    async def check_state(self) -> QrCodeLoginEvents:
        """
        检查二维码登录状态

        Returns:
            QrCodeLoginEvents: 二维码登录状态
        """
        result = (
            await CLIENT.get(
                url="https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                params={"qrcode_key": self.__qr_key, "source": "main-fe-header"},
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        events = result["data"]
        code = events["code"]
        if code == 86101:
            return QrCodeLoginEvents.SCAN
        elif code == 86090:
            return QrCodeLoginEvents.CONF
        elif code == 86038:
            return QrCodeLoginEvents.TIMEOUT
        else:
            cred_url = events["url"]
            ac_time_value = events["refresh_token"]
            cookies_list = cred_url.split("?")[1].split("&")
            sessdata = ""
            bili_jct = ""
            dedeuserid = ""
            for cookie in cookies_list:
                if cookie[:8] == "SESSDATA":
                    sessdata = cookie[9:]
                if cookie[:8] == "bili_jct":
                    bili_jct = cookie[9:]
                if cookie[:11].upper() == "DEDEUSERID=":
                    dedeuserid = cookie[11:]
            self.__credential = Credential(
                sessdata=sessdata,
                bili_jct=bili_jct,
                dedeuserid=dedeuserid,
                ac_time_value=ac_time_value,
            )
            return QrCodeLoginEvents.DONE
