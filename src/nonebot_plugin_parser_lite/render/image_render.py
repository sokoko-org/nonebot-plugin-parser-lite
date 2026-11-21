"""图片渲染：将解析结果绘制为主题卡片并缓存复用"""

from typing import Literal
import uuid

from anyio import Path
from nonebot import logger

from ..config import _nickname, pconfig
from ..data import AudioVideoContent, ParseResult
from ..helper import UniHelper
from ..utils.cache import CacheManager
from .context import ThemeData, build_theme_data
from .fonts import ensure_emoji_font
from .image import render_theme_data
from .theme import ThemeDefinition, ThemeManager, get_theme

Theme = Literal["light", "dark"]

RENDER_TEMPLATE_VERSION = "20261117-3"


class ImageRenderMixin:
    """提供主题卡片渲染与缓存能力"""

    templates_dir: Path

    async def render_image(
        self,
        result: ParseResult,
        *,
        theme: Theme,
        image_format: Literal["jpeg", "webp"],
        theme_definition: ThemeDefinition | None = None,
    ) -> tuple[Literal["jpeg", "webp"], bytes]:
        """使用选定主题绘制卡片，返回实际格式与编码后的图片"""
        selected_theme = theme_definition or await self._resolve_theme()
        template_data = await self.resolve_parse_result(
            result,
            color_scheme=theme,
            theme_id=selected_theme.id,
        )
        return await render_theme_data(
            template_data,
            image_format=image_format,
            theme_definition=selected_theme,
        )

    async def _resolve_theme(self) -> ThemeDefinition:
        return await ThemeManager(
            self.templates_dir,
            pconfig.theme_dirs,
        ).resolve(pconfig.render_theme)

    async def list_themes(self) -> list[ThemeDefinition]:
        """列出当前配置可用的主题"""
        return await ThemeManager(
            self.templates_dir,
            pconfig.theme_dirs,
        ).list_themes()

    async def resolve_parse_result(
        self,
        result: ParseResult,
        *,
        color_scheme: Theme | None = None,
        theme_id: str | None = None,
    ) -> ThemeData:
        """解析 ParseResult 为主题 API v1 数据"""
        selected_theme_id = theme_id or (await self._resolve_theme()).id
        return await build_theme_data(
            result,
            color_scheme=color_scheme or get_theme(),
            theme_id=selected_theme_id,
            bot_name=_nickname,
            max_comments=pconfig.max_comments,
            append_qrcode=pconfig.append_qrcode,
        )

    async def cache_or_render_image(self, result: ParseResult):
        """获取缓存图片，缺失时渲染并写入，支持跨重启复用

        以当前主题、解析结果 URL 与上传前倍速为 key 生成稳定文件名：
        - 若文件已存在：直接使用，不再重新渲染
        - 若不存在：渲染并写入该文件
        """
        theme = get_theme()
        selected_theme = await self._resolve_theme()
        render_format = pconfig.render_format
        # 卡片上的时长与体积按倍速换算，倍速变了就得重渲染
        speedup_digest = ",".join(
            f"{content.speedup:.2f}x"
            for content in result.iter_sendable_media()
            if isinstance(content, AudioVideoContent)
        )
        emoji_font = await ensure_emoji_font(pconfig.emoji_style)
        emoji_digest = emoji_font.digest if emoji_font else ""
        cache_key = (
            f"{RENDER_TEMPLATE_VERSION}:{selected_theme.id}:"
            f"{selected_theme.version}:{theme}:{render_format}:{result.url}"
            f":{speedup_digest}:{emoji_digest}:{pconfig.emoji_style}"
        )
        base_name = str(uuid.uuid5(uuid.NAMESPACE_URL, cache_key))
        cache_dir = await CacheManager.ensure_dir(CacheManager.RENDER)
        base_path = cache_dir / base_name

        entry = CacheManager.get_cached_entry(base_path)
        if entry is None:
            # 以 key 为粒度加锁，避免同一张图被多次并发渲染
            async with CacheManager.write_lock(f"render:{cache_key}"):
                entry = CacheManager.get_cached_entry(base_path)
                if entry is None:
                    logger.info(f"渲染主题: {selected_theme.name}")
                    image_format, image_raw = await self.render_image(
                        result,
                        theme=theme,
                        image_format=render_format,
                        theme_definition=selected_theme,
                    )
                    image_path = base_path.with_suffix(f".{image_format}")
                    temp_path = image_path.with_name(
                        f".{image_path.stem}.{uuid.uuid4().hex}.tmp{image_path.suffix}"
                    )
                    try:
                        await temp_path.write_bytes(image_raw)
                        await temp_path.replace(image_path)
                    finally:
                        await temp_path.unlink(missing_ok=True)
                    entry = await CacheManager.set_cached_file(
                        base_path, image_path, size_bytes=len(image_raw)
                    )

        result.render_image = entry.path
        if entry.size_bytes >= 5 * 1024 * 1024:
            return await UniHelper.file_seg(entry.path)

        return await UniHelper.img_seg(entry.path)
