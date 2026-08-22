from __future__ import annotations

from msgspec import Struct

from ...creator import ContentItem, Creator


class Img(Struct):
    original_url: str


class Info(Struct):
    img: Img
    style: str | None = None


class Part(Struct):
    type: str | None = None
    children: list[Part] | None = None
    text: str | None = None
    info: Info | None = None


class Contents(Struct):
    json: list[Part]

    @property
    def content(self) -> list[ContentItem]:
        content: list[ContentItem] = []
        for jpart in self.json:
            if children := jpart.children:
                for cpart in children:
                    if text := cpart.text:
                        content.append(text)
                    elif info := cpart.info:
                        if cpart.type == "tap_emoji":
                            desc = cpart.children[0].text if cpart.children else None
                            content.append(
                                Creator.sticker(
                                    url=info.img.original_url,
                                    size="small"
                                    if info.style == "inline"
                                    else "medium",
                                    desc=desc,
                                )
                            )
                        else:
                            content.append(Creator.image(url=info.img.original_url))
            elif info := jpart.info:
                content.append(Creator.image(info.img.original_url))
            if jpart.type == "paragraph":
                content.append("\n")
        return content
