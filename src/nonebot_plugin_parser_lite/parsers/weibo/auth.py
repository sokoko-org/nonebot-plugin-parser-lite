import asyncio
from collections.abc import Mapping
import re
from typing import Any

from httpx import AsyncClient
from nonebot import logger
import ujson

from ...constants import COMMON_TIMEOUT

callback_pattern = re.compile(r"visitor_gray_callback\((.*)\)")


class AuthHelper:
    xsrf_token: str = ""
    xsrf_obtained_at: float | None = None
    _refresh_lock: asyncio.Lock | None = None

    XSRF_TTL: float = 3 * 60 * 60  # XSRF 有效期，暂定 3 小时
    SESSION: AsyncClient = AsyncClient(timeout=COMMON_TIMEOUT)

    @classmethod
    async def aclose(cls) -> None:
        """关闭全局 HTTP 会话以释放连接/文件描述符"""
        await cls.SESSION.aclose()

    @classmethod
    def _need_refresh(cls) -> bool:
        """判断是否需要刷新 XSRF"""
        if not cls.xsrf_token or cls.xsrf_obtained_at is None:
            return True
        return (asyncio.get_event_loop().time() - cls.xsrf_obtained_at) > cls.XSRF_TTL

    @classmethod
    async def init_visitor(cls):
        """Initialize visitor auth"""
        try:
            resp = await cls.SESSION.post(
                "https://visitor.passport.weibo.cn/visitor/genvisitor2",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://visitor.passport.weibo.cn",
                    "Referer": "https://visitor.passport.weibo.cn/visitor/visitor?entry=sinawap&a=enter&url=https%3A%2F%2Fm.weibo.cn%2F",
                },
                data={"cb": "visitor_gray_callback", "tid": "", "new_tid": "null"},
            )
            if match := callback_pattern.search(resp.text):
                json_data = ujson.loads(match.group(1))
                if json_data.get("retcode") == 20000000:
                    sub = json_data["data"]["sub"]
                    subp = json_data["data"]["subp"]
                    cls.SESSION.cookies.set("SUB", sub, domain=".weibo.com")
                    cls.SESSION.cookies.set("SUBP", subp, domain=".weibo.com")
                    await cls.SESSION.get(
                        "https://www.weibo.com",
                        headers={"Referer": "https://visitor.passport.weibo.cn/"},
                    )
                    cls.xsrf_token = cls.SESSION.cookies["XSRF-TOKEN"]
                    cls.xsrf_obtained_at = asyncio.get_event_loop().time()
        except Exception as e:
            logger.error(f"Weibo visitor auth initialization failed: {type(e)}:{e!r}")

    @classmethod
    async def get_headers(cls) -> dict[str, str]:
        """Get standard headers (with cached XSRF token)."""
        if cls._need_refresh():
            if cls._refresh_lock is None:
                cls._refresh_lock = asyncio.Lock()
            async with cls._refresh_lock:
                if cls._need_refresh():
                    await cls.init_visitor()
        return {
            "X-Xsrf-Token": cls.xsrf_token,
            "Referer": "https://www.weibo.com/",
        }

    @classmethod
    async def get(
        cls, url: str, params: dict | None = None, follow_redirects: bool = False
    ):
        return await cls.SESSION.get(
            url=url,
            params=params,
            headers=await cls.get_headers(),
            follow_redirects=follow_redirects,
        )

    @classmethod
    async def post(
        cls,
        url: str,
        params: dict | None = None,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        follow_redirects: bool = False,
    ):
        return await cls.SESSION.post(
            url=url,
            params=params,
            json=json,
            data=data,
            headers=await cls.get_headers(),
            follow_redirects=follow_redirects,
        )


if __name__ == "__main__":

    async def main():
        a = await AuthHelper.get(
            "https://m.weibo.cn/comments/hotflow", params={"mid": "5181502771168068"}
        )
        try:
            print(a.json())  # noqa: T201
        except Exception:
            print(a.text)  # noqa: T201

    asyncio.run(main())
