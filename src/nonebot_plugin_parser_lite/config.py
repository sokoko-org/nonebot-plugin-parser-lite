from anyio import Path
from nonebot import get_driver, get_plugin_config
import nonebot_plugin_localstore as _store
from pydantic import BaseModel

from .constants import BiliVideoCodecs, BiliVideoQuality, PlatformEnum


class Config(BaseModel):
    plite_bili_ck: str | None = None
    """bilibili cookies"""
    plite_xhs_ck: str | None = None
    """小红书 cookies"""
    plite_need_upload: bool = False
    """是否需要上传音视频文件（兼容旧配置）"""
    plite_need_upload_audio: bool = False
    """是否需要上传音频文件"""
    plite_need_upload_video: bool = False
    """是否需要上传视频文件"""
    plite_use_base64: bool = False
    """是否使用 base64 编码发送图片，音频，视频"""
    plite_max_size: int = 90
    """资源最大大小，默认 100 单位 MB"""
    plite_duration_maximum: int = 480
    """视频/音频最大时长"""
    plite_append_url: bool = False
    """是否在解析结果中添加原始URL"""
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
    ]
    """B站视频编码"""
    plite_bili_video_quality: BiliVideoQuality = BiliVideoQuality._1080P
    """B站视频清晰度"""
    plite_need_forward_contents: bool = True
    """是否需要合并转发内容(大于四项时始终转发)"""
    plite_lazy_download: bool = False
    """是否开启懒下载模式，仅在用户请求时才下载视频"""
    plite_lazy_download_timeout: int = 30
    """懒下载模式等待命令超时时间"""
    plite_download_command: list[str] = ["xz", "下载"]
    """在懒下载模式中用户请求下载视频时的命令列表"""
    plite_browser_path: str = ""
    """浏览器程序路径，如果无法识别浏览器请填写此配置"""
    plite_live_photo: bool = True
    """是否使用 ffmpeg 转码 Live Photo"""
    plite_headless: bool = False
    """是否使用无头浏览器"""
    plite_max_comments: int = 5
    """最大评论数量"""
    plite_forward_text_threshold: int = 300
    """纯文本文本长度阈值，超过此长度的文本将会强制转发"""

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
    def bili_ck(self) -> str | None:
        """bilibili cookies"""
        return self.plite_bili_ck

    @property
    def xhs_ck(self) -> str | None:
        """小红书 cookies"""
        return self.plite_xhs_ck

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
    def append_qrcode(self) -> bool:
        """是否在解析结果中添加原始URL二维码"""
        return self.plite_append_qrcode

    @property
    def need_forward_contents(self) -> bool:
        """是否需要转发原文内容"""
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
    def lazy_download_timeout(self) -> int:
        """懒下载模式等待命令超时时间"""
        return self.plite_lazy_download_timeout

    @property
    def browser_path(self) -> str:
        """浏览器程序路径"""
        return self.plite_browser_path

    @property
    def live_photo(self) -> bool:
        """是否使用 iPhone Live Photo 功能"""
        return self.plite_live_photo

    @property
    def headless(self) -> bool:
        """是否无头模式"""
        return self.plite_headless

    @property
    def max_comments(self) -> int:
        """最大评论数量"""
        return self.plite_max_comments

    @property
    def forward_text_threshold(self) -> int:
        """纯文本文本长度阈值，超过此长度的文本将会强制转发"""
        return self.plite_forward_text_threshold


# 初始化配置实例
_driver = get_driver()
_cache_dir: Path = Path(_store.get_plugin_cache_dir())
_config_dir: Path = Path(_store.get_plugin_config_dir())
_data_dir: Path = Path(_store.get_plugin_data_dir())
pconfig: Config = get_plugin_config(Config)
"""插件配置"""
gconfig = _driver.config
"""全局配置"""
_nickname: str = next(iter(gconfig.nickname), "nonebot-plugin-parser")
"""机器人昵称"""
