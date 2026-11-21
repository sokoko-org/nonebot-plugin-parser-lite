"""渲染包：统一入口

- :class:`Renderer` 组合图片渲染与消息编排两类能力
- 分包工具见 :mod:`.forward`，图片渲染见 :mod:`.image_render`，
  消息编排见 :mod:`.message_render`
"""

from anyio import Path

from .context import PLACEHOLDER_IMAGE, ThemeData, build_theme_data, safe_src
from .forward import (
    MAX_FORWARD_NODES,
    MAX_FORWARD_TEXT_LEN,
    SPLIT_THRESHOLD,
    pack_forward_items,
    split_forward_content,
)
from .image import render_theme_data
from .image_render import ImageRenderMixin
from .message_render import MessageRenderMixin
from .theme import ThemeManager

__all__ = [
    "MAX_FORWARD_NODES",
    "MAX_FORWARD_TEXT_LEN",
    "PLACEHOLDER_IMAGE",
    "RENDERER",
    "SPLIT_THRESHOLD",
    "Renderer",
    "ThemeData",
    "ThemeManager",
    "build_theme_data",
    "pack_forward_items",
    "render_theme_data",
    "safe_src",
    "split_forward_content",
]


class Renderer(MessageRenderMixin, ImageRenderMixin):
    """将解析结果渲染为图片卡片与可发送消息"""

    templates_dir = Path(__file__).parent / "templates"
    """模板目录"""


RENDERER = Renderer()
