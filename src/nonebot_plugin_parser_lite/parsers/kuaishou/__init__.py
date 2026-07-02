from re import compile
from typing import ClassVar

from ..base import (
    BaseParser,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .state import decode_init_state

INIT_PATTERN = compile(r"window\.INIT_STATE\s*=\s*(.*?)</script>")


class KuaiShouParser(BaseParser):
    """快手解析器"""

    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.KUAISHOU, display_name="快手"
    )

    # https://v.kuaishou.com/2yAnzeZ
    @handle("v.kuaishou", r"v\.kuaishou\.com/[A-Za-z\d._?%&+\-=/#]+")
    @handle("kuaishou", r"(?:www\.)?kuaishou\.com/[A-Za-z\d._?%&+\-=/#]+")
    @handle("chenzhongtech", r"(?:v\.m\.)?chenzhongtech\.com/fw/[A-Za-z\d._?%&+\-=/#]+")
    @handle("m.gifshow.com", r"fw/photo/\d+")
    async def _parse_v_kuaishou(self, searched: MatchWithParams):
        url = f"https://{searched.url}"
        real_url = await self.get_final_url(url, headers=self.ios_headers)
        real_url = real_url.replace("/fw/long-video/", "/fw/photo/")
        response = await self.httpx.get(real_url, headers=self.ios_headers)
        response.raise_for_status()
        if matched := INIT_PATTERN.search(response.text):
            photo = decode_init_state(matched[1])
            return self.result(
                author=photo.author,
                content=photo.content,
                stats=photo.stats,
                timestamp=photo.timestamp // 1000,
                url=f"https://m.gifshow.com/fw/photo/{photo.photoId}",
            )
        else:
            raise ParseException(f"failed to parse video JSON info from HTML: {url}")
