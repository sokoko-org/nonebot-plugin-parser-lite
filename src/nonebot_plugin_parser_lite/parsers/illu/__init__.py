from typing import ClassVar, Literal, overload

from msgspec import ValidationError

from ...utils.format import format_num
from ..base import (
    BaseParser,
    Comment,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .articleByIdV2 import ArticleByIdV2
from .articleByIdV2 import decoder as article_decoder
from .commentList import Comment as IlluComment
from .commentList import decoder as comment_decoder
from .drawingDetail import DrawingDetail
from .drawingDetail import decoder as drawing_decoder
from .encrypt import sign_header
from .models import BizType, Detail, OrderType


class IlluParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.ILLU, display_name="ILLU")

    def __init__(self):
        super().__init__()
        self.httpx.base_url = "https://api.illund.com"

    # 文章
    # https://illund.com/share.html?al=mindlib%3A%2F%2Freactbox%2F%3FarticleId%3Dfcfb0ffe76%26hideTitleBar%3D1%26pagename%3DArticleDetailVC&st=%E3%80%90%E6%96%87%E7%AB%A0%E5%88%86%E4%BA%AB%E3%80%91%E3%80%90%E6%98%9F%E6%B5%B7%E6%8B%BE%E9%81%97%E3%80%919.2%E5%BF%83%E8%A1%80%E6%9D%A5%E6%BD%AE
    @handle("illund.com/share.html", r"articleId%3D(?P<articleId>[0-9a-z]+)")
    async def parse_article(self, searched: MatchWithParams):
        object_id = searched["articleId"]
        detail = (
            await self._fetch_detail(
                object_id,
                BizType.Article,
            )
        ).dataObject
        return self.result(
            content=await detail.get_content(),
            timestamp=detail.publishDate.timestamp,
            url=f"https://illund.com/share.html?al=mindlib%3A%2F%2Freactbox%2F%3FarticleId%3D{object_id}%26hideTitleBar%3D1%26pagename%3DArticleDetailVC",
            author=self.create_author(
                name=detail.author.nickname,
                avatar_url=detail.author.headerImage.url,
                id=detail.author.objectId,
            ),
            title=detail.title,
            stats=self.create_stats(
                view_count=format_num(detail.readCount),
                like_count=format_num(detail.thumbUpCount),
                comment_count=format_num(detail.commentCount),
                extra={
                    "rewardCoin": format_num(detail.rewardCoin),
                },
            ),
            comments=await self._build_comments(object_id, BizType.Article),
        )

    # 图集
    # https://illund.com/share.html?al=mindlib%3A%2F%2Freactbox%2F%3Fmainid%3Dfcecc2da36%26hideTitleBar%3D1%26pagename%3DDrawingDetailVC&st=%E3%80%90%E5%9B%BE%E7%89%87%E5%88%86%E4%BA%AB%E3%80%91%E6%9D%8E%E7%AE%B1%E6%B0%B4%E4%BB%99
    @handle("illund.com/share.html", r"mainid%3D(?P<mainId>[0-9a-z]+)")
    async def parse_drawing(self, searched: MatchWithParams):
        object_id = searched["mainId"]
        detail = await self._fetch_detail(object_id, BizType.Drawing)
        return self.result(
            content=detail.medias,
            timestamp=detail.publishDate.timestamp,
            url=f"https://illund.com/share.html?al=mindlib%3A%2F%2Freactbox%2F%3Fmainid%3D{object_id}%26hideTitleBar%3D1%26pagename%3DDrawingDetailVC",
            author=self.create_author(
                name=detail.author.nickname,
                avatar_url=detail.author.headerImage.url,
                id=detail.author.objectId,
            ),
            title=detail.title,
            stats=self.create_stats(
                view_count=format_num(detail.readCount),
                like_count=format_num(detail.likeCount),
                collect_count=format_num(detail.collectCount),
                comment_count=format_num(detail.commentCount),
                extra={
                    "rewardCoin": format_num(detail.rewardCoin),
                },
            ),
            comments=await self._build_comments(object_id, BizType.Drawing),
        )

    @overload
    async def _fetch_detail(
        self, objectId: str, type: Literal[BizType.Article]
    ) -> ArticleByIdV2: ...

    @overload
    async def _fetch_detail(
        self, objectId: str, type: Literal[BizType.Drawing]
    ) -> DrawingDetail: ...

    async def _fetch_detail(
        self,
        objectId: str,
        type: BizType,
    ) -> ArticleByIdV2 | DrawingDetail:
        """根据 objectId 和类型拉取 ILLU 详情数据。"""
        if type is BizType.Article:
            router = Detail.ArticleDetail.value
            payload = {"articleId": objectId}
            decoder = article_decoder
        elif type is BizType.Drawing:
            router = Detail.DrawingDetail.value
            payload = {"mainId": objectId}
            decoder = drawing_decoder
        else:
            raise ValueError(f"unsupported BizType: {type!r}")
        resp = await self.httpx.post(
            router,
            json=payload,
            headers=sign_header(router),
        )
        resp.raise_for_status()
        data = resp.json()["result"]
        try:
            return decoder.decode(data)
        except ValidationError as e:
            raise ParseException(data) from e

    async def _build_comments(
        self,
        objectId: str,
        type: BizType,
    ) -> list[Comment]:
        """
        根据 objectId 与类型拉取评论列表。

        :param objectId: 文章或绘图的 objectId
        :param type: BizType.Article 或 BizType.Drawing
        :return: Comment 实例列表。
        """
        router = Detail.CommentList.value
        resp = await self.httpx.post(
            router,
            json={
                "mainId": objectId,
                "page": 1,
                "orderType": OrderType.Popular,
                "bizType": type.value,
            },
            headers=sign_header(router),
        )
        resp.raise_for_status()
        data = resp.json()["result"]
        comment_data = comment_decoder.decode(data)

        def _make_comment(node: IlluComment) -> Comment:
            """从 commentList 的节点构造 Comment"""
            author = self.create_author(
                name=node.author.nickname,
                avatar_url=node.author.headerImage.url,
                id=node.author.objectId,
            )
            stats = self.create_stats(
                like_count=format_num(node.likeCount),
                comment_count=format_num(node.subCommentCount),
            )
            return self.create_comment(
                author=author,
                content=[node.content],
                timestamp=node.timestamp,
                stats=stats,
            )

        comments: list[Comment] = []

        for root in comment_data.results:
            root_comment = _make_comment(root)

            for sub in root.subCommentList:
                root_comment.replies.append(_make_comment(sub))

            comments.append(root_comment)

        return comments
