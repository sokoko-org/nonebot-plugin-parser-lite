# Ref https://github.com/lumina37/aiotieba/blob/ad99009d6584bb5341b8cf11cd0095085f81f414/aiotieba/api/get_posts/_classdef.py
# 精简优化版

# pyright: reportAttributeAccessIssue=false
# pyright: reportIncompatibleMethodOverride=false
# pyright: reportArgumentType=false


from __future__ import annotations

from collections.abc import Iterator
import dataclasses as dcs
from enum import IntEnum
from functools import cached_property
import re
from typing import Any, Generic, Protocol, SupportsIndex, TypeVar, overload

from google.protobuf.message import Message
import yarl

TypeContainer = TypeVar("TypeContainer")

TypeFragment = TypeVar("TypeFragment")


@dcs.dataclass
class FragText:
    """
    纯文本碎片

    Attributes:
        text (str): 文本内容
    """

    text: str = ""

    @staticmethod
    def from_tbdata(data_proto: Message) -> FragText:
        text = data_proto.text
        return FragText(text)


class TypeFragText(Protocol):
    text: str


@dcs.dataclass
class FragEmoji:
    """
    表情碎片

    Attributes:
        id (str): 表情图片id
        desc (str): 表情描述
    """

    id: str = ""
    desc: str = ""

    @staticmethod
    def from_tbdata(data_proto: Message) -> FragEmoji:
        id_ = data_proto.text
        desc = data_proto.c
        return FragEmoji(id_, desc)


class TypeFragEmoji(Protocol):
    id: str
    desc: str


_IMAGEHASH_EXP = re.compile(r"/([a-z0-9]{32,})\.")


@dcs.dataclass
class FragImage:
    """
    图像碎片

    Attributes:
        src (str): 小图链接 宽720px
        big_src (str): 大图链接 宽960px
        origin_src (str): 原图链接
        origin_size (int): 原图大小
        show_width (int): 图像在客户端预览显示的宽度
        show_height (int): 图像在客户端预览显示的高度
        hash (str): 百度图床hash
    """

    src: str = dcs.field(default="", repr=False)
    big_src: str = dcs.field(default="", repr=False)
    origin_src: str = dcs.field(default="", repr=False)
    origin_size: int = 0
    show_width: int = 0
    show_height: int = 0
    hash: str = ""

    @staticmethod
    def from_tbdata(data_proto: Message) -> FragImage:
        src = data_proto.cdn_src
        big_src = data_proto.big_cdn_src
        origin_src = data_proto.origin_src
        origin_size = data_proto.origin_size

        show_width, _, show_height = data_proto.bsize.partition(",")
        show_width = int(show_width)
        show_height = int(show_height)

        if hash_obj := _IMAGEHASH_EXP.search(src):
            hash_ = hash_obj[1]
        else:
            hash_ = ""
        return FragImage(
            src, big_src, origin_src, origin_size, show_width, show_height, hash_
        )


@dcs.dataclass
class TypeFragImage(Protocol):
    src: str
    origin_src: str
    hash: str


@dcs.dataclass
class FragAt:
    """
    @碎片

    Attributes:
        text (str): 被@用户的昵称 含@
        user_id (int): 被@用户的user_id
    """

    text: str = ""
    user_id: int = 0

    @staticmethod
    def from_tbdata(data_proto: Message) -> FragAt:
        text = data_proto.text
        user_id = data_proto.uid
        return FragAt(text, user_id)


class TypeFragAt(Protocol):
    text: str
    user_id: int


@dcs.dataclass
class FragVoice:
    """
    音频碎片

    Attributes:
        md5 (str): 音频md5
        duration (int): 音频长度 以秒为单位
    """

    md5: str = ""
    duration: int = 0

    @staticmethod
    def from_tbdata(data_proto: Message) -> FragVoice:
        md5 = data_proto.voice_md5
        duration = data_proto.during_time / 1000
        return FragVoice(md5, duration)

    def __bool__(self) -> bool:
        return bool(self.md5)


