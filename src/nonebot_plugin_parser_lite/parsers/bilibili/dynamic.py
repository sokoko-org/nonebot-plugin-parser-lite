from __future__ import annotations

from typing import Any

from msgspec import Struct, convert

from ...creator import Creator
from ...data import ContentItem


class AuthorInfo(Struct):
    """作者信息"""

    name: str
    face: str
    mid: int
    pub_time: str
    pub_ts: int
    views_text: str | None = None


class VideoArchive(Struct):
    """视频信息"""

    aid: str
    bvid: str
    title: str
    desc: str
    cover: str


class OpusImage(Struct):
    """图文动态图片信息"""

    url: str
    live_url: str | None = None
    """iPhone Live Photo 视频流（如果有）"""


class OpusSummary(Struct):
    """图文动态摘要"""

    text: str
    rich_text_nodes: list[dict[str, Any]]


class OpusContent(Struct):
    """图文动态内容"""

    jump_url: str
    pics: list[OpusImage]
    summary: OpusSummary
    title: str | None = None


class DynamicMajor(Struct):
    """动态主要内容 (Major)"""

    type: str | None = None
    archive: VideoArchive | None = None
    opus: OpusContent | None = None
    desc: OpusSummary | None = None
    draw: dict[str, Any] | None = None

    @property
    def title(self) -> str | None:
        """获取标题"""
        if self.type == "MAJOR_TYPE_ARCHIVE" and self.archive:
            return self.archive.title
        elif self.type == "MAJOR_TYPE_OPUS" and self.opus:
            return self.opus.title
        return None

    @property
    def text(self) -> str | None:
        """获取文本内容"""
        if self.type == "MAJOR_TYPE_ARCHIVE" and self.archive:
            return self.archive.desc
        elif self.type == "MAJOR_TYPE_OPUS" and self.opus:
            return self.opus.summary.text
        elif self.desc:
            return self.desc.text
        return None

    @property
    def rich_text_nodes(self) -> list[dict[str, Any]]:
        """获取富文本节点"""
        if self.type == "MAJOR_TYPE_OPUS" and self.opus:
            return self.opus.summary.rich_text_nodes
        elif self.desc:
            return self.desc.rich_text_nodes
        return []


    @property
    def medias(self) -> list[ContentItem]:
        """
        获取媒体资源列表（图片 + Live Photo）
        说明:
            - 对于 opus.pics:
                - 如果有 live_url -> 视为 Live Photo
                - 否则 -> 普通图片
            - 对于 draw.pictures:
                - 当前只有普通图片（没有 live）
        """
        items: list[ContentItem] = []

        # 优先处理 opus 图文里的图片 / livephoto
        if self.type == "MAJOR_TYPE_OPUS" and self.opus:
            for pic in self.opus.pics:
                if pic.live_url:
                    items.append(
                        Creator.live_photo(video_url=pic.live_url, image_url=pic.url)
                    )
                else:
                    items.append(Creator.image(url=pic.url))

        # draw 类型图片动态
        if self.type == "MAJOR_TYPE_DRAW" and self.draw:
            pictures = self.draw.get("pictures", [])
            for pic in pictures:
                if img_src := pic.get("img_src"):
                    items.append(Creator.image(url=img_src))

        # 视频封面作为普通图片补充（如果前面没有任何媒体）
        if not items and self.type == "MAJOR_TYPE_ARCHIVE" and self.archive:
            if cover := self.archive.cover:
                items.append(Creator.image(url=cover))

        return items


class DynamicModule(Struct):
    """动态模块"""

    module_author: AuthorInfo
    module_dynamic: dict[str, Any] | None = None
    module_stat: dict[str, Any] | None = None

    @property
    def author_name(self) -> str:
        """获取作者名称"""
        return self.module_author.name

    @property
    def author_face(self) -> str:
        """获取作者头像URL"""
        return self.module_author.face

    @property
    def pub_ts(self) -> int:
        """获取发布时间戳"""
        return self.module_author.pub_ts

    @property
    def major_info(self) -> dict[str, Any] | None:
        """获取主要内容信息"""
        if self.module_dynamic:
            if major := self.module_dynamic.get("major"):
                return major
            # 转发类型动态没有 major
            return self.module_dynamic
        return None


