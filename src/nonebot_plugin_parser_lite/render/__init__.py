import datetime
import traceback
import uuid
from collections.abc import AsyncGenerator
from io import BytesIO
from itertools import chain
from pathlib import Path
from typing import Any, ClassVar

import aiofiles
import qrcode
from nonebot import logger
from nonebot_plugin_htmlrender import template_to_pic

from ..config import _nickname, pconfig
from ..exception import DownloadException, DownloadLimitException
from ..helper import ForwardNodeInner, UniHelper, UniMessage
from ..parsers.data import (
    AudioContent,
    GraphicContent,
    ImageContent,
    LivePhotoContent,
    MediaContent,
    ParseResult,
    VideoContent,
)


async def safe_path(obj: Any, method: str = "get_path") -> str:
    """
    通用安全路径获取过滤器

    用法：
        {{ cont | safe_path }}                    # 默认调用 get_path()
        {{ cont | safe_path("get_base") }}        # 调用 get_base()
        {{ cont | safe_path("get_cover_path") }}  # 调用 get_cover_path()
        {{ author | safe_path("get_avatar_path") }} # 调用 get_avatar_path()
    """
    try:
        # 检查对象是否有指定方法
        if not hasattr(obj, method):
            logger.warning(f"Object {type(obj).__name__} has no method '{method}'")
            return ""

        # 获取方法并调用
        method_func = getattr(obj, method)
        src = method_func()

        # 如果是 coroutine，需要 await
        if hasattr(src, "__await__"):
            src = await src

        # 处理 None 或空值
        if not src:
            return ""

        # 自动执行 as_uri() 转换
        if isinstance(src, Path) or hasattr(src, "as_uri"):
            return src.as_uri()

        # 已经是字符串，直接返回
        return str(src)

    except Exception as e:
        logger.warning(f"safe_path({method}) failed for {type(obj).__name__}: {e}")
        return ""


