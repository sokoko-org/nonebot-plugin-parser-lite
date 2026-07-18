from curl_cffi import AsyncSession, Response

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 "
    "Safari/537.36 Edg/131.0.0.0",
    "Referer": "https://www.bilibili.com",
}

CLIENT = AsyncSession(
    impersonate="chrome131",
    timeout=30.0,
    verify=True,
    trust_env=True,
    headers=HEADERS,
)

__all__ = ["CLIENT", "Response"]
