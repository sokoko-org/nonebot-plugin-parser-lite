# pyright: reportAttributeAccessIssue=false

import contextlib
from typing import Any
from pathlib import Path
from datetime import datetime

from httpx import AsyncClient, NetworkError
from google.protobuf import descriptor_pb2, descriptor_pool
from google.protobuf.message_factory import GetMessageClass
from ..data import MediaContent, VideoContent, StickerContent, GraphicContent
from .models import (
    Post,
    Posts,
    FragAt,
    Contents,
    FragLink,
    FragText,
    FragEmoji,
    FragImage,
    FragVideo,
)
from ...download import DOWNLOADER
from ...constants import COMMON_HEADER

headers = COMMON_HEADER.copy()


def get_message(name: str):
    fds = descriptor_pb2.FileDescriptorSet()
    fds.ParseFromString((Path(__file__).parent / f"{name}.desc").read_bytes())
    pool = descriptor_pool.DescriptorPool()
    for fd in fds.file:
        pool.Add(fd)

    msg_descriptor = pool.FindMessageTypeByName(name)
    return GetMessageClass(msg_descriptor)


def make_req(tid: int) -> bytes:
    req_proto = get_message("PbPageReqIdl")()
    req_proto.data.common._client_type = 2
    req_proto.data.common._client_version = "12.64.1.1"
    req_proto.data.kz = tid
    req_proto.data.pn = 1
    req_proto.data.rn = 30
    req_proto.data.r = 0
    req_proto.data.lz = 0
    req_proto.data.with_floor = True
    req_proto.data.floor_sort_type = True
    req_proto.data.floor_rn = 4
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
    async with AsyncClient(verify=False) as client:
        response = await client.post(
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
    if res.error.errorno:
        raise NetworkError(res.error.errmsg)

    data_proto = res.data
    return Posts.from_tbdata(data_proto)


async def get_post(tid: int) -> Posts:
    req = make_req(tid)
    data = await pack_req(req)
    return parse_res(data)


def build_contents(posts: Posts) -> list[MediaContent | str]:
    """
    构建帖子内容

    :param posts: Posts数据

    :return: 富文本内容列表
    """
    contents: list[MediaContent | str] = [posts.thread.title]

    # 提取帖子正文
    for part in posts.objs[0].contents.objs:
        if isinstance(part, FragText):
            contents.append(part.text)
        elif isinstance(part, FragEmoji):
            sticker_task = DOWNLOADER.download_img(
                f"https://tb3.bdstatic.com/emoji/{part.id}@2x.png",
                ext_headers=headers,
            )
            contents.append(StickerContent(sticker_task, "small", part.desc))
        elif isinstance(part, FragImage):
            image_task = DOWNLOADER.download_img(part.origin_src, ext_headers=headers)
            contents.append(GraphicContent(image_task))
        elif isinstance(part, FragAt):
            # 如果上一项是文本，则追加到上一项末尾
            if contents and isinstance(contents[-1], str):
                contents[-1] += f"@{part.text}&nbsp;"  # &nbsp;
            else:
                contents.append(f"@{part.text}&nbsp;")
        elif isinstance(part, FragLink):
            url_str = str(part.url)
            if contents and isinstance(contents[-1], str):
                contents[-1] += url_str
            else:
                contents.append(url_str)
        elif isinstance(part, FragVideo):
            video_task = DOWNLOADER.download_video(part.src, ext_headers=headers)
            cover_task = DOWNLOADER.download_img(part.cover_src, ext_headers=headers)
            contents.append(VideoContent(video_task, cover_task, part.duration))
        # 经过测试，所有帖子中的语音均无法播放，无法进行地址捕获
        # 现在好像也发不了这玩意了
        # 最近的语音消息在2018年
        # elif isinstance(part, FragVoice):
        #     audio_task = DOWNLOADER.download_audio(part.md5, ext_headers=headers)
        #     contents.append(post.create_audio_content(audio_task, part.duration))

    return contents


def build_comment_content(contents: Contents) -> str:
    """
    构建帖子评论HTML内容

    :param contents: 内容碎片列表
    """
    content = ""
    for part in contents.objs:
        if isinstance(part, FragText):
            content += part.text
        elif isinstance(part, FragEmoji):
            content += f'<img class="sticker small" src="https://tb3.bdstatic.com/emoji/{part.id}@2x.png">'
        elif isinstance(part, FragImage):
            content += (
                '<div class="images-container">'
                f'<div class="images-grid single">'
                '<div class="image-item">'
                f'<img src="{part.origin_src}">'
                "</div></div></div>"
            )
        elif isinstance(part, FragAt):
            content += f"@{part.text}&nbsp;"
        elif isinstance(part, FragLink):
            content += str(part.url)
    return content


def build_comments(posts: list[Post], poster_id: int) -> list[dict[str, Any]]:
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
        # 处理评论作者信息
        comment_author = {
            "name": post.user.show_name,
            "avatar": f"http://tb.himg.baidu.com/sys/portraith/item/{post.user.portrait}",
        }

        # 处理评论时间
        formatted_time = ""
        if post.create_time:
            with contextlib.suppress(Exception):
                dt = datetime.fromtimestamp(post.create_time)
                formatted_time = dt.strftime("%Y-%m-%d %H:%M")
        # 处理楼中楼评论
        child_posts = []
        if post.comments:
            for comment in post.comments[:3]:  # 每个评论最多显示3条楼中楼
                child_author = {
                    "name": comment.user.show_name,
                    "avatar": f"http://tb.himg.baidu.com/sys/portraith/item/{comment.user.portrait}",
                }

                child_formatted_time = ""
                if hasattr(comment, "create_time") and comment.create_time:
                    with contextlib.suppress(Exception):
                        dt = datetime.fromtimestamp(comment.create_time)
                        child_formatted_time = dt.strftime("%Y-%m-%d %H:%M")
                child_posts.append(
                    {
                        "author": child_author,
                        "content": build_comment_content(comment.contents),
                        "formatted_time": child_formatted_time,
                        "ups": comment.agree,
                    }
                )

        comments.append(
            {
                "author": comment_author,
                "content": build_comment_content(post.contents),
                "formatted_time": formatted_time,
                "ups": post.agree,
                "comments": len(child_posts),
                "child_posts": child_posts,
            }
        )
    return comments
