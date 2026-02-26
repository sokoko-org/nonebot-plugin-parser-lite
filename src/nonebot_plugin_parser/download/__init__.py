import os
import asyncio
import hashlib
from pathlib import Path

import aiofiles
from httpx import HTTPError, AsyncClient
from nonebot import logger
from rich.progress import (
    DownloadColumn,
    Progress,
    BarColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

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
        file_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        max_retries: int = 3,
    ) -> Path:
        """
        :param url: 下载文件的链接地址
        :param file_name: 保存到本地的文件名，为空时根据 url 自动生成
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :param max_retries: 下载失败时的最大重试次数

        :return: 下载完成后的本地文件路径
        :raises ZeroSizeException: 资源大小为 0 时抛出
        :raises SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raises DownloadException: 重试多次仍失败时抛出
        """

        if not file_name:
            file_name = generate_file_name(url)
        file_path = self.cache_dir / file_name
        # 如果文件存在，则直接返回
        if file_path.exists():
            return file_path

        headers = {**self.headers, **(ext_headers or {})}

        retry_count = 0
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
                logger.warning(
                    f"下载失败，正在重试 ({retry_count}/{max_retries}) | url: {url}, "
                    f"error: {e}, 重试文件名: {file_name}"
                )
                # 等待一段时间后重试
                await asyncio.sleep(1 * retry_count)  # 指数退避
        return file_path

    @staticmethod
    def get_progress_bar(desc: str, total: int) -> Progress:
        """获取进度条 bar

        :param desc: 进度条描述文本
        :param total: 总大小（字节数），用于显示进度比例，为空时显示为不确定进度

        :return: 已配置好的进度条对象
        """
        progress = Progress(
            "[progress.description]{task.description}",
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        )
        progress.add_task(f"[green]{desc}", total=total)
        return progress

    @auto_task
    async def download_video(
        self,
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
        :raises DownloadException: 下载过程中发生错误时抛出
        """
        if video_name is None:
            video_name = generate_file_name(url, ".mp4")
        return await self.streamd(url, file_name=video_name, ext_headers=ext_headers)

    @auto_task
    async def download_m3u8_video(
        self, m3u8_url: str, video_name: str | None = None
    ) -> Path:
        """
        下载 m3u8 视频并合并到 mp4

        :param m3u8_url: m3u8 播放列表链接地址
        :param video_name: 输出的 mp4 文件名，为空时根据 m3u8 链接生成

        :return: 最终合并并转封装后的 mp4 文件路径
        :raises DownloadException: m3u8 解析、下载或转封装失败时抛出
        """
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
        """
        智能解析 m3u8，支持 Master Playlist (嵌套) 和 Media Playlist

        :param m3u8_url: m3u8 播放列表链接地址

        :return: 展平后的 ts 片段完整下载链接列表
        :raises DownloadException: 解析 m3u8 内容失败或未找到有效子列表时抛出
        """
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
        """
        获取文本内容

        :param url: 目标文本资源的链接地址

        :return: 响应体的文本内容
        :raises DownloadException: 请求状态码非 200 时抛出
        """
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

        if output_path.exists() and input_path.exists():
            os.remove(input_path)

    @auto_task
    async def download_audio(
        self,
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
        :raises DownloadException: 下载过程中发生错误时抛出
        """
        if audio_name is None:
            audio_name = generate_file_name(url, ".mp3")
        return await self.streamd(url, file_name=audio_name, ext_headers=ext_headers)

    @auto_task
    async def download_img(
        self,
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
        :raises DownloadException: 下载过程中发生错误时抛出
        """
        if img_name is None:
            img_name = generate_file_name(url, ".jpg")
        return await self.streamd(url, file_name=img_name, ext_headers=ext_headers)

    async def download_av_and_merge(
        self,
        v_url: str,
        a_url: str,
        output_path: Path,
        ext_headers: dict[str, str] | None = None,
    ) -> Path:
        """
        下载音频和视频文件并合并

        :param v_url: 视频流下载地址
        :param a_url: 音频流下载地址
        :param output_path: 合并后输出的文件路径
        :param ext_headers: 额外的请求头，会与默认请求头合并
        :return: 合并后的视频文件本地路径
        :raises DownloadException: 下载或合并过程中发生错误时抛出
        """
        v_path, a_path = await asyncio.gather(
            self.download_video(url=v_url, ext_headers=ext_headers),
            self.download_audio(url=a_url, ext_headers=ext_headers),
        )
        await merge_av(v_path=v_path, a_path=a_path, output_path=output_path)
        return output_path


DOWNLOADER: StreamDownloader = StreamDownloader()
