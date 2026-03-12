import re
import asyncio
import hashlib
from typing import TypeVar
from pathlib import Path
from collections import OrderedDict
from urllib.parse import urlparse

from nonebot import logger


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
            self.popitem(last=False)  # 移除最早添加的项


def keep_zh_en_num(text: str) -> str:
    """
    保留字符串中的中英文和数字
    """
    return re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\-_]", "", text.replace(" ", "_"))


async def safe_unlink(path: Path):
    """
    安全删除文件
    """
    try:
        await asyncio.to_thread(path.unlink, missing_ok=True)
    except Exception:
        logger.warning(f"删除 {path} 失败")


def fmt_size(file_path: Path) -> str:
    """格式化文件大小

    Args:
        video_path (Path): 视频路径
    """
    return f"大小: {file_path.stat().st_size / 1024 / 1024:.2f} MB"


def generate_file_name(url: str, default_suffix: str = "") -> str:
    """根据 url 生成文件名（忽略 query/fragment，尽量复用同一资源的缓存）

    :param url: 原始资源 URL（可能带签名、trace 等动态参数）
    :param default_suffix: 默认后缀名（当 path 中不含后缀时使用）

    :return: 适合作为文件名的短 md5（含后缀）
    """
    parsed = urlparse(url)
    path = Path(parsed.path)
    suffix = path.suffix or default_suffix

    # 只用  netloc + path 作为稳定 key，忽略 query / fragment
    stable_url = f"{parsed.netloc}{parsed.path}"
    url_hash = hashlib.md5(stable_url.encode("utf-8")).hexdigest()[:16]
    return f"{url_hash}.{suffix}"
