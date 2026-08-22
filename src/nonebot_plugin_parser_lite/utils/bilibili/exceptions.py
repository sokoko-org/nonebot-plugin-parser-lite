from typing import Any


class BiliHelperException(Exception):
    """
    BH 相关错误
    """

    def __init__(self, msg: Any):
        super().__init__(str(msg))
        self.msg = str(msg)

    def __str__(self):
        return self.msg


class CookieInvalidException(BiliHelperException):
    """
    Cookie 无效
    """

    pass


class CookiesRefreshException(BiliHelperException):
    """
    Cookie 刷新失败
    """

    pass
