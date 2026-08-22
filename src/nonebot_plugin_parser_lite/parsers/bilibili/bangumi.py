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
    media_id: int
    title: str
    season_title: str
    square_cover: str
    """方形封面"""
    staff: str
    """制作人员信息"""
    share_url: str
    stat: Stat
