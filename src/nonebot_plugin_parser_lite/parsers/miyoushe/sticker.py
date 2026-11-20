from pathlib import Path
import re

import ujson

from ...creator import ContentItem, Creator
from ...download import DOWNLOADER
from ...path import data_dir
from ...utils.log import logger

STICKER_PATTERN = re.compile(r"_\((.+?)\)")
STICKER_MAP: dict[str, str] = {}
# 插件启动时从米游社下载的表情列表
STICKER_PATH = Path(data_dir) / "miyoushe_sticker.json"


async def update_sticker() -> None:
    """拉取米游社最新表情列表"""
    try:
        res = await DOWNLOADER.content(
            "https://bbs-api-static.miyoushe.com/misc/api/emoticon_set"
        )
        data = ujson.loads(res)["data"]["list"]
        new = {item["name"]: item["icon"] for li in data for item in li["list"]}
        STICKER_PATH.parent.mkdir(parents=True, exist_ok=True)
        STICKER_PATH.write_text(
            ujson.dumps(new, ensure_ascii=False, escape_forward_slashes=False),
            encoding="utf8",
        )
        STICKER_MAP.clear()
        STICKER_MAP.update(new)
        logger.info(f"米游社表情更新完成，共 {len(new)} 个")
    except Exception as e:
        logger.warning(f"米游社表情更新失败，使用本地表情: {e!r}")


def replace_sticker(s: str) -> list[ContentItem]:
    content: list[ContentItem] = []
    last_end = 0
    if not STICKER_MAP and STICKER_PATH.is_file():
        STICKER_MAP.update(ujson.loads(STICKER_PATH.read_text(encoding="utf8")))

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