class DynamicInfo(Struct):
    """动态信息"""

    id_str: str
    type: str
    visible: bool
    modules: DynamicModule
    basic: dict[str, Any] | None = None
    # 【关键修改】添加 orig 字段以支持转发内容 (递归结构)
    orig: DynamicInfo | None = None

    @property
    def name(self) -> str:
        """获取作者名称"""
        return self.modules.author_name

    @property
    def avatar(self) -> str:
        """获取作者头像URL"""
        return self.modules.author_face

    @property
    def timestamp(self) -> int:
        """获取发布时间戳"""
        return self.modules.pub_ts

    @property
    def title(self) -> str | None:
        """获取标题"""
        if major_info := self.modules.major_info:
            major = convert(major_info, DynamicMajor)
            return major.title
        # 如果是转发动态且没有 major title，可以返回默认值
        return "转发动态" if self.type == "DYNAMIC_TYPE_FORWARD" else None

    @property
    def rich_text_nodes(self) -> list[dict[str, Any]]:
        """获取富文本节点"""
        if self.modules.module_dynamic:
            desc = self.modules.module_dynamic.get("desc")
            if desc and isinstance(desc, dict):
                if rich_text_nodes := desc.get("rich_text_nodes"):
                    return rich_text_nodes
        if major_info := self.modules.major_info:
            major = convert(major_info, DynamicMajor)
            return major.rich_text_nodes
        return []

    @property
    def text(self) -> str | None:
        """获取文本内容"""
        # 【关键修改】优先从 modules.module_dynamic.desc.text 获取
        # 这是用户发布的文字（包括转发时的评论）
        if self.modules.module_dynamic:
            desc = self.modules.module_dynamic.get("desc")
            if desc and isinstance(desc, dict):
                if text_content := desc.get("text"):
                    return text_content

        if major_info := self.modules.major_info:
            major = convert(major_info, DynamicMajor)
            return major.text

        return None

    @property
    def medias(self) -> list[ContentItem]:
        """
        统一获取当前动态的媒体资源（图片 + Live Photo）

        优先从 major 结构中解析（标准路径），
        对于部分老数据 / 特殊分享结构，再从 module_dynamic 兜底
        """
        # 1. 标准 major 结构
        if major_info := self.modules.major_info:
            major = convert(major_info, DynamicMajor)
            if medias := major.medias:
                return medias

        # 2. 处理旧式 / 特殊图文结构：直接从 module_dynamic 中兜底
        if self.type == "DYNAMIC_TYPE_DRAW" and self.modules.module_dynamic:
            dynamic_data = self.modules.module_dynamic
            if isinstance(dynamic_data, dict):
                # 2.1 直接 pics: [{url: ...}]
                if "pics" in dynamic_data:
                    return [
                        Creator.image(url=pic.get("url"))
                        for pic in dynamic_data["pics"]
                        if pic.get("url")
                    ]

                # 2.2 major 下的 pics / draw.pictures
                if "major" in dynamic_data and isinstance(
                    (major := dynamic_data["major"]), dict
                ):
                    if "pics" in major:
                        return [
                            Creator.image(url=pic.get("url"))
                            for pic in major["pics"]
                            if pic.get("url")
                        ]
                    draw = major.get("draw")
                    if isinstance(draw, dict) and "pictures" in draw:
                        return [
                            Creator.image(url=pic.get("img_src"))
                            for pic in draw["pictures"]
                            if pic.get("img_src")
                        ]

        # 3. 转发动态 / 无图动态：不再从 orig 递归取图，交由上游用默认封面兜底
        return []


class DynamicData(Struct):
    """动态项目"""

    item: DynamicInfo
