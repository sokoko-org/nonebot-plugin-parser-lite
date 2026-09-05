from .bilibili.app.archive.middleware.v1 import preload_pb2
from .bilibili.app.dynamic.v2 import dynamic_pb2
from .client import GRPC_CLIENT
from .credential import Credential
from .opus import Opus


class Dynamic:
    """
    动态类
    """

    def __init__(self, dynamic_id: str, credential: Credential | None = None) -> None:
        self.dynamic_id = dynamic_id
        self.credential = credential
        self.detail: dynamic_pb2.DynDetailReply | None = None
        self._is_opus = False

    async def get_info(self) -> dynamic_pb2.DynDetailReply:
        """
        获取动态信息

        :return: 调用 API 返回的结果
        """
        if self.detail is None:
            req = dynamic_pb2.DynDetailReq(
                uid=self.credential.mid if self.credential else 0,
                dynamic_id=self.dynamic_id,
                share_id="dt.opus-detail.0.0.pv",
                share_mode=3,
                local_time=8,
                player_args=preload_pb2.PlayerArgs(qn=32, fnval=400),
            )
            access_token = self.credential.access_token if self.credential else ""
            self.detail = await GRPC_CLIENT.request(
                "/bilibili.app.dynamic.v2.Dynamic/DynDetail",
                req,
                dynamic_pb2.DynDetailReply,
                access_token=access_token,
                user_mid=self.credential.mid
                if self.credential and access_token
                else None,
            )
            self._is_opus = self.detail.HasField("item") and (
                self.detail.item.card_type
                in (dynamic_pb2.draw, dynamic_pb2.article)
            )
        return self.detail

    async def is_opus(self) -> bool:
        """
        判断动态详情是否应使用 Opus 接口渲染

        DynDetail 将图文和专栏分别标记为 ``draw``、``article``，两者
        都需要继续请求 OpusDetail；转发等其他动态类型则保留动态渲染

        :return: 是否应使用 Opus 接口
        """
        if self.detail is None:
            await self.get_info()
        return self._is_opus

    def turn_to_opus(self) -> Opus:
        """
        将需要 Opus 渲染的动态转换为 Opus 对象

        :return: 图文对象
        """
        return Opus(oid=self.dynamic_id, credential=self.credential)