class TypeFragVoice(Protocol):
    md5: str
    duration: int


@dcs.dataclass
class FragVideo:
    """
    视频碎片

    Attributes:
        src (str): 视频链接
        cover_src (str): 封面链接
        duration (int): 视频长度
        width (int): 视频宽度
        height (int): 视频高度
        view_num (int): 浏览次数
    """

    src: str = ""
    cover_src: str = ""
    duration: int = 0
    width: int = 0
    height: int = 0
    view_num: int = 0

    @staticmethod
    def from_tbdata(data_proto: Message) -> FragVideo:
        src = data_proto.video_url
        cover_src = data_proto.thumbnail_url
        duration = data_proto.video_duration
        width = data_proto.video_width
        height = data_proto.video_height
        view_num = data_proto.play_count
        return FragVideo(src, cover_src, duration, width, height, view_num)

    def __bool__(self) -> bool:
        return bool(self.width)


class TypeFragVideo(Protocol):
    src: str
    cover_src: str
    duration: int
    width: int
    height: int
    view_num: int


@dcs.dataclass
class FragLink:
    """
    链接碎片

    Attributes:
        text (str): 原链接
        title (str): 链接标题
        raw_url (yarl.URL): 解析后的原链接
        url (yarl.URL): 解析后的去前缀链接
        is_external (bool): 是否外部链接
    """

    text: str = ""
    title: str = ""
    raw_url: yarl.URL = dcs.field(default_factory=yarl.URL)

    @staticmethod
    def from_tbdata(data_proto: Message) -> FragLink:
        text = data_proto.link
        title = data_proto.text
        raw_url = yarl.URL(text)
        return FragLink(text, title, raw_url)

    @cached_property
    def url(self) -> yarl.URL:
        return yarl.URL(self.raw_url.query["url"]) if self.is_external else self.raw_url

    @cached_property
    def is_external(self) -> bool:
        return self.raw_url.path == "/mo/q/checkurl"


class TypeFragLink(Protocol):
    text: str
    title: str
    raw_url: yarl.URL

    @property
    def url(self) -> yarl.URL: ...

    @property
    def is_external(self) -> bool: ...


@dcs.dataclass
class FragTiebaPlus:
    """
    贴吧plus广告碎片

    Attributes:
        text (str): 贴吧plus广告描述
        url (yarl.URL): 解析后的贴吧plus广告跳转链接
    """

    text: str = ""
    url: yarl.URL = dcs.field(default_factory=yarl.URL)

    @staticmethod
    def from_tbdata(data_proto: Message) -> FragTiebaPlus:
        text = data_proto.tiebaplus_info.desc
        url = yarl.URL(data_proto.tiebaplus_info.jump_url)
        return FragTiebaPlus(text, url)


class TypeFragTiebaPlus(Protocol):
    text: str
    url: yarl.URL


@dcs.dataclass
class FragItem:
    """
    item碎片

    Attributes:
        text (str): item名称
    """

    text: str = ""

    @staticmethod
    def from_tbdata(data_proto: Message) -> FragItem:
        text = data_proto.item.item_name
        return FragItem(text)


class TypeFragItem(Protocol):
    text: str


@dcs.dataclass
class FragUnknown:
    """
    未知碎片

    Attributes:
        data (Any): 原始数据
    """

    proto: Any

    @staticmethod
    def from_tbdata(data: Any) -> FragUnknown:
        return FragUnknown(data)


@dcs.dataclass
class VoteOption:
    """
    投票选项信息

    Attributes:
        vote_num (int): 得票数
        text (str): 选项描述文字
    """

    vote_num: int = 0
    text: str = ""

    @staticmethod
    def from_tbdata(data_proto: Message) -> VoteOption:
        vote_num = data_proto.num
        text = data_proto.text
        return VoteOption(vote_num, text)


