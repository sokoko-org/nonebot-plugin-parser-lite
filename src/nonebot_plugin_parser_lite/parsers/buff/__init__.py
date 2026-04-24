from re import Match
from typing import Any, ClassVar, TypeVar

from httpx import AsyncClient
from msgspec import convert
from nonebot.log import logger

from ...utils.format import format_num
from ..base import BaseParser, Comment, ParseException, Platform, PlatformEnum, handle
from .comments import Comments, Comment as RawComment
from .gallery import Gallery
from .news import News
from .topic import Topic
from .video import Video

T = TypeVar("T")


class BuffParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.BUFF, display_name="BUFF")

    async def _fetch_ok_json(
        self, url: str, params: dict[str, Any], err_msg: str, model: type[T]
    ) -> T:
        async with AsyncClient(headers=self.headers) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        if data.get("code") != "OK":
            raise ParseException(f"{err_msg}: {data}")
        return convert(data["data"], model)

    def _to_comment(self, c: RawComment) -> Comment:
        sub_comments = [
            self.create_comment(
                author=self.create_author(
                    name=sc.author.nickname,
                    avatar_url=sc.author.avatar,
                    id=sc.author.user_id,
                ),
                content=sc.content,
                timestamp=sc.created_at,
                stats=self.create_stats(
                    like_count=format_num(sc.ups_num),
                    comment_count=format_num(len(sc.replies)),
                ),
                location=sc.author.ip_location,
            )
            for sc in c.replies
        ]
        return self.create_comment(
            author=self.create_author(
                name=c.author.nickname,
                avatar_url=c.author.avatar,
                id=c.author.user_id,
            ),
            content=c.content,
            timestamp=c.created_at,
            stats=self.create_stats(
                like_count=format_num(c.ups_num),
                comment_count=format_num(len(c.replies)),
            ),
            replies=sub_comments,
            location=c.author.ip_location,
        )

    async def fetch_comments(self, comment_type: int, type_id: str) -> list[Comment]:
        try:
            async with AsyncClient(headers=self.headers) as client:
                resp = await client.get(
                    "https://buff.163.com/api/comment/share/detail",
                    params={"comment_type": comment_type, "type_id": type_id},
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("code") != "OK":
                logger.warning(f"buff 评论获取失败: {data}")
                return []

            raw = convert(data.get("data") or {}, Comments)
            return [self._to_comment(c) for c in raw.items]
        except Exception as e:
            logger.warning(f"buff 评论获取失败: {e}")
            return []

    # https://buff.163.com/s/news-detail_share.html?article_id=87832&comment_type=228
    @handle(
        "https://buff.163.com/s/news-detail_share.html",
        r"(?=[^#]*article_id=(?P<article_id>[^&]+))(?=[^#]*comment_type=228)",
    )
    async def parse_video(self, searched: Match[str]):
        article_id = searched["article_id"]
        video = await self._fetch_ok_json(
            url="https://buff.163.com/api/news/share/detail",
            params={"article_id": article_id},
            err_msg="获取视频信息失败",
            model=Video,
        )
        comments = await self.fetch_comments(228, article_id)
        return self.result(
            content=video.content,
            timestamp=video.publish_time,
            url=video.share_data.url,
            author=self.create_author(
                name=video.author, avatar_url=video.avatar, id=video.user_id
            ),
            stats=self.create_stats(
                view_count=format_num(video.views),
                like_count=format_num(video.ups_num),
                comment_count=format_num(video.replies),
            ),
            comments=comments,
        )

    # parse gallery
    # https://buff.163.com/s/preview_share.html?game=csgo&preview_id=V1092280822&comment_type=216
    @handle(
        "https://buff.163.com/s/preview_share.html",
        r"(?=[^#]*game=(?P<game>[^&]+))(?=[^#]*preview_id=(?P<preview_id>[^&]+))(?=[^#]*comment_type=216)",
    )
    async def parse_gallery(self, searched: Match[str]):
        preview_id = searched["preview_id"]
        game = searched["game"]
        gallery = await self._fetch_ok_json(
            url="https://buff.163.com/api/market/preview/share_detail",
            params={"preview_id": preview_id, "game": game},
            err_msg="获取玩家秀信息失败",
            model=Gallery,
        )
        comments = await self.fetch_comments(216, preview_id)
        author = gallery.user_infos[gallery.preview.user_id]
        return self.result(
            title=gallery.preview.share_data.title,
            content=[
                gallery.preview.description,
                self.create_graphic(gallery.preview.icon_url),
            ],
            timestamp=gallery.preview.publish_time,
            url=gallery.preview.share_data.url,
            author=self.create_author(
                name=author.nickname, avatar_url=author.avatar, id=author.user_id
            ),
            stats=self.create_stats(
                like_count=format_num(gallery.preview.ups_num),
            ),
            comments=comments,
        )

    # https://buff.163.com/s/news-detail_share.html?article_id=87855&comment_type=211
    @handle(
        "https://buff.163.com/s/news-detail_share.html",
        r"(?=[^#]*article_id=(?P<article_id>[^&]+))(?=[^#]*comment_type=211)",
    )
    async def parse_news(self, searched: Match[str]):
        article_id = searched["article_id"]
        news = await self._fetch_ok_json(
            url="https://buff.163.com/api/news/share/detail",
            params={"article_id": article_id},
            err_msg="获取NEWS信息失败",
            model=News,
        )
        comments = await self.fetch_comments(211, article_id)
        return self.result(
            title=news.share_data.title,
            content=news.content,
            timestamp=news.publish_time,
            url=news.share_data.url,
            author=self.create_author(
                name=news.author, avatar_url=news.avatar, id=news.user_id
            ),
            stats=self.create_stats(
                view_count=format_num(news.views),
                like_count=format_num(news.ups_num),
                comment_count=format_num(news.replies),
            ),
            comments=comments,
        )

    # https://buff.163.com/s/topic-detail_share.html?social_topic_post_id=P1093043595&comment_type=239
    @handle(
        "https://buff.163.com/s/topic-detail_share.html",
        r"(?=[^#]*social_topic_post_id=(?P<post_id>[^&]+))(?=[^#]*comment_type=239)",
    )
    async def parse_topic(self, searched: Match[str]):
        post_id = searched["post_id"]
        topic = await self._fetch_ok_json(
            url="https://buff.163.com/api/topic/posts/detail",
            params={"social_topic_post_id": post_id},
            err_msg="获取帖子信息失败",
            model=Topic,
        )
        item = topic.items[0]
        author = topic.user_infos[item.author_id]
        comments = await self.fetch_comments(239, post_id)

        return self.result(
            author=self.create_author(
                name=author.nickname,
                avatar_url=author.avatar,
                id=author.user_id,
            ),
            timestamp=item.publish_time,
            url=item.share_data.url,
            content=item.content,
            comments=comments,
            stats=self.create_stats(
                like_count=format_num(item.ups_num),
                comment_count=format_num(item.replies),
            ),
        )
