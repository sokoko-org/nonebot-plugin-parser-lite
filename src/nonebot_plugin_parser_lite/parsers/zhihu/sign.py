# 知乎 zse96 签名算法
# 移植自 zly2006/zhihu-plus-plus


import hashlib
from urllib.parse import quote, urlparse

# fmt: off
# ruff: disable [E501]
ZK = [
    1170614578, 1024848638, 1413669199, 3951632832, 3528873006, 2921909214, 4151847688, 3997739139,
    1933479194, 3323781115, 3888513386, 460404854, 3747539722, 2403641034, 2615871395, 2119585428,
    2265697227, 2035090028, 2773447226, 4289380121, 4217216195, 2200601443, 3051914490, 1579901135,
    1321810770, 456816404, 2903323407, 4065664991, 330002838, 3506006750, 363569021, 2347096187,
]

ZB = [
    20, 223, 245, 7, 248, 2, 194, 209, 87, 6, 227, 253, 240, 128, 222, 91, 237, 9, 125, 157, 230,
    93, 252, 205, 90, 79, 144, 199, 159, 197, 186, 167, 39, 37, 156, 198, 38, 42, 43, 168, 217,
    153, 15, 103, 80, 189, 71, 191, 97, 84, 247, 95, 36, 69, 14, 35, 12, 171, 28, 114, 178, 148,
    86, 182, 32, 83, 158, 109, 22, 255, 94, 238, 151, 85, 77, 124, 254, 18, 4, 26, 123, 176, 232,
    193, 131, 172, 143, 142, 150, 30, 10, 146, 162, 62, 224, 218, 196, 229, 1, 192, 213, 27, 110,
    56, 231, 180, 138, 107, 242, 187, 54, 120, 19, 44, 117, 228, 215, 203, 53, 239, 251, 127, 81,
    11, 133, 96, 204, 132, 41, 115, 73, 55, 249, 147, 102, 48, 122, 145, 106, 118, 74, 190, 29, 16,
    174, 5, 177, 129, 63, 113, 99, 31, 161, 76, 246, 34, 211, 13, 60, 68, 207, 160, 65, 111, 82,
    165, 67, 169, 225, 57, 112, 244, 155, 51, 236, 200, 233, 58, 61, 47, 100, 137, 185, 64, 17, 70,
    234, 163, 219, 108, 170, 166, 59, 149, 52, 105, 24, 212, 78, 173, 45, 0, 116, 226, 119, 136,
    206, 135, 175, 195, 25, 92, 121, 208, 126, 139, 3, 75, 141, 21, 130, 98, 241, 40, 154, 66, 184,
    49, 181, 46, 243, 88, 101, 183, 8, 23, 72, 188, 104, 179, 210, 134, 250, 201, 164, 89, 216,
    202, 220, 50, 221, 152, 140, 33, 235, 214,
]
# ruff: enable [E501]
# fmt:on

ALPHABET = "6fpLRqJO8M/c3jnYxFkUVC4ZIG12SiH=5v0mXDazWBTsuw7QetbKdoPyAl+hN9rgE"
KEY16 = b"059053f7d15e01d7"


def read_u32_be(b: bytes, off: int) -> int:
    return (
        ((b[off] & 0xFF) << 24)
        | ((b[off + 1] & 0xFF) << 16)
        | ((b[off + 2] & 0xFF) << 8)
        | (b[off + 3] & 0xFF)
    )


def write_u32_be(v: int, out: bytearray, off: int) -> None:
    out[off] = (v >> 24) & 0xFF
    out[off + 1] = (v >> 16) & 0xFF
    out[off + 2] = (v >> 8) & 0xFF
    out[off + 3] = v & 0xFF


def rotate_left(n: int, bits: int) -> int:
    n &= 0xFFFFFFFF
    return ((n << bits) | (n >> (32 - bits))) & 0xFFFFFFFF


def g_transform(tt: int) -> int:
    te0 = (tt >> 24) & 0xFF
    te1 = (tt >> 16) & 0xFF
    te2 = (tt >> 8) & 0xFF
    te3 = tt & 0xFF

    ti = (
        ((ZB[te0] & 0xFF) << 24)
        | ((ZB[te1] & 0xFF) << 16)
        | ((ZB[te2] & 0xFF) << 8)
        | (ZB[te3] & 0xFF)
    )

    return (
        ti
        ^ rotate_left(ti, 2)
        ^ rotate_left(ti, 10)
        ^ rotate_left(ti, 18)
        ^ rotate_left(ti, 24)
    ) & 0xFFFFFFFF


