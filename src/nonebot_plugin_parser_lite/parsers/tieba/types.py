# Ref https://github.com/lumina37/aiotieba/blob/bae68256fd250d5178e1447899ffa155c77eda38/aiotieba/api/get_posts/_classdef.py
# 精简优化版

# pyright: reportAttributeAccessIssue=false
# pyright: reportIncompatibleMethodOverride=false
# pyright: reportArgumentType=false

import dataclasses as dcs
from enum import IntEnum
from functools import cached_property
import logging
import re
from typing import Any, Generic, Protocol, SupportsIndex, TypeVar, overload

from google.protobuf.message import Message
import yarl

TypeFragment = TypeVar("TypeFragment")
_IMAGEHASH_EXP = re.compile(r"/([a-z0-9]{32,})\.")
LOG = logging.getLogger(__name__)


class Gender(IntEnum):
    UNKNOWN = 0
    MALE = 1
    FEMALE = 2


class PrivLike(IntEnum):
    UNKNOWN = 0
    PUBLIC = 1
    FRIEND = 2
    HIDE = 3

    @classmethod
    def _missing_(cls, value: object):
        return cls.UNKNOWN


class PrivReply(IntEnum):
    UNKNOWN = 0
    ALL = 1
    FANS = 5
    FOLLOW = 6

    @classmethod
    def _missing_(cls, value: object):
        return cls.UNKNOWN


class ThreadType(IntEnum):
    UNKNOWN = -1
    ARTICLE = 0
    ALBUM = 1
    EXT_SHARE = 6
    VOICE = 11
    NETDISK = 14
    STORY = 31
    VIDEO = 40
    LIVE = 50
    HELP = 71
    VOTE = 75
    LOTTERY = 76

    @classmethod
    def _missing_(cls, value: object):
        return cls.UNKNOWN


@dcs.dataclass
class Containers(Generic[TypeFragment]):
    objs: list[TypeFragment] = dcs.field(default_factory=list)

    def __iter__(self):
        return iter(self.objs)

    @overload
    def __getitem__(self, index: SupportsIndex) -> TypeFragment: ...

    @overload
    def __getitem__(self, index: slice) -> list[TypeFragment]: ...

    def __getitem__(self, index):
        return self.objs[index]

    def __len__(self) -> int:
        return len(self.objs)

    def __bool__(self) -> bool:
        return bool(self.objs)


@dcs.dataclass
class TbErrorExt:
    err: Exception | None = dcs.field(default=None, init=False, repr=False)


@dcs.dataclass
class FragText:
    text: str = ""

    @staticmethod
    def from_proto(data_proto: Message):
        return FragText(data_proto.text)


class TypeFragText(Protocol):
    text: str


@dcs.dataclass
class FragEmoji:
    id: str = ""
    desc: str = ""

    @staticmethod
    def from_proto(data_proto: Message):
        return FragEmoji(data_proto.text, data_proto.c)


@dcs.dataclass
class FragAt:
    text: str = ""
    user_id: int = 0

    @staticmethod
    def from_proto(data_proto: Message):
        return FragAt(data_proto.text, data_proto.uid)


@dcs.dataclass
class FragVoice:
    md5: str = ""
    duration: float = 0.0

    @staticmethod
    def from_proto(data_proto: Message):
        return FragVoice(data_proto.voice_md5, data_proto.during_time / 1000)

    def __bool__(self) -> bool:
        return bool(self.md5)


@dcs.dataclass
class FragVideo:
    src: str = ""
    cover_src: str = ""
    duration: int = 0
    width: int = 0
    height: int = 0
    view_num: int = 0

    @staticmethod
    def from_proto(data_proto: Message):
        if hasattr(data_proto, "video_url"):
            return FragVideo(
                data_proto.video_url,
                data_proto.thumbnail_url,
                data_proto.video_duration,
                data_proto.video_width,
                data_proto.video_height,
                data_proto.play_count,
            )
        return FragVideo(
            data_proto.link,
            data_proto.src,
            data_proto.during_time,
            data_proto.width,
            data_proto.height,
            data_proto.count,
        )

    def __bool__(self) -> bool:
        return bool(self.width)


