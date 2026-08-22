"""Framework-neutral HTML renderer for parse results."""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable
from datetime import datetime
from io import BytesIO
from pathlib import Path as SyncPath
from typing import Any, Literal, cast

from anyio import Path
from jinja2 import Environment, FileSystemLoader
import qrcode

from ..config import _nickname, pconfig
from ..data import ParseResult
from ..utils.browser import BrowserManager
from ..utils.log import logger

PLACEHOLDER_IMAGE = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxIiBoZWlnaHQ9IjEiLz4="
)
Theme = Literal["light", "dark"]


def get_theme() -> Theme:
    start, end = pconfig.day_range_minutes
    now = datetime.now()
    current = now.hour * 60 + now.minute
    in_day = (
        start <= current < end
        if start <= end
        else current >= start or current < end
    )
    return "light" if in_day else "dark"


async def safe_src(
    obj: object,
    method: str,
    *,
    return_none_on_fail: bool = False,
) -> str | None:
    fallback = None if return_none_on_fail else PLACEHOLDER_IMAGE
    if obj is None:
        return fallback
    try:
        attr = getattr(obj, method)
        callable_attr = cast(Callable[[], Path | Awaitable[Path | None]], attr)
        value = callable_attr()
        path = await value if isinstance(value, Awaitable) else value
        return path.as_uri() if path is not None else fallback
    except Exception as exc:
        logger.warning(
            "safe_src(%s) failed for %s: %r", method, type(obj).__name__, exc
        )
        return fallback


class Renderer:
    def __init__(self) -> None:
        self.templates_dir = Path(__file__).parent / "templates"

    def _template_name(self, result: ParseResult) -> str:
        platform = result.platform.name.lower()
        if platform in {"kugou", "netease", "kuwo", "qsmusic"}:
            return "music.html.jinja"
        candidate = SyncPath(self.templates_dir) / f"{platform}.html.jinja"
        return candidate.name if candidate.exists() else "default.html.jinja"

    async def resolve_parse_result(self, result: ParseResult) -> dict[str, Any]:
        data: dict[str, Any] = {
            "title": result.title,
            "formatted_datetime": result.formatted_datetime,
            "extra": result.extra,
            "platform": {
                "display_name": result.platform.display_name,
                "name": result.platform.name,
                "logo_path": await safe_src(result.platform, "get_logo_path"),
            },
            "content": result.content,
            "cover_path": await safe_src(
                result, "get_cover_path", return_none_on_fail=True
            ),
            "stats": result.stats,
            "comments": result.comments[: pconfig.max_comments],
            "author": {
                "name": result.author.name,
                "id": result.author.id,
                "avatar_path": await safe_src(result.author, "get_avatar_path"),
            },
            "ai_summary": result.ai_summary,
            "rendering_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "bot_name": _nickname,
        }
        if result.repost:
            data["repost"] = await self.resolve_parse_result(result.repost)
        if pconfig.append_qrcode:
            qr = qrcode.QRCode(version=1, error_correction=1, box_size=10, border=1)
            qr.add_data(result.url)
            qr.make(fit=True)
            image = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            data["qrcode_path"] = f"data:image/png;base64,{encoded}"
        return data

    async def render_html(
        self, result: ParseResult, *, theme: Theme | None = None
    ) -> str:
        environment = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            enable_async=True,
            autoescape=True,
        )
        environment.filters["safe_src"] = safe_src
        template = environment.get_template(self._template_name(result))
        return await template.render_async(
            result=await self.resolve_parse_result(result), theme=theme or get_theme()
        )

    async def render_image(
        self, result: ParseResult, *, theme: Theme | None = None
    ) -> bytes:
        return await BrowserManager.screenshot(
            html=await self.render_html(result, theme=theme),
            template_path=self.templates_dir.as_uri(),
            viewport={"width": 620, "height": 100},
            device_scale_factor=2,
            type="jpeg",
            quality=85,
        )


RENDERER = Renderer()
