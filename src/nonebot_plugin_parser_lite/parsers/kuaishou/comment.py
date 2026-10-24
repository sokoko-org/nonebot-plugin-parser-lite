from msgspec import Struct
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Comment
from ...utils.format import (
    DEFAULT_PLACEHOLDER_PATTERN,
    format_num,
    replace_placeholder_to_sticker,
)


class KsComment(Struct):
    content: str
    timestamp: int
    likedCount: int
    comment_id: int
    headurl: str
    author_name: str
    user_id: int
    subCommentCount: int = 0
    authorArea: str | None = None


class SubCommentList(Struct):
    subComments: list[KsComment]
    """子评论列表"""


def _build_comment(comment: KsComment, *, include_reply_count: bool = False) -> Comment:
    return Creator.comment(
        author=Creator.author(
            name=comment.author_name,
            avatar_url=comment.headurl,
            avatar_cache_key=f"kuaishou:{comment.user_id}",
            location=comment.authorArea,
        ),
        content=replace_placeholder_to_sticker(
            comment.content, DEFAULT_PLACEHOLDER_PATTERN, "kuaishou"
        ),
        timestamp=comment.timestamp // 1000,
        stats=Creator.stats(
            like_count=format_num(comment.likedCount),
            comment_count=(
                format_num(comment.subCommentCount) if include_reply_count else None
            ),
        ),
    )


class CommentList(Struct):
    subCommentsMap: dict[str, SubCommentList]
    """子评论映射, {父评论id: 子评论列表}"""
    rootComments: list[KsComment]
    """父评论列表"""

    @property
    def comment_list(self) -> list[Comment]:
        """格式化评论"""
        result: list[Comment] = []
        for root in self.rootComments:
            root_comment = _build_comment(root, include_reply_count=True)
            if replies := self.subCommentsMap.get(str(root.comment_id)):
                root_comment.replies.extend(
                    _build_comment(reply) for reply in replies.subComments
                )
            result.append(root_comment)
        return result


decoder = Decoder(CommentList)


def decode_comments(data: bytes) -> list[Comment]:
    return decoder.decode(data).comment_list
