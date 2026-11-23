from typing import ClassVar

from nonebot.log import logger

from ..base import (
    BaseParser,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
    pconfig,
)
from .article import decoder as articleDecoder
from .comment import decoder as commentDecoder
from .sign import get_token, sign_headers

MAX_PAGE_SIZE = 20
"""评论接口单页上限，超过会返回参数错误"""


class SkylandParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.SKYLAND, display_name="森空岛"
    )

    async def _get(self, path: str, params: dict[str, str]):
        url = self.httpx.build_request(
            "GET", f"https://zonai.skland.com{path}", params=params
        ).url
        token = await get_token(self.httpx)
        resp = await self.httpx.get(url, headers=sign_headers(token, url))
        if resp.is_success:
            return resp
        raise ParseException(f"请求失败: {resp.status_code} - {resp.text}")

    # https://www.skland.com/article?id=6503530
    @handle("skland.com/article", params={"id": {"as_int": True}})
    async def parse_article(self, searched: MatchWithParams):
        article_id = str(searched["id"])
        resp = await self._get("/web/v2/item", {"id": article_id})
        parsed = articleDecoder.decode(resp.content)
        if parsed.code != 0 or parsed.data is None:
            raise ParseException(f"获取文章失败: {parsed.code} - {parsed.message}")
        article = parsed.data

        comments = await self._fetch_comments(article_id)

        return self.result(
            author=article.author,
            url=article.url,
            title=article.title,
            content=article.content,
            stats=article.stats,
            timestamp=article.item.timestamp,
            comments=comments,
        )

    async def _fetch_comments(self, article_id: str):
        if not pconfig.max_comments:
            return []
        try:
            resp = await self._get(
                "/web/v1/comment/list-by-topic",
                {
                    "parentId": article_id,
                    "parentKind": "item",
                    "sortType": "1",
                    "pageSize": str(min(pconfig.max_comments, MAX_PAGE_SIZE)),
                },
            )
            return commentDecoder.decode(resp.content).comments
        except Exception:
            logger.exception("获取森空岛评论失败")
            return []
