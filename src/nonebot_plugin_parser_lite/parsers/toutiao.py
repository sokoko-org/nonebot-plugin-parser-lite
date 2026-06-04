import json
from typing import ClassVar

from nonebot import logger

from .base import (
    BaseParser,
    MatchWithParams,
    ParseException,
    PlatformEnum,
    handle,
)
from .data import MediaContent, Platform


class ToutiaoParser(BaseParser):
    # 平台信息
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.TOUTIAO, display_name="今日头条"
    )

    @handle(
        "ixigua.com",
        r"https?://[^\s]*?(?:toutiao\.com|ixigua\.com)/(?:is|video)/[^\s/]+/?",
    )
    @handle(
        "toutiao.com",
        r"https?://[^\s]*?(?:toutiao\.com|ixigua\.com)/(?:is|video)/[^\s/]+/?",
    )
    async def _parse_toutiao_share(self, searched: MatchWithParams):
        """解析今日头条分享链接"""
        share_url = searched[0]
        logger.debug(f"触发今日头条解析: {share_url}")

        # 使用API解析
        resp = await self.httpx.get(
            "https://api.bugpk.com/api/toutiao", params={"url": share_url}
        )
        resp.raise_for_status()

        # 检查响应内容
        if not resp.content:
            raise ParseException("今日头条接口返回空内容")

        try:
            # 获取原始响应文本
            response_text = resp.text

            # 提取JSON部分 - 找到第一个{和最后一个}，忽略前面的HTML警告
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

            if json_start != -1 and json_end != -1:
                # 提取纯JSON字符串
                pure_json = response_text[json_start:json_end]
                data = json.loads(pure_json)
            else:
                # 如果找不到JSON结构，尝试直接解析
                data = resp.json()
        except json.JSONDecodeError as e:
            # 记录响应内容以便调试
            logger.error(f"今日头条接口返回无效JSON: {resp.text[:100]}...")
            raise ParseException(f"今日头条接口返回无效JSON: {e}") from e

        # 检查接口返回状态
        if data.get("code") != 200:
            raise ParseException(f"今日头条接口返回错误: {data.get('msg', '未知错误')}")

        video_data = data.get("data")
        if not video_data or not isinstance(video_data, dict):
            raise ParseException("今日头条接口返回无效数据")

        # 创建视频内容 - 使用get方法安全访问
        video_url = video_data.get("url")
        if not video_url or not video_url.startswith("http"):
            raise ParseException("无效视频URL")

        # 解析封面 - 使用get方法安全访问
        cover_url = video_data.get("cover")

        # 创建视频内容
        video_content = self.create_video(
            video_url,
            cover_url,
            0.0,  # API没有返回时长
        )

        # 构建内容列表
        contents: list[MediaContent | str] = [
            video_data.get("description", ""),
            video_content,
        ]

        # 构建额外信息
        extra = {
            "info": f"作者: {video_data.get('author', '未知作者')}",
            "type": "video",
            "type_tag": "短视频",
            "type_icon": "fa-video",
        }

        # 构建作者信息 - 安全访问字段
        author_name = video_data.get("author", "未知作者")
        author_avatar = video_data.get("avatar")

        return self.result(
            title=video_data.get("title", "无标题"),
            author=self.create_author(name=author_name, avatar_url=author_avatar),
            url=share_url,
            content=contents,
            extra=extra,
        )
