from collections import OrderedDict
import hashlib
from typing import TypeVar
from urllib.parse import urlparse

from anyio import Path

from .log import logger

K = TypeVar("K")
V = TypeVar("V")

class LimitedSizeDict(OrderedDict[K, V]):
    """
    定长字典
    """

    def __init__(self, *args, max_size=20, **kwargs):
        self.max_size = max_size
        super().__init__(*args, **kwargs)

    def __setitem__(self, key: K, value: V):
        super().__setitem__(key, value)
        if len(self) > self.max_size:
            self.popitem(last=False)


async def safe_unlink(path: Path):
    """
    安全删除文件
    """
    try:
        await path.unlink(missing_ok=True)
    except Exception:
        logger.warning(f"删除 {path} 失败")


async def fmt_size(file_path: Path) -> str:
    """格式化文件大小

    :param video_path: 视频路径
    """
    stat = await file_path.stat()
    return f"大小: {stat.st_size / 1024 / 1024:.2f} MB"


def compose_cache_key(
    media_type: str,
    resource_key: str | None,
    variant: str | None = None,
) -> str | None:
    """为显式资源标识补充媒体类型和用途，未传标识时交给 URL 兜底"""
    if resource_key is None:
        return None
    if not media_type.strip() or not resource_key.strip():
        raise ValueError("缓存标识组成部分不能为空")
    if variant is not None and not variant.strip():
        raise ValueError("缓存用途不能为空")
    return ":".join(part for part in (media_type, resource_key, variant) if part)


def generate_file_name(url: str, cache_key: str | None = None) -> str:
    """根据稳定标识或完整 URL 生成不带后缀的文件名"""
    parsed = urlparse(url)
    if cache_key is not None and not cache_key.strip():
        raise ValueError("cache_key 不能为空字符串")
    identity = cache_key or parsed._replace(fragment="").geturl()
    return hashlib.md5(identity.encode("utf-8")).hexdigest()[:16]
