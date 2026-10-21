from contextlib import asynccontextmanager
import gzip
from types import SimpleNamespace

from anyio import Path
from httpx import DecodingError, Request, Response
import pytest
import render_test_support as support

from nonebot_plugin_parser_lite import download
from nonebot_plugin_parser_lite.download import client as client_module
from nonebot_plugin_parser_lite.utils import ffmpeg as ffmpeg_module
from nonebot_plugin_parser_lite.utils.cache import CacheManager
from nonebot_plugin_parser_lite.utils.common import generate_file_name


@pytest.fixture
def downloader_modules(tmp_path, monkeypatch):
    monkeypatch.setattr(
        type(support.pconfig), "cache_dir", property(lambda _: Path(tmp_path))
    )
    monkeypatch.setattr(download.StreamDownloader, "MAX_RETRIES", 2)
    return download, client_module, CacheManager


def response(status_code, *, headers=None, chunks=()):
    return client_module.UniResponse(
        Response(
            status_code,
            headers=headers,
            content=b"".join(chunks),
            request=Request("GET", "https://cdn.example/media"),
        )
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    @asynccontextmanager
    async def stream(self, method, url, *, headers, use_curl_cffi=False):
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "use_curl_cffi": use_curl_cffi,
            }
        )
        yield self.responses.pop(0)


def _new_downloader(download, client):
    downloader = object.__new__(download.StreamDownloader)
    downloader.headers = {
        "User-Agent": "downloader-test",
        "accept-encoding": "gzip, deflate, br",
    }
    downloader.client = client
    downloader._active_downloads = {}
    return downloader


@pytest.mark.asyncio
async def test_head_size_ignores_error_response_length(downloader_modules):
    download, _, _ = downloader_modules
    downloader = object.__new__(download.StreamDownloader)

    async def fake_head(*args, **kwargs):
        return SimpleNamespace(
            is_success=False,
            headers={"content-length": "335000000"},
        )

    downloader.head = fake_head

    assert await downloader.head_size("https://cdn.example/video.m4s") is None


async def _download_image(downloader, cache_manager):
    return await downloader.streamd(
        url="https://cdn.example/image.webp",
        cache_key="image",
        default_suffix=".webp",
        cache_type=cache_manager.MEDIA,
    )


async def _no_sleep(_delay):
    return None


@pytest.mark.asyncio
async def test_file_download_forces_identity_encoding(downloader_modules):
    download, _, cache_manager = downloader_modules
    client = FakeClient(
        [response(200, headers={"Content-Length": "4"}, chunks=[b"webp"])]
    )
    downloader = _new_downloader(download, client)

    path = await _download_image(downloader, cache_manager)

    assert await path.read_bytes() == b"webp"
    assert client.requests[0]["headers"]["Accept-Encoding"] == "identity"
    assert "accept-encoding" not in client.requests[0]["headers"]


@pytest.mark.asyncio
async def test_generic_binary_content_type_uses_puremagic_and_updates_cache_meta(
    downloader_modules,
):
    download, _, cache_manager = downloader_modules
    client = FakeClient(
        [
            response(
                200,
                headers={
                    "Content-Length": "12",
                    "Content-Type": "application/octet-stream",
                },
                chunks=[b"\x00\x00\x00\x18ftypisom"],
            )
        ]
    )
    downloader = _new_downloader(download, client)
    path = await downloader.streamd(
        url="https://cdn.example/media.bin",
        cache_key="video",
        default_suffix=".dat",
        cache_type=cache_manager.MEDIA,
    )

    assert path.suffix == ".mp4"
    assert await path.with_suffix(".meta").read_bytes() == path.suffix.encode()


