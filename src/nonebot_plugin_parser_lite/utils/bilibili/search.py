from enum import IntEnum
from typing import Literal, TypeVar, overload

from msgspec import Struct, convert, field

from .client import ENVIRONMENT, HTTP_CLIENT, MOBI_APP
from .credential import Credential
from .exceptions import BiliHelperException
from .sign import enc_app_sign


class SearchType(IntEnum):
    """搜索类型"""

    ALL = 0
    """综合搜索，响应中包含按类型分组的结果"""
    USER = 2
    """用户搜索"""
    BANGUMI = 7
    """番剧搜索"""
    MOVIE = 8
    """影视搜索"""


class SearchVideo(Struct):
    """综合搜索中的视频结果"""

    title: str | None
    cover: str
    uri: str
    aid: str = field(name="param")
    """视频 avid"""
    goto: str
    play: int
    danmaku: int
    author: str
    publish_time: int = field(name="ptime")
    """视频发布时间戳"""
    duration: str
    mid: int
    face: str


class SearchBangumi(Struct):
    """番剧搜索结果"""

    title: str
    cover: str
    uri: str
    media_id: str = field(name="param")
    """番剧媒体 ID"""
    goto: str
    season_id: int
    """番剧 season ID"""
    season_type: int
    season_type_name: str
    style: str
    rating: float
    vote: int
    area: str


class SearchMovie(Struct):
    """影视搜索结果"""

    title: str
    cover: str
    uri: str
    media_id: str = field(name="param")
    """影视媒体 ID"""
    goto: str
    season_id: int
    """影视 season ID"""
    season_type: int
    season_type_name: str
    style: str
    rating: float
    vote: int
    area: str


class SearchUser(Struct):
    """用户搜索结果"""

    title: str
    cover: str
    uri: str
    mid_text: str = field(name="param")
    """接口返回的字符串形式用户 ID"""
    goto: str
    sign: str
    fans: int
    level: int
    mid: int
    live_uri: str = ""
    """用户正在直播时返回的客户端链接"""
    room_id: int = field(default=0, name="roomid")
    """用户未开通直播间时可能缺失"""


class SearchAllItems(Struct):
    """综合搜索按内容类型分组的结果"""

    archive: list[SearchVideo] = field(default_factory=list)
    upper: list[SearchUser] = field(default_factory=list)
    season2: list[SearchBangumi] = field(default_factory=list)
    movie2: list[SearchMovie] = field(default_factory=list)


class SearchAllResult(Struct):
    """综合搜索分页结果"""

    trackid: str
    page: int
    items: SearchAllItems
    attribute: int
    next: str
    """下一页游标"""


class SearchBangumiResult(Struct):
    """番剧搜索分页结果"""

    trackid: str
    pages: int
    page: int
    total: int
    items: list[SearchBangumi]


class SearchUserResult(Struct):
    """用户搜索分页结果"""

    trackid: str
    pages: int
    page: int
    total: int
    items: list[SearchUser]


class SearchMovieResult(Struct):
    """影视搜索分页结果"""

    trackid: str
    pages: int
    page: int
    total: int
    items: list[SearchMovie]


SearchResultT = TypeVar(
    "SearchResultT",
    SearchAllResult,
    SearchBangumiResult,
    SearchUserResult,
    SearchMovieResult,
)


class Search:
    """搜索类"""

    def __init__(
        self,
        keyword: str,
        credential: Credential | None = None,
    ) -> None:
        if not keyword.strip():
            raise BiliHelperException("keyword 不能为空")
        self.keyword = keyword
        self.credential = credential

    async def _request(
        self,
        path: str,
        params: dict[str, str | int],
        result_type: type[SearchResultT],
    ) -> SearchResultT:
        result = (
            await HTTP_CLIENT.get(
                url=f"https://app.bilibili.com/{path}",
                params=enc_app_sign(params),
                headers={"app-key": MOBI_APP, "env": ENVIRONMENT},
                cookies=(
                    self.credential.get_cookies()
                    if self.credential is not None
                    else None
                ),
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        return convert(result["data"], result_type)

    @overload
    async def get_result(
        self,
        search_type: Literal[SearchType.ALL] = SearchType.ALL,
        *,
        page: int = 1,
        page_size: int = 20,
        order: str = "totalrank",
        duration: int = 0,
        category_id: int = 0,
        user_type: int = 0,
    ) -> SearchAllResult: ...

    @overload
    async def get_result(
        self,
        search_type: Literal[SearchType.BANGUMI],
        *,
        page: int = 1,
        page_size: int = 20,
        order: str = "totalrank",
        duration: int = 0,
        category_id: int = 0,
        user_type: int = 0,
    ) -> SearchBangumiResult: ...

    @overload
    async def get_result(
        self,
        search_type: Literal[SearchType.USER],
        *,
        page: int = 1,
        page_size: int = 20,
        order: str = "totalrank",
        duration: int = 0,
        category_id: int = 0,
        user_type: int = 0,
    ) -> SearchUserResult: ...

    @overload
    async def get_result(
        self,
        search_type: Literal[SearchType.MOVIE],
        *,
        page: int = 1,
        page_size: int = 20,
        order: str = "totalrank",
        duration: int = 0,
        category_id: int = 0,
        user_type: int = 0,
    ) -> SearchMovieResult: ...

    @overload
    async def get_result(
        self,
        search_type: SearchType,
        *,
        page: int = 1,
        page_size: int = 20,
        order: str = "totalrank",
        duration: int = 0,
        category_id: int = 0,
        user_type: int = 0,
    ) -> (
        SearchAllResult
        | SearchBangumiResult
        | SearchUserResult
        | SearchMovieResult
    ): ...

    async def get_result(
        self,
        search_type: SearchType = SearchType.ALL,
        *,
        page: int = 1,
        page_size: int = 20,
        order: str = "totalrank",
        duration: int = 0,
        category_id: int = 0,
        user_type: int = 0,
    ) -> SearchAllResult | SearchBangumiResult | SearchUserResult | SearchMovieResult:
        """按指定类型搜索；默认返回综合搜索结果"""
        if page <= 0:
            raise BiliHelperException("page 必须大于 0")
        if page_size <= 0:
            raise BiliHelperException("page_size 必须大于 0")

        params: dict[str, str | int] = {
            "keyword": self.keyword,
            "pn": page,
            "ps": page_size,
        }
        if search_type is SearchType.ALL:
            params.update(
                order=order,
                duration=duration,
                rid=category_id,
            )
            return await self._request("x/v2/search", params, SearchAllResult)
        if search_type is SearchType.BANGUMI:
            params["type"] = SearchType.BANGUMI
            return await self._request("x/v2/search/type", params, SearchBangumiResult)
        if search_type is SearchType.USER:
            params.update(
                type=SearchType.USER,
                disable_rcmd=0,
                highlight=1,
                order=order,
                user_type=user_type,
            )
            return await self._request("x/v2/search/type", params, SearchUserResult)
        if search_type is SearchType.MOVIE:
            params["type"] = SearchType.MOVIE
            return await self._request("x/v2/search/type", params, SearchMovieResult)
        raise BiliHelperException(f"不支持的搜索类型: {search_type}")
