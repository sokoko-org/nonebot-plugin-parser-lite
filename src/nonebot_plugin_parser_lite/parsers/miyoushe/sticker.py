from pathlib import Path
import re

import ujson

from ...creator import ContentItem, Creator

STICKER_PATTERN = re.compile(r"_\((.+?)\)")
STICKER_MAP: dict[str, str] = {}
STICKER_PATH = Path(__file__).parent / "sticker.json"


def replace_sticker(s: str) -> list[ContentItem]:
    global STICKER_MAP
    content: list[ContentItem] = []
    last_end = 0
    if not STICKER_MAP:
        STICKER_MAP = ujson.loads(STICKER_PATH.read_text())

    for m in STICKER_PATTERN.finditer(s):
        start, end = m.span()
        if start > last_end:
            if txt := s[last_end:start]:
                content.append(txt)

        name = m[1]
        if url := STICKER_MAP.get(name):
            content.append(Creator.sticker(url=url, desc=name))
        else:
            raw = s[start:end]
            content.append(raw)

        last_end = end

    if last_end < len(s):
        if tail := s[last_end:]:
            content.append(tail)

    return content
