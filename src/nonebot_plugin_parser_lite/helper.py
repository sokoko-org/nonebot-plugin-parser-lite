"""Framework-neutral media helpers kept at the original import path."""

from dataclasses import dataclass
from functools import wraps
from typing import Any, Literal

from anyio import Path


@dataclass(slots=True)
class MediaFile:
    kind: Literal["image", "audio", "video", "file"]
    path: Path | None = None
    raw: bytes | None = None
    name: str | None = None
    thumbnail: Path | None = None


ForwardNodeInner = str | MediaFile


class UniHelper:
    @staticmethod
    def construct_forward_message(
        segments: list[ForwardNodeInner], user_id: str | None = None
    ) -> list[ForwardNodeInner]:
        return segments.copy()

    @staticmethod
    async def img_seg(file: Path | bytes) -> MediaFile:
        if isinstance(file, bytes):
            return MediaFile("image", raw=bytes(file))
        return MediaFile("image", path=file)

    @staticmethod
    async def record_seg(file: Path) -> MediaFile:
        return MediaFile("audio", path=file)

    @staticmethod
    async def video_seg(file: Path, thumbnail: Path | None = None) -> MediaFile:
        return MediaFile("video", path=file, thumbnail=thumbnail)

    @staticmethod
    async def file_seg(file: Path, display_name: str | None = None) -> MediaFile:
        return MediaFile("file", path=file, name=display_name or file.name)

    @staticmethod
    async def message_reaction(event: object, status: str) -> None:
        raise RuntimeError("message reactions require a bot framework")

    @classmethod
    def with_reaction(cls, func):
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            return await func(*args, **kwargs)

        return wrapper
