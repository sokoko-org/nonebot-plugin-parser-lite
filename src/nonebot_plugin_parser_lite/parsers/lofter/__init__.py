import re
from typing import ClassVar
from msgspec import convert
from ..base import (
    BaseParser,
    handle,
    ParseException,
    Platform,
    PlatformEnum,
    MediaContent,
)

from ...utils.http_utils import get_async_client
from .post import Post
from ...utils.format import format_num

INITIAL_STATE = re.compile(
    pattern=r"window\.__initialize_data__\s*=(.*?)</script>",
    flags=re.DOTALL,
)


class LofterParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.LOFTER, display_name="lofter"
    )

    @handle(
        "lofter.com",
        r"post/(?P<blog_hex>[0-9a-zA-Z]+)_(?P<post_hex>[0-9a-zA-Z]+)",
    )
    async def _parser(self, searched: re.Match[str]):
        blog_id = int(searched["blog_hex"], 16)
        post_id = int(searched["post_hex"], 16)
        async with get_async_client() as client:
            response = await client.post(
                "https://api.lofter.com/oldapi/post/detail.api",
                params={"product": "lofter-android-8.1.20"},
                data={
                    "postid": post_id,
                    "targetblogid": blog_id,
                },
            )
            response.raise_for_status()
            data = response.json()
        if data["meta"]["status"] != 200:
            raise ParseException(f"Lofter 解析失败: {data['meta']['msg']}")
        post = convert(data["response"]["posts"][0]["post"], Post)
        content: list[MediaContent | str] = [post.text]
        content.extend(post.medias)
        author = post.blogInfo
        stats = post.postCount
        return self.result(
            title=post.title,
            content=content,
            timestamp=post.publishTime // 1000,
            url=searched[0],
            author=self.create_author(
                name=author.blogNickName,
                avatar_url=author.bigAvaImg,
                id=author.blogName,
            ),
            stats=self.create_stats(
                like_count=format_num(stats.favoriteCount),
                share_count=format_num(stats.shareCount),
                comment_count=format_num(stats.responseCount),
            ),
        )
