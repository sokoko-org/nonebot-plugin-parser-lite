from __future__ import annotations

import re

from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import ContentItem
from ...utils.format import replace_placeholder_to_sticker

REDNOTE_PATTERN = re.compile(r"\[(?P<name>[^]]+[a-zA-Z])\]")


class StreamUrl(Struct):
    """Wrapper for stream url"""

    masterUrl: str
    """主链接"""
    # backupUrls: list[str]
    # """备选链接"""


class Stream(Struct):
    """Wrapper for image stream"""

    h264: list[StreamUrl] = field(default_factory=list)
    h265: list[StreamUrl] = field(default_factory=list)
    h266: list[StreamUrl] = field(default_factory=list)
    av1: list[StreamUrl] = field(default_factory=list)

    @property
    def url(self) -> str:
        """
        获取第一个非空流列表中的第一个可用 URL

        优先级: h264 > h265 > h266 > av1

        约束：
            按业务约定，至少会存在一个可用链接；
            如无任何可用链接则抛出 ValueError
        """
        h264, h265, h266, av1 = self.h264, self.h265, self.h266, self.av1
        for stream_list in (h264, h265, h266, av1):
            if stream_list:
                return stream_list[0].masterUrl
        # 理论上不应达到此处，如到此处说明上游数据不符合约定
        raise ValueError("Stream.url: no available stream url found")


class Media(Struct):
    """媒体容器"""

    stream: Stream


class Consumer(Struct):
    originVideoKey: str


class Capa(Struct):
    duration: float


class Video(Struct):
    """笔记中的主视频信息"""

    capa: Capa
    consumer: Consumer

    @property
    def url(self) -> str:
        """主视频直链"""
        return f"https://sns-video-bd.xhscdn.com/{self.consumer.originVideoKey}"


class Image(Struct):
    fileId: str
    livePhoto: bool = False
    """是否为 iPhone Live Photo"""
    stream: Stream = field(default_factory=Stream)
    """iPhone Live Photo 视频流"""

    @property
    def url(self) -> str:
        """图片无水印直链"""
        return (
            f"https://ci.xiaohongshu.com/{self.fileId}?imageView2/2/w/1080/format/jpg"
        )


class CommentImage(Struct):
    originUrl: str


class User(Struct):
    """用户信息"""

    nickName: str
    avatar: str
    userId: str


class InteractInfo(Struct):
    """互动信息"""

    likedCount: str
    collectedCount: str
    commentCount: str
    shareCount: str


class Cover(Struct):
    fileId: str


class NoteDetail(Struct):
    # type: str
    # """类型，一般是normal/video"""
    title: str
    """标题"""
    desc: str
    """简介"""
    user: User
    lastUpdateTime: int
    interactInfo: InteractInfo
    cover: Cover
    imageList: list[Image] = field(default_factory=list)
    """图片列表，包括普通图片和 Live Photo"""
    video: Video | None = None
    """主视频（如果有）"""

    @property
    def nickname(self) -> str:
        """作者昵称"""
        return self.user.nickName

    @property
    def avatar_url(self) -> str:
        """作者头像地址"""
        return self.user.avatar

    @property
    def medias(self) -> list[ContentItem]:
        """
        统一构建当前笔记的媒体内容列表

        - Live Photo -> LivePhotoContent
        - 普通图片   -> ImageContent
        - 主视频     -> VideoContent (如果有视频，则第一张图是封面)
        """
        items: list[ContentItem] = []
        if self.video:
            items.append(
                Creator.video(
                    url_or_task=self.video.url,
                    cover_url=f"https://ci.xiaohongshu.com/{self.cover.fileId}?imageView2/2/w/1080/format/jpg",
                    duration=self.video.capa.duration,
                )
            )
        else:
            for img in self.imageList:
                if img.livePhoto:
                    items.append(
                        Creator.live_photo(
                            video_url=img.stream.url,
                            image_url=img.url,
                        )
                    )
                else:
                    items.append(
                        Creator.image(
                            url=img.url,
                        )
                    )

        return items

    @property
    def content(self):
        return [
            *replace_placeholder_to_sticker(self.desc, REDNOTE_PATTERN, "rednote"),
            *self.medias,
        ]


class CommentUser(Struct):
    nickname: str
    image: str
    userId: str


class Comment(Struct):
    user: CommentUser
    time: int
    likeViewCount: str
    text: str = field(name="content")
    ipLocation: str = ""
    pictures: list[CommentImage] = field(default_factory=list)
    subComments: list[Comment] = field(default_factory=list)

    @property
    def content(self) -> list[ContentItem]:
        content = replace_placeholder_to_sticker(self.text, REDNOTE_PATTERN, "rednote")
        content.extend(
            Creator.image(
                url=pic.originUrl,
            )
            for pic in self.pictures
        )
        return content


class CommentList(Struct):
    comments: list[Comment] = field(default_factory=list)


class NoteDetailWrapper(Struct):
    """Wrapper for note detail, represents the value in noteDetailMap[xhs_id]"""

    noteData: NoteDetail
    commentData: CommentList = field(default_factory=CommentList)


class Note(Struct):
    """Top-level note container with noteDetailMap"""

    data: NoteDetailWrapper


class InitialState(Struct):
    """Root structure of window.__INITIAL_STATE__"""

    noteData: Note


decoder = Decoder(InitialState)