@dcs.dataclass
class VoteInfo:
    """
    投票信息

    Attributes:
        title (str): 投票标题
        is_multi (bool): 是否多选
        options (list[VoteOption]): 选项列表
        total_vote (int): 总投票数
        total_user (int): 总投票人数
    """

    title: str = ""
    is_multi: bool = False
    options: list[VoteOption] = dcs.field(default_factory=list)
    total_vote: int = 0
    total_user: int = 0

    @staticmethod
    def from_tbdata(data_proto: Message) -> VoteInfo:
        title = data_proto.title
        is_multi = bool(data_proto.is_multi)
        options = [VoteOption.from_tbdata(p) for p in data_proto.options]
        total_vote = data_proto.total_poll
        total_user = data_proto.total_num
        return VoteInfo(title, is_multi, options, total_vote, total_user)

    def __len__(self) -> int:
        return len(self.options)

    def __bool__(self) -> bool:
        return bool(self.options)


@dcs.dataclass
class Containers(Generic[TypeContainer]):
    """
    内容列表的泛型基类
    约定取内容的通用接口

    Attributes:
        objs (list[TypeContainer]): 内容列表
    """

    objs: list[TypeContainer] = dcs.field(default_factory=list)

    def __iter__(self) -> Iterator[TypeContainer]:
        return self.objs.__iter__()

    @overload
    def __getitem__(self, idx: SupportsIndex) -> TypeContainer: ...

    @overload
    def __getitem__(self, idx: slice) -> list[TypeContainer]: ...

    def __getitem__(self, idx):
        return self.objs.__getitem__(idx)

    def __setitem__(self, idx, val):
        raise NotImplementedError

    def __delitem__(self, idx):
        raise NotImplementedError

    def __len__(self) -> int:
        return self.objs.__len__()

    def __bool__(self) -> bool:
        return bool(self.objs)


class Gender(IntEnum):
    """
    用户性别

    Note:
        UNKNOWN 未知\n
        MALE 男性\n
        FEMALE 女性
    """

    UNKNOWN = 0
    MALE = 1
    FEMALE = 2


class PrivLike(IntEnum):
    """
    关注吧列表的公开状态

    Note:
        PUBLIC 所有人可见\n
        FRIEND 好友可见\n
        HIDE 完全隐藏
    """

    PUBLIC = 1
    FRIEND = 2
    HIDE = 3


class PrivReply(IntEnum):
    """
    帖子评论权限

    Note:
        ALL 允许所有人\n
        UNKNOWN 未知分类\n
        FANS 仅允许我的粉丝\n
        FOLLOW 仅允许我的关注
    """

    ALL = 1
    UNKNOWN = 2
    FANS = 5
    FOLLOW = 6


