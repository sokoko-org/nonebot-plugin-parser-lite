import re
from typing import ClassVar

import json_repair
from msgspec import convert
from nonebot import logger

from ...utils.browser import BrowserManager
from ...utils.format import format_num
from ..base import (
    BaseParser,
    ContentItem,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .note import Note
from .video_or_article import decoder as video_or_article_decoder

ROUTER_PATTERN = re.compile(
    pattern=r"window\._ROUTER_DATA\s*=\s*(.*?)</script>",
    flags=re.DOTALL,
)
NOTE_PATTERN = re.compile(
    pattern=r'self\.__pace_f\.push\(\[1,"7:.*?null,(.*?)</script>',
    flags=re.DOTALL,
)


class DouyinParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.DOUYIN, display_name="抖音"
    )

    # https://v.douyin.com/_2ljF4AmKL8
    @handle("v.douyin", r"v\.douyin\.com/[a-zA-Z0-9_\-]+")
    @handle("jx.douyin", r"jx\.douyin\.com/[a-zA-Z0-9_\-]+")
    async def _parse_short_link(self, searched: MatchWithParams):
        url = f"https://{searched.url}"
        return await self.parse_with_redirect(url)

    # https://www.douyin.com/video/7521023890996514083
    # https://www.douyin.com/note/7469411074119322899
    # https://m.douyin.com/share/note/7591875747808560613
    @handle("douyin", r"douyin\.com/(?P<ty>video|note|slides|article)/(?P<vid>\d+)")
    @handle(
        "iesdouyin",
        r"iesdouyin\.com/share/(?P<ty>video|note|slides|article)/(?P<vid>\d+)",
    )
    @handle(
        "m.douyin",
        r"m\.douyin\.com/share/(?P<ty>video|note|slides|article)/(?P<vid>\d+)",
    )
    # https://jingxuan.douyin.com/m/video/7574300896016862490?app=yumme&utm_source=copy_link
    @handle(
        "jingxuan.douyin",
        r"jingxuan\.douyin.com/m/(?P<ty>video|note|slides|article)/(?P<vid>\d+)",
    )
    async def _parse_douyin(self, searched: MatchWithParams):
        ty, vid = searched["ty"], searched["vid"]
        try:
            if ty in ["video", "article"]:
                return await self.parse_video_or_article(
                    f"https://m.douyin.com/share/{ty}/{vid}"
                )
            else:
                return await self.parse_note(vid)
        except ParseException as e:
            logger.warning(f"failed to parse {searched[0]}, error: {e}")
        raise ParseException("分享已删除或资源直链提取失败, 请稍后再试")

    async def parse_note(self, vid: str):
        tab = await BrowserManager.new_tab()
        tab.set.load_mode.eager()
        tab.get(f"https://www.douyin.com/note/{vid}")
        text = tab.html
        tab.close()
        matched = NOTE_PATTERN.search(text)

        if not matched or not matched[1]:
            raise ParseException("未找到数据，可能触发验证码风控")
        data = convert(
            json_repair.loads(
                matched[1].replace('\\"', '"'),
                skip_json_loads=True,
            ),
            Note,
        )
        content: list[ContentItem] = [data.aweme.detail.desc]
        content.extend(data.aweme.content)
        comments = [
            self.create_comment(
                author=self.create_author(
                    name=comment.user.nickname,
                    avatar_url=comment.user.avatarUri,
                    location=comment.ipLabel,
                ),
                content=comment.content,
                timestamp=comment.createTime,
                stats=self.create_stats(
                    like_count=format_num(comment.diggCount),
                    comment_count=format_num(comment.replyTotal),
                ),
            )
            for comment in data.comment.comments
        ]
        return self.result(
            author=self.create_author(
                name=data.aweme.detail.authorInfo.nickname,
                avatar_url=data.aweme.detail.authorInfo.avatarUri,
            ),
            content=content,
            stats=self.create_stats(
                like_count=format_num(data.aweme.stats.diggCount),
                comment_count=format_num(data.aweme.stats.commentCount),
                share_count=format_num(data.aweme.stats.shareCount),
                collect_count=format_num(data.aweme.stats.collectCount),
            ),
            timestamp=data.aweme.detail.createTime,
            comments=comments,
            url=f"https://www.douyin.com/note/{vid}",
        )

    async def parse_video_or_article(self, url: str):
        response = await self.httpx.get(
            url, headers=self.ios_headers, follow_redirects=False
        )
        if response.status_code != 200:
            raise ParseException(f"status: {response.status_code}")
        text = response.text

        matched = ROUTER_PATTERN.search(text)

        if not matched or not matched[1]:
            raise ParseException("can't find _ROUTER_DATA in html")

        data = video_or_article_decoder.decode(matched[1].strip())
        video_data = data.video_data
        content: list[ContentItem] = [video_data.desc]

        content.extend(video_data.medias)

        stats = video_data.statistics

        comments = [
            self.create_comment(
                author=self.create_author(
                    name=comment.user.nickname,
                    avatar_url=comment.user.avatar_url,
                    location=comment.ip_label,
                ),
                content=[comment.text],
                timestamp=comment.createTime,
                stats=self.create_stats(
                    like_count=format_num(comment.digg_count),
                    comment_count=format_num(comment.reply_comment_total),
                ),
            )
            for comment in data.comment_list.comments
        ]
        return self.result(
            author=self.create_author(
                name=video_data.author.nickname, avatar_url=video_data.author.avatar_url
            ),
            content=content,
            stats=self.create_stats(
                like_count=format_num(stats.digg_count),
                comment_count=format_num(stats.comment_count),
                share_count=format_num(stats.share_count),
                collect_count=format_num(stats.collect_count),
            ),
            timestamp=video_data.create_time,
            comments=comments,
            url=url,
        )