@dcs.dataclass
class FragLink:
    text: str = ""
    title: str = ""
    raw_url: yarl.URL = dcs.field(default_factory=yarl.URL)

    @staticmethod
    def from_proto(data_proto: Message):
        return FragLink(data_proto.link, data_proto.text, yarl.URL(data_proto.link))

    @cached_property
    def is_external(self) -> bool:
        return self.raw_url.path == "/mo/q/checkurl"

    @cached_property
    def url(self) -> yarl.URL:
        return yarl.URL(self.raw_url.query["url"]) if self.is_external else self.raw_url


@dcs.dataclass
class FragTiebaPlus:
    text: str = ""
    url: yarl.URL = dcs.field(default_factory=yarl.URL)

    @staticmethod
    def from_proto(data_proto: Message):
        info = data_proto.tiebaplus_info
        return FragTiebaPlus(info.desc, yarl.URL(info.jump_url))


@dcs.dataclass
class FragUnknown:
    data: Any

    @staticmethod
    def from_proto(data_proto: Message):
        return FragUnknown(data_proto)


@dcs.dataclass
class FragImage:
    src: str = dcs.field(default="", repr=False)
    big_src: str = dcs.field(default="", repr=False)
    origin_src: str = dcs.field(default="", repr=False)
    origin_size: int = 0
    show_width: int = 0
    show_height: int = 0
    hash: str = ""

    @staticmethod
    def from_proto(data_proto: Message):
        if hasattr(data_proto, "cdn_src"):
            src = data_proto.cdn_src
            big_src = data_proto.big_cdn_src
            origin_src = data_proto.origin_src
            origin_size = data_proto.origin_size
            width, _, height = data_proto.bsize.partition(",")
        else:
            src = data_proto.water_pic
            big_src = data_proto.small_pic
            origin_src = data_proto.big_pic
            origin_size = 0
            width = str(data_proto.width)
            height = str(data_proto.height)
        match = _IMAGEHASH_EXP.search(src)
        return FragImage(
            src,
            big_src,
            origin_src,
            origin_size,
            int(width),
            int(height),
            match.group(1) if match else "",
        )


def _proto_field(data_proto: Message, name: str, default: Any = None):
    return getattr(data_proto, name, default)


@dcs.dataclass
class Contents(Containers[TypeFragment]):
    texts: list[TypeFragText] = dcs.field(default_factory=list, repr=False)
    emojis: list[Any] = dcs.field(default_factory=list, repr=False)
    imgs: list[Any] = dcs.field(default_factory=list, repr=False)
    ats: list[Any] = dcs.field(default_factory=list, repr=False)
    links: list[Any] = dcs.field(default_factory=list, repr=False)
    tiebapluses: list[Any] = dcs.field(default_factory=list, repr=False)
    video: Any = dcs.field(default_factory=FragVideo, repr=False)
    voice: Any = dcs.field(default_factory=FragVoice, repr=False)

    @staticmethod
    def from_proto(data_proto: Message):
        groups = {
            name: []
            for name in ("texts", "emojis", "imgs", "ats", "links", "tiebapluses")
        }
        video, voice, objects = FragVideo(), FragVoice(), []
        for proto in data_proto.content:
            kind = proto.type
            if kind in (0, 9, 18, 27, 40):
                frag, group = FragText.from_proto(proto), "texts"
            elif kind in (2, 11):
                frag, group = FragEmoji.from_proto(proto), "emojis"
            elif kind in (3, 20):
                frag, group = FragImage.from_proto(proto), "imgs"
            elif kind == 4:
                frag, group = FragAt.from_proto(proto), "ats"
            elif kind == 1:
                frag, group = FragLink.from_proto(proto), "links"
            elif kind == 10:
                frag, voice, group = (
                    FragVoice.from_proto(proto),
                    FragVoice.from_proto(proto),
                    None,
                )
            elif kind == 5:
                frag, video, group = (
                    FragVideo.from_proto(proto),
                    FragVideo.from_proto(proto),
                    None,
                )
            elif kind in (35, 36, 37):
                frag, group = FragTiebaPlus.from_proto(proto), "tiebapluses"
            elif kind in (34, 52):
                continue
            else:
                frag, group = FragUnknown.from_proto(proto), None
            objects.append(frag)
            if group:
                groups[group].append(frag)
                if group in ("ats", "links", "tiebapluses"):
                    groups["texts"].append(frag)
        media = _proto_field(data_proto, "media", ())
        images = []
        for image_proto in media:
            image = FragImage.from_proto(image_proto)
            images.append(image)
            objects.append(image)

        video_info = _proto_field(data_proto, "video_info")
        if video_info and _proto_field(video_info, "video_width", 0):
            video = FragVideo.from_proto(video_info)
            objects.append(video)

        if voice_info := _proto_field(data_proto, "voice_info"):
            voice = FragVoice.from_proto(voice_info[0])
            objects.append(voice)

        return Contents(
            objects,
            groups["texts"],
            groups["emojis"],
            groups["imgs"] + images,
            groups["ats"],
            groups["links"],
            groups["tiebapluses"],
            video,
            voice,
        )

    @cached_property
    def text(self) -> str:
        return "".join(fragment.text for fragment in self.texts)


