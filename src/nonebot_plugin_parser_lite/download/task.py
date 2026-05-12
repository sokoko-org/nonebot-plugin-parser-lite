from typing import Any, TypeVar, ParamSpec, Generic, Awaitable, Generator
from functools import wraps
from collections.abc import Callable, Coroutine

P = ParamSpec("P")
T = TypeVar("T")


class DownloadTaskWrapper(Generic[T], Awaitable[T]):
    """惰性下载包装器
    - 只保存函数和参数，不创建 Task
    - 在被 await 时才真正执行协程
    """

    __slots__ = ("url", "ext_headers", "_func", "_args", "_kwargs")

    def __init__(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        url: str,
        ext_headers: dict[str, str] | None = None,
    ):
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self.url: str = url
        self.ext_headers: dict[str, str] | None = ext_headers

    def __await__(self) -> Generator[Any, Any, T]:
        # 每次 await 都直接执行原始协程
        coro = self._func(*self._args, **self._kwargs)
        return coro.__await__()


def auto_task(
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, DownloadTaskWrapper[T]]:
    """装饰器：返回惰性的下载包装器，并挂载 url / ext_headers 属性。

    约束（运行时检查）：
    - 被修饰函数签名必须包含：
        url: str
        ext_headers: dict[str, str] | None = None
    - 调用方必须使用关键字传参 url=...
    - ext_headers 可以省略，不传时等价于 None（使用默认 headers）
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

        # 3) 运行时类型校验（防御性）
        if not isinstance(raw_url, str):
            raise TypeError(
                f"@auto_task 要求 {func.__qualname__} 的 url 参数为 str, "
                f"但实际是 {type(raw_url)!r}"
            )
        if ext_headers is not None and not isinstance(ext_headers, dict):
            raise TypeError(
                f"@auto_task 要求 {func.__qualname__} 的 ext_headers 类型为 dict[str, str] | None, "
                f"但实际是 {type(ext_headers)!r}"
            )

        url: str = raw_url

        # 4) 构造惰性下载包装器（保留原始 args/kwargs，不影响其它参数）
        return DownloadTaskWrapper(
            func=func,
            args=tuple(args),
            kwargs=dict(kwargs),
            url=url,
            ext_headers=ext_headers,
        )

    return wrapper
