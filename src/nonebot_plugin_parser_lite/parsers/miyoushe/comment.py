from __future__ import annotations

from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Comment, ContentItem
from ...utils.format import format_num
from .sticker import replace_sticker
from .structed_content import decode_structed_content


class Reply(Struct):
    post_id: str
    reply_id: str
    struct_content: str
    created_at: int
    updated_at: int

    @property
    def content(self):
        content: list[ContentItem] = []
        data = decode_structed_content(self.struct_content)
        for item in data:
            ins = item.insert
            if isinstance(ins, str):
                if ins.strip():
                    content.extend(replace_sticker(ins))
            elif v := ins.vod:
                content.append(
                    Creator.video(
                        url_or_task=v.resolutions[0].url,
                        cover_url=v.cover,
                        duration=v.duration,
                    )
                )
            elif link := ins.link_card:
                content.append(
                    Creator.link(
                        text=link.title,
                        url=link.origin_url,
                    )
                )
            elif url := ins.image:
                content.append(Creator.image(url=url))
            elif custom_emoticon := ins.custom_emoticon:
                content.append(
                    Creator.sticker(
                        url=custom_emoticon.url,
                        desc=ins.backup_text,
                    )
                )
        return content


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
