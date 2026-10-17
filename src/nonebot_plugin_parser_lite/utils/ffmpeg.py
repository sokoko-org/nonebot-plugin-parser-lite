import asyncio
from asyncio.subprocess import Process
from collections.abc import Callable
from fractions import Fraction
import hashlib
import json
import math
from typing import Any
from uuid import uuid4
from weakref import WeakKeyDictionary

from anyio import Path

from ..config import pconfig
from ..constants import MIN_KEEP_PIECE_SECONDS
from ..exception import SizeLimitException
from .cache import CacheManager
from .common import fmt_size
from .log import logger

_TRANSCODE_LIMITS: WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.Semaphore
] = WeakKeyDictionary()


def get_transcode_limit() -> asyncio.Semaphore:
    """返回当前事件循环共享的转码信号量

    信号量不能跨事件循环复用，因此按事件循环缓存。懒下载发生在原消息处理
    结束后，也必须走同一份限制。
    """
    loop = asyncio.get_running_loop()
    cached = _TRANSCODE_LIMITS.get(loop)
    if cached is None:
        cached = asyncio.Semaphore(pconfig.media_transcode_concurrency)
        _TRANSCODE_LIMITS[loop] = cached
    return cached


class FFmpeg:
    _available: bool | None = None

    @classmethod
    def hash_filename(cls, *args: Path) -> str:
        """
        根据若干路径（或字符串）生成一个稳定的 MD5 文件名（不带扩展名）
        """
        parts = [arg.stem for arg in args]
        raw = ",".join(sorted(parts))
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def temporary_output_path(output_path: Path) -> Path:
        return output_path.with_name(
            f".{output_path.stem}.{uuid4().hex}.tmp{output_path.suffix}"
        )

    @classmethod
    async def exec_ffmpeg(cls, cmd: list[str], input: bytes | None = None) -> bytes:
        """执行 ffmpeg 命令

        :param cmd: 不包含 'ffmpeg' 本身的命令参数列表
        :param input: _description_, defaults to None

        :return: bytes
        """
        full_cmd = ["ffmpeg", *cmd]
        try:
            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate(input)
        except FileNotFoundError as e:
            raise RuntimeError("ffmpeg 未安装或无法找到可执行文件") from e

        if process.returncode != 0:
            error_msg = stderr.decode(errors="ignore").strip()
            raise RuntimeError(f"ffmpeg 执行失败: {error_msg}")
        return stdout

    @classmethod
    async def exec_ffmpeg_monitored(
        cls,
        cmd: list[str],
        output_path: Path,
        max_size_mb: int,
        on_progress: Callable[[int], None] | None = None,
    ) -> bytes:
        """执行 FFmpeg，并在输出文件超过上限时终止进程

        :param cmd: 不包含 'ffmpeg' 本身的命令参数列表
        :param output_path: 需要监视大小的输出文件路径
        :param max_size_mb: 最大大小 MB

        :return: bytes
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise RuntimeError("ffmpeg 未安装或无法找到可执行文件") from e

        communicate = asyncio.create_task(process.communicate())
        max_size_bytes = max_size_mb * 1024 * 1024
        try:
            while not communicate.done():
                await asyncio.sleep(0.1)
                if await output_path.exists():
                    size = (await output_path.stat()).st_size
                    if on_progress is not None:
                        on_progress(size)
                    if size > max_size_bytes:
                        await cls.stop_process(process, communicate)
                        raise SizeLimitException(size / 1024 / 1024)

            stdout, stderr = await communicate
        except BaseException:
            await cls.stop_process(process, communicate)
            raise

        if process.returncode != 0:
            error_msg = stderr.decode(errors="ignore").strip()
            raise RuntimeError(f"ffmpeg 执行失败: {error_msg}")
        if await output_path.exists():
            size = (await output_path.stat()).st_size
            if size > max_size_bytes:
                raise SizeLimitException(size / 1024 / 1024)
            if on_progress is not None:
                on_progress(size)
        return stdout

    @staticmethod
    async def stop_process(process: Process, communicate: asyncio.Task) -> None:
        if process.returncode is None:
            process.kill()
        if communicate.done():
            return
        await communicate

    @classmethod
    async def exec_probe(cls, cmd: list[str]) -> bytes:
        """执行 ffprobe 命令并返回标准输出

        :param cmd: 不包含 'ffprobe' 本身的命令参数列表
        """
        full_cmd = ["ffprobe", *cmd]
        try:
            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        except FileNotFoundError as e:
            raise RuntimeError("ffprobe 未安装或无法找到可执行文件") from e

        if process.returncode != 0:
            error_msg = stderr.decode(errors="ignore").strip()
            raise RuntimeError(f"ffprobe 执行失败: {error_msg}")
        return stdout

    @classmethod
    async def _is_mp3_audio(cls, audio_path: Path) -> bool:
        """检查首个音频流是否已经使用 MP3 编码"""
        try:
            stdout = await cls.exec_probe(
                [
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ]
            )
        except RuntimeError as e:
            logger.debug(f"检测音频编码失败，将继续转码: {audio_path}: {e}")
            return False
        return stdout.decode(errors="ignore").strip().casefold() == "mp3"

    @classmethod
    async def _probe_media(cls, media_path: Path) -> dict[str, Any]:
        """读取合成所需的媒体时长、帧率和流信息"""
        stdout = await cls.exec_probe(
            [
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream="
                "codec_type,duration,avg_frame_rate,r_frame_rate",
                "-of",
                "json",
                str(media_path),
            ]
        )

        try:
            return json.loads(stdout)
        except (TypeError, json.JSONDecodeError) as e:
            raise RuntimeError(f"ffprobe 返回了无效数据: {media_path}") from e

    @staticmethod
    def _get_duration(probe: dict[str, Any], media_path: Path) -> float:
        raw_duration = probe.get("format", {}).get("duration")
        try:
            duration = float(raw_duration)
        except (TypeError, ValueError):
            duration = 0

        if not math.isfinite(duration) or duration <= 0:
            raise RuntimeError(f"无法获取有效的媒体时长: {media_path}")
        return duration

    @staticmethod
    def _get_video_frame_rate(probe: dict[str, Any], video_path: Path) -> str:
        video_stream = next(
            (
                stream
                for stream in probe.get("streams", [])
                if stream.get("codec_type") == "video"
            ),
            None,
        )
        if video_stream is None:
            raise RuntimeError(f"未找到视频流: {video_path}")

        for key in ("avg_frame_rate", "r_frame_rate"):
            raw_rate = video_stream.get(key)
            try:
                if raw_rate and Fraction(raw_rate) > 0:
                    return str(raw_rate)
            except (ValueError, ZeroDivisionError):
                continue
        raise RuntimeError(f"无法获取有效的视频帧率: {video_path}")

    @staticmethod
    def _format_filter_number(value: float) -> str:
        return f"{value:.9f}".rstrip("0").rstrip(".")

    @staticmethod
    def _validate_live_loop(loop: int) -> None:
        if isinstance(loop, bool) or not isinstance(loop, int) or loop < 1:
            raise ValueError("loop 必须是大于等于 1 的整数")

    @classmethod
    async def _get_live_output_path(
        cls,
        image_path: Path,
        video_path: Path,
        bgm_path: Path | None,
        file_name: str | None,
        loop: int,
        has_bgm: bool,
    ) -> Path:
        if file_name is None:
            cache_key = ",".join(
                (
                    str(image_path),
                    str(video_path),
                    str(bgm_path) if has_bgm else "",
                    f"loop={loop}",
                )
            )
            file_name = hashlib.md5(cache_key.encode("utf-8")).hexdigest()

        cache_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
        return cache_dir / f"{file_name}.mp4"

    @staticmethod
    def _build_live_inputs(video_path: Path, image_path: Path, loop: int) -> list[str]:
        # 多读取一轮可避免部分可变帧率素材在末段 trim 时缺最后一帧
        return [
            "-stream_loop",
            str(loop),
            "-i",
            str(video_path),
            "-loop",
            "1",
            "-i",
            str(image_path),
        ]

    @classmethod
    def _build_live_filter(
        cls, duration: float, video_fps: str, loop: int
    ) -> tuple[list[str], float]:
        fade_duration = min(0.5, max(0.12, duration * 0.18))
        static_duration = 2.5
        filter_parts = cls._build_live_segments(
            duration, video_fps, static_duration, loop
        )
        composed_duration, last_label = cls._append_live_transitions(
            filter_parts, duration, static_duration, fade_duration, loop
        )
        filter_parts.append(f"[{last_label}]null[outv]")
        return filter_parts, composed_duration

    @classmethod
    def _build_live_segments(
        cls, duration: float, video_fps: str, static_duration: float, loop: int
    ) -> list[str]:
        filter_parts = [
            "[0:v]setpts=PTS-STARTPTS,settb=1/1000,"
            f"format=yuv420p,setsar=1,fps={video_fps}[vbase]",
            "[1:v]setpts=PTS-STARTPTS,settb=1/1000,"
            f"format=yuv420p,setsar=1,fps={video_fps}[still_base]",
        ]
        filter_parts.extend(cls._build_live_split_filters(loop))

        formatted_duration = cls._format_filter_number(duration)
        for index in range(loop):
            start = cls._format_filter_number(duration * index)
            filter_parts.extend(
                (
                    f"[vsplit{index}]trim=start={start}:duration={formatted_duration},"
                    f"setpts=PTS-STARTPTS,settb=1/1000[v{index}]",
                    f"[still{index}][v{index}]"
                    f"scale2ref=iw:ih:flags=lanczos[s{index}raw][v{index}r]",
                    f"[s{index}raw]trim=duration={static_duration},"
                    f"setpts=PTS-STARTPTS,settb=1/1000[s{index}]",
                )
            )
        return filter_parts

    @staticmethod
    def _build_live_split_filters(loop: int) -> tuple[str, str]:
        if loop == 1:
            return "[vbase]null[vsplit0]", "[still_base]null[still0]"

        split_labels = "".join(f"[vsplit{i}]" for i in range(loop))
        still_labels = "".join(f"[still{i}]" for i in range(loop))
        return (
            f"[vbase]split={loop}{split_labels}",
            f"[still_base]split={loop}{still_labels}",
        )

    @classmethod
    def _append_live_transitions(
        cls,
        filter_parts: list[str],
        duration: float,
        static_duration: float,
        fade_duration: float,
        loop: int,
    ) -> tuple[float, str]:
        formatted_fade = cls._format_filter_number(fade_duration)
        video_fade_offset = cls._format_filter_number(max(0, duration - fade_duration))
        last_label = "x_s0"
        filter_parts.append(
            f"[v0r][s0]xfade=transition=fade:duration={formatted_fade}:"
            f"offset={video_fade_offset}[{last_label}]"
        )
        composed_duration = duration + static_duration - fade_duration

        for index in range(1, loop):
            to_video_label = f"x_v{index}"
            to_still_label = f"x_s{index}"
            offset_to_video = cls._format_filter_number(
                max(0, composed_duration - fade_duration)
            )
            filter_parts.append(
                f"[{last_label}][v{index}r]xfade=transition=fade:"
                f"duration={formatted_fade}:offset={offset_to_video}"
                f"[{to_video_label}]"
            )
            composed_duration += duration - fade_duration
            offset_to_still = cls._format_filter_number(
                max(0, composed_duration - fade_duration)
            )
            filter_parts.append(
                f"[{to_video_label}][s{index}]xfade=transition=fade:"
                f"duration={formatted_fade}:offset={offset_to_still}"
                f"[{to_still_label}]"
            )
            composed_duration += static_duration - fade_duration
            last_label = to_still_label

        return composed_duration, last_label

    @classmethod
    async def _configure_live_audio(
        cls,
        inputs: list[str],
        filter_parts: list[str],
        bgm_path: Path | None,
        has_bgm: bool,
        composed_duration: float,
    ) -> tuple[list[str], list[str], list[str]]:
        if not has_bgm or bgm_path is None:
            return ["-map", "0:a?"], ["-c:a", "aac"], []

        bgm_probe = await cls._probe_media(bgm_path)
        bgm_duration = cls._get_duration(bgm_probe, bgm_path)
        if bgm_loop := max(0, math.ceil(composed_duration / bgm_duration) - 1):
            inputs.extend(("-stream_loop", str(bgm_loop)))
        inputs.extend(("-i", str(bgm_path)))
        filter_parts.append("[2:a]anull[outa]")
        return (
            ["-map", "[outa]"],
            ["-c:a", "aac", "-b:a", "192k"],
            ["-shortest"],
        )

    @staticmethod
    def _build_live_command(
        inputs: list[str],
        filter_parts: list[str],
        audio_map: list[str],
        audio_output: list[str],
        finish_mode: list[str],
        output_path: Path,
    ) -> list[str]:
        return [
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *inputs,
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[outv]",
            *audio_map,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            *audio_output,
            "-pix_fmt",
            "yuv420p",
            *finish_mode,
            "-movflags",
            "+faststart",
            str(output_path),
        ]

    @classmethod
    async def is_available(cls) -> bool:
        if cls._available is not None:
            return cls._available

        try:
            await cls.exec_ffmpeg(["-version"])
        except Exception:
            cls._available = False
        else:
            cls._available = True
        return cls._available

    @classmethod
    async def png_to_jpeg(cls, png_data: bytes) -> bytes:
        cmd = [
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "image2pipe",
            "-c:v",
            "mjpeg",
            "-q:v",
            "85",
            "pipe:1",
        ]
        return await cls.exec_ffmpeg(cmd, png_data)

    @classmethod
    async def png_to_webp(cls, png_data: bytes) -> bytes:
        """PNG to WebP"""
        cmd = [
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-frames:v",
            "1",
            "-f",
            "webp",
            "-c:v",
            "libwebp",
            "-lossless",
            "0",
            "-quality",
            "85",
            "pipe:1",
        ]
        return await cls.exec_ffmpeg(cmd, png_data)

    @classmethod
    async def remux_to_mp4(cls, input_path: Path, output_path: Path) -> Path:
        """
        将 ts / fmp4 等容器转封装为 mp4，不重编码
        """
        temp_path = cls.temporary_output_path(output_path)
        cmd = [
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-probesize",
            "50M",
            "-analyzeduration",
            "100M",
            "-i",
            str(input_path),
            "-c",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            str(temp_path),
        ]
        try:
            await cls.exec_ffmpeg(cmd)
            await temp_path.replace(output_path)
        finally:
            await temp_path.unlink(missing_ok=True)
        return output_path

    @classmethod
    async def download_hls_to_mp4(
        cls,
        url: str,
        output_path: Path,
        headers: dict[str, str] | None = None,
        max_size_mb: int = 90,
        on_progress: Callable[[int], None] | None = None,
    ) -> Path:
        """让 ffmpeg 处理加密、初始化段和字节范围等完整 HLS 语义。"""
        temp_path = cls.temporary_output_path(output_path)
        input_options: list[str] = []
        if headers:
            header_text = "\r\n".join(
                f"{key}: {value}" for key, value in headers.items()
            )
            input_options = ["-headers", f"{header_text}\r\n"]
        cmd = [
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *input_options,
            "-i",
            url,
            "-c",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            "-movflags",
            "+faststart",
            str(temp_path),
        ]
        try:
            await cls.exec_ffmpeg_monitored(
                cmd,
                output_path=temp_path,
                max_size_mb=max_size_mb,
                on_progress=on_progress,
            )
            await temp_path.replace(output_path)
        finally:
            await temp_path.unlink(missing_ok=True)
        return output_path

    @classmethod
    async def merge_av(
        cls, v_path: Path, a_path: Path, file_name: str | None = None
    ) -> Path:
        """合并视频和音频

        :param v_path: 视频文件路径
        :param a_path: 音频文件路径
        :param file_name: 输出文件名
        """
        file_name = file_name or cls.hash_filename(v_path, a_path)
        cache_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
        output_path = cache_dir / f"{file_name}.mp4"
        if await output_path.exists():
            return output_path
        logger.info(f"Merging {v_path.name} and {a_path.name} to {output_path.name}")

        temp_path = cls.temporary_output_path(output_path)
        cmd = [
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(v_path),
            "-i",
            str(a_path),
            # 纯封装层合并：不重编码，最快
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-movflags",
            "+faststart",  # 将 moov 前移，优化流式播放
            str(temp_path),
        ]
        try:
            await cls.exec_ffmpeg(cmd)
            await temp_path.replace(output_path)
        finally:
            await temp_path.unlink(missing_ok=True)
        logger.success(f"Merged {output_path.name}, {await fmt_size(output_path)}")
        return output_path

    @classmethod
    async def merge_to_live_mp4(
        cls,
        image_path: Path,
        video_path: Path,
        bgm_path: Path | None = None,
        file_name: str | None = None,
        loop: int = 1,
    ) -> Path:
        """
        合并图片和视频为 iPhone Live Photo 视频

        :param image_path: 图片文件路径
        :param video_path: 视频文件路径
        :param bgm_path: 背景音乐文件路径
        :param file_name: 输出文件名
        :param loop: 视频与静态图组合的循环次数
        """
        cls._validate_live_loop(loop)
        has_bgm = bool(bgm_path and await bgm_path.exists())
        output_path = await cls._get_live_output_path(
            image_path, video_path, bgm_path, file_name, loop, has_bgm
        )
        if await output_path.exists():
            return output_path

        input_names = f"{image_path.name} and {video_path.name}"
        if has_bgm and bgm_path:
            input_names += f" with {bgm_path.name}"
        logger.info(
            f"Creating Live Photo video from {input_names} to {output_path.name}, "
            f"loop={loop}"
        )

        video_probe = await cls._probe_media(video_path)
        duration = cls._get_duration(video_probe, video_path)
        video_fps = cls._get_video_frame_rate(video_probe, video_path)
        inputs = cls._build_live_inputs(video_path, image_path, loop)
        filter_parts, composed_duration = cls._build_live_filter(
            duration, video_fps, loop
        )
        audio_options = await cls._configure_live_audio(
            inputs, filter_parts, bgm_path, has_bgm, composed_duration
        )
        temp_path = cls.temporary_output_path(output_path)
        cmd = cls._build_live_command(inputs, filter_parts, *audio_options, temp_path)
        try:
            await cls.exec_ffmpeg(cmd)
            await temp_path.replace(output_path)
        finally:
            await temp_path.unlink(missing_ok=True)
        logger.success(
            f"Created Live Photo video {output_path.name}, "
            f"{await fmt_size(output_path)}"
        )
        return output_path

    @classmethod
    async def _get_edit_output_path(
        cls, input_path: Path, suffix: str, *params: Any
    ) -> Path:
        """按源路径与编辑参数算出产物名，参数变了就不会命中旧产物"""
        cache_key = ",".join([str(input_path), *(str(param) for param in params)])
        file_name = hashlib.md5(cache_key.encode("utf-8")).hexdigest()
        cache_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
        return cache_dir / f"{file_name}{suffix}"

    @staticmethod
    def _build_keep_pieces(
        cut_ranges: tuple[tuple[float, float], ...],
        duration: float,
    ) -> list[tuple[float, float]]:
        """把「要删掉的区间」换算成「要保留的区间」，入参需已排序且不重叠"""
        pieces: list[tuple[float, float]] = []
        cursor = 0.0
        for start, end in cut_ranges:
            if start > cursor:
                pieces.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < duration:
            pieces.append((cursor, duration))
        return [
            (start, end)
            for start, end in pieces
            if end - start > MIN_KEEP_PIECE_SECONDS
        ]

    @classmethod
    def _build_mute_expression(
        cls, mute_ranges: tuple[tuple[float, float], ...]
    ) -> str:
        terms = [
            f"between(t,{cls._format_filter_number(start)},"
            f"{cls._format_filter_number(end)})"
            for start, end in mute_ranges
        ]
        return "+".join(terms)

    @classmethod
    def _build_timeline_filter(
        cls,
        pieces: list[tuple[float, float]],
        mute_ranges: tuple[tuple[float, float], ...],
        *,
        has_audio: bool,
    ) -> tuple[list[str], str, str | None]:
        """裁切并拼接保留区间

        消音表达式在 split 之前作用于原始时间轴，因此消音区间不需要随裁切
        重新映射。音频只取第一条流，多轨产物在 IM 侧基本只有第一条会被播。

        :return: (滤镜片段, 视频输出标签, 音频输出标签)
        """
        count = len(pieces)
        parts: list[str] = []

        if count == 1:
            parts.append("[0:v]null[vc0]")
        else:
            labels = "".join(f"[vc{i}]" for i in range(count))
            parts.append(f"[0:v]split={count}{labels}")

        audio_source = "0:a"
        if has_audio and mute_ranges:
            enable = cls._build_mute_expression(mute_ranges)
            parts.append(f"[0:a]volume=enable='{enable}':volume=0[am]")
            audio_source = "am"

        if has_audio:
            if count == 1:
                parts.append(f"[{audio_source}]anull[ac0]")
            else:
                audio_labels = "".join(f"[ac{i}]" for i in range(count))
                parts.append(f"[{audio_source}]asplit={count}{audio_labels}")

        for index, (start, end) in enumerate(pieces):
            left = cls._format_filter_number(start)
            right = cls._format_filter_number(end)
            parts.append(
                f"[vc{index}]trim=start={left}:end={right},"
                f"setpts=PTS-STARTPTS[v{index}]"
            )
            if has_audio:
                parts.append(
                    f"[ac{index}]atrim=start={left}:end={right},"
                    f"asetpts=PTS-STARTPTS[a{index}]"
                )

        joined = "".join(
            f"[v{i}]" + (f"[a{i}]" if has_audio else "") for i in range(count)
        )
        if has_audio:
            parts.append(f"{joined}concat=n={count}:v=1:a=1[vt][at]")
            return parts, "[vt]", "[at]"
        parts.append(f"{joined}concat=n={count}:v=1:a=0[vt]")
        return parts, "[vt]", None

    @classmethod
    async def edit_video(
        cls,
        input_path: Path,
        *,
        speed_ratio: float = 1.0,
        cut_ranges: tuple[tuple[float, float], ...] = (),
        mute_ranges: tuple[tuple[float, float], ...] = (),
    ) -> Path:
        """重编码视频，一次 ffmpeg 调用产出终态文件

        倍速、裁切、消音可以同时传，落在同一条滤镜链里，避免多代有损编码；只消音
        时视频流直接复制。产物名由源路径与编辑参数算出，命中缓存即复用。

        :param input_path: 源视频路径
        :param speed_ratio: 播放倍率
        :param cut_ranges: 需要删除的时间轴区间，需已排序、裁剪且不重叠
        :param mute_ranges: 需要消音的时间轴区间，按源时间轴表达
        :return: 产物路径
        """
        output_path = await cls._get_edit_output_path(
            input_path, ".mp4", speed_ratio, cut_ranges, mute_ranges
        )
        if await output_path.exists():
            return output_path

        probe = await cls._probe_media(input_path)
        duration = cls._get_duration(probe, input_path)
        has_audio = any(
            stream.get("codec_type") == "audio" for stream in probe.get("streams", [])
        )

        pieces = (
            cls._build_keep_pieces(cut_ranges, duration)
            if cut_ranges
            else [(0.0, duration)]
        )
        if not pieces:
            raise RuntimeError("裁切后没有剩余片段")
        # 裁掉开头或结尾时只剩一个片段，但仍然要裁，不能拿「片段数 > 1」当判据
        needs_trim = bool(cut_ranges)

        filter_parts: list[str] = []
        # 滤镜图里引用输入流要带方括号，-map 直接引用输入流时不带
        video_source, video_target = "[0:v]", "0:v"
        audio_source = "[0:a]" if has_audio else None
        audio_target = "0:a" if has_audio else None

        if needs_trim:
            filter_parts, video_target, audio_target = cls._build_timeline_filter(
                pieces, mute_ranges, has_audio=has_audio
            )
            video_source, audio_source = video_target, audio_target
        elif has_audio and mute_ranges:
            enable = cls._build_mute_expression(mute_ranges)
            filter_parts.append(f"[0:a]volume=enable='{enable}':volume=0[at]")
            audio_source = audio_target = "[at]"

        video_filtered = needs_trim or speed_ratio != 1.0
        if speed_ratio != 1.0:
            ratio = cls._format_filter_number(speed_ratio)
            filter_parts.append(f"{video_source}setpts=PTS/{ratio}[vf]")
            video_source = video_target = "[vf]"
            if audio_source is not None:
                filter_parts.append(f"{audio_source}atempo={ratio}[af]")
                audio_source = audio_target = "[af]"

        cmd: list[str] = ["-y", "-hide_banner", "-loglevel", "error"]
        cmd += ["-i", str(input_path)]
        if filter_parts:
            cmd += ["-filter_complex", ";".join(filter_parts)]
        cmd += ["-map", video_target]
        if video_filtered:
            cmd += [
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
            ]
        else:
            cmd += ["-c:v", "copy"]
        if audio_target is None:
            cmd += ["-an"]
        else:
            cmd += ["-map", audio_target]
            cmd += (
                ["-c:a", "copy"]
                if audio_target == "0:a"
                else ["-c:a", "aac", "-b:a", "192k"]
            )
        logger.info(f"Editing video '{input_path.name}' as '{output_path.name}'")
        temp_path = cls.temporary_output_path(output_path)
        cmd += ["-movflags", "+faststart", str(temp_path)]
        try:
            await cls.exec_ffmpeg_monitored(
                cmd, output_path=temp_path, max_size_mb=pconfig.max_size
            )
            await temp_path.replace(output_path)
        finally:
            await temp_path.unlink(missing_ok=True)
        logger.success(
            f"Edited video {output_path.name}, size={await fmt_size(output_path)}"
        )
        return output_path

    @classmethod
    async def edit_audio(
        cls,
        input_path: Path,
        *,
        speed_ratio: float,
    ) -> Path:
        """按倍率重编码音频，产物沿用源文件的容器

        音频只处理倍速，裁切与消音是画面时间轴上的概念；``-vn`` 会连内嵌封面
        一起去掉，语音/文件消息用不到它。

        :param input_path: 源音频路径
        :param speed_ratio: 播放倍率
        :return: 产物路径
        """
        suffix = input_path.suffix.lower() or ".m4a"
        output_path = await cls._get_edit_output_path(input_path, suffix, speed_ratio)
        if await output_path.exists():
            return output_path

        cmd: list[str] = ["-y", "-hide_banner", "-loglevel", "error"]
        cmd += [
            "-i",
            str(input_path),
            "-vn",
            "-af",
            f"atempo={cls._format_filter_number(speed_ratio)}",
        ]
        # 编码器与码率交给 ffmpeg 按输出后缀决定
        logger.info(f"Editing audio '{input_path.name}' as '{output_path.name}'")
        temp_path = cls.temporary_output_path(output_path)
        cmd += [str(temp_path)]
        try:
            await cls.exec_ffmpeg_monitored(
                cmd, output_path=temp_path, max_size_mb=pconfig.max_size
            )
            await temp_path.replace(output_path)
        finally:
            await temp_path.unlink(missing_ok=True)
        logger.success(
            f"Edited audio {output_path.name}, size={await fmt_size(output_path)}"
        )
        return output_path

    @classmethod
    async def convert_to_mp3(
        cls, audio_path: Path, file_name: str | None = None
    ) -> Path:
        """
        将任意音视频文件转码为 mp3

        :param audio_path: 输入音频文件路径
        :param file_name: 输出文件名（不含扩展名），为空时根据输入路径生成稳定名称
        :return: 转码后的 mp3 文件路径
        """
        if audio_path.suffix.casefold() == ".mp3" and await cls._is_mp3_audio(
            audio_path
        ):
            return audio_path

        file_name = file_name or cls.hash_filename(audio_path)
        cache_dir = await CacheManager.ensure_dir(CacheManager.MEDIA)
        output_path = cache_dir / f"{file_name}.mp3"
        replaces_input = output_path == audio_path

        if not replaces_input and await output_path.exists():
            return output_path
        if replaces_input and await cls._is_mp3_audio(audio_path):
            return audio_path

        ffmpeg_output_path = cls.temporary_output_path(output_path)

        logger.info(
            f"Converting audio '{audio_path.name}' to mp3 as '{output_path.name}'"
        )

        cmd = [
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(audio_path),
            "-vn",  # 明确丢弃视频流（若有）
            "-acodec",
            "libmp3lame",  # 使用 mp3 编码器
            str(ffmpeg_output_path),
        ]

        try:
            await cls.exec_ffmpeg(cmd)
            await ffmpeg_output_path.replace(output_path)
        finally:
            await ffmpeg_output_path.unlink(missing_ok=True)
        logger.success(
            f"Converted to mp3: {output_path.name}, size={await fmt_size(output_path)}"
        )
        return output_path
