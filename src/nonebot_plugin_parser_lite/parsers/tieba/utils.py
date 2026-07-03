from functools import lru_cache
from pathlib import Path

from google.protobuf import descriptor_pb2, descriptor_pool
from google.protobuf.message_factory import GetMessageClass
from httpx import AsyncClient

from ...constants import STICKER_CDN
from ...creator import Creator
from ...data import Comment, ContentItem
from .models import (
    Contents,
    FragAt,
    FragEmoji,
    FragImage,
    FragLink,
    FragText,
    FragVideo,
    Post,
    Posts,
)

_CLIENT = AsyncClient()


@lru_cache(maxsize=2)
def get_message(name: str):
    fds = descriptor_pb2.FileDescriptorSet()
    fds.ParseFromString((Path(__file__).parent / f"{name}.desc").read_bytes())
    pool = descriptor_pool.DescriptorPool()
    for fd in fds.file:
        pool.Add(fd)

    msg_descriptor = pool.FindMessageTypeByName(name)
    return GetMessageClass(msg_descriptor)


async def close_client() -> None:
    await _CLIENT.aclose()


def make_req(tid: int) -> bytes:
    req_proto = get_message("PbPageReqIdl")()
    req_proto.data.common._client_type = 2  # pyright: ignore[reportAttributeAccessIssue]
    req_proto.data.common._client_version = "12.64.1.1"  # pyright: ignore[reportAttributeAccessIssue]
    req_proto.data.kz = tid  # pyright: ignore[reportAttributeAccessIssue]
    req_proto.data.pn = 1  # pyright: ignore[reportAttributeAccessIssue]
    req_proto.data.rn = 30  # pyright: ignore[reportAttributeAccessIssue]
    req_proto.data.r = 0  # pyright: ignore[reportAttributeAccessIssue]
    req_proto.data.lz = 0  # pyright: ignore[reportAttributeAccessIssue]
    req_proto.data.with_floor = 1  # pyright: ignore[reportAttributeAccessIssue]
    req_proto.data.floor_sort_type = 1  # pyright: ignore[reportAttributeAccessIssue]
    req_proto.data.floor_rn = 4  # pyright: ignore[reportAttributeAccessIssue]
    return req_proto.SerializeToString()


