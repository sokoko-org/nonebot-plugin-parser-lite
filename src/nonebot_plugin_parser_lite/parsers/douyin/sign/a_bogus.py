# All the content in this article is only for learning and communication use,
# not for any other purpose, strictly prohibited for commercial use and illegal use,
# otherwise all the consequences are irrelevant to the author!

import base64
import random
import re
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse

from .sm3 import SM3


def rc4_encrypt(plaintext: str | bytes, key: bytes) -> bytes:
    """
    标准的 RC4 实现
    """
    raw = plaintext.encode() if isinstance(plaintext, str) else plaintext
    s = list(range(256))
    j = 0
    key_len = len(key)
    for i in range(256):
        j = (j + s[i] + key[i % key_len]) % 256
        s[i], s[j] = s[j], s[i]
    i = 0
    j = 0
    out = bytearray(len(raw))
    for k, byte_val in enumerate(raw):
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]

        t = (s[i] + s[j]) % 256
        out[k] = s[t] ^ byte_val

    return bytes(out)


def result_encrypt(long_str: str | bytes, num: str) -> str:
    """
    变异 Base64 加密函数

    :param long_str: 待加密的字符串或字节流
    :param num: 密码表选择，支持 's0', 's1', 's2', 's3', 's4'
    :return: 变异 Base64 编码后的字符串
    """
    s_obj = {
        "s0": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=",
        "s1": "Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
        "s2": "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
        "s3": "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe=",
        "s4": "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe=",
    }
    raw_bytes = long_str.encode("utf-8") if isinstance(long_str, str) else long_str
    standard_b64 = base64.b64encode(raw_bytes).decode("ascii")

    if num == "s0":
        return standard_b64
    translation_table = str.maketrans(s_obj["s0"], s_obj[num])
    return standard_b64.translate(translation_table)


def gener_random(random_val: int, option: list[int] | bytes) -> bytes:
    """
    比特位交织特征派生函数

    :param random_val: 随机数/种子整数
    :param option: 包含配置项的数组或字节流 (至少需要 2 字节)
    :return: 派生出的 4 字节 bytes 对象
    """
    MASK_EVEN = 0xAA  # 170 -> 10101010 (偶数位)
    MASK_ODD = 0x55  # 85  -> 01010101 (奇数位)

    r_byte0 = random_val & 0xFF
    r_byte1 = (random_val >> 8) & 0xFF

    return bytes(
        [
            (r_byte0 & MASK_EVEN) | (option[0] & MASK_ODD),
            (r_byte0 & MASK_ODD) | (option[0] & MASK_EVEN),
            (r_byte1 & MASK_EVEN) | (option[1] & MASK_ODD),
            (r_byte1 & MASK_ODD) | (option[1] & MASK_EVEN),
        ]
    )


