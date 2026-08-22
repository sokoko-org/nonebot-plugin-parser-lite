import json
from random import choice
import re
from typing import Final

from anyio import Path

from ...path import data_dir
from ..log import logger
from .client import CLIENT

CDN_DATA_URL: Final[str] = "https://kanda-akihito-kun.github.io/ccb/api/cdn.json"
CDN_DATA_PATH: Final[Path] = data_dir / "bilibili_cdn.json"

# 在线列表不可用时仍可使用的稳定官方镜像。
DEFAULT_CDN_DOMAINS: Final[dict[str, tuple[str, ...]]] = {
    "zh": ("upos-sz-mirrorcos.bilivideo.com",),
    "en": ("upos-sz-mirroraliov.bilivideo.com",),
    "ja": ("upos-sz-mirroralib.bilivideo.com",),
}
_HOST_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)
_cdn_domains: dict[str, tuple[str, ...]] = dict(DEFAULT_CDN_DOMAINS)


def _is_bilivideo_domain(domain: str) -> bool:
    domain = domain.lower()
    return domain == "bilivideo.com" or domain.endswith(".bilivideo.com")


def _validate_cdn_data(data: object) -> dict[str, tuple[str, ...]]:
    if not isinstance(data, dict):
        raise ValueError("CDN 数据必须是对象")

    result: dict[str, tuple[str, ...]] = {}
    for region, domains in data.items():
        if not isinstance(region, str) or not region.strip():
            raise ValueError("CDN 地区名称无效")
        if not isinstance(domains, list) or not domains:
            raise ValueError(f"CDN 地区 {region!r} 没有可用域名")

        normalized_domains: list[str] = []
        seen_domains: set[str] = set()
        for domain in domains:
            if not isinstance(domain, str):
                continue
            try:
                normalized_domain = normalize_cdn_domain(domain)
            except ValueError:
                continue
            if normalized_domain not in seen_domains:
                normalized_domains.append(normalized_domain)
                seen_domains.add(normalized_domain)
        if normalized_domains:
            result[region.strip()] = tuple(normalized_domains)

    if not result:
        raise ValueError("CDN 数据为空")
    return result


def normalize_cdn_domain(domain: str) -> str:
    """校验并规范化不含协议、端口或路径的 CDN 域名"""
    normalized_domain = domain.strip().lower()
    if not _HOST_PATTERN.fullmatch(normalized_domain) or not _is_bilivideo_domain(
        normalized_domain
    ):
        raise ValueError(f"无效的 B 站 CDN 域名: {domain!r}")
    return normalized_domain


def _set_cdn_domains(data: object) -> None:
    global _cdn_domains
    _cdn_domains = {**DEFAULT_CDN_DOMAINS, **_validate_cdn_data(data)}


async def load_cdn_domains(path: Path = CDN_DATA_PATH) -> bool:
    """从 data 目录加载 CDN 快照，失败时保留当前列表"""
    if not await path.is_file():
        return False
    try:
        _set_cdn_domains(json.loads(await path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as e:
        logger.warning(f"加载 B 站 CDN 列表失败: {e}")
        return False
    return True


def choose_cdn_domain(region: str) -> str:
    """从指定地区随机选择 CDN；在线地区与基础线路使用同一入口"""
    try:
        return choice(_cdn_domains[region])
    except KeyError:
        available_regions = ", ".join(_cdn_domains)
        raise ValueError(
            f"未知的 B 站 CDN 地区 {region!r}，可选：{available_regions}"
        ) from None


async def update_cdn_domains(path: Path = CDN_DATA_PATH) -> None:
    """下载 CDN 列表并原子更新 data 目录中的快照"""
    response = await CLIENT.get(CDN_DATA_URL)
    response.raise_for_status()
    data = response.json()
    validated_data = _validate_cdn_data(data)

    await path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    await temporary_path.write_text(
        json.dumps(validated_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    await temporary_path.replace(path)
    _set_cdn_domains(data)
    logger.info(
        f"已更新 B 站 CDN 列表: {len(validated_data)} 个地区，"
        f"{sum(map(len, validated_data.values()))} 个域名"
    )