@dcs.dataclass
class UserInfo:
    user_id: int = 0
    portrait: str = ""
    user_name: str = ""
    nick_name_new: str = ""
    level: int = 0
    glevel: int = 0
    gender: Gender = Gender.UNKNOWN
    ip: str = ""
    icons: list[str] = dcs.field(default_factory=list)
    is_bawu: bool = False
    is_vip: bool = False
    is_god: bool = False
    priv_like: PrivLike = PrivLike.PUBLIC
    priv_reply: PrivReply = PrivReply.ALL

    @staticmethod
    def from_proto(data_proto: Message):
        portrait = data_proto.portrait
        return UserInfo(
            data_proto.id,
            portrait[:-13] if "?" in portrait else portrait,
            data_proto.name,
            data_proto.name_show,
            data_proto.level_id,
            data_proto.user_growth.level_id,
            Gender(data_proto.gender),
            data_proto.ip_address,
            [item.name for item in data_proto.iconinfo if item.name],
            bool(data_proto.is_bawu),
            bool(data_proto.new_tshow_icon),
            bool(data_proto.new_god_data.status),
            PrivLike(data_proto.priv_sets.like)
            if data_proto.priv_sets.like
            else PrivLike.PUBLIC,
            PrivReply(data_proto.priv_sets.reply)
            if data_proto.priv_sets.reply
            else PrivReply.ALL,
        )

    def __str__(self) -> str:
        return self.user_name or self.portrait or str(self.user_id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, UserInfo) and self.user_id == other.user_id

    def __hash__(self) -> int:
        return self.user_id

    def __bool__(self) -> bool:
        return bool(self.user_id)

    @property
    def nick_name(self) -> str:
        return self.nick_name_new

    @property
    def show_name(self) -> str:
        return self.nick_name_new or self.user_name

    @cached_property
    def log_name(self) -> str:
        return self.user_name or (
            f"{self.nick_name_new}/{self.portrait}"
            if self.portrait
            else str(self.user_id)
        )


@dcs.dataclass
class VoteOption:
    vote_num: int = 0
    text: str = ""

    @staticmethod
    def from_proto(data_proto: Message):
        return VoteOption(data_proto.num, data_proto.text)


@dcs.dataclass
class VoteInfo:
    title: str = ""
    is_multi: bool = False
    options: list[VoteOption] = dcs.field(default_factory=list)
    total_vote: int = 0
    total_user: int = 0

    @staticmethod
    def from_proto(data_proto: Message):
        return VoteInfo(
            data_proto.title,
            bool(data_proto.is_multi),
            [VoteOption.from_proto(item) for item in data_proto.options],
            data_proto.total_poll,
            data_proto.total_num,
        )

    def __len__(self) -> int:
        return len(self.options)

    def __bool__(self) -> bool:
        return bool(self.options)


