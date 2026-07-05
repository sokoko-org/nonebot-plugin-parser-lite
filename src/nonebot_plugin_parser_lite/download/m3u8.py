import asyncio
from collections.abc import Awaitable, Callable
import hashlib
from typing import Any
from urllib.parse import urljoin

import aiofiles
from anyio import Path
from nonebot import logger

from ..cache import CacheManager
from ..exception import DownloadException, SizeLimitException
from ..utils.common import make_filename, safe_unlink
from .client import DownloadHttpClient
from .models import (
    M3U8_SEGMENT_RETRIES,
    M3U8_SEGMENT_TIMEOUT,
    MIN_VALID_VIDEO_BYTES,
    check_media_size,
)
from .progress import rich_progress


class M3U8Downloader:
    def __init__(
        self,
        *,
        client: DownloadHttpClient,
        headers: dict[str, str],
        fetch_text: Callable[..., Awaitable[str]],
        has_ffmpeg: Callable[[], Awaitable[bool]],
        remux_to_mp4: Callable[[Path, Path], Awaitable[None]],
    ):
        self.client = client
        self.headers = headers
        self._fetch_text = fetch_text
        self._has_ffmpeg = has_ffmpeg
        self._remux_to_mp4 = remux_to_mp4
        self._locks: dict[str, asyncio.Lock] = {}

    async def download(
        self,
        *,
        url: str,
        video_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        file_id = hashlib.md5(url.encode()).hexdigest()[:16]
        final_name = make_filename(video_name) if video_name else f"{file_id}.mp4"
        cache_dir = await CacheManager.ensure_dir(cache_type)
        final_video_path = cache_dir / final_name
        temp_ts_path = cache_dir / f"{file_id}_temp.ts"

        if await final_video_path.exists():
            return final_video_path

        lock = self._locks.setdefault(str(temp_ts_path), asyncio.Lock())
        async with lock:
            if await final_video_path.exists():
                return final_video_path
            return await self._download_locked(
                url=url,
                file_id=file_id,
                final_name=final_name,
                final_video_path=final_video_path,
                temp_ts_path=temp_ts_path,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )

    async def _download_locked(
        self,
        *,
        url: str,
        file_id: str,
        final_name: str,
        final_video_path: Path,
        temp_ts_path: Path,
        ext_headers: dict[str, str] | None,
        use_curl_cffi: bool,
    ) -> Path:
        logger.info(f"[StreamDownloader] 开始下载 m3u8 视频: {file_id}")
        try:
            ts_urls = await self._smart_parse_m3u8(
                url, ext_headers=ext_headers, use_curl_cffi=use_curl_cffi
            )
            if not ts_urls:
                raise DownloadException("m3u8 解析结果为空")

            downloaded_bytes = await self._download_ts_files(
                ts_urls=ts_urls,
                temp_ts_path=temp_ts_path,
                video_name=final_name,
                headers=self._headers(ext_headers),
                use_curl_cffi=use_curl_cffi,
            )
            await self._finalize(
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

    def _headers(self, ext_headers: dict[str, str] | None = None) -> dict[str, str]:
        return {**self.headers, **(ext_headers or {})}

    async def _download_ts_files(
        self,
        ts_urls: list[str],
        temp_ts_path: Path,
        video_name: str,
        headers: dict[str, str],
        use_curl_cffi: bool = False,
    ) -> int:
        with rich_progress(video_name) as update_progress:
            async with aiofiles.open(temp_ts_path, "wb") as file:
                for ts_url in ts_urls:
                    await self._download_single_ts(
                        ts_url=ts_url,
                        file=file,
                        update_progress=update_progress,
                        headers=headers,
                        use_curl_cffi=use_curl_cffi,
                    )
                return await file.tell()

    async def _download_single_ts(
        self,
        *,
        ts_url: str,
        file: Any,
        update_progress: Callable[..., None],
        headers: dict[str, str],
        use_curl_cffi: bool,
    ) -> None:
        for retry_index in range(M3U8_SEGMENT_RETRIES):
            try:
                await self._write_single_ts(
                    ts_url=ts_url,
                    file=file,
                    update_progress=update_progress,
                    headers=headers,
                    use_curl_cffi=use_curl_cffi,
                )
                return
            except SizeLimitException:
                raise
            except Exception as e:
                if retry_index + 1 >= M3U8_SEGMENT_RETRIES:
                    break
                logger.debug(
                    "下载 ts 文件失败，重试中 "
                    f"({retry_index + 1}/{M3U8_SEGMENT_RETRIES}): "
                    f"{ts_url}, error: {e}"
                )
                await asyncio.sleep(1)

        raise DownloadException(f"多次重试仍失败的 ts 片段: {ts_url}")

    async def _write_single_ts(
        self,
        *,
        ts_url: str,
        file: Any,
        update_progress: Callable[..., None],
        headers: dict[str, str],
        use_curl_cffi: bool,
    ) -> None:
        async with self.client.stream(
            "GET",
            ts_url,
            headers=headers,
            timeout=M3U8_SEGMENT_TIMEOUT,
            use_curl_cffi=use_curl_cffi,
        ) as resp:
            if resp.status_code != 200:
                raise DownloadException(
                    f"请求 ts 失败: {resp.status_code} | url={ts_url}"
                )

            async for chunk in resp.aiter_bytes():
                if not chunk:
                    continue
                await file.write(chunk)
                update_progress(advance=len(chunk))
                check_media_size(ts_url, await file.tell())

    async def _finalize(
        self,
        temp_ts_path: Path,
        final_video_path: Path,
        downloaded_bytes: int,
    ) -> None:
        if downloaded_bytes < MIN_VALID_VIDEO_BYTES:
            raise DownloadException(
                f"下载文件过小 ({downloaded_bytes} bytes)，可能下载失败"
            )

        if await self._has_ffmpeg():
            await self._remux_to_mp4(temp_ts_path, final_video_path)
        elif await temp_ts_path.exists():
            await temp_ts_path.rename(final_video_path)

        if not await self._is_valid_video_file(final_video_path):
            raise DownloadException("视频下载失败，最终文件不存在或大小过小")

    @staticmethod
    async def _is_valid_video_file(file_path: Path) -> bool:
        return (
            await file_path.exists()
            and (await file_path.stat()).st_size > MIN_VALID_VIDEO_BYTES
        )

    async def _smart_parse_m3u8(
        self,
        m3u8_url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> list[str]:
        logger.info(f"[StreamDownloader] 开始解析 m3u8: {m3u8_url}")
        content = await self._fetch_text(
            m3u8_url, ext_headers=ext_headers, use_curl_cffi=use_curl_cffi
        )
        base_url = m3u8_url.rsplit("/", 1)[0] + "/"

        if "#EXT-X-STREAM-INF" in content:
            return await self._parse_master_playlist(
                content=content,
                base_url=base_url,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            )

        ts_urls = parse_media_playlist(content, base_url)
        logger.info(
            f"[StreamDownloader] m3u8 解析完成，共找到 {len(ts_urls)} 个 ts 文件"
        )
        return ts_urls

    async def _parse_master_playlist(
        self,
        *,
        content: str,
        base_url: str,
        ext_headers: dict[str, str] | None,
        use_curl_cffi: bool,
    ) -> list[str]:
        logger.debug(
            "[StreamDownloader] 检测到 Master Playlist，正在提取最高画质链接..."
        )
        sub_playlists = parse_media_playlist(content, base_url)
        if not sub_playlists:
            raise DownloadException("Master Playlist 解析失败，未找到子链接")

        next_playlist = sub_playlists[-1]
        logger.debug(f"[StreamDownloader] 转向子播放列表: {next_playlist}")
        return await self._smart_parse_m3u8(
            next_playlist,
            ext_headers=ext_headers,
            use_curl_cffi=use_curl_cffi,
        )


def parse_media_playlist(content: str, base_url: str) -> list[str]:
    urls: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line if line.startswith("http") else urljoin(base_url, line))
    return urls
