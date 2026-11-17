"""从平台图标提取并缓存背景强调色。"""

from collections import defaultdict
from colorsys import hsv_to_rgb, rgb_to_hsv
from functools import lru_cache
from hashlib import blake2s
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

from PIL import Image


def _rgb_string(hue: float, saturation: float = 0.65) -> str:
    return ", ".join(
        str(round(channel * 255)) for channel in hsv_to_rgb(hue, saturation, 0.88)
    )


def _fallback(identity: str, pixels: bytes = b"") -> str:
    digest = blake2s(identity.encode() + pixels, digest_size=2).digest()
    return _rgb_string(int.from_bytes(digest) / 65536)


@lru_cache(maxsize=128)
def _logo_rgb(path: str, mtime_ns: int, size: int, identity: str) -> str:
    # mtime_ns 和 size 参与缓存键，替换图标后自动重新取色。
    try:
        with Image.open(path) as source, source.convert("RGBA") as image:
            image.thumbnail((48, 48))
            fallback = _fallback(identity, image.tobytes())
            buckets: dict[int, list[float]] = defaultdict(lambda: [0.0] * 4)
            visible = 0.0
            chromatic = 0.0
            for red, green, blue, alpha in image.getdata():
                if alpha < 32:
                    continue
                opacity = alpha / 255
                visible += opacity
                hue, saturation, value = rgb_to_hsv(red / 255, green / 255, blue / 255)
                if saturation < 0.2 or value < 0.12:
                    continue
                weight = opacity * saturation
                bucket = buckets[int(hue * 24) % 24]
                bucket[0] += weight
                bucket[1] += red * weight
                bucket[2] += green * weight
                bucket[3] += blue * weight
                chromatic += weight
            if not buckets or chromatic < visible * 0.02:
                return fallback
            dominant = max(buckets.values(), key=lambda bucket: bucket[0])
            if dominant[0] < chromatic * 0.15:
                return fallback  # 杂色图标没有可靠主色，使用稳定的备用配色。
            hue, saturation, _ = rgb_to_hsv(
                *(channel / dominant[0] / 255 for channel in dominant[1:])
            )
            return _rgb_string(hue, min(0.85, max(0.55, saturation)))
    except (OSError, ValueError):
        return _fallback(identity)


def ambient_rgb(logo: str | None, identity: str) -> str:
    """忽略透明和中性像素；黑白、杂色或缺失图标采用稳定备用色。"""
    if logo:
        parsed = urlsplit(logo)
        if parsed.scheme == "file":
            path = url2pathname(parsed.path)
            if parsed.netloc and parsed.netloc != "localhost":
                path = f"//{parsed.netloc}{path}"
            try:
                stat = Path(path).stat()
            except OSError:
                pass
            else:
                return _logo_rgb(path, stat.st_mtime_ns, stat.st_size, identity)
    return _fallback(identity)
