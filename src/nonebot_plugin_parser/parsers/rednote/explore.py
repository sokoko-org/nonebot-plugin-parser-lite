from msgspec import Struct, field
from msgspec.json import Decoder


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
    def stream_url(self) -> str:
        """获取第一个非空流列表中的第一个可用URL，优先级为h264 > h265 > h266 > av1"""
        return next(
            (
                stream_list[0].masterUrl
                for stream_list in [self.h264, self.h265, self.h266, self.av1]
                if stream_list
            ),
            "",
        )


class Media(Struct):
    stream: Stream


class Video(Struct):
    media: Media

    @property
    def video_url(self) -> str:
        return self.media.stream.stream_url


class Image(Struct):
    urlDefault: str
    livePhoto: bool = False
    """是否为动态图片(即视频)"""
    stream: Stream = field(default_factory=Stream)
    """图片流信息(若为动态图片，应从此获取图片mp4)"""

    @property
    def live_url(self) -> tuple[str, str] | None:
        """
        获取live图片地址

        :return: live视频地址, live图片底图
        """
        if self.livePhoto:
            return (self.stream.stream_url, self.urlDefault) if self.livePhoto else None
        return None


class User(Struct):
    nickname: str
    avatar: str


class InteractInfo(Struct):
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
    video: Video | None = None

    @property
    def nickname(self) -> str:
        return self.user.nickname

    @property
    def avatar_url(self) -> str:
        return self.user.avatar

    @property
    def image_urls(self) -> list[str]:
        return [image.urlDefault for image in self.imageList]

    @property
    def video_url(self) -> str | None:
        if self.video:
            return self.video.video_url

    @property
    def live_urls(self) -> list[tuple[str, str]]:
        return [image.live_url for image in self.imageList if image.live_url]


class CommentUser(Struct):
    nickname: str
    image: str
    userId: str


class Comment(Struct):
    userInfo: CommentUser
    createTime: int
    subCommentCount: str
    content: str
    likeCount: str
    ipLocation: str
    pictures: list[Image] = field(default_factory=list)
    subComments: list["Comment"] = field(default_factory=list)


class CommentsList(Struct):
    """Wrapper for comments list"""

    comments: list[Comment] = field(name="list", default_factory=list)


class NoteDetailWrapper(Struct):
    """Wrapper for note detail, represents the value in noteDetailMap[xhs_id]"""

    note: NoteDetail
    comments: CommentsList


class Note(Struct):
    """Top-level note container with noteDetailMap"""

    noteDetailMap: dict[str, NoteDetailWrapper]


class InitialState(Struct):
    """Root structure of window.__INITIAL_STATE__"""

    note: Note


decoder = Decoder(InitialState)
