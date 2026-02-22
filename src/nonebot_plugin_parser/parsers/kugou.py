import re
import json
import contextlib
from re import Match
from typing import ClassVar
from difflib import SequenceMatcher

from httpx import AsyncClient

from .base import (
    BaseParser,
    PlatformEnum,
    ParseException,
    handle,
)
from .data import Platform, ImageContent, MediaContent
from ..config import pconfig
from ..constants import COMMON_HEADER


class KuGouParser(BaseParser):
    # 平台信息
    platform: ClassVar[Platform] = Platform(name=PlatformEnum.KUGOU, display_name="酷狗音乐")

    async def search_songs(self, title: str, n: int | None = None) -> list:
        """搜索歌曲函数"""
        from httpx import AsyncClient

        # 检查kugou_lzkey是否已配置
        if not pconfig.kugou_lzkey:
            raise ParseException("酷狗音乐API密钥未配置，请在配置文件中设置parser_kugou_lzkey")

        if n is None:
            api_url = (
                f"https://sdkapi.hhlqilongzhu.cn/api/dgMusic_kugou/?key={pconfig.kugou_lzkey}&msg={title}&type=json"
            )
        else:
            api_url = f"https://sdkapi.hhlqilongzhu.cn/api/dgMusic_kugou/?key={pconfig.kugou_lzkey}&msg={title}&type=json&n={n}"

        headers = COMMON_HEADER.copy()
        async with AsyncClient(headers=headers, verify=False, timeout=self.timeout) as client:
            response = await client.get(api_url)
            if response.status_code != 200:
                raise ParseException(f"歌曲搜索接口异常: HTTP {response.status_code}")

            result = response.json()

            # 处理不同结构的API响应
            if "data" in result:
                return result["data"]  # 新格式: 包含data列表
            elif "title" in result:
                return [result]  # 旧格式: 单首歌曲直接返回
            else:
                raise ParseException("接口返回数据格式未知")

    def _extract_embedded_info(self, html_text: str) -> dict:
        """提取页面内嵌的歌曲信息"""
        if smarty_match := re.search(r"var dataFromSmarty\s*=\s*(\[.*?\]),", html_text, re.DOTALL):
            with contextlib.suppress(json.JSONDecodeError):
                smarty_data = json.loads(smarty_match[1])
                if isinstance(smarty_data, list) and smarty_data:
                    return {
                        "hash": smarty_data[0].get("hash", "").upper(),
                        "title": smarty_data[0].get("song_name", ""),
                        "author": smarty_data[0].get("author_name", ""),
                        "duration": smarty_data[0].get("timelength", 0),
                    }
        return {}

    def _clean_search_title(self, title: str) -> str:
        """清理搜索标题，只保留字母、数字和汉字（不含任何连接符）"""
        # 只保留字母(a-zA-Z)、数字(0-9)和汉字(\u4e00-\u9fa5)
        return re.sub(r"[^\w\u4e00-\u9fa5]", "", title)

    @handle(
        "kugou.com",
        r"https?://[^\s]*?kugou\.com.*?(?:/share/[a-zA-Z0-9]+\.html|(?:id|chain)=[a-zA-Z0-9]+)",
    )
    async def _parse_kugou_share(self, searched: Match[str]):
        """解析酷狗分享链接"""
        share_url = searched.group(0)
        # 获取分享页HTML
        headers = COMMON_HEADER.copy()
        async with AsyncClient(headers=headers, verify=False, timeout=self.timeout) as client:
            response = await client.get(share_url)
            response.raise_for_status()
            html_text = response.text

            # 提取内嵌歌曲信息
            embedded_info = self._extract_embedded_info(html_text)

            # 提取页面标题
            title_match = re.search(r"<title>(.+?)_(.+?)_高音质在线", html_text)
            if not title_match:
                raise ParseException("无法从分享页提取歌曲标题")

            page_title = title_match[1].strip()
            page_author = title_match[2].strip()
            search_title = f"{page_title} - {page_author}"

            search_title_clean = self._clean_search_title(search_title)
            page_title_clean = self._clean_search_title(page_title)

            # 搜索歌曲
            try:
                songs = await self.search_songs(search_title_clean)
            except Exception:
                try:
                    songs = await self.search_songs(page_title_clean)
                except Exception as e:
                    raise ParseException(f"使用标题二次搜索失败: {e}") from e

            if not songs:
                raise ParseException("未搜索到相关歌曲")

            # 匹配最佳歌曲
            best_match = None
            best_score = 0

            # 计算匹配分数

            for song in songs:
                # 1. 优先匹配内嵌hash
                if embedded_info and "hash" in embedded_info and song.get("hash", "").upper() == embedded_info["hash"]:
                    best_match = song
                    break

                # 2. 计算标题相似度
                title_similarity = SequenceMatcher(
                    None, str(song.get("title", "")).lower(), str(page_title).lower()
                ).ratio()

                # 3. 计算作者相似度
                author_similarity = SequenceMatcher(
                    None, str(song.get("singer", "")).lower(), str(page_author).lower()
                ).ratio()

                # 综合评分 = 标题相似度 * 0.6 + 作者相似度 * 0.4
                total_score = title_similarity * 0.6 + author_similarity * 0.4

                if total_score > best_score:
                    best_score = total_score
                    best_match = song

            # 检查匹配结果
            if not best_match:
                best_match = songs[0]  # 默认选择第一首

            # 获取最佳匹配歌曲数据
            _id = best_match.get("n", 1)

            try:
                song_info = await self.search_songs(search_title_clean, n=_id)
            except Exception as e:
                raise ParseException(f"歌曲信息获取失败: {e}") from e

            # 确保song_info是列表
            if not isinstance(song_info, list):
                song_info = [song_info]

            if not song_info:
                raise ParseException("未获取到歌曲详细信息")

            song_details = song_info[0]

            # 创建音频内容
            audio_url = song_details.get("music_url", "")
            if not audio_url:
                raise ParseException("未找到音频资源")

            # 创建有意义的音频文件名
            audio_name = f"{song_details.get('title', 'unknown')}-{song_details.get('singer', 'unknown')}.mp3"

            audio_content = self.create_audio(audio_url, float(song_details.get("duration", 0)), audio_name=audio_name)
            # 构建歌词文本
            lyric = song_details.get("lyrics", "")
            text = f"歌词:\n{lyric}" if lyric else ""

            # 创建封面图片内容
            cover_url = song_details.get("cover", "")
            contents: list[MediaContent | str] = [text]

            if cover_url:
                from ..download import DOWNLOADER

                cover_content = ImageContent(DOWNLOADER.download_img(cover_url, ext_headers=self.headers))
                contents.append(cover_content)

            contents.append(audio_content)

            # 构建链接
            hash_value = best_match.get("hash", "")
            link = song_details.get("link", f"https://www.kugou.com/song/#hash={hash_value}")

            # 构建额外信息
            extra = {
                "info": f"时长: {int(float(song_details.get('duration', 0)) // 60)}"
                f":{int(float(song_details.get('duration', 0)) % 60):02d}",
                "type": "audio",
                "type_tag": "音乐",
                "type_icon": "fa-music",
            }

            return self.result(
                title=song_details.get("title", page_title),
                author=self.create_author(song_details.get("singer", page_author)),
                url=link,
                content=contents,
                extra=extra,
            )