def generate_rc4_bb_str(
    url_search_params: str,
    user_agent: str,
    window_env_str: str,
) -> bytes:
    """
    现代化生产级反爬指纹生成函数 (100% 结果对齐原 TS/JS 逻辑)

    :return: 返回经过 RC4("y") 加密后的指纹字节流 (bytes)
    """
    arguments = [0, 1, 14]
    suffix = "cus"

    start_time = int(time.time() * 1000)
    url_search_params_list = list(SM3.sum(SM3.sum(url_search_params + suffix)))

    cus = list(SM3.sum(SM3.sum(suffix)))

    ua_rc4_key = bytes([0, 1, 14])
    ua_rc4_res = rc4_encrypt(user_agent, ua_rc4_key)
    ua_b64_res = result_encrypt(ua_rc4_res, "s3")
    ua = list(SM3.sum(ua_b64_res))

    end_time = int(time.time() * 1000)
    b: dict[int, Any] = {8: 3, 10: end_time, 16: start_time, 18: 44}

    start_bytes = start_time.to_bytes(8, byteorder="big")
    b[20], b[21], b[22], b[23] = (
        start_bytes[4],
        start_bytes[5],
        start_bytes[6],
        start_bytes[7],
    )
    b[24], b[25] = start_bytes[3], start_bytes[2]

    arg0_bytes = arguments[0].to_bytes(4, byteorder="big")
    b[26], b[27], b[28], b[29] = (
        arg0_bytes[0],
        arg0_bytes[1],
        arg0_bytes[2],
        arg0_bytes[3],
    )

    b[30] = int(arguments[1] // 256) & 255
    b[31] = (arguments[1] % 256) & 255
    arg1_bytes = arguments[1].to_bytes(4, byteorder="big")
    b[32], b[33] = arg1_bytes[0], arg1_bytes[1]

    arg2_bytes = arguments[2].to_bytes(4, byteorder="big")
    b[34], b[35], b[36], b[37] = (
        arg2_bytes[0],
        arg2_bytes[1],
        arg2_bytes[2],
        arg2_bytes[3],
    )
    b[38] = url_search_params_list[21]
    b[39] = url_search_params_list[22]
    b[40] = cus[21]
    b[41] = cus[22]
    b[42] = ua[23]
    b[43] = ua[24]

    end_bytes = end_time.to_bytes(8, byteorder="big")
    b[44], b[45], b[46], b[47] = end_bytes[4], end_bytes[5], end_bytes[6], end_bytes[7]
    b[48] = b[8]
    b[49], b[50] = end_bytes[3], end_bytes[2]

    page_id = 6241
    b[51] = page_id
    pid_bytes = page_id.to_bytes(4, byteorder="big")
    b[52], b[53], b[54], b[55] = pid_bytes[0], pid_bytes[1], pid_bytes[2], pid_bytes[3]

    aid = 6383
    b[56] = aid
    aid_bytes = aid.to_bytes(4, byteorder="big")
    b[57], b[58], b[59], b[60] = (
        aid_bytes[3],
        aid_bytes[2],
        aid_bytes[1],
        aid_bytes[0],
    )

    window_env_list = list(window_env_str.encode("utf-8"))
    b[64] = len(window_env_list)
    b[65] = b[64] & 255
    b[66] = (b[64] >> 8) & 255

    b[69] = 0
    b[70] = b[69] & 255
    b[71] = (b[69] >> 8) & 255

    checksum_keys = [
        18,
        20,
        26,
        30,
        38,
        40,
        42,
        21,
        27,
        31,
        35,
        39,
        41,
        43,
        22,
        28,
        32,
        36,
        23,
        29,
        33,
        37,
        44,
        45,
        46,
        47,
        48,
        49,
        50,
        24,
        25,
        52,
        53,
        54,
        55,
        57,
        58,
        59,
        60,
        65,
        66,
        70,
        71,
    ]
    checksum = 0
    for key in checksum_keys:
        checksum ^= b[key]
    b[72] = checksum

    bb_layout = [
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
    ]
    final_payload = bytes(bb_layout + window_env_list + [b[72]])
    final_rc4_key = b"y"
    return rc4_encrypt(final_payload, final_rc4_key)


def generate_random_str() -> bytes:
    """动态随机盐生成函数。"""
    res1 = gener_random(int(random.random() * 10000), [3, 45])
    res2 = gener_random(int(random.random() * 10000), [1, 0])
    res3 = gener_random(int(random.random() * 10000), [1, 5])
    return res1 + res2 + res3


def clean_user_agent_for_signing(user_agent: str) -> str:
    """清理 User-Agent 中的 Edge 标识"""
    return re.sub(r"\s+Edg/[\d\.]+", "", user_agent)


def a_bogus(url: str, user_agent: str) -> str:
    """
    a_bogus 签名算法总入口

    :param url: 待签名的完整 API URL 请求地址
    :param user_agent: 发起请求的原始 User-Agent
    :return: 算好的 a_bogus 签名字符串
    """
    cleaned_ua = clean_user_agent_for_signing(user_agent)

    parsed_url = urlparse(url)
    query_params = urlencode(parse_qsl(parsed_url.query))

    random_salt = generate_random_str()

    window_env = "1536|747|1536|834|0|30|0|0|1536|834|1536|864|1525|747|24|24|Win32"
    fingerprint_bytes = generate_rc4_bb_str(query_params, cleaned_ua, window_env)
    mixed_payload = random_salt + fingerprint_bytes
    return result_encrypt(mixed_payload, "s4")
