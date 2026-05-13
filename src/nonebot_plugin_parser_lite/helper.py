from collections.abc import Awaitable, Callable, Sequence
from functools import wraps
from typing import Any, Literal

from anyio import Path
from nonebot import logger
from nonebot.adapters import Event
from nonebot.matcher import current_bot, current_event
from nonebot_plugin_alconna import SupportAdapter, uniseg
from nonebot_plugin_alconna.uniseg import (
    CustomNode,
    File,
    Image,
    Reference,
    Segment,
    Text,
    UniMessage,
    Video,
    Voice,
)

from .config import pconfig
from .constants import EMOJI_MAP
from .exception import TipException

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
    async def img_seg(
        file: Path | bytes,
    ) -> Image:
        """获取图片 Seg

        :param file: 图片资源
        """

        if isinstance(file, (bytes, bytearray, memoryview)):
            return Image(raw=file)

        return (
            Image(raw=await file.read_bytes())
            if pconfig.use_base64
            else Image(path=str(file))
        )

    @staticmethod
    async def record_seg(file: Path) -> Voice:
        """获取语音 Seg

        :param file: 语音文件
        """
        return (
            Voice(raw=await file.read_bytes())
            if pconfig.use_base64
            else Voice(path=str(file))
        )

    @classmethod
    async def video_seg(
        cls,
        file: Path,
        thumbnail: Path | None = None,
    ) -> Video | File | Text:
        """获取视频 Seg

        :param file: 视频路径
        :param thumbnail: 缩略图路径
        """
        # 检测文件大小
        stat = await file.stat()
        file_size_byte_count = stat.st_size
        if file_size_byte_count == 0:
            return Text("视频文件大小为 0")

        # 超过 100MB，转为文件 Seg
        if file_size_byte_count > 100 * 1024 * 1024:
            return await cls.file_seg(file, display_name=file.name)

        # 构造 Video，对 base64 与路径模式统一一个逻辑分支
        if pconfig.use_base64:
            video = Video(raw=await file.read_bytes())
        else:
            video = Video(path=str(file))

        # 处理缩略图：只做一次 stat，避免重复 IO
        if thumbnail is not None:
            thumb_stat = await thumbnail.stat()
            if thumb_stat.st_size > 0:
                # img_seg 已经内部处理 base64 / path，不需要重复判断
                video.thumbnail = await cls.img_seg(thumbnail)

        return video

    @staticmethod
    async def file_seg(
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
            return File(raw=await file.read_bytes(), name=display_name)
        else:
            return File(path=str(file), name=display_name)

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
                await func(*args, **kwargs)
            except TipException as e:
                await UniMessage.text(e.message).send()
                await cls.message_reaction(event, "fail")
            except Exception:
                await cls.message_reaction(event, "fail")
                raise
            else:
                await cls.message_reaction(event, "done")
            return

        return wrapper
