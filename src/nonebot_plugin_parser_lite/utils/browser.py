"""使用 DrissionPage 启动浏览器，完美过检测，并支持无头模式.
本脚本会启动一个持久化的浏览器实例,
只要设备不重启或在任务管理器kill实例,实例将持续后台运行,时刻准备被接管"""

import contextlib
import platform

from DrissionPage import Chromium, ChromiumOptions
from DrissionPage._units.listener import DataPacket as DataPacket
from ..config import pconfig

system = platform.system()
browser_path = None

if system == "Windows":
    import winreg

    paths = {
        "chrome": r"SOFTWARE\Clients\StartMenuInternet\Google Chrome\DefaultIcon",
        "msedge": r"SOFTWARE\Clients\StartMenuInternet\Microsoft Edge\DefaultIcon",
    }
    for path in paths.values():
        with contextlib.suppress(FileNotFoundError):
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
            value, _ = winreg.QueryValueEx(key, "")
            browser_path = value.split(",")[0]
            break
elif system == "Darwin":
    # macOS 下常见浏览器的默认安装路径
    mac_paths = (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    )
    for path in mac_paths:
        from pathlib import Path

        if Path(path).is_file():
            browser_path = path
            break
elif pconfig.browser_path:
    browser_path = pconfig.browser_path
if not browser_path:
    raise RuntimeError("无法找到可启动的浏览器")


co = ChromiumOptions()
co.mute(True)
co.incognito(True)
co.headless(False)
# 无头模式会被检测到，不能无头
co.set_browser_path(browser_path)
# 浏览器数据缓存路径 C:\Users\用户名\AppData\Local\Temp\DrissionPage\userData\9222
BROWSER = Chromium(co)
