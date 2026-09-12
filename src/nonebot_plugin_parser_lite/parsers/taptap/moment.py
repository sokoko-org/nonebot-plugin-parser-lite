from msgspec import Struct
from msgspec.json import Decoder

from ...creator import ContentItem, Creator
from ...utils.format import format_num
from .share import Contents, Img


class User(Struct):
    id: int
    name: str
    avatar: str


class Author(Struct):
    user: User


class Video(Struct):
    video_id: int


class Topic(Struct):
    title: str | None = None
    pin_video: Video | None = None


class Stat(Struct):
    ups: int | None = None
    comments: int | None = None
    favorites: int | None = None
    reposts: int | None = None
    pv_total: int | None = None

    @property
    def stats(self):
        return Creator.stats(
            view_count=format_num(self.pv_total),
            like_count=format_num(self.ups),
            share_count=format_num(self.reposts),
            comment_count=format_num(self.comments),
            collect_count=format_num(self.favorites),
        )


class FirstPost(Struct):
    id_str: str
    contents: Contents | None = None
    footer_images: list[Img] | None = None

    @property
    def content(self) -> list[ContentItem]:
        base_content = self.contents.content if self.contents is not None else []
        if not self.footer_images:
            return base_content

        base_content.extend(
            [Creator.image(img.original_url) for img in self.footer_images]
        )

        return base_content


class Moment(Struct):
    id_str: str
    created_time: int
    edited_time: int
    author: Author
    topic: Topic
    stat: Stat

    @property
    def video_id(self):
        return self.topic.pin_video.video_id if self.topic.pin_video else None


class Data(Struct):
    moment: Moment
    first_post: FirstPost

    @property
    def content(self):
        return self.first_post.content

    @property
    def stats(self):
        return self.moment.stat.stats

    @property
    def author(self):
        return Creator.author(
            name=self.moment.author.user.name,
            avatar_url=self.moment.author.user.avatar,
            id=str(self.moment.author.user.id),
            avatar_cache_key=f"taptap:{self.moment.author.user.id}",
        )

    @property
    def title(self):
        return self.moment.topic.title

    @property
    def url(self):
        return f"https://www.taptap.com/moment/{self.moment.id_str}"

    @property
    def timestamp(self):
        return self.moment.created_time

    @property
    def video_id(self):
        return self.moment.video_id


class Response(Struct):
    data: Data


decoder = Decoder(Response)
