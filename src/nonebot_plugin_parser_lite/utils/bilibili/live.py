from datetime import datetime
from enum import IntEnum

from msgspec import Struct, convert

from .client import HTTP_CLIENT
from .exceptions import BiliHelperException


class LiveStatus(IntEnum):
    """直播间开播状态"""

    OFFLINE = 0
    """未开播"""
    LIVE = 1
    """直播中"""
    ROUND = 2
    """轮播中"""


class LiveRoomInfo(Struct):
    """直播间信息"""

    uid: int
    """主播用户 ID"""
    room_id: int
    """直播间长号"""
    short_id: int
    """直播间短号，没有短号时为 ``0``"""
    attention: int
    """直播间关注数"""
    online: int
    """当前在线人数"""
    is_portrait: bool
    description: str
    live_status: LiveStatus
    """当前开播状态"""
    area_id: int
    """直播分区 ID"""
    parent_area_id: int
    """直播父分区 ID"""
    parent_area_name: str
    background: str
    title: str
    user_cover: str
    keyframe: str
    """直播中的最新关键帧，未开播时通常为空"""
    live_time: str
    """本次开播时间；未开播时为 ``0000-00-00 00:00:00``"""
    is_anchor: int
    area_name: str

    @property
    def is_live(self) -> bool:
        """直播间当前是否正在直播"""
        return self.live_status is LiveStatus.LIVE

    @property
    def timestamp(self) -> int | None:
        """本次开播时间戳；未开播时返回 ``None``"""
        if self.live_time == "0000-00-00 00:00:00":
            return None
        live_time = datetime.strptime(self.live_time, "%Y-%m-%d %H:%M:%S")
        return int(live_time.timestamp())


class LiveRoom:
    """直播类"""

    def __init__(self, room_display_id: int) -> None:
        self.room_display_id = room_display_id

    async def get_room_info(self) -> LiveRoomInfo:
        """获取直播间信息"""
        result = (
            await HTTP_CLIENT.get(
                url="https://api.live.bilibili.com/room/v1/Room/get_info",
                params={"room_id": self.room_display_id},
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        return convert(result["data"], LiveRoomInfo)
