from typing import ClassVar

from msgspec import convert

from ...utils.format import format_num
from ..base import (
    BaseParser,
    Comment,
    ContentItem,
    MatchWithParams,
    Platform,
    PlatformEnum,
    handle,
)
from .model import AtlasData, BlogData, CommentData


class DuiTangParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.DUITANG, display_name="堆糖"
    )

    @handle("duitang.com/blog", params={"id": {"as_int": True}})
    async def parse_blog(self, searched: MatchWithParams):
        blog_id = searched["id"]

        blog_data = await self._fetch_blog_detail(blog_id=blog_id)
        comment_data = await self._fetch_comments(
            subject_id=blog_data.id,
            subject_type=0,
        )

        content: list[ContentItem] = [
            blog_data.msg,
            self.create_image(blog_data.photo.path),
        ]
        comments = self._build_comments(comment_data)

        return self.result(
            content=content,
            stats=self.create_stats(
                like_count=format_num(blog_data.like_count),
                collect_count=format_num(blog_data.favorite_count),
                comment_count=format_num(blog_data.reply_count),
            ),
            author=self.create_author(
                name=blog_data.sender.username,
                avatar_url=blog_data.sender.avatar,
            ),
            timestamp=blog_data.add_datetime_ts,
            comments=comments,
            url=f"https://m.duitang.com/blog?id={blog_id}",
        )

    @handle("duitang.com/atlas", params={"id": {"as_int": True}})
    async def parse_atlas(self, searched: MatchWithParams):
        atlas_id = searched["id"]

        atlas_data = await self._fetch_atlas_detail(atlas_id=atlas_id)
        comment_data = await self._fetch_comments(
            subject_id=atlas_data.id,
            subject_type=23,
        )

        content: list[ContentItem] = [
            atlas_data.desc,
            *self.create_images(atlas_data.img_list),
        ]
        comments = self._build_comments(comment_data)

        return self.result(
            content=content,
            stats=self.create_stats(
                view_count=format_num(atlas_data.visit_count),
                like_count=format_num(atlas_data.like_count),
                collect_count=format_num(atlas_data.favorite_count),
                comment_count=format_num(atlas_data.comment_count),
            ),
            author=self.create_author(
                name=atlas_data.sender.username,
                avatar_url=atlas_data.sender.avatar,
            ),
            timestamp=atlas_data.created_at // 1000,
            comments=comments,
            url=f"https://www.duitang.com/atlas?id={atlas_id}",
        )

    async def _fetch_atlas_detail(
        self,
        atlas_id: str,
    ) -> AtlasData:
        """
        调用堆糖接口获取图集详情数据，并将结果转换为 AtlasData 对象

        :param atlas_id: 图集 ID。
        :return: 转换后的图集详情数据。
        :raise ValueError: 当接口返回 message 不为 "success" 时抛出。
        """
        response = await self.httpx.get(
            "https://www.duitang.com/napi/vienna/atlas/detail/",
            params={"atlas_id": atlas_id},
        )
        response.raise_for_status()
        res = response.json()
        if res.get("status") != 1:
            raise ValueError(f"Unknown error: {res}")
        return convert(res["data"], AtlasData)

    async def _fetch_blog_detail(
        self,
        blog_id: str,
    ) -> BlogData:
        """
        调用堆糖接口获取博客图集详情数据，并将结果转换为 BlogData 对象

        :param blog_id: 图集 ID。
        :return: 转换后的博客图集详情数据。
        :raise ValueError: 当接口返回 message 不为 "success" 时抛出。
        """
        response = await self.httpx.get(
            "https://www.duitang.com/napi/blog/with_instance_tag/detail/",
            params={
                "blog_id": blog_id,
                "include_fields": (
                    "tags,related_albums,related_albums.covers,"
                    "root_album,share_links_2,extra_links,icon_description,root_id"
                ),
            },
        )
        response.raise_for_status()
        res = response.json()
        if res.get("status") != 1:
            raise ValueError(f"Unknown error: {res}")
        return convert(res["data"], BlogData)

    async def _fetch_comments(
        self,
        subject_id: int,
        subject_type: int,
        limit: int = 5,
    ) -> CommentData:
        """
        调用堆糖接口获取图集评论数据。该方法支持限制返回条数，用于构建评论列表。

        :param subject_id: 图集 ID，作为评论主体 ID。
        :param subject_type: 图集类型，作为评论主体类型。
        :param limit: 拉取的评论条数上限。
        :return: 转换后的评论数据对象。
        :raise ValueError: 当接口返回 message 不为 "success" 时抛出。
        """
        response = await self.httpx.get(
            "https://www.duitang.com/napi/vienna/comment/list/",
            params={
                "start": 0,
                "limit": limit,
                "more": 1,
                "subject_type": subject_type,
                "subject_id": subject_id,
            },
        )
        response.raise_for_status()
        res = response.json()
        if res.get("status") != 1:
            raise ValueError(f"Unknown error: {res}")
        return convert(res["data"], CommentData)

    def _build_comments(self, comment_data: CommentData) -> list[Comment]:
        """
        根据堆糖评论数据构建评论及其子回复。该方法会处理评论的文字、图片和基础统计信息。

        :param comment_data: 已转换的评论数据对象。
        :return: Comment 实例列表。
        """
        comments: list[Comment] = []

        for root_comment in comment_data.object_list:
            root_content: list[ContentItem] = [
                root_comment.content,
                *self.create_images(root_comment.img_list),
            ]

            comment = self.create_comment(
                author=self.create_author(
                    name=root_comment.sender.username,
                    avatar_url=root_comment.sender.avatar,
                    id=str(root_comment.sender.id),
                    location=root_comment.ipaddr,
                ),
                content=root_content,
                timestamp=root_comment.create_time // 1000,
                stats=self.create_stats(
                    like_count=format_num(root_comment.like_count),
                    comment_count=format_num(root_comment.reply_count),
                ),
            )

            for sub_comment in root_comment.replies:
                comment.replies.append(
                    self.create_comment(
                        author=self.create_author(
                            name=sub_comment.sender.username,
                            avatar_url=sub_comment.sender.avatar,
                            location=sub_comment.ipaddr,
                        ),
                        content=[sub_comment.content],
                        timestamp=sub_comment.add_datetime_ts // 1000,
                    )
                )

            comments.append(comment)

        return comments
