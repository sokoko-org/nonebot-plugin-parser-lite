from math import ceil
from typing import ClassVar

from nonebot import logger
import ujson

from ...utils.format import format_num
from ..base import (
    BaseParser,
    MatchWithParams,
    Platform,
    PlatformEnum,
    handle,
)
from .article import decoder as articleDecoder
from .article_comment import decoder as articleCommentDecoder
from .auth import AuthHelper
from .show import decoder as showDecoder
from .show_comment import decoder as showCommentDecoder
from .statuses import WeiboData
from .statuses import decoder as statusedDecoder
from .statuses_comment import decoder as statusesCommentDecoder

# 获取 微博内容
# https://www.weibo.com/ajax/statuses/show?id=5181502771168068

# 微博 $.isLongText 是 True, 需要请求下面的地址获取完整正文
# https://weibo.com/ajax/statuses/longtext?id=P5kWdcfDe

# 获取微博评论
# https://m.weibo.cn/comments/hotflow?mid=5181502771168068

# 获取文章内容
# https://card.weibo.com/article/m/aj/detail?id=2309404962180771742222

# 获取文章评论
# https://card.weibo.com/article/m/aj/comment?id=2309404962180771742222


# 获取 tv_show 评论
# https://weibo.com/ajax/statuses/buildComments?id=5007452630158934&count=20&expand_text=1&is_show_bulletin=2


class WeiBoParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.WEIBO, display_name="微博"
    )

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
        return await self.parse_tv_fid(fid)

    # https://m.weibo.cn/status/5234367615996775
    # https://m.weibo.cn/status/5181502771168068
    # https://m.weibo.cn/status/5234001406855704
    # https://m.weibo.cn/{uid}\d+/{wid}[0-9a-zA-Z]+/qq
    @handle("m.weibo.cn", r"weibo\.cn/(?:status|detail|\d+)/(?P<wid>[0-9a-zA-Z]+)")
    # https://weibo.com/7207262816/P5kWdcfDe
    @handle("weibo.com", r"weibo\.com/\d+/(?P<wid>[0-9a-zA-Z]+)")
    async def _parse_m_weibo_cn(self, searched: MatchWithParams):
        wid = searched["wid"]
        return await self.parse_weibo_id(wid)

    # https://mapp.api.weibo.cn/fx/f7f989b537bb2d94c802c9f77bd1c149.html
    @handle("mapp.api.weibo", r"mapp\.api\.weibo\.cn/fx/[0-9A-Za-z]+\.html")
    async def _parse_mapp_api_weibo(self, searched: MatchWithParams):
        url = f"https://{searched.url}"
        redirect_url = await AuthHelper.get(url, follow_redirects=True)
        keyword, searched = self.search_url(str(redirect_url.url))
        return await self.parse(keyword, searched)

    # https://weibo.com/ttarticle/p/show?id=2309404962180771742222
    # https://weibo.com/ttarticle/x/m/show#/id=2309404962180771742222
    @handle("weibo.com/ttarticle", r"id=(?P<id>\d+)")
    # https://card.weibo.com/article/m/show/id/2309404962180771742222
    @handle("weibo.com/article", r"/id/(?P<id>\d+)")
    async def _parse_article(self, searched: MatchWithParams):
        _id = searched["id"]
        return await self.parse_article(_id)

    async def parse_article(self, id: str):
        response = await AuthHelper.get(
            "https://card.weibo.com/article/m/aj/detail",
            params={
                "id": id,
            },
        )
        detail = articleDecoder.decode(response.content)
        data = detail.data
        comments = []
        total_comment = 0

        try:
            res = await AuthHelper.get(
                "https://card.weibo.com/article/m/aj/comment", params={"id": id}
            )
            comment_data = articleCommentDecoder.decode(res.content)
            total_comment = comment_data.data.total_number
            comments.extend(
                self.create_comment(
                    author=self.create_author(
                        name=sc.user_info.screen_name,
                        avatar_url=sc.user_info.profile_image_url,
                        ext_headers={"Referer": "https://weibo.com/"},
                    ),
                    content=sc.content,
                    timestamp=sc.created_at_unix,
                )
                for sc in comment_data.data.comments
            )
        except Exception as e:
            logger.warning(f"微博文章评论获取失败, mid={id}, {type(e)}:{e!r}")

        return self.result(
            url=data.url,
            title=data.title,
            author=self.create_author(
                name=data.userinfo.screen_name,
                avatar_url=data.userinfo.profile_image_url,
                location=data.region_info.region_name,
                ext_headers={"Referer": "https://weibo.com/"},
            ),
            timestamp=data.create_at_unix,
            content=data.content,
            stats=self.create_stats(
                view_count=data.read_count,
                comment_count=format_num(total_comment),
            ),
            comments=comments,
        )

    async def parse_tv_fid(self, fid: str):
        """解析 show"""

        payload = {"Component_Play_Playinfo": {"oid": fid}}

        response = await AuthHelper.post(
            f"https://weibo.com/tv/api/component?page=/show/{fid}",
            data={"data": ujson.dumps(payload, ensure_ascii=False)},
        )
        data = showDecoder.decode(response.content).data
        play_info = data.Component_Play_Playinfo
        video_content = self.create_video(
            url_or_task=play_info.video_url,
            cover_url=play_info.cover_url,
            duration=play_info.duration_time,
            ext_headers={"Referer": "https://weibo.com/"},
        )

        comments = []
        try:
            res = await AuthHelper.get(
                "https://weibo.com/ajax/statuses/buildComments",
                params={
                    "id": fid.split(":")[-1],
                    "count": 20,
                    "expand_text": 1,
                    "is_show_bulletin": 2,
                },
            )
            comment_data = showCommentDecoder.decode(res.content)
            comments.extend(
                self.create_comment(
                    author=self.create_author(
                        name=sc.user.screen_name,
                        avatar_url=sc.user.profile_image_url,
                        location=sc.source,
                        ext_headers={"Referer": "https://weibo.com/"},
                    ),
                    content=sc.content,
                    timestamp=sc.timestamp,
                    stats=self.create_stats(
                        like_count=format_num(sc.like_counts),
                        comment_count=format_num(len(sc.comments)),
                    ),
                    replies=[
                        self.create_comment(
                            author=self.create_author(
                                name=c.user.screen_name,
                                avatar_url=c.user.profile_image_url,
                                location=c.source,
                                ext_headers={"Referer": "https://weibo.com/"},
                            ),
                            content=c.content,
                            timestamp=c.timestamp,
                        )
                        for c in sc.comments
                    ],
                )
                for sc in comment_data.data
            )
        except Exception as e:
            logger.warning(f"微博评论获取失败, mid={fid}, {type(e)}:{e!r}")

        return self.result(
            title=play_info.title,
            author=self.create_author(
                name=play_info.author,
                avatar_url=play_info.avatar_url,
                location=play_info.ip_info_str,
                ext_headers={"Referer": "https://weibo.com/"},
            ),
            content=[play_info.description, video_content],
            stats=self.create_stats(
                view_count=play_info.play_count,
                like_count=format_num(play_info.attitudes_count),
                comment_count=play_info.comments_count,
                share_count=play_info.reposts_count,
            ),
            timestamp=play_info.real_date,
            url=f"https://h5.video.weibo.com/show/{fid}",
        )

    async def parse_weibo_id(self, weibo_id: str):
        """解析微博 id"""
        response = await AuthHelper.get(
            "https://www.weibo.com/ajax/statuses/show",
            params={"id": weibo_id},
        )
        weibo_data = statusedDecoder.decode(response.content)

        return await self._collect_statuses(weibo_data)

    async def _collect_statuses(self, data: WeiboData, is_repost: bool = False):
        repost = None
        if data.retweeted_status:
            repost = await self._collect_statuses(data.retweeted_status, True)
        comments = []
        if not is_repost:
            try:
                res = await AuthHelper.get(
                    "https://m.weibo.cn/comments/hotflow", params={"mid": data.idstr}
                )
                comment_data = statusesCommentDecoder.decode(res.content)
                comments.extend(
                    self.create_comment(
                        author=self.create_author(
                            name=sc.user.screen_name,
                            avatar_url=sc.user.profile_image_url,
                            location=sc.source,
                            ext_headers={"Referer": "https://weibo.com/"},
                        ),
                        content=sc.content,
                        timestamp=sc.timestamp,
                        stats=self.create_stats(
                            like_count=format_num(sc.like_count),
                            comment_count=format_num(len(sc.replies)),
                        ),
                        replies=[
                            self.create_comment(
                                author=self.create_author(
                                    name=c.user.screen_name,
                                    avatar_url=c.user.profile_image_url,
                                    location=c.source,
                                    ext_headers={"Referer": "https://weibo.com/"},
                                ),
                                content=c.content,
                                timestamp=c.timestamp,
                                stats=self.create_stats(
                                    like_count=format_num(c.like_count),
                                ),
                            )
                            for c in sc.replies
                        ],
                    )
                    for sc in comment_data.data.data
                )
            except Exception as e:
                logger.warning(f"微博评论获取失败, mid={data.idstr}, {type(e)}:{e!r}")

        return self.result(
            author=self.create_author(
                name=data.user.screen_name,
                avatar_url=data.user.profile_image_url,
                id=data.user.idstr,
                location=data.region_name,
                ext_headers={"Referer": "https://weibo.com/"},
            ),
            content=await data.get_content(),
            stats=self.create_stats(
                like_count=format_num(data.attitudes_count),
                share_count=format_num(data.reposts_count),
                comment_count=format_num(data.comments_count),
            ),
            timestamp=data.timestamp,
            url=data.url,
            repost=repost,
            comments=comments,
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
        size = ceil(len(mid) / 7)
        result = []

        for i in range(size):
            s = mid[i * 7 : (i + 1) * 7][::-1]
            s = self._base62_encode(int(s))
            if i < size - 1 and len(s) < 4:
                s = "0" * (4 - len(s)) + s
            result.append(s)

        result.reverse()
        return "".join(result)
