from __future__ import annotations

import contextlib
import math
import random
import re
import time
from urllib.parse import parse_qsl, urlparse


class SM3:
    def __init__(self) -> None:
        self.reg: list[int] = []
        self.chunk: list[int] = []
        self.size: int = 0
        self.reset()

    def reset(self) -> None:
        self.reg = [
            1937774191,
            1226093241,
            388252375,
            3666478592,
            2842636476,
            372324522,
            3817729613,
            2969243214,
        ]
        self.chunk = []
        self.size = 0

    def write(self, e: str | list[int]) -> None:
        a = self._string_to_bytes(e) if isinstance(e, str) else e
        self.size += len(a)
        f = 64 - len(self.chunk)
        if len(a) < f:
            self.chunk.extend(a)
        else:
            self.chunk.extend(a[:f])
            while len(self.chunk) >= 64:
                self._compress(self.chunk[:64])
                self.chunk = a[f : min(f + 64, len(a))] if f < len(a) else []
                f += 64

    def sum(self, e: str | list[int] | None = None, t: str | None = None):
        if e is not None:
            self.reset()
            self.write(e)
        self._fill()
        for f in range(0, len(self.chunk), 64):
            self._compress(self.chunk[f : f + 64])
        if t == "hex":
            i: str | list[int] = "".join(
                self._pad_hex(format(self.reg[f], "x"), 8) for f in range(8)
            )
        else:
            i = [0] * 32
            for f in range(8):
                c = self.reg[f]
                i[4 * f + 3] = (255 & c) & 0xFFFFFFFF
                c >>= 8
                i[4 * f + 2] = (255 & c) & 0xFFFFFFFF
                c >>= 8
                i[4 * f + 1] = (255 & c) & 0xFFFFFFFF
                c >>= 8
                i[4 * f] = (255 & c) & 0xFFFFFFFF
        self.reset()
        return i

    # --- 内部实现 ---

    def _compress(self, t: list[int]) -> None:
        if len(t) < 64:
            return
        f = self._expand(t)
        i = self.reg[:]
        for c in range(64):
            o = (self._le(i[0], 12) + i[4] + self._le(self._de(c), c)) & 0xFFFFFFFF
            o = self._le(o & 0xFFFFFFFF, 7)
            s = (o ^ self._le(i[0], 12)) & 0xFFFFFFFF
            u = self._pe(c, i[0], i[1], i[2])
            u = (u + i[3] + s + f[c + 68]) & 0xFFFFFFFF
            b = self._he(c, i[4], i[5], i[6])
            b = (b + i[7] + o + f[c]) & 0xFFFFFFFF

            i[3] = i[2]
            i[2] = self._le(i[1], 9)
            i[1] = i[0]
            i[0] = u & 0xFFFFFFFF
            i[7] = i[6]
            i[6] = self._le(i[5], 19)
            i[5] = i[4]
            i[4] = (b ^ self._le(b, 9) ^ self._le(b, 17)) & 0xFFFFFFFF

        for _l in range(8):
            self.reg[_l] = (self.reg[_l] ^ i[_l]) & 0xFFFFFFFF

    def _expand(self, e: list[int]) -> list[int]:
        r = [0] * 132
        for t in range(16):
            r[t] = (
                (e[4 * t] << 24)
                | (e[4 * t + 1] << 16)
                | (e[4 * t + 2] << 8)
                | e[4 * t + 3]
            ) & 0xFFFFFFFF
        for n in range(16, 68):
            a = r[n - 16] ^ r[n - 9] ^ self._le(r[n - 3], 15)
            a = a ^ self._le(a, 15) ^ self._le(a, 23)
            r[n] = (a ^ self._le(r[n - 13], 7) ^ r[n - 6]) & 0xFFFFFFFF
        for n in range(64):
            r[n + 68] = (r[n] ^ r[n + 4]) & 0xFFFFFFFF
        return r

    def _fill(self) -> None:
        a = 8 * self.size
        self.chunk.append(128)
        f = len(self.chunk) % 64
        while f > 56:
            self.chunk.append(0)
            f = len(self.chunk) % 64
        while len(self.chunk) % 64 != 56:
            self.chunk.append(0)
        # 高 32 位
        c = math.floor(a / 0x100000000)
        for i in range(4):
            self.chunk.append((c >> (8 * (3 - i))) & 255)
        # 低 32 位
        for i in range(4):
            self.chunk.append((a >> (8 * (3 - i))) & 255)

    def _de(self, e: int) -> int:
        if 0 <= e < 16:
            return 2043430169
        return 2055708042 if 16 <= e < 64 else 0

    def _pe(self, e: int, r: int, t: int, n: int) -> int:
        if 0 <= e < 16:
            return (r ^ t ^ n) & 0xFFFFFFFF
        return ((r & t) | (r & n) | (t & n)) & 0xFFFFFFFF if 16 <= e < 64 else 0

    def _he(self, e: int, r: int, t: int, n: int) -> int:
        if 0 <= e < 16:
            return (r ^ t ^ n) & 0xFFFFFFFF
        return ((r & t) | (~r & n)) & 0xFFFFFFFF if 16 <= e < 64 else 0

    def _le(self, e: int, r: int) -> int:
        r %= 32
        return ((e << r) | (e >> (32 - r))) & 0xFFFFFFFF

    def _string_to_bytes(self, s: str) -> list[int]:
        """
        等价于 TS 中：
        const n = encodeURIComponent(str).replace(
          /%([0-9A-F]{2})/g,
          (_, r) => String.fromCharCode(parseInt(r, 16))
        )
        然后对 n 做 charCodeAt 得到字节数组。
        """
        from urllib.parse import quote

        # 1. encodeURIComponent(str)
        encoded = quote(
            s,
            safe="~-_.!~*'()",  # encodeURIComponent 的保留字符
        )
        # 2. 把 %XX 还原为对应的字节字符
        out_bytes: list[int] = []
        i = 0
        length = len(encoded)
        while i < length:
            ch = encoded[i]
            if ch == "%" and i + 2 < length:
                hex_part = encoded[i + 1 : i + 3]
                with contextlib.suppress(ValueError):
                    out_bytes.append(int(hex_part, 16))
                    i += 3
                    continue
            # 非 %XX：就是单字符，charCodeAt 直接是 ord(ch)
            out_bytes.append(ord(ch))
            i += 1
        return out_bytes

    @staticmethod
    def _pad_hex(num: str, size: int) -> str:
        return num.rjust(size, "0")


