import json
from math import ceil
from time import time
from typing import ClassVar
from uuid import uuid4

from bs4 import BeautifulSoup, Tag
from curl_cffi import AsyncSession

from ..base import (
    BaseParser,
    MatchWithParams,
    MediaContent,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .article import decoder as articleDecoder
from .common import WeiboData
from .common import decoder as commonDecoder
from .show import decoder as showDecoder

SESSION = AsyncSession(impersonate="chrome131")


class WeiBoParser(BaseParser):
    # 平台信息
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.WEIBO, display_name="微博"
    )

    def __init__(self):
        super().__init__()
        self.headers.update(
            {
                "accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
                    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
                ),
                "referer": "https://weibo.com/",
                "origin": "https://weibo.com",
            }
        )
        self.httpx.headers.update(self.headers)

    # https://weibo.com/tv/show/1034:5007449447661594?mid=5007452630158934
    @handle(
        "weibo.com/tv",
        r"weibo\.com/tv/show/\d{4}:\d+",
        params={"mid": {"as_int": True}},
    )
    async def _parse_weibo_tv(self, searched: MatchWithParams):
        mid = searched["mid"]
        weibo_id = self._mid2id(mid)
        return await self.parse_weibo_id(weibo_id)

    # https://video.weibo.com/show?fid=1034:5145615399845897
    @handle(
        "video.weibo.com/show",
        params={"fid": {}},
    )
    async def _parse_video_weibo(self, searched: MatchWithParams):
        fid = searched["fid"]
        return await self.parse_fid(fid)

    # https://m.weibo.cn/status/5234367615996775
    # https://m.weibo.cn/detail/4976424138313924
    # https://m.weibo.cn/status/Q0KtXh6z2
    # https://m.weibo.cn/{uid}\d+/{wid}[0-9a-zA-Z]+/qq
    @handle("m.weibo.cn", r"weibo\.cn/(?:status|detail|\d+)/(?P<wid>[0-9a-zA-Z]+)")
    # https://weibo.com/7207262816/P5kWdcfDe
    @handle("weibo.com", r"weibo\.com/\d+/(?P<wid>[0-9a-zA-Z]+)")
    async def _parse_m_weibo_cn(self, searched: MatchWithParams):
        wid = searched["wid"]
        return await self.parse_weibo_id(wid)

    # https://mapp.api.weibo.cn/fx/233911ddcc6bffea835a55e725fb0ebc.html
    @handle("mapp.api.weibo", r"mapp\.api\.weibo\.cn/fx/[0-9A-Za-z]+\.html")
    async def _parse_mapp_api_weibo(self, searched: MatchWithParams):
        url = f"https://{searched.url}"
        return await self.parse_with_redirect(url)

    # https://weibo.com/ttarticle/p/show?id=2309404962180771742222
    # https://weibo.com/ttarticle/x/m/show#/id=2309404962180771742222
    @handle("weibo.com/ttarticle", r"id=(?P<id>\d+)")
    # https://card.weibo.com/article/m/show/id/2309404962180771742222
    @handle("weibo.com/article", r"/id/(?P<id>\d+)")
    async def _parse_article(self, searched: MatchWithParams):
        _id = searched["id"]
        return await self.parse_article(_id)

    async def parse_article(self, _id: str):
        response = await self.httpx.get(
            "https://card.weibo.com/article/m/aj/detail",
            params={
                "_rid": str(uuid4()),
                "id": _id,
                "_t": int(time() * 1000),
            },
        )
        response.raise_for_status()

        detail = articleDecoder.decode(response.content)

        if detail.msg != "success":
            raise ParseException("请求失败")

        data = detail.data

        soup = BeautifulSoup(data.content, "html.parser")
        contents: list[MediaContent | str] = []

        for element in soup.find_all(["p", "img"]):
            if not isinstance(element, Tag):
                continue

            if element.name == "p":
                text = element.get_text()
                if text := text.replace("\u200b", ""):
                    contents.append(text)
            elif element.name == "img":
                src = element.get("src")
                if isinstance(src, str):
                    contents.append(self.create_image(src))

        author = self.create_author(
            name=data.userinfo.screen_name,
            avatar_url=data.userinfo.profile_image_url,
        )

        return self.result(
            url=data.url,
            title=data.title,
            author=author,
            timestamp=data.create_at_unix,
            content=contents,
        )

    async def parse_fid(self, fid: str):
        """解析 show (带 fid)"""

        payload = {"Component_Play_Playinfo": {"oid": fid}}

        response = await self.httpx.post(
            f"https://h5.video.weibo.com/api/component?page=/show/{fid}",
            data={"data": json.dumps(payload, ensure_ascii=False)},
            headers={
                "Referer": f"https://h5.video.weibo.com/show/{fid}",
                "Content-Type": "application/x-www-form-urlencoded",
                **self.headers,
            },
        )
        response.raise_for_status()

        data = showDecoder.decode(response.content).data
        play_info = data.Component_Play_Playinfo
        author = self.create_author(
            name=play_info.name,
            avatar_url=play_info.avatar,
            description=play_info.description,
        )
        video_content = self.create_video(
            play_info.video_url,
            play_info.cover_url,
        )

        return self.result(
            title=play_info.title,
            author=author,
            content=[play_info.text, video_content],
            timestamp=play_info.real_date,
            url=f"https://h5.video.weibo.com/show/{fid}",
        )

    async def parse_weibo_id(self, weibo_id: str):
        """解析微博 id"""
        headers = {
            "referer": "https://weibo.com/",
            **self.headers,
        }
        # 关键：不带 cookie、不跟随重定向（避免二跳携 cookie）
        response = await SESSION.get(
            "https://weibo.com/ajax/statuses/show",
            params={"id": weibo_id},
            headers=headers,
        )
        weibo_data = commonDecoder.decode(response.content).data

        return self._collect_result(weibo_data)

    def _collect_result(self, data: WeiboData):
        contents: list[MediaContent | str] = [data.text_content]

        # 添加视频内容
        if video_url := data.video_url:
            cover_url = data.cover_url
            contents.append(
                self.create_video(
                    url_or_task=video_url,
                    cover_url=cover_url,
                    ext_headers={"Referer": "https://weibo.com/"},
                )
            )

        # 添加图片内容
        if image_urls := data.image_urls:
            contents.extend(
                self.create_images(
                    image_urls=image_urls,
                    ext_headers={"Referer": "https://weibo.com/"},
                )
            )

        # 构建作者
        author = self.create_author(
            name=data.display_name, avatar_url=data.user.profile_image_url
        )
        repost = None
        if data.retweeted_status:
            repost = self._collect_result(data.retweeted_status)

        return self.result(
            title=data.title,
            author=author,
            content=contents,
            timestamp=data.timestamp,
            url=data.url,
            repost=repost,
        )

    def _base62_encode(self, number: int) -> str:
        """将数字转换为 base62 编码"""
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if number == 0:
            return "0"

        result = ""
        while number > 0:
            result = alphabet[number % 62] + result
            number //= 62

        return result

    def _mid2id(self, mid: str) -> str:
        """将微博 mid 转换为 id"""

        mid = mid[::-1]
        size = ceil(len(mid) / 7)  # 计算每个块的大小
        result = []

        for i in range(size):
            # 对每个块进行处理并反转
            s = mid[i * 7 : (i + 1) * 7][::-1]
            # 将字符串转为整数后进行 base62 编码
            s = self._base62_encode(int(s))
            # 如果不是最后一个块并且长度不足4位，进行左侧补零操作
            if i < size - 1 and len(s) < 4:
                s = "0" * (4 - len(s)) + s
            result.append(s)

        result.reverse()  # 反转结果数组
        return "".join(result)  # 将结果数组连接成字符串
