from datetime import datetime, timedelta
import re

from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Comment
from .util import parse_rich_content

_HUPU_RELATIVE_RE = re.compile(r"(\d+)(天|小时|分钟|秒)前")


def parse_hupu_date(date_str: str) -> int:
    """将虎扑时间字符串解析为时间戳"""
    date_str = date_str.strip()
    now_dt = datetime.now()
    if date_str == "刚刚":
        return int(now_dt.timestamp())

    if m := _HUPU_RELATIVE_RE.match(date_str):
        value = int(m[1])
        unit = m[2]
        if unit == "天":
            dt = now_dt - timedelta(days=value)
        elif unit == "小时":
            dt = now_dt - timedelta(hours=value)
        elif unit == "分钟":
            dt = now_dt - timedelta(minutes=value)
        else:
            dt = now_dt - timedelta(seconds=value)
        return int(dt.timestamp())

    try:
        year = now_dt.year
        dt = datetime.strptime(f"{year}-{date_str}", "%Y-%m-%d %H:%M")
        return int(dt.timestamp())
    except Exception as e:
        raise ValueError(f"无法解析时间字符串: {date_str!r}") from e


class Forum(Struct):
    fid: str
    f_name: str


class User(Struct):
    puid: str
    username: str
    header: str
    date: str

    @property
    def timestamp(self) -> int:
        return parse_hupu_date(self.date)


class Detail(Struct):
    tid: str
    f_info: Forum
    user: User
    title: str
    html: str = field(name="content")
    hits: str
    replies: str
    lights: str
    via: str
    """发帖签名档信息"""

    @property
    def content(self):
        return parse_rich_content(self.html)

    @property
    def timestamp(self) -> int:
        return self.user.timestamp


class Image(Struct):
    format: str
    src: str


class QuoteInfo(Struct):
    pid: str
    user_ip: str | None = None


class Reply(Struct):
    pid: str
    user: User
    html: str = field(name="content")
    images: list[Image] | None
    light: str | int
    replies: str | int
    via: str
    quote_info: QuoteInfo | None

    @property
    def content(self):
        return [
            *parse_rich_content(self.html),
            *[Creator.image(url=image.src) for image in (self.images or [])],
        ]

    @property
    def timestamp(self) -> int:
        return self.user.timestamp


class Data(Struct):
    t_detail: Detail
    r_list: list[Reply]

    @property
    def comments(self) -> list[Comment]:

        pid_to_node: dict[str, Comment] = {}

        for c in self.r_list:
            node = Creator.comment(
                author=Creator.author(
                    name=c.user.username,
                    avatar_url=c.user.header,
                    id=c.user.puid,
                ),
                content=c.content,
                stats=Creator.stats(
                    like_count=str(c.light), comment_count=str(c.replies)
                ),
                timestamp=c.user.timestamp,
            )

            if quote_info := c.quote_info:
                parent = pid_to_node.get(quote_info.pid)
                if parent is not None:
                    parent.author.location = quote_info.user_ip
                    parent.add_reply(node)
                    continue
            pid_to_node[c.pid] = node
        return list(pid_to_node.values())


class BBS(Struct):
    data: Data


decoder = Decoder(BBS)
