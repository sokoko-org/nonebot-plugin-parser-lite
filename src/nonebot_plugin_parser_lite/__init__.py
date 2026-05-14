import asyncio
from enum import Enum
import traceback

from nonebot import logger, require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_localstore")

import time

from anyio import Path
import bilibili_api.video
from nonebot_plugin_apscheduler import scheduler


class HookAudioQuality(Enum):
    """
    视频的音频流清晰度枚举

    - _64K: 64K
    - _132K: 132K
    - _192K: 192K
    - HI_RES: Hi-Res 无损
    - DOLBY: 杜比全景声
    """

    _64K = 30216
    _132K = 30232
    DOLBY = 30250
    HI_RES = 30251
    _192K = 30280


bilibili_api.video.AudioQuality = HookAudioQuality


from .config import Config, pconfig
from .matchers import clear_result_cache
from .utils.browser import BROWSER
from .utils.common import safe_unlink

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
        "version": "1.2.3",
    },
)


@scheduler.scheduled_job("interval", hours=1, id="parser-clean-local-cache")
async def clean_plugin_cache() -> None:
    """周期性清理过期缓存文件，并重置解析状态。"""

    try:
        # 保留最近 N 小时内的缓存，默认 1 小时
        reserve_hours: int = 1
        now = time.time()

        if all_files := [
            f async for f in pconfig.cache_dir.iterdir() if await f.is_file()
        ]:
            to_delete: list[Path] = []
            expire_seconds = reserve_hours * 60 * 60
            for f in all_files:
                try:
                    mtime = (await f.stat()).st_mtime
                except OSError:
                    # 拿不到 stat 就直接尝试删除
                    to_delete.append(f)
                    continue

                if now - mtime >= expire_seconds:
                    to_delete.append(f)

            if not to_delete:
                logger.info(
                    f"缓存文件共 {len(all_files)} 个，"
                    f"无早于 {reserve_hours} 小时的文件，本次跳过清理"
                )
            else:
                tasks = [safe_unlink(file) for file in to_delete]
                await asyncio.gather(*tasks)
                logger.success(
                    f"已清理 {len(to_delete)} 个过期缓存文件，"
                    f"保留 {len(all_files) - len(to_delete)} 个"
                )

        else:
            logger.info("未找到需要清理的缓存文件")
    except Exception:
        logger.exception(f"清理缓存文件时发生异常: {traceback.format_exc()}")

    # 资源清理完毕后，清理 result 缓存并重连浏览器
    clear_result_cache()
    BROWSER.reconnect()
