import contextlib
from re import Match
from typing import ClassVar

from httpx import AsyncClient
from nonebot import logger

from .base import (
    BaseParser,
    PlatformEnum,
    ParseException,
    handle,
)
from .data import Platform, ImageContent, MediaContent


class KuWoParser(BaseParser):
    # 平台信息
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.KUWO, display_name="酷我音乐")

    @handle("kuwo.cn", r"https?://[^\s]*?kuwo\.cn/play_detail/\d+")
    async def _parse_kuwo_share(self, searched: Match[str]):
        """解析酷我音乐分享链接"""
        share_url = searched.group(0)
        logger.debug(f"触发酷我音乐解析: {share_url}")

        # 使用API解析
        try:
            async with AsyncClient(verify=False, timeout=self.timeout) as client:
                api_url = "https://api.bugpk.com/api/kuwo"
                params = {"url": share_url}
                resp = await client.get(api_url, params=params)
                resp.raise_for_status()
                data = resp.json()

                # 检查接口返回状态
                if data.get("code") != 200:
                    raise ParseException(f"酷我音乐接口返回错误: {data.get('msg', '未知错误')}")

                music_data = data["data"]
                logger.info(f"酷我音乐解析成功: {music_data['title']} - {music_data['artist']}")

                # 创建音频内容
                audio_url = music_data["music_url"]
                if not audio_url.startswith("http"):
                    raise ParseException("无效音乐URL")

                # 解析时长
                duration = 0.0
                if music_data.get("songTimeMinutes"):
                    # 格式为 "mm:ss"
                    with contextlib.suppress(ValueError):
                        minutes, seconds = map(int, music_data["songTimeMinutes"].split(":"))
                        duration = minutes * 60 + seconds
                # 创建有意义的音频文件名
                audio_name = f"{music_data['title']}-{music_data['artist']}.mp3"
                # 创建音频内容
                audio_content = self.create_audio(audio_url, duration, audio_name=audio_name)
                # 构建文本内容
                text = (
                    f"专辑: {music_data['album']}\n发行时间: {music_data['releaseDate']}"
                    f"\n时长: {music_data['songTimeMinutes']}"
                )
                if music_data.get("lyrics_url"):
                    text += f"\n歌词:\n{music_data['lyrics_url']}"

                # 创建封面图片内容
                contents: list[MediaContent | str] = [text]

                if cover_url := music_data.get("pic"):
                    from ..download import DOWNLOADER

                    cover_content = ImageContent(DOWNLOADER.download_img(cover_url, ext_headers=self.headers))
                    contents.append(cover_content)

                # 添加音频内容到列表
                contents.append(audio_content)

                # 构建额外信息
                extra = {
                    "info": f"时长: {music_data['songTimeMinutes']} | 专辑: {music_data['album']}",
                    "type": "audio",
                    "type_tag": "音乐",
                    "type_icon": "fa-music",
                }

                return self.result(
                    title=music_data["title"],
                    author=self.create_author(music_data["artist"]),
                    url=share_url,
                    content=contents,
                    extra=extra,
                )
        except Exception as e:
            raise ParseException(f"酷我音乐解析失败: {e}") from e
