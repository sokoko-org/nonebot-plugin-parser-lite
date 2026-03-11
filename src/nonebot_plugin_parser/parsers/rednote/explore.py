from msgspec import Struct, field
from msgspec.json import Decoder

from ...parsers.data import MediaContent
from ...parsers.creator import (
    create_image,
    create_live_photo,
    create_video,
)


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
    """视频媒体容器"""

    stream: Stream


class Video(Struct):
    """笔记中的主视频信息"""

    media: Media

    @property
    def url(self) -> str:
        """主视频直链"""
        return self.media.stream.url


class Image(Struct):
    urlDefault: str
    livePhoto: bool = False
    """是否为 iPhone Live Photo"""
    stream: Stream = field(default_factory=Stream)
    """iPhone Live Photo 视频流"""


class User(Struct):
    """用户信息"""

    nickname: str
    avatar: str


class InteractInfo(Struct):
    """互动信息"""

    likedCount: str
    collectedCount: str
    commentCount: str
    shareCount: str


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
    imageList: list[Image] = field(default_factory=list)
    """图片列表，包括普通图片和 Live Photo"""
    video: Video | None = None
    """主视频（如果有）"""

    @property
    def nickname(self) -> str:
        """作者昵称"""
        return self.user.nickname

    @property
    def avatar_url(self) -> str:
        """作者头像地址"""
        return self.user.avatar

    @property
    def medias(self) -> list[MediaContent]:
        """
        统一构建当前笔记的媒体内容列表

        - Live Photo -> LivePhotoContent
        - 普通图片   -> ImageContent
        - 主视频     -> VideoContent
        """
        items: list[MediaContent] = []

        for img in self.imageList:
            if img.livePhoto:
                items.append(
                    create_live_photo(
                        video_url=img.stream.url,
                        image_url=img.urlDefault,
                    )
                )
            else:
                items.append(create_image(url=img.urlDefault))
        # 主视频：有就追加一个
        if self.video:
            if v_url := self.video.url:
                items.append(create_video(url_or_task=v_url))

        return items


class CommentUser(Struct):
    nickname: str
    image: str
    userId: str


class Comment(Struct):
    userInfo: CommentUser
    createTime: int
    content: str
    likeCount: str
    ipLocation: str
    pictures: list[Image] = field(default_factory=list)
    subComments: list["Comment"] = field(default_factory=list)


class CommentList(Struct):
    comments: list[Comment] = field(default_factory=list)


class NoteDetailWrapper(Struct):
    """Wrapper for note detail, represents the value in noteDetailMap[xhs_id]"""

    note: NoteDetail
    comments_list: CommentList = field(default_factory=CommentList)


class Note(Struct):
    """Top-level note container with noteDetailMap"""

    noteDetailMap: dict[str, NoteDetailWrapper]


class InitialState(Struct):
    """Root structure of window.__INITIAL_STATE__"""

    note: Note


decoder = Decoder(InitialState)
