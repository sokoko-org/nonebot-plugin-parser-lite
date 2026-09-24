from msgspec import Struct, convert

from .client import HTTP_CLIENT
from .exceptions import BiliHelperException


class FavoriteUpper(Struct):
    """收藏夹创建者"""

    mid: int
    name: str
    face: str


class FavoriteItem(Struct):
    """收藏夹中的视频"""

    title: str
    cover: str
    intro: str
    link: str

    @property
    def url(self) -> str:
        """视频网页地址"""
        return self.link.replace("bilibili://video/", "https://bilibili.com/video/av")

    @property
    def desc(self) -> str:
        """用于渲染的视频描述"""
        return f"标题: {self.title}\n简介: {self.intro}\n链接: {self.url}"

    @property
    def avid(self) -> int:
        """视频 avid"""
        return int(self.link.split("/")[-1])


class FavoriteInfo(Struct):
    """收藏夹基础信息"""

    title: str
    cover: str
    upper: FavoriteUpper
    """收藏夹创建者"""
    ctime: int
    """创建时间戳"""
    mtime: int
    """最后修改时间戳"""
    media_count: int
    """收藏夹内媒体总数"""
    intro: str


class FavoriteListContent(Struct):
    """收藏夹内容分页结果"""

    info: FavoriteInfo
    medias: list[FavoriteItem] | None
    """当前页视频；风控或空收藏夹时可能为 ``None``"""
    has_more: bool
    """是否还有下一页"""

    @property
    def title(self) -> str:
        return f"收藏夹 - {self.info.title}"

    @property
    def cover(self) -> str:
        return self.info.cover

    @property
    def desc(self) -> str:
        return f"简介: {self.info.intro}"

    @property
    def timestamp(self) -> int:
        return self.info.ctime


async def get_video_favorite_list_content(
    media_id: int,
    page: int = 1,
    keyword: str = "",
) -> FavoriteListContent:
    """获取视频收藏夹内容，也可用于搜索收藏夹"""
    params: dict[str, int | str] = {
        "media_id": media_id,
        "pn": page,
        "ps": 20,
    }
    if keyword:
        params["keyword"] = keyword

    result = (
        await HTTP_CLIENT.get(
            url="https://api.bilibili.com/x/v3/fav/resource/list",
            params=params,
        )
    ).json()
    if result["code"] != 0:
        raise BiliHelperException(result)
    return convert(result["data"], FavoriteListContent)