@dcs.dataclass
class Contents(
    Containers[
        FragText
        | FragEmoji
        | FragImage
        | FragAt
        | FragLink
        | FragVoice
        | FragVideo
        | FragTiebaPlus
        | FragUnknown
    ]
):
    """
    内容碎片列表

    Attributes:
        objs (list[TypeFragment]): 所有内容碎片的混合列表

        text (str): 文本内容

        texts (list[TypeFragText]): 纯文本碎片列表
        emojis (list[FragEmoji_p]): 表情碎片列表
        imgs (list[FragImage_p]): 图像碎片列表
        ats (list[FragAt_p]): @碎片列表
        links (list[FragLink_p]): 链接碎片列表
        tiebapluses (list[FragTiebaPlus_p]): 贴吧plus碎片列表
        video (FragVideo_p): 视频碎片
        voice (FragVoice_p): 音频碎片
    """

    texts: list[TypeFragText] = dcs.field(default_factory=list, repr=False)
    emojis: list[FragEmoji] = dcs.field(default_factory=list, repr=False)
    imgs: list[FragImage] = dcs.field(default_factory=list, repr=False)
    ats: list[FragAt] = dcs.field(default_factory=list, repr=False)
    links: list[FragLink] = dcs.field(default_factory=list, repr=False)
    tiebapluses: list[FragTiebaPlus] = dcs.field(default_factory=list, repr=False)
    video: FragVideo = dcs.field(default_factory=FragVideo, repr=False)
    voice: FragVoice = dcs.field(default_factory=FragVoice, repr=False)

    @staticmethod
    def from_tbdata(data_proto: Message) -> Contents:
        content_protos = data_proto.content

        texts = []
        emojis = []
        imgs = []
        ats = []
        links = []
        tiebapluses = []
        video = FragVideo()
        voice = FragVoice()

        def _frags():
            for proto in content_protos:
                _type = proto.type
                # 0纯文本 9电话号 18话题 27百科词条 40梗百科
                if _type in [0, 9, 18, 27, 40]:
                    frag = FragText.from_tbdata(proto)
                    texts.append(frag)
                    yield frag
                # 11:tid=5047676428
                elif _type in [2, 11]:
                    frag = FragEmoji.from_tbdata(proto)
                    emojis.append(frag)
                    yield frag
                # 20:tid=5470214675
                elif _type in [3, 20]:
                    frag = FragImage.from_tbdata(proto)
                    imgs.append(frag)
                    yield frag
                elif _type == 4:
                    frag = FragAt.from_tbdata(proto)
                    ats.append(frag)
                    texts.append(frag)
                    yield frag
                elif _type == 1:
                    frag = FragLink.from_tbdata(proto)
                    links.append(frag)
                    texts.append(frag)
                    yield frag
                elif _type == 10:  # voice
                    frag = FragVoice.from_tbdata(proto)
                    nonlocal voice
                    voice = frag
                    yield frag
                elif _type == 5:  # video
                    frag = FragVideo.from_tbdata(proto)
                    nonlocal video
                    video = frag
                    yield frag
                # 35|36:tid=7769728331 / 37:tid=7760184147
                elif _type in [35, 36, 37]:
                    frag = FragTiebaPlus.from_tbdata(proto)
                    tiebapluses.append(frag)
                    texts.append(frag)
                    yield frag
                # outdated tiebaplus
                elif _type == 34:
                    continue
                else:
                    yield FragUnknown.from_tbdata(proto)

        objs = list(_frags())

        return Contents(
            objs, texts, emojis, imgs, ats, links, tiebapluses, video, voice
        )

    @cached_property
    def text(self) -> str:
        return "".join(frag.text for frag in self.texts)


@dcs.dataclass
class UserInfo:
    """
    用户信息

    Attributes:
        user_id (int): user_id
        portrait (str): portrait
        user_name (str): 用户名
        nick_name_new (str): 新版昵称

        level (int): 等级
        glevel (int): 贴吧成长等级
        gender (int): 性别
        ip (str): ip归属地
        icons (list[str]): 印记信息

        is_bawu (bool): 是否吧务
        is_vip (bool): 是否超级会员
        is_god (bool): 是否大神
        priv_like (PrivLike): 关注吧列表的公开状态
        priv_reply (PrivReply): 帖子评论权限

        nick_name (str): 用户昵称
        show_name (str): 显示名称
        log_name (str): 用于在日志中记录用户信息
    """

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
    def from_tbdata(data_proto: Message) -> UserInfo:
        user_id = data_proto.id
        portrait = data_proto.portrait
        if "?" in portrait:
            portrait = portrait[:-13]
        user_name = data_proto.name
        nick_name_new = data_proto.name_show
        level = data_proto.level_id
        glevel = data_proto.user_growth.level_id
        gender = Gender(data_proto.gender)
        ip = data_proto.ip_address
        icons = [name for i in data_proto.iconinfo if (name := i.name)]
        is_bawu = bool(data_proto.is_bawu)
        is_vip = bool(data_proto.new_tshow_icon)
        is_god = bool(data_proto.new_god_data.status)
        priv_like = (
            PrivLike(priv_like)
            if (priv_like := data_proto.priv_sets.like)
            else PrivLike.PUBLIC
        )
        priv_reply = (
            PrivReply(priv_reply)
            if (priv_reply := data_proto.priv_sets.reply)
            else PrivReply.ALL
        )
        return UserInfo(
            user_id,
            portrait,
            user_name,
            nick_name_new,
            level,
            glevel,
            gender,
            ip,
            icons,
            is_bawu,
            is_vip,
            is_god,
            priv_like,
            priv_reply,
        )

    def __str__(self) -> str:
        return self.user_name or self.portrait or str(self.user_id)

    def __eq__(self, obj: UserInfo) -> bool:
        return self.user_id == obj.user_id

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
        if self.user_name:
            return self.user_name
        elif self.portrait:
            return f"{self.nick_name_new}/{self.portrait}"
        else:
            return str(self.user_id)


