from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
from render_test_support import ROOT

API_DIR = ROOT / "api_txt"

Route = tuple[str, str]


def _load(platform: str, name: str) -> Any:
    return json.loads((API_DIR / platform / name).read_text(encoding="utf-8"))


def mock_transport(
    platform: str,
    routes: list[Route],
    *,
    redirects: dict[str, str] | None = None,
) -> httpx.MockTransport:
    """按 URL 子串把请求路由到 api_txt 样本。

    routes: (url 子串, 样本文件名) 列表，首个匹配生效。
    redirects: (url 子串 -> Location) 用于模拟 302 外链跳转。
    """

    redirects = redirects or {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for fragment, location in redirects.items():
            if fragment in url:
                return httpx.Response(302, headers={"location": location})
        for fragment, name in routes:
            if fragment in url:
                return httpx.Response(
                    200, content=(API_DIR / platform / name).read_bytes()
                )
        raise AssertionError(f"未预期的请求 {request.method} {url}")

    return httpx.MockTransport(handler)


def attach(parser: Any, transport: httpx.MockTransport) -> None:
    """把 mock transport 挂到 parser 自己的 httpx 客户端上，保留原 base_url。"""
    parser.httpx = httpx.AsyncClient(
        transport=transport,
        base_url=parser.httpx.base_url,
        follow_redirects=True,
    )


def stub_head_size(monkeypatch, size: int | None = 2048) -> None:
    from nonebot_plugin_parser_lite.download import DOWNLOADER

    monkeypatch.setattr(DOWNLOADER, "head_size", AsyncMock(return_value=size))
