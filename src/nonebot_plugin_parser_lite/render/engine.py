"""Blitz 布局、模糊图层合成与长图分段绘制"""

from collections import defaultdict
from math import ceil
import re
from typing import Any, cast

import blitz_py
from bs4 import BeautifulSoup, Tag
from PIL import Image, ImageChops

TILE_HEIGHT = 2048
BLUR_CLASS = re.compile(r"(dark:)?blur-\[(\d+)px\]")


def render_html(
    html: str,
    *,
    base_url: str,
    color_scheme: str = "light",
    width: int = 620,
    scale: float = 2,
) -> Image.Image:
    """绘制 HTML，返回 RGBA 图片"""
    page = BeautifulSoup(
        html,
        "html.parser",
        preserve_whitespace_tags={"span", "p", "div", "pre", "textarea", "code"},
    )
    root = cast(Tag, page.find("main"))
    root_id = str(root.get("id", "parser-render-root"))
    root["id"] = root_id
    veil = page.select_one("[data-render-veil]")
    if veil is not None:
        veil["id"] = str(veil.get("id", "parser-render-veil"))
    dark = color_scheme == "dark"
    ambient: dict[int, list[str]] = defaultdict(list)
    media: dict[int, list[str]] = defaultdict(list)
    blur_selectors = []
    for index, image in enumerate(page.select("img")):
        radii = {}
        for name in image.get_attribute_list("class"):
            if match := BLUR_CLASS.fullmatch(str(name)):
                radii[bool(match[1])] = int(match[2])
        radius = radii.get(dark, radii.get(False, 0))
        if not radius:
            continue
        image["id"] = str(image.get("id", f"parser-render-blur-{index}"))
        selector = f"#{image['id']}"
        blur_selectors.append(selector)
        group = ambient if image.parent is root else media
        group[radius].append(selector)

    html = str(page)
    options: dict[str, Any] = {
        "base_url": base_url,
        "allow_file_urls": True,
        "background": None,
        "color_scheme": color_scheme,
    }
    layout = blitz_py.Template(html, width=width, height=1, **options)
    height = ceil(layout.get_box(root_id)[3])
    del layout

    def layer(
        selectors: list[str], *, blur: int = 0, base: bool = False
    ) -> dict[str, Any]:
        selected = ",".join(selectors)
        # Blitz 会跳过隐藏祖先的子树；清空绘制颜色以保留布局和可见子元素
        css = (
            f"body *:not(:is({selected})){{color:transparent!important;"
            "background:transparent!important;border-color:transparent!important;"
            "box-shadow:none!important;text-shadow:none!important}"
            "img{visibility:hidden!important}"
            f"{selected}{{visibility:visible!important}}"
        )
        if not base:
            css += "main{background:transparent!important}"
        return {"css": css, "blur": min(blur * scale, 100)}

    layers = [layer([f"#{root_id}"], base=True)]
    layers.extend(
        layer(selectors, blur=radius) for radius, selectors in ambient.items()
    )
    if veil is not None:
        layers.append(layer([f"#{veil['id']}"]))
    layers.extend(layer(selectors, blur=radius) for radius, selectors in media.items())
    hidden = [*blur_selectors]
    if veil is not None:
        hidden.append(f"#{veil['id']}")
    foreground_css = "main{background:transparent!important}"
    if hidden:
        foreground_css += f"{','.join(hidden)}{{visibility:hidden!important}}"
    layers.append({"css": foreground_css, "blur": 0})

    # 三次 box blur 的影响范围是半径的三倍，重叠绘制后裁切可避免接缝
    padding = ceil(3 * max(item["blur"] for item in layers) / scale)
    canvas = Image.new("RGBA", (round(width * scale), round(height * scale)))
    for offset in range(0, height, TILE_HEIGHT):
        end = min(offset + TILE_HEIGHT, height)
        start = max(0, offset - padding)
        stop = min(height, end + padding)
        viewport_css = (
            f"body{{height:{stop - start}px!important;overflow:hidden!important}}"
            f"main{{height:{height}px!important;transform:translateY({-start}px)!important}}"
        )
        frame_options = {
            **options,
            "width": width,
            "height": stop - start,
            "scale": scale,
        }
        if blur_selectors:
            frame_layers = [
                {
                    **frame_options,
                    "html": html,
                    **item,
                    "css": item["css"] + viewport_css,
                }
                for item in layers
            ]
            w, h, rgba = blitz_py.render_layers(
                frame_layers,
                width=round(width * scale),
                height=round((stop - start) * scale),
                background="#00000000",
            )
            frame = Image.frombytes("RGBA", (w, h), rgba)
            del rgba
            # 图层模糊后恢复 main 的圆角裁剪，同时保留透明背景
            _, _, mask_rgba = blitz_py.render_rgba(
                html,
                css=layers[0]["css"] + viewport_css + "main{background:#fff!important}",
                **frame_options,
            )
            with Image.frombytes("RGBA", frame.size, mask_rgba) as mask:
                del mask_rgba
                with mask.getchannel("A") as clip, frame.getchannel("A") as alpha:
                    with ImageChops.darker(alpha, clip) as clipped:
                        frame.putalpha(clipped)
        else:
            w, h, rgba = blitz_py.render_rgba(html, css=viewport_css, **frame_options)
            frame = Image.frombytes("RGBA", (w, h), rgba)
            del rgba
        with frame:
            with frame.crop(
                (
                    0,
                    round((offset - start) * scale),
                    frame.width,
                    round((end - start) * scale),
                )
            ) as part:
                canvas.paste(part, (0, round(offset * scale)))
    return canvas
