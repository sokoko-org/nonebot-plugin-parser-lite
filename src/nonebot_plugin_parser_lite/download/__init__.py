import asyncio
from collections.abc import Callable, Collection, Generator, Sequence
import contextlib
from functools import partial
import re
from urllib.parse import urljoin

import aiofiles
from anyio import Path
import puremagic
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from ..config import pconfig
from ..constants import COMMON_HEADER, DOWNLOAD_TIMEOUT
from ..exception import DownloadException, SizeLimitException, ZeroSizeException
from ..utils.cache import CacheManager
from ..utils.common import (
    compose_cache_key,
    generate_file_name,
    safe_unlink,
)
from ..utils.ffmpeg import FFmpeg
from ..utils.log import logger
from .client import RetryableDownloadError, UniHttpClient, UniResponse
from .task import auto_task

_RE_RANGE_PATTERN = re.compile(r"bytes\s+(\d+)-\d+/(\d+|\*)")


def _with_identity_encoding(headers: dict[str, str]) -> dict[str, str]:
    """让文件长度、Content-Length 与 Range 使用同一字节坐标系"""
    result = {
        key: value for key, value in headers.items() if key.lower() != "accept-encoding"
    }
    result["Accept-Encoding"] = "identity"
    return result


def _parse_content_encodings(value: str | None) -> tuple[str, ...]:
    """解析 Content-Encoding 编码链，忽略空标记并统一大小写"""
    return tuple(
        encoding
        for token in (value or "").split(",")
        if (encoding := token.strip().lower())
    )


async def _detect_file_suffix(file_path: Path, default_suffix: str) -> str:
    try:
        return await asyncio.to_thread(
            puremagic.from_file,
            str(file_path),
        )
    except (OSError, puremagic.PureError):
        return default_suffix


