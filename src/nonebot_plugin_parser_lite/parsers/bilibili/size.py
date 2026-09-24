from collections.abc import Awaitable, Callable


async def probe_source_size(
    urls: tuple[str, ...] | None,
    probe: Callable[[str], Awaitable[int | None]],
) -> int | None:
    if not urls:
        return
    for url in urls:
        try:
            if size := await probe(url):
                return size
        except Exception:
            continue
