from enum import Enum

from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import ContentItem
from ...utils.format import format_num
from .share import Author, Photo
from .util import parse_date, parse_rich_content


class ImageLayout(str, Enum):
    ARTICLE = "vertical"
    IMAGE = "horizontal"


class Post(Struct):
    id: str
    type: str
    url: str
    title: str
    html: str = field(name="content")
    create_time: str
    update_time: str
    author: Author
    image_layout: ImageLayout
    photos: list[Photo]
    ip_location: str
    reshares_count: int
    like_count: int
    comments_count: int

    @property
    def timestamp(self):
        return parse_date(self.update_time)

    @property
    def content(self) -> list[ContentItem]:
        content = parse_rich_content(self.html)
        if self.image_layout == ImageLayout.IMAGE:
            for photo in self.photos:
                content.append(
                    Creator.image(
                        url=photo.image.large.url,
                        ext_headers={"Referer": "https://douban.com/"},
                        use_curl_cffi=True,
                    )
                )
        return content

    @property
    def stats(self):
        return Creator.stats(
            like_count=format_num(self.like_count),
            share_count=format_num(self.reshares_count),
            comment_count=format_num(self.comments_count),
        )

    @property
    def author_obj(self):
        return Creator.author(
            name=self.author.name,
            avatar_url=self.author.avatar,
            id=self.author.uid,
            location=self.ip_location,
            ext_headers={"Referer": "https://douban.com/"},
            use_curl_cffi=True,
        )


decoder = Decoder(Post)
