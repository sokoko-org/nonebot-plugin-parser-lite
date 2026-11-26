"""解析统计图渲染

统计图同样走主题系统：当前主题提供 ``stats.html.jinja`` 时使用主题模板，
否则回退到内置模板。模板上下文只有 ``data``，结构见 THEME.md「统计图」一节。
"""

from collections.abc import Mapping
from datetime import date, datetime
from math import ceil
from typing import Any, Literal

from ..config import _nickname, pconfig
from ..stats import ParseStatsSummary, StatsCount
from .constants import THEME_SCHEMA_VERSION
from .context import _escape_html
from .image import TEMPLATES_DIR, render_template
from .theme import ThemeDefinition, ThemeManager, get_theme

STATS_TEMPLATE = "stats.html.jinja"
MAX_CHART_BARS = 31
MAX_PLATFORM_ROWS = 12


def _percent(value: int, maximum: int) -> float:
    return round(value * 100 / maximum, 2) if maximum else 0.0


def _rate(count: StatsCount) -> float | None:
    """成功率（0-100），无记录时为 None"""
    return round(count.success * 100 / count.total, 1) if count.total else None


def _count(count: StatsCount, peak: int = 0) -> dict[str, Any]:
    return {
        "total": count.total,
        "success": count.success,
        "failure": count.failure,
        "rate": _rate(count),
        "success_pct": _percent(count.success, peak),
        "failure_pct": _percent(count.failure, peak),
    }


def _bucket_label(start: date, end: date, *, first: bool) -> str:
    if first or start.day == 1 or end != start:
        return start.strftime("%m-%d")
    return str(start.day)


def _chart(summary: ParseStatsSummary) -> dict[str, Any]:
    """把每日数据合并为不超过 MAX_CHART_BARS 根柱子"""
    days = list(summary.daily.items())
    size = max(1, ceil(len(days) / MAX_CHART_BARS))
    buckets: list[tuple[date, date, StatsCount]] = []
    for index in range(0, len(days), size):
        chunk = days[index : index + size]
        count = StatsCount()
        for _, item in chunk:
            count.add(item.success, item.failure)
        buckets.append((chunk[0][0], chunk[-1][0], count))
    peak = max((count.total for *_, count in buckets), default=0)
    label_every = max(1, ceil(len(buckets) / 8))
    return {
        "bucket_days": size,
        "unit": "每日" if size == 1 else f"每柱 {size} 天",
        "bars": [
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "label": _bucket_label(start, end, first=index == 0)
                if index % label_every == 0
                else "",
                **_count(count, peak),
            }
            for index, (start, end, count) in enumerate(buckets)
        ],
    }


def _hourly(summary: ParseStatsSummary) -> list[dict[str, Any]]:
    peak = max((count.total for count in summary.hourly.values()), default=0)
    return [
        {"hour": hour, **_count(count, peak)}
        for hour, count in sorted(summary.hourly.items())
    ]


def _ranking(
    counts: Mapping[str, StatsCount], names: Mapping[str, str], limit: int
) -> list[dict[str, Any]]:
    items: list[tuple[str | None, str, StatsCount]] = [
        (key, names.get(key, key) or "(未知)", count)
        for key, count in list(counts.items())[:limit]
    ]
    if rest := list(counts.values())[limit:]:
        other = StatsCount()
        for count in rest:
            other.add(count.success, count.failure)
        items.append((None, f"其他 {len(rest)} 项", other))
    peak = max((count.total for *_, count in items), default=0)
    return [
        {"id": key, "name": name, **_count(count, peak)} for key, name, count in items
    ]


def build_stats_data(
    summary: ParseStatsSummary,
    *,
    platform_names: Mapping[str, str] | None = None,
    color_scheme: str | None = None,
    theme_id: str | None = None,
) -> dict[str, Any]:
    """生成统计图模板数据（字符串已转义）"""
    names = platform_names or {}
    peak_day, peak = max(
        summary.daily.items(),
        key=lambda item: item[1].total,
        default=(None, StatsCount()),
    )
    is_global = summary.target is None
    data = {
        "schema_version": THEME_SCHEMA_VERSION,
        "theme": color_scheme or get_theme(),
        "theme_id": theme_id or pconfig.render_theme,
        "meta": {
            "bot_name": _nickname,
            "rendering_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "width": 620,
        },
        "stats": {
            "title": "解析统计",
            "days": summary.days,
            "since": summary.since.isoformat(),
            "until": summary.until.isoformat(),
            "scope": {
                "global": is_global,
                "target": summary.target,
                "label": "全部会话" if is_global else summary.target,
            },
            "total": _count(summary.total),
            "average": round(summary.total.total / summary.days, 1),
            "peak": {"date": peak_day.isoformat(), "total": peak.total}
            if peak_day is not None and peak.total
            else None,
            "chart": _chart(summary),
            "hourly": _hourly(summary),
            "platforms": _ranking(summary.platforms, names, MAX_PLATFORM_ROWS),
            "targets": _ranking(summary.targets, {}, pconfig.stats_top_targets)
            if is_global
            else [],
        },
    }
    return _escape_html(data)


async def render_stats_image(
    summary: ParseStatsSummary,
    *,
    platform_names: Mapping[str, str] | None = None,
    color_scheme: str | None = None,
    theme_id: str | None = None,
    theme_definition: ThemeDefinition | None = None,
    image_format: Literal["jpeg", "webp"] | None = None,
) -> tuple[Literal["jpeg", "webp"], bytes]:
    """把统计结果按当前主题渲染为图片，返回实际图片格式和图片内容"""
    theme = theme_definition or await ThemeManager(
        TEMPLATES_DIR, pconfig.theme_dirs
    ).resolve(theme_id or pconfig.render_theme)
    data = build_stats_data(
        summary,
        platform_names=platform_names,
        color_scheme=color_scheme,
        theme_id=theme.id,
    )
    template = await theme.resolve_named_template(STATS_TEMPLATE)
    return await render_template(
        template,
        data,
        color_scheme=data["theme"],
        image_format=image_format or pconfig.render_format,
    )
