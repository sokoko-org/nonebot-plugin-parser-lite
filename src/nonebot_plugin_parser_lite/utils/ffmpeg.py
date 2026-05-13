import asyncio
import hashlib

from anyio import Path
from nonebot import logger

from ..config import pconfig
from .common import fmt_size, safe_unlink


class FFmpeg:
    @classmethod
    def generate_file_name(cls, *args: Path) -> str:
        """
        根据若干路径（或字符串）生成一个稳定的 MD5 文件名（不带扩展名）
        """
        parts = [arg.stem for arg in args]
        raw = ",".join(sorted(parts))
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    @classmethod
    async def exec_ffmpeg(cls, cmd: list[str]) -> None:
        """执行 ffmpeg 命令

        :param cmd: 不包含 'ffmpeg' 本身的命令参数列表
        """
        full_cmd = ["ffmpeg", *cmd]
        try:
            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
        except FileNotFoundError as e:
            raise RuntimeError("ffmpeg 未安装或无法找到可执行文件") from e

        if process.returncode != 0:
            error_msg = stderr.decode(errors="ignore").strip()
            raise RuntimeError(f"ffmpeg 执行失败: {error_msg}")

    @classmethod
    async def merge_av(
        cls, v_path: Path, a_path: Path, file_name: str | None = None
    ) -> Path:
        """合并视频和音频

        :param v_path: 视频文件路径
        :param a_path: 音频文件路径
        :param file_name: 输出文件名
        """
        file_name = file_name or cls.generate_file_name(v_path, a_path)
        output_path = pconfig.cache_dir / f"{file_name}.mp4"
        if output_path.exists():
            return output_path
        logger.info(f"Merging {v_path.name} and {a_path.name} to {output_path.name}")

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
            str(output_path),
        ]

        await cls.exec_ffmpeg(cmd)
        await asyncio.gather(safe_unlink(v_path), safe_unlink(a_path))
        logger.success(f"Merged {output_path.name}, {fmt_size(output_path)}")
        return output_path

    @classmethod
    async def merge_av_h264(
        cls, v_path: Path, a_path: Path, file_name: str | None = None
    ) -> Path:
        """合并视频和音频，并使用 H.264 编码

        :param v_path: 视频文件路径
        :param a_path: 音频文件路径
        :param file_name: 输出文件名
        """
        file_name = file_name or cls.generate_file_name(v_path, a_path)
        output_path = pconfig.cache_dir / f"{file_name}.mp4"
        if output_path.exists():
            return output_path
        logger.info(
            f"Merging {v_path.name} and {a_path.name} to {output_path.name} with H.264"
        )

        # 修改命令以确保视频使用 H.264 编码
        cmd = [
            "-y",
            "-i",
            str(v_path),
            "-i",
            str(a_path),
            "-c:v",
            "libx264",  # 明确指定使用 H.264 编码
            "-preset",
            "medium",  # 编码速度和质量的平衡
            "-crf",
            "23",  # 质量因子，值越低质量越高
            "-c:a",
            "aac",  # 音频使用 AAC 编码
            "-b:a",
            "128k",  # 音频比特率
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            str(output_path),
        ]

        await cls.exec_ffmpeg(cmd)
        await asyncio.gather(safe_unlink(v_path), safe_unlink(a_path))
        logger.success(f"Merged {output_path.name} with H.264, {fmt_size(output_path)}")
        return output_path

    @classmethod
    async def encode_video_to_h264(cls, video_path: Path) -> Path:
        """将视频重新编码到 h264

        :param video_path: 视频路径

        :return: 编码后的视频路径
        """
        output_path = video_path.with_name(f"{video_path.stem}_h264{video_path.suffix}")
        if output_path.exists():
            return output_path
        cmd = [
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            # 保留原始音频（如果有）
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        await cls.exec_ffmpeg(cmd)
        logger.success(
            f"视频重新编码为 H.264 成功: {output_path}, {fmt_size(output_path)}"
        )
        await safe_unlink(video_path)
        return output_path

    @classmethod
    async def merge_to_live_mp4(
        cls,
        image_path: Path,
        video_path: Path,
        bgm_path: Path | None = None,
        file_name: str | None = None,
    ):
        """
        合并图片和视频为 iPhone Live Photo 视频

        :param image_path: 图片文件路径
        :param video_path: 视频文件路径
        :param bgm_path: 背景音乐文件路径
        :param file_name: 输出文件名
        """
        file_name = file_name or cls.generate_file_name(image_path, video_path)
        output_path = pconfig.cache_dir / f"{file_name}.mp4"
        if output_path.exists():
            return output_path
        # 2. 构建指令：单进程一次性完成
        # 逻辑：视频 + 底图(0.6s) + 淡入
        inputs = [
            "-i",
            str(video_path),
            "-loop",
            "1",
            "-t",
            "0.6",
            "-i",
            str(image_path),
        ]

        # 模拟 iPhone 质感的核心滤镜：
        # - 主视频作为参考尺寸
        # - 静态图用 scale2ref 缩放到与主视频一致
        # - 对静态图做淡入，再与主视频 concat
        #
        # 这样可以避免手动算尺寸导致 concat 报尺寸不一致。
        filter_v = (
            "[1:v][0:v]scale2ref=flags=bicubic[v_still_raw][v_main];"
            "[v_still_raw]setsar=1,"
            "fade=t=in:st=0:d=0.2[v_still];"
            "[v_main]setsar=1[v_main_sar];"
            "[v_still][v_main_sar]concat=n=2:v=1:a=0[outv]"
        )

        if bgm_path and bgm_path.exists():
            inputs += ["-i", str(bgm_path)]
            # amix: 混合原音与BGM，duration=first 保证不因BGM太长而导致视频变长
            filter_a = ";[0:a][2:a]amix=inputs=2:duration=first[outa]"
            audio_map = ["-map", "[outa]"]
        else:
            filter_a = ""
            audio_map = ["-map", "0:a?"]

        cmd = [
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *inputs,
            "-filter_complex",
            filter_v + filter_a,
            "-map",
            "[outv]",
            *audio_map,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",  # 从 ultrafast 调回一点，画质更稳，CPU 仍较低
            "-tune",
            "stillimage",
            "-crf",
            "20",  # 保证底图文字清晰度
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

        await cls.exec_ffmpeg(cmd)
        return output_path
