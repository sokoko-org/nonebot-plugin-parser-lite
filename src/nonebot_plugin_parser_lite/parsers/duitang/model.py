from msgspec import Struct


class Sender(Struct):
    id: int
    """作者id"""
    username: str
    avatar: str


class Photo(Struct):
    path: str
    """图片地址"""


class Blog(Struct):
    photo: Photo
    short_video: bool
    copyright_author_name: str
    """发布时声明的版权作者"""

class BlogData(Blog):
    msg: str
    id: int
    """blog id"""
    sender: Sender
    reply_count: int
    add_datetime_ts: int
    """秒级时间戳"""
    like_count: int
    favorite_count: int
    atlas_id: int
    """所属atlas id"""

class AtlasData(Struct):
    id: int
    """atlas id"""
    desc: str
    """描述"""
    blogs: list[Blog]
    """atlas内容"""
    favorite_count: int
    """收藏数"""
    like_count: int
    """点赞数"""
    comment_count: int
    """评论数"""
    visit_count: int
    """浏览数"""
    created_at: int
    """创建时间(毫秒)"""
    sender: Sender

    @property
    def img_list(self) -> list[str]:
        return [blog.photo.path for blog in self.blogs]


class Reply(Struct):
    sender: Sender
    content: str
    add_datetime_ts: int
    """毫秒时间戳"""
    add_datetime_str: str
    ipaddr: str


class Comment(Struct):
    sender: Sender
    content: str
    like_count: int
    reply_count: int
    photos: list[Photo]
    create_time: int
    """毫秒时间戳"""
    create_time_str: str
    replies: list[Reply]
    ipaddr: str

    @property
    def img_list(self) -> list[str]:
        return [photo.path for photo in self.photos]


class CommentData(Struct):
    object_list: list[Comment]
