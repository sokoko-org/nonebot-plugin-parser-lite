"""Validate note pages before decoding their typed data."""

import json
import re
from urllib.parse import urlsplit


class NotePageUnavailable(ValueError):
    pass


INITIAL_STATE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*(.*?)</script>", re.DOTALL)


def note_page_state(html: str, final_url: str) -> str:
    path = urlsplit(final_url).path.lower()
    if path.startswith(("/website-login/captcha", "/captcha")):
        raise NotePageUnavailable("小红书页面要求验证码，暂时无法获取正文，请稍后重试")
    if path.startswith(("/404", "/login", "/website-login")):
        raise NotePageUnavailable("该链接暂时无法从网页获取正文，请重新复制分享链接后重试")
    match = INITIAL_STATE.search(html)
    if not match:
        raise NotePageUnavailable("小红书页面未返回正文，请重新复制分享链接后重试")
    raw = match[1].strip().removesuffix(";")
    raw = re.sub(
        r'("(?:\\.|[^"\\])*")|\bundefined\b',
        lambda match: match[1] if match[1] is not None else "null",
        raw,
    )
    try:
        state = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise NotePageUnavailable("小红书页面数据格式暂不支持，请稍后重试") from exc
    root = state.get("noteData") if isinstance(state, dict) else None
    data = root.get("data") if isinstance(root, dict) else None
    note = data.get("noteData") if isinstance(data, dict) else None
    if not isinstance(note, dict) or not note:
        raise NotePageUnavailable("该链接暂时无法从网页获取正文，请重新复制分享链接后重试")
    return raw
