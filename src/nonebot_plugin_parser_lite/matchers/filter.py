"""Standalone platform enablement helper."""

from ..config import pconfig


def is_enabled(platform: str) -> bool:
    return platform not in pconfig.disabled_platforms


__all__ = ["is_enabled"]
