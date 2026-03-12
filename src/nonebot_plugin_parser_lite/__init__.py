# ruff: noqa: E402
import asyncio

from nonebot import logger, require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_localstore")

from .utils.common import safe_unlink
from .utils.browser import BROWSER
from .config import Config, pconfig
from .matchers import clear_result_cache
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="链接分享解析 Lite 版",
    description="通用媒体链接分享解析",
    usage="发送支持平台的(BV号/链接/小程序/卡片)即可",
    type="application",
    homepage="https://github.com/molanp/nonebot-plugin-parser-lite",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna", "nonebot_plugin_uninfo"
    ),
    extra={
        "author": "molanp",
        "homepage": "https://github.com/molanp/nonebot-plugin-parser-lite",
        "version": "1.1.0-cefa70",
    },
)


@scheduler.scheduled_job("cron", hour=1, minute=0, id="parser-clean-local-cache")
async def clean_plugin_cache():
    try:
        files = [f for f in pconfig.cache_dir.iterdir() if f.is_file()]
        if not files:
            logger.info("No cache files to clean")
            return

        # 并发删除文件
        tasks = [safe_unlink(file) for file in files]
        await asyncio.gather(*tasks)

        logger.success(f"Successfully cleaned {len(files)} cache files")
    except Exception:
        logger.exception("Error while cleaning cache files")

    # 资源清理完毕后，清理 result 缓存
    clear_result_cache()
    # 定时重启浏览器防止长时间连接造成卡顿
    BROWSER.reconnect()
