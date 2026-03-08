from __future__ import annotations

import hashlib
import time
from typing import TypedDict
from urllib.parse import urlparse


class XBogusResult(TypedDict):
    fullUrl: str
    xbogus: str
    userAgent: str


class XBogus:
    """
    X-Bogus 生成工具（TikTok/Douyin 签名算法）- Python 版本

    尽量一一对应原 TypeScript 实现：
    - 使用 latin-1 模拟 Buffer 的逐字节行为
    - RC4、MD5 逻辑严格按 TS 写法移植
    """

    def __init__(self) -> None:
        # 初始化字符映射表，对应 this.charMap
        self.charMap: list[int | None] = [None] * 128
        for i in range(48, 58):  # '0'..'9'
            self.charMap[i] = i - 48
        for i in range(65, 71):  # 'A'..'F'
            self.charMap[i] = i - 55
        for i in range(97, 103):  # 'a'..'f'
            self.charMap[i] = i - 87

        self.base64Charset: str = (
            "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe="
        )
        # Buffer.from([0x00, 0x01, 0x0c])
        self.uaKey: bytes = bytes([0x00, 0x01, 0x0C])
        self.defaultUa: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
        )

        # 对齐 TS 里的可选属性
        self.params: str | None = None
        self.xb: str | None = None

    # --- 内部工具方法 ---

    def _md5_str_to_array(self, md5_str: str) -> list[int]:
        """
        对应 TS: private md5StrToArray (md5Str: string): number[]
        """
        result: list[int] = []

        if len(md5_str) > 32:
            result.extend(ord(ch) for ch in md5_str)
            return result

        idx = 0
        while idx < len(md5_str):
            left_char_code = ord(md5_str[idx])
            right_char_code = ord(md5_str[idx + 1])

            left = self.charMap[left_char_code]
            right = self.charMap[right_char_code]
            if left is None or right is None:
                raise ValueError(
                    f"Invalid MD5 character: {md5_str[idx]}{md5_str[idx + 1]}"
                )

            result.append((left << 4) | right)
            idx += 2

        return result

    def _md5(self, input_val: str | list[int]) -> str:
        """
        对应 TS: private md5 (input: string | number[]): string
        """
        if isinstance(input_val, str):
            data_array = self._md5_str_to_array(input_val)
        else:
            data_array = input_val

        data_bytes = bytes(data_array)
        return hashlib.md5(data_bytes).hexdigest()

    def _md5_encrypt(self, url_path: str) -> list[int]:
        """
        对应 TS: private md5Encrypt (urlPath: string): number[]
        """
        first_md5 = self._md5(url_path)
        first_array = self._md5_str_to_array(first_md5)
        second_md5 = self._md5(first_array)
        return self._md5_str_to_array(second_md5)

    def _encoding_conversion(self, *params: int | str) -> str:
        """
        对应 TS: private encodingConversion (...params: (number | string)[]): string
        返回 latin1 字符串
        """
        byte_list: list[int] = []

        for param in params:
            if isinstance(param, (int, float)):
                byte_list.append(int(param))
            elif isinstance(param, str):
                byte_list.extend(ord(ch) for ch in param)
        return bytes(byte_list).decode("latin1")

    def _encoding_conversion2(self, a: int, b: int, c: str) -> str:
        """
        对应 TS: private encodingConversion2 (a: number, b: number, c: string): string
        """
        return chr(a) + chr(b) + c

    def _rc4_encrypt(self, key: bytes | str, data: str) -> str:
        """
        对应 TS: private rc4Encrypt (key: string | Buffer, data: string): string
        key / data 都按 latin1 解释
        """
        if isinstance(key, str):
            key_bytes: bytes = key.encode("latin1")
        else:
            assert isinstance(key, bytes)
            key_bytes = key
        data_bytes: bytes = data.encode("latin1")

        S: list[int] = list(range(256))
        j: int = 0

        # KSA
        for i in range(256):
            kb: int = key_bytes[i % len(key_bytes)]
            j = (j + S[i] + kb) % 256
            S[i], S[j] = S[j], S[i]

        i = 0
        j = 0
        out = bytearray(len(data_bytes))

        # PRGA
        for k in range(len(data_bytes)):
            i = (i + 1) % 256
            j = (j + S[i]) % 256
            S[i], S[j] = S[j], S[i]
            t = (S[i] + S[j]) % 256
            out[k] = data_bytes[k] ^ S[t]

        return out.decode("latin1")

    def _calculation(self, a1: int, a2: int, a3: int) -> str:
        """
        对应 TS: private calculation (a1: number, a2: number, a3: number): string
        """
        x1 = (a1 & 0xFF) << 16
        x2 = (a2 & 0xFF) << 8
        x3 = x1 | x2 | (a3 & 0xFF)

        c1 = self.base64Charset[(x3 & 0xFFC000) >> 18]
        c2 = self.base64Charset[(x3 & 0x3F000) >> 12]
        c3 = self.base64Charset[(x3 & 0xFC0) >> 6]
        c4 = self.base64Charset[x3 & 0x3F]

        return c1 + c2 + c3 + c4

    # --- 对外主方法 ---

    def getXBogus(self, url: str, ua: str | None = None) -> XBogusResult:
        """
        生成 X-Bogus 签名
        对应 TS:
          public getXBogus (url: string, ua?: string): XBogusResult
        """
        parsed = urlparse(url)
        url_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        current_ua = ua or self.defaultUa

        # 生成 array1
        rc4_encrypted_ua = self._rc4_encrypt(self.uaKey, current_ua)
        base64_ua = rc4_encrypted_ua.encode("latin1").hex()  # 这里先用 hex 过渡
        # 注意：TS 是 Buffer(...).toString('base64')
        # 为保持一一对应，应当用真正 base64：
        import base64

        base64_ua = base64.b64encode(rc4_encrypted_ua.encode("latin1")).decode("ascii")
        md5_ua = self._md5(base64_ua)
        array1 = self._md5_str_to_array(md5_ua)

        # 生成 array2
        empty_str_md5 = "d41d8cd98f00b204e9800998ecf8427e"
        array2 = self._md5_str_to_array(
            self._md5(self._md5_str_to_array(empty_str_md5))
        )

        # 生成 URL 加密数组
        url_encrypted_array = self._md5_encrypt(url_path)

        # 时间戳与固定值处理
        timestamp = int(time.time())  # Math.floor(Date.now() / 1000)
        ct = 536919696

        # 构建 newArray 并计算异或结果
        new_array: list[int] = [
            64,
            1,
            1,
            12,
            url_encrypted_array[14],
            url_encrypted_array[15],
            array2[14],
            array2[15],
            array1[14],
            array1[15],
            (timestamp >> 24) & 0xFF,
            (timestamp >> 16) & 0xFF,
            (timestamp >> 8) & 0xFF,
            timestamp & 0xFF,
            (ct >> 24) & 0xFF,
            (ct >> 16) & 0xFF,
            (ct >> 8) & 0xFF,
            ct & 0xFF,
        ]

        xor_result = new_array[0]
        for i in range(1, len(new_array)):
            xor_result ^= new_array[i]
        new_array.append(xor_result)

        # 拆分与合并数组
        array3: list[int] = []
        array4: list[int] = []
        idx = 0
        while idx < len(new_array):
            array3.append(new_array[idx])
            if idx + 1 < len(new_array):
                array4.append(new_array[idx + 1])
            idx += 2
        merged_array: list[int] = [*array3, *array4]

        # 生成乱码字符串
        first_conversion = self._encoding_conversion(*merged_array)
        rc4_garbled = self._rc4_encrypt("ÿ", first_conversion)  # 'ÿ' == 0xFF in latin1
        garbled_code = self._encoding_conversion2(2, 255, rc4_garbled)

        # 生成最终 X-Bogus
        xb = ""
        idx = 0
        while idx < len(garbled_code) and idx + 2 < len(garbled_code):
            a1 = ord(garbled_code[idx])
            a2 = ord(garbled_code[idx + 1])
            a3 = ord(garbled_code[idx + 2])
            xb += self._calculation(a1, a2, a3)
            idx += 3

        self.xb = xb

        # 构建最终 URL
        full_url = f"{url}&X-Bogus={xb}" if "?" in url else f"{url}?X-Bogus={xb}"
        self.params = full_url

        return XBogusResult(fullUrl=full_url, xbogus=xb, userAgent=current_ua)
