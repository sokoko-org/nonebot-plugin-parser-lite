from typing import Any, Literal, ClassVar
from pathlib import Path
from functools import wraps
from collections.abc import Callable, Sequence, Awaitable

from nonebot import logger
from nonebot.matcher import current_bot, current_event
from nonebot.adapters import Event
from nonebot_plugin_alconna import SupportAdapter, uniseg
from nonebot_plugin_alconna.uniseg import (
    File,
    Text,
    Image,
    Video,
    Voice,
    Segment,
    Reference,
    CustomNode,
    UniMessage,
)

from .config import pconfig

# from .exception import TipException

ForwardNodeInner = str | Segment | UniMessage
"""转发消息节点内部允许的类型"""


class UniHelper:
    @staticmethod
    def construct_forward_message(
        segments: Sequence[ForwardNodeInner],
        user_id: str | None = None,
    ) -> Reference:
        """构造转发消息

        Args:
            user_id (str): 用户ID
            segments (Sequence[ForwardNode]): 消息段

        Returns:
            Reference: 转发消息
        """
        if user_id is None:
            user_id = current_bot.get().self_id
        nodes = []
        for seg in segments:
            if isinstance(seg, str):
                content = UniMessage([Text(seg)])
            elif isinstance(seg, Segment):
                content = UniMessage([seg])
            else:
                content = seg
            node = CustomNode(uid=user_id, name=pconfig.nickname, content=content)
            nodes.append(node)

        return Reference(nodes=nodes)

    @staticmethod
    def img_seg(
        img_path: Path | None = None,
        raw: bytes | None = None,
    ) -> Image:
        """获取图片 Seg

        Args:
            img_path (Path): 图片路径

        Returns:
            Image: 图片 Seg
        """

        if raw is not None:
            return Image(raw=raw)

        if img_path is None:
            raise ValueError("img_path 和 raw 不能都为 None")

        if pconfig.use_base64:
            return Image(raw=img_path.read_bytes())
        else:
            return Image(path=img_path)

    @staticmethod
    def record_seg(audio_path: Path) -> Voice:
        """获取语音 Seg

        Args:
            audio_path (Path): 语音路径

        Returns:
            Voice: 语音 Seg
        """
        if pconfig.use_base64:
            return Voice(raw=audio_path.read_bytes())
        else:
            return Voice(path=audio_path)

    @classmethod
    def video_seg(cls, video_path: Path) -> Video | File | Text:
        """获取视频 Seg

        Returns:
            Video | File | Text: 视频 Seg
        """
        # 检测文件大小
        file_size_byte_count = int(video_path.stat().st_size)
        if file_size_byte_count == 0:
            return Text("视频文件大小为 0")
        elif file_size_byte_count > 100 * 1024 * 1024:
            # 转为文件 Seg
            return cls.file_seg(video_path, display_name=video_path.name)
        else:
            if pconfig.use_base64:
                return Video(raw=video_path.read_bytes())
            else:
                return Video(path=video_path)

    @staticmethod
    def file_seg(
        file: Path,
        display_name: str | None = None,
    ) -> File:
        """获取文件 Seg

        Args:
            file (Path): 文件路径
            display_name (str): 显示名称. Defaults to file.name.

        Returns:
            File: 文件 Seg
        """
        if not display_name:
            display_name = file.name
        if not display_name:
            raise ValueError("文件名不能为空")
        if pconfig.use_base64:
            return File(raw=file.read_bytes(), name=display_name)
        else:
            return File(path=file, name=display_name)

    EMOJI_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        "fail": ("10060", "❌"),
        "resolving": ("424", "👀"),
        "done": ("144", "🎉"),
    }

    @classmethod
    async def message_reaction(
        cls,
        event: Event,
        status: Literal["fail", "resolving", "done"],
    ):
        """发送消息回应

        Args:
            event (Event): 事件对象
            status (Literal["fail", "resolving", "done"]): 状态
        """
        message_id = uniseg.get_message_id(event)
        target = uniseg.get_target(event)

        if target.adapter in (SupportAdapter.onebot11, SupportAdapter.qq):
            emoji = cls.EMOJI_MAP[status][0]
        else:
            emoji = cls.EMOJI_MAP[status][1]

        try:
            await uniseg.message_reaction(emoji, message_id=message_id)
        except Exception:
            logger.warning(f"reaction {emoji} to {message_id} failed, maybe not support")

    @classmethod
    def with_reaction(cls, func: Callable[..., Awaitable[Any]]):
        """自动回应装饰器

        自动处理消息响应状态，并捕获 TipException 发送提示消息

        Args:
            func: 被装饰的函数

        Returns:
            装饰后的函数
        """

        @wraps(func)
        async def wrapper(*args, **kwargs):
            event = current_event.get()
            await cls.message_reaction(event, "resolving")

            try:
                result = await func(*args, **kwargs)
            # except TipException as e:
            #     await UniMessage.text(e.message).send()
            #     raise
            except Exception:
                await cls.message_reaction(event, "fail")
                raise

            await cls.message_reaction(event, "done")
            return result

        return wrapper
