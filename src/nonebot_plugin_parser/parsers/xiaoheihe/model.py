import re

from msgspec import Struct, field
import json

from ..creator import create_image, create_sticker, create_video
from ..data import MediaContent
from .sticker_map import EMOJI_MAP


class User(Struct):
    avatar: str
    username: str
    userid: str | int

    @property
    def avatar_url(self) -> str:
        return self.avatar + "\\"


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
    def content(self) -> list[MediaContent | str]:
        content = format_sticker(self.text)
        for img in self.imgs:
            content.append(create_image(url=img.url + "\\"))
        if self.is_cy:
            content.append(
                create_sticker(
                    url="https://imgheybox.max-c.com/oa/2024/10/31/ce360d2affd7976e27e5c68a3de676c7.png",
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
    def content(self) -> list[MediaContent | str]:
        """格式化的富文本内容"""
        content: list[MediaContent | str] = []
        try:
            parts = json.loads(self.text)
            for part in parts:
                if part["type"] == "text":
                    content.extend(format_sticker(part["text"]))
                elif part["type"] == "img":
                    content.append(create_image(url=part["url"] + "\\"))
        except (json.JSONDecodeError, TypeError):
            content.append(self.text)
        if self.has_video and self.video_url and self.video_thumb:
            content.append(
                create_video(url_or_task=self.video_url, cover_url=self.video_thumb)
            )
        return content


class BaseResult(Struct):
    comments: list[CommentData]
    link: Link


_STICKER_PATTERN = re.compile(r"\[(?P<name>[^]]+)\]")


def format_sticker(text: str) -> list[MediaContent | str]:
    """
    将包含小黑盒表情占位符的文本拆分为文本与图片。表情格式形如「[cube_开心]」，先整体按中括号匹配，再解析内部的 group_name 和 code。

    :param text: 可能包含表情占位符的原始文本，如 "你好[cube_开心]呀"。
    :return: 由普通文本和 MediaContent 组成的列表，顺序与原字符串一致。
    """
    if "[" not in text or "]" not in text or not _STICKER_PATTERN.search(text):
        return [text]

    result: list[MediaContent | str] = []
    last_pos = 0

    for match in _STICKER_PATTERN.finditer(text):
        start, end = match.span()
        if start > last_pos:
            if plain := text[last_pos:start]:
                result.append(plain)

        group_name = match["name"]
        if img_url := EMOJI_MAP.get(group_name):
            result.append(create_sticker(url=img_url, size="small"))
        else:
            result.append(match[0])

        last_pos = end

    # 最后剩余的纯文本
    if last_pos < len(text):
        if tail := text[last_pos:]:
            result.append(tail)

    return result
