from datetime import datetime
from urllib.parse import urljoin

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
    skip_parent: Tag | None = None
    for element in soup.descendants:
        if skip_parent:
            if element in skip_parent.descendants:
                continue
            else:
                skip_parent = None
        if isinstance(element, Tag):
            if element.name == "aside" and "quote" in (element.get("class") or []):
                if quote := _parse_quote(element):
                    yield quote
                skip_parent = element
                continue

            if element.name == "aside" and "onebox" in (element.get("class") or []):
                if link := _parse_onebox(element):
                    yield link
                skip_parent = element
                continue

            if element.name == "a" and not element.find("img"):
                if text := anchor_text(element, "https://linux.do/"):
                    yield text
                    skip_parent = element
                    continue

            if element.name == "span" and (
                "filename" in (element.get("class") or [])
                or "informations" in (element.get("class") or [])
            ):
                skip_parent = element
                continue

            if element.name in HTML_NEWLINE_TAGS:
                yield "\n"
                continue

            if element.name == "img":
                if src := element.get("src"):
                    src = urljoin("https://linux.do/", str(src))
                    classes = element.get("class") or []
                    if "emoji" in classes:
                        yield Creator.sticker(
                            url=src,
                            desc=element.get("alt", None),  # pyright: ignore[reportArgumentType]
                            size="small",
                            ext_headers={"Referer": "https://linux.do/"},
                            use_curl_cffi=True,
                        )
                    else:
                        yield Creator.image(
                            url=src,
                            ext_headers={"Referer": "https://linux.do/"},
                            use_curl_cffi=True,
                        )

        elif isinstance(element, NavigableString):
            if text := clean_clank(str(element)):
                yield text


def _parse_quote(aside: Tag):
    """将 Discourse quote 映射为引用内容，并避免重复解析内部节点"""
    title_link = aside.select_one(".quote-title__text-content a[href]")
    blockquote = aside.find("blockquote")
    icon = aside.select_one(".title img.avatar[src]")

    title = title_link.get_text(" ", strip=True) if title_link else None
    if not title:
        display_name = aside.get("data-display-name")
        if isinstance(display_name, str):
            title = display_name.strip() or None
    url = (
        urljoin("https://linux.do/", str(title_link.get("href")))
        if title_link
        else None
    )
    text = ""
    if blockquote:
        text = "\n".join(
            line.strip()
            for line in blockquote.get_text("\n", strip=True).splitlines()
            if line.strip()
        )
    if not any((title, url, text)):
        return None

    icon_url = urljoin("https://linux.do/", str(icon.get("src"))) if icon else None
    return Creator.quote(
        text=text,
        title=title,
        url=url,
        icon_url=icon_url,
        ext_headers={"Referer": "https://linux.do/"},
        use_curl_cffi=True,
        cache_key=f"linuxdo:quote:{url}" if url else None,
    )


def _parse_onebox(aside: Tag):
    """将 Discourse onebox 映射为带摘要和图片的链接卡片"""
    source_link = aside.select_one("header.source a[href]")
    title_link = aside.select_one(".onebox-body h3 a[href]")
    description = aside.select_one(".onebox-body p")
    icon = aside.select_one("header.source img.site-icon[src]")
    preview = aside.select_one(".onebox-body img.thumbnail[src]")

    raw_url = aside.get("data-onebox-src")
    if not raw_url and title_link:
        raw_url = title_link.get("href")
    if not raw_url and source_link:
        raw_url = source_link.get("href")
    if not raw_url:
        return None

    url = urljoin("https://linux.do/", str(raw_url))
    title = title_link.get_text(" ", strip=True) if title_link else None
    site_name = source_link.get_text(" ", strip=True) if source_link else None
    description_text = description.get_text(" ", strip=True) if description else None
    icon_url = urljoin("https://linux.do/", str(icon.get("src"))) if icon else None
    preview_url = (
        urljoin("https://linux.do/", str(preview.get("src"))) if preview else None
    )
    return Creator.link(
        url=url,
        title=title or site_name or url,
        site_name=site_name,
        description=description_text,
        icon_url=icon_url,
        preview_url=preview_url,
        ext_headers={"Referer": "https://linux.do/"},
        use_curl_cffi=True,
        cache_key=f"linuxdo:onebox:{url}",
    )


def parse_date(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())
