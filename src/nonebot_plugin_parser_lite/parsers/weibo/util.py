import re

from bs4 import BeautifulSoup, Comment, Tag
from bs4.element import NavigableString, PageElement

_CARD_ICON_RE = re.compile(r"timeline_card_small_([a-z0-9]+)", re.I)

_ENTITY_CARD_LABELS = {
    "super": "超话",
}


def _attr_str(value: str | list[str] | None) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def _entity_label_from_card(a: Tag) -> str | None:
    for img in a.find_all("img"):
        src = _attr_str(img.get("src"))
        if m := _CARD_ICON_RE.search(src):
            return _ENTITY_CARD_LABELS.get(m.group(1).lower())
    return None


def weibo_long_html_to_raw(html: str) -> str:
    """将微博 HTML 转为纯文本"""
    soup = BeautifulSoup(html, "html.parser")
    parts: list[str] = []

    def walk(node: BeautifulSoup | PageElement) -> None:
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            parts.append(str(node))
            return
        if not isinstance(node, Tag):
            return

        if node.name == "br":
            parts.append("\n")
            return

        if node.name == "img":
            if alt := _attr_str(node.get("alt")):
                parts.append(alt)
            return

        if node.name == "a":
            surl = node.find("span", class_="surl-text")
            if isinstance(surl, Tag):
                title = surl.get_text(strip=True)
                if title and (label := _entity_label_from_card(node)):
                    parts.append(f"#{title}[{label}]#")
                    return
                data_url = _attr_str(node.get("data-url"))
                if data_url.startswith(("http://t.cn/", "https://t.cn/")):
                    parts.append(data_url)
                    return
                parts.append(title or node.get_text())
                return
            parts.append(node.get_text())
            return

        for child in node.children:
            walk(child)

    walk(soup)
    return "".join(parts)
