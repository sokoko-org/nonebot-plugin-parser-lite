from typing import Any

from msgspec import Struct, convert, field

from .bilibili.app.dynamic.v2 import dynamic_pb2
from .client import ENVIRONMENT, GRPC_CLIENT, HTTP_CLIENT, MOBI_APP
from .credential import Credential
from .exceptions import BiliHelperException
from .live import LiveStatus
from .sign import enc_app_sign


class UserInfo(Struct):
    """用户基础资料"""

    mid: str
    name: str
    face: str
    sign: str


class UserLiveRoom(Struct):
    """用户空间返回的直播间摘要"""

    roomStatus: int
    """是否已开通直播间：``0`` 未开通，``1`` 已开通"""
    roundStatus: int
    """是否处于轮播状态；不能用于判断直播是否开播"""
    liveStatus: LiveStatus
    """当前开播状态"""
    url: str
    title: str
    cover: str
    online: int
    """直播间在线人数"""
    roomid: int
    """直播间长号；未开通直播间时为 ``0``"""
    broadcast_type: int
    """直播类型，``0`` 为普通直播，``1`` 为竖屏直播"""
    online_hidden: int
    link: str

    @property
    def has_room(self) -> bool:
        """用户是否已开通直播间"""
        return self.roomStatus == 1

    @property
    def is_live(self) -> bool:
        """用户当前是否正在直播"""
        return self.liveStatus is LiveStatus.LIVE


class UserSpaceInfo(Struct):
    """用户空间中本工具需要的资料"""

    card: UserInfo
    live: UserLiveRoom | None
    """直播间摘要； ``room_status=0`` 表示未开通"""


class UserVideo(Struct):
    """用户投稿视频"""

    title: str
    translated_title: str
    subtitle: str
    type_name: str = field(name="tname")
    cover: str
    uri: str
    aid: str = field(name="param")
    """投稿 avid，同时也是 ``get_videos`` 的下一页游标"""
    goto: str
    duration: int
    play: int
    danmaku: int
    ctime: int
    author: str
    bvid: str
    videos: int
    first_cid: int
    publish_time_text: str


class UserVideoPage(Struct):
    """用户投稿视频分页结果"""

    count: int
    """用户投稿总数"""
    item: list[UserVideo]
    has_next: bool
    """是否还有下一页"""
    has_prev: bool


class User:
    """用户类"""

    def __init__(self, mid: int, credential: Credential | None = None) -> None:
        if mid <= 0:
            raise BiliHelperException("mid 必须大于 0")
        self.mid = mid
        self.credential = credential
        self._space_info: UserSpaceInfo | None = None

    async def _get_space_info(self) -> UserSpaceInfo:
        if self._space_info is not None:
            return self._space_info

        result = (
            await HTTP_CLIENT.get(
                url="https://app.bilibili.com/x/v2/space",
                params=enc_app_sign({"vmid": self.mid}),
                headers={"app-key": MOBI_APP, "env": ENVIRONMENT},
                cookies=(
                    self.credential.get_cookies()
                    if self.credential is not None
                    else None
                ),
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        self._space_info = convert(result["data"], UserSpaceInfo)
        return self._space_info

    async def get_info(self) -> UserInfo:
        """获取用户基础资料"""
        return (await self._get_space_info()).card

    async def get_live_room_info(self) -> UserLiveRoom | None:
        """获取用户直播间摘要；用户没有直播间时返回 ``None``"""
        live_room = (await self._get_space_info()).live
        return None if live_room is None or not live_room.has_room else live_room

    async def has_live_room(self) -> bool:
        """用户是否已开通直播间"""
        live_room = (await self._get_space_info()).live
        return live_room is not None and live_room.has_room

    async def get_dynamics(
        self,
        history_offset: str = "",
        page: int = 1,
        local_time: int = 8,
    ) -> dynamic_pb2.DynSpaceRsp:
        """获取用户动态列表"""
        if page <= 0:
            raise BiliHelperException("page 必须大于 0")
        request = dynamic_pb2.DynSpaceReq(
            host_uid=self.mid,
            history_offset=history_offset,
            local_time=local_time,
            page=page,
        )
        access_token = self.credential.access_token if self.credential else ""
        return await GRPC_CLIENT.request(
            "/bilibili.app.dynamic.v2.Dynamic/DynSpace",
            request,
            dynamic_pb2.DynSpaceRsp,
            access_token=access_token,
            user_mid=(
                self.credential.mid if self.credential and access_token else None
            ),
        )

    async def get_videos(
        self,
        aid: int | str = 0,
        page_size: int = 20,
        keyword: str = "",
        order: str = "pubdate",
    ) -> UserVideoPage:
        """获取用户视频列表；下一页游标为本页最后一个视频的 ``aid``"""
        if page_size <= 0:
            raise BiliHelperException("page_size 必须大于 0")
        result = (
            await HTTP_CLIENT.get(
                url="https://app.bilibili.com/x/v2/space/archive/cursor",
                params=enc_app_sign(
                    {
                        "vmid": self.mid,
                        "aid": aid,
                        "ps": page_size,
                        "keyword": keyword,
                        "order": order,
                    }
                ),
                headers={"app-key": MOBI_APP, "env": ENVIRONMENT},
                cookies=(
                    self.credential.get_cookies()
                    if self.credential is not None
                    else None
                ),
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        return convert(result["data"], UserVideoPage)


async def get_black_list(
    credential: Credential,
    page_size: int = 50,
    page_index: int = 1,
) -> dict[str, Any]:
    """获取当前登录用户的黑名单"""
    if page_index <= 0:
        raise BiliHelperException("page_index 必须大于或等于 1")
    result = (
        await HTTP_CLIENT.get(
            url="https://api.bilibili.com/x/relation/blacks",
            params={"ps": page_size, "pn": page_index},
            cookies=credential.get_cookies(),
        )
    ).json()
    if result["code"] != 0:
        raise BiliHelperException(result)
    return result["data"]
