from enum import IntEnum

from msgspec import Struct
from msgspec.json import Decoder

from ...creator import Creator
from ...utils.format import format_num
from .structed_content import build_body


class ViewType(IntEnum):
    VIDEO = 5
    IMAGE = 2
    TEXT = 1


class Post(Struct):
    post_id: str
    subject: str
    structured_content: str
    images: list[str]
    created_at: int
    updated_at: int
    view_type: ViewType

    @property
    def content(self):
        content = build_body(self.structured_content)
        if self.view_type == ViewType.IMAGE:
            content.extend(Creator.images(self.images))
        return content


class Forum(Struct):
    id: int
    name: str
    icon: str


class User(Struct):
    uid: str
    nickname: str
    introduce: str
    gender: int
    avatar_url: str


class Stat(Struct):
    view_num: int
    reply_num: int
    like_num: int
    bookmark_num: int
    forward_num: int
    share_num: int


class PostData(Struct):
    post: Post
    forum: Forum
    user: User
    stat: Stat


class ResponseData(Struct):
    post: PostData


class Response(Struct):
    retcode: int
    message: str
    data: ResponseData

    @property
    def post(self):
        return self.data.post.post

    @property
    def forum(self):
        return self.data.post.forum

    @property
    def user(self):
        return self.data.post.user

    @property
    def stat(self):
        return self.data.post.stat

    @property
    def stats(self):
        return Creator.stats(
            view_count=format_num(self.stat.view_num),
            like_count=format_num(self.stat.like_num),
            collect_count=format_num(self.stat.bookmark_num),
            share_count=format_num(self.stat.share_num + self.stat.forward_num),
            comment_count=format_num(self.stat.reply_num),
        )


decoder = Decoder(Response)
