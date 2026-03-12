from pathlib import Path
from typing import Any
from markupsafe import escape
from ..parsers.data import (
    ImageContent,
    LivePhotoContent,
    MediaContent,
    StickerContent,
    Comment,
    GraphicContent,
    VideoContent,
)


def build_images(img_list: list[str]) -> str:
    """根据图片数量构建单/双/四宫格/九宫格 HTML.

    :param img_list: 图片 url 列表
    """
    if not img_list:
        return ""

    count = len(img_list)
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
    max_visible = 9
    visible_imgs = img_list[:max_visible]
    hidden_count = max(0, count - max_visible)

    items_html: list[str] = []
    for idx, src in enumerate(visible_imgs):
        more_html = ""
        # 最后一张叠加 "+N"
        if hidden_count > 0 and idx == len(visible_imgs) - 1:
            more_html = f'<div class="more-count">+{hidden_count}</div>'
        items_html.append(f'<div class="image-item"><img src="{src}">{more_html}</div>')

    return (
        '<div class="images-container">'
        f'<div class="images-grid {grid_class}">'
        f"{''.join(items_html)}"
        "</div></div>"
    )


async def build_html(
    content: list[MediaContent | str | None], download: bool = True
) -> str:
    """构建模板可用的内容 HTML 字符串。

    文本、图片、表情、graphics 在这里直接拼成完整 HTML
    :param content: 内容列表
    :param download: 是否下载媒体

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
    first_text_seen = False

    for idx, cont in enumerate(content):
        # 统一处理“可以进宫格的图片类内容”
        if isinstance(cont, ImageContent):
            src = await cont.get_path(download=download)
            if isinstance(src, Path):
                src = src.as_uri()
            current_imgs.append(src)
            continue

        if isinstance(cont, LivePhotoContent):
            # Live Photo 底图也作为图片参与宫格合并
            src = await cont.get_base(download=download)
            if isinstance(src, Path):
                src = src.as_uri()
            current_imgs.append(src)
            continue

        # 任意非 image / live-photo 内容会打断图片连续段
        flush_images()

        # 计算“前一个 / 后一个是否是贴纸”
        prev_is_sticker = idx > 0 and isinstance(content[idx - 1], StickerContent)
        next_is_sticker = idx + 1 < total and isinstance(
            content[idx + 1], StickerContent
        )

        if isinstance(cont, str):
            text = escape(cont)
            # 第一个文本一定使用 span，之后只要前后任意一侧是贴纸就用 span；否则用 p
            is_first_text = not first_text_seen
            if is_first_text or prev_is_sticker or next_is_sticker:
                html_parts.append(f'<span class="text">{text}</span>')
            else:
                html_parts.append(f'<p class="text">{text}</p>')
            first_text_seen = True

        elif isinstance(cont, GraphicContent):
            src = await cont.get_path(download=download)
            if isinstance(src, Path):
                src = src.as_uri()
            alt = cont.alt or ""
            html_parts.append(
                '<div class="images-container">'
                '<div class="images-grid single">'
                '<div class="image-item">'
                f'<img src="{src}">'
                "</div></div>"
                f'<center><span class="text">{alt}</span></center>'
                "</div>"
            )

        elif isinstance(cont, StickerContent):
            src = await cont.get_path(download=download)
            if isinstance(src, Path):
                src = src.as_uri()
            size = cont.size
            html_parts.append(f'<img class="sticker {size}" src="{src}">')

        elif isinstance(cont, VideoContent):
            src = await cont.get_cover_path(download=download)
            if isinstance(src, Path):
                src = src.as_uri()
            html_parts.append(
                '<div class="images-container">'
                '<div class="images-grid single">'
                '<div class="image-item">'
                f'<img src="{src}">'
                '<div class="play-btn-overlay">'
                '<i class="fas fa-play" style="margin-left: 4px;"></i>'
                "</div>"
                "</div>"
                "</div>"
                "</div>"
            )

    # 末尾如果还有图片段，补一次 flush
    flush_images()
    return "".join(html_parts)


def build_plain_text(content: list[MediaContent | str | None]) -> str:
    """构建纯文本内容"""

    return "".join(f"\n{c}" for c in content if isinstance(c, str) and c)


async def build_comments(comment_list: list[Comment]) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for comment in comment_list:
        avatar_path = await comment.author.get_avatar_path(download=False)
        comments.append(
            {
                "author": {
                    "name": comment.author.name,
                    "id": comment.author.id,
                    "avatar_path": avatar_path or None,
                },
                "content": await build_html(
                    content=list(comment.content), download=False
                ),
                "formatted_datetime": comment.formatted_datetime,
                "stats": comment.stats,
                "location": comment.location,
                "replies": await build_comments(comment.replies),
            }
        )
    return comments