def rc4_encrypt(plaintext: str, key: str) -> str:
    s = list(range(256))
    j = 0
    key_len = len(key)

    for i in range(256):
        j = (j + s[i] + ord(key[i % key_len])) % 256
        s[i], s[j] = s[j], s[i]

    i = 0
    j = 0
    cipher_chars: list[str] = []
    for ch in plaintext:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        t = (s[i] + s[j]) % 256
        cipher_chars.append(chr(s[t] ^ ord(ch)))
    return "".join(cipher_chars)


def result_encrypt(long_str: str, num: str) -> str:
    s_obj: dict[str, str] = {
        "s0": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=",
        "s1": "Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
        "s2": "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
        "s3": "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe",
        "s4": "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe",
    }
    constant: dict[int, int] = {
        0: 16515072,
        1: 258048,
        2: 4032,
    }

    result = []
    lound = 0
    long_int = get_long_int(lound, long_str)

    total = len(long_str) // 3 * 4
    for i in range(total):
        if math.floor(i / 4) != lound:
            lound += 1
            long_int = get_long_int(lound, long_str)
        key = i % 4
        if key == 0:
            temp_int = (long_int & constant[0]) >> 18
        elif key == 1:
            temp_int = (long_int & constant[1]) >> 12
        elif key == 2:
            temp_int = (long_int & constant[2]) >> 6
        else:
            temp_int = long_int & 63
        result.append(s_obj[num][temp_int])  # type: ignore[index]
    return "".join(result)


def get_long_int(round_: int, long_str: str) -> int:
    round_ *= 3
    return (
        (ord(long_str[round_]) << 16)
        | (ord(long_str[round_ + 1]) << 8)
        | ord(long_str[round_ + 2])
    )


