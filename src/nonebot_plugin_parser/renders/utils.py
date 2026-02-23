from typing import Any, cast, overload
from collections.abc import Mapping, Sequence

from markupsafe import escape

from ..parsers.data import (
    ImageContent,
    MediaContent,
    StickerContent,
    GraphicContent,
)


@overload
def build_images(
    img_list: list[str],
    max_visible: int = 9,
) -> str: ...
@overload
def build_images(
    img_list: list[Mapping[str, Any]],
    max_visible: int = 9,
    *,
    key: str,
) -> str: ...
def build_images(
    img_list: list[str] | list[Mapping[str, Any]],
    max_visible: int = 9,
    *,
    key: str | None = None,
) -> str:
    """根据图片数量构建单/双/四宫格/九宫格 HTML.

    - 支持传入字符串列表: list[str]
    - 支持传入字典列表: list[Mapping]，需要指定 key 作为图片链接字段

    :param img_list: 图片 src 列表，或字典列表
    :param max_visible: 最多展示的图片数量，超出的会叠加为 +N
    :param key: 当 img_list 为字典列表时，指定图片链接字段名
    """
    if not img_list:
        return ""

    img_src_list: list[str] = []
    # 统一转换成 src 字符串列表
    if isinstance(img_list[0], str):
        img_src_list = img_list  # type: ignore[assignment]
    else:
        if not key:
            raise ValueError("当传入字典列表时必须指定 key 参数作为图片链接字段名")
        mapping_list = cast(Sequence[Mapping[str, Any]], img_list)
        for item in mapping_list:
            if value := item.get(key):
                img_src_list.append(value)

    if not img_src_list:
        return ""

    count = len(img_src_list)
    if count == 1:
        grid_class = "single"
    elif count == 2:
        grid_class = "double"
    elif count == 4:
        grid_class = "quad"
    elif count >= 3:
        grid_class = "nine"
    else:
        grid_class = "single"

    # 最多展示 max_visible 张，超出的收纳为 +N
    max_visible = max(1, max_visible)
    visible_imgs = img_src_list[:max_visible]
    hidden_count = max(0, count - max_visible)

    items_html: list[str] = []
    for idx, src in enumerate(visible_imgs):
        more_html = ""
        # 最后一张叠加 "+N"
        if hidden_count > 0 and idx == len(visible_imgs) - 1:
            more_html = f'<div class="more-count">+{hidden_count}</div>'
        items_html.append(
            '<div class="image-item">' f'<img src="{src}">{more_html}</div>'
        )

    return (
        '<div class="images-container">'
        f'<div class="images-grid {grid_class}">'
        f"{''.join(items_html)}"
        "</div></div>"
    )


async def build_html(content: Sequence[MediaContent | str | None]) -> str:
    """构建模板可用的内容 HTML 字符串。

    文本、图片、表情、graphics 在这里直接拼成完整 HTML

    :return: HTML
    """
    html_parts: list[str] = []

    current_imgs: list[str] = []
    """当前图片段相关状态：用于处理“连续图片合并为宫格”"""

    def flush_images() -> None:
        """结束当前连续图片段并写入 HTML."""
        nonlocal current_imgs
        if current_imgs:
            html_parts.append(build_images(current_imgs))
            current_imgs = []

    total = len(content)

    for idx, cont in enumerate(content):
        if isinstance(cont, ImageContent):
            path = await cont.get_path()
            src = path.as_uri()
            current_imgs.append(src)
        else:
            # 任意非 image 内容会打断图片连续段
            flush_images()

            # 计算“前一个 / 后一个是否是贴纸”
            prev_is_sticker = idx > 0 and isinstance(content[idx - 1], StickerContent)
            next_is_sticker = idx + 1 < total and isinstance(
                content[idx + 1], StickerContent
            )

            if isinstance(cont, str):
                # 只要前后任意一侧是贴纸，就用 span；否则用 p
                if prev_is_sticker or next_is_sticker:
                    html_parts.append(f'<span class="text">{cont}</span>')
                else:
                    html_parts.append(f'<p class="text">{cont}</p>')

            elif isinstance(cont, GraphicContent):
                g_path = await cont.get_path()
                g_src = g_path.as_uri()
                alt = cont.alt or ""
                html_parts.append(
                    '<div class="images-container">'
                    '<div class="images-grid single">'
                    '<div class="image-item">'
                    f'<img src="{g_src}">'
                    "</div></div>"
                    f'<center><span class="text">{alt}</span></center>'
                    "</div>"
                )
            elif isinstance(cont, StickerContent):
                s_path = await cont.get_path()
                s_src = s_path.as_uri()
                size = cont.size or "medium"
                html_parts.append(f'<img class="sticker {size}" src="{s_src}">')

    # 末尾如果还有图片段，补一次 flush
    flush_images()
    return "".join(html_parts)


def build_plain_text(content: Sequence[MediaContent | str | None]) -> str:
    """构建纯文本内容"""

    return "".join("\n" + escape(c) for c in content if isinstance(c, str) and c)
