import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal

import aiofiles
from anyio import Path
from nonebot import logger

from ..cache import CacheManager
from ..exception import DownloadException, SizeLimitException, ZeroSizeException
from ..utils.common import generate_file_name, make_filename, safe_unlink
from .client import DownloadHttpClient, DownloadResponse
from .models import (
    STREAM_CHUNK_SIZE,
    STREAM_DOWNLOAD_RETRIES,
    StreamDownloadTarget,
    StreamRequestPlan,
    StreamWritePlan,
    check_media_size,
    file_size,
    make_part_path,
    parse_content_range_total,
    parse_int_header,
    resolve_total_size,
)
from .progress import rich_progress


class FileDownloader:
    def __init__(
        self,
        *,
        client: DownloadHttpClient,
        headers: dict[str, str],
        active_downloads: dict[str, asyncio.Task[None]],
    ):
        self.client = client
        self.headers = headers
        self._active_downloads = active_downloads

    async def download(
        self,
        *,
        url: str,
        file_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        target = await self._build_target(
            url=url,
            file_name=file_name,
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )
        if await target.file_path.exists():
            return target.file_path

        await self._run_deduplicated(
            target.file_path,
            lambda: self._download_with_retries(target),
        )
        return target.file_path

    async def _build_target(
        self,
        *,
        url: str,
        file_name: str | None,
        ext_headers: dict[str, str] | None,
        cache_type: str,
        use_curl_cffi: bool,
    ) -> StreamDownloadTarget:
        final_name = make_filename(file_name) if file_name else generate_file_name(url)
        cache_dir = await CacheManager.ensure_dir(cache_type)
        file_path = cache_dir / final_name
        return StreamDownloadTarget(
            url=url,
            file_path=file_path,
            part_path=make_part_path(file_path),
            desc=final_name,
            headers=self._headers(ext_headers),
            use_curl_cffi=use_curl_cffi,
        )

    def _headers(self, ext_headers: dict[str, str] | None = None) -> dict[str, str]:
        return {**self.headers, **(ext_headers or {})}

    async def _run_deduplicated(
        self,
        file_path: Path,
        download_factory: Callable[[], Awaitable[None]],
    ) -> None:
        download_key = str(file_path)
        active_download = self._active_downloads.get(download_key)
        if active_download is not None:
            await active_download
            return

        async def _download_task() -> None:
            if not await file_path.exists():
                await download_factory()

        task = asyncio.create_task(_download_task())
        self._active_downloads[download_key] = task
        try:
            await task
        finally:
            if self._active_downloads.get(download_key) is task:
                self._active_downloads.pop(download_key, None)

    async def _download_with_retries(self, target: StreamDownloadTarget) -> None:
        last_error: Exception | None = None

        for retry_index in range(STREAM_DOWNLOAD_RETRIES):
            try:
                await self._run_attempt(target)
                return
            except (SizeLimitException, ZeroSizeException):
                await safe_unlink(target.part_path)
                raise
            except Exception as e:
                last_error = e
                if retry_index + 1 >= STREAM_DOWNLOAD_RETRIES:
                    break
                logger.warning(
                    f"[StreamDownloader] 下载中断，准备断点续传 ({retry_index + 1}/"
                    f"{STREAM_DOWNLOAD_RETRIES}): {target.url}, error: {last_error}"
                )
                await asyncio.sleep(1)

        await safe_unlink(target.part_path)
        raise DownloadException("多次重试仍下载失败，已删除临时文件") from last_error

    async def _run_attempt(self, target: StreamDownloadTarget) -> None:
        request = await self._build_request(target)
        async with self.client.stream(
            "GET",
            target.url,
            headers=request.headers,
            use_curl_cffi=target.use_curl_cffi,
        ) as response:
            if await self._handle_special_status(response, target):
                return

            write_plan = self._build_write_plan(response, request)
            if write_plan.total_size is not None:
                check_media_size(target.url, write_plan.total_size)

            await self._write_response(
                response=response,
                file_path=target.part_path,
                desc=target.desc,
                declared_length=write_plan.total_size,
                url=target.url,
                initial_bytes=write_plan.initial_bytes,
                mode=write_plan.mode,
            )

        await self._commit(target, write_plan.total_size)

    async def _build_request(self, target: StreamDownloadTarget) -> StreamRequestPlan:
        partial_size = await file_size(target.part_path)
        headers = target.headers.copy()
        if partial_size > 0:
            headers["Range"] = f"bytes={partial_size}-"
        return StreamRequestPlan(headers=headers, partial_size=partial_size)

    async def _handle_special_status(
        self,
        response: DownloadResponse,
        target: StreamDownloadTarget,
    ) -> bool:
        if response.status_code == 416:
            if await self._handle_range_not_satisfiable(response, target):
                return True
            raise DownloadException("Range 不可满足，已丢弃临时文件并准备重试")

        try:
            response.raise_for_status()
        except Exception as e:
            raise DownloadException(str(e)) from e
        return False

    async def _handle_range_not_satisfiable(
        self,
        response: DownloadResponse,
        target: StreamDownloadTarget,
    ) -> bool:
        total_size = parse_content_range_total(response.headers.get("Content-Range"))
        part_size = await file_size(target.part_path)
        if total_size is not None and part_size == total_size:
            await target.part_path.rename(target.file_path)
            return True

        logger.debug(
            "[StreamDownloader] Range 不可满足，丢弃临时文件后重新下载: "
            f"{target.part_path}"
        )
        await safe_unlink(target.part_path)
        return False

    @staticmethod
    def _build_write_plan(
        response: DownloadResponse,
        request: StreamRequestPlan,
    ) -> StreamWritePlan:
        content_length = parse_int_header(response.headers.get("Content-Length"))
        total_size = resolve_total_size(
            response=response,
            content_length=content_length,
            partial_size=request.partial_size,
        )
        can_resume = request.partial_size > 0 and response.status_code == 206

        if request.partial_size > 0 and not can_resume:
            logger.warning(
                f"[StreamDownloader] 服务器未响应 206, 重新下载: {response.url}"
            )

        return StreamWritePlan(
            total_size=total_size,
            initial_bytes=request.partial_size if can_resume else 0,
            mode="ab" if can_resume else "wb",
        )

    async def _commit(
        self,
        target: StreamDownloadTarget,
        total_size: int | None,
    ) -> None:
        part_size = await file_size(target.part_path)
        if total_size is not None and part_size < total_size:
            raise DownloadException(f"下载不完整: {part_size}/{total_size} bytes")
        if part_size == 0:
            raise ZeroSizeException
        await target.part_path.rename(target.file_path)

    @staticmethod
    async def _write_response(
        *,
        response: DownloadResponse,
        file_path: Path,
        desc: str,
        declared_length: int | None,
        url: str,
        initial_bytes: int = 0,
        mode: Literal["wb", "ab"] = "wb",
    ) -> None:
        with rich_progress(desc, declared_length) as update_progress:
            downloaded_bytes = initial_bytes
            if downloaded_bytes:
                update_progress(completed=downloaded_bytes)

            async with aiofiles.open(file_path, mode) as file:
                async for chunk in response.aiter_bytes(STREAM_CHUNK_SIZE):
                    if not chunk:
                        continue

                    await file.write(chunk)
                    downloaded_bytes += len(chunk)
                    update_progress(advance=len(chunk))

                    if declared_length is None:
                        check_media_size(url, downloaded_bytes)
