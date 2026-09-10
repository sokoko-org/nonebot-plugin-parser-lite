from contextlib import asynccontextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import ClassVar

from httpx import DecodingError, Request, Timeout
import pytest

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src/nonebot_plugin_parser_lite"
TEST_PACKAGE = "_parser_lite_downloader_test"
FFMPEG_TEST_PACKAGE = "_parser_lite_ffmpeg_test"


class AsyncPathStub:
    """只供下载器单元测试使用，避免依赖 anyio 的工作线程"""

    def __init__(self, path):
        self._path = Path(path)

    def __fspath__(self):
        return str(self._path)

    def __str__(self):
        return str(self._path)

    def __truediv__(self, child):
        return type(self)(self._path / child)

    @property
    def parent(self):
        return type(self)(self._path.parent)

    @property
    def name(self):
        return self._path.name

    @property
    def stem(self):
        return self._path.stem

    @property
    def suffix(self):
        return self._path.suffix

    async def exists(self):
        return self._path.exists()

    async def mkdir(self, *, parents=False, exist_ok=False):
        self._path.mkdir(parents=parents, exist_ok=exist_ok)

    async def rename(self, target):
        self._path.rename(Path(target))

    async def replace(self, target):
        self._path.replace(Path(target))

    async def stat(self):
        return self._path.stat()

    async def unlink(self, *, missing_ok=False):
        self._path.unlink(missing_ok=missing_ok)

    async def read_bytes(self):
        return self._path.read_bytes()

    async def write_bytes(self, data):
        return self._path.write_bytes(data)

    def with_suffix(self, suffix):
        return type(self)(self._path.with_suffix(suffix))

    def with_name(self, name):
        return type(self)(self._path.with_name(name))


class AsyncFileStub:
    """aiofiles.open 的同步测试替身"""

    def __init__(self, path, mode):
        self._file = open(Path(path), mode)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self._file.close()

    async def write(self, data):
        return self._file.write(data)


def _module(name: str, **attrs):
    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_module(name: str, path: Path):
    spec = spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def downloader_modules(tmp_path):
    for name in list(sys.modules):
        if name == TEST_PACKAGE or name.startswith(f"{TEST_PACKAGE}."):
            sys.modules.pop(name)

    package = _module(TEST_PACKAGE)
    package.__path__ = [str(SOURCE)]

    class ParseException(Exception):
        pass

    class DownloadException(ParseException):
        pass

    class SizeLimitException(DownloadException):
        pass

    class ZeroSizeException(DownloadException):
        pass

    _module(
        f"{TEST_PACKAGE}.exception",
        ParseException=ParseException,
        DownloadException=DownloadException,
        SizeLimitException=SizeLimitException,
        ZeroSizeException=ZeroSizeException,
    )

    pconfig = SimpleNamespace(
        max_retries=2,
        cache_dir=AsyncPathStub(tmp_path),
        max_size=10,
    )
    _module(f"{TEST_PACKAGE}.config", pconfig=pconfig)
    _module(
        f"{TEST_PACKAGE}.constants",
        COMMON_HEADER={"User-Agent": "downloader-test"},
        DOWNLOAD_TIMEOUT=Timeout(1.0),
    )

    utils = _module(f"{TEST_PACKAGE}.utils")
    utils.__path__ = []

    class CacheManager:
        MEDIA = "media"
        cached_files: ClassVar[list[tuple[object, object]]] = []

        @classmethod
        async def ensure_dir(cls, cache_type):
            path = pconfig.cache_dir / cache_type
            await path.mkdir(parents=True, exist_ok=True)
            return path

        @classmethod
        async def get_cached_file(cls, _base_path):
            return None

        @classmethod
        async def set_cached_file(cls, base_path, file_path):
            cls.cached_files.append((base_path, file_path))

    async def safe_unlink(path):
        await path.unlink(missing_ok=True)

    _module(f"{TEST_PACKAGE}.utils.cache", CacheManager=CacheManager)
    _module(
        f"{TEST_PACKAGE}.utils.common",
        compose_cache_key=lambda *parts: ":".join(
            str(part) for part in parts if part is not None
        ),
        generate_file_name=lambda url, cache_key=None: (
            cache_key or "download"
        ).replace(":", "-"),
        safe_unlink=safe_unlink,
    )
    _module(f"{TEST_PACKAGE}.utils.ffmpeg", FFmpeg=object)

    download_name = f"{TEST_PACKAGE}.download"
    download_path = SOURCE / "download"
    download_spec = spec_from_file_location(
        download_name,
        download_path / "__init__.py",
        submodule_search_locations=[str(download_path)],
    )
    assert download_spec is not None
    assert download_spec.loader is not None
    download = module_from_spec(download_spec)
    sys.modules[download_name] = download

    client = _load_module(f"{download_name}.client", download_path / "client.py")
    _load_module(f"{download_name}.task", download_path / "task.py")
    download_spec.loader.exec_module(download)
    download.aiofiles = SimpleNamespace(open=AsyncFileStub)  # type: ignore

    yield download, client, CacheManager

    for name in list(sys.modules):
        if name == TEST_PACKAGE or name.startswith(f"{TEST_PACKAGE}."):
            sys.modules.pop(name)


