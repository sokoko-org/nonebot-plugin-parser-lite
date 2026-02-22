import os
import asyncio
import hashlib
from pathlib import Path

import aiofiles
from httpx import HTTPError, AsyncClient
from nonebot import logger
from rich.progress import Progress, BarColumn, TimeElapsedColumn, TimeRemainingColumn

from .task import auto_task
from ..utils import merge_av, safe_unlink, generate_file_name
from ..config import pconfig
from ..constants import COMMON_HEADER, DOWNLOAD_TIMEOUT
from ..exception import DownloadException, ZeroSizeException, SizeLimitException


class StreamDownloader:
    """Downloader class for downloading files with stream"""

    def __init__(self):
        self.headers: dict[str, str] = COMMON_HEADER.copy()
        self.cache_dir: Path = pconfig.cache_dir
        self.client: AsyncClient = AsyncClient(timeout=DOWNLOAD_TIMEOUT, verify=False)

    @auto_task
    async def streamd(
        self,
        url: str,
        *,
        file_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        max_retries: int = 3,
    ) -> Path:
        """download file by url with stream

        Args:
            url (str): url address
            file_name (str | None): file name. Defaults to generate_file_name.
            ext_headers (dict[str, str] | None): ext headers. Defaults to None.
            max_retries (int): maximum number of retries when download fails. Defaults to 3.

        Returns:
            Path: file path

        Raises:
            httpx.HTTPError: When download fails
        """

        if not file_name:
            file_name = generate_file_name(url)
        file_path = self.cache_dir / file_name
        # 如果文件存在，则直接返回
        if file_path.exists():
            return file_path

        headers = {**self.headers, **(ext_headers or {})}

        retry_count = 0
        original_file_name = file_name
        while retry_count <= max_retries:
            try:
                async with self.client.stream(
                    "GET", url, headers=headers, follow_redirects=True
                ) as response:
                    response.raise_for_status()
                    content_length = response.headers.get("Content-Length")
                    content_length = int(content_length) if content_length else 0

                    if content_length == 0:
                        logger.warning(f"媒体 url: {url}, 大小为 0, 取消下载")
                        raise ZeroSizeException

                    if (file_size := content_length / 1024 / 1024) > pconfig.max_size:
                        logger.warning(
                            f"媒体 url: {url} 大小 {file_size:.2f} MB 超过 {pconfig.max_size} MB, 取消下载"
                        )
                        raise SizeLimitException

                    with self.get_progress_bar(file_name, content_length) as bar:
                        task_id = bar.task_ids[0]
                        async with aiofiles.open(file_path, "wb") as file:
                            async for chunk in response.aiter_bytes(1024 * 1024):
                                await file.write(chunk)
                                bar.advance(task_id, len(chunk))
                    # 下载成功，跳出循环
                    break
            except (HTTPError, ConnectionError, TimeoutError, OSError) as e:
                retry_count += 1
                await safe_unlink(file_path)
                if retry_count > max_retries:
                    logger.exception(
                        f"下载失败，已重试 {max_retries} 次 | url: {url}, file_path: {file_path}"
                    )
                    raise DownloadException(f"媒体下载失败: {e}") from e
                # 如果是第二次重试或更晚，使用随机文件名
                if retry_count >= 2:
                    file_name = generate_file_name(url, Path(original_file_name).suffix)
                    file_path = self.cache_dir / file_name
                    logger.warning(f"使用随机文件名重试下载: {file_name}")
                logger.warning(
                    f"下载失败，正在重试 ({retry_count}/{max_retries}) | url: {url}, "
                    f"error: {e}, 重试文件名: {file_name}"
                )
                # 等待一段时间后重试
                await asyncio.sleep(1 * retry_count)  # 指数退避
        return file_path

    @staticmethod
    def get_progress_bar(desc: str, total: int | None = None) -> Progress:
        """获取进度条 bar

        Args:
            desc (str): 描述
            total (int | None): 总大小. Defaults to None.

        Returns:
            Progress: 进度条
        """
        progress = Progress(
            "[progress.description]{task.description}",
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeElapsedColumn(),  # 已用时间
            TimeRemainingColumn(),  # 剩余时间
        )
        progress.add_task(f"[green]{desc}", total=total)
        return progress

    @auto_task
    async def download_video(
        self,
        url: str,
        *,
        video_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """download video file by url with stream

        Args:
            url (str): url address
            video_name (str | None): video name. Defaults to get name by parse url.
            ext_headers (dict[str, str] | None): ext headers. Defaults to None.

        Returns:
            Path: video file path

        Raises:
            httpx.HTTPError: When download fails
        """
        # 检查是否是 m3u8 链接
        if ".m3u8" in url:
            return await self._download_m3u8_video(url, video_name)

        if video_name is None:
            video_name = generate_file_name(url, ".mp4")
        return await self.streamd(url, file_name=video_name, ext_headers=ext_headers)

    async def _download_m3u8_video(
        self, m3u8_url: str, video_name: str | None = None
    ) -> Path:
        """下载 m3u8 视频并合并为 mp4"""
        # 生成文件 ID
        file_id = hashlib.md5(m3u8_url.encode()).hexdigest()[:16]

        if video_name is None:
            video_name = f"{file_id}.mp4"

        final_video_path = self.cache_dir / video_name
        temp_ts_path = self.cache_dir / f"{file_id}_temp.ts"

        if final_video_path.exists():
            return final_video_path

        logger.info(f"[StreamDownloader] 开始下载 m3u8 视频: {file_id}")

        try:
            # 1. 智能解析 m3u8 (自动处理嵌套列表)
            ts_urls = await self._smart_parse_m3u8(m3u8_url)

            if not ts_urls:
                raise DownloadException("m3u8 解析结果为空")

            # 2. 下载并追加写入
            downloaded_bytes = 0
            # 准备用于 ts 下载的 headers，确保包含必要的验证信息
            ts_headers = self.headers.copy()
            # 如果是 TapTap 的链接，添加特定的 headers
            if "taptap.cn" in m3u8_url:
                ts_headers["Referer"] = "https://www.taptap.cn/"
                ts_headers["Origin"] = "https://www.taptap.cn"

            with self.get_progress_bar(video_name, len(ts_urls) * 1024 * 1024) as bar:
                task_id = bar.task_ids[0]
                async with aiofiles.open(temp_ts_path, "wb") as f:
                    for ts_url in ts_urls:
                        for retry in range(3):
                            try:
                                async with self.client.stream(
                                    "GET",
                                    ts_url,
                                    headers=ts_headers,
                                    timeout=15,
                                    follow_redirects=True,
                                ) as resp:
                                    if resp.status_code == 200:
                                        async for chunk in resp.aiter_bytes():
                                            await f.write(chunk)
                                            downloaded_bytes += len(chunk)
                                            bar.advance(task_id, len(chunk))
                                        break
                                # 检查 resp.status
                            except Exception as e:
                                logger.debug(
                                    f"下载 ts 文件失败，重试中 ({retry+1}/3): {ts_url}, error: {e}"
                                )
                                await asyncio.sleep(1)

            # 3. 校验文件大小 (防止空文件送给 FFmpeg)
            if downloaded_bytes < 1024:
                raise DownloadException(
                    f"下载文件过小 ({downloaded_bytes} bytes)，可能下载失败"
                )

            # 4. 转封装处理
            if await self._has_ffmpeg():
                await self._remux_to_mp4(temp_ts_path, final_video_path)
            elif temp_ts_path.exists():
                temp_ts_path.rename(final_video_path)

            if not final_video_path.exists() or final_video_path.stat().st_size <= 1024:
                raise DownloadException("视频下载失败，最终文件不存在或大小过小")

            logger.success(f"[StreamDownloader] m3u8 视频下载完成: {final_video_path}")
            return final_video_path
        except Exception as e:
            logger.error(f"[StreamDownloader] m3u8 视频下载流程出错: {e}")
            await safe_unlink(temp_ts_path)
            raise DownloadException(f"视频下载失败: {e}") from e

    async def _smart_parse_m3u8(self, m3u8_url: str) -> list[str]:
        """智能解析 m3u8，支持 Master Playlist (嵌套) 和 Media Playlist"""
        from urllib.parse import urljoin

        logger.info(f"[StreamDownloader] 开始解析 m3u8: {m3u8_url}")
        content = await self._fetch_text(m3u8_url)
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
                return await self._smart_parse_m3u8(sub_playlists[-1])
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

    async def _fetch_text(self, url: str) -> str:
        """辅助函数：获取文本内容"""
        # 准备请求 headers
        fetch_headers = self.headers.copy()
        if "taptap.cn" in url:
            fetch_headers["Referer"] = "https://www.taptap.cn/"
            fetch_headers["Origin"] = "https://www.taptap.cn"

        # 使用 get 方法获取完整响应
        resp = await self.client.get(
            url, headers=fetch_headers, timeout=10, follow_redirects=True
        )
        if resp.status_code != 200:
            raise DownloadException(f"请求失败: {resp.status_code}")
        return resp.text

    async def _has_ffmpeg(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_shell(
                "ffmpeg -version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False

    async def _remux_to_mp4(self, input_path: Path, output_path: Path):
        # 增加 -f mp4 强制格式，增加 probesize 防止开头数据分析失败
        cmd = (
            f'ffmpeg -y -v error -probesize 50M -analyzeduration 100M -i "{input_path}"'
            f' -c copy -bsf:a aac_adtstoasc "{output_path}"'
        )
        proc = await asyncio.create_subprocess_shell(cmd)
        await proc.communicate()

        if output_path.exists() and input_path.exists():
            os.remove(input_path)

    @auto_task
    async def download_audio(
        self,
        url: str,
        *,
        audio_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """download audio file by url with stream

        Args:
            url (str): url address
            audio_name (str | None ): audio name. Defaults to generate from url.
            ext_headers (dict[str, str] | None): ext headers. Defaults to None.

        Returns:
            Path: audio file path

        Raises:
            httpx.HTTPError: When download fails
        """
        if audio_name is None:
            audio_name = generate_file_name(url, ".mp3")
        return await self.streamd(url, file_name=audio_name, ext_headers=ext_headers)

    @auto_task
    async def download_img(
        self,
        url: str,
        *,
        img_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """download image file by url with stream

        Args:
            url (str): url
            img_name (str | None): image name. Defaults to generate from url.
            ext_headers (dict[str, str] | None): ext headers. Defaults to None.

        Returns:
            Path: image file path

        Raises:
            httpx.HTTPError: When download fails
        """
        if img_name is None:
            img_name = generate_file_name(url, ".jpg")
        return await self.streamd(url, file_name=img_name, ext_headers=ext_headers)

    async def download_imgs_without_raise(
        self,
        urls: list[str],
        *,
        ext_headers: dict[str, str] | None = None,
    ) -> list[Path]:
        """download images without raise

        Args:
            urls (list[str]): urls
            ext_headers (dict[str, str] | None): ext headers. Defaults to None.

        Returns:
            list[Path]: image file paths
        """
        paths_or_errs = await asyncio.gather(
            *[self.download_img(url, ext_headers=ext_headers) for url in urls],
            return_exceptions=True,
        )
        return [p for p in paths_or_errs if isinstance(p, Path)]

    @auto_task
    async def download_av_and_merge(
        self,
        v_url: str,
        a_url: str,
        *,
        output_path: Path,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """download video and audio file by url with stream and merge"""
        v_path, a_path = await asyncio.gather(
            self.download_video(v_url, ext_headers=ext_headers),
            self.download_audio(a_url, ext_headers=ext_headers),
        )
        await merge_av(v_path=v_path, a_path=a_path, output_path=output_path)
        return output_path


DOWNLOADER: StreamDownloader = StreamDownloader()