@pytest.mark.asyncio
async def test_unidentified_binary_uses_default_suffix(downloader_modules):
    download, _, cache_manager = downloader_modules
    client = FakeClient(
        [
            response(
                200,
                headers={
                    "Content-Length": "3",
                    "Content-Type": "application/octet-stream",
                },
                chunks=[b"\x00\x01\x02"],
            )
        ]
    )
    downloader = _new_downloader(download, client)

    path = await downloader.streamd(
        url="https://cdn.example/media",
        cache_key="unknown",
        default_suffix=".dat",
        cache_type=cache_manager.MEDIA,
    )

    assert path.suffix == ".dat"
    assert await path.with_suffix(".meta").read_bytes() == path.suffix.encode()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "expected_suffix"),
    [
        ("https://cdn.example/song.mgg?guid=test&vkey=test", ".mgg"),
        ("https://cdn.example/song.MFLAC?token=test", ".mflac"),
        ("https://cdn.example/song.mmp4", ".mmp4"),
        ("https://cdn.example/audio?filename=song.mgg", ".mp3"),
        ("https://cdn.example/song.bin", ".bin"),
    ],
)
async def test_unidentified_audio_preserves_source_suffix(
    downloader_modules, url, expected_suffix
):
    download, _, cache_manager = downloader_modules  # noqa: RUF059
    client = FakeClient(
        [response(200, headers={"Content-Length": "3"}, chunks=[b"\x00\x01\x02"])]
    )
    downloader = _new_downloader(download, client)

    path = await downloader.download_audio(url=url)

    assert path.suffix == expected_suffix
    assert await path.read_bytes() == b"\x00\x01\x02"
    assert await path.with_suffix(".meta").read_bytes() == path.suffix.encode()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "default_suffix", "expected_suffix"),
    [
        ("https://cdn.example/file.part", ".ogg", ".ogg"),
        ("https://cdn.example/file.meta", ".dat", ".dat"),
        ("https://cdn.example/file.META", ".dat", ".dat"),
        ("https://cdn.example/file.meta.part", ".dat", ".dat"),
    ],
)
async def test_reserved_suffix_does_not_destroy_download(
    downloader_modules, monkeypatch, url, default_suffix, expected_suffix
):
    download, _, cache_manager = downloader_modules  # noqa: RUF059
    client = FakeClient(
        [response(200, headers={"Content-Length": "3"}, chunks=[b"\x00\x01\x02"])]
    )
    downloader = _new_downloader(download, client)

    path = await downloader.streamd(url=url, default_suffix=default_suffix)

    assert path.suffix == expected_suffix
    assert await path.read_bytes() == b"\x00\x01\x02"
    assert await path.with_suffix(".meta").read_bytes() == expected_suffix.encode()
    assert not await path.with_suffix(".part").exists()


@pytest.mark.asyncio
async def test_stream_suffix_comes_from_successful_fallback_url(
    downloader_modules, monkeypatch
):
    download, _, _ = downloader_modules
    client = FakeClient(
        [
            response(404),
            response(200, headers={"Content-Length": "3"}, chunks=[b"\x00\x01\x02"]),
        ]
    )
    downloader = _new_downloader(download, client)
    monkeypatch.setattr(download.asyncio, "sleep", _no_sleep)

    path = await downloader.streamd(
        url="https://primary.example/song.mp3",
        fallback_urls=("https://backup.example/song.mgg?token=test",),
        retry_http_statuses={404},
        default_suffix=".dat",
    )

    assert path.suffix == ".mgg"
    assert await path.read_bytes() == b"\x00\x01\x02"


@pytest.mark.asyncio
async def test_retryable_http_status_rotates_to_fallback_url(
    downloader_modules, monkeypatch
):
    download, _, cache_manager = downloader_modules
    client = FakeClient(
        [
            response(404),
            response(200, headers={"Content-Length": "5"}, chunks=[b"fresh"]),
        ]
    )
    downloader = _new_downloader(download, client)
    monkeypatch.setattr(download.asyncio, "sleep", _no_sleep)

    path = await downloader.streamd(
        url="https://primary.example/video.m4s",
        fallback_urls=("https://backup.example/video.m4s",),
        retry_http_statuses={404},
        cache_key="video",
        default_suffix=".m4s",
        cache_type=cache_manager.MEDIA,
    )

    assert await path.read_bytes() == b"fresh"
    assert [request["url"] for request in client.requests] == [
        "https://primary.example/video.m4s",
        "https://backup.example/video.m4s",
    ]


@pytest.mark.asyncio
async def test_retryable_http_status_retries_primary_without_fallback(
    downloader_modules, monkeypatch
):
    download, _, cache_manager = downloader_modules
    client = FakeClient(
        [
            response(404),
            response(200, headers={"Content-Length": "5"}, chunks=[b"fresh"]),
        ]
    )
    downloader = _new_downloader(download, client)
    monkeypatch.setattr(download.asyncio, "sleep", _no_sleep)

    path = await downloader.streamd(
        url="https://primary.example/video.m4s",
        retry_http_statuses={404},
        cache_key="video",
        default_suffix=".m4s",
        cache_type=cache_manager.MEDIA,
    )

    assert await path.read_bytes() == b"fresh"
    assert [request["url"] for request in client.requests] == [
        "https://primary.example/video.m4s",
        "https://primary.example/video.m4s",
    ]


