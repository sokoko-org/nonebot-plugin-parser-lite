from __future__ import annotations

from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Comment, ContentItem
from ...utils.format import format_num


class UserDTO(Struct):
    avatar: str
    userId: int
    userName: str


class CommentDTO(Struct):
    likeCount: int
    text: str = field(name="content")
    createTime: int
    """ms"""
    updateTime: int
    replyCount: int = 0
    userRegion: str = ""
    userDTO: UserDTO | None = None
    fromUserDTO: UserDTO | None = None
    replyComments: list[CommentDTO] | None = None
    image: str | None = None

    @property
    def content(self) -> list[ContentItem]:
        return [
            self.text,
            *(
                [
                    Creator.image(
                        url=self.image,
                        ext_headers={"Referer": "https://news.wmpvp.com"},
                    )
                ]
                if self.image
                else []
            ),
        ]

    @property
    def author(self) -> UserDTO:
        return self.userDTO or self.fromUserDTO  # pyright: ignore[reportReturnType]


class CommentResponse(Struct):
    itemCount: int
    commentDTOS: list[CommentDTO]


class Result(Struct):
    commentResponse: CommentResponse


class Response(Struct):
    result: Result

    @property
    def comments(self) -> list[Comment]:
        if not self.result.commentResponse.commentDTOS:
            return []

        def to_author(cd: CommentDTO):
            return Creator.author(
                name=cd.author.userName,
                avatar_url=cd.author.avatar,
                location=cd.userRegion,
                ext_headers={"Referer": "https://news.wmpvp.com"},
            )

        def to_comment(cd: CommentDTO):
            return Creator.comment(
                author=to_author(cd),
                content=cd.content,
                timestamp=cd.createTime // 1000,
                stats=Creator.stats(
                    like_count=format_num(cd.likeCount),
                    comment_count=format_num(cd.replyCount),
                ),
            )

        result: list[Comment] = []
        for c in self.result.commentResponse.commentDTOS:
            root = to_comment(c)
            if children := c.replyComments:
                for sc in children:
                    root.add_reply(to_comment(sc))
            result.append(root)
        return result


decoder = Decoder(Response)
