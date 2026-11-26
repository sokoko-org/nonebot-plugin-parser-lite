"""emoji 样式，字体更新和渲染内存资源"""

import asyncio
import base64
from collections.abc import Callable, Coroutine, Iterable
import contextlib
from dataclasses import dataclass
from functools import partial
import hashlib
from io import BytesIO
import tarfile
from typing import Final, Literal, TypeVar

from bs4 import BeautifulSoup, Comment, Stylesheet
from httpx import HTTPError
from nonebot import logger
import regex
import ujson

from ..download import DOWNLOADER
from ..download.client import RetryableDownloadError
from ..exception import DownloadException
from ..path import data_dir

EmojiStyle = Literal["system", "twitter", "google"]
T = TypeVar("T")
FONT_DIR = data_dir / "fonts"
LOCAL_FONT_TIMEOUT: Final = 0.7
"""等待本地字体缓存落地的秒数，超时则认为需要联网下载"""
MAX_METADATA_BYTES: Final = 1024 * 1024
MAX_FONT_ARCHIVE_BYTES: Final = 64 * 1024 * 1024
MAX_FONT_BYTES: Final = 32 * 1024 * 1024
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


_FONTS: dict[str, EmojiFont | None] = {}
"""已准备好的字体，纯数据可跨事件循环共享；None 表示本次运行准备失败"""
_TASKS: dict[str, asyncio.Task[None]] = {}
"""进行中的准备/更新任务，结束后自动移除；只在创建它的事件循环中有效"""


def _provider(style: EmojiStyle) -> str:
    return "twitter" if style == "system" else style


def _spawn(key: str, coro: Coroutine[None, None, None]) -> asyncio.Task[None]:
    task = _TASKS[key] = asyncio.create_task(coro)

    def discard(done: asyncio.Task[None]) -> None:
        if _TASKS.get(key) is done:
            del _TASKS[key]

    task.add_done_callback(discard)
    return task


def _make_font(provider: str, data: bytes) -> EmojiFont:
    digest = hashlib.sha256(data).hexdigest()
    url = f"https://parser-lite.invalid/fonts/{provider}-{digest}.woff2"
    css = f'@font-face{{font-family:ParserEmoji;src:url("{url}");font-weight:400}}'
    return EmojiFont(css, {url: data}, digest)


async def _load_cached_font(provider: str) -> tuple[EmojiFont, str] | None:
    """读取本地字体，返回 (字体, 版本)；摘要不符说明写入不完整"""
    manifest = FONT_DIR / f"{provider}.json"
    if not await manifest.is_file():
        return None
    metadata = ujson.loads(await manifest.read_text(encoding="utf-8"))
    font = _make_font(provider, await (FONT_DIR / metadata["file"]).read_bytes())
    if font.digest != metadata["sha256"]:
        raise ValueError("本地字体内容与摘要不符")
    return font, metadata["version"]


async def _save_font(provider: str, version: str, font: EmojiFont) -> None:
    await FONT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{provider}.woff2"
    metadata = {"version": version, "file": filename, "sha256": font.digest}
    (data,) = font.resources.values()
    for name, content in (
        (filename, data),
        (f"{provider}.json", ujson.dumps(metadata).encode()),
    ):
        temporary = FONT_DIR / f"{name}.tmp"
        await temporary.write_bytes(content)
        await temporary.replace(FONT_DIR / name)
    # 旧版本按版本号命名字体文件
    async for legacy in FONT_DIR.glob(f"{provider}-*.woff2"):
        with contextlib.suppress(OSError):
            await legacy.unlink()


async def _get(urls: Iterable[str], max_size: int, parse: Callable[[bytes], T]) -> T:
    """依次尝试各镜像，返回第一个下载并解析成功的结果"""
    errors = []
    for url in urls:
        try:
            async with asyncio.timeout(15):
                data = await DOWNLOADER.content(url, max_size=max_size)
            return await asyncio.to_thread(parse, data)
        except (
            DownloadException,
            RetryableDownloadError,
            HTTPError,
            TimeoutError,
            ValueError,
            KeyError,
            tarfile.TarError,
        ) as exc:
            errors.append(f"{url}: {exc}")
    raise DownloadException("; ".join(errors))


def _parse_release(raw: bytes) -> tuple[str, str]:
    """npm ``latest`` 元数据 -> (版本, 完整性校验值)"""
    metadata = ujson.loads(raw)
    return metadata["version"], metadata["dist"]["integrity"]


