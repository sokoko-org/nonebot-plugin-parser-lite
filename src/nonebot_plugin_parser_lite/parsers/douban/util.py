from datetime import datetime

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from ...creator import Creator
from ...data import ContentItem
from ...utils.format import (
    HTML_NEWLINE_TAGS,
    anchor_text,
    append_html_text,
    clean_clank,
)


def parse_rich_content(html: str) -> list[ContentItem]:
    soup = BeautifulSoup(html, "html.parser")

    result: list[ContentItem] = []
    buffer: list[str] = []

    for item in _iter_media_and_text(soup):
        if isinstance(item, str):
            buffer.append(item)
        else:
            if buffer:
                append_html_text(result, buffer)
                buffer.clear()
            result.append(item)

    if buffer:
        append_html_text(result, buffer)

    return result


def _iter_media_and_text(soup: BeautifulSoup):
    seen_anchors: set[int] = set()
    for element in soup.descendants:
        if isinstance(element, Tag):
            if element.name in HTML_NEWLINE_TAGS:
                yield "\n"
                continue

            if element.name == "img":
                if src := element.get("src"):
                    src = str(src)
                    yield Creator.graphic(
                        url=src,
                        ext_headers={"Referer": "https://douban.com/"},
                        use_curl_cffi=True,
                    )

        elif isinstance(element, NavigableString):
            anchor = element.find_parent("a")
            if anchor is not None and id(anchor) not in seen_anchors:
                seen_anchors.add(id(anchor))
                if text := anchor_text(anchor, "https://m.douban.com/"):
                    yield text
                continue
            if anchor is not None:
                continue
            if text := clean_clank(str(element)):
                yield text


def parse_date(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp())
