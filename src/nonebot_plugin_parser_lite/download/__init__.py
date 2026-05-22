import asyncio
from collections.abc import Callable, Generator
import contextlib
from functools import partial
import hashlib
import os
from urllib.parse import urljoin

import aiofiles
from anyio import Path
from httpx import AsyncClient, Response
from nonebot import logger
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
from ..utils.common import generate_file_name, make_filename, safe_unlink
from ..utils.ffmpeg import FFmpeg
from .task import auto_task


class StreamDownloader:
    """Downloader class for downloading files with stream"""

    def __init__(self):
        self.headers: dict[str, str] = COMMON_HEADER.copy()
        self.cache_dir: Path = pconfig.cache_dir
        self.client: AsyncClient = AsyncClient(timeout=DOWNLOAD_TIMEOUT, verify=False)

    async def head_size(
        self, url: str, ext_headers: dict[str, str] | None = None
    ) -> int | None:
        """对给定 url 发送 HEAD 请求，返回 Content-Length（字节数）。

        - 请求失败或无 Content-Length 时返回 None
        - 不做大小限制校验，只用于展示/预估
        """
        headers = {**self.headers, **(ext_headers or {})}
        resp = await self.client.head(
            url=url,
            headers=headers,
            follow_redirects=True,
        )
        resp.raise_for_status()

        raw_len = resp.headers.get("Content-Length")
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
    ) -> Path:
        """
        :param url: 下载文件的链接地址
        :param file_name: 保存到本地的文件名，为空时根据 url 自动生成
        :param ext_headers: 额外的请求头，会与默认请求头合并

        :return: 下载完成后的本地文件路径
        :raise ZeroSizeException: 资源大小为 0 时抛出
        :raise SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raise DownloadException: 重试多次仍失败时抛出
        """
        file_name = make_filename(file_name) if file_name else generate_file_name(url)
        file_path = self.cache_dir / file_name

        # 已有缓存文件，直接返回
        if await file_path.exists():
            return file_path

        headers = {**self.headers, **(ext_headers or {})}

        await self._download_with_stream(
            url=url,
            file_path=file_path,
            headers=headers,
            desc=file_name,
        )

        return file_path

    async def _download_with_stream(
        self,
        url: str,
        file_path: Path,
        headers: dict[str, str],
        desc: str,
    ) -> None:
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
                    f"媒体 url: {url} 大小 {file_size_mb:.2f} MB 超过 {pconfig.max_size} MB, 取消下载"  # noqa: E501
                )
                raise SizeLimitException(file_size_mb)

        async with self.client.stream(
            "GET", url, headers=headers, follow_redirects=True
        ) as response:
            try:
                response.raise_for_status()
            except Exception as e:
                raise DownloadException from e
            content_length = parse_content_length(
                response.headers.get("Content-Length")
            )
            if content_length is not None:
                check_declared_size(content_length)
            await self._write_stream_to_file(
                response=response,
                file_path=file_path,
                desc=desc,
                declared_length=content_length,
                url=url,
            )

    async def _write_stream_to_file(
        self,
        response: Response,
        file_path: Path,
        desc: str,
        declared_length: int | None,
        url: str,
    ) -> None:
        """将 HTTP 流写入文件，并处理进度条与实际大小限制。"""
        with self.rich_progress(desc, declared_length) as update_progress:
            downloaded_bytes = 0

            async with aiofiles.open(file_path, "wb") as file:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    if not chunk:
                        continue

                    await file.write(chunk)
                    chunk_len = len(chunk)
                    downloaded_bytes += chunk_len

                    # 更新进度条（无 Content-Length 时显示“已下载字节数”）
                    update_progress(advance=chunk_len)

                    # 无 Content-Length 时，按实际已下载大小做限制
                    if declared_length is None:
                        file_size_mb = downloaded_bytes / 1024 / 1024
                        if file_size_mb > pconfig.max_size:
                            logger.warning(
                                f"媒体 url: {url} 实际下载大小 {file_size_mb:.2f} MB 超过 {pconfig.max_size} MB, 取消下载"  # noqa: E501
                            )
                            raise SizeLimitException(file_size_mb)

    @auto_task
    async def download_video(
        self,
        *,
        url: str,
        video_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """
        下载普通视频

        :param url: 视频下载地址
        :param video_name: 保存到本地的视频文件名，为空时根据 url 自动生成 mp4 文件名
        :param ext_headers: 额外的请求头，会与默认请求头合并

        :return: 下载完成后的视频文件路径
        :raise ZeroSizeException: 资源大小为 0 时抛出
        :raise SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raise DownloadException: 重试多次仍失败时抛出
        """
        if video_name is None:
            video_name = generate_file_name(url, ".mp4")

        return await self.streamd(
            url=url, file_name=video_name, ext_headers=ext_headers
        )

    @auto_task
    async def download_m3u8_video(
        self,
        *,
        url: str,
        video_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """
        下载 m3u8 视频并合并到 mp4

        :param m3u8_url: m3u8 播放列表链接地址
        :param video_name: 输出的 mp4 文件名，为空时根据 m3u8 链接生成
        :param ext_headers: 额外的请求头，会与默认请求头合并

        :return: 最终合并并转封装后的 mp4 文件路径
        :raise SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raise DownloadException: m3u8 解析、下载或转封装失败时抛出
        """
        file_id = hashlib.md5(url.encode()).hexdigest()[:16]

        if video_name is None:
            video_name = f"{file_id}.mp4"

        final_video_path = self.cache_dir / video_name
        temp_ts_path = self.cache_dir / f"{file_id}_temp.ts"

        if await final_video_path.exists():
            return final_video_path

        logger.info(f"[StreamDownloader] 开始下载 m3u8 视频: {file_id}")

        try:
            # 1. 智能解析 m3u8 (自动处理嵌套列表)
            ts_urls = await self._smart_parse_m3u8(url)
            if not ts_urls:
                raise DownloadException("m3u8 解析结果为空")

            # 2. 下载所有 ts 片段到临时文件
            headers = {**self.headers, **(ext_headers or {})}
            downloaded_bytes = await self._download_m3u8_ts_files(
                ts_urls=ts_urls,
                temp_ts_path=temp_ts_path,
                video_name=video_name,
                headers=headers,
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
                        timeout=15,
                        follow_redirects=True,
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

    async def _smart_parse_m3u8(self, m3u8_url: str) -> list[str]:
        """
        智能解析 m3u8，支持 Master Playlist (嵌套) 和 Media Playlist

        :param m3u8_url: m3u8 播放列表链接地址

        :return: 展平后的 ts 片段完整下载链接列表
        :raise DownloadException: 解析 m3u8 内容失败或未找到有效子列表时抛出
        """

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
        """
        获取文本内容

        :param url: 目标文本资源的链接地址

        :return: 响应体的文本内容
        :raise DownloadException: 请求状态码非 200 时抛出
        """
        # 准备请求 headers
        fetch_headers = self.headers.copy()
        # 使用 get 方法获取完整响应
        resp = await self.client.get(
            url, headers=fetch_headers, timeout=10, follow_redirects=True
        )
        if resp.status_code != 200:
            raise DownloadException(f"请求失败: {resp.status_code}")
        return resp.text

    async def _has_ffmpeg(self) -> bool:
        """
        :return: 本机是否可用 ffmpeg 可执行程序
        """
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
    ) -> Path:
        """
        下载音频
        :param url: 音频下载地址
        :param audio_name: 保存到本地的音频文件名，为空时根据 url 自动生成 mp3 文件名
        :param ext_headers: 额外的请求头，会与默认请求头合并

        :return: 下载完成后的音频文件路径
        :raise DownloadException: 下载过程中发生错误时抛出
        """
        if audio_name is None:
            audio_name = generate_file_name(url, ".mp3")
        return await self.streamd(
            url=url, file_name=audio_name, ext_headers=ext_headers
        )

    @auto_task
    async def download_img(
        self,
        *,
        url: str,
        img_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """
        下载图片

        :param url: 图片下载地址
        :param img_name: 保存到本地的图片文件名，为空时根据 url 自动生成 jpg 文件名
        :param ext_headers: 额外的请求头，会与默认请求头合并

        :return: 下载完成后的图片文件路径
        :raise DownloadException: 下载过程中发生错误时抛出
        """
        if img_name is None:
            img_name = generate_file_name(url, ".jpg")
        return await self.streamd(url=url, file_name=img_name, ext_headers=ext_headers)

    async def download_av_and_merge(
        self,
        v_url: str,
        a_url: str,
        file_name: str,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """
        下载音频和视频文件并合并

        :param v_url: 视频流下载地址
        :param a_url: 音频流下载地址
        :param file_name: 合并后输出文件名(不含扩展名)
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :return: 合并后的视频文件本地路径
        :raise DownloadException: 下载或合并过程中发生错误时抛出
        """
        v_path, a_path = await asyncio.gather(
            self.download_video(url=v_url, ext_headers=ext_headers),
            self.download_audio(url=a_url, ext_headers=ext_headers),
        )
        return await FFmpeg.merge_av(v_path=v_path, a_path=a_path, file_name=file_name)

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