async def pack_req(data: bytes) -> bytes:
    """
    打包移动端protobuf请求

    :param data: protobuf序列化后的二进制数据
    :return: bytes
    """
    boundary = "-*_r1999"

    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="data"; filename="file"\r\n'
            f"\r\n"
        ).encode()
        + data
        + f"\r\n--{boundary}--\r\n".encode()
    )

    # 设置 Content-Type，带上固定 boundary
    response = await _CLIENT.post(
        "http://tiebac.baidu.com/c/f/pb/page",
        headers={
            "x_bd_data_type": "protobuf",
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "miku/39",
            "Host": "tiebac.baidu.com",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        params={"cmd": 302001},
        content=body,
    )
    return response.content


def parse_res(data: bytes) -> Posts:
    res = get_message("PbPageResIdl")()
    res.ParseFromString(data)
    if res.error.errorno:  # pyright: ignore[reportAttributeAccessIssue]
        raise ValueError(res.error.errmsg)  # pyright: ignore[reportAttributeAccessIssue]

    data_proto = res.data  # pyright: ignore[reportAttributeAccessIssue]
    return Posts.from_tbdata(data_proto)


async def get_post(tid: int) -> Posts:
    req = make_req(tid)
    data = await pack_req(req)
    return parse_res(data)


def build_content(posts: Posts) -> list[ContentItem]:
    """
    构建帖子内容

    :param posts: Posts数据

    :return: 富文本内容列表
    """
    contents: list[ContentItem] = [posts.thread.title]

    # 提取帖子正文
    for part in posts.objs[0].contents.objs:
        if isinstance(part, FragText):
            contents.append(part.text)
        elif isinstance(part, FragEmoji):
            contents.append(
                Creator.sticker(
                    url=STICKER_CDN.format(platform="tieba", name=part.id),
                    size="small",
                    desc=part.desc,
                )
            )
        elif isinstance(part, FragImage):
            contents.append(
                Creator.graphic(
                    url=part.origin_src,
                    ext_headers={"Referer": "https://tieba.baidu.com/"},
                )
            )
        elif isinstance(part, FragAt):
            # 如果上一项是文本，则追加到上一项末尾
            if contents and isinstance(contents[-1], str):
                contents[-1] += f"@{part.text} "
            else:
                contents.append(f"@{part.text} ")
        elif isinstance(part, FragLink):
            url_str = str(part.url)
            if contents and isinstance(contents[-1], str):
                contents[-1] += url_str
            else:
                contents.append(url_str)
        elif isinstance(part, FragVideo):
            contents.append(
                Creator.video(
                    url_or_task=part.src,
                    cover_url=part.cover_src,
                    duration=part.duration,
                    ext_headers={"Referer": "https://tieba.baidu.com/"},
                )
            )
        # 经过测试，所有帖子中的语音均无法播放，无法进行地址捕获
        # 现在好像也发不了这玩意了
        # 最近的语音消息在2018年
        # elif isinstance(part, FragVoice):
        #     audio_task = DOWNLOADER.download_audio(part.md5, ext_headers=headers)
        #     contents.append(post.create_audio_content(audio_task, part.duration))

    return contents


def build_comment(contents: Contents) -> list[ContentItem]:
    """
    构建帖子评论内容

    :param contents: 内容碎片列表
    """
    content: list[ContentItem] = []
    for part in contents.objs:
        if isinstance(part, FragText):
            content.append(part.text)
        elif isinstance(part, FragEmoji):
            content.append(
                Creator.sticker(
                    url=STICKER_CDN.format(platform="tieba", name=part.id),
                    size="small",
                    desc=part.desc,
                )
            )
        elif isinstance(part, FragImage):
            content.append(Creator.graphic(part.origin_src))
        elif isinstance(part, FragAt):
            content.append(f"@{part.text} ")
        elif isinstance(part, FragLink):
            content.append(str(part.url))
    return content


def build_comments(posts: list[Post], poster_id: int) -> list[Comment]:
    """
    构建帖子评论

    :param posts: 评论列表
    :param poster_id: 帖子作者id
    """
    comments = []
    # 获取前10条评论（优先显示楼主的评论）
    main_comments = []
    other_comments = []

    for post in posts:  # 跳过主楼
        if post.user.user_id == poster_id:
            main_comments.append(post)
        else:
            other_comments.append(post)

    # 合并评论，优先显示楼主的评论
    combined_comments: list[Post] = main_comments[:5] + other_comments[:5]

    for post in combined_comments:
        comment_author = Creator.author(
            name=post.user.show_name,
            avatar_url=f"http://tb.himg.baidu.com/sys/portraith/item/{post.user.portrait}",
            id=post.user.portrait,
            location=post.user.ip,
        )
        # 处理楼中楼评论
        child_posts = []
        if post.comments:
            child_posts.extend(
                Creator.comment(
                    author=Creator.author(
                        name=comment.user.show_name,
                        avatar_url=f"http://tb.himg.baidu.com/sys/portraith/item/{comment.user.portrait}",
                        id=comment.user.portrait,
                        location=comment.user.ip,
                    ),
                    content=build_comment(comment.contents),
                    timestamp=comment.create_time,
                    stats=Creator.stats(
                        like_count=str(comment.agree) if comment.agree else None
                    ),
                    parent_author=comment_author,
                )
                for comment in post.comments[:3]
            )
        comments.append(
            Creator.comment(
                author=comment_author,
                content=build_comment(post.contents),
                timestamp=post.create_time,
                stats=Creator.stats(
                    like_count=str(post.agree), comment_count=str(post.reply_num)
                ),
                replies=child_posts,
            )
        )
    return comments
