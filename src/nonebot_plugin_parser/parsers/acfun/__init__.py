import re
from typing import ClassVar

from httpx import AsyncClient

from ..base import (
    DOWNLOADER,
    COMMON_TIMEOUT,
    Platform,
    BaseParser,
    PlatformEnum,
    ParseException,
    handle,
)
from .video import decoder


class AcfunParser(BaseParser):
    # 平台信息
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.ACFUN, display_name="猴山"
    )

    def __init__(self):
        super().__init__()
        self.headers["referer"] = "https://www.acfun.cn/"

    @handle("acfun.cn", r"(?:ac=|/ac)(?P<acid>\d+)")
    async def _parse(self, searched: re.Match[str]):
        acid = int(searched.group("acid"))
        url = f"https://www.acfun.cn/v/ac{acid}"

        video_info = await self.parse_video_info(url)
        author = self.create_author(
            name=video_info.name, avatar_url=video_info.avatar_url
        )

        video_task = DOWNLOADER.download_m3u8_video(
            video_info.m3u8_url,
        )

        video_content = self.create_video(
            video_task,
            cover_url=video_info.coverUrl,
            duration=video_info.duration,
            video_name=f"acfun_{acid}.mp4",
        )

        return self.result(
            title=video_info.title,
            author=author,
            timestamp=video_info.timestamp,
            content=[video_info.text or "", video_content],
        )

    async def parse_video_info(self, url: str):
        """解析acfun链接获取详细信息

        Args:
            url (str): 链接

        Returns:
            video.VideoInfo
        """

        # 拼接查询参数
        url = f"{url}?quickViewId=videoInfo_new&ajaxpipe=1"

        async with AsyncClient(headers=self.headers, timeout=COMMON_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            raw = response.text

        matched = re.search(r"window\.videoInfo =(.*?)</script>", raw)
        if not matched:
            raise ParseException("解析 acfun 视频信息失败")

        raw = str(matched[1])
        raw = re.sub(r'\\{1,4}"', '"', raw)
        raw = raw.replace('"{', "{").replace('}"', "}")
        return decoder.decode(raw)