def gener_random(random_val: float, option: list[int]) -> list[int]:
    r = int(random_val)  # TS 里通过位运算会自动转 int
    return [
        (r & 255 & 170) | (option[0] & 85),
        (r & 255 & 85) | (option[0] & 170),
        ((r >> 8) & 255 & 170) | (option[1] & 85),
        ((r >> 8) & 255 & 85) | (option[1] & 170),
    ]


def generate_rc4_bb_str(
    url_search_params: str,
    user_agent: str,
    window_env_str: str,
    suffix: str = "cus",
    Arguments: list[int] | None = None,
) -> str:
    if Arguments is None:
        Arguments = [0, 1, 14]

    sm3 = SM3()
    # 严格对应 JS 的 Date.now()（毫秒时间戳，整数）
    start_time = int(time.time() * 1000)

    # url_search_params 两次 SM3 的结果
    url_search_params_list = sm3.sum(sm3.sum(url_search_params + suffix))
    # 后缀两次 SM3 的结果
    cus = sm3.sum(sm3.sum(suffix))

    # JS: String.fromCharCode.apply(null, [0.00390625, 1, 14])
    # 0.00390625 -> ToUint16(0.00390625) -> 0
    # 所以 key = "\x00\x01\x0e"
    rc4_key_for_ua = "".join(chr(int(c) & 0xFFFF) for c in (0.00390625, 1, 14))

    # 对 UA 处理后的结果
    ua = sm3.sum(
        result_encrypt(
            rc4_encrypt(user_agent, rc4_key_for_ua),
            "s3",
        )
    )
    end_time = int(time.time() * 1000)

    b: dict[int, object] = {
        8: 3,
        10: end_time,
        15: {
            "aid": 6383,
            "pageId": 6241,
            "boe": False,
            "ddrt": 7,
            "paths": {"include": [{}, {}, {}, {}, {}, {}, {}], "exclude": []},
            "track": {"mode": 0, "delay": 300, "paths": []},
            "dump": True,
            "rpU": "",
        },
        16: start_time,
        18: 44,
        19: [1, 0, 1, 5],
    }

    # 3 次加密开始时间
    b[20] = (b[16] >> 24) & 255  # type: ignore[index]
    b[21] = (b[16] >> 16) & 255  # type: ignore[index]
    b[22] = (b[16] >> 8) & 255  # type: ignore[index]
    b[23] = b[16] & 255  # type: ignore[index]
    b[24] = int(b[16] / 256 / 256 / 256 / 256)  # type: ignore[index]
    b[25] = int(b[16] / 256 / 256 / 256 / 256 / 256)  # type: ignore[index]

    b[26] = (Arguments[0] >> 24) & 255
    b[27] = (Arguments[0] >> 16) & 255
    b[28] = (Arguments[0] >> 8) & 255
    b[29] = Arguments[0] & 255

    b[30] = (Arguments[1] // 256) & 255
    b[31] = Arguments[1] % 256 & 255
    b[32] = (Arguments[1] >> 24) & 255
    b[33] = (Arguments[1] >> 16) & 255

    b[34] = (Arguments[2] >> 24) & 255
    b[35] = (Arguments[2] >> 16) & 255
    b[36] = (Arguments[2] >> 8) & 255
    b[37] = Arguments[2] & 255

    url_list = url_search_params_list  # type: ignore[assignment]
    b[38] = url_list[21]
    b[39] = url_list[22]

    cus_list = cus  # type: ignore[assignment]
    b[40] = cus_list[21]
    b[41] = cus_list[22]

    ua_list = ua  # type: ignore[assignment]
    b[42] = ua_list[23]
    b[43] = ua_list[24]

    b[44] = (b[10] >> 24) & 255  # type: ignore[index]
    b[45] = (b[10] >> 16) & 255  # type: ignore[index]
    b[46] = (b[10] >> 8) & 255  # type: ignore[index]
    b[47] = b[10] & 255  # type: ignore[index]
    b[48] = b[8]
    b[49] = int(b[10] / 256 / 256 / 256 / 256)  # type: ignore[index]
    b[50] = int(b[10] / 256 / 256 / 256 / 256 / 256)  # type: ignore[index]

    page_id = b[15]["pageId"]  # type: ignore[index]
    aid = b[15]["aid"]  # type: ignore[index]

    b[51] = page_id
    b[52] = (page_id >> 24) & 255
    b[53] = (page_id >> 16) & 255
    b[54] = (page_id >> 8) & 255
    b[55] = page_id & 255

    b[56] = aid
    b[57] = aid & 255
    b[58] = (aid >> 8) & 255
    b[59] = (aid >> 16) & 255
    b[60] = (aid >> 24) & 255

    window_env_list: list[int] = [ord(ch) for ch in window_env_str]
    b[64] = len(window_env_list)
    b[65] = b[64] & 255  # type: ignore[index]
    b[66] = (b[64] >> 8) & 255  # type: ignore[index]

    b[69] = 0
    b[70] = b[69] & 255  # type: ignore[index]
    b[71] = (b[69] >> 8) & 255  # type: ignore[index]

    b[72] = (
        b[18]
        ^ b[20]
        ^ b[26]
        ^ b[30]
        ^ b[38]
        ^ b[40]
        ^ b[42]
        ^ b[21]
        ^ b[27]
        ^ b[31]
        ^ b[35]
        ^ b[39]
        ^ b[41]
        ^ b[43]
        ^ b[22]
        ^ b[28]
        ^ b[32]
        ^ b[36]
        ^ b[23]
        ^ b[29]
        ^ b[33]
        ^ b[37]
        ^ b[44]
        ^ b[45]
        ^ b[46]
        ^ b[47]
        ^ b[48]
        ^ b[49]
        ^ b[50]
        ^ b[24]
        ^ b[25]
        ^ b[52]
        ^ b[53]
        ^ b[54]
        ^ b[55]
        ^ b[57]
        ^ b[58]
        ^ b[59]
        ^ b[60]
        ^ b[65]
        ^ b[66]
        ^ b[70]
        ^ b[71]
    )

    bb = [
        b[18],
        b[20],
        b[52],
        b[26],
        b[30],
        b[34],
        b[58],
        b[38],
        b[40],
        b[53],
        b[42],
        b[21],
        b[27],
        b[54],
        b[55],
        b[31],
        b[35],
        b[57],
        b[39],
        b[41],
        b[43],
        b[22],
        b[28],
        b[32],
        b[60],
        b[36],
        b[23],
        b[29],
        b[33],
        b[37],
        b[44],
        b[45],
        b[59],
        b[46],
        b[47],
        b[48],
        b[49],
        b[50],
        b[24],
        b[25],
        b[65],
        b[66],
        b[70],
        b[71],
        *window_env_list,
        b[72],
    ]
    return rc4_encrypt("".join(chr(x) for x in bb), chr(121))  # pyright: ignore[reportArgumentType]


def generate_random_str() -> str:
    random_str_list: list[int] = []
    random_str_list += gener_random(random.random() * 10000, [3, 45])
    random_str_list += gener_random(random.random() * 10000, [1, 0])
    random_str_list += gener_random(random.random() * 10000, [1, 5])
    return "".join(chr(x) for x in random_str_list)


def clean_user_agent_for_signing(user_agent: str) -> str:
    """
    清理 User-Agent 中的 Edge 标识
    """
    return re.sub(r"\s+Edg/[\d\.]+", "", user_agent)


def a_bogus(url: str, user_agent: str) -> str:
    """
    抖音 a_bogus 签名算法（Python 版）
    :param url: 需要签名的 URL
    :param user_agent: UA
    :return: a_bogus 字符串
    """
    cleaned_ua = clean_user_agent_for_signing(user_agent)

    parsed = urlparse(url)
    query_str = "&".join(
        f"{k}={v}" for k, v in parse_qsl(parsed.query, keep_blank_values=True)
    )

    window_env = "1536|747|1536|834|0|30|0|0|1536|834|1536|864|1525|747|24|24|Win32"

    result_str = generate_random_str() + generate_rc4_bb_str(
        query_str, cleaned_ua, window_env
    )
    return result_encrypt(result_str, "s4") + "="
