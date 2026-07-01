import base64
import contextlib
import json
import os
import time
from typing import ClassVar

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .base import (
    BaseParser,
    ContentItem,
    MatchWithParams,
    ParseException,
    Platform,
    PlatformEnum,
    handle,
)


def parse_duration_to_seconds(duration: str) -> int:
    """将时长字符串解析为总秒数。"""
    parts = duration.split(":")
    if not (1 <= len(parts) <= 3):
        raise ValueError(f"非法的时长格式: {duration!r}")

    try:
        parts_int = [int(p) for p in parts]
    except ValueError as exc:
        raise ValueError(f"时长中包含非法数字: {duration!r}") from exc

    if len(parts_int) == 1:
        hours = 0
        minutes = 0
        seconds = parts_int[0]
    elif len(parts_int) == 2:
        hours = 0
        minutes, seconds = parts_int
    else:
        hours, minutes, seconds = parts_int

    if not (0 <= seconds < 60 and 0 <= minutes < 60 and hours >= 0):
        raise ValueError(f"时长数值不合法: {duration!r}")

    return hours * 3600 + minutes * 60 + seconds


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(s: str) -> bytes:
    return base64.b64decode(s)


def _encrypt(payload: dict, key_b64: str) -> str:
    key = _b64decode(key_b64)
    iv = os.urandom(12)
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    aesgcm = AESGCM(key)
    encrypted = aesgcm.encrypt(iv, plaintext, None)
    ciphertext = encrypted[:-16]
    tag = encrypted[-16:]
    return f"{_b64encode(iv)}.{_b64encode(tag)}.{_b64encode(ciphertext)}"


def _decrypt(ciphertext_str: str, key_b64: str) -> dict:
    key = _b64decode(key_b64)
    parts = ciphertext_str.split(".")
    if len(parts) != 3:
        raise ValueError("invalid ciphertext format")
    iv = _b64decode(parts[0])
    tag = _b64decode(parts[1])
    ciphertext = _b64decode(parts[2])
    combined = ciphertext + tag
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, combined, None)
    return json.loads(plaintext.decode("utf-8"))


class NCMParser(BaseParser):
    platform: ClassVar[Platform] = Platform(
        name=PlatformEnum.NETEASE, display_name="网易云音乐"
    )

    def __init__(self):
        super().__init__()
        self.httpx.headers.update({"Referer": "https://wyapi.toubiec.cn/"})
        self.httpx.base_url = "https://nextmusic.toubiec.cn/api"

    async def getEncryptParam(self) -> dict:
        resp = await self.httpx.post("key")
        data = resp.json()
        if data.get("code") != 200:
            raise ParseException(f"获取解密密钥失败: {data}")
        return data["data"]

    async def fetch(self, endpoint: str, payload: dict) -> dict:
        session = await self.getEncryptParam()
        encrypted = _encrypt(
            {**payload, "timestamp": int(time.time() * 1000)},
            session["key"],
        )
        body = {
            "keyId": session["keyId"],
            "keyToken": session["keyToken"],
            "data": encrypted,
        }
        resp = await self.httpx.post(endpoint, json=body)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") != 200:
            raise ParseException(f"接口返回错误: {result}")
        if ciphertext := result.get("ciphertext"):
            return _decrypt(ciphertext, session["key"])["data"]
        return result["data"]

    @handle("163cn.tv", r"https?://[^\s]*?163cn\.tv/[a-zA-Z0-9]+")
    async def _parse_163cn(self, searched: MatchWithParams):
        return await self.parse_with_redirect(searched[0])

    @handle("music.163.com", params={"id": {"as_int": True}})
    @handle("music.163.com", r"song/(?P<id>\d+)")
    async def _parse_netease(self, searched: MatchWithParams):
        ncm_id = searched["id"]
        song = await self.fetch("getSongInfo", {"id": ncm_id})
        title = song.get("name", "未知")
        artist = song.get("singer", "未知歌手")
        duration = parse_duration_to_seconds(song.get("duration", "0"))
        lyric = ""
        with contextlib.suppress(Exception):
            lyric = (await self.fetch("getSongLyric", {"id": ncm_id})).get("lrc")
        url_data = await self.fetch("getSongUrl", {"id": ncm_id, "level": "standard"})
        if not (audio_url := url_data.get("url")):
            raise ParseException("无法获取音频下载地址")
        url_no_params = audio_url.split("?", 1)[0]
        ext = url_no_params.rsplit(".", 1)[-1].lower() if "." in url_no_params else ""
        audio_type = ext if ext in {"flac", "wav", "m4a", "aac", "mp3"} else "mp3"
        contents: list[ContentItem] = []

        audio_name = f"{title}-{artist}.{audio_type}"
        audio = self.create_audio(
            audio_url,
            duration=duration,
            audio_name=audio_name,
        )
        contents.append(audio)

        if cover_url := song.get("picimg"):
            contents.append(self.create_image(cover_url))

        audio_info = f"大小: {await audio.get_display_size()} | 格式: {audio_type}"

        extra = {
            "info": audio_info,
            "lyric": lyric,
        }

        return self.result(
            title=title,
            author=self.create_author(name=artist),
            url=f"https://music.163.com/song/{ncm_id}",
            content=contents,
            extra=extra,
        )
