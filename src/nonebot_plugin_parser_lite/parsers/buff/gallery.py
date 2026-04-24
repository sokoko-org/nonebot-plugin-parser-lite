from msgspec import Struct

from .share import ShareData


class Preview(Struct):
    description: str
    icon_url: str
    user_id: str
    publish_time: int
    ups_num: int
    share_data: ShareData


class UserInfo(Struct):
    avatar: str
    ip_location: str
    nickname: str
    user_id: str


class Gallery(Struct):
    preview: Preview
    user_infos: dict[str, UserInfo]
