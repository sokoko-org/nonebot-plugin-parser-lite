from __future__ import annotations

from msgspec import Struct

from ...creator import ContentItem, Creator


class Img(Struct):
    original_url: str


class Info(Struct):
    img: Img | None = None
    style: str | None = None


class Part(Struct):
    type: str | None = None
    children: list[Part] | None = None
    text: str | None = None
    info: Info | None = None


class Contents(Struct):
    json: list[Part]

    @staticmethod
    def _append_part(part: Part, content: list[ContentItem]) -> None:
        info = part.info
        img = info.img if info else None

        if part.type == "tap_emoji":
            desc = next(
                (child.text for child in part.children or [] if child.text),
                None,
            )
            if img:
                content.append(
                    Creator.sticker(
                        url=img.original_url,
                        size="small" if info and info.style == "inline" else "medium",
                        desc=desc,
                    )
                    if desc
                    else Creator.image(url=img.original_url)
                )
            elif text := (desc or part.text):
                content.append(text)
            return

        if part.text:
            content.append(part.text)
        if img:
            content.append(Creator.image(url=img.original_url))
        if part.children:
            for child in part.children:
                Contents._append_part(child, content)

    @property
    def content(self) -> list[ContentItem]:
        content: list[ContentItem] = []
        for jpart in self.json:
            Contents._append_part(jpart, content)
            if jpart.type == "paragraph":
                content.append("\n")
        return content
