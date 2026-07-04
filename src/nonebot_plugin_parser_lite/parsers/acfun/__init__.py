import re
from typing import ClassVar

from ..base import (
    DOWNLOADER,
    BaseParser,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)
from .video import decoder


class AcfunParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.ACFUN, display_name="ACFUN"
    )

    def __init__(self):
        super().__init__()
        self.headers["referer"] = "https://www.acfun.cn/"
        self.httpx.headers.update(self.headers)

    @handle("acfun.cn", r"(?:ac=|/ac)(?P<acid>\d+)")
    async def _parse(self, searched: MatchWithParams):
        acid = int(searched["acid"])
        url = f"https://www.acfun.cn/v/ac{acid}"

        video_info = await self.parse_video_info(url)
        author = self.create_author(
            name=video_info.name, avatar_url=video_info.avatar_url
        )

        video_content = self.create_video(
            url_or_task=DOWNLOADER.download_m3u8_video(
                url=video_info.m3u8_url, video_name=f"acfun_{acid}.mp4"
            ),
            cover_url=video_info.coverUrl,
            duration=video_info.duration,
            video_name=f"acfun_{acid}.mp4",
        )

        return self.result(
            title=video_info.title,
            author=author,
            timestamp=video_info.timestamp,
            content=[video_info.text or "", video_content],
            url=url,
        )

    async def parse_video_info(self, url: str):
        """解析acfun链接获取详细信息

        :param url: 链接
        """

        # 拼接查询参数
        url = f"{url}?quickViewId=videoInfo_new&ajaxpipe=1"

        response = await self.httpx.get(url)
        response.raise_for_status()
        raw = response.text

        matched = re.search(r"window\.videoInfo =(.*?)</script>", raw)
        if not matched:
            raise ParseException("解析 acfun 视频信息失败")

        raw = str(matched[1])
        raw = re.sub(r'\\{1,4}"', '"', raw)
        raw = raw.replace('"{', "{").replace('}"', "}")
        return decoder.decode(raw)
