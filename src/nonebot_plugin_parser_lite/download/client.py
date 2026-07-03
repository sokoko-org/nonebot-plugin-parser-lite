from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from curl_cffi import AsyncSession
from httpx import AsyncClient, Headers, Request, Response, Timeout


class DownloadResponse:
    """Normalize the small response surface used by StreamDownloader."""

    __slots__ = ("_raw",)

    def __init__(self, raw: Any):
        self._raw = raw

    @property
    def status_code(self) -> int:
        return self._raw.status_code

    @property
    def headers(self) -> Headers:
        return Headers(self._raw.headers)

    @property
    def url(self) -> str:
        return str(self._raw.url)

    @property
    def text(self) -> str:
        return self._raw.text

    @property
    def content(self) -> bytes:
        return self._raw.content

    def raise_for_status(self) -> None:
        self._raw.raise_for_status()

    async def aiter_bytes(self, chunk_size: int | None = None) -> AsyncIterator[bytes]:
        if hasattr(self._raw, "aiter_bytes"):
            async for chunk in self._raw.aiter_bytes(chunk_size):
                yield chunk
            return

        async for chunk in self._raw.aiter_content():
            yield chunk

    def to_httpx_response(self) -> Response:
        request = getattr(self._raw, "request", None)
        if not isinstance(request, Request):
            request = Request("GET", self.url)
        return Response(
            status_code=self.status_code,
            headers=self.headers,
            request=request,
        )


class DownloadHttpClient:
    """Adapter over httpx and curl_cffi with one request interface."""

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
    ) -> DownloadResponse:
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
        return DownloadResponse(resp)

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        use_curl_cffi: bool = False,
    ) -> DownloadResponse:
        if use_curl_cffi:
            resp = await self._curl.get(
                url,
                headers=headers,
                allow_redirects=True,
                timeout=self._curl_timeout(),
                verify=False,
            )
        else:
            resp = await self._httpx.get(
                url,
                headers=headers,
                follow_redirects=True,
            )
        return DownloadResponse(resp)

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
    ) -> AsyncGenerator[DownloadResponse]:
        if use_curl_cffi:
            async with self._curl.stream(
                method,
                url,
                headers=headers,
                timeout=self._curl_timeout(timeout),
                allow_redirects=True,
                verify=False,
            ) as resp:
                yield DownloadResponse(resp)
        else:
            kwargs: dict[str, Any] = {
                "headers": headers,
                "follow_redirects": True,
            }
            if timeout is not None:
                kwargs["timeout"] = timeout
            async with self._httpx.stream(method, url, **kwargs) as resp:
                yield DownloadResponse(resp)
