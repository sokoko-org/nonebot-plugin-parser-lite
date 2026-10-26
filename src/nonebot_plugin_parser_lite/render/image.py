"""将 Theme API 数据渲染为编码后的图片"""

import asyncio

# from datetime import datetime
from io import BytesIO
import re
from typing import Literal

from anyio import Path
from jinja2 import Environment, FileSystemLoader

from ..config import pconfig
from ..utils.ffmpeg import FFmpeg
from ..utils.log import logger
from .context import ThemeData
from .engine import render_html
from .theme import ThemeDefinition, ThemeManager

TEMPLATES_DIR = Path(__file__).parent / "templates"


async def render_theme_data(
    data: ThemeData,
    *,
    image_format: Literal["jpeg", "webp"] | None = None,
    theme_definition: ThemeDefinition | None = None,
    debug: bool = False,
) -> tuple[Literal["jpeg", "webp"], bytes]:
    """按主题绘制数据，返回实际图片格式和图片内容"""
    if image_format is None:
        image_format = pconfig.render_format
    theme = theme_definition or await ThemeManager(
        TEMPLATES_DIR, pconfig.theme_dirs
    ).resolve(data["theme_id"])
    selected = await theme.resolve_template(data["post"]["platform"]["id"])
    env = Environment(
        loader=FileSystemLoader(str(selected.root)),
        enable_async=True,
        autoescape=False,
    )
    html = await env.get_template(selected.name).render_async(data=data)
    icon_css = await (TEMPLATES_DIR / "icon.css").read_text(encoding="utf-8")
    style = f'<style data-parser-fallback="icon-css">\n{icon_css}\n</style>'
    head = re.search(r"<head\b[^>]*>", html, flags=re.IGNORECASE)
    html = (
        f"{html[: head.end()]}\n{style}{html[head.end() :]}" if head else style + html
    )
    # if debug:
    #     path = TEMPLATES_DIR / f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.html"
    #     await path.write_text(html, encoding="utf-8")
    #     logger.info(f"已生成调试 HTML: {path}")

    canvas = await asyncio.to_thread(
        render_html,
        html,
        base_url=selected.base_url,
        color_scheme=data["theme"],
    )
    if image_format == "webp" and max(canvas.size) > 16383:
        logger.warning("渲染结果尺寸超过 WebP 编码上限，已改用 JPEG 输出")
        image_format = "jpeg"

    if image_format == "webp":
        width, height = canvas.size

        def raw_pixels() -> bytes:
            with canvas:
                return canvas.tobytes()

        rgba = await asyncio.to_thread(raw_pixels)
        return image_format, await FFmpeg.rgba_to_webp(rgba, width, height)

    def encode_jpeg() -> bytes:
        with canvas, canvas.convert("RGB") as rgb, BytesIO() as output:
            rgb.save(output, format="JPEG", quality=85, subsampling=0)
            return output.getvalue()

    return image_format, await asyncio.to_thread(encode_jpeg)
