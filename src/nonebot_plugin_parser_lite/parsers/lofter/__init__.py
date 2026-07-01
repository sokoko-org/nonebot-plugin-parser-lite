from typing import ClassVar

from msgspec import convert
from nonebot import logger

from ...utils.format import format_num
from ..base import (
    BaseParser,
    ContentItem,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .comments import CommentList
from .post import Post


class LofterParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.LOFTER, display_name="LOFTER"
    )

    @handle(
        "s.lofter.com",
        r"s\.lofter\.com/-s/[0-9A-Za-z]+",
    )
    async def _parse_short_link(self, searched: MatchWithParams):
        """解析 Lofter 短链"""
        short_url = f"https://{searched[0]}"
        return await self.parse_with_redirect(short_url)

    @handle(
        "lofter.com",
        r"post/(?P<blog_hex>[0-9a-zA-Z]+)_(?P<post_hex>[0-9a-zA-Z]+)",
    )
    async def _parser(self, searched: MatchWithParams):
        blog_id = int(searched["blog_hex"], 16)
        post_id = int(searched["post_hex"], 16)

        # 帖子详情
        post_resp = await self.httpx.post(
            "https://api.lofter.com/oldapi/post/detail.api",
            params={"product": "lofter-android-8.1.20"},
            data={
                "postid": post_id,
                "targetblogid": blog_id,
            },
        )
        post_data = post_resp.json()

        # 评论数据
        com_resp = await self.httpx.get(
            "https://www.lofter.com/comment/l1/hotnew.json",
            params={"postId": post_id, "blogId": blog_id},
        )
        com_data = com_resp.json()

        # 校验帖子状态
        meta = post_data.get("meta") or {}
        if meta.get("status") != 200:
            raise ParseException(f"Lofter 解析失败: {meta.get('msg', '未知错误')}")

        # 解析帖子主体
        post_raw = (post_data.get("response") or {}).get("posts") or []
        if not post_raw:
            raise ParseException("Lofter 解析失败: 未找到帖子内容")
        post = convert(post_raw[0]["post"], Post)

        # 解析评论
        if com_data.get("code") != 0:
            logger.warning(f"Lofter 获取评论失败: {com_data.get('msg')}")
            comment_list = CommentList(hotList=[], default=[])
        else:
            comment_list = convert(com_data.get("data") or {}, CommentList)

        # 构建正文内容：文本 + 媒体
        contents: list[ContentItem] = [post.text]
        contents.extend(post.medias)

        author = post.blogInfo
        stats = post.postCount

        # 构建评论
        comments = [
            self.create_comment(
                author=self.create_author(
                    name=c.publisherBlogInfo.blogNickName,
                    avatar_url=c.publisherBlogInfo.bigAvaImg,
                    id=c.publisherBlogInfo.blogName,
                    location=c.ipLocation,
                ),
                content=c.content,
                timestamp=c.publishTime // 1000,
                stats=self.create_stats(
                    like_count=format_num(c.likeCount),
                    comment_count=format_num(len(c.l2Comments)),
                ),
                replies=[
                    self.create_comment(
                        author=self.create_author(
                            name=s.publisherBlogInfo.blogNickName,
                            avatar_url=s.publisherBlogInfo.bigAvaImg,
                            id=s.publisherBlogInfo.blogName,
                            location=s.ipLocation,
                        ),
                        content=s.content,
                        timestamp=s.publishTime // 1000,
                        stats=self.create_stats(
                            like_count=format_num(s.likeCount),
                        ),
                    )
                    for s in c.l2Comments
                ],
            )
            for c in comment_list.comments
        ]

        return self.result(
            title=post.title,
            content=contents,
            timestamp=post.publishTime // 1000,
            url=f"https://www.lofter.com{searched[0]}",
            author=self.create_author(
                name=author.blogNickName,
                avatar_url=author.bigAvaImg,
                id=author.blogName,
            ),
            comments=comments,
            stats=self.create_stats(
                like_count=format_num(stats.favoriteCount),
                share_count=format_num(stats.shareCount),
                comment_count=format_num(stats.responseCount),
            ),
        )
