import re
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
from .data import Platform, MediaContent


class QSMusicParser(BaseParser):
    # 平台信息
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.QSMUSIC, display_name="汽水音乐"
    )

    @handle("qishui.douyin.com", r"https?://[^\s]*?qishui\.douyin\.com/s/[a-zA-Z0-9]+/")
    async def _parse_qsmusic_share(self, searched: Match[str]):
        """解析汽水音乐分享链接"""
        share_url = searched.group(0)
        logger.debug(f"触发汽水音乐解析: {share_url}")

        # 使用API解析
        try:
            async with AsyncClient(verify=False, timeout=self.timeout) as client:
                api_url = "https://api.bugpk.com/api/qsmusic"
                params = {"url": share_url}
                resp = await client.get(api_url, params=params)
                resp.raise_for_status()
                data = resp.json()

                # 检查接口返回状态
                if data.get("code") != 200:
                    raise ParseException(f"汽水音乐接口返回错误: {data.get('msg')}")

                music_data = data["data"]
                logger.info(
                    f"汽水音乐解析成功: {music_data['albumname']} - {music_data['artistsname']}"
                )

                # 创建音频内容
                audio_url = music_data["url"]
                if not audio_url.startswith("http"):
                    raise ParseException("无效音乐URL")

                # 创建有意义的音频文件名
                audio_name = (
                    f"{music_data['albumname']}-{music_data['artistsname']}.mp3"
                )

                # 由于API没有返回音频时长，我们设置为0.0
                audio_content = self.create_audio(audio_url, 0.0, audio_name=audio_name)
                # 构建文本内容
                text = f"专辑: {music_data['albumname']}\n音质: {music_data['Format']} | 大小: {music_data['Size']}"
                # 创建封面图片内容（如果有）
                contents: list[MediaContent] = [audio_content]

                # 清理歌词，去除时间标记
                def clean_lyrics(lyrics: str) -> str:
                    # 移除<>中的时间标记
                    return re.sub(r"<[^>]+>", "", lyrics)

                if music_data.get("lyric"):
                    cleaned_lyrics = clean_lyrics(music_data["lyric"])
                    text += f"\n歌词:\n{cleaned_lyrics}"

                # 构建额外信息
                extra = {
                    "info": f"音质: {music_data['Format']} | 大小: {music_data['Size']}",
                    "lyric": text,
                    "type": "audio",
                    "type_tag": "音乐",
                    "type_icon": "fa-music",
                }

                return self.result(
                    title=music_data["albumname"],
                    author=self.create_author(music_data["artistsname"]),
                    url=share_url,
                    content=contents,
                    extra=extra,
                )
        except Exception as e:
            raise ParseException(f"汽水音乐解析失败: {e}")
