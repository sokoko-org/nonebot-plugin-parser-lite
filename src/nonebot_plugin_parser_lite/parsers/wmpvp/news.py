from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...utils.format import format_num
from .util import parse_rich_content


class CommunityUserItem(Struct):
    userId: int
    steamId: str
    nickname: str
    avatar: str


class News(Struct):
    newsId: int
    gameType: int
    title: str
    communityUserItem: CommunityUserItem
    html: str = field(name="content")
    pageViewCount: int
    publishTime: int
    """ms"""
    userRegion: str
    likeCount: int

    @property
    def content(self):
        return parse_rich_content(self.html)

    @property
    def timestamp(self) -> int:
        return self.publishTime // 1000

    @property
    def author(self):
        return Creator.author(
            name=self.communityUserItem.nickname,
            avatar_url=self.communityUserItem.avatar,
            ext_headers={"Referer": "https://news.wmpvp.com"},
            location=self.userRegion,
        )

    @property
    def stats(self):
        return Creator.stats(
            view_count=format_num(self.pageViewCount),
            like_count=format_num(self.likeCount),
        )

    @property
    def url(self):
        return f"https://news.wmpvp.com/news.html?id={self.newsId}&gameTypeStr={self.gameType}"


class Result(Struct):
    news: News


class Response(Struct):
    result: Result


decoder = Decoder(Response)
