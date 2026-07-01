import json
import re
from typing import Literal

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from msgspec import Struct, field

from ...constants import STICKER_CDN
from ...creator import Creator
from ...data import ContentItem
from ...utils.format import replace_placeholder_to_sticker

HEYBOX_PATTERN = re.compile(r"\[(?P<name>[^]]+)\]")


def size_resolver(name: str) -> Literal["small", "medium"]:
    return "medium" if "bigemoji" in name else "small"


class User(Struct):
    avatar: str
    username: str
    userid: str | int

    @property
    def avatar_url(self) -> str:
        return self.avatar + "\\" if "?" in self.avatar else self.avatar


class Img(Struct):
    url: str


class CommentItem(Struct):
    is_cy: int
    """是否插眼"""
    create_at: int
    text: str
    ip_location: str
    child_num: int
    """评论数"""
    up: int
    """点赞数"""
    user: User
    imgs: list[Img] = field(default_factory=list)

    @property
    def content(self) -> list[ContentItem]:
        content = replace_placeholder_to_sticker(
            self.text, HEYBOX_PATTERN, "heybox", size_resolver
        )
        for img in self.imgs:
            content.append(Creator.image(url=img.url + "\\"))
        if self.is_cy:
            content.append(
                Creator.sticker(
                    url=STICKER_CDN.format(platform="heybox", name="cy"),
                    size="small",
                    desc="插眼",
                )
            )
        return content


class CommentData(Struct):
    comment: list[CommentItem]
    """第一个是主评论，后面都是回复"""


class Link(Struct):
    has_video: int
    """是否有视频，无视频则text为json，否则为str"""
    title: str
    description: str
    """纯文本内容"""
    text: str
    """可能的富文本内容"""
    ip_location: str
    click: int
    """浏览数"""
    comment_num: int
    """评论数"""
    create_at: int
    """创建时间"""
    favour_count: int
    """收藏数"""
    link_award_num: int
    """点赞数"""
    forward_num: int
    """转发数"""
    user: User
    video_url: str | None = None
    video_thumb: str | None = None

    @property
    def content(self) -> list[ContentItem]:
        """格式化的富文本内容"""
        content: list[ContentItem] = []
        try:
            parts = json.loads(self.text)
            for part in parts:
                if part["type"] == "html":
                    content.extend(extract_from_html(part["text"]))

                    break
                if part["type"] == "text":
                    content.extend(
                        replace_placeholder_to_sticker(
                            part["text"], HEYBOX_PATTERN, "heybox", size_resolver
                        )
                    )
                elif part["type"] == "img":
                    content.append(Creator.image(url=part["url"] + "\\"))
        except (json.JSONDecodeError, TypeError):
            content.append(self.text)
        if self.has_video and self.video_url and self.video_thumb:
            content.append(
                Creator.video(url_or_task=self.video_url, cover_url=self.video_thumb)
            )
        return content


class BaseResult(Struct):
    comments: list[CommentData]
    link: Link


def extract_from_html(html: str) -> list[ContentItem]:
    """
    从 HTML 内容中按顺序提取纯文本和图片

    :param html: 包含知乎内容的 HTML 字符串。
    :return: 由纯文本字符串和 ContentItem 对象组成的列表
    """

    soup = BeautifulSoup(html.replace(r"\"", '"'), "html.parser")

    # 忽略 <noscript> 中的内容，避免重复或无效的占位文本干扰顺序
    for noscript in soup.find_all("noscript"):
        noscript.decompose()

    result: list[ContentItem] = []

    for element in soup.descendants:
        # 处理图片标签
        if isinstance(element, Tag) and element.name == "img":
            attrs: dict[str, str] = {
                str(k): str(v[0] if isinstance(v, list) and v else v)
                for k, v in (element.attrs or {}).items()
                if v is not None
            }
            if src := (
                attrs.get("data-original")
                or attrs.get("data-actualsrc")
                or attrs.get("data-default-watermark-src")
            ):
                result.append(
                    Creator.image(
                        url=src,
                    )
                )
        # 处理纯文本节点
        elif isinstance(element, NavigableString):
            if text := str(element).strip():
                result.append(text)

    return result
