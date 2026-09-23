from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
import contextlib
from datetime import datetime
from html import escape
import inspect
from io import BytesIO
from typing import Any, TypedDict, cast

from anyio import Path
from nonebot import logger
import qrcode

from ..data import (
    AudioContent,
    Author,
    Comment,
    ContentItem,
    GraphicContent,
    ImageContent,
    LinkContent,
    LivePhotoContent,
    MediaContent,
    ParseResult,
    PollContent,
    QuoteContent,
    Stats,
    StickerContent,
    VideoContent,
)
from .theme import MUSIC_PLATFORMS, THEME_SCHEMA_VERSION

PLACEHOLDER_IMAGE = (
    "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


class ThemeData(TypedDict):
    """Theme API v1 的根数据结构"""

    schema_version: int
    theme: str
    theme_id: str
    post: dict[str, Any]
    meta: dict[str, Any]


async def safe_src(
    obj: Any,
    method: str = "get_path",
    *,
    return_none_on_fail: bool = False,
) -> str | None:
    """把模型对象的资源方法解析成浏览器可用的 URI。

    该函数只供数据转换层使用。主题模板拿到的已经是 URI，不再接触
    Python 模型或异步方法。
    """
    fallback = None if return_none_on_fail else PLACEHOLDER_IMAGE
    try:
        if obj is None or not hasattr(obj, method):
            return fallback
        attr = getattr(obj, method)
        if not callable(attr):
            return fallback
        result = cast(Any, attr)()
        value = await result if inspect.isawaitable(result) else result
        return fallback if value is None else await _path_to_uri(value)
    except Exception as error:
        logger.warning(
            f"safe_src({method}) 处理 {type(obj).__name__} 时失败: {error!r}"
        )
        return fallback


async def build_theme_data(
    result: ParseResult,
    *,
    color_scheme: str,
    theme_id: str,
    bot_name: str,
    max_comments: int,
    append_qrcode: bool,
) -> ThemeData:
    """构造主题 API v1 数据。

    返回值只包含 JSON-like 数据：字典、列表、字符串、数字、布尔值和
    ``None``。主题因此不需要知道解析器内部的数据类或资源获取方法
    """
    post = await _serialize_result(result, max_comments=max_comments)
    if append_qrcode:
        post["qrcode"] = _build_qrcode(result.url)

    data: ThemeData = {
        "schema_version": THEME_SCHEMA_VERSION,
        "theme": color_scheme,
        "theme_id": theme_id,
        "post": post,
        "meta": {
            "bot_name": bot_name,
            "rendering_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "width": 620,
        },
    }
    return cast(ThemeData, _escape_html(data))


async def _serialize_result(
    result: ParseResult, *, max_comments: int
) -> dict[str, Any]:
    is_music = str(result.platform.name) in MUSIC_PLATFORMS

    content: list[dict[str, Any]] = []
    cover_found = False
    for item in result.content:
        is_cover = (
            is_music
            and not cover_found
            and isinstance(item, ImageContent | GraphicContent)
        )
        content.append(await _serialize_content(item, is_cover=is_cover))
        cover_found = cover_found or is_cover

    return {
        "title": result.title,
        "url": result.url,
        "formatted_datetime": result.formatted_datetime,
        "extra": _json_value(result.extra),
        "platform": {
            "id": str(result.platform.name),
            "name": result.platform.display_name,
            "logo": await safe_src(result.platform, "get_logo_path"),
        },
        "author": await _serialize_author(result.author),
        "content": content,
        "stats": _serialize_stats(result.stats),
        "comments": [
            await _serialize_comment(comment)
            for comment in result.comments[:max_comments]
        ],
        "qrcode": None,
        "ai_summary": result.ai_summary,
        "embed_url": result.embed_url,
        "repost": (
            await _serialize_result(result.repost, max_comments=max_comments)
            if result.repost
            else None
        ),
    }


async def _serialize_author(author: Author) -> dict[str, Any]:
    return {
        "name": author.name,
        "id": author.id,
        "description": author.description,
        "location": author.location,
        "avatar": await safe_src(author, "get_avatar_path"),
    }


async def _serialize_comment(comment: Comment) -> dict[str, Any]:
    return {
        "author": await _serialize_author(comment.author),
        "content": [await _serialize_content(item) for item in comment.content],
        "timestamp": comment.timestamp,
        "formatted_datetime": comment.formatted_datetime,
        "stats": _serialize_stats(comment.stats),
        "replies": [await _serialize_comment(reply) for reply in comment.replies],
        "parent_author": (
            await _serialize_author(comment.parent_author)
            if comment.parent_author
            else None
        ),
    }


def _serialize_stats(stats: Stats) -> dict[str, Any]:
    extra: list[dict[str, Any]] = []
    for key, value in stats.extra.items():
        if isinstance(value, list | tuple) and len(value) >= 2:
            label, amount = value[0], value[1]
        else:
            label, amount = key, value
        extra.append(
            {"key": str(key), "label": _json_value(label), "value": _json_value(amount)}
        )
    return {
        "view_count": stats.view_count,
        "like_count": stats.like_count,
        "collect_count": stats.collect_count,
        "share_count": stats.share_count,
        "comment_count": stats.comment_count,
        "extra": extra,
    }


async def _serialize_content(
    item: ContentItem, *, is_cover: bool = False
) -> dict[str, Any]:
    if isinstance(item, str):
        return {"type": "text", "text": item}
    if isinstance(item, ImageContent):
        content = {
            "type": "cover" if is_cover else "image",
            "src": await safe_src(item),
            "layout": item.layout,
            "is_live": False,
            "source_url": _task_url(item),
        }
        if is_cover:
            content["alt"] = "专辑封面"
        return content
    if isinstance(item, LivePhotoContent):
        return {
            "type": "live_photo",
            "src": await safe_src(item, "get_base"),
            "layout": "grid",
            "is_live": True,
            "source_url": _task_url(item),
        }
    if isinstance(item, GraphicContent):
        content = {
            "type": "cover" if is_cover else "graphic",
            "src": await safe_src(item),
            "alt": item.alt,
            "source_url": _task_url(item),
        }
        if is_cover:
            content["layout"] = "grid"
            content["is_live"] = False
        return content
    if isinstance(item, StickerContent):
        return {
            "type": "sticker",
            "src": await safe_src(item, return_none_on_fail=True),
            "size": item.size,
            "description": item.desc,
            "source_url": _task_url(item),
        }
    if isinstance(item, VideoContent):
        return {
            "type": "video",
            "src": await safe_src(item, "get_cover_path"),
            "duration": item.display_duration,
            "size": await _display_size(item),
            "source_url": _task_url(item),
        }
    if isinstance(item, AudioContent):
        return {
            "type": "audio",
            "duration": item.display_duration,
            "size": await _display_size(item),
            "source_url": _task_url(item),
        }
    if isinstance(item, LinkContent):
        return {
            "type": "link",
            "url": item.url,
            "title": item.title,
            "site_name": item.site_name,
            "description": item.description,
            "icon": await safe_src(item, "get_icon_path", return_none_on_fail=True),
            "preview": await safe_src(
                item, "get_preview_path", return_none_on_fail=True
            ),
        }
    if isinstance(item, QuoteContent):
        return {
            "type": "quote",
            "text": item.text,
            "title": item.title,
            "url": item.url,
            "icon": await safe_src(item, "get_icon_path", return_none_on_fail=True),
        }
    if isinstance(item, PollContent):
        total = item.option_vote_total
        return {
            "type": "poll",
            "title": item.title,
            "options": [
                {
                    "text": option.text,
                    "votes": option.votes,
                    "percentage": item.option_percentage(option, total),
                }
                for option in item.options
            ],
            "option_vote_total": total,
            "total_votes": item.total_votes,
            "total_voters": item.total_voters,
            "multiple": item.multiple,
            "closed": item.closed,
            "close_at": item.close_at,
        }
    return {"type": "unknown", "text": str(item)}


async def _display_size(item: MediaContent) -> str:
    try:
        return await item.get_display_size()
    except Exception:
        return "未知大小"


def _task_url(item: MediaContent) -> str | None:
    task = getattr(item, "path_task", None)
    url = getattr(task, "url", None)
    return url if isinstance(url, str) else None


async def _path_to_uri(value: Any) -> str:
    if hasattr(value, "as_uri"):
        with contextlib.suppress(ValueError):
            return cast(Callable[[], str], value.as_uri)()
    return (await Path(str(value)).resolve()).as_uri()


def _build_qrcode(url: str) -> str:
    qr = qrcode.QRCode(version=1, error_correction=1, box_size=10, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")  # pyright: ignore[reportCallIssue]
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"


def _escape_html(value: Any) -> Any:
    """递归转义传给主题模板的字符串值。"""
    if isinstance(value, str):
        return escape(value, quote=True)
    if isinstance(value, Mapping):
        return {
            escape(key, quote=True) if isinstance(key, str) else key: _escape_html(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [_escape_html(item) for item in value]
    return value


def _json_value(value: Any) -> Any:
    """把扩展字段限制为主题可以安全消费的 JSON-like 值"""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_value(item) for item in value]
    return str(value)
