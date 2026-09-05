from msgspec import Struct


class RoomData(Struct):
    """``room/v1/Room/get_info`` 返回的直播间信息。"""

    uid: int
    room_id: int
    short_id: int
    background: str
    title: str
    user_cover: str
    keyframe: str

    @property
    def cover(self) -> str:
        return self.user_cover or self.keyframe
