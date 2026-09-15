from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
from msgspec import Struct

from ...creator import Creator
from ...data import ContentItem
from ...utils.format import (
    HTML_NEWLINE_TAGS,
    append_html_text,
    clean_clank,
    replace_anchor_hrefs,
)
from .share import ShareData


class News(Struct):
    author: str
    user_id: str
    avatar: str
    body: str
    ip_location: str
    publish_time: int
    replies: int
    title: str
    ups_num: int
    views: int
    share_data: ShareData

    @property
    def content(self) -> list[ContentItem]:
        """按 DOM 顺序依次产出文本 / 图片 / 视频内容列表"""
        data: list[ContentItem] = []
        soup = BeautifulSoup(self.body, "html.parser")
        replace_anchor_hrefs(soup, "https://buff.163.com/")

        text_buffer: list[str] = []

        def flush_text() -> None:
            append_html_text(data, text_buffer)
            text_buffer.clear()

        for element in soup.descendants:
            # 标签节点
            if isinstance(element, Tag):
                if element.name in HTML_NEWLINE_TAGS:
                    text_buffer.append("\n")
                    continue
                if element.name == "div" and "video-content" in (
                    element.get("class") or []
                ):
                    # data-src 一定存在
                    video = str(element["data-src"])
                    # div 下面必含一个 img 封面（第一个 img 即封面）
                    imgs = element.find_all("img")
                    if not imgs:
                        continue
                    flush_text()
                    cover_img = imgs[0]
                    thumb = str(cover_img["src"])

                    data.append(
                        Creator.video(
                            url_or_task=video,
                            cover_url=thumb,
                        )
                    )
                    # 处理完后从 DOM 树移除该节点，避免内部 img 再被当作普通图处理
                    element.decompose()
                    continue

                # 普通图片
                if element.name == "img":
                    if src_attr := element.get("data-original"):
                        flush_text()
                        data.append(Creator.graphic(url=str(src_attr)))

            elif isinstance(element, NavigableString):
                if text := clean_clank(str(element)):
                    text_buffer.append(text)

        flush_text()

        return data
