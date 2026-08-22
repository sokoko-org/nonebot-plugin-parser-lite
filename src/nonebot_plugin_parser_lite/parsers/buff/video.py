from msgspec import Struct

from ...creator import Creator
from ...data import ContentItem
from .share import ShareData


class VideoItem(Struct):
    duration: str
    """字符串格式的float时长"""
    icon_url: str
    video_url: str


class Video(Struct):
    author: str
    user_id: str
    avatar: str
    body: str
    ip_location: str
    publish_time: int
    replies: int
    ups_num: int
    views: int
    video: list[VideoItem]
    share_data: ShareData

    @property
    def content(self) -> list[ContentItem]:
        return [
            self.body,
            *[
                Creator.video(
                    url_or_task=item.video_url,
                    cover_url=item.icon_url,
                    duration=float(item.duration),
                )
                for item in self.video
            ],
        ]