def _extract_font(provider: str, integrity: str, data: bytes) -> bytes:
    algorithm, expected = integrity.split("-", 1)
    if base64.b64encode(hashlib.new(algorithm, data).digest()).decode() != expected:
        raise ValueError(f"{provider} 字体包完整性校验失败")
    with tarfile.open(fileobj=BytesIO(data), mode="r|gz") as archive:
        for info in archive:
            if info.name != FONT_PACKAGES[provider][1]:
                continue
            if not info.isfile() or info.size > MAX_FONT_BYTES:
                raise ValueError(
                    f"{provider} 字体类型无效或超过 {MAX_FONT_BYTES} 字节限制"
                )
            if member := archive.extractfile(info):
                with member:
                    return member.read(MAX_FONT_BYTES)
    raise ValueError(f"{provider} 字体包缺少 WOFF2 字体")


async def _fetch_font(provider: str, cached_version: str | None) -> EmojiFont | None:
    """从 npm 获取最新字体；与本地版本相同时返回 None"""
    package = FONT_PACKAGES[provider][0]
    version, integrity = await _get(
        (f"{registry}/{package}/latest" for registry in NPM_REGISTRIES),
        MAX_METADATA_BYTES,
        _parse_release,
    )
    if version == cached_version:
        return None
    tarball = f"{package}/-/{package.rsplit('/', 1)[-1]}-{version}.tgz"
    data = await _get(
        (f"{registry}/{tarball}" for registry in reversed(NPM_REGISTRIES)),
        MAX_FONT_ARCHIVE_BYTES,
        partial(_extract_font, provider, integrity),
    )
    font = _make_font(provider, data)
    await _save_font(provider, version, font)
    logger.info(f"已更新 {provider} emoji 字体: {version}")
    return font


async def _update_font(provider: str, cached_version: str | None) -> None:
    try:
        if font := await _fetch_font(provider, cached_version):
            _FONTS[provider] = font
    except (DownloadException, OSError) as exc:
        logger.warning(
            f"无法获取 {provider} emoji 字体，请检查 npm 或镜像站连接: {exc}"
        )


async def _prepare_font(provider: str) -> None:
    """本地字体可用时立即生效，版本检查放到后台；否则联网下载"""
    try:
        cached = await _load_cached_font(provider)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning(f"读取 {provider} emoji 字体缓存失败，将重新下载: {exc}")
        cached = None
    if cached is None:
        await _update_font(provider, None)
        _FONTS.setdefault(provider, None)
    else:
        _FONTS[provider] = cached[0]
        _spawn(f"{provider}:update", _update_font(provider, cached[1]))


def _start(provider: str) -> asyncio.Task[None]:
    """返回当前事件循环中的准备任务；其他事件循环留下的任务不能 await，直接重建"""
    task = _TASKS.get(provider)
    if task is None or task.get_loop() is not asyncio.get_running_loop():
        task = _spawn(provider, _prepare_font(provider))
    return task


def warmup_emoji_font(style: EmojiStyle) -> None:
    """启动字体准备；版本检查每次进程启动一次"""
    if _provider(style) not in _FONTS:
        _start(_provider(style))


async def shutdown_emoji_fonts() -> None:
    """停止当前事件循环中的字体任务；已加载的字体保留"""
    loop = asyncio.get_running_loop()
    tasks = [task for task in _TASKS.values() if task.get_loop() is loop]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def ensure_emoji_font(style: EmojiStyle) -> EmojiFont | None:
    """返回可用字体；并发的预热与渲染共享同一准备任务

    ``system`` 样式下字体只是系统 emoji 之外的兜底：本地字体读取很快，
    需要联网下载时不等待，直接用系统字族渲染这一张图
    """
    provider = _provider(style)
    if provider not in _FONTS:
        task = asyncio.shield(_start(provider))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(
                task, LOCAL_FONT_TIMEOUT if style == "system" else None
            )
    font = _FONTS.get(provider)
    if font is None and style != "system":
        raise RuntimeError(f"无法准备 {provider} emoji 字体，请检查 npm 或镜像站连接")
    return font


def apply_emoji_font(
    page: BeautifulSoup, font: EmojiFont | None, style: EmojiStyle
) -> None:
    if font is not None:
        stylesheet = page.new_tag("style")
        # 须与解析出的 <style> 同类型，否则 get_text() 读不到，后续改写会清空它
        stylesheet.string = Stylesheet(font.css)
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
