"""Lazy exports for platform parsers."""

from importlib import import_module
from typing import Any

_PARSERS = {
    "AcfunParser": ".acfun",
    "BilibiliParser": ".bilibili",
    "BuffParser": ".buff",
    "CoolapkParser": ".coolapk",
    "DoubanParser": ".douban",
    "DouBaoParser": ".doubao",
    "DouyinParser": ".douyin",
    "DuiTangParser": ".duitang",
    "FiveEPlayParser": ".fiveeplay",
    "HeyBoxParser": ".heybox",
    "HupuParser": ".hupu",
    "IlluParser": ".illu",
    "KuaiShouParser": ".kuaishou",
    "KuGouParser": ".kugou",
    "KuWoParser": ".kuwo",
    "LinuxDoParser": ".linuxdo",
    "LofterParser": ".lofter",
    "MiyousheParser": ".miyoushe",
    "NCMParser": ".netease",
    "QSMusicParser": ".qsmusic",
    "RedNoteParser": ".rednote",
    "TiebaParser": ".tieba",
    "WeiBoParser": ".weibo",
    "WMPVPParser": ".wmpvp",
    "XParser": ".x",
    "ZhiHuParser": ".zhihu",
    "ZLBParser": ".zlb",
}

__all__ = list(_PARSERS)


def __getattr__(name: str) -> Any:
    try:
        module_name = _PARSERS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def load_all() -> tuple[type, ...]:
    """Load every platform parser for automatic text matching."""
    return tuple(
        __getattr__(name) if name not in globals() else globals()[name]
        for name in __all__
    )
