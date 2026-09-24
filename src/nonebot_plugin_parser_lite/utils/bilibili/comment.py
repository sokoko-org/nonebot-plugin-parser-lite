from enum import IntEnum

from .bilibili.main.community.reply.v1 import reply_pb2
from .client import GRPC_CLIENT
from .credential import Credential


class CommentResourceType(IntEnum):
    """
    资源类型枚举
    """

    VIDEO = 1
    """视频"""
    OPUS = 11
    """图文动态"""
    ARTICLE = 12
    """专栏文章"""
    DYNAMIC = 17
    """动态"""


async def get_comments(
    oid: int,
    type: CommentResourceType,
    credential: Credential | None = None,
) -> reply_pb2.MainListReply:
    """
    获取资源评论列表(wbi)

    :param oid: 资源 ID
    :param type_: 资源类枚举
    :param credential: 凭证, defaults to None
    :raises BiliHelperError: _description_
    :return: 调用 API 返回的结果, 现在不想写翻页
    """
    req = reply_pb2.MainListReq(
        oid=oid,
        type=type.value,
        cursor=reply_pb2.CursorReq(
            next=0,
            mode=reply_pb2.MAIN_LIST_HOT,
        ),
    )
    if type is CommentResourceType.DYNAMIC:
        req.extra = '{"spmid":"dt.dt-detail.0.0","from_spmid":""}'
        req.filter_tag_name = "全部"
    access_token = credential.access_token if credential else ""
    return await GRPC_CLIENT.request(
        "/bilibili.main.community.reply.v1.Reply/MainList",
        req,
        reply_pb2.MainListReply,
        access_token=access_token,
        user_mid=credential.mid if credential and access_token else None,
    )
