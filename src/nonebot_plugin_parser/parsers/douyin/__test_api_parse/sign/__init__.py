from __future__ import annotations

import random
import secrets
import time

from .a_bogus import a_bogus
from .x_bogus import XBogus

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def base36_encode(num: int) -> str:
    """等价于 JS Number.prototype.toString(36) 的非负整数部分。"""
    if num == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    res: list[str] = []
    n = num
    while n > 0:
        n, rem = divmod(n, 36)
        res.append(digits[rem])
    return "".join(reversed(res))


class douyinSign:
    """
    抖音签名工具类，对应 TS 版本的 douyinSign。
    """

    @staticmethod
    def Mstoken(length: int = 116) -> str:
        """
        生成一个指定长度的随机字符串（默认 116）
        """
        characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        # 使用 secrets 替代 node:crypto.randomBytes
        random_bytes = secrets.token_bytes(length or 116)
        return "".join(characters[b % len(characters)] for b in random_bytes)

    @staticmethod
    def AB(url: str, user_agent: str | None = None) -> str:
        """
        a_bogus 签名算法

        :param url: 需要签名的地址
        :param user_agent: UA，可选
        :return: 对此地址签名后的 URL 查询参数
        """
        return a_bogus(url, user_agent or DEFAULT_USER_AGENT)

    @staticmethod
    def XB(url: str, user_agent: str | None = None) -> str:
        """
        X-Bogus 签名算法

        :param url: 需要签名的地址
        :param user_agent: UA，可选
        :return: 对此地址签名后的 URL 查询参数
        """
        xbogus_result = XBogus().getXBogus(url, user_agent or DEFAULT_USER_AGENT)
        # TS 中返回 xbogusResult.xbogus，这里保持一致
        return (
            xbogus_result["xbogus"]
            if isinstance(xbogus_result, dict)
            else xbogus_result.xbogus
        )

    @staticmethod
    def VerifyFpManager() -> str:
        """
        生成一个唯一的验证字符串，对应 TS 版 VerifyFpManager：

        const e = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'.split('')
        const t = e.length
        const n = new Date().getTime().toString(36)
        const r: (string | number)[] = []

        r[8] = '_'
        r[13] = '_'
        r[18] = '_'
        r[23] = '_'
        r[14] = '4'

        for (let o, i = 0; i < 36; i++) {
          if (!r[i]) {
            o = 0 | (Math.random() * t)
            r[i] = e[i === 19 ? (3 & o) | 8 : o]
          }
        }

        return 'verify_' + n + '_' + r.join('')
        """
        chars: list[str] = list(
            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        )
        t = len(chars)

        # new Date().getTime().toString(36)
        # Date.getTime() 是毫秒时间戳，这里用 time.time() * 1000
        millis = int(time.time() * 1000)
        n_str = base36_encode(millis)

        r: list[str] = [""] * 36
        r[8] = "_"
        r[13] = "_"
        r[18] = "_"
        r[23] = "_"
        r[14] = "4"

        for i in range(36):
            if not r[i]:
                # 0 | (Math.random() * t)  => 等价于 floor(...)
                o = int(random.random() * t)
                idx = ((3 & o) | 8) if i == 19 else o
                r[i] = chars[idx]

        return f"verify_{n_str}_" + "".join(r)
