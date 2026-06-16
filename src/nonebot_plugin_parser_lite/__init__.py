import traceback

from nonebot import logger, require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_localstore")

from nonebot_plugin_apscheduler import scheduler

from .cache import CacheManager
from .config import Config
from .matchers import clear_result_cache
from .utils.browser import BrowserManager

__plugin_meta__ = PluginMetadata(
    name="链接分享解析 Lite 版",
    description="通用媒体链接分享解析",
    usage="发送支持平台的(BV号/链接/小程序/卡片)即可",
    type="application",
    homepage="https://github.com/sokoko-org/nonebot-plugin-parser-lite",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna", "nonebot_plugin_uninfo"
    ),
    extra={
        "author": "molanp",
        "homepage": "https://github.com/sokoko-org/nonebot-plugin-parser-lite",
        "version": "1.2.5",
        "plugin_type": "NORMAL",
    },
)


@scheduler.scheduled_job("interval", hours=1, id="parser-clean-local-cache")
async def clean_plugin_cache() -> None:
    """周期性清理过期缓存文件，并重置解析状态。"""

    try:
        await CacheManager.clean_expired()
    except Exception:
        logger.exception(f"清理缓存文件时发生异常: {traceback.format_exc()}")

    # 资源清理完毕后，清理 result 缓存并重连浏览器
    clear_result_cache()
    BrowserManager.clear_cache()
    BrowserManager.reconnect()