@dcs.dataclass
class Comment:
    contents: Contents = dcs.field(default_factory=Contents)
    fid: int = 0
    fname: str = ""
    tid: int = 0
    ppid: int = 0
    pid: int = 0
    user: UserInfo = dcs.field(default_factory=UserInfo)
    author_id: int = 0
    reply_to_id: int = 0
    floor: int = 0
    agree: int = 0
    disagree: int = 0
    create_time: int = 0
    is_thread_author: bool = False

    @staticmethod
    def from_proto(data_proto: Message):
        return Comment(
            Contents.from_proto(data_proto),
            pid=data_proto.id,
            author_id=data_proto.author_id,
            agree=data_proto.agree.agree_num,
            disagree=data_proto.agree.disagree_num,
            create_time=data_proto.time,
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Comment) and self.pid == other.pid

    def __hash__(self) -> int:
        return self.pid

    @property
    def text(self) -> str:
        return self.contents.text


@dcs.dataclass
class Post:
    contents: Contents = dcs.field(default_factory=Contents)
    sign: str = ""
    comments: list[Comment] = dcs.field(default_factory=list)
    is_aimeme: bool = False
    fid: int = 0
    fname: str = ""
    tid: int = 0
    pid: int = 0
    user: UserInfo = dcs.field(default_factory=UserInfo)
    author_id: int = 0
    floor: int = 0
    reply_num: int = 0
    agree: int = 0
    disagree: int = 0
    create_time: int = 0
    is_thread_author: bool = False

    @staticmethod
    def from_proto(data_proto: Message):
        return Post(
            Contents.from_proto(data_proto),
            "".join(
                item.text for item in data_proto.signature.content if item.type == 0
            ),
            [
                Comment.from_proto(item)
                for item in data_proto.sub_post_list.sub_post_list
            ],
            bool(data_proto.sprite_meme_info.meme_id),
            pid=data_proto.id,
            author_id=data_proto.author_id,
            floor=data_proto.floor,
            reply_num=data_proto.sub_post_number,
            agree=data_proto.agree.agree_num,
            disagree=data_proto.agree.disagree_num,
            create_time=data_proto.time,
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Post) and self.pid == other.pid

    def __hash__(self) -> int:
        return self.pid

    @cached_property
    def text(self) -> str:
        return f"{self.contents.text}\n{self.sign}" if self.sign else self.contents.text


@dcs.dataclass
class Page:
    page_size: int = 0
    current_page: int = 0
    total_page: int = 0
    total_count: int = 0
    has_more: bool = False
    has_prev: bool = False

    @staticmethod
    def from_proto(data_proto: Message):
        return Page(
            data_proto.page_size,
            data_proto.current_page,
            data_proto.total_page,
            data_proto.total_count,
            bool(data_proto.has_more),
            bool(data_proto.has_prev),
        )


@dcs.dataclass
class Forum:
    fid: int = 0
    fname: str = ""
    category: str = ""
    subcategory: str = ""
    member_num: int = 0
    post_num: int = 0

    @staticmethod
    def from_proto(data_proto: Message):
        return Forum(
            data_proto.id,
            data_proto.name,
            data_proto.first_class,
            data_proto.second_class,
            data_proto.member_num,
            data_proto.post_num,
        )


@dcs.dataclass
class ShareThread:
    contents: Contents = dcs.field(default_factory=Contents)
    title: str = ""
    fid: int = 0
    fname: str = ""
    tid: int = 0
    author_id: int = 0
    vote_info: VoteInfo = dcs.field(default_factory=VoteInfo)

    @staticmethod
    def from_proto(data_proto: Message):
        return ShareThread(
            Contents.from_proto(data_proto),
            data_proto.title,
            data_proto.fid,
            data_proto.fname,
            int(data_proto.tid) if data_proto.tid else 0,
            data_proto.content[0].uid if data_proto.content else 0,
            VoteInfo.from_proto(data_proto.poll_info),
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ShareThread) and self.tid == other.tid

    def __hash__(self) -> int:
        return self.tid

    @cached_property
    def text(self) -> str:
        return (
            f"{self.title}\n{self.contents.text}" if self.title else self.contents.text
        )