def r_block(input16: bytes) -> bytes:
    tr = [0] * 36
    tr[0] = read_u32_be(input16, 0)
    tr[1] = read_u32_be(input16, 4)
    tr[2] = read_u32_be(input16, 8)
    tr[3] = read_u32_be(input16, 12)

    for i in range(32):
        ta = g_transform((tr[i + 1] ^ tr[i + 2] ^ tr[i + 3] ^ ZK[i]) & 0xFFFFFFFF)
        tr[i + 4] = (tr[i] ^ ta) & 0xFFFFFFFF

    out = bytearray(16)
    write_u32_be(tr[35], out, 0)
    write_u32_be(tr[34], out, 4)
    write_u32_be(tr[33], out, 8)
    write_u32_be(tr[32], out, 12)
    return bytes(out)


def x_blocks(data: bytes, iv0: bytes) -> bytes:
    iv = bytearray(iv0)
    out = bytearray(len(data))
    out_off = 0
    for off in range(0, len(data), 16):
        mixed = bytearray(16)
        for i in range(16):
            mixed[i] = data[off + i] ^ iv[i]
        iv = bytearray(r_block(bytes(mixed)))
        out[out_off : out_off + 16] = iv
        out_off += 16
    return bytes(out)


def custom_encode(bytes_in: bytes) -> str:
    rem = len(bytes_in) % 3
    if rem != 0:
        bytes_in += b"\x00" * (3 - rem)

    out = []
    i = 0
    p = len(bytes_in) - 1

    while p >= 0:
        v = 0

        b0 = bytes_in[p] & 0xFF
        m0 = (58 >> (8 * (i % 4))) & 0xFF
        i += 1
        v |= (b0 ^ m0) & 0xFF

        b1 = bytes_in[p - 1] & 0xFF
        m1 = (58 >> (8 * (i % 4))) & 0xFF
        i += 1
        v |= ((b1 ^ m1) & 0xFF) << 8

        b2 = bytes_in[p - 2] & 0xFF
        m2 = (58 >> (8 * (i % 4))) & 0xFF
        i += 1
        v |= ((b2 ^ m2) & 0xFF) << 16

        out.extend(
            (
                ALPHABET[v & 63],
                ALPHABET[(v >> 6) & 63],
                ALPHABET[(v >> 12) & 63],
                ALPHABET[(v >> 18) & 63],
            )
        )
        p -= 3

    return "".join(out)


class ZseSigner:
    @staticmethod
    def encrypt_zse_v4(input_str: str) -> str:
        plain = bytearray()
        plain.append(210)
        plain.append(0)

        encoded = quote(input_str, safe="~()*!")
        for char in encoded:
            plain.append(ord(char))

        pad = 16 - (len(plain) % 16)
        for _ in range(pad):
            plain.append(pad)

        first = bytearray(16)
        for i in range(16):
            first[i] = plain[i] ^ KEY16[i] ^ 42

        c0 = r_block(bytes(first))
        cipher = bytearray(len(plain))
        cipher[:16] = c0

        if len(plain) > 16:
            rest = x_blocks(bytes(plain[16:]), c0)
            cipher[16:] = rest

        return custom_encode(bytes(cipher))


class ZhihuFetchSignature:
    @classmethod
    def create_zse96_header(
        cls, zse93: str, url: str, dc0: str, body: str | None = None
    ) -> str:
        parsed_url = urlparse(url)
        pathname = parsed_url.path
        if parsed_url.query:
            pathname += f"?{parsed_url.query}"
        if not pathname.startswith("/"):
            pathname = f"/{pathname}"

        source_elements = [zse93, pathname, dc0]
        if body is not None:
            source_elements.append(body)

        sign_source = "+".join(source_elements)
        md5_result = hashlib.md5(sign_source.encode("utf-8")).hexdigest()

        return f"2.0_{ZseSigner.encrypt_zse_v4(md5_result)}"


def sign_zhihu_fetch_request(
    url: str, dc0: str = "", body: str | None = None, zse93: str = "101_3_3.0"
) -> dict:
    """
    获取签名后的请求头
    """
    zse96 = ZhihuFetchSignature.create_zse96_header(
        zse93=zse93, url=url, dc0=dc0, body=body
    )
    return {"x-zse-93": zse93, "x-zse-96": zse96, "x-requested-with": "fetch"}


if __name__ == "__main__":
    v = sign_zhihu_fetch_request("https://www.zhihu.com/api/v4/questions/67423622")[
        "x-zse-96"
    ]
    print(v)  # noqa: T201
    print(v == "2.0_bw8rs/Qvnxh3cHhoYw8Q9zT3dxVk2HASUMPIxxuR2Webcc8W=Pn6iebqbq5Y1sI/")  # noqa: T201
