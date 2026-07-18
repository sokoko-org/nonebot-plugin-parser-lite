import binascii
import io
import random
import re
import struct
import time
import urllib.parse
import uuid

from Cryptodome.Cipher import PKCS1_OAEP
from Cryptodome.Hash import SHA256
from Cryptodome.PublicKey import RSA
import ujson

from .client import CLIENT, HEADERS, Response
from .exceptions import (
    BiliHelperException,
    CookieInvalidException,
    CookiesRefreshException,
)

CORRESPOND_KEY = RSA.importKey(
    """\
-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDLgd2OAkcGVtoE3ThUREbio0Eg
Uc/prcajMKXvkCKFCWhJYJcLkcM2DKKcSeFpD/j6Boy538YXnR6VhcuUJOhH2x71
nzPjfdTcqMz7djHum0qSZA0AyCBDABUqCrfNgCiJ00Ra7GmRj+YCK1NJEuewlb40
JNrRuoEUXpabUzGB8QIDAQAB
-----END PUBLIC KEY-----"""
)
CORRESPOND_CIPHER = PKCS1_OAEP.new(CORRESPOND_KEY, SHA256)

LAST_REFRESH_TIME = 0


class Credential:
    """
    凭证类，用于各种请求操作的验证
    """

    def __init__(
        self,
        sessdata: str | None = None,
        bili_jct: str | None = None,
        buvid3: str | None = None,
        buvid4: str | None = None,
        dedeuserid: str | None = None,
        ac_time_value: str | None = None,
    ) -> None:
        """
        各字段获取方式查看：https://nemo2011.github.io/bilibili-api/#/get-credential.md

        :param sessdata: 浏览器 Cookies 中的 SESSDATA 字段值, defaults to None
        :param bili_jct: 浏览器 Cookies 中的 bili_jct 字段值, defaults to None
        :param buvid3: 浏览器 Cookies 中的 BUVID3 字段值, defaults to None
        :param buvid4: 浏览器 Cookies 中的 BUVID4 字段值, defaults to None
        :param dedeuserid: 浏览器 Cookies 中的 DedeUserID 字段值, defaults to None
        :param ac_time_value: 浏览器 Cookies 中的 ac_time_value 字段值, defaults to None
        """
        self.sessdata = (
            None
            if sessdata is None
            else (
                sessdata if sessdata.find("%") != -1 else urllib.parse.quote(sessdata)
            )
        )
        self.bili_jct = bili_jct
        self.buvid3 = buvid3
        self.buvid4 = buvid4
        self.dedeuserid = dedeuserid
        self.ac_time_value = ac_time_value

    def get_cookies(self) -> dict[str, str]:
        """
        获取请求 Cookies 字典

        :return: 请求 Cookies 字典
        """
        cookies = {
            "SESSDATA": self.sessdata or "",
            "buvid3": self.buvid3 or "",
            "buvid4": self.buvid4 or "",
            "bili_jct": self.bili_jct or "",
            "ac_time_value": self.ac_time_value or "",
        }
        if self.dedeuserid:
            cookies["DedeUserID"] = self.dedeuserid
        return cookies

    async def get_buvid_cookies(self) -> dict[str, str]:
        """
        获取请求 Cookies 字典，自动补充 buvid 字段

        :return: 请求 Cookies 字典
        """
        cookies = {
            "SESSDATA": self.sessdata or "",
            "buvid3": self.buvid3 or (await get_buvid())[0],
            "buvid4": self.buvid4 or (await get_buvid())[1],
            "bili_jct": self.bili_jct or "",
            "ac_time_value": self.ac_time_value or "",
        }
        if self.dedeuserid:
            cookies["DedeUserID"] = self.dedeuserid

        return cookies

    def has_dedeuserid(self) -> bool:
        """
        是否提供 dedeuserid。

        :return: 是否提供 dedeuserid。
        """
        return self.dedeuserid is not None and self.dedeuserid != ""

    def has_sessdata(self) -> bool:
        """
        是否提供 sessdata。

        :return: 是否提供 sessdata。
        """
        return self.sessdata is not None and self.sessdata != ""

    def has_bili_jct(self) -> bool:
        """
        是否提供 bili_jct。

        :return: 是否提供 bili_jct。
        """
        return self.bili_jct is not None and self.bili_jct != ""

    def has_buvid3(self) -> bool:
        """
        是否提供 buvid3

        :return: 是否提供 buvid3
        """
        return self.buvid3 is not None and self.buvid3 != ""

    def has_buvid4(self) -> bool:
        """
        是否提供 buvid4

        :return: 是否提供 buvid4
        """
        return self.buvid4 is not None and self.buvid4 != ""

    def has_ac_time_value(self) -> bool:
        """
        是否提供 ac_time_value

        Returns:
            bool: 是否提供 ac_time_value
        """
        return self.ac_time_value is not None and self.ac_time_value != ""

    def raise_for_no_sessdata(self):
        """
        没有提供 sessdata 则抛出异常。
        """
        if not self.has_sessdata():
            raise BiliHelperException("no sessdata provided")

    def raise_for_no_bili_jct(self):
        """
        没有提供 bili_jct 则抛出异常
        """
        if not self.has_bili_jct():
            raise BiliHelperException("no bili_jct provided")

    def raise_for_no_buvid3(self):
        """
        没有提供 buvid3 时抛出异常
        """
        if not self.has_buvid3():
            raise BiliHelperException("no buvid3 provided")

    def raise_for_no_buvid4(self):
        """
        没有提供 buvid3 时抛出异常
        """
        if not self.has_buvid4():
            raise BiliHelperException("no buvid4 provided")

    def raise_for_no_dedeuserid(self):
        """
        没有提供 DedeUserID 时抛出异常
        """
        if not self.has_dedeuserid():
            raise BiliHelperException("no DedeUserID provided")

    def raise_for_no_ac_time_value(self):
        """
        没有提供 ac_time_value 时抛出异常。
        """
        if not self.has_ac_time_value():
            raise BiliHelperException("no ac_time_value provided")

    async def check_refresh(self) -> bool:
        """
        检查是否需要刷新 cookies

        Returns:
            bool: cookies 是否需要刷新
        """
        return await _check_refresh(self)

    async def check_valid(self) -> bool:
        """
        检查 cookies 是否有效

        :return: cookies 是否有效
        """
        return await _check_valid(self)

    async def refresh(self) -> None:
        """
        刷新 cookies
        """
        global LAST_REFRESH_TIME
        new_cred: Credential = await _refresh_cookies(self)
        self.sessdata = new_cred.sessdata
        self.bili_jct = new_cred.bili_jct
        self.dedeuserid = new_cred.dedeuserid
        self.ac_time_value = new_cred.ac_time_value
        LAST_REFRESH_TIME = time.time()

    @staticmethod
    def from_cookies(cookies: dict | None = None) -> "Credential":
        """
        从 cookies 新建 Credential

        :param cookies: cookies, defaults to None
        :return: 凭证类
        """
        if cookies is None:
            cookies = {}
        c = Credential()
        c.sessdata = cookies.get("SESSDATA")
        c.bili_jct = cookies.get("bili_jct")
        c.buvid3 = cookies.get("buvid3")
        c.buvid4 = cookies.get("buvid4")
        c.dedeuserid = cookies.get("DedeUserID")
        c.ac_time_value = cookies.get("ac_time_value")
        return c


