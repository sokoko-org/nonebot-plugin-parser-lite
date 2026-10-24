from .bilibili.app.archive.middleware.v1 import preload_pb2
from .bilibili.app.dynamic.v2 import opus_pb2
from .client import GRPC_CLIENT
from .credential import Credential


class Opus:
    """
    图文类
    """

    def __init__(self, oid: int | str, credential: Credential | None = None) -> None:
        self.oid = int(oid)
        self.credential = credential
        self.info: opus_pb2.OpusDetailResp | None = None

    async def get_info(self) -> opus_pb2.OpusDetailResp:
        """
        获取图文基本信息

        :return: 调用 API 返回的结果
        """
        if self.info is None:
            req = opus_pb2.OpusDetailReq(
                oid=self.oid,
                share_id="dt.opus-detail.0.0.pv",
                share_mode=3,
                local_time=8,
                player_args=preload_pb2.PlayerArgs(qn=32, fnval=400),
            )
            access_token = self.credential.access_token if self.credential else ""
            self.info = await GRPC_CLIENT.request(
                "/bilibili.app.dynamic.v2.Opus/OpusDetail",
                req,
                opus_pb2.OpusDetailResp,
                access_token=access_token,
                user_mid=(
                    self.credential.mid if self.credential and access_token else None
                ),
            )
        return self.info