@pytest.fixture
def ffmpeg_module():
    for name in list(sys.modules):
        if name == FFMPEG_TEST_PACKAGE or name.startswith(f"{FFMPEG_TEST_PACKAGE}."):
            sys.modules.pop(name)

    package = _module(FFMPEG_TEST_PACKAGE)
    package.__path__ = [str(SOURCE)]
    utils = _module(f"{FFMPEG_TEST_PACKAGE}.utils")
    utils.__path__ = [str(SOURCE / "utils")]

    class CacheManager:
        MEDIA = "media"

    _module(f"{FFMPEG_TEST_PACKAGE}.utils.cache", CacheManager=CacheManager)

    async def fmt_size(_path):
        return "0 B"

    _module(f"{FFMPEG_TEST_PACKAGE}.utils.common", fmt_size=fmt_size)
    yield _load_module(
        f"{FFMPEG_TEST_PACKAGE}.utils.ffmpeg", SOURCE / "utils/ffmpeg.py"
    )
    for name in list(sys.modules):
        if name == FFMPEG_TEST_PACKAGE or name.startswith(f"{FFMPEG_TEST_PACKAGE}."):
            sys.modules.pop(name)


class FakeResponse:
    def __init__(self, status_code, *, headers=None, chunks=()):
        self.status_code = status_code
        self.headers = {key.lower(): value for key, value in (headers or {}).items()}
        self._chunks = list(chunks)

    def raise_for_status(self):
        if not 200 <= self.status_code < 300:
            raise RuntimeError(f"HTTP {self.status_code}")

    async def aiter_bytes(self, _chunk_size=None):
        for chunk in self._chunks:
            yield chunk


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
        [FakeResponse(200, headers={"Content-Length": "4"}, chunks=[b"webp"])]
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
            FakeResponse(
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
        url="https://cdn.example/media",
        cache_key="video",
        default_suffix=".dat",
        cache_type=cache_manager.MEDIA,
    )

    assert path.name == "video.mp4"
    assert cache_manager.cached_files[-1][1] is path


