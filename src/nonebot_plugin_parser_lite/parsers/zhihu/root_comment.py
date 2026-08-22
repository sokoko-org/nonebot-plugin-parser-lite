import re

from bs4 import BeautifulSoup
from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import ImageContent
from ...utils.format import replace_placeholder_to_sticker

ZHIHU_PATTERN = re.compile(r"\[(?P<name>[^]]+)\]")


class Counts(Struct):
    total_counts: int
    collapsed_counts: int
    """被折叠评论数"""


class Tag(Struct):
    type: str
    text: str
    color: str
    """hex"""


class Author(Struct):
    id: str
    url_token: str
    avatar_url: str
    url: str
    gender: int
    headline: str
    name: str


class Comment(Struct):
    id: str
    raw_content: str = field(name="content")
    hot: bool
    created_time: int
    url: str
    """api"""
    reply_root_comment_id: str
    reply_comment_id: str
    like_count: int
    child_comment_count: int
    comment_tag: list[Tag]
    author: Author

    @property
    def content(self):
        """
        解析评论文本与图片：

        - 文本部分：保留原始文字与表情占位符（例如 `[捂脸]`），并转换为贴纸。
        - 图片部分：识别 `<a class="comment_img" href="...">` 并提取为图片媒体。
        """
        soup = BeautifulSoup(self.raw_content, "html.parser")

        images: list[ImageContent] = []
        for a in soup.find_all("a", class_="comment_img"):
            href = a.get("href")
            if not isinstance(href, str) or not href:
                continue
            images.append(Creator.image(href))

        text = soup.get_text()
        parts = replace_placeholder_to_sticker(text, ZHIHU_PATTERN, "zhihu")
        return parts + images

    @property
    def ip_info(self):
        return next(
            (tag.text for tag in self.comment_tag if tag.type == "ip_info"), None
        )


class RootComment(Struct):
    counts: Counts
    data: list[Comment]


decoder = Decoder(RootComment)
