"""emoji 样式，字体更新和渲染内存资源"""

import asyncio
import base64
from dataclasses import dataclass
import hashlib
from io import BytesIO
import tarfile
from typing import Literal

from bs4 import BeautifulSoup, Comment
from httpx import HTTPError
from nonebot import logger
import regex
import ujson

from ..download import DOWNLOADER
from ..exception import DownloadException
from ..path import data_dir

EmojiStyle = Literal["system", "twitter", "google"]
FONT_DIR = data_dir / "fonts"
NPM_REGISTRIES = ("https://registry.npmjs.org", "https://registry.npmmirror.com")
FONT_PACKAGES = {
    "twitter": ("twemoji-colr-font", "package/twemoji.woff2"),
    "google": (
        "@fontsource/noto-color-emoji",
        "package/files/noto-color-emoji-emoji-400-normal.woff2",
    ),
}
EMOJI = regex.compile(
    r"(?=\p{Extended_Pictographic}|\p{Regional_Indicator}|[#*0-9]\uFE0F?\u20E3)\X"
)

SYSTEM_EMOJI_FAMILIES = (
    "Apple Color Emoji",
    "Segoe UI Emoji",
    "Noto Color Emoji",
    "Twemoji Mozilla",
)


@dataclass(frozen=True, slots=True)
class EmojiFont:
    css: str
    resources: dict[str, bytes]
    digest: str


@dataclass(frozen=True, slots=True)
class FontRelease:
    version: str
    urls: tuple[str, ...]
    integrity: str


_FONTS: dict[str, EmojiFont | None] = {}
_FONT_TASKS: dict[str, asyncio.Task[EmojiFont | None]] = {}


def _make_font(provider: str, data: bytes) -> EmojiFont:
    digest = hashlib.sha256(data).hexdigest()
    url = f"https://parser-lite.invalid/fonts/{provider}-{digest}.woff2"
    css = f'@font-face{{font-family:ParserEmoji;src:url("{url}");font-weight:400}}'
    return EmojiFont(css, {url: data}, digest)


async def _load_cached_font(provider: str) -> tuple[EmojiFont, str] | None:
    manifest = FONT_DIR / f"{provider}.json"
    if not await manifest.is_file():
        return None
    metadata = ujson.loads(await manifest.read_text(encoding="utf-8"))
    data = await (FONT_DIR / metadata["file"]).read_bytes()
    font = _make_font(provider, data)
    if font.digest != metadata["sha256"]:
        raise ValueError("本地字体内容与摘要不符")
    return font, metadata["version"]


async def _save_font(provider: str, version: str, data: bytes, digest: str) -> None:
    await FONT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{provider}-{version}.woff2"
    metadata = ujson.dumps({"version": version, "file": filename, "sha256": digest})
    for target, content in (
        (FONT_DIR / filename, data),
        (FONT_DIR / f"{provider}.json", metadata.encode()),
    ):
        temporary = target.with_name(f"{target.name}.tmp")
        await temporary.write_bytes(content)
        await temporary.replace(target)
    async for previous in FONT_DIR.glob(f"{provider}-*.woff2"):
        if previous.name != filename:
            try:
                await previous.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(f"清理旧 emoji 字体失败: {previous}: {exc}")


async def _get(urls: tuple[str, ...]) -> bytes:
    errors = []
    for url in urls:
        try:
            async with asyncio.timeout(15):
                return await DOWNLOADER.content(url)
        except (DownloadException, HTTPError, TimeoutError) as exc:
            errors.append(f"{url}: {exc}")
    raise DownloadException("; ".join(errors))


async def _latest_release(provider: str) -> FontRelease:
    package, _ = FONT_PACKAGES[provider]

    metadata = ujson.loads(
        await _get(tuple(f"{registry}/{package}/latest" for registry in NPM_REGISTRIES))
    )
    version = metadata["version"]
    return FontRelease(
        version,
        tuple(
            f"{registry}/{package}/-/{package.rsplit('/', 1)[-1]}-{version}.tgz"
            for registry in reversed(NPM_REGISTRIES)
        ),
        metadata["dist"]["integrity"],
    )


