from __future__ import annotations

from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Comment, ContentItem
from ...utils.format import format_num


class UserData(Struct):
    username: str
    domain: str
    avatar_url: str


class FComment(Struct):
    pid: str
    likes: int
    html: str = field(name="content")
    dateline: str
    user_data: UserData
    images: list[str] | None
    children: list[FComment] | None = None

    @property
    def content(self) -> list[ContentItem]:
        content: list[ContentItem] = [
            self.html.split("<***>", 1)[0].split("<end>", 1)[0]
        ]
        if images := self.images:
            content.extend(Creator.images(images))
        return content


class ShareData(Struct):
    share_url: str


class VideoData(Struct):
    video_cover: str | None = None
    video_url: str | None = None


class Post(Struct):
    tid: str
    type: str
    """0-文字,2-视频"""
    domain: str
    username: str
    avatar_url: str
    title: str
    dateline: str
    topic_likes_count: str
    images: list[str] | None
    hits: str
    intro_text: str
    forward: str
    topic_favorites: str
    share_data: ShareData
    video_data: VideoData

    @property
    def author(self):
        return Creator.author(
            name=self.username,
            avatar_url=self.avatar_url,
            id=self.domain,
        )

    @property
    def timestamp(self):
        return int(self.dateline)

    @property
    def url(self):
        return self.share_data.share_url

    @property
    def content(self):
        content: list[ContentItem] = [self.intro_text.split("<img", 1)[0]]
        if images := self.images:
            content.extend(Creator.images(images))
        if video_url := self.video_data.video_url:
            content.append(
                Creator.video(
                    url_or_task=video_url,
                    cover_url=self.video_data.video_cover,
                )
            )
        return content


class CommentList(Struct):
    total: int
    _list: list[FComment] | None = field(name="list")

    @property
    def comments(self):
        if not self._list:
            return []

        def to_author(fd: FComment):
            return Creator.author(
                name=fd.user_data.username,
                id=fd.user_data.domain,
                avatar_url=fd.user_data.avatar_url,
            )

        def to_comment(fd: FComment):
            return Creator.comment(
                author=to_author(fd),
                content=fd.content,
                timestamp=int(fd.dateline),
                stats=Creator.stats(like_count=format_num(fd.likes)),
            )

        result: list[Comment] = []
        for c in self._list:
            root = to_comment(c)
            if children := c.children:
                for sc in children:
                    root.add_reply(to_comment(sc))
            result.append(root)
        return result


class Data(Struct):
    content: Post
    comments: CommentList


class Response(Struct):
    success: bool
    errcode: int
    data: Data

    @property
    def post(self):
        return self.data.content

    @property
    def stats(self):
        return Creator.stats(
            like_count=self.post.topic_likes_count,
            share_count=self.post.forward,
            comment_count=format_num(self.data.comments.total),
            collect_count=self.post.topic_favorites,
            view_count=self.post.hits,
        )

    @property
    def author(self):
        return self.post.author

    @property
    def timestamp(self) -> int:
        return self.post.timestamp

    @property
    def url(self) -> str:
        return self.post.url

    @property
    def content(self) -> list[ContentItem]:
        return self.post.content

    @property
    def title(self) -> str:
        return self.post.title

    @property
    def comments(self) -> list[Comment]:
        return self.data.comments.comments


decoder = Decoder(Response)
