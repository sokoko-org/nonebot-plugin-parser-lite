from types import MappingProxyType
from typing import Final

from anyio import CancelScope, Path, to_thread

from .qmc import decrypt_qmc_file

_OUTPUT_EXTENSIONS: Final = MappingProxyType(
    {
        ".mflac": ".flac",
        ".mgg": ".ogg",
        ".mmp4": ".m4a",
        ".flac": ".flac",
        ".ogg": ".ogg",
        ".m4a": ".m4a",
        ".mp3": ".mp3",
    }
)


async def decrypt_qqmusic_file(
    source: Path,
    ekey: str,
) -> Path:
    """Decrypt the entire QQMusic file using the API ekey and source.suffix."""
    extension = _OUTPUT_EXTENSIONS.get(source.suffix.lower())
    if extension is None:
        raise ValueError(f"unsupported QQMusic source suffix: {source.suffix!r}")
    target = source.with_name(f"{source.stem}.decrypted{extension}")
    if await target.exists():
        return target
    await target.parent.mkdir(parents=True, exist_ok=True)
    try:
        await to_thread.run_sync(decrypt_qmc_file, str(source), str(target), ekey)
    except BaseException:
        with CancelScope(shield=True):
            await target.unlink(missing_ok=True)
        raise
    return target
