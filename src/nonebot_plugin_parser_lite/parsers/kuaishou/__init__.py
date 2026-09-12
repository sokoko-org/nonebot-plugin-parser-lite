from re import compile
from secrets import choice
from string import ascii_letters, digits
from typing import ClassVar

from ...data import Comment
from ...utils.log import logger
from ..base import (
    BaseParser,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
    pconfig,
)
from .comment import decode_comments
from .state import Photo, decode_init_state

INIT_PATTERN = compile(r"window\.INIT_STATE\s*=\s*(.*?)</script>")
COMMENT_API = "https://kph8gvfz.m.chenzhongtech.com/rest/wd/photo/comment/list"


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
        photo = await self._fetch_photo(url)
        comments = await self._fetch_comments(photo.photoId)

        return self.result(
            author=photo.author,
            content=photo.content,
            stats=photo.stats,
            comments=comments,
            timestamp=photo.timestamp // 1000,
            url=f"https://m.gifshow.com/fw/photo/{photo.photoId}",
        )

    async def _fetch_photo(self, url: str) -> Photo:
        """获取页面并提取作品数据"""
        real_url = await self.get_final_url(url, headers=self.ios_headers)
        real_url = real_url.replace("/fw/long-video/", "/fw/photo/")
        response = await self.httpx.get(real_url, headers=self.ios_headers)
        response.raise_for_status()

        matched = INIT_PATTERN.search(response.text)
        if matched is None:
            raise ParseException(f"failed to parse video JSON info from HTML: {url}")
        return decode_init_state(matched[1])

    async def _fetch_comments(self, photo_id: str) -> list[Comment]:
        """获取评论；评论接口失败不影响作品解析"""
        try:
            response = await self.httpx.post(
                COMMENT_API,
                json={"photoId": photo_id, "count": pconfig.max_comments},
                cookies={
                    "did": "web_"
                    + "".join(choice(ascii_letters + digits) for _ in range(32))
                },
            )
            return decode_comments(response.content)
        except Exception:
            logger.exception(f"快手获取评论失败, photoId: {photo_id}")
            return []
