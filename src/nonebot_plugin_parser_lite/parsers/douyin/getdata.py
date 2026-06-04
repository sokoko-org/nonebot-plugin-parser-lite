from .API import getDouyinDefaultConfig
from .sign import douyinSign


def getSignature(url: str, userAgent: str) -> str:
    """
    获取签名参数

    :param url: 需要签名的 URL
    :param userAgent: 用户代理
    """

    return douyinSign.AB(url, userAgent)


def buildSignedUrl(url: str, userAgent: str) -> str:
    """
    构建带签名的 URL

    :param url: 基础 URL
    :param userAgent: 用户代理
    """
    signature = getSignature(url, userAgent)
    return f"{url}&a_bogus={signature}"


class DouyinData:
    def __init__(self, cookie: str):
        self.defHeaders = getDouyinDefaultConfig(cookie)["headers"]
