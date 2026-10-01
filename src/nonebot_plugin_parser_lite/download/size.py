from ..exception import SizeLimitException


class DownloadSizeBudget:
    """按各源流当前大小共享预算，重试和断点续传不会重复计数。"""

    def __init__(self, max_size_mb: int):
        self.limit_bytes = max_size_mb * 1024 * 1024
        self._source_sizes: dict[str, int] = {}

    def check(self, size: int) -> None:
        if size > self.limit_bytes:
            raise SizeLimitException(size / 1024 / 1024)

    def update(self, source: str, size: int) -> None:
        self._source_sizes[source] = size
        self.check(sum(self._source_sizes.values()))
