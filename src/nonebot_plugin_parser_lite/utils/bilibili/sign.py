from collections.abc import Mapping
from functools import reduce
from hashlib import md5
import time
from typing import Any
from urllib.parse import quote, urlencode

from .client import (
    API_CHANNEL,
    API_LOCALE,
    API_STATISTICS,
    APPKEY,
    APPSEC,
    BUILD,
    HTTP_CLIENT,
    MOBI_APP,
    PLATFORM,
)

AppParameter = str | int | float | bool

# fmt: off
mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]
# fmt: on

IMG_KEY, SUB_KEY = "", ""
WBI_KEY_EXPIRE = 0


def getMixinKey(orig: str):
    "对 imgKey 和 subKey 进行字符顺序打乱编码"
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, "")[:32]


def encWbi(params: dict[str, Any], img_key: str, sub_key: str):
    "为请求参数进行 wbi 签名"
    mixin_key = getMixinKey(img_key + sub_key)
    params.pop("w_rid", None)
    params["wts"] = int(time.time())
    params = dict(sorted(params.items()))
    params = {
        k: "".join(filter(lambda char: char not in "!'()*", str(v)))
        for k, v in params.items()
    }
    query = urlencode(params, quote_via=quote)
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = wbi_sign
    return params


async def getWbiKeys() -> tuple[str, str]:
    global IMG_KEY, SUB_KEY, WBI_KEY_EXPIRE
    now = int(time.time())
    if IMG_KEY and SUB_KEY and WBI_KEY_EXPIRE > now:
        return IMG_KEY, SUB_KEY
    resp = await HTTP_CLIENT.get(url="https://api.bilibili.com/x/web-interface/nav")
    resp.raise_for_status()
    json_content = resp.json()
    img_url: str = json_content["data"]["wbi_img"]["img_url"]
    sub_url: str = json_content["data"]["wbi_img"]["sub_url"]
    IMG_KEY = img_url.rsplit("/", 1)[1].split(".")[0]
    SUB_KEY = sub_url.rsplit("/", 1)[1].split(".")[0]
    WBI_KEY_EXPIRE = now + 600
    return IMG_KEY, SUB_KEY


def enc_sign(
    params: Mapping[str, AppParameter],
) -> dict[str, AppParameter]:
    params = dict(sorted({**params, "appkey": APPKEY}.items()))
    params["sign"] = md5((urlencode(params) + APPSEC).encode("utf-8")).hexdigest()
    return params


def enc_app_sign(
    params: Mapping[str, AppParameter],
) -> dict[str, AppParameter]:
    """补全客户端公共参数并生成签名"""
    return enc_sign(
        {
            "build": BUILD,
            "c_locale": API_LOCALE,
            "channel": API_CHANNEL,
            "mobi_app": MOBI_APP,
            "platform": PLATFORM,
            "s_locale": API_LOCALE,
            "statistics": API_STATISTICS,
            "ts": int(time.time()),
            **params,
        }
    )
