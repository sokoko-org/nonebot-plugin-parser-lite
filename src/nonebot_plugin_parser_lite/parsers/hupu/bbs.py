from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...utils.format import format_num
from .util import parse_rich_content


class Author(Struct):
    name: str
    header: str
    view: int
    puid: int


class Data(Struct):
    fid: str
    tid: str
    title: str
    html: str = field(name="content")
    share_num: int
    replies: str
    create_time: int

    @property
    def content(self):
        return parse_rich_content(self.html)


class OfflineData(Struct):
    data: Data


class VideoInfo(Struct):
    img: str
    src: str
    duration: str
    size: str
    play_num: str


class BBS(Struct):
    offline_data: OfflineData
    author: Author
    recommend_num: str
    """点赞"""
    video_info: VideoInfo | None
    tid: str
    fid: str

    @property
    def title(self):
        return self.offline_data.data.title

    @property
    def timestamp(self):
        return self.offline_data.data.create_time

    @property
    def content(self):
        c = self.offline_data.data.content
        if video := self.video_info:
            c.append(
                Creator.video(
                    url_or_task=video.src,
                    cover_url=video.img,
                    duration=int(video.duration),
                )
            )
        return c

    @property
    def author_obj(self):
        return Creator.author(
            name=self.author.name,
            avatar_url=self.author.header,
            id=str(self.author.puid),
        )

    @property
    def stats(self):
        return Creator.stats(
            view_count=format_num(self.author.view),
            like_count=self.recommend_num,
            share_count=format_num(self.offline_data.data.share_num),
            comment_count=self.offline_data.data.replies,
        )


decoder = Decoder(BBS)