def _extract_font(provider: str, release: FontRelease, data: bytes) -> bytes:
    algorithm, expected = release.integrity.split("-", 1)
    actual = base64.b64encode(hashlib.new(algorithm, data).digest()).decode()
    if actual != expected:
        raise ValueError(f"{provider} 字体包完整性校验失败")
    with tarfile.open(fileobj=BytesIO(data), mode="r:gz") as archive:
        member = archive.extractfile(FONT_PACKAGES[provider][1])
        if member is None:
            raise ValueError(f"{provider} 字体包缺少 WOFF2 字体")
        with member:
            return member.read()


async def _download_font(provider: str, release: FontRelease) -> bytes:
    errors = []
    for url in release.urls:
        try:
            data = await _get((url,))
            return await asyncio.to_thread(_extract_font, provider, release, data)
        except (DownloadException, ValueError, KeyError, tarfile.TarError) as exc:
            errors.append(f"{url}: {exc}")
    raise ValueError("; ".join(errors))


async def _prepare_font(provider: str) -> EmojiFont | None:
    cached = None
    try:
        cached = await _load_cached_font(provider)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning(f"读取 {provider} emoji 字体缓存失败，将重新下载: {exc}")
    try:
        release = await _latest_release(provider)
        if cached is not None and cached[1] == release.version:
            return cached[0]
        data = await _download_font(provider, release)
        font = _make_font(provider, data)
        await _save_font(provider, release.version, data, font.digest)
        logger.info(f"已更新 {provider} emoji 字体: {release.version}")
        return font
    except (DownloadException, OSError, ValueError, KeyError, tarfile.TarError) as exc:
        if cached is not None:
            logger.warning(f"检查或更新 {provider} emoji 字体失败，沿用本地字体: {exc}")
            return cached[0]
        logger.warning(
            f"无法准备 {provider} emoji 字体，请检查 npm 或镜像站连接: {exc}"
        )
        return None


async def ensure_emoji_font(style: EmojiStyle) -> EmojiFont | None:
    """每次启动检查一次版本；并发预热和渲染共享同一任务及结果。"""
    provider = "twitter" if style == "system" else style
    if provider not in _FONTS:
        task = _FONT_TASKS.get(provider)
        if task is None:
            task = asyncio.create_task(_prepare_font(provider))
            _FONT_TASKS[provider] = task
        try:
            _FONTS[provider] = await asyncio.shield(task)
        finally:
            if task.done():
                _FONT_TASKS.pop(provider, None)
    font = _FONTS[provider]
    if font is None and style != "system":
        raise RuntimeError(f"无法准备 {provider} emoji 字体，请检查 npm 或镜像站连接")
    return font


def apply_emoji_font(
    page: BeautifulSoup, font: EmojiFont | None, style: EmojiStyle
) -> None:
    if font is not None:
        stylesheet = page.new_tag("style")
        stylesheet.string = font.css
        (page.head or page).insert(0, stylesheet)
    families = (
        (*SYSTEM_EMOJI_FAMILIES, "ParserEmoji")
        if style == "system"
        else ("ParserEmoji",)
    )
    family_css = ",".join(ujson.dumps(name) for name in families)
    for text in page.find_all(string=True):
        if isinstance(text, Comment) or text.find_parent(
            ["style", "script", "svg", "math", "textarea", "title"]
        ):
            continue
        matches = [
            match for match in EMOJI.finditer(str(text)) if "\ufe0e" not in match[0]
        ]
        if not matches:
            continue
        parts = []
        offset = 0
        for match in matches:
            parts.append(str(text)[offset : match.start()])
            span = page.new_tag("span")
            span["style"] = (
                f"font-family:{family_css}!important;"
                "font-weight:400!important;font-style:normal!important"
            )
            span.string = match[0]
            parts.append(span)
            offset = match.end()
        parts.append(str(text)[offset:])
        text.replace_with(*parts)
