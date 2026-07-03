from __future__ import annotations

from itertools import chain

from msgspec import Struct
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Comment, ContentItem
from ...utils.format import format_num
from .share import Author, Photo
from .util import parse_date


class DComment(Struct):
    id: str
    text: str
    ip_location: str
    photos: list[Photo]
    author: Author
    create_time: str
    vote_count: int
    ref_comment: DComment | None = None

    @property
    def content(self) -> list[ContentItem]:
        content: list[ContentItem] = [self.text]
        content.extend(
            Creator.image(
                url=photo.image.large.url,
                ext_headers={"Referer": "https://douban.com/"},
                use_curl_cffi=True,
            )
            for photo in self.photos
        )
        return content

    @property
    def timestamp(self):
        return parse_date(self.create_time)


class Response(Struct):
    comments: list[DComment]
    popular_comments: list[DComment]
    total: int

    @property
    def comment_list(self) -> list[Comment]:
        id_to_node: dict[str, Comment] = {}

        for c in chain(self.popular_comments, self.comments):
            node = id_to_node.get(c.id)
            if node is None:
                node = Creator.comment(
                    author=Creator.author(
                        name=c.author.name,
                        avatar_url=c.author.avatar,
                        id=c.author.uid,
                        location=c.ip_location,
                        ext_headers={"Referer": "https://douban.com/"},
                        use_curl_cffi=True,
                    ),
                    content=c.content,
                    stats=Creator.stats(like_count=format_num(c.vote_count)),
                    timestamp=c.timestamp,
                )

                if c.ref_comment is None:
                    id_to_node[c.id] = node

            if quote_info := c.ref_comment:
                if parent := id_to_node.get(quote_info.id):
                    parent.add_reply(node)

        return list(id_to_node.values())


decoder = Decoder(Response)