@dcs.dataclass
class Comment:
    """
    楼中楼信息

    Attributes:
        text (str): 文本内容
        contents (Contents): 正文内容碎片列表

        fid (int): 所在吧id
        fname (str): 所在贴吧名
        tid (int): 所在主题帖id
        ppid (int): 所在楼层id
        pid (int): 楼中楼id
        user (UserInfo): 发布者的用户信息
        author_id (int): 发布者的user_id
        reply_to_id (int): 被回复者的user_id

        floor (int): 所在楼层数
        agree (int): 点赞数
        disagree (int): 点踩数
        create_time (int): 创建时间 10位时间戳 以秒为单位
        is_thread_author (bool): 是否楼主
    """

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
    def from_tbdata(data_proto: Message) -> Comment:
        contents = Contents.from_tbdata(data_proto)

        reply_to_id = 0
        if contents:
            first_frag = contents[0]
            if (
                isinstance(first_frag, FragText)
                and first_frag.text == "回复 "
                and (reply_to_id := data_proto.content[1].uid)
            ):
                reply_to_id = reply_to_id
                if isinstance(contents[1], FragAt):
                    del contents.ats[0]
                contents.objs = contents.objs[2:]
                contents.texts = contents.texts[2:]
                if contents.texts:
                    first_text_frag = contents.texts[0]
                    first_text_frag.text = first_text_frag.text.removeprefix(" :")

        contents = contents

        pid = data_proto.id
        author_id = data_proto.author_id
        agree = data_proto.agree.agree_num
        disagree = data_proto.agree.disagree_num
        create_time = data_proto.time

        return Comment(
            contents,
            0,
            "",
            0,
            0,
            pid,
            None,
            author_id,
            reply_to_id,
            0,
            agree,
            disagree,
            create_time,
            False,
        )

    def __eq__(self, obj: Comment) -> bool:
        return self.pid == obj.pid

    def __hash__(self) -> int:
        return self.pid

    @property
    def text(self) -> str:
        return self.contents.text


@dcs.dataclass
class Post:
    """
    楼层信息

    Attributes:
        text (str): 文本内容
        contents (Contents_p): 正文内容碎片列表
        sign (str): 小尾巴文本内容
        comments (list[Comment_p]): 楼中楼列表
        is_aimeme (bool): 是否是AI生成的表情包

        fid (int): 所在吧id
        fname (str): 所在贴吧名
        tid (int): 所在主题帖id
        pid (int): 回复id
        user (UserInfo_p): 发布者的用户信息
        author_id (int): 发布者的user_id

        floor (int): 楼层数
        reply_num (int): 楼中楼数
        agree (int): 点赞数
        disagree (int): 点踩数
        create_time (int): 创建时间
        is_thread_author (bool): 是否楼主
    """

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
    def from_tbdata(data_proto: Message) -> Post:
        contents = Contents.from_tbdata(data_proto)
        sign = "".join(p.text for p in data_proto.signature.content if p.type == 0)
        comments = [
            Comment.from_tbdata(p) for p in data_proto.sub_post_list.sub_post_list
        ]
        is_aimeme = bool(data_proto.sprite_meme_info.meme_id)
        pid = data_proto.id
        author_id = data_proto.author_id
        floor = data_proto.floor
        reply_num = data_proto.sub_post_number
        agree = data_proto.agree.agree_num
        disagree = data_proto.agree.disagree_num
        create_time = data_proto.time
        return Post(
            contents,
            sign,
            comments,
            is_aimeme,
            0,
            "",
            0,
            pid,
            None,
            author_id,
            floor,
            reply_num,
            agree,
            disagree,
            create_time,
            False,
        )

    def __eq__(self, obj: Post) -> bool:
        return self.pid == obj.pid

    def __hash__(self) -> int:
        return self.pid

    @cached_property
    def text(self) -> str:
        return f"{self.contents.text}\n{self.sign}" if self.sign else self.contents.text


