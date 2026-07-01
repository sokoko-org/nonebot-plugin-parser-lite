from enum import IntEnum
import json

from bs4 import BeautifulSoup
from msgspec import Struct

from ...creator import Creator
from ...data import ContentItem


class PostType(IntEnum):
    DOCUMENT = 1
    """文档"""
    PHOTO = 2
    """含有图片"""
    MUSIC = 3
    """音乐"""


class BlogInfo(Struct):
    blogId: int
    """用户id"""
    blogName: str
    """用户名"""
    blogNickName: str
    """用户昵称"""
    bigAvaImg: str
    """头像"""
    homePageUrl: str
    """主页url"""


class PostCount(Struct):
    responseCount: int
    """评论数"""
    favoriteCount: int
    """点赞数"""
    shareCount: int
    """分享数"""
    reblogCount: int
    """转载数"""
    postHot: int
    """热度"""


class Post(Struct):
    type: PostType
    """post类型"""
    blogId: int
    """用户id"""
    title: str
    """标题"""
    publishTime: int
    """发布时间(ms)"""
    tag: str
    """标签(多个标签用,分隔)"""
    tagList: list[str]
    """标签列表"""
    content: str
    """文本内容(html)"""
    blogInfo: BlogInfo
    """用户信息"""
    postCount: PostCount
    """统计信息"""
    # postCollection: dict
    # """post所属合集，这里不再解析了，可能为空"""
    ipLocation: str
    """IP归属地"""
    photoLinks: str
    """图片链接信息，需要json解析"""

    @property
    def text(self) -> str:
        soup = BeautifulSoup(self.content, "html.parser")
        return soup.get_text("\n", strip=True)

    @property
    def medias(self) -> list[ContentItem]:
        return [Creator.image(photo["orign"]) for photo in json.loads(self.photoLinks)]
