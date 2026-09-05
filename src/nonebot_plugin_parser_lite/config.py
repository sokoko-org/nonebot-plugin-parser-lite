import json
import os
from typing import Any

from anyio import Path
from pydantic import BaseModel

from .constants import PlatformEnum
from .path import cache_dir as _cache_dir
from .path import config_dir as _config_dir
from .path import data_dir as _data_dir
from .utils.bilibili.video import BiliVideoCodecs, BiliVideoQuality


def parse_hm_to_minutes(value: str) -> int:
    """将 h:m 或 hh:mm 解析为从 0 点起的分钟数"""
    text = value.strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError(f"时间格式错误，应为 h:m，收到: {value!r}")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as e:
        raise ValueError(f"时间格式错误，应为 h:m，收到: {value!r}") from e
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"时间超出有效范围 (0:00-23:59)，收到: {value!r}")
    return hour * 60 + minute


class Config(BaseModel):
    plite_zhihu_ck: str | None = None
    """知乎 cookies"""
    plite_linuxdo_ck: str | None = None
    """linuxdo cookies"""
    plite_need_upload: bool = False
    """是否需要上传音视频文件（兼容旧配置）"""
    plite_need_upload_audio: bool = False
    """是否需要上传音频文件"""
    plite_need_upload_video: bool = False
    """是否需要上传视频文件"""
    plite_use_base64: bool = False
    """是否使用 base64 编码发送图片，音频，视频"""
    plite_max_size: int = 90
    """资源最大大小，默认 90 单位 MB"""
    plite_duration_maximum: int = 480
    """视频/音频最大时长"""
    plite_append_url: bool = False
    """是否在解析结果中添加原始URL"""
    plite_embed_url: bool = False
    """是否在解析结果中添加嵌入式播放链接"""
    plite_append_qrcode: bool = False
    """是否在解析结果中添加原始URL二维码"""
    plite_disabled_platforms: list[PlatformEnum] = []
    """禁用的解析器"""
    plite_blacklist_users: list[str] = []
    """黑名单用户列表，这些用户触发的解析将被忽略"""
    plite_bili_video_codes: list[BiliVideoCodecs] = [
        BiliVideoCodecs.AVC,
        BiliVideoCodecs.AV1,
        BiliVideoCodecs.HEV,
        BiliVideoCodecs.UNKNOWN,
    ]
    """B站视频编码"""
    plite_bili_video_quality: BiliVideoQuality = BiliVideoQuality._1080P
    """B站视频清晰度"""
    plite_need_forward_contents: bool = True
    """是否需要合并转发内容(大于四项时始终转发)"""
    plite_lazy_download: bool = False
    """是否开启懒下载模式，仅在用户请求时才下载视频"""
    plite_lazy_download_tip: bool = False
    """懒下载是否发送命令提示"""
    plite_lazy_download_timeout: int = 30
    """懒下载模式等待命令超时时间"""
    plite_download_command: list[str] = ["xz", "下载"]
    """在懒下载模式中用户请求下载视频时的命令列表"""
    plite_live_photo: bool = True
    """是否使用 ffmpeg 转码 Live Photo"""
    plite_max_comments: int = 5
    """最大评论数量"""
    plite_forward_text_threshold: int = 1000
    """纯文本文本长度阈值，超过此长度的文本将会强制转发(最大4500)"""
    plite_max_retries: int = 3
    """最大下载重试次数"""
    plite_day_range: list[str] = ["6:00", "19:00"]
    """白天时间范围 [开始, 结束]，格式 h:m；范围内为浅色主题，范围外为夜间模式"""
    plite_bili_cdn_region: str = "zh"
    """哔哩哔哩 CDN 地区；zh、en、ja 为内置基础线路"""
    plite_bili_cdn_domain: str | None = None
    """自定义哔哩哔哩 CDN 域名，优先于地区配置"""

    @property
    def nickname(self) -> str:
        """机器人昵称"""
        return _nickname

    @property
    def cache_dir(self) -> Path:
        """插件缓存目录"""
        return _cache_dir

    @property
    def config_dir(self) -> Path:
        """插件配置目录"""
        return _config_dir

    @property
    def data_dir(self) -> Path:
        """插件数据目录"""
        return _data_dir

    @property
    def max_size(self) -> int:
        """资源最大大小(mb)"""
        return self.plite_max_size

    @property
    def duration_maximum(self) -> int:
        """视频/音频最大时长(s)"""
        return self.plite_duration_maximum

    @property
    def disabled_platforms(self) -> list[PlatformEnum]:
        """禁用的解析器"""
        return self.plite_disabled_platforms

    @property
    def bili_video_codes(self) -> list[BiliVideoCodecs]:
        """B站视频编码"""
        return self.plite_bili_video_codes

    @property
    def bili_video_quality(self) -> BiliVideoQuality:
        """B站视频清晰度"""
        return self.plite_bili_video_quality

    @property
    def zhihu_ck(self) -> str | None:
        """知乎 cookies"""
        return self.plite_zhihu_ck

    @property
    def linuxdo_ck(self) -> str | None:
        """linuxdo cookies"""
        return self.plite_linuxdo_ck

    @property
    def need_upload_audio(self) -> bool:
        """是否需要上传音频文件"""
        return self.plite_need_upload_audio or self.plite_need_upload

    @property
    def need_upload_video(self) -> bool:
        """是否需要上传视频文件"""
        return self.plite_need_upload_video or self.plite_need_upload

    @property
    def use_base64(self) -> bool:
        """是否使用 base64 编码发送图片，音频，视频"""
        return self.plite_use_base64

    @property
    def append_url(self) -> bool:
        """是否在解析结果中添加原始URL"""
        return self.plite_append_url

    @property
    def embed_url(self) -> bool:
        """是否在解析结果中添加嵌入式播放链接"""
        return self.plite_embed_url

    @property
    def append_qrcode(self) -> bool:
        """是否在解析结果中添加原始URL二维码"""
        return self.plite_append_qrcode

    @property
    def need_forward_contents(self) -> bool:
        """是否需要合并转发"""
        return self.plite_need_forward_contents

    @property
    def blacklist_users(self) -> list[str]:
        """黑名单用户列表"""
        return self.plite_blacklist_users

    @property
    def download_command(self) -> list[str]:
        """在懒下载模式中用户请求下载视频时的命令列表"""
        return self.plite_download_command

    @property
    def lazy_download(self) -> bool:
        """是否开启懒下载模式"""
        return self.plite_lazy_download

    @property
    def lazy_download_tip(self) -> bool:
        """懒下载是否发送命令提示"""
        return self.plite_lazy_download_tip

    @property
    def lazy_download_timeout(self) -> int:
        """懒下载模式等待命令超时时间"""
        return self.plite_lazy_download_timeout

    @property
    def live_photo(self) -> bool:
        """是否使用 iPhone Live Photo 功能"""
        return self.plite_live_photo

    @property
    def max_comments(self) -> int:
        """最大评论数量"""
        return self.plite_max_comments

    @property
    def forward_text_threshold(self) -> int:
        """纯文本文本长度阈值，超过此长度的文本将会强制转发"""
        return self.plite_forward_text_threshold

    @property
    def max_retries(self) -> int:
        """最大下载重试次数"""
        return self.plite_max_retries

    @property
    def day_range_minutes(self) -> tuple[int, int]:
        """白天时间范围，返回 (开始分钟, 结束分钟)"""
        return (
            parse_hm_to_minutes(self.plite_day_range[0]),
            parse_hm_to_minutes(self.plite_day_range[1]),
        )

    @property
    def bili_cdn_region(self) -> str:
        """哔哩哔哩 CDN 地区"""
        return self.plite_bili_cdn_region

    @property
    def bili_cdn_domain(self) -> str | None:
        """自定义哔哩哔哩 CDN 域名"""
        return self.plite_bili_cdn_domain


# Standalone configuration
def _decode_env_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _config_from_env() -> Config:
    values: dict[str, Any] = {}
    for name in Config.model_fields:
        if (raw := os.getenv(name)) is None:
            raw = os.getenv(name.upper())
        if raw is not None:
            values[name] = _decode_env_value(raw)
    return Config.model_validate(values)


pconfig: Config = _config_from_env()
"""Active standalone configuration."""


class GlobalConfig(BaseModel):
    log_level: str | int = os.getenv("LOG_LEVEL", "INFO")
    nickname: list[str] = [os.getenv("PARSER_LITE_NICKNAME", "parser-lite")]


gconfig = GlobalConfig()
_nickname: str = next(iter(gconfig.nickname), "parser-lite")


def configure(config: Config | None = None, **overrides: Any) -> Config:
    """Update the shared configuration without invalidating imported references."""
    values = (config or pconfig).model_dump()
    values.update(overrides)
    validated = Config.model_validate(values)
    for name, value in validated:
        setattr(pconfig, name, value)
    return pconfig
