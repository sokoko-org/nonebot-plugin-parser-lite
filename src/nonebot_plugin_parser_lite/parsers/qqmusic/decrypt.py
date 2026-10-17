from types import MappingProxyType
from typing import Final

from anyio import CancelScope, Path, open_file, to_thread

from .qmc import QmcCipher, derive_qmc_key

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


def _crc(data: bytes, bits: int, polynomial: int) -> int:
    value = 0
    mask = (1 << bits) - 1
    for byte in data:
        value ^= byte << (bits - 8)
        for _ in range(8):
            value = (
                (value << 1) ^ (polynomial if value & (1 << (bits - 1)) else 0)
            ) & mask
    return value


def _flac_frame_samples(data: bytes, fixed_block: int) -> tuple[int, int] | None:
    if len(data) < 7 or data[0] != 0xFF or data[1] & 0xFE != 0xF8 or data[3] & 1:
        return None
    pos = 4
    first = data[pos]
    if first < 0x80:
        number = first
        pos += 1
    else:
        count = 0
        while count < 8 and first & (0x80 >> count):
            count += 1
        if count < 2 or count > 7 or len(data) <= pos + count:
            return None
        number = first & (0x7F >> count)
        for byte in data[pos + 1 : pos + count]:
            if byte & 0xC0 != 0x80:
                return None
            number = (number << 6) | (byte & 0x3F)
        pos += count
    block_code, rate_code = data[2] >> 4, data[2] & 0xF
    if block_code == 0 or rate_code == 15:
        return None
    if block_code == 1:
        samples = 192
    elif 2 <= block_code <= 5:
        samples = 576 << (block_code - 2)
    elif block_code == 6:
        if len(data) <= pos:
            return None
        samples = data[pos] + 1
        pos += 1
    elif block_code == 7:
        if len(data) <= pos + 1:
            return None
        samples = int.from_bytes(data[pos : pos + 2], "big") + 1
        pos += 2
    else:
        samples = 256 << (block_code - 8)
    pos += 1 if rate_code == 12 else 2 if rate_code in {13, 14} else 0
    if len(data) <= pos or _crc(data[: pos + 1], 8, 0x07):
        return None
    start = number if data[1] & 1 else number * fixed_block
    return start, samples


async def _remove_flac_trailer(path: Path) -> int:
    """Strip the observed 30-byte QQMusic footer only after validating the final FLAC frame."""
    async with await open_file(path, "r+b") as file:
        header = await file.read(42)
        if (
            len(header) != 42
            or header[:4] != b"fLaC"
            or header[4] & 0x7F
            or header[5:8] != b"\0\0\x22"
        ):
            return 0
        info = header[8:42]
        total_samples = int.from_bytes(info[10:18], "big") & ((1 << 36) - 1)
        fixed_block = int.from_bytes(info[2:4], "big")
        max_frame = int.from_bytes(info[7:10], "big") or 1024 * 1024
        size = await file.seek(0, 2)
        await file.seek(max(42, size - max_frame - 30))
        tail = await file.read()
        for index in range(len(tail) - 30):
            if tail[index : index + 1] != b"\xff":
                continue
            samples = _flac_frame_samples(tail[index:], fixed_block)
            if samples is None or samples[0] + samples[1] != total_samples:
                continue
            if _crc(tail[index:], 16, 0x8005) == 0:
                return 0
            if len(tail) - index > 32 and _crc(tail[index:-30], 16, 0x8005) == 0:
                await file.truncate(size - 30)
                return 30
        return 0


def _validate_audio(header: bytes, extension: str) -> None:
    valid = {
        ".flac": header.startswith(b"fLaC"),
        ".ogg": header.startswith(b"OggS"),
        ".m4a": header[4:8] == b"ftyp",
        ".mp3": header.startswith(b"ID3")
        or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0),
    }
    if extension not in valid or not valid[extension]:
        raise ValueError(f"QQMusic decrypted data does not have a valid {extension} header")


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
    cipher = QmcCipher(derive_qmc_key(ekey.encode("ascii"))) if ekey else None
    await target.parent.mkdir(parents=True, exist_ok=True)
    decrypted = bytearray(await source.read_bytes())
    if cipher is not None:
        await to_thread.run_sync(cipher.decrypt, decrypted, 0)
    _validate_audio(bytes(decrypted[:16]), extension)
    try:
        await target.write_bytes(decrypted)  # pyright: ignore[reportArgumentType]
        if extension == ".flac":
            await _remove_flac_trailer(target)
    except BaseException:
        with CancelScope(shield=True):
            await target.unlink(missing_ok=True)
        raise
    return target