@dcs.dataclass
class Page:
    """
    页信息

    Attributes:
        page_size (int): 页大小
        current_page (int): 当前页码
        total_page (int): 总页码
        total_count (int): 总计数

        has_more (bool): 是否有后继页
        has_prev (bool): 是否有前驱页
    """

    page_size: int = 0
    current_page: int = 0
    total_page: int = 0
    total_count: int = 0

    has_more: bool = False
    has_prev: bool = False

    @staticmethod
    def from_tbdata(data_proto: Message) -> Page:
        page_size = data_proto.page_size
        current_page = data_proto.current_page
        total_page = data_proto.total_page
        total_count = data_proto.total_count
        has_more = bool(data_proto.has_more)
        has_prev = bool(data_proto.has_prev)
        return Page(
            page_size, current_page, total_page, total_count, has_more, has_prev
        )


@dcs.dataclass
class Forum:
    """
    吧信息

    Attributes:
        fid (int): 贴吧id
        fname (str): 贴吧名

        category (str): 一级分类
        subcategory (str): 二级分类

        member_num (int): 吧会员数
        post_num (int): 发帖量
    """

    fid: int = 0
    fname: str = ""

    category: str = ""
    subcategory: str = ""

    member_num: int = 0
    post_num: int = 0

    @staticmethod
    def from_tbdata(data_proto: Message) -> Forum:
        fid = data_proto.id
        fname = data_proto.name
        category = data_proto.first_class
        subcategory = data_proto.second_class
        member_num = data_proto.member_num
        post_num = data_proto.post_num
        return Forum(fid, fname, category, subcategory, member_num, post_num)


@dcs.dataclass
class ShareThread:
    """
    被分享的主题帖信息

    Attributes:
        text (str): 文本内容
        contents (Contents_pt): 正文内容碎片列表
        title (str): 标题内容

        fid (int): 所在吧id
        fname (str): 所在贴吧名
        tid (int): 主题帖tid
        author_id (int): 发布者的user_id

        vote_info (VoteInfo): 投票内容
    """

    contents: Contents = dcs.field(default_factory=Contents)
    title: str = ""

    fid: int = 0
    fname: str = ""
    tid: int = 0
    author_id: int = 0

    vote_info: VoteInfo = dcs.field(default_factory=VoteInfo)

    @staticmethod
    def from_tbdata(data_proto: Message) -> ShareThread:
        contents = Contents.from_tbdata(data_proto)
        title = data_proto.title
        fid = data_proto.fid
        fname = data_proto.fname
        tid = int(tid) if (tid := data_proto.tid) else 0
        author_id = data_proto.content[0].uid if data_proto.content else 0
        vote_info = VoteInfo.from_tbdata(data_proto.poll_info)
        return ShareThread(contents, title, fid, fname, tid, author_id, vote_info)

    def __eq__(self, obj: ShareThread) -> bool:
        return self.pid == obj.pid

    def __hash__(self) -> int:
        return self.pid

    @cached_property
    def text(self) -> str:
        return (
            f"{self.title}\n{self.contents.text}" if self.title else self.contents.text
        )


