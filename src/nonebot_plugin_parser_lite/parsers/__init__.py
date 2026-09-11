from importlib import import_module
from importlib.util import find_spec

from ..config import pconfig
from ..constants import PlatformEnum
from .base import BaseParser


def load_enabled_parsers() -> list[type[BaseParser]]:
    """按需导入启用的解析器模块，返回已注册子类"""
    disabled = set(pconfig.disabled_platforms)

    for plat in PlatformEnum:
        if plat in disabled:
            continue

        mod_name = plat.name.lower()
        if find_spec(f"{__package__}.{mod_name}") is None:
            continue

        import_module(f".{mod_name}", package=__package__)

    return [
        parser_cls
        for parser_cls in BaseParser.get_all_subclass()
        if parser_cls.platform.name not in disabled
    ]


__all__ = ["load_enabled_parsers"]
