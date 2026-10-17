"""哔哩哔哩空降：查询 SponsorBlock 兼容服务，把标注换算成裁切与消音区间"""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
import json
from typing import Any

from anyio import Path

from ...config import pconfig
from ...constants import MIN_KEEP_PIECE_SECONDS
from ...download import DOWNLOADER
from ...utils.ffmpeg import FFmpeg, get_transcode_limit
from ...utils.log import logger

REQUEST_TIMEOUT = 5.0
"""查询超时，免得第三方实例拖慢整条解析链路"""

STALENESS_TOLERANCE = 2.0
"""标注记录的视频时长与实际时长相差多少秒以内还算对得上（上游约定 ±2 秒）"""


SegmentRange = tuple[float, float]
SegmentRanges = tuple[SegmentRange, ...]
RangePlan = tuple[SegmentRanges, SegmentRanges, float]


@dataclass(frozen=True, slots=True)
class SponsorSegment:
    """一条归一化后的片段"""

    start: float
    end: float
    category: str
    action_type: str
    recorded_duration: float | None


def _iter_segment_dicts(payload: Any) -> list[dict[str, Any]]:
    """摊平两种返回形态：裸片段数组与按视频分组的数组"""
    if not isinstance(payload, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        segments = item.get("segments")
        if isinstance(segments, list):
            entries.extend(seg for seg in segments if isinstance(seg, dict))
        elif isinstance(item.get("segment"), list):
            entries.append(item)
    return entries


def _parse_segment(entry: dict[str, Any]) -> SponsorSegment | None:
    pair = entry.get("segment")
    if not isinstance(pair, list | tuple) or len(pair) != 2:
        return None
    try:
        start, end = float(pair[0]), float(pair[1])
    except (TypeError, ValueError):
        return None
    if start < 0 or end <= start:
        return None
    category, action_type = entry.get("category"), entry.get("actionType")
    if not isinstance(category, str) or not isinstance(action_type, str):
        return None
    try:
        recorded = float(entry.get("videoDuration", 0))
    except (TypeError, ValueError):
        recorded = 0.0
    return SponsorSegment(
        start=start,
        end=end,
        category=category.casefold(),
        action_type=action_type.casefold(),
        recorded_duration=recorded if recorded > 0 else None,
    )


async def fetch_segments(
    base_url: str,
    bvid: str,
    cid: str,
    categories: list[str],
) -> list[SponsorSegment]:
    """查询这条视频标记的片段"""
    params = {"videoID": bvid, "cid": cid, "categories": categories}
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            response = await DOWNLOADER.client.get(
                f"{base_url.rstrip('/')}/api/skipSegments",
                params=params,
                headers=DOWNLOADER.headers,
            )
    except Exception as e:
        logger.warning(f"SponsorBlock 查询失败 {bvid}: {type(e).__name__}: {e!r}")
        return []

    if response.status_code != 200:
        logger.warning(f"SponsorBlock 返回 HTTP {response.status_code}，忽略片段")
        return []
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        logger.warning(f"SponsorBlock 返回了非 JSON 内容 {bvid}，忽略片段")
        return []

    segments: list[SponsorSegment] = []
    for entry in _iter_segment_dicts(payload):
        if parsed := _parse_segment(entry):
            segments.append(parsed)
    return segments


def _normalize_ranges(
    ranges: Iterable[tuple[float, float]],
    duration: float,
    min_gap: float = 0.0,
) -> tuple[tuple[float, float], ...]:
    """裁到视频时长内、排序、合并；间隔不超过 min_gap 的碎片也并掉"""
    clamped = sorted(
        (max(0.0, start), min(end, duration))
        for start, end in ranges
        if min(end, duration) > max(0.0, start)
    )

    merged: list[list[float]] = []
    for start, end in clamped:
        if merged and start - merged[-1][1] <= min_gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    if merged:
        if merged[0][0] <= min_gap:
            merged[0][0] = 0.0
        if merged[-1][1] >= duration - min_gap:
            merged[-1][1] = duration
    return tuple((start, end) for start, end in merged)


async def skip_ranges(
    api_base: str,
    categories: list[str],
    bvid: str,
    cid: str,
    duration: float,
) -> RangePlan:
    """取回要裁掉 / 要消音的区间，以及裁掉的总秒数"""
    cuts: list[tuple[float, float]] = []
    mutes: list[tuple[float, float]] = []
    for segment in await fetch_segments(api_base, bvid, cid, categories):
        if segment.category not in categories:
            continue
        recorded = segment.recorded_duration
        if recorded is not None and abs(recorded - duration) > STALENESS_TOLERANCE:
            logger.debug(f"片段分类 {segment.category} 的标注已对不上当前视频，忽略")
            continue
        if segment.action_type == "skip":
            cuts.append((segment.start, segment.end))
        elif segment.action_type == "mute":
            mutes.append((segment.start, segment.end))

    # 并掉太短的碎片，让换算出来的时长就是真正会留下来的时长
    normalized = _normalize_ranges(cuts, duration, MIN_KEEP_PIECE_SECONDS)
    removed = sum(end - start for start, end in normalized)
    if removed >= duration:
        logger.debug("片段几乎覆盖整条视频，放弃裁切")
        return (), _normalize_ranges(mutes, duration), 0.0
    return (
        normalized,
        _normalize_ranges(mutes, duration),
        removed,
    )


async def skip_for_video(bvid: str, cid: int | None, duration: float) -> RangePlan:
    """查询空降标注"""
    api_base = pconfig.bsb_api_base
    categories = pconfig.bsb_categories
    if not api_base or not categories or cid is None or duration <= 0:
        return (), (), 0.0
    return await skip_ranges(api_base, categories, bvid, str(cid), duration)


async def skip_video(
    path: Path,
    cut_ranges: tuple[tuple[float, float], ...],
    mute_ranges: tuple[tuple[float, float], ...],
) -> Path:
    """按标注产出空降后的视频"""
    if not cut_ranges and not mute_ranges:
        return path
    if not await FFmpeg.is_available():
        logger.warning("ffmpeg 不可用，跳过空降裁切")
        return path

    try:
        async with get_transcode_limit():
            return await FFmpeg.edit_video(
                path, cut_ranges=cut_ranges, mute_ranges=mute_ranges
            )
    except Exception as e:
        logger.warning(f"空降裁切失败，改用原始文件: {type(e).__name__}: {e!r}")
    return path
