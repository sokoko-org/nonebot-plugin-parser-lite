from random import choice
from typing import Any

from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import ContentItem


class Avatar(Struct):
    url_list: list[str]


class Author(Struct):
    nickname: str
    avatar_thumb: Avatar | None = None
    avatar_medium: Avatar | None = None

    @property
    def avatar_url(self) -> str | None:
        if avatar := self.avatar_thumb:
            return choice(avatar.url_list)
        elif avatar := self.avatar_medium:
            return choice(avatar.url_list)
        return None


class PlayAddr(Struct):
    url_list: list[str]


class Cover(Struct):
    url_list: list[str]


class Video(Struct):
    play_addr: PlayAddr
    cover: Cover
    duration: int


class Image(Struct):
    video: Video | None = None
    url_list: list[str] = field(default_factory=list)


class Statistics(Struct):
    comment_count: int
    """评论数"""
    digg_count: int
    """点赞数"""
    share_count: int
    """分享数"""
    collect_count: int
    """收藏数"""


class VideoData(Struct):
    aweme_id: str
    create_time: int
    author: Author
    statistics: Statistics
    desc: str
    images: list[Image] | None = None
    video: Video | None = None

    @property
    def medias(self) -> list[ContentItem]:
        medias: list[ContentItem] = []
        if self.images:
            medias.extend(
                Creator.image(
                    url=image.url_list[0].replace("playwm", "play"),
                    ext_headers={"Referer": "https://www.douyin.com/"},
                )
                for image in self.images
            )
        if self.video:
            medias.append(
                Creator.video(
                    url_or_task=self.video.play_addr.url_list[0].replace(
                        "playwm", "play"
                    ),
                    cover_url=self.video.cover.url_list[0],
                    duration=self.video.duration // 1000,
                    video_name=f"{self.aweme_id}.mp4",
                    ext_headers={"Referer": "https://www.douyin.com/"},
                )
            )
        return medias


class VideoInfoRes(Struct):
    item_list: list[VideoData] = field(default_factory=list)

    @property
    def video_data(self) -> VideoData:
        if not self.item_list:
            raise ValueError("can't find data in videoInfoRes")
        return choice(self.item_list)


class Comment(Struct):
    user: Author
    text: str
    createTime: int
    digg_count: int
    reply_comment_total: int
    ip_label: str


class CommentList(Struct):
    comments: list[Comment] = field(default_factory=list)


class VideoOrNotePage(Struct):
    video_info_res: VideoInfoRes = field(
        name="videoInfoRes", default_factory=VideoInfoRes
    )
    commentListData: CommentList = field(default_factory=CommentList)
    """评论区，仅图集有"""


class LoaderData(Struct):
    video_page: VideoOrNotePage | None = field(name="video_(id)/page", default=None)
    note_page: VideoOrNotePage | None = field(name="note_(id)/page", default=None)


class RouterData(Struct):
    loader_data: LoaderData = field(name="loaderData", default_factory=LoaderData)
    errors: dict[str, Any] | None = None

    @property
    def video_data(self) -> VideoData:
        if page := self.loader_data.video_page:
            return page.video_info_res.video_data
        elif page := self.loader_data.note_page:
            return page.video_info_res.video_data
        raise ValueError(
            "can't find video_(id)/page or note_(id)/page in router data"
        )

    @property
    def comment_list(self) -> CommentList:
        if page := self.loader_data.video_page:
            return page.commentListData
        elif page := self.loader_data.note_page:
            return page.commentListData
        raise ValueError(
            "can't find video_(id)/page or note_(id)/page in router data"
        )


decoder = Decoder(RouterData)
