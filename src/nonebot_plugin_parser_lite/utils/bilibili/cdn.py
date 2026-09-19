import re
from typing import Final
from urllib.parse import parse_qs, urlsplit

DEFAULT_CDN_DOMAINS: Final[dict[str, str]] = {
    "zh": "upos-sz-mirrorcos.bilivideo.com",
    "en": "upos-sz-mirroraliov.bilivideo.com",
    "ja": "upos-sz-mirroralib.bilivideo.com",
    "proxy": "proxy-tf-all-ws.bilivideo.com",
}
_HOST_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)
RE_PCDN_HOST = re.compile(
    r"\.mcdn\.bilivideo\.(?:cn|com|net)$|"
    r"\.szbdyd\.com$|"
    r"\.mountaintoys\.cn$|"
    r"\.nexusedgeio\.com$|"
    r"\.ahdohpiechei\.com$|"
    r"^upos-sz-mirror14b\.bilivideo\.com$",
    re.IGNORECASE,
)
RE_PCDN_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
RE_PCDN_QUERY = re.compile(r"(?:^|&)os=mcdn(?:&|$)", re.IGNORECASE)


def normalize_cdn_domain(domain: str) -> str:
    """校验并规范化不含协议、端口或路径的 CDN 域名"""
    normalized_domain = domain.strip().lower()
    is_bilivideo = normalized_domain == "bilivideo.com" or normalized_domain.endswith(
        ".bilivideo.com"
    )
    if not _HOST_PATTERN.fullmatch(normalized_domain) or not is_bilivideo:
        raise ValueError(f"无效的 B 站 CDN 域名: {domain!r}")
    return normalized_domain


def pick_cdn_domain(region: str) -> str:
    """从 B 站 CDN 地区线路中选择域名"""
    try:
        return DEFAULT_CDN_DOMAINS[region]
    except KeyError:
        available_regions = ", ".join(DEFAULT_CDN_DOMAINS)
        raise ValueError(
            f"未知的 B 站 CDN 地区 {region!r}，可选：{available_regions}"
        ) from None


def get_szbdyd_source(url: str) -> str | None:
    """从 szbdyd URL 提取 ``xy_usource`` 源站"""
    try:
        parsed = urlsplit(url if "://" in url or url.startswith("//") else f"//{url}")
        host = (parsed.hostname or "").rstrip(".").lower()
        if not RE_PCDN_HOST.search(host) or not host.endswith(".szbdyd.com"):
            return None
        source = parse_qs(parsed.query).get("xy_usource", [""])[0]
        source = source.strip().split("://", 1)[-1].split("/", 1)[0]
        source = source.rsplit(":", 1)[0].lower()
        return normalize_cdn_domain(source)
    except (ValueError, IndexError):
        return None


def is_pcdn_url(url: str | None) -> bool:
    """
    检测给定 URL 是否为 PCDN / P2P 节点 URL

    :param url: 待检测的 URL 字符串
    :return: 若为 PCDN 地址则返回 True，否则 False
    """
    if not url:
        return False
    value = url.strip()
    if not value:
        return False
    try:
        return _extracted_from_is_pcdn_url_14(value)
    except ValueError:
        return False


# TODO Rename this here and in `is_pcdn_url`
def _extracted_from_is_pcdn_url_14(value):
    parsed = urlsplit(
        value if "://" in value or value.startswith("//") else f"//{value}"
    )
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        return False
    if RE_PCDN_IPV4.fullmatch(host) or RE_PCDN_HOST.search(host):
        return True
    if RE_PCDN_QUERY.search(parsed.query):
        return True
    if parsed.port not in (None, 80, 443):
        return True
    first_label = host.split(".", 1)[0]
    return first_label.startswith("upos-") and "302" in first_label
