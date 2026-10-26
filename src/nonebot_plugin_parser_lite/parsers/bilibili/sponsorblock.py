"""哔哩哔哩空降：查询 SponsorBlock 兼容服务，把标注换算成裁切与消音区间"""

from collections.abc import Iterable
from dataclasses import dataclass
import json
import math
from typing import Any
from urllib.parse import urljoin

from anyio import Path

from ...config import pconfig
from ...download import DOWNLOADER
from ...exception import TipException
from ...utils.ffmpeg import FFmpeg, get_transcode_limit
from ...utils.log import logger

SegmentRange = tuple[float, float]
SegmentRanges = tuple[SegmentRange, ...]


@dataclass(frozen=True, slots=True)
class SponsorSegment:
    """片段信息"""

    start: float
    end: float
    category: str
    action_type: str
    cid: int


def _parse_segment(entry: Any) -> SponsorSegment | None:
    """保留原始标注，区间是否可执行由规划阶段判断"""
    try:
        pair = entry["segment"]
        return SponsorSegment(
            start=pair[0],
            end=pair[1] if len(pair) > 1 else math.nan,
            category=entry["category"].lower(),
            action_type=entry["actionType"].lower(),
            cid=int(entry["cid"]),
        )
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        return None


def _normalize_ranges(
    ranges: Iterable[tuple[float, float]],
    duration: float,
) -> tuple[tuple[float, float], ...]:
    """按规则限制终点、排除无效区间，只合并重叠或相接的区间"""
    clamped: list[SegmentRange] = []
    for start, end in ranges:
        if not isinstance(start, int | float) or isinstance(start, bool):
            continue
        try:
            end = min(end, duration)
            if (
                not math.isfinite(start)
                or not math.isfinite(end)
                or start < 0
                or end <= start
            ):
                continue
        except TypeError:
            continue
        clamped.append((start, end))

    merged: list[list[float]] = []
    for start, end in sorted(clamped):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    return tuple((start, end) for start, end in merged)


class SponsorBlock:
    """单个分 P 的空降结果，统一提供区间、成片时长与整片广告判断

    用 ``await SponsorBlock.query(cid, duration)`` 查询，再通过
    ``await result.apply(path)`` 处理文件
    """

    def __init__(
        self, duration: float, segments: tuple[SponsorSegment, ...] = ()
    ) -> None:
        self.duration = duration
        self.segments = segments
        self.cut_ranges = _normalize_ranges(
            ((s.start, s.end) for s in self.segments if s.action_type == "skip"),
            self.duration,
        )
        self.covers_entire_video = self.cut_ranges == ((0.0, self.duration),)
        self.mute_ranges = _normalize_ranges(
            ((s.start, s.end) for s in self.segments if s.action_type == "mute"),
            self.duration,
        )

    @property
    def removed_duration(self) -> float:
        """实际计划裁掉的秒数"""
        return sum(end - start for start, end in self.cut_ranges)

    @property
    def output_duration(self) -> float:
        return self.duration - self.removed_duration

    @property
    def full_video_categories(self) -> frozenset[str]:
        """整片标签分类，full 不一定是广告，也可能是音乐等其他分类"""
        return frozenset(s.category for s in self.segments if s.action_type == "full")

    @property
    def is_full_video_ad(self) -> bool:
        """广告/自我推广的 full 标签，或广告 skip 区间确实覆盖整片"""
        ad_categories = {"sponsor", "selfpromo"}
        if self.full_video_categories & ad_categories:
            return True
        ad_ranges = _normalize_ranges(
            (
                (s.start, s.end)
                for s in self.segments
                if s.action_type == "skip" and s.category in ad_categories
            ),
            self.duration,
        )
        return ad_ranges == ((0.0, self.duration),)

    @staticmethod
    async def fetch_segments(bvid: str, cid: int) -> list[SponsorSegment]:
        """查询"""
        api_base = pconfig.bsb_api_base
        categories = pconfig.bsb_categories
        if not api_base or not categories:
            return []
        params = {
            "videoID": bvid,
            "cid": cid,
            "categories": json.dumps(categories, separators=(",", ":")),
            "actionTypes": json.dumps(["skip", "mute", "full"], separators=(",", ":")),
        }
        try:
            response = await DOWNLOADER.client.get(
                urljoin(api_base, "api/skipSegments"),
                params=params,
                headers=DOWNLOADER.headers,
            )
        except Exception as e:
            logger.exception(
                f"SponsorBlock 查询失败 cid={cid}: {type(e).__name__}: {e!r}"
            )
            return []

        if response.status_code != 200:
            excerpt = "".join(
                ch
                for ch in response.content[:200].decode("utf-8", "replace")
                if ch.isprintable()
            )
            logger.warning(
                f"SponsorBlock 返回 HTTP {response.status_code}，忽略片段: {excerpt}"
            )
            return []
        try:
            data = response.json()
        except ValueError:
            logger.warning(f"SponsorBlock 返回了非 JSON 内容 cid={cid}，忽略片段")
            return []
        if not isinstance(data, list):
            return []
        return [
            segment
            for entry in data
            if (segment := _parse_segment(entry)) is not None
            and segment.cid == cid
            and segment.category in categories
        ]

    @classmethod
    async def query(cls, bvid: str, cid: int, duration: float) -> "SponsorBlock":
        """查询空降信息"""
        return cls(duration, tuple(await cls.fetch_segments(bvid=bvid, cid=cid)))

    async def apply(self, path: Path) -> Path:
        """应用空降"""
        if self.covers_entire_video:
            raise TipException("空降区间覆盖整条视频，没有可发送的内容")
        if not self.cut_ranges and not self.mute_ranges:
            return path
        try:
            async with get_transcode_limit():
                return await FFmpeg.edit_video(
                    path, cut_ranges=self.cut_ranges, mute_ranges=self.mute_ranges
                )
        except Exception as e:
            logger.exception(f"空降裁切失败，改用原始文件: {type(e).__name__}: {e!r}")
        return path
