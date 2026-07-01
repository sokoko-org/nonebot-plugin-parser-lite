import re

from msgspec import Struct, field

from ...creator import Creator
from ...data import ContentItem
from ...utils.format import replace_placeholder_to_sticker

DOUYIN_PATTERN = re.compile(r"\[(?P<name>[^]]+)\]")


class Stats(Struct):
    commentCount: int = 0
    """评论数"""
    diggCount: int = 0
    """点赞数"""
    shareCount: int = 0
    """分享数"""
    collectCount: int = 0
    """收藏数"""


class AuthorInfo(Struct):
    uid: str
    nickname: str
    avatarUri: str
    """头像"""


class Addr(Struct):
    src: str


class Video(Struct):
    duration: int
    """视频时长(/1000)"""
    cover: str
    """封面"""
    playAddr: list[Addr]


class Image(Struct):
    urlList: list[str]
    livePhotoType: int | str = "$undefined"
    """为 1 时为 livePhoto, 其他时候是 $undefined"""
    video: Video | None = field(default=None)
    """Live Photo 视频"""


class PlayUrl(Struct):
    uri: str


class Music(Struct):
    playUrl: PlayUrl


class Detail(Struct):
    authorInfo: AuthorInfo
    desc: str
    createTime: int
    stats: Stats = field(default_factory=Stats)
    images: list[Image] = field(default_factory=list)
    music: Music | None = field(default=None)


class Aweme(Struct):
    detail: Detail
    music: Music | None = field(default=None)

    @property
    def content(self) -> list[ContentItem]:
        content: list[ContentItem] = [self.detail.desc.replace("\\n", "\n")]
        for image in self.detail.images:
            if image.livePhotoType == 1 and image.video:
                content.append(
                    Creator.live_photo(
                        video_url=image.video.playAddr[0].src,
                        image_url=image.video.cover,
                        ext_headers={"Referer": "https://www.douyin.com/"},
                    )
                )
            else:
                content.append(
                    Creator.image(
                        url=image.urlList[0],
                        ext_headers={"Referer": "https://www.douyin.com/"},
                    )
                )
        if music := (self.music or self.detail.music):
            content.append(
                Creator.audio(
                    url=music.playUrl.uri,
                )
            )
        return content

    @property
    def stats(self) -> Stats:
        return self.detail.stats


class ImageList(Struct):
    originUrl: Image


class Comment(Struct):
    diggCount: int
    """点赞数"""
    text: str
    """文本内容，可能含表情占位"""
    user: AuthorInfo
    createTime: int
    imageList: list[ImageList]
    replyTotal: int
    ipLabel: str = ""

    @property
    def content(self) -> list[ContentItem]:
        content: list[ContentItem] = []
        content.extend(
            replace_placeholder_to_sticker(self.text, DOUYIN_PATTERN, "douyin")
        )
        content.extend(
            Creator.image(
                url=image.originUrl.urlList[0],
                ext_headers={"Referer": "https://www.douyin.com/"},
            )
            for image in self.imageList
        )
        return content


class Comments(Struct):
    comments: list[Comment]


class Note(Struct):
    awemeId: str
    aweme: Aweme
    comment: Comments
