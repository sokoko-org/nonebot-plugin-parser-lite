from hashlib import md5
from typing import ClassVar, TypeVar

from msgspec.json import Decoder

from ..base import (
    BaseParser,
    MatchWithParams,
    Platform,
    PlatformEnum,
    handle,
)
from .bbs import decoder as bbsDecoder
from .comment import decoder as commentDecoder

T = TypeVar("T")


class HupuParser(BaseParser):
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.HUPU, display_name="虎扑")

    async def fetch(self, decoder: Decoder[T], url: str, params: dict | None = None):
        if params is None:
            params = {}
        sorted_keys = sorted(params.keys())
        query_string = "&".join([f"{k}={params[k]}" for k in sorted_keys])

        sign_str = f"{query_string}HUPU_SALT_AKJfoiwer394Jeiow4u309"
        sign = md5(sign_str.encode("utf-8")).hexdigest()
        params["sign"] = sign
        resp = await self.httpx.get(url, params=params)
        return decoder.decode(resp.content)

    # 图文
    # https://m.hupu.com/bbs-share/639669147.html
    # https://bbs.hupu.com/639669147.html
    # https://m.hupu.com/bbs/639669147.html
    @handle("m.hupu.com/bbs", r"bbs/(?P<topic_id>\d+)(?:\.html)?")
    @handle("bbs.hupu.com", r"(?P<topic_id>\d+)(?:\.html)?")
    @handle("m.hupu.com/bbs-share", r"bbs-share/(?P<topic_id>\d+)(?:\.html)?")
    async def parse_bbs(self, searched: MatchWithParams):
        topic_id = searched["topic_id"]
        bbs = await self.fetch(
            bbsDecoder, f"https://bbs.mobileapi.hupu.com/1/7.5.51/threads/{topic_id}"
        )
        comment_data = await self.fetch(
            commentDecoder,
            "https://bbs.mobileapi.hupu.com/1/7.5.51/threads/getsThreadPostList",
            {
                "fid": "",
                "tid": topic_id,
                "order": "score",
                "page": "1",
            },
        )
        return self.result(
            author=bbs.author_obj,
            content=bbs.content,
            comments=comment_data.comments,
            stats=bbs.stats,
            title=bbs.title,
            timestamp=bbs.timestamp,
            url=f"https://m.hupu.com/bbs/{bbs.tid}",
        )