@pytest.mark.asyncio
async def test_unlisted_http_status_is_not_retried(downloader_modules):
    download, _, cache_manager = downloader_modules
    client = FakeClient([response(404)])
    downloader = _new_downloader(download, client)

    with pytest.raises(client_module.HTTPStatusError):
        await downloader.streamd(
            url="https://cdn.example/missing.webp",
            retry_http_statuses={503},
            cache_key="missing",
            default_suffix=".webp",
            cache_type=cache_manager.MEDIA,
        )

    assert len(client.requests) == 1


@pytest.mark.asyncio
async def test_legacy_part_416_is_removed_and_restarted(downloader_modules, tmp_path):
    download, _, cache_manager = downloader_modules
    media_dir = tmp_path / cache_manager.MEDIA
    media_dir.mkdir()
    (
        media_dir
        / f"{generate_file_name('https://cdn.example/image.webp', 'image')}.part"
    ).write_bytes(b"stale-decoded-data")
    client = FakeClient(
        [
            response(416),
            response(200, headers={"Content-Length": "5"}, chunks=[b"fresh"]),
        ]
    )
    downloader = _new_downloader(download, client)

    path = await _download_image(downloader, cache_manager)

    assert await path.read_bytes() == b"fresh"
    assert client.requests[0]["headers"]["Range"] == "bytes=18-"
    assert "Range" not in client.requests[1]["headers"]
    assert not (
        media_dir
        / f"{generate_file_name('https://cdn.example/image.webp', 'image')}.part"
    ).exists()


@pytest.mark.parametrize(
    "content_range",
    [
        None,
        "not-a-content-range",
        "bytes 2-7/10",
    ],
    ids=["missing", "malformed", "mismatched-start"],
)
@pytest.mark.asyncio
async def test_invalid_content_range_removes_part_and_restarts_cleanly(
    downloader_modules, tmp_path, content_range
):
    download, _, cache_manager = downloader_modules
    media_dir = tmp_path / cache_manager.MEDIA
    media_dir.mkdir()
    part_path = (
        media_dir
        / f"{generate_file_name('https://cdn.example/image.webp', 'image')}.part"
    )
    part_path.write_bytes(b"partial-data")

    resume_headers = {
        "Content-Length": "20",
        "Content-Encoding": "identity",
    }
    if content_range is not None:
        resume_headers["Content-Range"] = content_range

    client = FakeClient(
        [
            response(
                206,
                headers=resume_headers,
                chunks=[b"must-not-be-appended"],
            ),
            response(200, headers={"Content-Length": "5"}, chunks=[b"fresh"]),
        ]
    )
    downloader = _new_downloader(download, client)

    path = await _download_image(downloader, cache_manager)

    assert await path.read_bytes() == b"fresh"
    assert client.requests[0]["headers"]["Range"] == "bytes=12-"
    assert "Range" not in client.requests[1]["headers"]
    assert len(client.requests) == 2
    assert not part_path.exists()


@pytest.mark.asyncio
async def test_short_identity_response_resumes_with_matching_range(
    downloader_modules,
):
    download, _, cache_manager = downloader_modules
    prefix = b"a" * 512
    remainder = b"b" * 1536
    client = FakeClient(
        [
            response(
                200,
                headers={"Content-Length": "2048"},
                chunks=[prefix],
            ),
            response(
                206,
                headers={
                    "Content-Length": "1536",
                    "Content-Range": "bytes 512-2047/2048",
                },
                chunks=[remainder],
            ),
        ]
    )
    downloader = _new_downloader(download, client)

    path = await _download_image(downloader, cache_manager)

    assert await path.read_bytes() == prefix + remainder
    assert client.requests[1]["headers"]["Range"] == "bytes=512-"


@pytest.mark.asyncio
async def test_unexpected_encoded_response_does_not_compare_decoded_length(
    downloader_modules,
):
    download, _, cache_manager = downloader_modules
    decoded = b"decoded-webp" * 1024
    encoded = gzip.compress(decoded)
    client = FakeClient(
        [
            response(
                200,
                headers={
                    "Content-Encoding": "gzip",
                    "Content-Length": str(len(encoded)),
                },
                chunks=[encoded],
            )
        ]
    )
    downloader = _new_downloader(download, client)

    path = await _download_image(downloader, cache_manager)

    assert await path.read_bytes() == decoded


