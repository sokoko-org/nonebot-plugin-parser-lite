import re
from typing import ClassVar

from nonebot import logger

from ...utils.http_utils import get_async_client

from ..base import (
    Platform,
    BaseParser,
    PlatformEnum,
    ParseException,
    handle,
)
from .video import decoder
from ...utils.format import format_num


ROUTER_PATTERN = re.compile(
    pattern=r"window\._ROUTER_DATA\s*=\s*(.*?)</script>",
    flags=re.DOTALL,
)


class DouyinParser(BaseParser):
    # 平台信息
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.DOUYIN, display_name="抖音"
    )

    # https://v.douyin.com/_2ljF4AmKL8
    @handle("v.douyin", r"v\.douyin\.com/[a-zA-Z0-9_\-]+")
    @handle("jx.douyin", r"jx\.douyin\.com/[a-zA-Z0-9_\-]+")
    async def _parse_short_link(self, searched: re.Match[str]):
        url = f"https://{searched.group(0)}"
        return await self.parse_with_redirect(url)

    # https://www.douyin.com/video/7521023890996514083
    # https://www.douyin.com/note/7469411074119322899
    @handle("douyin", r"douyin\.com/(?P<ty>video|note|article)/(?P<vid>\d+)")
    @handle(
        "iesdouyin",
        r"iesdouyin\.com/share/(?P<ty>slides|video|note|article)/(?P<vid>\d+)",
    )
    @handle(
        "m.douyin",
        r"m\.douyin\.com/share/(?P<ty>slides|video|note|article)/(?P<vid>\d+)",
    )
    # https://jingxuan.douyin.com/m/video/7574300896016862490?app=yumme&utm_source=copy_link
    @handle(
        "jingxuan.douyin",
        r"jingxuan\.douyin.com/m/(?P<ty>slides|video|note|article)/(?P<vid>\d+)",
    )
    async def _parse_douyin(self, searched: re.Match[str]):
        ty, vid = searched["ty"], searched["vid"]
        if ty == "article":
            ty = "note"
        url = f"https://m.douyin.com/share/{ty}/{vid}"
        try:
            return await self.parse_video(url)
        except ParseException as e:
            logger.warning(f"failed to parse {url}, error: {e}")
        raise ParseException("分享已删除或资源直链提取失败, 请稍后再试")

    async def parse_video(self, url: str):
        async with get_async_client(
            headers=self.ios_headers,
            follow_redirects=False,
        ) as client:
            response = await client.get(url)
            if response.status_code != 200:
                raise ParseException(f"status: {response.status_code}")
            text = response.text

        matched = ROUTER_PATTERN.search(text)

        if not matched or not matched[1]:
            raise ParseException("can't find _ROUTER_DATA in html")

        data = decoder.decode(matched[1].strip())
        video_data = data.video_data
        # 使用新的简洁构建方式
        contents = []

        # 添加图片内容
        if image_urls := video_data.image_urls:
            contents.extend(self.create_images(image_urls))

        # 添加视频内容
        elif video_url := video_data.video_url:
            cover_url = video_data.cover_url
            duration = video_data.video.duration if video_data.video else 0
            contents.append(self.create_video(video_url, cover_url, duration))

        stats = video_data.statistics

        # 构建作者
        author = self.create_author(
            name=video_data.author.nickname, avatar_url=video_data.author.avatar_url
        )
        comments = [
            self.create_comment(
                author=self.create_author(
                    name=comment.user.nickname, avatar_url=comment.user.avatar_url
                ),
                content=[comment.text],
                timestamp=comment.createTime,
                stats=self.create_stats(
                    like_count=format_num(comment.digg_count),
                    comment_count=format_num(comment.reply_comment_total),
                ),
                location=comment.ip_label,
            )
            for comment in data.comment_list.comments
        ]
        return self.result(
            title=video_data.desc,
            author=author,
            content=contents,
            stats=self.create_stats(
                like_count=format_num(stats.digg_count),
                comment_count=format_num(stats.comment_count),
                share_count=format_num(stats.share_count),
                collect_count=format_num(stats.collect_count),
            ),
            timestamp=video_data.create_time,
            comments=comments,
        )
