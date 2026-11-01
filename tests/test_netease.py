import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock

import httpx
import pytest
from render_test_support import ROOT  # noqa: F401  初始化插件包导入环境

from nonebot_plugin_parser_lite.data import AudioContent, ImageContent
from nonebot_plugin_parser_lite.download import DOWNLOADER
from nonebot_plugin_parser_lite.exception import ParseException, TipException
from nonebot_plugin_parser_lite.parsers.netease import NCMParser

DETAIL_PATH = "/api/song/detail"
LYRIC_PATH = "/api/song/lyric"
OUTER_PATH = "/song/media/outer/url"

SONG = {
    "name": "Sand",
    "id": 28845027,
    "duration": 196000,
    "fee": 0,
    "artists": [{"name": "Keaton Henson", "id": 38078}],
    "album": {
        "name": "Sand",
        "picUrl": "https://p1.music.126.net/abc/5930765720666186.jpg",
    },
}
DETAIL = {"songs": [SONG], "code": 200}
AUDIO_LOCATION = (
    "http://m10.music.126.net/20261101190030/e0fd48/ymusic/8817/4264/"
    "cd2a46f2998bec881f89a03ec14cd860.mp3?vuutv=uvghhphjqbHn"
)
LYRIC = {"lrc": {"version": 1, "lyric": "[00:05.00]纯音乐，请欣赏\n"}, "code": 200}
SONG_URL = "https://music.163.com/song?id=28845027"

Handler = Callable[[httpx.Request], httpx.Response]


def resp(status: int, **kwargs) -> Handler:
    """按请求造新响应，同一对象不复用"""
    return lambda request: httpx.Response(status, **kwargs)


def detail_of(**song) -> Handler:
    return resp(200, json={**DETAIL, "songs": [{**SONG, **song}]})


@pytest.fixture
def serve(monkeypatch):
    clients: list[httpx.AsyncClient] = []

    def serve_to(
        *,
        detail: Handler | None = None,
        lyric: Handler | None = None,
        outer: Handler | None = None,
        size: int | None = 1024,
    ) -> tuple[NCMParser, list[httpx.Request]]:
        seen: list[httpx.Request] = []
        routes: dict[str, Handler] = {
            DETAIL_PATH: resp(200, json=DETAIL),
            LYRIC_PATH: resp(200, json=LYRIC),
            OUTER_PATH: resp(302, headers={"location": AUDIO_LOCATION}),
        }
        overrides = ((DETAIL_PATH, detail), (LYRIC_PATH, lyric), (OUTER_PATH, outer))
        for path, override in overrides:
            if override is not None:
                routes[path] = override

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            for path, build in routes.items():
                if request.url.path == path:
                    return build(request)
            raise AssertionError(f"未预期的请求 {request.method} {request.url}")

        parser = NCMParser()
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=True
        )
        parser.httpx = client
        clients.append(client)
        monkeypatch.setattr(DOWNLOADER, "head_size", AsyncMock(return_value=size))
        return parser, seen

    yield serve_to
    for client in clients:
        asyncio.run(client.aclose())


def parse(parser: NCMParser, url: str = SONG_URL):
    keyword, searched = NCMParser.search_url(url)
    return asyncio.run(parser.parse(keyword, searched))


def parse_error(parser: NCMParser, url: str = SONG_URL) -> Exception:
    try:
        parse(parser, url)
    except Exception as exc:
        return exc
    raise AssertionError("解析没有失败")


def test_only_official_music_163_endpoints_are_requested(serve):
    parser, seen = serve()
    assert parse(parser).title == "Sand"
    assert sorted({request.url.host for request in seen}) == ["music.163.com"]
    assert [request.url.path for request in seen] == [DETAIL_PATH, OUTER_PATH, LYRIC_PATH]


def test_detail_and_outer_query_shapes(serve):
    parser, seen = serve()
    parse(parser)
    detail, outer, lyric = seen
    assert detail.url.params.get("ids") == "[28845027]"
    assert lyric.url.params.get("id") == "28845027"
    assert lyric.url.params.get("lv") == "-1"
    assert outer.url.params.get("id") == "28845027.mp3"


def test_song_fields_map_to_audio_cover_and_lyric(serve):
    parser, _ = serve()
    result = parse(parser)
    audio, cover, lyric_text = result.content
    assert isinstance(audio, AudioContent)
    assert isinstance(cover, ImageContent)
    assert audio.path_task.url == AUDIO_LOCATION
    assert audio.duration == 196.0
    assert cover.path_task.url == "https://p1.music.126.net/abc/5930765720666186.jpg"
    assert lyric_text == "[00:05.00]纯音乐，请欣赏\n"
    assert result.author.name == "Keaton Henson"
    assert result.url == "https://music.163.com/song/28845027"
    assert result.extra["info"] == "大小: 1.00KB"


