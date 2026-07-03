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

            if element.name == "video":
                yield Creator.video(
                    url_or_task=str(element.get("src")),
                    cover_url=str(element.get("poster")),
                )
                element.decompose()
                continue

            if element.name == "img":
                attrs: dict[str, str] = {
                    str(k): str(v[0] if isinstance(v, list) and v else v)
                    for k, v in (element.attrs or {}).items()
                    if v
                }
                if src := (
                    attrs.get("data-gif") or attrs.get("data-src") or attrs.get("src")
                ):
                    yield Creator.graphic(url=src)

        elif isinstance(element, NavigableString):
            if text := str(element).strip():
                yield text