class StreamDownloader:
    """Downloader class for downloading files with stream"""

    MAX_RETRIES = pconfig.max_retries
    _SIZE_MISMATCH_TOLERANCE_BYTES = 1024

    def __init__(self):
        self.headers: dict[str, str] = COMMON_HEADER.copy()
        self.cache_dir: Path = pconfig.cache_dir
        self.client = UniHttpClient(timeout=DOWNLOAD_TIMEOUT)
        self._active_downloads: dict[str, asyncio.Task[Path]] = {}

    async def aclose(self) -> None:
        await self.client.aclose()

    async def head(
        self,
        url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> UniResponse:
        """
        发送 HEAD 请求并返回响应对象

        :param url: 目标资源地址
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 发起请求
        :return: UniResponse 对象
        :raise HTTPStatusError: HEAD 与 GET 均非 2xx 时抛出
        """
        headers = _with_identity_encoding({**self.headers, **(ext_headers or {})})
        resp = await self.client.head(
            url=url,
            headers=headers,
            use_curl_cffi=use_curl_cffi,
        )
        if 200 <= resp.status_code < 300:
            return resp
        logger.debug(
            f"[StreamDownloader] HEAD {url} returned {resp.status_code}, fallback to streamed GET"  # noqa: E501
        )
        async with self.client.stream(
            "GET",
            url,
            headers=headers,
            use_curl_cffi=use_curl_cffi,
        ) as stream_resp:
            return stream_resp

    async def head_size(
        self,
        url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> int | None:
        """
        对给定 url 发送 HEAD 请求，返回 Content-Length
        """
        response = await self.head(
            url, ext_headers=ext_headers, use_curl_cffi=use_curl_cffi
        )
        if not response.is_success:
            return None
        raw_len = response.headers.get("content-length")
        if not raw_len:
            return None
        try:
            return int(raw_len)
        except ValueError:
            return None

    @auto_task
    async def streamd(
        self,
        *,
        url: str,
        fallback_urls: Sequence[str] | None = None,
        retry_http_statuses: Collection[int] = (),
        cache_key: str | None = None,
        default_suffix: str = ".dat",
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        """
        :param url: 下载文件的链接地址
        :param fallback_urls: 主链接失败时轮换使用的同资源备用链接
        :param retry_http_statuses: 可通过重试或切换线路恢复的 HTTP 状态码
        :param cache_key: 稳定缓存标识，为空时根据 URL 生成
        :param default_suffix: puremagic 无法识别文件类型时使用的后缀名
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param cache_type: 缓存类型
        :param use_curl_cffi: 是否使用 curl_cffi 下载

        :return: 下载完成后的本地文件路径
        :raise ZeroSizeException: 资源大小为 0 时抛出
        :raise SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raise DownloadException: 重试多次仍失败时抛出
        """
        cache_name = generate_file_name(url, cache_key)
        cache_dir = await CacheManager.ensure_dir(cache_type)
        base_path = cache_dir / cache_name
        partial_path = cache_dir / f"{cache_name}.part"
        download_urls = tuple(
            dict.fromkeys(
                candidate for candidate in (url, *(fallback_urls or ())) if candidate
            )
        )

        headers = _with_identity_encoding(self.headers | (ext_headers or {}))
        download_key = str(base_path)
        active_download = self._active_downloads.get(download_key)
        if active_download is not None:
            return await active_download

        async def __download_task() -> Path:
            if cached_path := await CacheManager.get_cached_file(base_path):
                return cached_path
            result = await self.__download_with_retry(
                download_urls=download_urls,
                base_path=base_path,
                partial_path=partial_path,
                default_suffix=default_suffix,
                headers=headers,
                desc=f"{cache_name}{default_suffix}",
                retry_http_statuses=frozenset(retry_http_statuses),
                use_curl_cffi=use_curl_cffi,
            )
            await CacheManager.set_cached_file(base_path, result)
            return result

        download_task = asyncio.create_task(__download_task())
        self._active_downloads[download_key] = download_task

        try:
            return await download_task
        except (SizeLimitException, ZeroSizeException):
            await safe_unlink(partial_path)
            raise
        finally:
            if self._active_downloads.get(download_key) is download_task:
                self._active_downloads.pop(download_key, None)

    async def __download_with_retry(
        self,
        download_urls: tuple[str, ...],
        base_path: Path,
        partial_path: Path,
        default_suffix: str,
        headers: dict[str, str],
        desc: str,
        retry_http_statuses: frozenset[int],
        use_curl_cffi: bool = False,
    ) -> Path:
        last_error: Exception | None = None

        for retry in range(self.MAX_RETRIES + 1):
            current_url = download_urls[retry % len(download_urls)]
            try:
                await self.__download_once(
                    url=current_url,
                    file_path=partial_path,
                    headers=headers,
                    desc=desc,
                    retry_http_statuses=retry_http_statuses,
                    use_curl_cffi=use_curl_cffi,
                )
                suffix = await _detect_file_suffix(
                    partial_path,
                    default_suffix
                    if default_suffix.startswith(".")
                    else f".{default_suffix}",
                )
                file_path = base_path.with_suffix(suffix)
                if await file_path.exists():
                    await safe_unlink(partial_path)
                    return file_path
                await partial_path.rename(file_path)
                return file_path
            except (SizeLimitException, ZeroSizeException):
                await safe_unlink(partial_path)
                raise
            except RetryableDownloadError as e:
                last_error = e
                if not last_error.keep_part:
                    await safe_unlink(partial_path)
                if retry >= self.MAX_RETRIES:
                    break

                delay = min(2**retry, 8)
                logger.warning(
                    f"下载失败，{delay} 秒后重试 ({retry + 1}/"
                    f"{self.MAX_RETRIES}) | {current_url}: {last_error!r}"
                )
                await asyncio.sleep(delay)

        raise DownloadException(
            f"在 {self.MAX_RETRIES} 次重试后下载失败"
        ) from last_error

    def __validate_response(
        self,
        response: UniResponse,
        downloaded: int,
        retry_http_statuses: Collection[int],
    ):
        if downloaded > 0 and response.status_code == 416:
            raise RetryableDownloadError("断点位置无效，重新完整下载", keep_part=False)
        if response.status_code in retry_http_statuses:
            raise RetryableDownloadError(
                f"HTTP {response.status_code}，切换下载线路后重试",
                keep_part=False,
            )
        response.raise_for_status()
        if downloaded > 0:
            self.__validate_header(response, downloaded)

    def __validate_header(self, response: UniResponse, downloaded: int):
        if response.status_code != 206:
            raise RetryableDownloadError("服务器不支持断点续传", keep_part=False)
        content_range = response.headers.get("content-range") or ""
        match = _RE_RANGE_PATTERN.fullmatch(content_range)
        if match is None:
            raise RetryableDownloadError(
                "服务器未返回有效的 Content-Range", keep_part=False
            )
        server_start = int(match[1])
        if server_start != downloaded:
            raise RetryableDownloadError(
                f"Content-Range 错误: 请求 {downloaded}, 返回 {server_start}",
                keep_part=False,
            )

    def __make_range_headers(
        self, headers: dict[str, str], downloaded: int
    ) -> dict[str, str]:
        result = {**headers}
        if downloaded > 0:
            result["Range"] = f"bytes={downloaded}-"
        return result

    async def __download_once(
        self,
        url: str,
        file_path: Path,
        headers: dict[str, str],
        desc: str,
        retry_http_statuses: Collection[int],
        use_curl_cffi: bool,
    ):
        downloaded = (await file_path.stat()).st_size if await file_path.exists() else 0
        async with self.client.stream(
            "GET",
            url,
            headers=self.__make_range_headers(headers, downloaded),
            use_curl_cffi=use_curl_cffi,
        ) as response:
            self.__validate_response(response, downloaded, retry_http_statuses)
            content_encodings = _parse_content_encodings(
                response.headers.get("content-encoding")
            )
            zipped_content = any(
                encoding != "identity" for encoding in content_encodings
            )

            if downloaded > 0 and zipped_content:
                raise RetryableDownloadError(
                    f"压缩响应 {', '.join(content_encodings)!r} 无法安全断点续传",
                    keep_part=False,
                )

            # 编码响应的 Content-Length 是压缩传输体大小，而 aiter_bytes()
            # 返回解码后的文件内容，不能用前者校验后者。正常情况下
            # Accept-Encoding: identity 会避免进入此兼容分支
            content_length = (
                None if zipped_content else response.headers.get("content-length")
            )
            total_size = (
                downloaded + int(content_length)
                if content_length and downloaded > 0
                else int(content_length)
                if content_length
                else None
            )

            if total_size is not None:
                if total_size == 0:
                    raise ZeroSizeException

                if total_size / 1024 / 1024 > pconfig.max_size:
                    logger.warning(
                        f"媒体 url: {url} 大小 {(total_size / 1024 / 1024):.2f} MB "
                        f"超过 {pconfig.max_size} MB, 取消下载"
                    )
                    raise SizeLimitException(total_size / 1024 / 1024)

            mode = "ab" if downloaded > 0 else "wb"

            current_size = downloaded

            with self.rich_progress(
                desc,
                total_size,
            ) as update:
                if downloaded:
                    update(advance=downloaded)

                async with aiofiles.open(
                    file_path,
                    mode,
                ) as f:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        await f.write(chunk)

                        current_size += len(chunk)

                        update(advance=len(chunk))

                        # 没有Content-Length时限制大小
                        if (
                            total_size is None
                            and current_size / 1024 / 1024 > pconfig.max_size
                        ):
                            logger.warning(
                                f"媒体 url: {url} 实际"
                                f"下载大小 {(current_size / 1024 / 1024):.2f} MB "
                                f"超过 {pconfig.max_size} MB, 取消下载"
                            )
                            raise SizeLimitException(current_size / 1024 / 1024)

            final_size = (await file_path.stat()).st_size

            if final_size == 0:
                raise ZeroSizeException

            # 允许一定范围内的大小不匹配（最多 1KB），避免因为服务器端的轻微差异导致失败
            if total_size is not None and final_size != total_size:
                size_diff = abs(final_size - total_size)
                if size_diff > self._SIZE_MISMATCH_TOLERANCE_BYTES:
                    raise RetryableDownloadError(
                        f"文件大小不匹配: {final_size}/{total_size} "
                        f"(差值: {size_diff} bytes, 超过允许的 "
                        f"{self._SIZE_MISMATCH_TOLERANCE_BYTES} bytes)",
                        keep_part=final_size < total_size,
                    )

    @auto_task
    async def download_video(
        self,
        *,
        url: str,
        fallback_urls: Sequence[str] | None = None,
        retry_http_statuses: Collection[int] = (),
        cache_key: str | None = None,
        cache_variant: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        """
        下载普通视频

        :param url: 视频下载地址
        :param fallback_urls: 主链接失败时轮换使用的同资源备用链接
        :param retry_http_statuses: 可通过重试或切换线路恢复的 HTTP 状态码
        :param cache_key: 视频的稳定缓存标识，为空时根据 URL 生成
        :param cache_variant: 同一资源下的视频用途标识
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param cache_type: 缓存类型
        :param use_curl_cffi: 是否使用 curl_cffi 下载

        :return: 下载完成后的视频文件路径
        :raise ZeroSizeException: 资源大小为 0 时抛出
        :raise SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raise DownloadException: 重试多次仍失败时抛出
        """
        return await self.streamd(
            url=url,
            fallback_urls=fallback_urls,
            retry_http_statuses=retry_http_statuses,
            cache_key=compose_cache_key("video", cache_key, cache_variant),
            default_suffix=".mp4",
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )

    @auto_task
    async def download_m3u8_video(
        self,
        *,
        url: str,
        cache_key: str | None = None,
        cache_variant: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        """
        下载 m3u8 视频并合并到 mp4

        :param m3u8_url: m3u8 播放列表链接地址
        :param cache_key: 视频的稳定缓存标识，为空时根据 URL 生成
        :param cache_variant: 同一资源下的视频用途标识
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param cache_type: 缓存类型
        :param use_curl_cffi: 是否使用 curl_cffi 下载

        :return: 最终合并并转封装后的 mp4 文件路径
        :raise SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raise DownloadException: m3u8 解析、下载或转封装失败时抛出
        """
        file_id = generate_file_name(
            url=url,
            cache_key=compose_cache_key("m3u8", cache_key, cache_variant),
        )
        video_name = f"{file_id}.mp4"

        cache_dir = await CacheManager.ensure_dir(cache_type)
        final_video_path = cache_dir / video_name
        temp_ts_path = cache_dir / f"{file_id}_temp.ts"

        if await final_video_path.exists():
            return final_video_path

        logger.info(f"[StreamDownloader] 开始下载 m3u8 视频: {file_id}")

        try:
            # 1. 智能解析 m3u8 (自动处理嵌套列表)
            ts_urls = await self._smart_parse_m3u8(
                url, ext_headers=ext_headers, use_curl_cffi=use_curl_cffi
            )
            if not ts_urls:
                raise DownloadException("m3u8 解析结果为空")

            # 2. 下载所有 ts 片段到临时文件
            headers = {**self.headers, **(ext_headers or {})}
            downloaded_bytes = await self._download_m3u8_ts_files(
                ts_urls=ts_urls,
                temp_ts_path=temp_ts_path,
                video_name=video_name,
                headers=headers,
                use_curl_cffi=use_curl_cffi,
            )

            # 3/4. 校验大小并转封装
            await self._finalize_m3u8_download(
                temp_ts_path=temp_ts_path,
                final_video_path=final_video_path,
                downloaded_bytes=downloaded_bytes,
            )

            logger.success(f"[StreamDownloader] m3u8 视频下载完成: {final_video_path}")
            return final_video_path
        except SizeLimitException as e:
            logger.warning(f"[StreamDownloader] m3u8 视频大小超限: {e}")
            await safe_unlink(temp_ts_path)
            raise
        except Exception as e:
            logger.error(f"[StreamDownloader] m3u8 视频下载流程出错: {e}")
            await safe_unlink(temp_ts_path)
            raise DownloadException(f"视频下载失败: {e}") from e

    async def _download_m3u8_ts_files(
        self,
        ts_urls: list[str],
        temp_ts_path: Path,
        video_name: str,
        headers: dict[str, str],
        use_curl_cffi: bool = False,
    ) -> int:
        """
        下载所有 ts 片段并写入临时 ts 文件，返回最终文件实际字节数
        """

        async def download_single_ts(
            ts_url: str,
            f: aiofiles.threadpool.binary.AsyncBufferedIOBase,
            update_progress: Callable[..., None],
            max_retries: int = 3,
        ) -> None:
            for retry in range(max_retries):
                try:
                    async with self.client.stream(
                        "GET",
                        ts_url,
                        headers=headers,
                        use_curl_cffi=use_curl_cffi,
                    ) as resp:
                        if resp.status_code != 200:
                            raise DownloadException(
                                f"请求 ts 失败: {resp.status_code} | url={ts_url}"
                            )

                        async for chunk in resp.aiter_bytes():
                            if not chunk:
                                continue

                            await f.write(chunk)
                            inc = len(chunk)
                            update_progress(advance=inc)

                            # 基于文件当前实际大小判断总大小限制
                            current_bytes = await f.tell()
                            file_size_mb = current_bytes / 1024 / 1024
                            if file_size_mb > pconfig.max_size:
                                logger.warning(
                                    f"m3u8 视频大小 {file_size_mb:.2f} MB 超过 {pconfig.max_size} MB，取消下载"  # noqa: E501
                                )
                                raise SizeLimitException(file_size_mb)
                    return
                except SizeLimitException:
                    # 超限直接抛出，不再重试
                    raise
                except Exception as e:
                    logger.debug(
                        f"下载 ts 文件失败，重试中 ({retry + 1}/{max_retries}): {ts_url}, error: {e}"  # noqa: E501
                    )
                    await asyncio.sleep(1)
            raise DownloadException(f"多次重试仍失败的 ts 片段: {ts_url}")

        with self.rich_progress(video_name) as update_progress:
            async with aiofiles.open(temp_ts_path, "wb") as f:
                for ts_url in ts_urls:
                    await download_single_ts(ts_url, f, update_progress)

                # 所有 ts 下载完成后，取一次实际文件大小返回
                final_size = await f.tell()

        return final_size

    async def _finalize_m3u8_download(
        self,
        temp_ts_path: Path,
        final_video_path: Path,
        downloaded_bytes: int,
    ) -> None:
        """
        校验 ts 汇总大小，并根据 ffmpeg 是否可用输出最终 mp4 文件
        """
        # 校验文件大小 (防止空文件送给 FFmpeg)
        if downloaded_bytes < 1024:
            raise DownloadException(
                f"下载文件过小 ({downloaded_bytes} bytes)，可能下载失败"
            )

        # 转封装处理
        if await FFmpeg.is_available():
            await FFmpeg.remux_to_mp4(temp_ts_path, final_video_path)
        elif await temp_ts_path.exists():
            await temp_ts_path.rename(final_video_path)

        if (
            not await final_video_path.exists()
            or (await final_video_path.stat()).st_size <= 1024
        ):
            raise DownloadException("视频下载失败，最终文件不存在或大小过小")

    async def _smart_parse_m3u8(
        self,
        m3u8_url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> list[str]:
        """
        智能解析 m3u8，支持 Master Playlist (嵌套) 和 Media Playlist

        :param m3u8_url: m3u8 播放列表链接地址

        :return: 展平后的 ts 片段完整下载链接列表
        :raise DownloadException: 解析 m3u8 内容失败或未找到有效子列表时抛出
        """

        logger.info(f"[StreamDownloader] 开始解析 m3u8: {m3u8_url}")
        content = await self.text(
            m3u8_url, ext_headers=ext_headers, use_curl_cffi=use_curl_cffi
        )
        base_url = m3u8_url.rsplit("/", 1)[0] + "/"

        # 检查是否是 Master Playlist (包含子 m3u8 链接)
        if "#EXT-X-STREAM-INF" in content:
            logger.debug(
                "[StreamDownloader] 检测到 Master Playlist，正在提取最高画质链接..."
            )
            lines = content.splitlines()
            sub_playlists = []

            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    # 处理相对路径
                    if not line.startswith("http"):
                        line = urljoin(base_url, line)
                    sub_playlists.append(line)

            if sub_playlists:
                # 通常最后一个是最高画质，或者是第一个
                logger.debug(f"[StreamDownloader] 转向子播放列表: {sub_playlists[-1]}")
                return await self._smart_parse_m3u8(
                    sub_playlists[-1],
                    ext_headers=ext_headers,
                    use_curl_cffi=use_curl_cffi,
                )
            else:
                raise DownloadException("Master Playlist 解析失败，未找到子链接")

        # 处理 Media Playlist (真正的 TS 列表)
        ts_urls = []
        lines = content.splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("http"):
                ts_urls.append(line)
            else:
                ts_urls.append(urljoin(base_url, line))

        logger.info(
            f"[StreamDownloader] m3u8 解析完成，共找到 {len(ts_urls)} 个 ts 文件"
        )
        return ts_urls

    async def text(
        self,
        url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> str:
        """
        获取文本内容

        :param url: 目标文本资源的链接地址
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param use_curl_cffi: 是否使用 curl_cffi 请求

        :return: 响应体的文本内容
        :raise DownloadException: 请求状态码非 200 时抛出
        """
        headers = {**self.headers, **(ext_headers or {})}
        resp = await self.client.get(
            url,
            headers=headers,
            use_curl_cffi=use_curl_cffi,
        )
        if resp.status_code != 200:
            raise DownloadException(f"请求失败: {resp.status_code}")
        return resp.text

    async def content(
        self,
        url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> bytes:
        """
        获取内容

        :param url: 目标资源的链接地址
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param use_curl_cffi: 是否使用 curl_cffi 请求

        :return: 响应体的内容
        :raise DownloadException: 请求状态码非 200 时抛出
        """
        headers = {**self.headers, **(ext_headers or {})}
        resp = await self.client.get(
            url,
            headers=headers,
            use_curl_cffi=use_curl_cffi,
        )
        if resp.status_code != 200:
            raise DownloadException(f"请求失败: {resp.status_code}")
        return resp.content

    @auto_task
    async def download_audio(
        self,
        *,
        url: str,
        fallback_urls: Sequence[str] | None = None,
        retry_http_statuses: Collection[int] = (),
        cache_key: str | None = None,
        cache_variant: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
        convert_to_mp3: bool = False,
    ) -> Path:
        """
        下载音频

        :param url: 音频下载地址
        :param fallback_urls: 主链接失败时轮换使用的同资源备用链接
        :param retry_http_statuses: 可通过重试或切换线路恢复的 HTTP 状态码
        :param cache_key: 音频的稳定缓存标识，为空时根据 URL 生成
        :param cache_variant: 同一资源下的音频用途标识
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param cache_type: 缓存类型
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        :param convert_to_mp3: 下载完成后是否使用 ffmpeg 转换为 mp3

        :return: 下载完成后的音频文件路径
        :raise DownloadException: 下载过程中发生错误时抛出
        """
        audio_path = await self.streamd(
            url=url,
            fallback_urls=fallback_urls,
            retry_http_statuses=retry_http_statuses,
            cache_key=compose_cache_key("audio", cache_key, cache_variant),
            default_suffix=".mp3",
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )
        if convert_to_mp3:
            return await FFmpeg.convert_to_mp3(audio_path)
        return audio_path

    @auto_task
    async def download_img(
        self,
        *,
        url: str,
        cache_key: str | None = None,
        cache_variant: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        """
        下载图片

        :param url: 图片下载地址
        :param cache_key: 图片的稳定缓存标识，为空时根据 URL 生成
        :param cache_variant: 同一资源下的图片用途标识
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param cache_type: 缓存类型
        :param use_curl_cffi: 是否使用 curl_cffi 下载

        :return: 下载完成后的图片文件路径
        :raise DownloadException: 下载过程中发生错误时抛出
        """
        return await self.streamd(
            url=url,
            cache_key=compose_cache_key("image", cache_key, cache_variant),
            default_suffix=".jpg",
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )

    async def download_av_and_merge(
        self,
        video_url: str,
        audio_url: str,
        cache_key: str | None = None,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
        video_fallback_urls: Sequence[str] | None = None,
        audio_fallback_urls: Sequence[str] | None = None,
        retry_http_statuses: Collection[int] = (),
    ) -> Path:
        """
        下载音频和视频文件并合并

        :param video_url: 视频流下载地址
        :param audio_url: 音频流下载地址
        :param video_fallback_urls: 视频流备用下载地址
        :param audio_fallback_urls: 音频流备用下载地址
        :param retry_http_statuses: 可通过重试或切换线路恢复的 HTTP 状态码
        :param cache_key: 合并任务的稳定缓存标识，为空时根据两个 URL 生成
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        :return: 合并后的视频文件本地路径(mp4)
        :raise DownloadException: 下载或合并过程中发生错误时抛出
        """
        merge_cache_key = compose_cache_key("video", cache_key, "merged")
        if merge_cache_key is None:
            merge_cache_key = f"video:{video_url}\naudio:{audio_url}\nmerged"
        merge_name = generate_file_name(url=video_url, cache_key=merge_cache_key)
        cache_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
        output_path = cache_dir / f"{merge_name}.mp4"
        if await output_path.exists():
            return output_path
        v_path, a_path = await asyncio.gather(
            self.download_video(
                url=video_url,
                fallback_urls=video_fallback_urls,
                retry_http_statuses=retry_http_statuses,
                cache_key=cache_key,
                cache_variant="source" if cache_key is not None else None,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            ),
            self.download_audio(
                url=audio_url,
                fallback_urls=audio_fallback_urls,
                retry_http_statuses=retry_http_statuses,
                cache_key=cache_key,
                cache_variant="source" if cache_key is not None else None,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            ),
        )
        return await FFmpeg.merge_av(v_path=v_path, a_path=a_path, file_name=merge_name)

    @staticmethod
    @contextlib.contextmanager
    def rich_progress(
        desc: str, total: int | None = None
    ) -> Generator[Callable[..., None], None, None]:
        """
        :param desc: 进度条描述
        :param total: 进度条总长度
        :return: progress.update
        """
        with Progress(
            "[progress.description]{task.description}",
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task_id = progress.add_task(description=desc, total=total)
            yield partial(progress.update, task_id)


DOWNLOADER: StreamDownloader = StreamDownloader()
