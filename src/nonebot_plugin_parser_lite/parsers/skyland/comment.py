from msgspec import Struct, field
from msgspec.json import Decoder

from ...creator import ContentItem, Creator
from ...data import Author, Comment, Stats
from ...utils.format import format_num
from .sticker import replace_emoji, sticker_content
from .util import merge_text


class Slice(Struct):
    """内容切片，`c` 为内容，`u` 为 @ 对象的 uid"""

    id: str = ""
    c: str = ""
    u: str = ""
    url: str = ""


class CommentImage(Struct):
    """评论配图"""

    id: str = ""
    url: str = ""


class FormatContent(Struct):
    """段落内的元素"""

    type: str = ""
    contentId: str = ""
    linkId: str = ""
    id: str = ""


class FormatBlock(Struct):
    """排版区块"""

    type: str = ""
    contents: list[FormatContent] = field(default_factory=list)


class CommentFormat(Struct):
    """`format` 字段反序列化后的结构"""

    data: list[FormatBlock] = field(default_factory=list)
    version: int = 0


format_decoder = Decoder(CommentFormat)


class CaptionItem(Struct):
    """`caption` 扁平预览项"""

    type: str = ""
    id: str = ""


class CommentBody(Struct):
    """评论主体"""

    id: str = ""
    userId: str = ""
    level: int = 1
    """1级评论"""
    itemId: str = ""
    parentId: str = ""
    parentUserId: str = ""
    format: str = ""
    textSlice: list[Slice] = field(default_factory=list)
    linkSlice: list[Slice] = field(default_factory=list)
    atSlice: list[Slice] = field(default_factory=list)
    imageListSlice: list[CommentImage] = field(default_factory=list)
    createdAtTs: int = 0
    firstIpLocation: str = ""
    caption: list[CaptionItem] = field(default_factory=list)

    def _slice_map(self, slices: list[Slice]) -> dict[str, Slice]:
        """切片表按 id 建索引"""
        return {item.id: item for item in slices}

    def _text(self, content_id: str) -> list[ContentItem]:
        """取文本切片，并把内嵌的小表情替换为贴纸"""
        if item := self._slice_map(self.textSlice).get(content_id):
            return replace_emoji(item.c)
        return []

    def _at(self, content_id: str) -> list[ContentItem]:
        """取 @ 切片"""
        if item := self._slice_map(self.atSlice).get(content_id):
            return [f"@{item.c}"] if item.c else []
        return []

    def _link(self, content_id: str, link_id: str) -> list[ContentItem]:
        """取链接切片，文字与地址分别来自 textSlice 与 linkSlice"""
        link_item = self._slice_map(self.linkSlice).get(link_id)
        text_item = self._slice_map(self.textSlice).get(content_id)
        url = (link_item.c or link_item.url) if link_item else ""
        text = text_item.c if text_item else ""
        if not url:
            return replace_emoji(text) if text else []
        return [f"{text} {url}"] if text and text.strip() != url else [url]

    @property
    def _format_content(self) -> list[ContentItem]:
        """按 `format` 渲染正文"""
        if not self.format:
            return []
        try:
            parsed = format_decoder.decode(self.format.encode("utf-8"))
        except Exception:
            return []

        content: list[ContentItem] = []
        for index, block in enumerate(parsed.data):
            if index:
                # 每个段落之间补换行
                content.append("\n")
            if block.type and block.type != "paragraph":
                # image / video / b_video / dividing_line 等区块
                # 图片统一由 imageListSlice 附加，这里不重复处理
                continue
            for element in block.contents:
                match element.type:
                    case "text":
                        content.extend(self._text(element.contentId))
                    case "link":
                        content.extend(self._link(element.contentId, element.linkId))
                    case "at" | "mention":
                        content.extend(self._at(element.contentId))
                    case "emoji" | "sticker":
                        if element.id:
                            content.append(sticker_content(element.id))
                    case _:
                        pass
        return content

    @property
    def _caption_content(self) -> list[ContentItem]:
        """`format` 不可用时按 `caption` 渲染"""
        content: list[ContentItem] = []
        for item in self.caption:
            match item.type:
                case "text":
                    content.extend(self._text(item.id))
                case "newline":
                    content.append("\n")
                case "at" | "mention":
                    content.extend(self._at(item.id))
                case "emoji" | "sticker":
                    if item.id:
                        content.append(sticker_content(item.id))
                case _:
                    pass
        return content

    @property
    def content(self) -> list[ContentItem]:
        """评论完整内容：正文 + 配图"""
        content = self._format_content or self._caption_content
        for image in self.imageListSlice:
            if image.url:
                content.append(
                    Creator.image(
                        url=image.url,
                        cache_key=f"skyland:image:{image.id}",
                    )
                )
        return merge_text(content)


class CommentUser(Struct):
    """评论作者"""

    id: str = ""
    nickname: str = ""
    profile: str = ""
    avatar: str = ""
    latestIpLocation: str = ""

    @property
    def author(self) -> Author:
        """构造作者对象"""
        return Creator.author(
            name=self.nickname or "森空岛用户",
            avatar_url=self.avatar or None,
            id=self.id or None,
            location=self.latestIpLocation or None,
            avatar_cache_key=f"skyland:{self.id}" if self.id else None,
        )


class CommentRts(Struct):
    """评论互动计数"""

    liked: str = "0"
    commented: str = "0"

    @property
    def stats(self) -> Stats:
        """构造统计对象"""

        def to_int(value: str) -> int | None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        return Creator.stats(
            like_count=format_num(to_int(self.liked)),
            comment_count=format_num(to_int(self.commented)),
        )


class Meta(Struct):
    """评论元信息"""

    comment: CommentBody
    user: CommentUser | None = None
    commentRts: CommentRts | None = None

    @property
    def author(self) -> Author:
        """评论作者"""
        return Creator.author(name="森空岛用户") if self.user is None else self.user.author

    @property
    def to_comment(self) -> Comment:
        """构造评论对象"""
        return Creator.comment(
            author=self.author,
            content=self.comment.content,
            timestamp=self.comment.createdAtTs or None,
            stats=self.commentRts.stats if self.commentRts else None,
        )


class Item(Struct):
    """一级评论及其楼中楼"""

    meta: Meta
    subMetas: list[Meta] = field(default_factory=list)

    @property
    def to_comment(self) -> Comment:
        """构造带回复的评论"""
        root = self.meta.to_comment
        root_user = self.meta.user
        # 以 uid 索引已知用户，供“回复 @xxx”定位父级作者
        authors: dict[str, Author] = {}
        if root_user and root_user.id:
            authors[root_user.id] = root.author
        for sub in self.subMetas:
            if sub.user and sub.user.id:
                authors[sub.user.id] = sub.author

        for sub in self.subMetas:
            parent_id = sub.comment.parentUserId
            parent = authors.get(parent_id) if parent_id else None
            root.add_reply(sub.to_comment, parent=parent)
        return root


class Data(Struct):
    """评论列表数据"""

    comment_list: list[Item] = field(name="list", default_factory=list)

    @property
    def comments(self) -> list[Comment]:
        """构造评论列表"""
        return [item.to_comment for item in self.comment_list]


class Response(Struct):

    code: int = 0
    message: str = ""
    data: Data | None = None

    @property
    def comments(self) -> list[Comment]:
        """构造评论列表"""
        return self.data.comments if self.data else []


decoder = Decoder(Response)
