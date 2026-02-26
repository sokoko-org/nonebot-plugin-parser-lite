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

    __slots__ = ("url", "_func", "_args", "_kwargs")

    def __init__(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        url: str,
    ):
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self.url: str = url

    def __await__(self) -> Generator[Any, Any, T]:
        # 每次 await 都直接执行原始协程
        coro = self._func(*self._args, **self._kwargs)
        return coro.__await__()


def auto_task(
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, DownloadTaskWrapper[T]]:
    """装饰器：返回惰性的下载包装器，并挂载 url 属性

    约定：
    - 被修饰函数的签名类似：
        async def fn(self, url: str, *..., **...)
      即 args[0] 是 self/cls，args[1] 或 kwargs["url"] 为 url: str
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> DownloadTaskWrapper[T]:
        # 优先从关键字参数中获取 url，其次才从位置参数中取
        if "url" in kwargs:
            raw_url = kwargs["url"]
        else:
            if len(args) < 2:
                raise RuntimeError(
                    f"@auto_task 要求 {func.__qualname__} 的第二个参数为 url: str"
                )
            raw_url = args[1]

        if not isinstance(raw_url, str):
            raise TypeError(
                f"@auto_task 要求 {func.__qualname__} 的 url 参数为 str, "
                f"但实际是 {type(raw_url)!r}"
            )
        url: str = raw_url

        # 这里把 args/kwargs 转为简单类型传给 DownloadTaskWrapper
        return DownloadTaskWrapper(
            func,
            tuple(args),  # 保证 *args 全部原样保留
            dict(kwargs),  # 保证 **kwargs 全部原样保留
            url,
        )

    return wrapper
