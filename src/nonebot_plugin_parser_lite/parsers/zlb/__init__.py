from typing import ClassVar

from ...utils.format import format_num
from ..base import (
    DOWNLOADER,
    BaseParser,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .topic import decoder as postDecoder


class ZLBParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.ZLB, display_name="壁吧专楼吧"
    )

    @handle("zlb.ink", r"topic/(?P<topic_id>\d+)")
    async def parse_topic(self, searched: MatchWithParams):
        topic_id = searched["topic_id"]
        res = await DOWNLOADER.client.get(
            f"https://bb.zlb.ink/t/topic/{topic_id}.json",
            use_curl_cffi=True,
            headers=self.headers,
        )
        if not res.is_success:
            try:
                summary = res.json()
            except Exception:
                summary = res.text[:100]
            raise ParseException(f"获取帖子失败: {summary}")
        post = postDecoder.decode(res.content)
        return self.result(
            author=self.create_author(
                name=post.detail.display_username or post.detail.username,
                avatar_url=post.detail.avatar_url,
            ),
            url=f"https://bb.zlb.ink/t/topic/{post.id}",
            title=post.title,
            content=post.detail.content,
            comments=post.comment_list,
            stats=self.create_stats(
                like_count=format_num(post.like_count),
                view_count=format_num(post.views),
                comment_count=format_num(post.posts_count - 1),
            ),
            timestamp=post.detail.timestamp,
        )
