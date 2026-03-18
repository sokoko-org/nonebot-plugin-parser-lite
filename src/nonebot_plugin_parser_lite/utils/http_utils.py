from curl_cffi import AsyncSession


def get_async_client(**kwargs) -> AsyncSession:
    """
    Parameters:
        loop: loop to use, if not provided, the running loop will be used.
        async_curl: [AsyncCurl](/api/curl_cffi#curl_cffi.AsyncCurl) object to use.
        max_clients: maxmium curl handle to use in the session,
            this will affect the concurrency ratio.
        headers: headers to use in the session.
        cookies: cookies to add in the session.
        auth: HTTP basic auth, a tuple of (username, password), only basic auth is
            supported.
        proxies: dict of proxies to use, prefer to use ``proxy`` if they are the
            same. format: ``{"http": proxy_url, "https": proxy_url}``.
        proxy: proxy to use, format: "http://proxy_url".
            Cannot be used with the above parameter.
        proxy_auth: HTTP basic auth for proxy, a tuple of (username, password).
        base_url: absolute url to use for relative urls.
        params: query string for the session.
        verify: whether to verify https certs.
        timeout: how many seconds to wait before giving up.
        trust_env: use http_proxy/https_proxy and other environments, default True.
        allow_redirects: whether to allow redirection.
        max_redirects: max redirect counts, default 30, use -1 for unlimited.
        impersonate: which browser version to impersonate in the session.
        ja3: ja3 string to impersonate in the session.
        akamai: akamai string to impersonate in the session.
        extra_fp: extra fingerprints options, in complement to ja3 and akamai str.
        default_encoding: encoding for decoding response content if charset is not
            found in headers. Defaults to "utf-8". Can be set to a callable for
            automatic detection.
        cert: a tuple of (cert, key) filenames for client cert.
        response_class: A customized subtype of ``Response`` to use.
        raise_for_status: automatically raise an HTTPError for 4xx and 5xx
            status codes.
    """
    timeout = kwargs.pop("timeout", 15)

    return AsyncSession(timeout=timeout, **kwargs, impersonate="chrome131")
