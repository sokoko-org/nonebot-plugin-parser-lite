from msgspec import Struct


class UrlList(Struct):
    url_list: list[str]


class Owner(Struct):
    id_str: str
    nickname: str
    avatar_thumb: UrlList


class RoomViewStats(Struct):
    display_value: int


class Room(Struct):
    id_str: str
    status: int
    title: str
    cover: UrlList
    owner: Owner
    room_view_stats: RoomViewStats
    like_count: int
