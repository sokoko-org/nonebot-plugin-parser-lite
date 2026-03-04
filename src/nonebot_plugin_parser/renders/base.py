import uuid
import datetime
from io import BytesIO
from typing import Any, ClassVar
from pathlib import Path
from collections.abc import AsyncGenerator

import qrcode
from nonebot import logger

from .utils import build_html, build_plain_text, build_comments
from ..config import pconfig, _nickname
from ..helper import UniHelper, UniMessage, ForwardNodeInner
from ..exception import DownloadException, ZeroSizeException, DownloadLimitException
from ..parsers.data import (
    ParseResult,
    AudioContent,
    ImageContent,
    MediaContent,
    GraphicContent,
    VideoContent,
)

from nonebot_plugin_htmlrender import template_to_pic


class Renderer:
    """统一的渲染器，将解析结果转换为消息"""

    templates_dir: ClassVar[Path] = Path(__file__).parent / "templates"
    """模板目录"""

    async def render_messages(
        self, result: ParseResult
    ) -> AsyncGenerator[UniMessage[Any], None]:
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
        msg = UniMessage(image_seg) if image_seg else UniMessage("图片渲染失败")
        if self.append_url:
            urls = (result.display_url, result.repost_display_url)
            msg += "\n".join(url for url in urls if url)
        yield msg

        # 媒体内容
        async for message in self.send_content(result):
            yield message

    async def send_content(
        self, result: ParseResult
    ) -> AsyncGenerator[UniMessage[Any], None]:
        """发送媒体内容消息。

        将解析结果中的媒体内容拆分为立即发送的音视频和可合并转发的图文，并处理延迟发送配置。
        """
        forwardable_segs: list[ForwardNodeInner] = []
        media_contents: list[MediaContent | Path] = []
        failed_count = 0

        need_delay = pconfig.delay_send_media or pconfig.delay_send_lazy_download

        for cont in result.content:
            if not isinstance(cont, MediaContent) or not cont.need_send:
                continue

            match cont:
                case VideoContent() | AudioContent():
                    failed_delta, media = await self._handle_media_content(
                        cont, need_delay
                    )
                    failed_count += failed_delta
                    if media is not None:
                        media_contents.append(media)
                case ImageContent():
                    try:
                        path = await cont.get_path()
                        forwardable_segs.append(UniHelper.img_seg(path))
                    except (DownloadLimitException, ZeroSizeException):
                        continue
                    except DownloadException:
                        failed_count += 1
                        continue
                case GraphicContent():
                    try:
                        path = await cont.get_path()
                        graphics_msg = UniHelper.img_seg(path)
                        if cont.alt is not None:
                            graphics_msg = graphics_msg + cont.alt
                        forwardable_segs.append(graphics_msg)
                    except (DownloadLimitException, ZeroSizeException):
                        continue
                    except DownloadException:
                        failed_count += 1
                        continue

        if media_contents and need_delay:
            result.media_contents = media_contents

        if forwardable_segs:
            self._append_forward_text_segments(result, forwardable_segs)

            if pconfig.need_forward_contents or len(forwardable_segs) > 4:
                forward_msg = UniHelper.construct_forward_message(forwardable_segs)
                yield UniMessage(forward_msg)
            else:
                yield UniMessage(forwardable_segs)

        if failed_count > 0:
            message = f"{failed_count} 项媒体下载失败"
            yield UniMessage(message)
            raise DownloadException(message)

    async def _handle_media_content(
        self, cont: MediaContent, need_delay: bool
    ) -> tuple[int, MediaContent | Path | None]:
        """处理单个音视频内容，返回失败次数增量和可能的延迟发送内容。"""
        logger.debug(
            f"处理{type(cont).__name__}，"
            f"need_delay={need_delay}, lazy_download={pconfig.delay_send_lazy_download}"
        )

        if need_delay:
            return await self._handle_delayed_media(cont)
        return await self._handle_immediate_media(cont)

    async def _handle_delayed_media(
        self, cont: MediaContent
    ) -> tuple[int, MediaContent | Path | None]:
        """处理延迟发送的音视频内容。"""
        if pconfig.delay_send_lazy_download:
            logger.debug(
                f"延迟发送{type(cont).__name__}，缓存MediaContent对象，不立即下载"
            )
            return 0, cont

        try:
            path = await cont.get_path()
            logger.debug(f"延迟发送{type(cont).__name__}，已下载，缓存路径: {path}")
            return 0, path
        except (DownloadLimitException, ZeroSizeException):
            return 0, None
        except DownloadException:
            return 1, None

    async def _handle_immediate_media(self, cont: MediaContent) -> tuple[int, None]:
        """处理立即发送的音视频内容。"""
        try:
            path = await cont.get_path()
            logger.debug(f"立即发送{type(cont).__name__}: {path}")

            if isinstance(cont, VideoContent):
                if pconfig.need_upload_video:
                    await UniMessage(UniHelper.file_seg(path)).send()
                else:
                    await UniMessage(UniHelper.video_seg(path)).send()
            elif isinstance(cont, AudioContent):
                try:
                    if pconfig.need_upload_audio:
                        await UniMessage(UniHelper.file_seg(path)).send()
                    else:
                        await UniMessage(UniHelper.record_seg(path)).send()
                except Exception as e:
                    logger.debug(f"直接发送音频失败，尝试使用群文件发送: {e}")
                    await UniMessage(UniHelper.file_seg(path)).send()
            return 0, None
        except (DownloadLimitException, ZeroSizeException):
            return 0, None
        except DownloadException:
            return 1, None

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

        from jinja2 import FileSystemLoader, Environment

        # 创建一个包加载器对象
        env = Environment(loader=FileSystemLoader(self.templates_dir))
        template = env.get_template(template_name)
        # 渲染
        with open(
            f"{self.templates_dir.parent.parent}/{datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')}.html",
            "w",
            encoding="utf8",
        ) as f:  # noqa: E501
            f.write(
                template.render(
                    **{
                        "result": template_data,
                        "rendering_time": datetime.datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "bot_name": _nickname,
                    }
                )
            )

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
