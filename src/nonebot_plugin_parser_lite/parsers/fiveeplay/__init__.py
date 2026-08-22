from typing import ClassVar

from ..base import BaseParser, MatchWithParams, Platform, PlatformEnum, handle
from .topic import decoder as postDecoder


class FiveEPlayParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.FIVEEPLAY, display_name="5EPlay"
    )

    # https://csgo.5eplay.com/forum/share/1050838
    # https://csgo.5eplay.com/forum/1050838
    # https://csgo.5eplay.com/forum/share/1050797
    @handle("csgo.5eplay.com/forum", r"forum/(?P<topic_id>\d+)")
    @handle("csgo.5eplay.com/forum", r"share/(?P<topic_id>\d+)")
    async def parse_topic(self, searched: MatchWithParams):
        topic_id = searched["topic_id"]
        res = await self.httpx.get(
            f"https://app.5eplay.com/api/csgo/forum/topic/{topic_id}"
        )
        res.raise_for_status()
        post = postDecoder.decode(res.content)
        return self.result(
            author=post.author,
            url=post.url,
            content=post.content,
            timestamp=post.timestamp,
            title=post.title,
            stats=post.stats,
            comments=post.comments,
        )