async def _check_valid(credential: Credential) -> bool:
    """
    检查cookie是否有效

    :param credential: 凭证
    :return: 是否有效
    """
    result = (
        await CLIENT.get(
            "https://api.bilibili.com/x/web-interface/nav",
            cookies=credential.get_cookies(),
        )
    ).json()
    return result["data"]["isLogin"]


async def _check_refresh(credential: Credential) -> bool:
    """
    检查cookie是否需要刷新

    :param credential: 凭证
    :raises CredentialInvalidException: cookie无效
    :return: 是否需要刷新
    """
    if time.time() - LAST_REFRESH_TIME > 60 * 30:
        result = (
            await CLIENT.get(
                "https://passport.bilibili.com/x/passport-login/web/cookie/info",
                cookies=credential.get_cookies(),
            )
        ).json()
        if result["code"] == -101:
            raise CookieInvalidException(result)
        return result["data"]["refresh"]
    return False


def _getCorrespondPath() -> str:
    ts = round(time.time() * 1000)
    encrypted = CORRESPOND_CIPHER.encrypt(f"refresh_{ts}".encode())
    return binascii.b2a_hex(encrypted).decode()


async def _get_refresh_csrf(credential: Credential) -> str:
    cookies = credential.get_cookies()
    cookies["buvid3"] = str(uuid.uuid1())
    resp: Response = await CLIENT.get(
        url=f"https://www.bilibili.com/correspond/1/{_getCorrespondPath()}",
        cookies=cookies,
    )
    if resp.status_code == 404:
        raise CookiesRefreshException("correspondPath 过期或错误。")
    elif resp.status_code == 200:
        text = resp.text
        return re.findall('<div id="1-name">(.+?)</div>', text)[0]
    else:
        raise CookiesRefreshException("获取刷新 Cookies 的 csrf 失败。")