@pytest.mark.asyncio
async def test_unidentified_binary_uses_default_suffix(downloader_modules):
    download, _, cache_manager = downloader_modules
    client = FakeClient(
        [
            FakeResponse(
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

    assert path.name == "unknown.dat"
    assert cache_manager.cached_files[-1][1] is path


@pytest.mark.asyncio
async def test_retryable_http_status_rotates_to_fallback_url(
    downloader_modules, monkeypatch
):
    download, _, cache_manager = downloader_modules
    client = FakeClient(
        [
            FakeResponse(404),
            FakeResponse(200, headers={"Content-Length": "5"}, chunks=[b"fresh"]),
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
            FakeResponse(404),
            FakeResponse(200, headers={"Content-Length": "5"}, chunks=[b"fresh"]),
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
    client = FakeClient([FakeResponse(404)])
    downloader = _new_downloader(download, client)

    with pytest.raises(RuntimeError, match="HTTP 404"):
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
    (media_dir / "image.part").write_bytes(b"stale-decoded-data")
    client = FakeClient(
        [
            FakeResponse(416),
            FakeResponse(200, headers={"Content-Length": "5"}, chunks=[b"fresh"]),
        ]
    )
    downloader = _new_downloader(download, client)

    path = await _download_image(downloader, cache_manager)

    assert await path.read_bytes() == b"fresh"
    assert client.requests[0]["headers"]["Range"] == "bytes=18-"
    assert "Range" not in client.requests[1]["headers"]
    assert not (media_dir / "image.part").exists()


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
    part_path = media_dir / "image.part"
    part_path.write_bytes(b"partial-data")

    resume_headers = {
        "Content-Length": "20",
        "Content-Encoding": "identity",
    }
    if content_range is not None:
        resume_headers["Content-Range"] = content_range

    client = FakeClient(
        [
            FakeResponse(
                206,
                headers=resume_headers,
                chunks=[b"must-not-be-appended"],
            ),
            FakeResponse(200, headers={"Content-Length": "5"}, chunks=[b"fresh"]),
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
            FakeResponse(
                200,
                headers={"Content-Length": "2048"},
                chunks=[prefix],
            ),
            FakeResponse(
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
    client = FakeClient(
        [
            FakeResponse(
                200,
                headers={
                    "Content-Encoding": "gzip, br",
                    "Content-Length": "124406",
                },
                chunks=[b"decoded-webp"],
            )
        ]
    )
    downloader = _new_downloader(download, client)

    path = await _download_image(downloader, cache_manager)

    assert await path.read_bytes() == b"decoded-webp"


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
    calls = {"parse": 0, "download": 0, "finalize": 0}

    async def fake_parse(*args, **kwargs):
        calls["parse"] += 1
        return ["https://cdn.example/segment.ts"]

    async def fake_download(*, temp_ts_path, **kwargs):
        calls["download"] += 1
        await temp_ts_path.write_bytes(b"t" * 2048)
        return 2048

    async def fake_finalize(*, final_video_path, **kwargs):
        calls["finalize"] += 1
        await final_video_path.write_bytes(b"mp4-cache")

    monkeypatch.setattr(downloader, "_smart_parse_m3u8", fake_parse)
    monkeypatch.setattr(downloader, "_download_m3u8_ts_files", fake_download)
    monkeypatch.setattr(downloader, "_finalize_m3u8_download", fake_finalize)

    kwargs = {
        "url": "https://cdn.example/master.m3u8",
        "cache_key": "same-video",
        "cache_type": cache_manager.MEDIA,
    }
    first_path = await downloader.download_m3u8_video(**kwargs)
    second_path = await downloader.download_m3u8_video(**kwargs)

    assert str(first_path) == str(second_path)
    assert await second_path.read_bytes() == b"mp4-cache"
    assert calls == {"parse": 1, "download": 1, "finalize": 1}
    assert not list((tmp_path / cache_manager.MEDIA).glob("*.tmp.ts"))


@pytest.mark.asyncio
async def test_m3u8_master_selects_highest_resolution_even_when_listed_first(
    downloader_modules, monkeypatch
):
    download, _, _ = downloader_modules
    downloader = _new_downloader(download, FakeClient([]))
    requested_urls = []
    playlists = {
        "https://cdn.example/master.m3u8": """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
high/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION=640x360
low/index.m3u8
""",
        "https://cdn.example/high/index.m3u8": """#EXTM3U
#EXTINF:10,
segment.ts
""",
    }

    async def fake_text(url, **kwargs):
        requested_urls.append(url)
        return playlists[url]

    monkeypatch.setattr(downloader, "text", fake_text)

    urls = await downloader._smart_parse_m3u8("https://cdn.example/master.m3u8")

    assert urls == ["https://cdn.example/high/segment.ts"]
    assert requested_urls == [
        "https://cdn.example/master.m3u8",
        "https://cdn.example/high/index.m3u8",
    ]


@pytest.mark.asyncio
async def test_complex_hls_is_delegated_to_ffmpeg(downloader_modules, monkeypatch):
    download, _, cache_manager = downloader_modules
    downloader = _new_downloader(download, FakeClient([]))
    delegated = []

    async def fake_text(url, **kwargs):
        return """#EXTM3U
#EXT-X-KEY:METHOD=AES-128,URI=\"key.bin\"
#EXTINF:10,
segment.ts
"""

    class FakeFFmpeg:
        @classmethod
        async def download_hls_to_mp4(cls, url, output_path, headers=None):
            delegated.append((url, headers))
            await output_path.write_bytes(b"mp4-cache")

    monkeypatch.setattr(downloader, "text", fake_text)
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
async def test_ffmpeg_failure_does_not_publish_partial_output(
    ffmpeg_module, tmp_path, monkeypatch
):
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
