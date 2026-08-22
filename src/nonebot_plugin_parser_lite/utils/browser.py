"""Small Playwright runtime shared by parsing and rendering."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
import os
import platform
from typing import Any, Literal, Self

from anyio import Path
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from .log import logger

WaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]
ImageType = Literal["jpeg", "png"]
_DEFAULT_TIMEOUT_MS = 30_000
_SYSTEM = platform.system()


async def _which(name: str) -> str:
    extensions = [""]
    if _SYSTEM == "Windows":
        extensions = os.environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(";")
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        for extension in extensions:
            candidate = Path(directory) / f"{name}{extension}"
            if await candidate.is_file():
                return str(candidate)
    logger.debug("PATH 中未找到浏览器可执行文件: %s", name)
    return ""


class BrowserTab:
    def __init__(self, context: BrowserContext, page: Page) -> None:
        self._context = context
        self._page = page
        page.set_default_timeout(_DEFAULT_TIMEOUT_MS)

    @property
    def raw(self) -> Page:
        return self._page

    async def goto(
        self, url: str, *, wait_until: WaitUntil = "domcontentloaded"
    ) -> None:
        await self._page.goto(url, wait_until=wait_until)

    async def content(self) -> str:
        return await self._page.content()

    async def close(self) -> None:
        with suppress(Exception):
            await self._context.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class BrowserManager:
    browser: Browser | None = None
    _playwright: Playwright | None = None
    _start_lock = asyncio.Lock()
    _resolve_lock = asyncio.Lock()
    _browser_path: str = ""
    _browser_path_resolved = False

    @staticmethod
    async def _find_browser_from_system() -> str:
        if _SYSTEM == "Darwin":
            for path in (
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ):
                if await Path(path).is_file():
                    return path
        elif _SYSTEM == "Windows":
            import winreg

            for registry_path in (
                r"SOFTWARE\Clients\StartMenuInternet\Google Chrome\DefaultIcon",
                r"SOFTWARE\Clients\StartMenuInternet\Microsoft Edge\DefaultIcon",
            ):
                with suppress(FileNotFoundError, OSError):
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE, registry_path
                    ) as key:
                        value, _ = winreg.QueryValueEx(key, "")
                        candidate = value.split(",")[0].strip().strip('"')
                        if candidate and await Path(candidate).is_file():
                            return candidate

            for registry_path in (
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            ):
                for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    with suppress(FileNotFoundError, OSError):
                        with winreg.OpenKey(root, registry_path) as key:
                            value, _ = winreg.QueryValueEx(key, "")
                            if value and await Path(value).is_file():
                                return value
        else:
            for name in (
                "google-chrome",
                "google-chrome-stable",
                "chromium",
                "chromium-browser",
                "chrome",
            ):
                if found := await _which(name):
                    return found
            for path in (
                "/usr/bin/google-chrome",
                "/opt/google/chrome/google-chrome",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            ):
                if await Path(path).is_file():
                    return path
        logger.debug("系统浏览器查找失败: platform=%s", _SYSTEM)
        return ""

    @staticmethod
    async def _find_browser_from_playwright() -> str:
        if configured := os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
            base = Path(configured)
        else:
            home = await Path.home()
            if _SYSTEM == "Darwin":
                base = home / "Library" / "Caches" / "ms-playwright"
            elif _SYSTEM == "Windows":
                base = home / "AppData" / "Local" / "ms-playwright"
            else:
                base = home / ".cache" / "ms-playwright"
        if not await base.is_dir():
            logger.debug("Playwright 浏览器缓存目录不存在: %s", base)
            return ""

        chromium_dirs = sorted([p async for p in base.glob("chromium-*")], reverse=True)
        for chromium_dir in chromium_dirs:
            if _SYSTEM == "Windows":
                candidates = [
                    p async for p in chromium_dir.glob("chrome-win*/chrome.exe")
                ]
            elif _SYSTEM == "Darwin":
                candidates = [
                    p / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
                    async for p in chromium_dir.glob("chrome-mac*")
                ]
            else:
                candidates = [
                    p async for p in chromium_dir.glob("chrome-linux*/chrome")
                ]
            for executable in candidates:
                if await executable.is_file():
                    return str(await executable.resolve())
        logger.debug("Playwright 浏览器缓存中未找到 Chromium: %s", base)
        return ""

    @staticmethod
    async def _find_browser_from_puppeteer() -> str:
        home = await Path.home()
        if _SYSTEM == "Darwin":
            bases = [home / "Library" / "Caches" / "puppeteer"]
        elif _SYSTEM == "Windows":
            bases = [home / "AppData" / "Local" / "puppeteer"]
        else:
            bases = [home / ".cache" / "puppeteer"]

        target = "chrome.exe" if _SYSTEM == "Windows" else "chrome"
        for base in bases:
            if not await base.is_dir():
                continue
            async for executable in base.rglob(target):
                if await executable.is_file():
                    return str(await executable.resolve())
            if _SYSTEM == "Darwin":
                async for app in base.rglob("Chromium.app"):
                    executable = app / "Contents" / "MacOS" / "Chromium"
                    if await executable.is_file():
                        return str(await executable.resolve())
        logger.debug("Puppeteer 浏览器缓存中未找到 Chromium: %s", bases)
        return ""

    @classmethod
    async def _resolve_browser_path(cls) -> str:
        if cls._browser_path_resolved:
            return cls._browser_path

        async with cls._resolve_lock:
            if cls._browser_path_resolved:
                return cls._browser_path

            path = await cls._find_browser_from_system()
            if not path:
                path = await cls._find_browser_from_playwright()
            if not path:
                path = await cls._find_browser_from_puppeteer()
            cls._browser_path = path
            cls._browser_path_resolved = True
            if path:
                logger.info("已找到渲染浏览器: %s", path)
            else:
                logger.info("未发现外部浏览器，将使用 Playwright 默认 Chromium")
            return path

    @classmethod
    async def ensure_started(cls) -> None:
        if cls.browser is not None and cls.browser.is_connected():
            return
        async with cls._start_lock:
            if cls.browser is not None and cls.browser.is_connected():
                return
            await cls.quit()
            cls._playwright = await async_playwright().start()
            launch: dict[str, Any] = {"headless": True}
            if browser_path := await cls._resolve_browser_path():
                launch["executable_path"] = browser_path
            cls.browser = await cls._playwright.chromium.launch(**launch)

    @classmethod
    async def new_tab(
        cls,
        url: str | None = None,
        *,
        wait_until: WaitUntil = "domcontentloaded",
        **context_kwargs: Any,
    ) -> BrowserTab:
        await cls.ensure_started()
        assert cls.browser is not None
        context = await cls.browser.new_context(**context_kwargs)
        try:
            page = await context.new_page()
            tab = BrowserTab(context, page)
            if url:
                await tab.goto(url, wait_until=wait_until)
            return tab
        except Exception:
            await context.close()
            raise

    @classmethod
    @asynccontextmanager
    async def open_tab(
        cls,
        url: str | None = None,
        *,
        wait_until: WaitUntil = "domcontentloaded",
        **context_kwargs: Any,
    ) -> AsyncGenerator[BrowserTab]:
        tab = await cls.new_tab(url, wait_until=wait_until, **context_kwargs)
        try:
            yield tab
        finally:
            await tab.close()

    @classmethod
    async def screenshot(
        cls,
        *,
        html: str,
        template_path: str,
        wait: int = 0,
        type: ImageType = "png",
        quality: int | None = None,
        device_scale_factor: float = 2,
        screenshot_timeout: float | None = _DEFAULT_TIMEOUT_MS,
        full_page: bool = True,
        **context_kwargs: Any,
    ) -> bytes:
        if not template_path.startswith("file:"):
            raise ValueError("template_path 必须是 file:// URL")
        context_kwargs["device_scale_factor"] = device_scale_factor
        async with cls.open_tab(**context_kwargs) as tab:
            page = tab.raw
            page.on(
                "console",
                lambda message: logger.debug("浏览器控制台: %s", message.text),
            )
            await page.goto(template_path)
            await page.set_content(html, wait_until="networkidle")
            await page.wait_for_timeout(wait)
            options: dict[str, Any] = {
                "full_page": full_page,
                "type": type,
                "timeout": screenshot_timeout,
            }
            if quality is not None:
                options["quality"] = quality
            return await page.screenshot(**options)

    @classmethod
    async def quit(cls) -> None:
        browser, cls.browser = cls.browser, None
        playwright, cls._playwright = cls._playwright, None
        if browser is not None:
            with suppress(Exception):
                await browser.close()
        if playwright is not None:
            with suppress(Exception):
                await playwright.stop()
