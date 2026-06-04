import secrets
import string
import time

from .a_bogus import a_bogus


def _int_to_base36(num: int) -> str:
    """现代化 10 进制转 36 进制辅助函数"""
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if num == 0:
        return "0"
    res = []
    while num > 0:
        num, rem = divmod(num, 36)
        res.append(chars[rem])
    return "".join(reversed(res))


class douyinSign:
    @staticmethod
    def Mstoken(length: int = 116) -> str:
        """
        现代化 msToken 生成器

        :param length: 期望的字符串长度，默认为 116
        :return: 随机生成的 msToken 字符串
        """
        characters = string.ascii_letters + string.digits
        return "".join(secrets.choice(characters) for _ in range(length))

    @staticmethod
    def AB(url: str, ua: str) -> str:
        """a_bogus 签名算法入口"""
        return a_bogus(url, ua)

    @staticmethod
    def VerifyFpManager() -> str:
        """唯一验证字符串 (verifyFp) 生成器"""
        alphabet = list(
            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        )
        base36_len = len(alphabet)
        now_ms = int(time.time() * 1000)
        time_b36 = _int_to_base36(now_ms)
        r: list[str] = [None] * 36  # pyright: ignore[reportAssignmentType]
        r[8] = "_"
        r[13] = "_"
        r[18] = "_"
        r[23] = "_"
        r[14] = "4"
        for i in range(36):
            if r[i] is None:
                o = secrets.randbelow(base36_len)
                # i === 19 ? (3 & o) | 8 : o
                idx = (3 & o) | 8 if i == 19 else o
                r[i] = alphabet[idx]
        return f"verify_{time_b36}_{''.join(r)}"
