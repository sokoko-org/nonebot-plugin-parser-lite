from urllib.parse import urljoin

from msgspec import Struct
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Comment
from ...utils.format import format_num
from .util import parse_date, parse_rich_content


class Post(Struct):
    username: str
    """用户名"""
    display_username: str | None
    """昵称(可能没设置)"""
    created_at: str
    cooked: str
    """html(空需要过滤)"""
    avatar_template: str
    reply_count: int
    """该post的回复数"""
    reaction_users_count: int
    """可以当成该post的点赞数"""

    @property
    def timestamp(self) -> int:
        return parse_date(self.created_at)

    @property
    def avatar_url(self) -> str:
        return urljoin("https://linux.do/", self.avatar_template.format(size=288))

    @property
    def content(self):
        return parse_rich_content(self.cooked)


class PostStream(Struct):
    posts: list[Post]


class Response(Struct):
    post_stream: PostStream
    title: str
    id: int
    posts_count: int
    """跟帖数,包含主贴"""
    reply_count: int
    """所有跟贴的总回复数"""
    views: int
    """所有跟帖总浏览数"""
    like_count: int

    @property
    def detail(self):
        return self.post_stream.posts[0]

    @property
    def comment_list(self) -> list[Comment]:
        return [
            Creator.comment(
                author=Creator.author(
                    name=c.display_username or c.username,
                    avatar_url=c.avatar_url,
                    ext_headers={"Referer": "https://linux.do/"},
                    use_curl_cffi=True,
                ),
                content=c.content,
                stats=Creator.stats(
                    like_count=format_num(c.reaction_users_count),
                    comment_count=format_num(c.reply_count),
                ),
                timestamp=c.timestamp,
            )
            for c in self.post_stream.posts[1:]
            if c.cooked
        ]


decoder = Decoder(Response)
