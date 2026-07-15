from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from curl_cffi import AsyncSession
from curl_cffi import Response as CurlResponse
from httpx import AsyncClient, Timeout, codes
from httpx import Response as HttpxResponse

from ..exception import ParseException


class HTTPStatusError(ParseException):
    """HTTP 状态码异常"""

    def __init__(self, message: str, response: UniResponse):
        super().__init__(message)
        self.response = response


class HeadResponse:
    __solts__ = ("status_code", "headers", "url")

    def __init__(self, url: str, status_code: int, headers: dict[str, str | None]):
        self.status_code = status_code
        self.headers = headers
        self.url = url


class UniResponse:
    __slots__ = ("_raw",)
    raw: CurlResponse | HttpxResponse

    def __init__(self, raw: CurlResponse | HttpxResponse):
        self._raw = raw

    @property
    def status_code(self) -> int:
        return self._raw.status_code

    @property
    def headers(self) -> dict[str, str | None]:
        """被全部小写的 HTTP 头"""
        return {k.lower(): v for k, v in self._raw.headers.items()}

    @property
    def url(self) -> str:
        return str(self._raw.url)

    @property
    def text(self) -> str:
        return self._raw.text

    @property
    def content(self) -> bytes:
        return self._raw.content

    def json(self) -> Any:
        return self._raw.json()

    def raise_for_status(self):
        if self.status_code >= 400 or self.status_code < 200:
            status_class = self.status_code // 100
            error_types = {
                1: "Informational response",
                3: "Redirect response",
                4: "Client error",
                5: "Server error",
            }
            error_type = error_types.get(status_class, "Invalid status code")
            reason_phrase = codes.get_reason_phrase(self.status_code)
            message = (
                f"{error_type} '{self.status_code} {reason_phrase}' "
                f"for url '{self.url}'\n"
                f"For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{self.status_code}"
            )
            raise HTTPStatusError(message, response=self)
        return self

    async def aiter_bytes(self, chunk_size: int | None = None) -> AsyncIterator[bytes]:
        if isinstance(self._raw, HttpxResponse):
            async for chunk in self._raw.aiter_bytes(chunk_size):
                yield chunk
            return

        async for chunk in self._raw.aiter_content():
            yield chunk


class UniHttpClient:
    def __init__(self, timeout: Timeout):
        self._timeout = timeout
        self._httpx = AsyncClient(timeout=timeout, verify=False)
        self._curl = AsyncSession(impersonate="chrome146")

    async def aclose(self) -> None:
        await self._httpx.aclose()
        await self._curl.close()

    def _curl_timeout(self, timeout: float | None = None) -> float:
        if timeout is not None:
            return float(timeout)
        return float(max(self._timeout.connect or 15, self._timeout.read or 240))

    async def head(
        self,
        url: str,
        *,
        headers: dict[str, str],
        use_curl_cffi: bool = False,
    ) -> UniResponse:
        if use_curl_cffi:
            resp = await self._curl.head(
                url=url,
                headers=headers,
                allow_redirects=True,
                timeout=self._curl_timeout(),
                verify=False,
            )
        else:
            resp = await self._httpx.head(
                url=url,
                headers=headers,
                follow_redirects=True,
            )
        return UniResponse(resp)

    async def get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str],
        use_curl_cffi: bool = False,
    ) -> UniResponse:
        if use_curl_cffi:
            resp = await self._curl.get(
                url,
                params=params,
                headers=headers,
                allow_redirects=True,
                timeout=self._curl_timeout(),
                verify=False,
            )
        else:
            resp = await self._httpx.get(
                url,
                params=params,
                headers=headers,
                follow_redirects=True,
            )
        return UniResponse(resp)

    async def post(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str],
        content: str | bytes | None = None,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        use_curl_cffi: bool = False,
    ) -> UniResponse:
        if use_curl_cffi:
            resp = await self._curl.post(
                url,
                params=params,
                headers=headers,
                data=content or data,
                json=json,
                allow_redirects=True,
                timeout=self._curl_timeout(),
                verify=False,
            )
        else:
            resp = await self._httpx.post(
                url,
                params=params,
                headers=headers,
                content=content,
                data=data,
                json=json,
                follow_redirects=True,
            )
        return UniResponse(resp)

    @asynccontextmanager
    async def stream(
        self,
        method: Literal[
            "GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH", "QUERY"
        ],
        url: str,
        *,
        headers: dict[str, str],
        timeout: float | None = None,
        use_curl_cffi: bool = False,
    ) -> AsyncGenerator[UniResponse]:
        if use_curl_cffi:
            async with self._curl.stream(
                method,
                url,
                headers=headers,
                timeout=self._curl_timeout(timeout),
                allow_redirects=True,
                verify=False,
            ) as resp:
                yield UniResponse(resp)
        else:
            kwargs: dict[str, Any] = {
                "headers": headers,
                "follow_redirects": True,
            }
            if timeout is not None:
                kwargs["timeout"] = timeout
            async with self._httpx.stream(method, url, **kwargs) as resp:
                yield UniResponse(resp)