@dcs.dataclass
class Thread:
    contents: Contents = dcs.field(default_factory=Contents)
    title: str = ""
    fid: int = 0
    fname: str = ""
    tid: int = 0
    pid: int = 0
    user: UserInfo = dcs.field(default_factory=UserInfo)
    type: ThreadType = ThreadType.UNKNOWN
    is_share: bool = False
    vote_info: VoteInfo = dcs.field(default_factory=VoteInfo)
    share_origin: ShareThread = dcs.field(default_factory=ShareThread)
    view_num: int = 0
    reply_num: int = 0
    share_num: int = 0
    agree: int = 0
    disagree: int = 0
    create_time: int = 0

    @staticmethod
    def from_proto(data_proto: Message):
        proto = data_proto.thread
        share = bool(proto.is_share_thread)
        origin = proto.origin_thread_info
        return Thread(
            Contents() if share else Contents.from_proto(origin),
            proto.title,
            tid=proto.id,
            pid=proto.post_id,
            user=UserInfo.from_proto(proto.author),
            type=ThreadType(proto.thread_type),
            is_share=share,
            vote_info=VoteInfo() if share else VoteInfo.from_proto(origin.poll_info),
            share_origin=ShareThread.from_proto(origin) if share else ShareThread(),
            view_num=data_proto.thread_freq_num,
            reply_num=proto.reply_num,
            share_num=proto.share_num,
            agree=proto.agree.agree_num,
            disagree=proto.agree.disagree_num,
            create_time=proto.create_time,
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Thread) and self.pid == other.pid

    def __hash__(self) -> int:
        return self.pid

    @property
    def text(self) -> str:
        return (
            f"{self.title}\n{self.contents.text}" if self.title else self.contents.text
        )

    @property
    def author_id(self) -> int:
        return self.user.user_id


@dcs.dataclass
class Posts(TbErrorExt, Containers[Post]):
    page: Page = dcs.field(default_factory=Page)
    forum: Forum = dcs.field(default_factory=Forum)
    thread: Thread = dcs.field(default_factory=Thread)

    @staticmethod
    def from_proto(data_proto: Message):
        page, forum, thread = (
            Page.from_proto(data_proto.page),
            Forum.from_proto(data_proto.forum),
            Thread.from_proto(data_proto),
        )
        thread.fid, thread.fname = forum.fid, forum.fname
        posts = [
            Post.from_proto(item)
            for item in data_proto.post_list
            if not item.chat_content.bot_uk
        ]
        users = {item.id: UserInfo.from_proto(item) for item in data_proto.user_list}
        for post in posts:
            post.fid, post.fname, post.tid = forum.fid, forum.fname, thread.tid
            post.user = users[post.author_id]
            post.is_thread_author = thread.author_id == post.author_id
            for comment in post.comments:
                comment.fid, comment.fname, comment.tid, comment.ppid, comment.floor = (
                    post.fid,
                    post.fname,
                    post.tid,
                    post.pid,
                    post.floor,
                )
                comment.user = users[comment.author_id]
                comment.is_thread_author = thread.author_id == comment.author_id
        return Posts(posts, page, forum, thread)

    @property
    def has_more(self) -> bool:
        return self.page.has_more


__all__ = [
    "Comment",
    "Contents",
    "Forum",
    "FragAt",
    "FragEmoji",
    "FragImage",
    "FragLink",
    "FragText",
    "FragTiebaPlus",
    "FragUnknown",
    "FragVideo",
    "FragVoice",
    "Gender",
    "Page",
    "Post",
    "Posts",
    "PrivLike",
    "PrivReply",
    "ShareThread",
    "Thread",
    "ThreadType",
    "UserInfo",
    "VoteInfo",
    "VoteOption",
]