async def _refresh_cookies(credential: Credential) -> Credential:
    credential.raise_for_no_bili_jct()
    credential.raise_for_no_ac_time_value()
    refresh_csrf = await _get_refresh_csrf(credential)
    cookies = credential.get_cookies()
    cookies["buvid3"] = str(uuid.uuid1())
    resp: Response = await CLIENT.post(
        url="https://passport.bilibili.com/x/passport-login/web/cookie/refresh",
        cookies=cookies,
        data={
            "csrf": credential.bili_jct or "",
            "refresh_csrf": refresh_csrf,
            "refresh_token": credential.ac_time_value or "",
            "source": "main_web",
        },
    )
    if resp.status_code != 200 or resp.json()["code"] != 0:
        raise CookiesRefreshException("刷新 Cookies 失败")
    new_credential = Credential(
        sessdata=resp.cookies["SESSDATA"],
        bili_jct=resp.cookies["bili_jct"],
        dedeuserid=resp.cookies["DedeUserID"],
        ac_time_value=resp.json()["data"]["refresh_token"],
    )
    await _confirm_refresh(credential, new_credential)
    return new_credential


async def _confirm_refresh(
    old_credential: Credential, new_credential: Credential
) -> None:
    await CLIENT.post(
        url="https://passport.bilibili.com/x/passport-login/web/confirm/refresh",
        cookies=new_credential.get_cookies(),
        data={
            "refresh_csrf": "refresh_csrf",
            "source": "main_web",
            "csrf": new_credential.bili_jct or "",
            "refresh_token": old_credential.ac_time_value or "",
        },
    )


__buvid3 = ""
__buvid4 = ""


async def _get_spi_buvid() -> dict:
    return (
        await CLIENT.get(url="https://api.bilibili.com/x/frontend/finger/spi")
    ).json()["data"]


async def get_buvid() -> tuple[str, str]:
    """
    获取 buvid3 和 buvid4

    Returns:
        Tuple[str, str]: 第 0 项为 buvid3，第 1 项为 buvid4。
    """
    global __buvid3, __buvid4
    if not __buvid3 or not __buvid4:
        spi = await _get_spi_buvid()
        __buvid3 = spi["b_3"]
        __buvid4 = spi["b_4"]
        await _active_buvid(__buvid3, __buvid4)
    return (__buvid3, __buvid4)