@dcs.dataclass
class Thread:
    """
    主题帖信息

    Attributes:
        text (str): 文本内容
        contents (Contents_pt): 正文内容碎片列表
        title (str): 标题内容

        fid (int): 所在吧id
        fname (str): 所在贴吧名
        tid (int): 主题帖tid
        pid (int): 首楼回复pid
        user (UserInfo_pt): 发布者的用户信息
        author_id (int): 发布者的user_id

        type (int): 帖子类型
        is_share (bool): 是否分享帖
        is_help (bool): 是否为求助帖

        vote_info (VoteInfo): 投票信息
        share_origin (ShareThread_pt): 转发来的原帖内容
        view_num (int): 浏览量
        reply_num (int): 回复数
        share_num (int): 分享数
        agree (int): 点赞数
        disagree (int): 点踩数
        create_time (int): 创建时间 10位时间戳 以秒为单位
    """

    contents: Contents = dcs.field(default_factory=Contents)
    title: str = ""

    fid: int = 0
    fname: str = ""
    tid: int = 0
    pid: int = 0
    user: UserInfo = dcs.field(default_factory=UserInfo)

    type: int = 0
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
    def from_tbdata(data_proto: Message) -> Thread:
        thread_proto = data_proto.thread
        title = thread_proto.title
        tid = thread_proto.id
        pid = thread_proto.post_id
        user = UserInfo.from_tbdata(thread_proto.author)
        type_ = thread_proto.thread_type
        is_share = bool(thread_proto.is_share_thread)
        view_num = data_proto.thread_freq_num
        reply_num = thread_proto.reply_num
        share_num = thread_proto.share_num
        agree = thread_proto.agree.agree_num
        disagree = thread_proto.agree.disagree_num
        create_time = thread_proto.create_time

        if not is_share:
            real_thread_proto = thread_proto.origin_thread_info
            contents = Contents.from_tbdata(real_thread_proto)
            vote_info = VoteInfo.from_tbdata(real_thread_proto.poll_info)
            share_origin = ShareThread()
        else:
            contents = Contents()
            vote_info = VoteInfo()
            share_origin = ShareThread.from_tbdata(thread_proto.origin_thread_info)

        return Thread(
            contents,
            title,
            0,
            "",
            tid,
            pid,
            user,
            type_,
            is_share,
            vote_info,
            share_origin,
            view_num,
            reply_num,
            share_num,
            agree,
            disagree,
            create_time,
        )

    def __eq__(self, obj: Thread) -> bool:
        return self.pid == obj.pid

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

    @property
    def is_help(self) -> bool:
        return self.type == 71


@dcs.dataclass
class Posts(Containers[Post]):
    """
    回复列表

    Attributes:
        objs (list[Post]): 回复列表
        err (Exception | None): 捕获的异常

        page (Page_p): 页信息
        has_more (bool): 是否还有下一页

        forum (Forum_p): 所在吧信息
        thread (Thread_p): 所在主题帖信息
    """

    err: Exception | None = dcs.field(default=None, init=False, repr=False)
    page: Page = dcs.field(default_factory=Page)
    forum: Forum = dcs.field(default_factory=Forum)
    thread: Thread = dcs.field(default_factory=Thread)

    @staticmethod
    def from_tbdata(data_proto: Message) -> Posts:
        page = Page.from_tbdata(data_proto.page)
        forum = Forum.from_tbdata(data_proto.forum)
        thread = Thread.from_tbdata(data_proto)

        thread.fid = forum.fid
        thread.fname = forum.fname

        objs = [
            Post.from_tbdata(p)
            for p in data_proto.post_list
            if not p.chat_content.bot_uk
        ]
        users = {p.id: UserInfo.from_tbdata(p) for p in data_proto.user_list}
        for post in objs:
            post.fid = forum.fid
            post.fname = forum.fname
            post.tid = thread.tid
            post.user = users[post.author_id]
            post.is_thread_author = thread.author_id == post.author_id
            for comment in post.comments:
                comment.fid = post.fid
                comment.fname = post.fname
                comment.tid = post.tid
                comment.ppid = post.pid
                comment.floor = post.floor
                comment.user = users[comment.author_id]
                comment.is_thread_author = thread.author_id == comment.author_id

        return Posts(objs, page, forum, thread)

    @property
    def has_more(self) -> bool:
        return self.page.has_more