@pytest.mark.asyncio
async def test_decoding_error_discards_partial_file(downloader_modules, monkeypatch):
    _, client_module, _ = downloader_modules

    class BrokenHttpxResponse:
        async def aiter_bytes(self, _chunk_size=None):
            yield b"partial"
            raise DecodingError(
                "invalid gzip stream",
                request=Request("GET", "https://cdn.example/image.webp"),
            )

    monkeypatch.setattr(client_module, "HttpxResponse", BrokenHttpxResponse)
    response = client_module.UniResponse(BrokenHttpxResponse())

    async def consume_response():
        async for _ in response.aiter_bytes():
            pass

    with pytest.raises(client_module.RetryableDownloadError) as exc_info:
        await consume_response()

    assert exc_info.value.keep_part is False


@pytest.mark.asyncio
async def test_m3u8_reuses_final_mp4_after_removing_task_ts(
    downloader_modules, tmp_path, monkeypatch
):
    download, _, cache_manager = downloader_modules
    downloader = _new_downloader(download, FakeClient([]))
    calls = 0

    class FakeFFmpeg:
        @classmethod
        async def download_hls_to_mp4(cls, url, output_path, **kwargs):
            nonlocal calls
            calls += 1
            await output_path.write_bytes(b"mp4-cache")

    monkeypatch.setattr(download, "FFmpeg", FakeFFmpeg)

    kwargs = {
        "url": "https://cdn.example/master.m3u8",
        "cache_key": "same-video",
        "cache_type": cache_manager.MEDIA,
    }
    first_path = await downloader.download_m3u8_video(**kwargs)
    second_path = await downloader.download_m3u8_video(**kwargs)

    assert str(first_path) == str(second_path)
    assert await second_path.read_bytes() == b"mp4-cache"
    assert calls == 1
    assert not list((tmp_path / cache_manager.MEDIA).glob("*.tmp.ts"))


@pytest.mark.asyncio
async def test_complex_hls_is_delegated_to_ffmpeg(downloader_modules, monkeypatch):
    download, _, cache_manager = downloader_modules
    downloader = _new_downloader(download, FakeClient([]))
    delegated = []

    class FakeFFmpeg:
        @classmethod
        async def download_hls_to_mp4(
            cls, url, output_path, headers=None, max_size_mb=None, on_progress=None
        ):
            delegated.append((url, headers))
            await output_path.write_bytes(b"mp4-cache")

    monkeypatch.setattr(download, "FFmpeg", FakeFFmpeg)

    path = await downloader.download_m3u8_video(
        url="https://cdn.example/encrypted.m3u8",
        cache_key="encrypted-video",
        cache_type=cache_manager.MEDIA,
    )

    assert await path.read_bytes() == b"mp4-cache"
    assert delegated == [
        (
            "https://cdn.example/encrypted.m3u8",
            {
                "User-Agent": "downloader-test",
                "accept-encoding": "gzip, deflate, br",
            },
        )
    ]


@pytest.mark.asyncio
async def test_native_hls_zero_output_raises_zero_size(downloader_modules, monkeypatch):
    download, _, cache_manager = downloader_modules
    downloader = _new_downloader(download, FakeClient([]))

    class FakeFFmpeg:
        @classmethod
        async def download_hls_to_mp4(cls, url, output_path, **kwargs):
            await output_path.write_bytes(b"")

    monkeypatch.setattr(download, "FFmpeg", FakeFFmpeg)

    with pytest.raises(download.ZeroSizeException):
        await downloader.download_m3u8_video(
            url="https://cdn.example/empty.m3u8",
            cache_key="empty-video",
            cache_type=cache_manager.MEDIA,
        )


@pytest.mark.asyncio
async def test_ffmpeg_failure_does_not_publish_partial_output(tmp_path, monkeypatch):
    input_path = ffmpeg_module.Path(tmp_path / "input.ts")
    output_path = ffmpeg_module.Path(tmp_path / "video.mp4")
    await input_path.write_bytes(b"input")

    async def fail_after_partial_write(cls, cmd, input=None):
        await ffmpeg_module.Path(cmd[-1]).write_bytes(b"partial")
        raise RuntimeError("ffmpeg failed")

    monkeypatch.setattr(
        ffmpeg_module.FFmpeg,
        "exec_ffmpeg",
        classmethod(fail_after_partial_write),
    )

    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        await ffmpeg_module.FFmpeg.remux_to_mp4(input_path, output_path)

    assert not await output_path.exists()
    assert not list(tmp_path.glob(".video.*.tmp.mp4"))
