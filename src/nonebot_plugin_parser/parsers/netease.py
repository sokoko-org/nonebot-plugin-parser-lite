import re
from re import Match
from typing import ClassVar

from ..utils.http_utils import get_async_client
from nonebot import logger

from .base import (
    BaseParser,
    PlatformEnum,
    ParseException,
    handle,
)
from .data import Platform, MediaContent


class NCMParser(BaseParser):
    # 平台信息
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.NETEASE, display_name="网易云音乐"
    )

    def __init__(self):
        super().__init__()
        self.short_url_pattern = re.compile(r"(http:|https:)//163cn\.tv/([a-zA-Z0-9]+)")

    async def _get_redirect_url(self, url: str) -> str:
        """获取重定向后的URL"""

        async with get_async_client(follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return str(response.url)

    async def parse_ncm(self, ncm_url: str) -> dict:
        """解析网易云音乐链接"""
        # 处理短链接
        if matched := self.short_url_pattern.search(ncm_url):
            ncm_url = matched.group(0)
            ncm_url = await self._get_redirect_url(ncm_url)

        # 获取网易云歌曲id
        matched = re.search(r"(?:\?|&)id=(\d+)", ncm_url) or re.search(
            r"song/(\d+)", ncm_url
        )

        if not matched:
            raise ParseException(f"无效网易云链接: {ncm_url}")

        ncm_id = matched.group(1)
        logger.info(f"成功提取ID: {ncm_id} 来自 {ncm_url}")

        # 使用新API解析
        try:
            async with get_async_client() as client:
                api_url = "https://api.bugpk.com/api/163_music"
                # 使用GET请求，参数包括ids、level和type
                params = {"ids": ncm_id, "level": "standard", "type": "json"}
                resp = await client.get(api_url, params=params)
                resp.raise_for_status()
                data = resp.json()

                # 检查接口返回状态
                if data.get("status") != 200:
                    raise ParseException(f"网易云接口返回错误: {data}")

                logger.info(f"解析成功: {data['name']} - {data['ar_name']}")
                audio_info = f"音质: standard | 大小: {data.get('size', '')}"

                # 提取歌词信息
                lyric = ""
                if data.get("lyric"):
                    lyric = data["lyric"]
                    logger.info(f"找到歌词，长度: {len(lyric)}字符")

                # 成功获取，返回结果
                return {
                    "title": data["name"],
                    "author": data["ar_name"],
                    "audio_info": audio_info,
                    "cover_url": data["pic"],
                    "audio_url": data["url"],
                    "mv_info": {},  # 新API没有返回MV信息
                    "lyric": lyric,
                }
        except Exception as e:
            raise ParseException(f"网易云音乐解析失败: {e}") from e

    @handle("music.163.com", r"https?://[^\s]*?music\.163\.com.*?(?:id=\d+|song/\d+)")
    @handle("163cn.tv", r"https?://[^\s]*?163cn\.tv/[a-zA-Z0-9]+")
    async def _parse_netease(self, searched: Match[str]):
        """解析网易云音乐分享链接"""
        share_url = searched.group(0)
        logger.debug(f"触发网易云解析: {share_url}")

        # 解析网易云音乐
        result = await self.parse_ncm(share_url)
        # 构建文本内容
        text = f"{result['audio_info']}"
        if result["lyric"]:
            text += f"\n歌词:\n{result['lyric']}"

        contents: list[MediaContent] = []

        # 创建音频内容
        if result["audio_url"]:
            # 创建有意义的音频文件名
            audio_name = f"{result['title']}-{result['author']}.mp3"
            contents.append(
                self.create_audio(
                    result["audio_url"],
                    0.0,
                    audio_name=audio_name,  # 暂时无法从API获取准确时长
                )
            )

        # 创建封面图片内容

        contents.append(self.create_image(result["cover_url"]))

        # 构建额外信息
        extra = {
            "info": result["audio_info"],
            "lyric": text,
            "type": "audio",
            "type_tag": "音乐",
            "type_icon": "fa-music",
        }

        return self.result(
            title=result["title"],
            author=self.create_author(name=result["author"]),
            url=share_url,
            content=contents,
            extra=extra,
        )
