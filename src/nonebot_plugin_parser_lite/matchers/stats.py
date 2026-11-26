from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Match, UniMessage, on_alconna
from nonebot_plugin_uninfo import ADMIN, Uninfo

from ..config import pconfig
from ..helper import UniHelper
from ..parsers.registry import REGISTRY
from ..render.stats import render_stats_image
from ..stats import query_stats
from .filter import _make_target_key


def platform_names() -> dict[str, str]:
    return {
        str(parser_cls.platform.name): parser_cls.platform.display_name
        for parser_cls in REGISTRY.enabled_classes
    }


async def send_stats(days: Match[int], target: str | None) -> None:
    day_count = days.result if days.available else 7
    max_days = pconfig.stats_max_days
    if not 1 <= day_count <= max_days:
        await UniMessage(f"天数需在 1-{max_days} 之间").send(reply_to=True)
        return
    summary = await query_stats(day_count, target)
    _, image = await render_stats_image(summary, platform_names=platform_names())
    await UniMessage(await UniHelper.img_seg(image)).send(reply_to=True)


@on_alconna(
    Alconna("解析统计", Args["days?", int]),
    rule=to_me(),
    permission=SUPERUSER | ADMIN(),
    block=True,
).handle()
async def handle_stats(session: Uninfo, days: Match[int]):
    """查看当前会话的解析统计"""
    await send_stats(days, _make_target_key(session))


@on_alconna(
    Alconna("全局解析统计", Args["days?", int]),
    rule=to_me(),
    permission=SUPERUSER,
    block=True,
).handle()
async def handle_global_stats(days: Match[int]):
    """查看所有会话的解析统计与会话排行"""
    await send_stats(days, None)
