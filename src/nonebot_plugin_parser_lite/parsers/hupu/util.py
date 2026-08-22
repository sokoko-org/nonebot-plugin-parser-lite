from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from ...creator import Creator
from ...data import ContentItem


def parse_rich_content(html: str) -> list[ContentItem]:
    soup = BeautifulSoup(html, "html.parser")

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
                video_url = str(element.get("src"))
                stable_url = (
                    urlparse(video_url)._replace(query="", fragment="").geturl()
                )
                yield Creator.video(
                    url_or_task=video_url,
                    cover_url=str(element.get("poster")),
                    cache_key=f"hupu:{stable_url}",
                )
                element.decompose()
                continue

            if element.name == "img":
                if src := (
                    element.get("data-gif")
                    or element.get("data-src")
                    or element.get("src")
                ):
                    yield Creator.graphic(url=str(src))

        elif isinstance(element, NavigableString):
            if text := str(element).strip():
                yield text
