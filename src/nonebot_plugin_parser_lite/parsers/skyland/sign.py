import hashlib
import hmac
import json
import time
from urllib.parse import urlparse

from httpx import URL, AsyncClient


async def get_token(client: AsyncClient) -> bytes:
    """获取 token

    :param client: 复用的 HTTP 客户端
    """
    resp = await client.get("https://zonai.skland.com/web/v1/auth/refresh")
    resp.raise_for_status()
    data = resp.json()
    if token := (data.get("data") or {}).get("token"):
        return token.encode("utf-8")
    else:
        raise ValueError(f"获取森空岛 token 失败: {data}")


def sign_headers(token: bytes, url: str | URL) -> dict[str, str]:
    """根据 URL 生成签名请求头

    :param token:  token
    :param url: 完整请求地址
    """
    parsed = urlparse(str(url))
    t = str(int(time.time()))
    h = {
        "platform": "3",
        "timestamp": t,
        "dId": "",
        "vName": "1.0.0",
    }
    hs = json.dumps(h, separators=(",", ":"))
    raw = f"{parsed.path}{parsed.query}{t}{hs}"
    digest = hmac.new(token, raw.encode("utf-8"), hashlib.sha256).hexdigest()
    h["sign"] = hashlib.md5(digest.encode("utf-8")).hexdigest()
    return h