class Renderer:
    """统一的渲染器，将解析结果转换为消息"""

    templates_dir: ClassVar[Path] = Path(__file__).parent / "templates"
    """模板目录"""

    async def render_messages(self, result: ParseResult) -> UniMessage[Any]:
        """渲染消息

        :param result: 解析结果
        """
        # 尝试获取图片路径，以便在直接发送失败时使用文件发送
        try:
            # 复用 cache_or_render_image 方法获取图片段，同时确保图片已保存
            image_seg = await self.cache_or_render_image(result)
            # 获取图片路径
        except Exception:
            logger.error(f"获取图片路径失败: {traceback.format_exc()}")
            image_seg = None

        # 尝试直接发送图片
        msg = UniMessage(image_seg or "图片渲染失败")
        if self.append_url:
            urls = (result.display_url, result.repost_display_url)
            msg += "\n".join(url for url in urls if url)
        return msg

    async def send_content(
        self, result: ParseResult
    ) -> AsyncGenerator[UniMessage[Any], None]:
        """发送媒体内容消息。

        将解析结果中的媒体内容拆分为：
        - 需要立即发送的音视频（逐条 yield）
        - 可合并转发的图文 / 图片（统一收集后一次发送）
        """
        forwardable_segs: list[ForwardNodeInner] = []
        failed_count = 0
        repost_medias = result.repost.content if result.repost else []
        media_contents = [
            cont
            for cont in chain(result.content, repost_medias)
            if isinstance(cont, MediaContent) and cont.need_send
        ]
        for cont in media_contents:
            # 先处理需要立即发送的音视频
            try:
                async for msg in self._handle_immediate_media(cont):
                    yield msg
            except DownloadLimitException as e:
                yield UniMessage(str(e))
                continue
            except DownloadException:
                failed_count += 1
                continue

            # 再尝试构建可转发的图文 / 图片片段
            try:
                seg = await self._build_forwardable_segment(cont)
            except DownloadException:
                failed_count += 1
                continue

            if seg:
                forwardable_segs.extend(seg)

        # 处理图文转发部分
        if forwardable_segs:
            # 根据“当前 + 转发”的文本/媒体顺序构建完整列表
            ordered_segs = self._build_ordered_forward_segs(result, forwardable_segs)

            if pconfig.need_forward_contents or len(ordered_segs) > 4:
                forward_msg = UniHelper.construct_forward_message(ordered_segs)
                yield UniMessage(forward_msg)
            else:
                yield UniMessage(ordered_segs)

        # 汇总下载失败信息
        if failed_count > 0:
            message = f"{failed_count} 项媒体下载失败"
            yield UniMessage(message)
            raise DownloadException(message)

    async def _handle_immediate_media(
        self, cont: MediaContent
    ) -> AsyncGenerator[UniMessage[Any], None]:
        """
        处理需要立即发送的音视频媒体，返回对应的消息段

        :raises ZeroSizeException: 资源大小为 0 时抛出
        :raises SizeLimitException: 资源大小超过配置的最大限制时抛出
        :raises DownloadException: 重试多次仍失败时抛出
        """
        if not isinstance(cont, (VideoContent, AudioContent)):
            return

        path = await cont.get_path()
        logger.debug(f"立即发送{type(cont).__name__}: {path}")

        if (
            isinstance(cont, VideoContent)
            and pconfig.need_upload_video
            or not isinstance(cont, VideoContent)
            and isinstance(cont, AudioContent)
            and pconfig.need_upload_audio
        ):
            yield UniMessage(UniHelper.file_seg(path))
        elif isinstance(cont, VideoContent):
            yield UniMessage(UniHelper.video_seg(path))
        elif isinstance(cont, AudioContent):
            yield UniMessage(UniHelper.record_seg(path))

    async def _build_forwardable_segment(
        self, cont: MediaContent
    ) -> list[ForwardNodeInner]:
        """构建可加入转发消息的片段（图片 / 图文 / LivePhoto）。"""

        # 视频封面
        if isinstance(cont, VideoContent):
            try:
                path = await cont.get_cover_path()
            except Exception as e:
                logger.warning(
                    f"get_cover_path() failed for {type(cont).__name__}: {e}"
                )
                return []
            return [UniHelper.img_seg(path)] if path else []
        # 图片
        if isinstance(cont, ImageContent):
            path = await cont.get_path()
            return [UniHelper.img_seg(path)]

        # 图文：图片 + 可选文字说明
        if isinstance(cont, GraphicContent):
            path = await cont.get_path()
            seg: ForwardNodeInner = UniHelper.img_seg(path)
            if cont.alt:
                seg = seg + cont.alt
            return [seg]

        # Live Photo：根据配置决定用视频还是图+视频
        if isinstance(cont, LivePhotoContent):
            if pconfig.live_photo:
                live_path = await cont.get_live()
                return [UniHelper.video_seg(live_path)]
            base_path = await cont.get_base()
            live_path = await cont.get_path()
            return [
                UniHelper.img_seg(base_path),
                UniHelper.video_seg(live_path),
            ]

        return []

    def _build_ordered_forward_segs(
        self,
        result: ParseResult,
        media_segs: list[ForwardNodeInner],
    ) -> list[ForwardNodeInner]:
        """根据当前内容和转发内容构造有序的转发段列表。

        顺序：
        1. 当前帖子的纯文本（作者：文本）
        2. 当前帖子的所有媒体片段
        3. 若有转发：
           3.1 一条“作者[转发原作者]：当前文本”说明
           3.2 原帖文本（原作者[被转作者]：原帖标题+内容）
        """
        ordered: list[ForwardNodeInner] = []
        author_name = result.author.name if result.author else "未知用户"

        # 1. 当前文本
        if plain := "".join(
            f"\n{c}" for c in result.content if isinstance(c, str) and c
        ):
            ordered.append(f"{author_name}：{plain}")

        # 2. 当前媒体
        ordered.extend(media_segs)

        # # 3. 转发内容
        # if not result.repost:
        #     return ordered

        # repost = result.repost
        # repost_author = repost.author.name if repost.author else "未知用户"

        # # 3.1 当前作者带“转发”说明 + 自己的文字
        # current_plain = build_plain_text(list(result.content))
        # ordered.append(f"{repost_author}[转发{author_name}]：{current_plain}")

        # # 3.2 原帖文字：标题 + 内容
        # repost_text_parts: list[str] = []
        # if repost.title:
        #     repost_text_parts.append(repost.title)
        # if plain_repost := build_plain_text(list(repost.content)):
        #     repost_text_parts.append(plain_repost)
        # if repost_text_parts:
        #     repost_text = "\n".join(repost_text_parts)
        #     ordered.append(f"{repost_author}[被转作者]：{repost_text}")

        return ordered

    @property
    def append_url(self) -> bool:
        return pconfig.append_url

    @property
    def append_qrcode(self) -> bool:
        return pconfig.append_qrcode

    async def render_image(self, result: ParseResult) -> bytes:
        """使用 HTML 绘制通用社交媒体帖子卡片"""
        # 准备模板数据
        template_data = await self._resolve_parse_result(result)

        # 处理模板针对
        template_name = "default.html.jinja"
        if result.platform:
            # 音乐平台使用音乐模板
            music_platforms = ["kugou", "netease", "kuwo", "qsmusic"]
            platform_name = result.platform.name.lower()

            if platform_name in music_platforms:
                template_name = "music.html.jinja"
            else:
                # 其他平台使用各自的模板
                file_name = f"{platform_name}.html.jinja"
                if (self.templates_dir / file_name).exists():
                    template_name = file_name

        # from jinja2 import FileSystemLoader, Environment

        # # 创建一个包加载器对象
        # env = Environment(
        #     loader=FileSystemLoader(self.templates_dir),
        #     enable_async=True,
        # )
        # env.filters["safe_path"] = safe_path
        # template = env.get_template(template_name)
        # # 渲染
        # with open(
        #     f"{self.templates_dir.parent.parent}/{datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')}.html",
        #     "w",
        #     encoding="utf8",
        # ) as f:  # noqa: E501
        #     f.write(
        #         await template.render_async(
        #             **{
        #                 "result": template_data,
        #                 "rendering_time": datetime.datetime.now().strftime(
        #                     "%Y-%m-%d %H:%M:%S"
        #                 ),
        #                 "bot_name": _nickname,
        #             }
        #         )
        #     )

        return await template_to_pic(
            template_path=str(self.templates_dir),
            template_name=template_name,
            screenshot_timeout=60000,
            templates={
                "result": template_data,
                "rendering_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "bot_name": _nickname,
            },
            pages={
                "viewport": {"width": 800, "height": 100},
                "base_url": f"file://{self.templates_dir}",
            },
            filters={"safe_path": safe_path},
        )

    async def _resolve_parse_result(self, result: ParseResult) -> dict[str, Any]:
        """解析 ParseResult 为模板可用的字典数据"""

        avatar_path = await result.author.get_avatar_path()
        # 这些是一定会有的字段
        data: dict[str, Any] = {
            "title": result.title,
            "formatted_datetime": result.formatted_datetime,
            "extra_info": result.extra_info,
            "extra": result.extra,
            "platform": {
                "display_name": result.platform.display_name,
                "name": result.platform.name,
                "logo_path": f"https://emoji.awkchan.top/assets/logo/{result.platform.name}.png",
            },
            "content": result.content,
            "cover_path": await safe_path(result, "get_cover_path"),
            "stats": result.stats,
            "comments": result.comments[: pconfig.max_comments],
            "author": {
                "name": result.author.name,
                "id": result.author.id,
                "avatar_path": avatar_path,
            },
        }

        if result.repost:
            data["repost"] = await self._resolve_parse_result(result.repost)

        # 添加二维码支持
        if pconfig.append_qrcode and result.url:
            # 生成二维码
            qr = qrcode.QRCode(
                version=1,
                error_correction=1,
                box_size=10,
                border=4,
            )
            qr.add_data(result.url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            # 将二维码转换为 base64 编码
            buffer = BytesIO()
            img.save(buffer, format="PNG")  # type: ignore
            buffer.seek(0)
            import base64

            img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            # 添加 base64 编码的图片数据到模板数据
            data["qr_code_path"] = f"data:image/png;base64,{img_base64}"

        return data

    async def cache_or_render_image(self, result: ParseResult):
        """获取缓存图片

        :param result: 解析结果
        """
        if result.render_image is None:
            image_raw = await self.render_image(result)
            image_path = await self.save_img(image_raw)
            result.render_image = image_path
            if pconfig.use_base64:
                return UniHelper.img_seg(image_raw)
        if result.render_image.stat().st_size >= 5 * 1024 * 1024:
            return UniHelper.file_seg(result.render_image)

        return UniHelper.img_seg(result.render_image)

    @classmethod
    async def save_img(cls, raw: bytes) -> Path:
        """保存图片

        :param raw: 图片字节
        """

        file_name = f"{uuid.uuid4().hex}.png"
        image_path = pconfig.cache_dir / file_name
        async with aiofiles.open(image_path, "wb+") as f:
            await f.write(raw)
        return image_path


RENDERER = Renderer()
