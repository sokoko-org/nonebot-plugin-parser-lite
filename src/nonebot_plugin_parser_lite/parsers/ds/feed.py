from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import ContentItem, Creator
from ...utils.format import format_num
from .util import parse_rich_content


class DisplayIpInfo(Struct):
    ipLocationName: str


class User(Struct):
    uid: str
    nick: str
    icon: str
    intro: str


class UserInfo(Struct):
    user: User


class Record(Struct):
    repostCount: int
    commentCount: int
    likeCount: int
    shareCount: int
    favCount: int


class Media(Struct):
    url: str
    mimeType: str
    """video/xxx, image/xxx"""
    name: str | None = field(default=None)
    duration: int | None = field(default=None)
    cover: str | None = field(default=None)


class Body(Struct):
    text: str | None = field(default=None)
    media: list[Media] = field(default_factory=list)
    title: str | None = field(default=None)
    html: str | None = field(name="longText", default=None)


class Content(Struct):
    body: Body


contentDecoder = Decoder(Content)


class Feed(Struct):
    id: str
    uid: str
    dumps: str = field(name="content")
    createTime: int
    record: Record
    displayIpInfo: DisplayIpInfo | None = field(default=None)
    _content_obj: Content | None = field(default=None)

    @property
    def content_obj(self) -> Content:
        if self._content_obj is None:
            self._content_obj = contentDecoder.decode(self.dumps)
        return self._content_obj

    @property
    def content(self):
        body = self.content_obj.body
        if body.html:
            return parse_rich_content(body.html)
        content: list[ContentItem] = []
        if text := body.text:
            content.append(text)
        if medias := body.media:
            for media in medias:
                if media.mimeType.startswith("video"):
                    assert media.duration, "duration is required in video media"
                    content.append(
                        Creator.video(
                            url_or_task=media.url,
                            duration=media.duration // 1000,
                            cover_url=media.cover,
                        )
                    )
                elif media.mimeType.startswith("image"):
                    content.append(Creator.image(url=media.url))
        return content

    @property
    def title(self):
        return self.content_obj.body.title

    @property
    def timestamp(self):
        return self.createTime // 1000

    @property
    def stats(self):
        record = self.record
        return Creator.stats(
            like_count=format_num(record.likeCount),
            comment_count=format_num(record.commentCount),
            share_count=format_num(record.shareCount),
            collect_count=format_num(record.favCount),
        )


class Result(Struct):
    feed: Feed
    userInfos: list[UserInfo]

    @property
    def user_info_by_uid(self):
        return {info.user.uid: info for info in self.userInfos}

    @property
    def author(self):
        author = self.user_info_by_uid[self.feed.uid]
        location = (
            self.feed.displayIpInfo.ipLocationName if self.feed.displayIpInfo else None
        )
        return Creator.author(
            id=author.user.uid,
            name=author.user.nick,
            avatar_url=author.user.icon,
            location=location,
        )



decoder = Decoder(Result)
