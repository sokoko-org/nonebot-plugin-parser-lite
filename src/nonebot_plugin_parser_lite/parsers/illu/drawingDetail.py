from msgspec import Struct
from msgspec.json import Decoder

from ...creator import Creator
from ...data import ContentItem
from .models import File, Time, User


class DrawingDetail(Struct):
    author: User
    collectCount: int
    commentCount: int
    title: str
    content: str
    images: list[File]
    likeCount: int
    readCount: int
    rewardCoin: int
    objectId: str
    modifyDate: Time
    publishDate: Time

    @property
    def medias(self) -> list[ContentItem]:
        return [
            self.content,
            *[Creator.image(url=image.url) for image in self.images],
        ]


decoder = Decoder(DrawingDetail)
