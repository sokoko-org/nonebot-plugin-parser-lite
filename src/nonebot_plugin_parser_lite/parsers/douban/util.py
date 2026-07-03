from datetime import datetime

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from ...creator import Creator
from ...data import ContentItem


def parse_rich_content(html: str) -> list[ContentItem]:
    soup = BeautifulSoup(html.replace(r"\"", '"'), "html.parser")

    result: list[ContentItem] = []
    buffer: list[str] = []

    for item in _iter_media_and_text(soup):
        if isinstance(item, str):
            buffer.append(item)
        else:
            if buffer:
                text_block = "".join(buffer)
                lines = [line.rstrip() for line in text_block.splitlines()]
                if normalized := "\n".join(lines).strip():
                    result.append(normalized)
                buffer.clear()
            result.append(item)

    if buffer:
        text_block = "".join(buffer)
        lines = [line.rstrip() for line in text_block.splitlines()]
        if normalized := "\n".join(lines).strip():
            result.append(normalized)

    return result


def _iter_media_and_text(soup: BeautifulSoup):
    for element in soup.descendants:
        if isinstance(element, Tag):
            if element.name == "p":
                yield "\n"
                continue

            if element.name == "br":
                yield "\n"
                continue

            if element.name == "img":
                attrs: dict[str, str] = {
                    str(k): str(v[0] if isinstance(v, list) and v else v)
                    for k, v in (element.attrs or {}).items()
                    if v
                }
                if src := attrs.get("src"):
                    yield Creator.graphic(
                        url=src,
                        ext_headers={"Referer": "https://douban.com/"},
                        use_curl_cffi=True,
                    )

        elif isinstance(element, NavigableString):
            if text := str(element).strip():
                yield text


def parse_date(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp())
