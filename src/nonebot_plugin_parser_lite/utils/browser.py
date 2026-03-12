"""使用 DrissionPage 启动浏览器，优先使用系统/Playwright/Puppeteer 已安装的内核."""

import contextlib
import platform
from pathlib import Path

from DrissionPage import Chromium, ChromiumOptions
from DrissionPage._units.listener import DataPacket as DataPacket

from ..config import pconfig
from nonebot import get_driver

system = platform.system()
driver = get_driver()


def _find_browser_from_system() -> str | None:
    """从系统默认安装位置寻找浏览器."""
    if system == "Darwin":
        mac_paths = (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        )
        for path in mac_paths:
            if Path(path).is_file():
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
    return None


def _find_browser_from_playwright() -> str | None:
    """从 ms-playwright 默认目录寻找 Chromium."""
    home = Path.home()
    if system == "Windows":
        base = home / "AppData" / "Local" / "ms-playwright"
    elif system == "Darwin":
        base = home / "Library" / "Caches" / "ms-playwright"
    else:
        base = home / ".cache" / "ms-playwright"

    candidates = (
        base / "chromium" / "chrome-win" / "chrome.exe",
        base
        / "chromium"
        / "chrome-mac"
        / "Chromium.app"
        / "Contents"
        / "MacOS"
        / "Chromium",
        base / "chromium" / "chrome-linux" / "chrome",
    )
    return next((str(exe) for exe in candidates if exe.is_file()), None)


def _find_browser_from_puppeteer() -> str | None:
    """从 Puppeteer 默认目录寻找 Chromium."""
    home = Path.home()
    if system == "Windows":
        base = home / "AppData" / "Local" / "puppeteer"
    elif system == "Darwin":
        base = home / "Library" / "Caches" / "puppeteer"
    else:
        base = home / ".cache" / "puppeteer"

    if not base.is_dir():
        return None

    # Windows / Linux: 查找 chrome.exe / chrome
    target_name = "chrome.exe" if system == "Windows" else "chrome"
    for sub in base.rglob(target_name):
        if sub.is_file():
            return str(sub)

    # macOS: 查找 Chromium.app
    if system == "Darwin":
        for app in base.rglob("Chromium.app"):
            exe = app / "Contents" / "MacOS" / "Chromium"
            if exe.is_file():
                return str(exe)

    return None


def _resolve_browser_path() -> str:
    """按优先级解析浏览器路径."""
    # 1. 显式配置优先
    if pconfig.browser_path:
        return pconfig.browser_path

    # 2. 系统默认安装位置
    if path := _find_browser_from_system():
        return path

    # 3. ms-playwright 默认安装目录
    if path := _find_browser_from_playwright():
        return path

    # 4. Puppeteer 默认安装目录
    if path := _find_browser_from_puppeteer():
        return path

    raise RuntimeError("无法找到可启动的浏览器，请在配置中设置 browser_path")


browser_path = _resolve_browser_path()

co = ChromiumOptions()
co.mute(True)
co.incognito(True)
co.no_imgs(True)
co.headless(pconfig.headless)
co.set_argument("--no-sandbox")
co.set_browser_path(browser_path)
# 浏览器数据缓存路径 C:\Users\用户名\AppData\Local\Temp\DrissionPage\userData\9222
BROWSER = Chromium(co)


@driver.on_shutdown
def close_browser():
    BROWSER.quit()
