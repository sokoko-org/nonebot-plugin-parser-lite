import re

from msgspec import Struct, field

from ...utils.format import replace_placeholder_to_sticker

KUAISHOU_PATTERN = re.compile(r"\[(?P<name>[^]]+)\]")


class VisionRootCommentItem(Struct):
    commentId: str
    authorId: str
    authorName: str
    text: str = field(name="content")
    headurl: str
    timestamp: int
    """ms"""
    likedCount: str

    @property
    def content(self):
        return replace_placeholder_to_sticker(self.text, KUAISHOU_PATTERN, "kuaishou")


class VisionRootCommentFeed(Struct):
    commentCountV2: int
    rootCommentsV2: list[VisionRootCommentItem]
