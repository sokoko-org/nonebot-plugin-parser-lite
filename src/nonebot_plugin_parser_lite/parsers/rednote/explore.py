import re

from msgspec import Struct, field
from msgspec.json import Decoder

from ..creator import create_image, create_live_photo, create_video
from ..data import MediaContent

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


class VideoInfo(Struct):
    duration: float


class Media(Struct):
    """视频媒体容器"""

    stream: Stream
    video: VideoInfo


class Video(Struct):
    """笔记中的主视频信息"""

    media: Media

    @property
    def url(self) -> str:
        """主视频直链"""
        return self.media.stream.url


class ImageInfo(Struct):
    url: str


# # 新版图片资源优先保留 notes_pre_post token，使用 ci.xiaohongshu.com 输出 JPEG。
# # 例：
# # https://sns-webpic-qc.xhscdn.com/<time>/<hash>/notes_pre_post/<img_id>!nd_dft_wlteh_webp_3
# # -> https://ci.xiaohongshu.com/notes_pre_post/<img_id>?imageView2/format/jpeg
# if 'notes_pre_post/' in img_url:
#     token = 'notes_pre_post/' + img_url.split('notes_pre_post/', 1)[1].split('!', 1)[0].split('?', 1)[0]  # noqa: E501
#     new_url = f'https://ci.xiaohongshu.com/{token}?imageView2/format/jpeg'
# elif 'spectrum' in img_url:
#     token = '/'.join(img_url.split('/')[-2:]).split('!', 1)[0].split('?', 1)[0]
#     new_url = f'https://ci.xiaohongshu.com/{token}?imageView2/format/jpeg'
# elif '.jpg' in img_url:
#     token = '/'.join([split for split in img_url.split('/')[-3:]]).split('!', 1)[0].split('?', 1)[0]  # noqa: E501
#     new_url = f'https://ci.xiaohongshu.com/{token}?imageView2/format/jpeg'
# else:
#     token = img_url.split('/')[-1].split('!', 1)[0].split('?', 1)[0]
#     new_url = f'https://ci.xiaohongshu.com/{token}?imageView2/format/jpeg'


class Image(Struct):
    infoList: list[ImageInfo]
    livePhoto: bool = False
    """是否为 iPhone Live Photo"""
    stream: Stream = field(default_factory=Stream)
    """iPhone Live Photo 视频流"""

    @property
    def url(self) -> str:
        """图片无水印直链"""
        return self.infoList[1].url


class User(Struct):
    """用户信息"""

    nickname: str
    avatar: str
    userId: str


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
    xsecToken: str
    noteId: str
    imageList: list[Image] = field(default_factory=list)
    """图片列表，包括普通图片和 Live Photo"""
    video: Video | None = field(default=None)
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
        - 主视频     -> VideoContent (如果有视频，则第一张图是封面)
        """
        items: list[MediaContent] = []

        # 处理视频情况：如果有视频，第一张图片是封面
        if self.video:
            items.append(
                create_video(
                    url_or_task=self.video.url,
                    cover_url=self.imageList[0].url,
                    duration=self.video.media.video.duration,
                )
            )
        else:
            # 处理图片情况：没有视频时，正常处理图片列表
            for img in self.imageList:
                if img.livePhoto:
                    items.append(
                        create_live_photo(
                            video_url=img.stream.url,
                            image_url=img.url,
                        )
                    )
                else:
                    items.append(
                        create_image(
                            url=img.url,
                        )
                    )

        return items


class NoteDetailMap(Struct):
    note: NoteDetail


class Note(Struct):
    noteDetailMap: dict[str, NoteDetailMap]
    currentNoteId: str


class InitialState(Struct):
    note: Note


decoder = Decoder(InitialState)
