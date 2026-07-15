import asyncio
from collections.abc import Callable, Generator
import contextlib
from functools import partial
import hashlib
import os
import re
from urllib.parse import urljoin

import aiofiles
from anyio import Path
from nonebot import logger
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from ..cache import CacheManager
from ..config import pconfig
from ..constants import COMMON_HEADER, DOWNLOAD_TIMEOUT
from ..exception import DownloadException, SizeLimitException, ZeroSizeException
from ..utils.common import generate_file_name, make_filename, safe_unlink
from ..utils.ffmpeg import FFmpeg
from .client import UniHttpClient, UniResponse
from .task import auto_task

_RE_RANGE_PATTERN = re.compile(r"bytes\s+(\d+)-\d+/(\d+|\*)")


class StreamDownloader:
    """Downloader class for downloading files with stream"""

    MAX_RETRIES = pconfig.max_retries
    _RESUME_BACKTRACK_BYTES = 256 * 1024
    _SIZE_MISMATCH_TOLERANCE_BYTES = 10 * 1024

    def __init__(self):
        self.headers: dict[str, str] = COMMON_HEADER.copy()
        self.cache_dir: Path = pconfig.cache_dir
        self.client = UniHttpClient(timeout=DOWNLOAD_TIMEOUT)
        self._active_downloads: dict[str, asyncio.Task[None]] = {}
        self._ffmpeg_available: bool | None = None

    async def aclose(self) -> None:
        await self.client.aclose()

    async def head(
        self,
        url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> UniResponse:
        """
        发送 HEAD 请求并返回响应对象。

        :param url: 目标资源地址
        :param ext_headers: 额外请求头
        :param use_curl_cffi: 是否使用 curl_cffi 发起请求
        :return: UniResponse 对象
        :raise HTTPStatusError: HEAD 与 GET 均非 2xx 时抛出
        """
        headers = {**self.headers, **(ext_headers or {})}
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
        file_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        """
        :param url: 下载文件的链接地址
        :param file_name: 保存到本地的文件名，为空时根据 url 自动生成
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param cache_type: 缓存类型
        :param use_curl_cffi: 是否使用 curl_cffi 下载

        :return: 下载完成后的本地文件路径
        :raise ZeroSizeException: 资源大小为 0 时抛出
        :raise SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raise DownloadException: 重试多次仍失败时抛出
        """
        file_name = make_filename(file_name) if file_name else generate_file_name(url)
        cache_dir = await CacheManager.ensure_dir(cache_type)
        file_path = cache_dir / file_name
        partial_path = file_path.parent / f"{file_path.name}.part"

        if await file_path.exists():
            return file_path

        headers = {**self.headers, **(ext_headers or {})}
        download_key = str(file_path)
        active_download = self._active_downloads.get(download_key)
        if active_download is not None:
            await active_download
            return file_path

        async def __download_task() -> None:
            if await file_path.exists():
                return
            await self.__download(
                url=url,
                file_path=file_path,
                partial_path=partial_path,
                headers=headers,
                desc=file_name,
                use_curl_cffi=use_curl_cffi,
            )

        download_task = asyncio.create_task(__download_task())
        self._active_downloads[download_key] = download_task

        try:
            await download_task
        except (SizeLimitException, ZeroSizeException):
            await safe_unlink(file_path)
            await safe_unlink(partial_path)
            raise
        finally:
            if self._active_downloads.get(download_key) is download_task:
                self._active_downloads.pop(download_key, None)

        return file_path

    async def __download(
        self,
        url: str,
        file_path: Path,
        partial_path: Path,
        headers: dict[str, str],
        desc: str,
        use_curl_cffi: bool = False,
    ) -> None:
        last_error: Exception | None = None

        for retry in range(self.MAX_RETRIES + 1):
            try:
                await self.__download_single(
                    url=url,
                    partial_path=partial_path,
                    headers=headers,
                    desc=desc,
                    use_curl_cffi=use_curl_cffi,
                )
                await partial_path.rename(file_path)
                return
            except (SizeLimitException, ZeroSizeException):
                await safe_unlink(partial_path)
                raise
            except Exception as e:
                last_error = e
                if retry >= self.MAX_RETRIES:
                    break

                delay = min(2**retry, 8)
                if await partial_path.exists():
                    partial_size = (await partial_path.stat()).st_size
                    logger.warning(
                        f"下载失败，保留已下载的 {partial_size / 1024 / 1024:.2f} MB "
                        f"数据, {delay} 秒后使用断点续传重试 ({retry + 1}/"
                        f"{self.MAX_RETRIES}): {last_error}"
                    )
                else:
                    logger.warning(
                        f"下载失败，{delay} 秒后重试 ({retry + 1}/"
                        f"{self.MAX_RETRIES}): {last_error}"
                    )
                await asyncio.sleep(delay)

        if last_error is not None:
            if await partial_path.exists():
                partial_size = (await partial_path.stat()).st_size
                logger.warning(
                    "下载失败但保留了部分文件 "
                    f"({partial_size / 1024 / 1024:.2f} MB): {partial_path}"
                )
            raise DownloadException(
                f"在 {self.MAX_RETRIES} 次重试后下载失败: {last_error}"
            ) from last_error

        raise DownloadException("下载失败")

    async def __download_single(
        self,
        url: str,
        partial_path: Path,
        headers: dict[str, str],
        desc: str,
        use_curl_cffi: bool,
    ):
        def parse_content_length(header_val: str | None) -> int | None:
            if not header_val:
                return None
            try:
                return int(header_val)
            except ValueError:
                return None

        def check_declared_size(content_length: int) -> None:
            if content_length == 0:
                logger.warning(f"媒体 url: {url}, 大小为 0, 取消下载")
                raise ZeroSizeException
            file_size_mb = content_length / 1024 / 1024
            if file_size_mb > pconfig.max_size:
                logger.warning(
                    f"媒体 url: {url} 大小 {file_size_mb:.2f} MB "
                    f"超过 {pconfig.max_size} MB, 取消下载"
                )
                raise SizeLimitException(file_size_mb)

        if not await partial_path.exists():
            start_byte = 0
        else:
            partial_size = (await partial_path.stat()).st_size
            if partial_size <= 0:
                logger.debug("检测到异常part文件, 将重新下载")
                start_byte = 0
            else:
                start_byte = max(0, partial_size - self._RESUME_BACKTRACK_BYTES)
        request_headers = headers
        if start_byte > 0:
            request_headers = {**headers, "Range": f"bytes={start_byte}-"}

        async with self.client.stream(
            "GET",
            url,
            headers=request_headers,
            use_curl_cffi=use_curl_cffi,
        ) as response:
            if response.status_code == 416 and await partial_path.exists():
                partial_size = (await partial_path.stat()).st_size
                if partial_size > 1024:
                    logger.debug("文件大小合理，认为下载已完成")
                    return
                else:
                    logger.warning("文件太小，删除并重新下载")
                    await safe_unlink(partial_path)
                    raise DownloadException("收到416, 但文件大小不合理")

            if response.status_code not in (200, 206):
                try:
                    response.raise_for_status()
                except Exception as e:
                    raise DownloadException(str(e)) from e

            supports_range = response.status_code == 206
            if start_byte > 0 and not supports_range:
                logger.warning("服务器不支持断点续传，将重新下载整个文件")
                start_byte = 0

            if supports_range:
                start_byte = await self.__validate_content_range(
                    response=response,
                    partial_path=partial_path,
                    requested_start=start_byte,
                )

            try:
                response.raise_for_status()
            except Exception as e:
                raise DownloadException(str(e)) from e
            content_length = parse_content_length(
                response.headers.get("content-length")
            )
            total_length = (
                start_byte + content_length
                if supports_range and content_length is not None
                else content_length
            )
            if total_length is not None:
                check_declared_size(total_length)
            await self.__write_to_file(
                response=response,
                file_path=partial_path,
                desc=desc,
                declared_length=total_length,
                downloaded_start=start_byte,
                url=url,
            )

    async def __write_to_file(
        self,
        response: UniResponse,
        file_path: Path,
        desc: str,
        declared_length: int | None,
        downloaded_start: int,
        url: str,
    ) -> None:

        with self.rich_progress(desc, declared_length) as update_progress:
            if downloaded_start > 0:
                update_progress(advance=downloaded_start)

            mode = "r+b" if downloaded_start > 0 else "wb"
            downloaded_bytes = downloaded_start

            async with aiofiles.open(file_path, mode) as file:
                if downloaded_bytes > 0:
                    await file.seek(downloaded_bytes)
                    await file.truncate(downloaded_bytes)

                async for chunk in response.aiter_bytes(1024 * 1024):
                    if not chunk:
                        continue

                    await file.write(chunk)
                    chunk_len = len(chunk)
                    downloaded_bytes += chunk_len

                    update_progress(advance=chunk_len)

                    # 无 Content-Length 时，按实际已下载大小做限制
                    if declared_length is None:
                        file_size_mb = downloaded_bytes / 1024 / 1024
                        if file_size_mb > pconfig.max_size:
                            logger.warning(
                                f"媒体 url: {url} 实际下载大小 {file_size_mb:.2f} MB 超过 {pconfig.max_size} MB, 取消下载"  # noqa: E501
                            )
                            raise SizeLimitException(file_size_mb)

            actual_size = (await file_path.stat()).st_size
            if actual_size == 0:
                raise ZeroSizeException

            if declared_length is None:
                return

            if actual_size < declared_length:
                diff = declared_length - actual_size
                logger.warning(
                    f"文件大小不匹配: 实际 {actual_size} bytes"
                    f" , 预期 {declared_length} bytes"
                )
                logger.warning(
                    f"差异: {diff} bytes "
                    f"({round(((diff) / declared_length) * 100, 2)}%)"
                )
                if diff > self._SIZE_MISMATCH_TOLERANCE_BYTES:
                    raise DownloadException(
                        f"文件下载不完整: 实际 {actual_size} bytes, "
                        f"预期 {declared_length} bytes"
                    )

    async def __validate_content_range(
        self,
        response: UniResponse,
        partial_path: Path,
        requested_start: int,
    ) -> int:
        content_range = response.headers.get("content-range")
        if not content_range:
            return requested_start

        match = _RE_RANGE_PATTERN.match(content_range)
        if not match:
            return requested_start

        response_start = int(match[1])
        if response_start == requested_start:
            return requested_start

        logger.warning(
            "Content-Range 起始位置不匹配: "
            f"请求 {requested_start}, 实际 {response_start}，将重新下载"
        )
        await safe_unlink(partial_path)
        raise DownloadException("Content-Range 起始位置不匹配")

    @auto_task
    async def download_video(
        self,
        *,
        url: str,
        video_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        """
        下载普通视频

        :param url: 视频下载地址
        :param video_name: 保存到本地的视频文件名，为空时根据 url 自动生成 mp4 文件名
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param cache_type: 缓存类型
        :param use_curl_cffi: 是否使用 curl_cffi 下载

        :return: 下载完成后的视频文件路径
        :raise ZeroSizeException: 资源大小为 0 时抛出
        :raise SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raise DownloadException: 重试多次仍失败时抛出
        """
        if video_name is None:
            video_name = generate_file_name(url, ".mp4")

        return await self.streamd(
            url=url,
            file_name=video_name,
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )

    @auto_task
    async def download_m3u8_video(
        self,
        *,
        url: str,
        video_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        """
        下载 m3u8 视频并合并到 mp4

        :param m3u8_url: m3u8 播放列表链接地址
        :param video_name: 输出的 mp4 文件名，为空时根据 m3u8 链接生成
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param cache_type: 缓存类型
        :param use_curl_cffi: 是否使用 curl_cffi 下载

        :return: 最终合并并转封装后的 mp4 文件路径
        :raise SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raise DownloadException: m3u8 解析、下载或转封装失败时抛出
        """
        file_id = hashlib.md5(url.encode()).hexdigest()[:16]

        if video_name is None:
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
        校验 ts 汇总大小，并根据 ffmpeg 是否可用输出最终 mp4 文件。
        """
        # 校验文件大小 (防止空文件送给 FFmpeg)
        if downloaded_bytes < 1024:
            raise DownloadException(
                f"下载文件过小 ({downloaded_bytes} bytes)，可能下载失败"
            )

        # 转封装处理
        if await self._has_ffmpeg():
            await self._remux_to_mp4(temp_ts_path, final_video_path)
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

    async def _has_ffmpeg(self) -> bool:
        """
        :return: 本机是否可用 ffmpeg 可执行程序
        """
        if self._ffmpeg_available is not None:
            return self._ffmpeg_available

        try:
            proc = await asyncio.create_subprocess_shell(
                "ffmpeg -version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            self._ffmpeg_available = proc.returncode == 0
        except Exception:
            self._ffmpeg_available = False
        return self._ffmpeg_available

    async def _remux_to_mp4(self, input_path: Path, output_path: Path):
        """
        :param input_path: 输入的 ts 或其他容器格式文件路径
        :param output_path: 转封装后输出的 mp4 文件路径
        :return: None
        """
        # 增加 -f mp4 强制格式，增加 probesize 防止开头数据分析失败
        cmd = (
            f'ffmpeg -y -v error -probesize 50M -analyzeduration 100M -i "{input_path}"'
            f' -c copy -bsf:a aac_adtstoasc "{output_path}"'
        )
        proc = await asyncio.create_subprocess_shell(cmd)
        await proc.communicate()

        if await output_path.exists() and await input_path.exists():
            os.remove(input_path)

    @auto_task
    async def download_audio(
        self,
        *,
        url: str,
        audio_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        """
        下载音频

        :param url: 音频下载地址
        :param audio_name: 保存到本地的音频文件名，为空时根据 url 自动生成 mp3 文件名
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param cache_type: 缓存类型
        :param use_curl_cffi: 是否使用 curl_cffi 下载

        :return: 下载完成后的音频文件路径
        :raise DownloadException: 下载过程中发生错误时抛出
        """
        if audio_name is None:
            audio_name = generate_file_name(url, ".mp3")
        return await self.streamd(
            url=url,
            file_name=audio_name,
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )

    @auto_task
    async def download_img(
        self,
        *,
        url: str,
        img_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        """
        下载图片

        :param url: 图片下载地址
        :param img_name: 保存到本地的图片文件名，为空时根据 url 自动生成 jpg 文件名
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param cache_type: 缓存类型
        :param use_curl_cffi: 是否使用 curl_cffi 下载

        :return: 下载完成后的图片文件路径
        :raise DownloadException: 下载过程中发生错误时抛出
        """
        if img_name is None:
            img_name = generate_file_name(url, ".jpg")
        return await self.streamd(
            url=url,
            file_name=img_name,
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )

    async def download_av_and_merge(
        self,
        video_url: str,
        audio_url: str,
        merge_name: str,
        video_name: str | None = None,
        audio_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> Path:
        """
        下载音频和视频文件并合并

        :param video_url: 视频流下载地址
        :param audio_url: 音频流下载地址
        :param merge_name: 合并后输出文件名(不含扩展名)
        :param video_name: 保存到本地的视频文件名，为空时根据 url 自动生成 mp4 文件名
        :param audio_name: 保存到本地的音频文件名，为空时根据 url 自动生成 mp3 文件名
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param use_curl_cffi: 是否使用 curl_cffi 下载
        :return: 合并后的视频文件本地路径(mp4)
        :raise DownloadException: 下载或合并过程中发生错误时抛出
        """
        cache_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
        output_path = cache_dir / f"{merge_name}.mp4"
        if await output_path.exists():
            return output_path
        v_path, a_path = await asyncio.gather(
            self.download_video(
                url=video_url,
                video_name=video_name,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            ),
            self.download_audio(
                url=audio_url,
                audio_name=audio_name,
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