async def _active_buvid(buvid3: str, buvid4: str):
    MOD = 1 << 64

    def get_time_milli() -> int:
        return int(time.time() * 1000)

    def rotate_left(x: int, k: int) -> int:
        bin_str = bin(x)[2:].rjust(64, "0")
        return int(bin_str[k:] + bin_str[:k], base=2)

    def gen_uuid_infoc() -> str:
        t = get_time_milli() % 100000
        mp = [*list("123456789ABCDEF"), "10"]
        pck = [8, 4, 4, 4, 12]

        def gen_part(x):
            return "".join([random.choice(mp) for _ in range(x)])

        return "-".join([gen_part(i) for i in pck]) + str(t).ljust(5, "0") + "infoc"

    def gen_buvid_fp(key: str, seed: int):
        source = io.BytesIO(bytes(key, "ascii"))
        m = murmur3_x64_128(source, seed)
        return f"{hex(m & (MOD - 1))[2:]}{hex(m >> 64)[2:]}"

    def murmur3_x64_128(source: io.BufferedIOBase, seed: int) -> int:
        C1 = 0x87C3_7B91_1142_53D5
        C2 = 0x4CF5_AD43_2745_937F
        C3 = 0x52DC_E729
        C4 = 0x3849_5AB5
        R1, R2, R3, M = 27, 31, 33, 5
        h1, h2 = seed, seed
        processed = 0
        while 1:
            read = source.read(16)
            processed += len(read)
            if len(read) == 16:
                k1 = struct.unpack("<q", read[:8])[0]
                k2 = struct.unpack("<q", read[8:])[0]
                h1 ^= rotate_left(k1 * C1 % MOD, R2) * C2 % MOD
                h1 = ((rotate_left(h1, R1) + h2) * M + C3) % MOD
                h2 ^= rotate_left(k2 * C2 % MOD, R3) * C1 % MOD
                h2 = ((rotate_left(h2, R2) + h1) * M + C4) % MOD
            elif len(read) == 0:
                h1 ^= processed
                h2 ^= processed
                h1 = (h1 + h2) % MOD
                h2 = (h2 + h1) % MOD
                h1 = fmix64(h1)
                h2 = fmix64(h2)
                h1 = (h1 + h2) % MOD
                h2 = (h2 + h1) % MOD
                return (h2 << 64) | h1  # pyright: ignore[reportReturnType]
            else:
                k1 = 0
                k2 = 0
                if len(read) >= 15:
                    k2 ^= int(read[14]) << 48
                if len(read) >= 14:
                    k2 ^= int(read[13]) << 40
                if len(read) >= 13:
                    k2 ^= int(read[12]) << 32
                if len(read) >= 12:
                    k2 ^= int(read[11]) << 24
                if len(read) >= 11:
                    k2 ^= int(read[10]) << 16
                if len(read) >= 10:
                    k2 ^= int(read[9]) << 8
                if len(read) >= 9:
                    k2 ^= int(read[8])
                    k2 = rotate_left(k2 * C2 % MOD, R3) * C1 % MOD
                    h2 ^= k2
                if len(read) >= 8:
                    k1 ^= int(read[7]) << 56
                if len(read) >= 7:
                    k1 ^= int(read[6]) << 48
                if len(read) >= 6:
                    k1 ^= int(read[5]) << 40
                if len(read) >= 5:
                    k1 ^= int(read[4]) << 32
                if len(read) >= 4:
                    k1 ^= int(read[3]) << 24
                if len(read) >= 3:
                    k1 ^= int(read[2]) << 16
                if len(read) >= 2:
                    k1 ^= int(read[1]) << 8
                if len(read) >= 1:
                    k1 ^= int(read[0])
                k1 = rotate_left(k1 * C1 % MOD, R2) * C2 % MOD
                h1 ^= k1

    def fmix64(k: int) -> int:
        C1 = 0xFF51_AFD7_ED55_8CCD
        C2 = 0xC4CE_B9FE_1A85_EC53
        R = 33
        tmp = k
        tmp ^= tmp >> R
        tmp = tmp * C1 % MOD
        tmp ^= tmp >> R
        tmp = tmp * C2 % MOD
        tmp ^= tmp >> R
        return tmp

    def get_payload(uuid: str) -> str:
        content = {
            "3064": 1,
            "5062": get_time_milli(),
            "03bf": "https%3A%2F%2Fwww.bilibili.com%2F",
            "39c8": "333.788.fp.risk",
            "34f1": "",
            "d402": "",
            "654a": "",
            "6e7c": "839x959",
            "3c43": {
                "2673": 0,
                "5766": 24,
                "6527": 0,
                "7003": 1,
                "807e": 1,
                "b8ce": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",  # noqa: E501
                "641c": 0,
                "07a4": "en-US",
                "1c57": "not available",
                "0bd0": 8,
                "748e": [900, 1440],
                "d61f": [875, 1440],
                "fc9d": -480,
                "6aa9": "Asia/Shanghai",
                "75b8": 1,
                "3b21": 1,
                "8a1c": 0,
                "d52f": "not available",
                "adca": "MacIntel",
                "80c9": [
                    [
                        "PDF Viewer",
                        "Portable Document Format",
                        [["application/pdf", "pdf"], ["text/pdf", "pdf"]],
                    ],
                    [
                        "Chrome PDF Viewer",
                        "Portable Document Format",
                        [["application/pdf", "pdf"], ["text/pdf", "pdf"]],
                    ],
                    [
                        "Chromium PDF Viewer",
                        "Portable Document Format",
                        [["application/pdf", "pdf"], ["text/pdf", "pdf"]],
                    ],
                    [
                        "Microsoft Edge PDF Viewer",
                        "Portable Document Format",
                        [["application/pdf", "pdf"], ["text/pdf", "pdf"]],
                    ],
                    [
                        "WebKit built-in PDF",
                        "Portable Document Format",
                        [["application/pdf", "pdf"], ["text/pdf", "pdf"]],
                    ],
                ],
                "13ab": "0dAAAAAASUVORK5CYII=",
                "bfe9": "QgAAEIQAACEIAABCCQN4FXANGq7S8KTZayAAAAAElFTkSuQmCC",
                "a3c1": [
                    "extensions:ANGLE_instanced_arrays;EXT_blend_minmax;EXT_color_buffer_half_float;EXT_float_blend;EXT_frag_depth;EXT_shader_texture_lod;EXT_texture_compression_bptc;EXT_texture_compression_rgtc;EXT_texture_filter_anisotropic;EXT_sRGB;KHR_parallel_shader_compile;OES_element_index_uint;OES_fbo_render_mipmap;OES_standard_derivatives;OES_texture_float;OES_texture_float_linear;OES_texture_half_float;OES_texture_half_float_linear;OES_vertex_array_object;WEBGL_color_buffer_float;WEBGL_compressed_texture_astc;WEBGL_compressed_texture_etc;WEBGL_compressed_texture_etc1;WEBGL_compressed_texture_pvrtc;WEBKIT_WEBGL_compressed_texture_pvrtc;WEBGL_compressed_texture_s3tc;WEBGL_compressed_texture_s3tc_srgb;WEBGL_debug_renderer_info;WEBGL_debug_shaders;WEBGL_depth_texture;WEBGL_draw_buffers;WEBGL_lose_context;WEBGL_multi_draw",
                    "webgl aliased line width range:[1, 1]",
                    "webgl aliased point size range:[1, 511]",
                    "webgl alpha bits:8",
                    "webgl antialiasing:yes",
                    "webgl blue bits:8",
                    "webgl depth bits:24",
                    "webgl green bits:8",
                    "webgl max anisotropy:16",
                    "webgl max combined texture image units:32",
                    "webgl max cube map texture size:16384",
                    "webgl max fragment uniform vectors:1024",
                    "webgl max render buffer size:16384",
                    "webgl max texture image units:16",
                    "webgl max texture size:16384",
                    "webgl max varying vectors:30",
                    "webgl max vertex attribs:16",
                    "webgl max vertex texture image units:16",
                    "webgl max vertex uniform vectors:1024",
                    "webgl max viewport dims:[16384, 16384]",
                    "webgl red bits:8",
                    "webgl renderer:WebKit WebGL",
                    "webgl shading language version:WebGL GLSL ES 1.0 (1.0)",
                    "webgl stencil bits:0",
                    "webgl vendor:WebKit",
                    "webgl version:WebGL 1.0",
                    "webgl unmasked vendor:Apple Inc.",
                    "webgl unmasked renderer:Apple GPU",
                    "webgl vertex shader high float precision:23",
                    "webgl vertex shader high float precision rangeMin:127",
                    "webgl vertex shader high float precision rangeMax:127",
                    "webgl vertex shader medium float precision:23",
                    "webgl vertex shader medium float precision rangeMin:127",
                    "webgl vertex shader medium float precision rangeMax:127",
                    "webgl vertex shader low float precision:23",
                    "webgl vertex shader low float precision rangeMin:127",
                    "webgl vertex shader low float precision rangeMax:127",
                    "webgl fragment shader high float precision:23",
                    "webgl fragment shader high float precision rangeMin:127",
                    "webgl fragment shader high float precision rangeMax:127",
                    "webgl fragment shader medium float precision:23",
                    "webgl fragment shader medium float precision rangeMin:127",
                    "webgl fragment shader medium float precision rangeMax:127",
                    "webgl fragment shader low float precision:23",
                    "webgl fragment shader low float precision rangeMin:127",
                    "webgl fragment shader low float precision rangeMax:127",
                    "webgl vertex shader high int precision:0",
                    "webgl vertex shader high int precision rangeMin:31",
                    "webgl vertex shader high int precision rangeMax:30",
                    "webgl vertex shader medium int precision:0",
                    "webgl vertex shader medium int precision rangeMin:31",
                    "webgl vertex shader medium int precision rangeMax:30",
                    "webgl vertex shader low int precision:0",
                    "webgl vertex shader low int precision rangeMin:31",
                    "webgl vertex shader low int precision rangeMax:30",
                    "webgl fragment shader high int precision:0",
                    "webgl fragment shader high int precision rangeMin:31",
                    "webgl fragment shader high int precision rangeMax:30",
                    "webgl fragment shader medium int precision:0",
                    "webgl fragment shader medium int precision rangeMin:31",
                    "webgl fragment shader medium int precision rangeMax:30",
                    "webgl fragment shader low int precision:0",
                    "webgl fragment shader low int precision rangeMin:31",
                    "webgl fragment shader low int precision rangeMax:30",
                ],
                "6bc5": "Apple Inc.~Apple GPU",
                "ed31": 0,
                "72bd": 0,
                "097b": 0,
                "52cd": [0, 0, 0],
                "a658": [
                    "Andale Mono",
                    "Arial",
                    "Arial Black",
                    "Arial Hebrew",
                    "Arial Narrow",
                    "Arial Rounded MT Bold",
                    "Arial Unicode MS",
                    "Comic Sans MS",
                    "Courier",
                    "Courier New",
                    "Geneva",
                    "Georgia",
                    "Helvetica",
                    "Helvetica Neue",
                    "Impact",
                    "LUCIDA GRANDE",
                    "Microsoft Sans Serif",
                    "Monaco",
                    "Palatino",
                    "Tahoma",
                    "Times",
                    "Times New Roman",
                    "Trebuchet MS",
                    "Verdana",
                    "Wingdings",
                    "Wingdings 2",
                    "Wingdings 3",
                ],
                "d02f": "124.04345259929687",
            },
            "54ef": '{"in_new_ab":true,"ab_version":{"remove_back_version":"REMOVE","login_dialog_version":"V_PLAYER_PLAY_TOAST","open_recommend_blank":"SELF","storage_back_btn":"HIDE","call_pc_app":"FORBID","clean_version_old":"GO_NEW","optimize_fmp_version":"LOADED_METADATA","for_ai_home_version":"V_OTHER","bmg_fallback_version":"DEFAULT","ai_summary_version":"SHOW","weixin_popup_block":"ENABLE","rcmd_tab_version":"DISABLE","in_new_ab":true},"ab_split_num":{"remove_back_version":11,"login_dialog_version":43,"open_recommend_blank":90,"storage_back_btn":87,"call_pc_app":47,"clean_version_old":46,"optimize_fmp_version":28,"for_ai_home_version":38,"bmg_fallback_version":86,"ai_summary_version":466,"weixin_popup_block":45,"rcmd_tab_version":90,"in_new_ab":0},"pageVersion":"new_video","videoGoOldVersion":-1}',  # noqa: E501
            "8b94": "https%3A%2F%2Fwww.bilibili.com%2F",
            "df35": uuid,
            "07a4": "en-US",
            "5f45": None,
            "db46": 0,
        }
        return ujson.dumps(
            {"payload": ujson.dumps(content, separators=(",", ":"))},
            separators=(",", ":"),
        )

    uuid = gen_uuid_infoc()
    payload = get_payload(uuid)
    buvid_fp = gen_buvid_fp(payload, 31)
    headers = HEADERS.copy()
    headers["Content-Type"] = "application/json"
    resp = await CLIENT.post(
        url="https://api.bilibili.com/x/internal/gaia-gateway/ExClimbWuzhi",
        data=payload,
        headers=headers,
        cookies={
            "buvid3": buvid3,
            "buvid4": buvid4,
            "buvid_fp": buvid_fp,
            "_uuid": uuid,
        },
    )
    data = resp.json()
    if data["code"] != 0:
        raise BiliHelperException(data)
