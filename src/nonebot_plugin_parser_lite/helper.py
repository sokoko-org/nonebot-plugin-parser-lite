from typing import Any, Literal
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
from .constants import EMOJI_MAP
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

        :param segments: 转发消息节点列表
        :param user_id: 用户ID
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
        file: Path | bytes,
    ) -> Image:
        """获取图片 Seg

        :param file: 图片资源
        """

        if isinstance(file, (bytes, bytearray, memoryview)):
            return Image(raw=file)

        return Image(raw=file.read_bytes()) if pconfig.use_base64 else Image(path=file)

    @staticmethod
    def record_seg(file: Path) -> Voice:
        """获取语音 Seg

        :param file: 语音文件
        """
        return Voice(raw=file.read_bytes()) if pconfig.use_base64 else Voice(path=file)

    @classmethod
    def video_seg(
        cls,
        file: Path,
        thumbnail: Path | None = None,
    ) -> Video | File | Text:
        """获取视频 Seg

        :param file: 视频路径
        :param thumbnail: 缩略图路径
        """
        # 检测文件大小
        file_size_byte_count = int(file.stat().st_size)
        if file_size_byte_count == 0:
            return Text("视频文件大小为 0")
        elif file_size_byte_count > 100 * 1024 * 1024:
            # 转为文件 Seg
            return cls.file_seg(file, display_name=file.name)
        else:
            if pconfig.use_base64:
                video = Video(raw=file.read_bytes())
                if thumbnail and thumbnail.stat().st_size > 0:
                    video.thumbnail = cls.img_seg(thumbnail.read_bytes())
            else:
                video = Video(path=file)
                if thumbnail and thumbnail.stat().st_size > 0:
                    video.thumbnail = cls.img_seg(thumbnail)

            return video

    @staticmethod
    def file_seg(
        file: Path,
        display_name: str | None = None,
    ) -> File:
        """获取文件 Seg

        :param file: 文件路径
        :param display_name: 显示名称
        """
        if not display_name:
            display_name = file.name
        if not display_name:
            raise ValueError("文件名不能为空")
        if pconfig.use_base64:
            return File(raw=file.read_bytes(), name=display_name)
        else:
            return File(path=file, name=display_name)

    @classmethod
    async def message_reaction(
        cls,
        event: Event,
        status: Literal["fail", "resolving", "done"],
    ) -> None:
        """发送消息回应

        :param event: 事件对象
        :param status: 状态
        """
        message_id = uniseg.get_message_id(event)
        target = uniseg.get_target(event)

        if target.adapter in (
            SupportAdapter.onebot11,
            SupportAdapter.qq,
            SupportAdapter.milky,
        ):
            emoji = EMOJI_MAP[status][0]
        else:
            emoji = EMOJI_MAP[status][1]

        try:
            await uniseg.message_reaction(emoji, message_id=message_id)
        except Exception:
            logger.warning(
                f"reaction {emoji} to {message_id} failed, maybe not support"
            )

    @classmethod
    def with_reaction(cls, func: Callable[..., Awaitable[Any]]):
        """自动回应装饰器

        自动处理消息响应状态，并捕获 TipException 发送提示消息

        :param func: 被装饰的函数
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
