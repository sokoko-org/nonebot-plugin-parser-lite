from msgspec import Struct


class Stat(Struct):
    coins: int
    danmakus: int
    favorite: int
    likes: int
    reply: int
    share: int
    views: int


class BangumiInfo(Struct):
    cover: str
    evaluate: str
    title: str
    season_title: str
    square_cover: str
    share_url: str
    stat: Stat