def test_relative_audio_location_is_resolved_against_the_api_host(serve):
    parser, _ = serve(outer=resp(302, headers={"location": "/ymusic/real.mp3"}))
    assert parse(parser).content[0].path_task.url == (  # pyright: ignore[reportAttributeAccessIssue]
        "https://music.163.com/ymusic/real.mp3"
    )


def test_multiple_artists_are_joined(serve):
    parser, _ = serve(
        detail=detail_of(artists=[{"name": "坂本真綾"}, {"name": "菅野よう子"}])
    )
    assert parse(parser).author.name == "坂本真綾、菅野よう子"


def test_unnamed_artist_is_skipped(serve):
    parser, _ = serve(detail=detail_of(artists=[{"name": "Keaton Henson"}, {"name": ""}]))
    assert parse(parser).author.name == "Keaton Henson"


def test_placeholder_song_falls_back_to_unknown_names(serve):
    parser, _ = serve(
        detail=detail_of(name=None, artists=[{"name": ""}], album=None, duration=None)
    )
    result = parse(parser)
    assert result.title == "未知"
    assert result.author.name == "未知歌手"
    assert result.content[0].duration == 0.0  # pyright: ignore[reportAttributeAccessIssue]
    assert [type(item) for item in result.content] == [AudioContent, str]


def test_missing_song_is_reported_as_tip(serve):
    parser, _ = serve(detail=resp(200, json={"songs": [], "code": 200}))
    assert isinstance(parse_error(parser), TipException)


def test_detail_body_error_is_not_reported_as_tip(serve):
    parser, _ = serve(detail=resp(200, json={"code": 400}))
    error = parse_error(parser)
    assert isinstance(error, ParseException)
    assert not isinstance(error, TipException)
    assert "400" in error.message


def test_detail_http_error_is_not_parsed_as_success(serve):
    parser, _ = serve(detail=resp(500, json=DETAIL))
    assert isinstance(parse_error(parser), httpx.HTTPStatusError)


@pytest.mark.parametrize(
    "location",
    [
        "http://music.163.com/404",
        "http://music.163.com/404/",
        "http://music.163.com/404?code=404",
        "http://music.163.com/404#audio",
        "/404",
        "//music.163.com/404",
    ],
)
def test_redirect_to_not_found_is_reported_as_tip(serve, location):
    parser, seen = serve(outer=resp(302, headers={"location": location}))
    assert isinstance(parse_error(parser), TipException)
    assert [request.url.path for request in seen] == [DETAIL_PATH, OUTER_PATH]


def test_paid_song_without_source_says_vip(serve):
    parser, _ = serve(
        detail=detail_of(fee=1),
        outer=resp(302, headers={"location": "http://music.163.com/404"}),
    )
    error = parse_error(parser)
    assert isinstance(error, TipException)
    assert "VIP" in error.message


def test_free_song_without_source_does_not_blame_vip(serve):
    parser, _ = serve(outer=resp(302, headers={"location": "http://music.163.com/404"}))
    assert "VIP" not in parse_error(parser).message


@pytest.mark.parametrize(
    "outer",
    [
        # 实测：该端点缺少 id 时回 200 + {"msg":"参数错误","code":400}，没有 Location
        resp(200, json={"msg": "参数错误", "code": 400}),
        resp(302, headers={"location": ""}),
        resp(403, text="forbidden"),
    ],
)
def test_audio_response_without_redirect_is_parse_error(serve, outer):
    parser, _ = serve(outer=outer)
    error = parse_error(parser)
    assert isinstance(error, ParseException)
    assert not isinstance(error, TipException)


def test_audio_endpoint_error_is_not_reported_as_copyright_tip(serve):
    parser, _ = serve(outer=resp(500, text="boom"))
    error = parse_error(parser)
    assert isinstance(error, ParseException)
    assert not isinstance(error, TipException)
    assert "500" in error.message


def test_lyric_http_error_is_not_trusted(serve):
    parser, _ = serve(lyric=resp(500, json=LYRIC))
    result = parse(parser)
    assert [type(item) for item in result.content] == [AudioContent, ImageContent]


def test_lyric_failure_keeps_audio_and_cover(serve):
    parser, _ = serve(lyric=resp(500, text="boom"))
    result = parse(parser)
    assert [type(item) for item in result.content] == [AudioContent, ImageContent]


def test_cover_missing_keeps_audio_and_lyric(serve):
    parser, _ = serve(detail=detail_of(album=None))
    result = parse(parser)
    assert [type(item) for item in result.content] == [AudioContent, str]


def test_unknown_size_still_produces_info(serve):
    parser, _ = serve(size=None)
    assert parse(parser).extra["info"] == "大小: 未知大小"


def test_mobile_song_path_resolves_same_id(serve):
    parser, seen = serve()
    assert parse(parser, "https://music.163.com/m/song?id=28845027").title == "Sand"
    assert seen[0].url.params.get("ids") == "[28845027]"
