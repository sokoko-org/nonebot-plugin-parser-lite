from ..config import _nickname, pconfig
from ..data import ParseResult
from .context import PLACEHOLDER_IMAGE, ThemeData, build_theme_data, safe_src
from .image import render_theme_data
from .theme import ThemeDefinition, ThemeManager, get_theme

__all__ = [
    "PLACEHOLDER_IMAGE",
    "ThemeData",
    "ThemeDefinition",
    "ThemeManager",
    "build_theme_data",
    "render_theme_data",
    "resolve_parse_result",
    "safe_src",
]


async def resolve_parse_result(
    result: ParseResult,
    *,
    color_scheme: str | None = None,
    theme_id: str | None = None,
) -> ThemeData:
    """Return Theme API data using local file URIs for downloaded resources."""
    return await build_theme_data(
        result,
        color_scheme=color_scheme if color_scheme is not None else get_theme(),
        theme_id=theme_id or pconfig.render_theme,
        bot_name=_nickname,
        max_comments=pconfig.max_comments,
        append_qrcode=pconfig.append_qrcode,
    )
