from msgspec import Struct
from msgspec.json import Decoder

from ...creator import ContentItem, Creator
from ...utils.format import (
    DEFAULT_PLACEHOLDER_PATTERN,
    format_num,
    replace_placeholder_to_sticker,
)
from .aweme import Author, Image


class ImageList(Struct):
    origin_url: Image


class Sticker(Struct):
    static_url: Image


class DComment(Struct):
    digg_count: int
    text: str
    user: Author
    create_time: int
    image_list: list[ImageList] | None
    reply_comment_total: int
    sticker: Sticker | None = None
    ip_label: str | None = None

    @property
    def content(self) -> list[ContentItem]:
        content: list[ContentItem] = []
        self.text = self.text.replace("[图片表情]", "")
        content.extend(
            replace_placeholder_to_sticker(
                self.text, DEFAULT_PLACEHOLDER_PATTERN, "douyin"
            )
        )
        if image_list := self.image_list:
            content.extend(
                Creator.image(
                    url=image.origin_url.url_list[-1],
                    cache_key=(
                        f"douyin:{image.origin_url.uri}"
                        if image.origin_url.uri
                        else None
                    ),
                    ext_headers={"Referer": "https://www.douyin.com/"},
                )
                for image in image_list
            )
        if sticker := self.sticker:
            content.append(
                Creator.image(
                    url=sticker.static_url.url_list[-1],
                    cache_key=(
                        f"douyin:{sticker.static_url.uri}"
                        if sticker.static_url.uri
                        else None
                    ),
                    ext_headers={"Referer": "https://www.douyin.com/"},
                )
            )
        return content


class Response(Struct):
    comments: list[DComment]

    @property
    def comment_list(self):
        return [
            Creator.comment(
                author=Creator.author(
                    name=comment.user.nickname,
                    avatar_url=comment.user.avatar_thumb.url_list[-1],
                    avatar_cache_key=f"douyin:{comment.user.uid}",
                    location=comment.ip_label,
                ),
                content=comment.content,
                timestamp=comment.create_time,
                stats=Creator.stats(
                    like_count=format_num(comment.digg_count),
                    comment_count=format_num(comment.reply_comment_total),
                ),
            )
            for comment in self.comments
        ]


decoder = Decoder(Response)
