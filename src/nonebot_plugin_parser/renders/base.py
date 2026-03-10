import datetime
import uuid
from collections.abc import AsyncGenerator
from io import BytesIO
from pathlib import Path
from typing import Any, ClassVar

import qrcode
from nonebot import logger
from nonebot_plugin_htmlrender import template_to_pic

from ..config import _nickname, pconfig
from ..exception import DownloadException, SizeLimitException, ZeroSizeException
from ..helper import ForwardNodeInner, UniHelper, UniMessage
from ..parsers.data import (
    AudioContent,
    GraphicContent,
    ImageContent,
    MediaContent,
    ParseResult,
    VideoContent,
)
from .utils import build_comments, build_html, build_plain_text


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
        except Exception as e:
            logger.error(f"获取图片路径失败: {type(e)}:{e!r}")
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

        async for cont in self._iter_all_media(result):
            # 先处理需要立即发送的音视频
            try:
                async for msg in self._handle_immediate_media(cont):
                    yield msg
            except (SizeLimitException, ZeroSizeException):
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

            if seg is not None:
                forwardable_segs.append(seg)

        # 处理图文转发部分
        if forwardable_segs:
            self._append_forward_text_segments(result, forwardable_segs)

            if pconfig.need_forward_contents or len(forwardable_segs) > 4:
                forward_msg = UniHelper.construct_forward_message(forwardable_segs)
                yield UniMessage(forward_msg)
            else:
                # 直接按顺序发出若干段（视平台实现为合并转发或多条消息）
                yield UniMessage(forwardable_segs)

        # 汇总下载失败信息
        if failed_count > 0:
            message = f"{failed_count} 项媒体下载失败"
            yield UniMessage(message)
            raise DownloadException(message)

    async def _iter_all_media(
        self, result: ParseResult
    ) -> AsyncGenerator[MediaContent, None]:
        """统一遍历主体内容和需要下载的评论里的 MediaContent。"""
        # 主内容
        for cont in result.content:
            if isinstance(cont, MediaContent) and cont.need_send:
                yield cont

        # 评论内容（仅遍历需要下载的评论）
        for com in result.comments:
            if not com._download:
                continue
            for cont in com.content:
                if isinstance(cont, MediaContent) and cont.need_send:
                    yield cont

    async def _handle_immediate_media(
        self, cont: MediaContent
    ) -> AsyncGenerator[UniMessage[Any], None]:
        # sourcery skip: merge-duplicate-blocks, remove-redundant-if
        """处理需要立即发送的音视频媒体，返回对应的消息段。"""
        if not isinstance(cont, (VideoContent, AudioContent)):
            return

        path = await cont.get_path()
        logger.debug(f"立即发送{type(cont).__name__}: {path}")

        if isinstance(cont, VideoContent):
            if pconfig.need_upload_video:
                yield UniMessage(UniHelper.file_seg(path))
            else:
                yield UniMessage(UniHelper.video_seg(path))
        elif isinstance(cont, AudioContent):
            if pconfig.need_upload_audio:
                yield UniMessage(UniHelper.file_seg(path))
            else:
                yield UniMessage(UniHelper.record_seg(path))

    async def _build_forwardable_segment(
        self, cont: MediaContent
    ) -> ForwardNodeInner | None:
        """构建可加入转发消息的片段（图片 / 图文）。"""
        # 只有图片和图文会进入可转发段
        if isinstance(cont, ImageContent):
            path = await cont.get_path()
            return UniHelper.img_seg(path)

        if isinstance(cont, GraphicContent):
            path = await cont.get_path()
            seg = UniHelper.img_seg(path)
            if cont.alt:
                seg = seg + cont.alt
            return seg

        return None

    def _append_forward_text_segments(
        self,
        result: ParseResult,
        forwardable_segs: list[ForwardNodeInner],
    ) -> None:
        """追加转发消息中的文本片段（作者、转发信息等）。"""
        if not forwardable_segs or not result.content:
            return

        author_name = result.author.name if result.author else "未知用户"

        if result.repost:
            self._build_result_with_repost(result, forwardable_segs, author_name)
        elif plain := build_plain_text(list(result.content)):
            forwardable_segs.append(f"{author_name}：{plain}")

    def _build_result_with_repost(
        self,
        result: ParseResult,
        forwardable_segs: list[ForwardNodeInner],
        author_name: str,
    ):
        assert result.repost
        repost_author = (
            result.repost.author.name if result.repost.author else "未知用户"
        )
        forwardable_segs.append(
            f"{author_name}[转发{repost_author}]：{build_plain_text(list(result.content))}"
        )

        repost_text: list[str] = []
        if result.repost.title:
            repost_text.append(result.repost.title)
        if plain := build_plain_text(list(result.repost.content)):
            repost_text.append(plain)

        if repost_text:
            repost_content = "\n".join(repost_text)
            forwardable_segs.append(f"{repost_author}[被转作者]：{repost_content}")

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

            #    from jinja2 import FileSystemLoader, Environment

            #    # 创建一个包加载器对象
            #    env = Environment(loader=FileSystemLoader(self.templates_dir))
            #    template = env.get_template(template_name)
            #    # 渲染
            #    with open(
            #        f"{self.templates_dir.parent.parent}/{datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')}.html",
            #        "w",
            #        encoding="utf8",
            #    ) as f:  # noqa: E501
            #        f.write(
            #            template.render(
            #                **{
            #                    "result": template_data,
            #                    "rendering_time": datetime.datetime.now().strftime(
            #                        "%Y-%m-%d %H:%M:%S"
            #                    ),
            #                    "bot_name": _nickname,
            #                }
            #            )
            #        )

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
        )

    async def _resolve_parse_result(
        self, result: ParseResult, download: bool = True
    ) -> dict[str, Any]:
        """解析 ParseResult 为模板可用的字典数据"""

        logo_path = Path(__file__).parent / "resources" / f"{result.platform.name}.png"
        content = await build_html(list(result.content), download=download)
        comments = await build_comments(result.comments)
        avatar_path = await result.author.get_avatar_path(download=False)
        # 这些是一定会有的字段
        data: dict[str, Any] = {
            "title": result.title,
            "formatted_datetime": result.formatted_datetime,
            "extra_info": result.extra_info,
            "extra": result.extra,
            "platform": {
                "display_name": result.platform.display_name,
                "name": result.platform.name,
                "logo_path": (logo_path.as_uri() if logo_path.exists() else None),
            },
            "content": content,
            "cover_path": await result.get_cover_path(),
            "stats": result.stats,
            "comments": comments,
            "author": {
                "name": result.author.name,
                "id": result.author.id,  # 传递 UID
                "avatar_path": avatar_path or None,
            },
        }

        if result.repost:
            data["repost"] = await self._resolve_parse_result(
                result.repost, download=False
            )

        # 添加二维码支持
        if pconfig.append_qrcode and result.url:
            # 生成二维码
            qr = qrcode.QRCode(
                version=1,
                error_correction=1,  # ERROR_CORRECT_L 的数值
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

        Args:
            result (ParseResult): 解析结果

        Returns:
            Image: 图片 Segment
        """
        if result.render_image is None:
            image_raw = await self.render_image(result)
            image_path = await self.save_img(image_raw)
            result.render_image = image_path
            if pconfig.use_base64:
                return UniHelper.img_seg(raw=image_raw)

        return UniHelper.img_seg(result.render_image)

    @classmethod
    async def save_img(cls, raw: bytes) -> Path:
        """保存图片

        Args:
            raw (bytes): 图片字节

        Returns:
            Path: 图片路径
        """
        import aiofiles

        file_name = f"{uuid.uuid4().hex}.png"
        image_path = pconfig.cache_dir / file_name
        async with aiofiles.open(image_path, "wb+") as f:
            await f.write(raw)
        return image_path
