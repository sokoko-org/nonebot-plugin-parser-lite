from __future__ import annotations

from itertools import chain

from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import Creator
from ...data import Author, Comment, ContentItem
from ...utils.format import format_num
from .feed import DisplayIpInfo, UserInfo


class CommentRich(Struct):
    url: str
    name: str = ""


class CommentRecord(Struct):
    likeCount: int = 0
    commentCount: int = 0


class FeedComment(Struct):
    id: str
    uid: str
    createTime: int
    text: str = field(name="content", default="")
    record: CommentRecord = field(default_factory=CommentRecord)
    displayIpInfo: DisplayIpInfo | None = None
    commentRich: CommentRich | None = None
    replyId: str | None = None
    replyUid: str | None = None
    parent: str | None = None

    @property
    def content(self) -> list[ContentItem]:
        text = self.text
        result: list[ContentItem] = []

        if rich := self.commentRich:
            if rich.name:
                text = text.replace(f"[{rich.name}]", "", 1).strip()
            if text:
                result.append(text)
            result.append(Creator.image(url=rich.url))
        elif text:
            result.append(text)

        return result

    @property
    def timestamp(self) -> int:
        return self.createTime // 1000

    @property
    def root_id(self) -> str | None:
        """parent 格式为 feedId.feedAuthorId.commentId"""
        return self.parent.rsplit(".", 1)[-1] if self.parent else None


FeaturedReply = FeedComment


class Result(Struct):
    feedComments: list[FeedComment] = field(default_factory=list)
    featuredReplies: list[FeaturedReply] = field(default_factory=list)
    userInfos: list[UserInfo] = field(default_factory=list)

    @property
    def user_info_by_uid(self) -> dict[str, UserInfo]:
        return {info.user.uid: info for info in self.userInfos}

    def _author(
        self,
        comment: FeedComment,
        user_info_by_uid: dict[str, UserInfo],
    ) -> Author:
        info = user_info_by_uid.get(comment.uid)
        location = (
            comment.displayIpInfo.ipLocationName
            if comment.displayIpInfo is not None
            else None
        )
        if info is None:
            return Creator.author(name=comment.uid, id=comment.uid, location=location)

        user = info.user
        return Creator.author(
            id=user.uid,
            name=user.nick,
            avatar_url=user.icon,
            description=user.intro or None,
            location=location,
        )

    def _to_comment(
        self,
        comment: FeedComment,
        user_info_by_uid: dict[str, UserInfo],
    ) -> Comment:
        return Creator.comment(
            author=self._author(comment, user_info_by_uid),
            content=comment.content,
            timestamp=comment.timestamp,
            stats=Creator.stats(
                like_count=format_num(comment.record.likeCount),
                comment_count=format_num(comment.record.commentCount),
            ),
        )

    def _build_nodes(
        self,
        raw_comments: list[FeedComment],
    ) -> tuple[dict[str, Comment], dict[str, Author]]:
        """创建评论节点及作者索引"""
        user_info_by_uid = self.user_info_by_uid
        nodes: dict[str, Comment] = {}
        author_by_uid: dict[str, Author] = {}

        for raw in raw_comments:
            if raw.id not in nodes:
                node = self._to_comment(raw, user_info_by_uid)
                nodes[raw.id] = node
                author_by_uid.setdefault(raw.uid, node.author)

        return nodes, author_by_uid

    def _attach_replies(
        self,
        nodes: dict[str, Comment],
        author_by_uid: dict[str, Author],
    ) -> None:
        """将回复压平挂到根评论"""
        attached: set[str] = set()
        for raw in self.featuredReplies:
            root = nodes.get(raw.root_id or "")
            node = nodes.get(raw.id)
            if root is None or node is None or root is node or raw.id in attached:
                continue

            replied_to = nodes.get(raw.replyId or "")
            parent_author = replied_to.author if replied_to is not None else None
            if parent_author is None and raw.replyUid:
                parent_author = author_by_uid.get(raw.replyUid)
            root.add_reply(node, parent_author)
            attached.add(raw.id)

    def _root_comments(self, nodes: dict[str, Comment]) -> list[Comment]:
        return list({raw.id: nodes[raw.id] for raw in self.feedComments}.values())

    @property
    def comment_list(self) -> list[Comment]:
        raw_comments = list(chain(self.feedComments, self.featuredReplies))
        nodes, author_by_uid = self._build_nodes(raw_comments)
        self._attach_replies(nodes, author_by_uid)
        return self._root_comments(nodes)


decoder = Decoder(Result)
