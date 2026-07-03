import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Generator
from functools import wraps
from typing import Any, Generic, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


class DownloadTaskWrapper(Awaitable[T], Generic[T]):
    """惰性下载包装器
    - 只保存函数和参数，不创建 Task
    - 在被 await 时才真正执行协程
    """

    __slots__ = (
        "_args",
        "_func",
        "_has_result",
        "_kwargs",
        "_lock",
        "_result",
        "ext_headers",
        "url",
        "use_curl_cffi",
    )

    def __init__(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ):
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self.url: str = url
        self.ext_headers: dict[str, str] | None = ext_headers
        self.use_curl_cffi: bool = use_curl_cffi
        self._has_result = False
        self._lock: asyncio.Lock | None = None
        self._result: T | None = None

    def __await__(self) -> Generator[Any, Any, T]:
        return self._run().__await__()

    async def _run(self) -> T:
        if self._has_result:
            return self._result  # type: ignore[return-value]

        if self._lock is None:
            self._lock = asyncio.Lock()

        async with self._lock:
            if self._has_result:
                return self._result  # type: ignore[return-value]

            self._result = await self._func(*self._args, **self._kwargs)
            self._has_result = True
            return self._result

    def __repr__(self) -> str:
        return self.url


def auto_task(
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, DownloadTaskWrapper[T]]:
    """装饰器：返回惰性的下载包装器，并挂载 url / ext_headers 属性。

    约束（运行时检查）：
    - 被修饰函数签名必须包含：
        url: str
        ext_headers: dict[str, str] | None = None
        use_curl_cffi: bool = False
    - 调用方必须使用关键字传参 url=...
    - ext_headers 可以省略，不传时等价于 None（使用默认 headers）
    - use_curl_cffi 可以省略，不传时等价于 False（使用 httpx）
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> DownloadTaskWrapper[T]:
        # 1) 强制要求 url 通过关键字参数传入
        if "url" not in kwargs:
            raise RuntimeError(
                f"@auto_task 要求 {func.__qualname__} 必须有关键字参数 url: str，"
                f"请使用 {func.__name__}(url=..., ...) 的形式调用"
            )

        raw_url = kwargs["url"]
        # 2) ext_headers 允许缺省，默认为 None
        ext_headers = kwargs.get("ext_headers", None)
        use_curl_cffi = kwargs.get("use_curl_cffi", False)

        # 3) 运行时类型校验（防御性）
        if not isinstance(raw_url, str):
            raise TypeError(
                f"@auto_task 要求 {func.__qualname__} 的 url 参数为 str, "
                f"但实际是 {type(raw_url)!r}"
            )
        if ext_headers is not None and not isinstance(ext_headers, dict):
            raise TypeError(
                f"@auto_task 要求 {func.__qualname__} 的 ext_headers 类型为 dict[str, str] | None, "  # noqa: E501
                f"但实际是 {type(ext_headers)!r}"
            )
        if not isinstance(use_curl_cffi, bool):
            raise TypeError(
                f"@auto_task 要求 {func.__qualname__} 的 use_curl_cffi 类型为 bool, "
                f"但实际是 {type(use_curl_cffi)!r}"
            )

        url: str = raw_url

        # 4) 构造惰性下载包装器（保留原始 args/kwargs，不影响其它参数）
        return DownloadTaskWrapper(
            func=func,
            args=tuple(args),
            kwargs=dict(kwargs),
            url=url,
            ext_headers=ext_headers,
            use_curl_cffi=use_curl_cffi,
        )

    return wrapper
