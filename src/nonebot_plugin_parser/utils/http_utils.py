import httpx
from httpx import AsyncHTTPTransport, Proxy

from ..constants import COMMON_TIMEOUT


def get_async_client(
    proxies: dict[str, str] | str | None = None,
    proxy: str | None = None,
    verify: bool = False,
    **kwargs,
) -> httpx.AsyncClient:
    # 允许调用方传入自定义 transport；否则按 verify 创建默认 transport
    base_transport: AsyncHTTPTransport = kwargs.pop(
        "transport", AsyncHTTPTransport(verify=verify)
    )
    timeout = kwargs.pop("timeout", COMMON_TIMEOUT)

    mounts: dict[str, AsyncHTTPTransport] = {}

    # 优先使用 proxies，其次使用 proxy
    if proxies:
        # 兼容字符串形式的 proxies
        if isinstance(proxies, str):
            proxies = {"http://": proxies, "https://": proxies}

        http_proxy = proxies.get("http://")
        https_proxy = proxies.get("https://")

        mounts["http://"] = AsyncHTTPTransport(
            proxy=Proxy(http_proxy) if http_proxy else None,
            verify=verify,
        )
        mounts["https://"] = AsyncHTTPTransport(
            proxy=Proxy(https_proxy) if https_proxy else None,
            verify=verify,
        )

    elif proxy:
        proxy_obj = Proxy(proxy)
        mounts["http://"] = AsyncHTTPTransport(proxy=proxy_obj, verify=verify)
        mounts["https://"] = AsyncHTTPTransport(proxy=proxy_obj, verify=verify)

    return httpx.AsyncClient(
        transport=base_transport,
        mounts=mounts or None,
        timeout=timeout,
        trust_env=False,
        **kwargs,
    )
