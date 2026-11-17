"""Blitz 原生 CSS 绘制与长图分段"""

from math import ceil
import re
from typing import Any, Final, cast

import blitz_py
from bs4 import BeautifulSoup, Tag
from PIL import Image

from .fonts import EmojiFont, EmojiStyle, apply_emoji_font

MAX_IMAGE_EDGE: Final = 16_000  # MAX 16384
MAX_IMAGE_PIXELS: Final = 60_000_000  # MAX 64M
BLUR_CLASS = re.compile(r"(?:dark:)?blur-\[(\d+)px\]")


def render_html(
    html: str,
    *,
    base_url: str,
    color_scheme: str = "light",
    width: int = 620,
    scale: float = 2,
    emoji_font: EmojiFont | None = None,
    emoji_style: EmojiStyle = "system",
) -> Image.Image:
    """绘制 HTML，返回 RGBA 图片"""
    page = BeautifulSoup(
        html,
        "html.parser",
        preserve_whitespace_tags={"span", "p", "div", "pre", "textarea", "code"},
    )
    apply_emoji_font(page, emoji_font, emoji_style)
    root = cast(Tag, page.find("main"))
    root_id = str(root.get("id", "parser-render-root"))
    root["id"] = root_id
    # 只用类名估算长图分段的重叠范围，滤镜及明暗模式均由 CSS 绘制
    blur_radius = max(
        (
            int(match[1])
            for element in page.select("[class]")
            for name in element.get_attribute_list("class")
            if (match := BLUR_CLASS.fullmatch(str(name)))
        ),
        default=0,
    )
    html = str(page)
    options: dict[str, Any] = {
        "base_url": base_url,
        "allow_file_urls": True,
        "background": None,
        "color_scheme": color_scheme,
        "resources": emoji_font.resources if emoji_font else {},
    }
    physical_width = int(width * scale)
    if not 0 < physical_width <= MAX_IMAGE_EDGE:
        raise ValueError(f"截图物理宽度须在 1 到 {MAX_IMAGE_EDGE} 像素之间")
    max_frame_height = int(
        min(MAX_IMAGE_EDGE, MAX_IMAGE_PIXELS // physical_width) / scale
    )
    if max_frame_height < 1:
        raise ValueError("缩放比例过大，无法在 Blitz 限制内绘制一行")
    layout = blitz_py.Template(html, width=width, height=1, **options)
    height = ceil(layout.get_box(root_id)[3])
    del layout

    physical_height = int(height * scale)
    # 原生滤镜也会裁掉视口外元素的光晕，分段时保留三倍模糊半径
    padding = ceil(3 * blur_radius * scale)
    frame_height = int(max_frame_height * scale)
    tile_height = (
        physical_height
        if physical_height <= frame_height
        else frame_height - 2 * padding
    )
    if tile_height <= 0:
        raise ValueError("模糊重叠区域超过 Blitz 单张截图限制")
    canvas = Image.new("RGBA", (physical_width, physical_height))
    for offset in range(0, physical_height, tile_height):
        end = min(offset + tile_height, physical_height)
        start = max(0, offset - padding)
        stop = min(physical_height, end + padding)
        viewport_height = ceil((stop - start) / scale)
        # 画布本身会裁切；矩形 overflow 裁切会触发上游 filter 的偏移问题
        viewport_css = (
            f"body{{height:{viewport_height}px!important;overflow:visible!important}}"
            f"main{{height:{height}px!important;transform:translateY({-start / scale}px)!important}}"
        )
        frame_options = {
            **options,
            "width": width,
            "height": viewport_height,
            "scale": scale,
        }
        w, h, rgba = blitz_py.render_rgba(html, css=viewport_css, **frame_options)
        frame = Image.frombytes("RGBA", (w, h), rgba)
        del rgba
        with frame:
            with frame.crop(
                (
                    0,
                    offset - start,
                    frame.width,
                    end - start,
                )
            ) as part:
                canvas.paste(part, (0, offset))
    return canvas
