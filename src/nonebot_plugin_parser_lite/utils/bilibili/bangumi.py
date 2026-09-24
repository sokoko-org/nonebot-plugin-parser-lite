from msgspec import Struct, convert, field

from .client import HTTP_CLIENT, get_bilibili_headers
from .exceptions import BiliHelperException
from .sign import enc_app_sign


class BangumiStat(Struct):
    """番剧统计信息"""

    coins: int
    danmakus: int
    favorite: int
    """追番或收藏数"""
    likes: int
    reply: int
    """评论数"""
    share: int
    views: int
    """播放数"""


class BangumiEpisode(Struct):
    """番剧中的单个剧集"""

    aid: int
    """关联稿件 avid"""
    bvid: str
    """关联稿件 bvid"""
    cid: int
    cover: str
    duration: int
    """剧集时长，单位为毫秒"""
    ep_id: int
    """剧集 epid"""
    id: int
    link: str
    long_title: str
    pub_time: int
    release_date: str
    share_url: str
    short_link: str
    status: int
    subtitle: str
    title: str


class BangumiEpisodeModuleData(Struct):
    """番剧选集分组的数据"""

    episodes: list[BangumiEpisode] = field(default_factory=list)
    """当前分组的剧集；关联季度等非选集分组中不存在(比如电影)"""


class BangumiEpisodeModule(Struct):
    """番剧选集分组"""

    id: int
    title: str
    """分组标题，例如“正片”或“花絮”"""
    style: str
    data: BangumiEpisodeModuleData


class BangumiInfo(Struct):
    """番剧详情"""

    cover: str
    evaluate: str
    """番剧简介"""
    title: str
    season_title: str
    """季度或系列标题"""
    square_cover: str
    share_url: str
    """番剧分享页地址"""
    stat: BangumiStat
    modules: list[BangumiEpisodeModule]
    """按正片、花絮等类别划分的选集分组"""


class Bangumi:
    """番剧类"""

    def __init__(
        self,
        ep_id: int | str | None = None,
        season_id: int | str | None = None,
    ) -> None:
        self.ep_id = ep_id
        self.season_id = season_id
        self.info: BangumiInfo | None = None

    async def get_info(self) -> BangumiInfo:
        """获取番剧详情"""
        if self.info is not None:
            return self.info

        params: dict[str, str] = {}
        if self.season_id not in (None, ""):
            params["season_id"] = str(self.season_id)
        if self.ep_id not in (None, ""):
            params["ep_id"] = str(self.ep_id)

        headers = get_bilibili_headers()
        headers = {
            key: headers[key] for key in ("user-agent", "app-key", "env", "buvid")
        }
        result = (
            await HTTP_CLIENT.get(
                url="https://api.bilibili.com/pgc/view/v2/app/season",
                params=enc_app_sign(params),
                headers=headers,
            )
        ).json()
        if result["code"] != 0:
            raise BiliHelperException(result)
        self.info = convert(result["data"], BangumiInfo)
        return self.info

    async def get_episodes(self) -> list[BangumiEpisode]:
        """获取全部选集，按接口中的分组和剧集顺序展开"""
        info = await self.get_info()
        return [episode for module in info.modules for episode in module.data.episodes]
