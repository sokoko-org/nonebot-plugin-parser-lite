from datetime import datetime
from enum import Enum, IntEnum

from msgspec import Struct, field


class File(Struct):
    filename: str
    url: str


class Time(Struct):
    iso: str

    @property
    def timestamp(self) -> int:
        dt = datetime.strptime(self.iso, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp())


class User(Struct):
    level: int
    nickname: str
    objectId: str
    createdAt: str
    headerImage: File
    words: str = field(default="")


class Detail(Enum):
    ArticleDetail = "/1/functions/getArticleByIdV2"
    DrawingDetail = "/1/functions/getDrawingDetail"
    CommentList = "/1/functions/getCommonCommentList"
    ArticleCommentList = "/1/functions/getCommonCommentList"


class OrderType(IntEnum):
    Ascending = 0
    Descending = 1
    Popular = 2


class BizType(IntEnum):
    Article = 1
    ArticleCollect = 2
    Game = 3
    Drawing = 4
    Trends = 5
    TrpgModule = 6
    TrpgRoom = 7
    TrpgRoleCardTemplate = 8
    TrpgRoleCard = 9
    TrpgDice = 10
    TrpgDataSource = 11
