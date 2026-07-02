from __future__ import annotations

from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Comment
from ...utils.format import format_num
from .structed_content import build_body


class Reply(Struct):
    post_id: str
    reply_id: str
    struct_content: str
    created_at: int
    updated_at: int

    @property
    def content(self):
        return build_body(self.struct_content)


class User(Struct):
    uid: str
    nickname: str
    avatar_url: str
    gender: int
    ip_region: str


class Stat(Struct):
    reply_num: int
    """回复该用户的回复数"""
    sub_num: int
    """总回复数"""
    like_num: int


class CommentData(Struct):
    reply: Reply
    user: User
    stat: Stat
    sub_replies: list[CommentData]


class ResponseData(Struct):
    _list: list[CommentData] = field(name="list")


class Response(Struct):
    retcode: int
    message: str
    data: ResponseData

    @property
    def comments(self):
        def to_author(user: User):
            return Creator.author(
                name=user.nickname,
                avatar_url=user.avatar_url,
                id=user.uid,
                location=user.ip_region,
            )

        def to_stats(stat: Stat):
            return Creator.stats(
                like_count=format_num(stat.like_num),
                comment_count=format_num(stat.sub_num),
            )

        def build_comment(node: CommentData):
            return Creator.comment(
                author=to_author(node.user),
                content=node.reply.content,
                stats=to_stats(node.stat),
                timestamp=node.reply.updated_at,
            )

        comments: list[Comment] = []
        for comment in self.data._list:
            c = build_comment(comment)
            if comment.sub_replies:
                for sub in comment.sub_replies:
                    c.add_reply(build_comment(sub))
            comments.append(c)
        return comments


decoder = Decoder(Response)
