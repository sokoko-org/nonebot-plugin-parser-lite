from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
from msgspec import Struct

from ...creator import Creator
from ...data import ContentItem
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
        """按 DOM 顺序依次产出文本 / 图片 / 视频内容列表。"""
        data: list[ContentItem] = []
        soup = BeautifulSoup(self.body, "html.parser")

        for element in soup.descendants:
            # 标签节点
            if isinstance(element, Tag):
                if element.name == "div" and "video-content" in (
                    element.get("class") or []
                ):
                    # data-src 一定存在
                    video = str(element["data-src"])
                    # div 下面必含一个 img 封面（第一个 img 即封面）
                    imgs = element.find_all("img")
                    if not imgs:
                        continue
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
                    if src_attr := element.attrs.get("data-original"):
                        data.append(Creator.graphic(url=str(src_attr)))

            elif isinstance(element, NavigableString):
                if text := str(element).strip():
                    data.append(text)

        return data
