from dataclasses import dataclass
from typing import Literal

from anyio import Path
from nonebot import logger

from ..config import pconfig
from ..exception import SizeLimitException, ZeroSizeException
from .client import DownloadResponse

STREAM_CHUNK_SIZE = 1024 * 1024
STREAM_DOWNLOAD_RETRIES = 3
M3U8_SEGMENT_RETRIES = 3
M3U8_SEGMENT_TIMEOUT = 15
MIN_VALID_VIDEO_BYTES = 1024


@dataclass(slots=True)
class StreamDownloadTarget:
    url: str
    file_path: Path
    part_path: Path
    desc: str
    headers: dict[str, str]
    use_curl_cffi: bool


@dataclass(slots=True)
class StreamRequestPlan:
    headers: dict[str, str]
    partial_size: int


@dataclass(slots=True)
class StreamWritePlan:
    total_size: int | None
    initial_bytes: int
    mode: Literal["wb", "ab"]


def make_part_path(file_path: Path) -> Path:
    return file_path.parent / f"{file_path.name}.part"


async def file_size(file_path: Path) -> int:
    try:
        return (await file_path.stat()).st_size
    except FileNotFoundError:
        return 0


def parse_int_header(header_val: str | None) -> int | None:
    if not header_val:
        return None
    try:
        return int(header_val)
    except ValueError:
        return None


def parse_content_range_total(header_val: str | None) -> int | None:
    if not header_val:
        return None
    _, _, range_spec = header_val.partition(" ")
    _, _, total = range_spec.partition("/")
    return None if not total or total == "*" else parse_int_header(total)


def check_media_size(url: str, size_bytes: int) -> None:
    if size_bytes == 0:
        logger.warning(f"媒体 url: {url}, 大小为 0, 取消下载")
        raise ZeroSizeException

    file_size_mb = size_bytes / 1024 / 1024
    if file_size_mb > pconfig.max_size:
        logger.warning(
            f"媒体 url: {url} 大小 {file_size_mb:.2f} MB 超过 "
            f"{pconfig.max_size} MB, 取消下载"
        )
        raise SizeLimitException(file_size_mb)


def resolve_total_size(
    response: DownloadResponse,
    content_length: int | None,
    partial_size: int,
) -> int | None:
    if response.status_code != 206:
        return content_length

    range_total = parse_content_range_total(response.headers.get("Content-Range"))
    if range_total is not None:
        return range_total
    return partial_size + content_length if content_length is not None else None
