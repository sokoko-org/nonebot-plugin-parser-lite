from bs4 import BeautifulSoup
from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import ContentItem
from ...utils.format import format_num


class CommunityUserItem(Struct):
    userId: int
    steamId: str
    nickname: str
    avatar: str


class Image(Struct):
    url: str


class VideoBase(Struct):
    coverURL: str
    duration: str
    """float"""
    videoId: str


class PlayInfo(Struct):
    size: int
    playURL: str
    duration: str
    format: str


class VideoInfo(Struct):
    videoBase: VideoBase
    playInfoList: list[PlayInfo]


class Post(Struct):
    id: int
    userId: int
    steamId: str
    title: str
    html: str | None = field(name="content")
    """may html"""
    videoInfo: VideoInfo | None
    type: int
    """1-文图,3-视频"""
    readTotalCount: int
    likeCountTotal: int
    gmtCreate: int
    """ms"""
    gmtModified: int
    """ms"""
    replyCount: int
    images: list[Image] | None
    postUrl: str
    communityUserItem: CommunityUserItem
    userRegion: str

    @property
    def text(self):
        return BeautifulSoup(self.html, "html.parser").get_text() if self.html else ""

    @property
    def timestamp(self) -> int:
        return self.gmtCreate // 1000

    @property
    def stats(self):
        return Creator.stats(
            view_count=format_num(self.readTotalCount),
            like_count=format_num(self.likeCountTotal),
            comment_count=format_num(self.replyCount),
        )

    @property
    def author(self):
        return Creator.author(
            name=self.communityUserItem.nickname,
            avatar_url=self.communityUserItem.avatar,
            location=self.userRegion,
            ext_headers={"Referer": "https://news.wmpvp.com"},
        )

    @property
    def content(self) -> list[ContentItem]:
        return [
            self.text,
            *(
                Creator.image(
                    url=i.url,
                    ext_headers={"Referer": "https://news.wmpvp.com"},
                )
                for i in self.images or []
            ),
            *(
                [
                    Creator.video(
                        url_or_task=self.videoInfo.playInfoList[0].playURL,
                        cover_url=self.videoInfo.videoBase.coverURL,
                        duration=float(self.videoInfo.videoBase.duration),
                        ext_headers={"Referer": "https://news.wmpvp.com"},
                    )
                ]
                if self.videoInfo
                else []
            ),
        ]


class Result(Struct):
    post: Post


class Response(Struct):
    result: Result


decoder = Decoder(Response)
