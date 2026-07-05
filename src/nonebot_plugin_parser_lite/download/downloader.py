import asyncio

from anyio import Path
from httpx import Response

from ..cache import CacheManager
from ..constants import COMMON_HEADER, DOWNLOAD_TIMEOUT
from ..exception import DownloadException
from ..utils.common import generate_file_name, safe_unlink
from ..utils.ffmpeg import FFmpeg
from .client import DownloadHttpClient
from .m3u8 import M3U8Downloader
from .models import parse_int_header
from .stream import FileDownloader
from .task import auto_task


class StreamDownloader:
    """Public downloader facade used by parsers and message creators."""

    def __init__(self):
        self.headers: dict[str, str] = COMMON_HEADER.copy()
        self.client = DownloadHttpClient(timeout=DOWNLOAD_TIMEOUT)
        self._active_downloads: dict[str, asyncio.Task[None]] = {}
        self._file_downloader = FileDownloader(
            client=self.client,
            headers=self.headers,
            active_downloads=self._active_downloads,
        )
        self._m3u8_downloader = M3U8Downloader(
            client=self.client,
            headers=self.headers,
            fetch_text=self.text,
            has_ffmpeg=self._has_ffmpeg,
            remux_to_mp4=self._remux_to_mp4,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    def _headers(self, ext_headers: dict[str, str] | None = None) -> dict[str, str]:
        return {**self.headers, **(ext_headers or {})}

    async def head(
        self,
        url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> Response:
        headers = self._headers(ext_headers)
        resp = await self.client.head(
            url=url,
            headers=headers,
            use_curl_cffi=use_curl_cffi,
        )
        if 200 <= resp.status_code < 300:
            return resp.to_httpx_response()

        async with self.client.stream(
            "GET",
            url,
            headers=headers,
            use_curl_cffi=use_curl_cffi,
        ) as stream_resp:
            return stream_resp.to_httpx_response()

    async def head_size(
        self,
        url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> int | None:
        response = await self.head(
            url, ext_headers=ext_headers, use_curl_cffi=use_curl_cffi
        )
        return parse_int_header(response.headers.get("Content-Length"))

    async def text(
        self,
        url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> str:
        resp = await self.client.get(
            url,
            headers=self._headers(ext_headers),
            use_curl_cffi=use_curl_cffi,
        )
        if resp.status_code != 200:
            raise DownloadException(f"请求失败: {resp.status_code}")
        return resp.text

    async def content(
        self,
        url: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> bytes:
        resp = await self.client.get(
            url,
            headers=self._headers(ext_headers),
            use_curl_cffi=use_curl_cffi,
        )
        if resp.status_code != 200:
            raise DownloadException(f"请求失败: {resp.status_code}")
        return resp.content

    @auto_task
    async def streamd(
        self,
        *,
        url: str,
        file_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        return await self._file_downloader.download(
            url=url,
            file_name=file_name,
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )

    @auto_task
    async def download_video(
        self,
        *,
        url: str,
        video_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        if video_name is None:
            video_name = generate_file_name(url, ".mp4")
        return await self.streamd(
            url=url,
            file_name=video_name,
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )

    @auto_task
    async def download_audio(
        self,
        *,
        url: str,
        audio_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        if audio_name is None:
            audio_name = generate_file_name(url, ".mp3")
        return await self.streamd(
            url=url,
            file_name=audio_name,
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )

    @auto_task
    async def download_img(
        self,
        *,
        url: str,
        img_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        if img_name is None:
            img_name = generate_file_name(url, ".jpg")
        return await self.streamd(
            url=url,
            file_name=img_name,
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )

    @auto_task
    async def download_m3u8_video(
        self,
        *,
        url: str,
        video_name: str | None = None,
        ext_headers: dict[str, str] | None = None,
        cache_type: str = CacheManager.MEDIA,
        use_curl_cffi: bool = False,
    ) -> Path:
        return await self._m3u8_downloader.download(
            url=url,
            video_name=video_name,
            ext_headers=ext_headers,
            cache_type=cache_type,
            use_curl_cffi=use_curl_cffi,
        )

    async def download_av_and_merge(
        self,
        v_url: str,
        a_url: str,
        file_name: str,
        ext_headers: dict[str, str] | None = None,
        use_curl_cffi: bool = False,
    ) -> Path:
        v_path, a_path = await asyncio.gather(
            self.download_video(
                url=v_url,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            ),
            self.download_audio(
                url=a_url,
                ext_headers=ext_headers,
                use_curl_cffi=use_curl_cffi,
            ),
        )
        return await FFmpeg.merge_av(v_path=v_path, a_path=a_path, file_name=file_name)

    async def _has_ffmpeg(self) -> bool:
        return await FFmpeg.is_available()

    async def _remux_to_mp4(self, input_path: Path, output_path: Path) -> None:
        await FFmpeg.remux_to_mp4(input_path, output_path)
        if await output_path.exists():
            await safe_unlink(input_path)


DOWNLOADER: StreamDownloader = StreamDownloader()
