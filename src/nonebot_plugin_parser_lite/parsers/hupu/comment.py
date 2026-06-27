from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Comment
from ...utils.format import format_num
from .util import parse_rich_content


class Quote(Struct):
    pid: str


class CheckReplyInfo(Struct):
    num: int


class HComment(Struct):
    pid: str
    puid: str
    html: str = field(name="content")
    create_time: str
    """unix"""
    light_count: int
    userName: str
    userImg: str
    location: str
    check_reply_info: CheckReplyInfo | None
    quote: list[Quote]

    @property
    def content(self):
        return parse_rich_content(self.html)


class Result(Struct):
    clist: list[HComment] = field(name="list")


class Data(Struct):
    result: Result
    status: int
    """200"""


class Response(Struct):
    data: Data
    status: int
    """0"""

    @property
    def comments(self) -> list[Comment]:

        pid_to_node: dict[str, Comment] = {}

        for c in self.data.result.clist:
            node = Creator.comment(
                author=Creator.author(
                    name=c.userName,
                    avatar_url=c.userImg,
                    id=c.puid,
                    location=c.location,
                ),
                content=c.content,
                stats=Creator.stats(
                    like_count=format_num(c.light_count),
                    comment_count=format_num(
                        c.check_reply_info.num if c.check_reply_info else 0
                    ),
                ),
                timestamp=int(c.create_time),
            )

            if quote_info := c.quote:
                if parent := pid_to_node.get(quote_info[0].pid):
                    parent.add_reply(node)
                    continue
            pid_to_node[c.pid] = node
        return list(pid_to_node.values())


decoder = Decoder(Response)
