"""使用 DrissionPage 启动浏览器，优先使用系统/Playwright/Puppeteer 已安装的内核."""

import asyncio
import contextlib
import os
import platform

from anyio import Path
from DrissionPage import Chromium, ChromiumOptions
from DrissionPage._units.listener import DataPacket as DataPacket
from nonebot import get_driver
from nonebot.log import logger

from ..config import pconfig

system = platform.system()
driver = get_driver()


class BrowserManager:
    BROWSER: Chromium | None = None
    _init_lock: asyncio.Lock = asyncio.Lock()
    _last_used: float | None = None
    _idle_timeout: float = 60 * 30
    """浏览器空闲超时时间(s)"""
    _idle_task: asyncio.Task[None] | None = None

    @staticmethod
    async def _find_browser_from_system() -> str:
        """从系统默认安装位置寻找浏览器."""
        if system == "Darwin":
            mac_paths = (
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            )
            for path in mac_paths:
                if await Path(path).is_file():
                    return path
        elif system == "Windows":
            import winreg

            paths = (
                r"SOFTWARE\Clients\StartMenuInternet\Google Chrome\DefaultIcon",
                r"SOFTWARE\Clients\StartMenuInternet\Microsoft Edge\DefaultIcon",
            )
            for path in paths:
                with contextlib.suppress(FileNotFoundError):
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
                    value, _ = winreg.QueryValueEx(key, "")
                    # DefaultIcon 的值通常形如 "C:\\...\\chrome.exe,0"
                    return value.split(",")[0]
        return ""

    @staticmethod
    async def _find_browser_from_playwright() -> str:
        """从 ms-playwright 默认目录寻找 Chromium 可执行文件"""
        if browser_path := os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
            base = Path(browser_path)
        else:
            home = await Path.home()
            if system == "Darwin":
                base = home / "Library" / "Caches" / "ms-playwright"
            elif system == "Windows":
                base = home / "AppData" / "Local" / "ms-playwright"
            else:
                base = home / ".cache" / "ms-playwright"
        if not await base.is_dir():
            return ""

        chromium_dirs = sorted([p async for p in base.glob("chromium-*")], reverse=True)
        for chromium_dir in chromium_dirs:
            if not await chromium_dir.is_dir():
                continue

            if system == "Windows":
                # 任意 chrome-win*/chrome.exe
                exe_candidates = [
                    p async for p in chromium_dir.glob("chrome-win*/chrome.exe")
                ]
            elif system == "Darwin":
                # 任意 chrome-mac*/Chromium.app
                exe_candidates = [
                    chromium_dir
                    / "chrome-mac"
                    / "Chromium.app"
                    / "Contents"
                    / "MacOS"
                    / "Chromium"
                ]
            else:  # Linux
                # 任意 chrome-linux*/chrome 或 chrome-linux64*/chrome
                exe_candidates = [
                    p async for p in chromium_dir.glob("chrome-linux*/chrome")
                ]

            for exe_path in exe_candidates:
                if await exe_path.is_file():
                    return str(await exe_path.resolve())

        return ""

    @staticmethod
    async def _find_browser_from_puppeteer() -> str:
        """从 Puppeteer 默认目录寻找 Chromium/Chrome."""
        home = await Path.home()
        candidates: list[Path] = []

        if system == "Darwin":
            candidates.append(home / "Library" / "Caches" / "puppeteer")
        elif system == "Windows":
            candidates.append(home / "AppData" / "Local" / "puppeteer")
        else:
            # 常见：~/.cache/puppeteer
            candidates.append(home / ".cache" / "puppeteer")

        target_name = "chrome.exe" if system == "Windows" else "chrome"

        for base in candidates:
            if not await base.is_dir():
                continue

            # Windows / Linux: 查找 chrome.exe / chrome，版本号目录用 rglob 解决
            async for sub in base.rglob(target_name):
                if await sub.is_file():
                    return str(sub)

            # macOS: 查找 Chromium.app
            if system == "Darwin":
                async for app in base.rglob("Chromium.app"):
                    exe = app / "Contents" / "MacOS" / "Chromium"
                    if await exe.is_file():
                        return str(await exe.resolve())

        return ""

    @classmethod
    async def _resolve_browser_path(cls) -> str:
        """按优先级解析浏览器路径."""
        # 1. 显式配置优先
        if pconfig.browser_path:
            return pconfig.browser_path

        # 2. 系统默认安装位置
        if path := await cls._find_browser_from_system():
            return path

        # 3. ms-playwright 默认安装目录
        if path := await cls._find_browser_from_playwright():
            return path

        # 4. Puppeteer 默认安装目录
        if path := await cls._find_browser_from_puppeteer():
            return path

        raise RuntimeError("无法找到可启动的浏览器，请在配置中设置 browser_path")

    @classmethod
    def _touch(cls) -> None:
        """更新最近使用时间戳"""
        cls._last_used = asyncio.get_event_loop().time()

    @classmethod
    async def _idle_watcher(cls) -> None:
        """后台协程：浏览器长时间空闲时自动关闭以节省资源"""
        try:
            while cls.BROWSER is not None:
                await asyncio.sleep(cls._idle_timeout / 2)
                if cls.BROWSER is None or cls._last_used is None:
                    continue
                now = asyncio.get_event_loop().time()
                if now - cls._last_used > cls._idle_timeout:
                    logger.info(
                        f"Browser idle for {int(now - cls._last_used)}s, auto quitting."
                    )
                    cls.quit()
                    break
        finally:
            cls._idle_task = None

    @classmethod
    async def start(cls):
        if cls.BROWSER is not None:
            return
        browser_path = await cls._resolve_browser_path()

        if system == "Linux":
            logger.warning(
                "You are running on Linux. If there is no desktop environment, "
                "please enable headless mode."
            )

        logger.info(f"Launching browser from {browser_path}")
        co = ChromiumOptions()
        co.mute(True)
        # co.no_imgs(True)
        co.auto_port(True)
        co.headless(pconfig.headless)
        co.set_argument("--no-sandbox")
        co.set_argument("--guest")
        co.remove_extensions()
        co.set_browser_path(browser_path)
        cls.BROWSER = Chromium(co)
        cls._touch()
        cls._idle_task = asyncio.create_task(cls._idle_watcher())

    @classmethod
    def reconnect(cls):
        if cls.BROWSER is None:
            return
        cls.BROWSER.reconnect()

    @classmethod
    def clear_cache(cls):
        if cls.BROWSER is None:
            return
        cls.BROWSER.clear_cache(cookies=False)

    @classmethod
    async def ensure_started(cls) -> None:
        """确保浏览器已启动，若未启动则启动（惰性初始化）"""
        if cls.BROWSER is not None:
            cls._touch()
            return
        async with cls._init_lock:
            if cls.BROWSER is None:
                await cls.start()

    @classmethod
    async def new_tab(cls, *args, **kwargs):
        await cls.ensure_started()
        assert cls.BROWSER
        cls._touch()
        return cls.BROWSER.new_tab(*args, **kwargs)

    @classmethod
    def quit(cls):
        if cls.BROWSER is None:
            return
        logger.info("Closing browser launched by Parser Lite")
        try:
            cls.BROWSER.quit(del_data=True)
        except Exception:
            logger.exception("Error while quitting browser")
        finally:
            cls.BROWSER = None
            cls._last_used = None
            if cls._idle_task is not None:
                cls._idle_task.cancel()
                cls._idle_task = None


@driver.on_shutdown
def close_browser():
    BrowserManager.quit()
