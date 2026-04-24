from msgspec import Struct

from ..data import MediaContent
from ..creator import create_graphic, create_video
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
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
    def content(self) -> list[MediaContent | str]:
        """按 DOM 顺序依次产出文本 / 图片 / 视频内容列表。"""
        data: list[MediaContent | str] = []
        soup = BeautifulSoup(self.body, "html.parser")

        for element in list(soup.descendants):
            # 标签节点
            if isinstance(element, Tag):
                # 视频卡片：整体视为一个单元
                if element.name == "div" and "video-content" in (
                    element.get("class") or []
                ):
                    # 结构约定：video-content 内必含一个 <img> 封面和 data-src 视频地址
                    img = element.find("img")
                    if img is None:
                        continue
                    thumb = str(img.attrs["src"])
                    video_attr = element.attrs["data-src"]
                    video = str(video_attr)
                    data.append(
                        create_video(
                            url_or_task=video,
                            cover_url=thumb,
                        )
                    )
                    # 处理完后从 DOM 树移除该节点，避免内部 img 被再次当作普通图处理
                    element.decompose()
                    continue

                # 图片
                if element.name == "img":
                    if src_attr := element.attrs.get("data-original"):
                        src = str(src_attr)
                        data.append(create_graphic(image_url=src))

            elif isinstance(element, NavigableString):
                if text := str(element).strip():
                    data.append(text)

        return data
