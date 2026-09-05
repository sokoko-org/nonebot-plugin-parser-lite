import base64
import gzip
import struct
from typing import TypeVar, cast
import uuid

from curl_cffi import AsyncSession
from google.protobuf.message import Message
import httpx

from .bilibili.metadata import metadata_pb2
from .bilibili.metadata.device import device_pb2
from .bilibili.metadata.fawkes import fawkes_pb2
from .bilibili.metadata.locale import locale_pb2
from .bilibili.metadata.network import network_pb2
from .bilibili.metadata.restriction import restriction_pb2

HEADERS = {
    "User-Agent": "Bilibili Freedoooooom/MarkII",
}

DALVIK_VERSION = "2.1.0"
OS_VERSION = "12"
BRAND = "Xiaomi"
MODEL = "2201123C"
APP_VERSION = "1.45.0"
BUILD = 1450000
CHANNEL = "bilibili140"
NETWORK_OID = "46007"
MOBI_APP = "android_hd"
PLATFORM = "android"
ENVIRONMENT = "prod"
APP_ID = 5
REGION = "CN"
LANGUAGE = "zh"
API_CHANNEL = "bili"
API_LOCALE = f"{LANGUAGE.lower()}_{REGION}"
API_STATISTICS = (
    f'{{"appId":{APP_ID},"platform":3,"version":"{APP_VERSION}","abtest":""}}'
)
GRPC_BASE_URL = "https://app.bilibili.com/"
GRPC_TIMEOUT = "20100m"
APPKEY = "dfca71928277209b"
APPSEC = "b5475a8825547a4fc26c7d518eaaa02e"

RequestT = TypeVar("RequestT", bound=Message)
ResponseT = TypeVar("ResponseT", bound=Message)


def generate_buvid() -> str:
    value = uuid.uuid4().hex + uuid.uuid4().hex
    return f"XY{value[:35].upper()}"


BUVID = generate_buvid()


def _base64_without_padding(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii").rstrip("=")


def get_bilibili_headers(
    access_token: str = "", user_mid: int | None = None
) -> dict[str, str]:
    """Build the headers"""
    device = device_pb2.Device(
        app_id=APP_ID,
        build=BUILD,
        buvid=BUVID,
        mobi_app=MOBI_APP,
        platform=PLATFORM,
        channel=CHANNEL,
        brand=BRAND,
        model=MODEL,
        osver=OS_VERSION,
    )
    locale = locale_pb2.Locale(
        c_locale=locale_pb2.LocaleIds(language=LANGUAGE, region=REGION),
        s_locale=locale_pb2.LocaleIds(language=LANGUAGE, region=REGION),
    )
    metadata = metadata_pb2.Metadata(
        access_key=access_token,
        mobi_app=MOBI_APP,
        build=BUILD,
        channel=CHANNEL,
        buvid=BUVID,
        platform=PLATFORM,
    )
    network = network_pb2.Network(
        type=network_pb2.NetworkType.WIFI,
        oid=NETWORK_OID,
    )
    fawkes = fawkes_pb2.FawkesReq(appkey=MOBI_APP, env=ENVIRONMENT)
    restriction = restriction_pb2.Restriction()
    headers = {
        "content-type": "application/grpc",
        "accept": "application/grpc",
        "user-agent": (
            f"Mozilla/5.0 BiliDroid/{APP_VERSION} (bbcallen@gmail.com) "
            f"os/{PLATFORM} model/{MODEL} mobi_app/{MOBI_APP} build/{BUILD} "
            f"channel/bili innerVer/{BUILD} osVer/{OS_VERSION} network/2"
        ),
        "app-key": MOBI_APP,
        "x-bili-device-bin": _base64_without_padding(device.SerializeToString()),
        "x-bili-fawkes-req-bin": _base64_without_padding(fawkes.SerializeToString()),
        "x-bili-locale-bin": _base64_without_padding(locale.SerializeToString()),
        "x-bili-metadata-bin": _base64_without_padding(metadata.SerializeToString()),
        "x-bili-network-bin": _base64_without_padding(network.SerializeToString()),
        "x-bili-restriction-bin": _base64_without_padding(
            restriction.SerializeToString()
        ),
        "grpc-accept-encoding": "identity,deflate,gzip",
        "grpc-timeout": GRPC_TIMEOUT,
        "env": ENVIRONMENT,
        "te": "trailers",
        "buvid": BUVID,
    }
    if access_token:
        headers["authorization"] = f"identify_v1 {access_token}"
        if user_mid is not None:
            headers["x-bili-mid"] = str(user_mid)
    return headers


class BiliGRPCError(Exception):
    def __init__(self, status: int, details: str) -> None:
        super().__init__(f"gRPC status {status}: {details}")
        self.status = status
        self.details = details


class BiliGRPCClient:
    """Unary gRPC-over-HTTP/2 client"""

    def __init__(
        self,
        base_url: str = GRPC_BASE_URL,
        *,
        proxy: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self._client = httpx.AsyncClient(
            http2=True,
            proxy=proxy,
            timeout=20.1,
            verify=True,
            trust_env=False,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )

    async def request(
        self,
        method: str,
        request: RequestT,  # pyright: ignore[reportInvalidTypeVarUse]
        response_type: type[ResponseT],
        *,
        access_token: str = "",
        user_mid: int | None = None,
    ) -> ResponseT:
        message = request.SerializeToString()
        body = b"\x00" + struct.pack(">I", len(message)) + message
        response = await self._client.post(
            self.base_url + method.lstrip("/"),
            content=body,
            headers=get_bilibili_headers(access_token, user_mid),
        )
        grpc_status = int(response.headers.get("grpc-status", "0"))
        if response.status_code >= 400 or grpc_status:
            details = (
                response.headers.get("grpc-message")
                or response.headers.get("bili-status-code")
                or response.text[:200]
                or f"HTTP {response.status_code}"
            )
            raise BiliGRPCError(grpc_status or 2, details)
        payload = response.content
        if len(payload) < 5:
            raise BiliGRPCError(13, "response is missing the gRPC frame header")
        compressed, size = struct.unpack(">BI", payload[:5])
        if len(payload) < size + 5:
            raise BiliGRPCError(13, "response gRPC frame is truncated")
        message = payload[5 : size + 5]
        if compressed:
            encoding = response.headers.get("grpc-encoding", "gzip").lower()
            if encoding != "gzip":
                raise BiliGRPCError(12, f"unsupported gRPC encoding: {encoding}")
            message = gzip.decompress(message)
        return cast(ResponseT, response_type.FromString(message))

    async def aclose(self) -> None:
        await self._client.aclose()


HTTP_CLIENT = AsyncSession(
    impersonate="chrome146",
    timeout=30.0,
    verify=True,
    trust_env=True,
    headers=HEADERS,
    allow_redirects=True,
    max_clients=40,
)
GRPC_CLIENT = BiliGRPCClient()


__all__ = [
    "API_CHANNEL",
    "API_LOCALE",
    "API_STATISTICS",
    "APPKEY",
    "APPSEC",
    "BUVID",
    "GRPC_BASE_URL",
    "GRPC_CLIENT",
    "HEADERS",
    "HTTP_CLIENT",
    "BiliGRPCClient",
    "BiliGRPCError",
    "generate_buvid",
    "get_bilibili_headers",
]
