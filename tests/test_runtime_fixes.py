import asyncio

from bs4 import BeautifulSoup
from render_test_support import ROOT  # noqa: F401  初始化插件包导入环境

from nonebot_plugin_parser_lite.data import (
    Author,
    GraphicContent,
    ParseResult,
    Platform,
    PlatformEnum,
    VideoContent,
)
from nonebot_plugin_parser_lite.parsers.hupu.util import (
    parse_rich_content as parse_hupu,
)
from nonebot_plugin_parser_lite.parsers.linuxdo.util import (
    parse_rich_content as parse_linuxdo,
)
from nonebot_plugin_parser_lite.render import context
from nonebot_plugin_parser_lite.utils.format import is_inside


def _texts(items) -> str:
    return "".join(item for item in items if isinstance(item, str))


def test_is_inside_uses_identity():
    soup = BeautifulSoup("<p><a>hi</a>hi</p>", "html.parser")
    anchor = soup.a
    inner, outer = anchor.string, soup.p.contents[1]
    assert inner == outer
    assert is_inside(inner, anchor)
    assert not is_inside(outer, anchor)


def test_linuxdo_keeps_text_equal_to_quote_content():
    html = (
        '<aside class="quote"><blockquote><p>quoted</p></blockquote></aside>'
        "<p>same</p>"
    )
    assert "same" in _texts(parse_linuxdo(html))


def test_hupu_keeps_content_after_video():
    html = (
        '<p>before</p><video src="https://example.com/v.mp4" '
        'poster="https://example.com/c.jpg"></video>'
        '<p>after</p><img src="https://example.com/i.jpg">'
    )
    items = parse_hupu(html)
    assert "after" in _texts(items)
    assert any(isinstance(item, VideoContent) for item in items)
    assert any(isinstance(item, GraphicContent) for item in items)


class _SlowIcon:
    def __init__(self, delay: float, state: dict[str, int]):
        self.delay = delay
        self.state = state

    async def get_logo_path(self):
        self.state["active"] += 1
        self.state["peak"] = max(self.state["peak"], self.state["active"])
        await asyncio.sleep(self.delay)
        self.state["active"] -= 1


def test_render_resources_fetched_concurrently_with_limit():
    state = {"active": 0, "peak": 0}

    async def run():
        token = context._resource_limit.set(asyncio.Semaphore(3))
        try:
            await asyncio.gather(
                *(
                    context.safe_src(_SlowIcon(0.05, state), "get_logo_path")
                    for _ in range(10)
                )
            )
        finally:
            context._resource_limit.reset(token)

    asyncio.run(run())
    assert state["peak"] == 3


def test_serialize_result_keeps_content_order():
    result = ParseResult(
        platform=Platform(PlatformEnum.X, "X"),
        author=Author("tester"),
        url="https://example.com",
        content=["a", "b", "c"],
    )

    async def run():
        return await context._serialize_result(result, max_comments=0)

    post = asyncio.run(run())
    assert [item["text"] for item in post["content"]] == ["a", "b", "c"]


def test_bilibili_bare_av_defaults_to_first_page():
    from nonebot_plugin_parser_lite.parsers.bilibili import BilibiliParser

    _, searched = BilibiliParser.search_url("av170001")
    assert int(searched.get("p", 1)) == 1


def test_kuaishou_gifshow_url_keeps_host():
    from nonebot_plugin_parser_lite.parsers.kuaishou import KuaiShouParser

    keyword, searched = KuaiShouParser.search_url(
        "https://m.gifshow.com/fw/photo/3x123abc"
    )
    assert keyword == "m.gifshow.com"
    assert searched.url == "m.gifshow.com/fw/photo/3x123abc"


def test_bilibili_concurrent_credential_refresh_runs_once():
    from nonebot_plugin_parser_lite.parsers.bilibili import BilibiliParser

    class FakeCredential:
        access_token = "access"
        refresh_token = "refresh"

        def __init__(self):
            self.refresh_calls = 0
            self.stale = True

        def check_refresh(self) -> bool:
            return self.stale

        async def refresh(self) -> None:
            self.refresh_calls += 1
            await asyncio.sleep(0.05)
            self.stale = False

    async def run():
        parser = BilibiliParser()
        fake = FakeCredential()
        parser._credential = fake  # pyright: ignore[reportAttributeAccessIssue]

        async def save() -> None:
            return None

        parser._save_credential = save  # pyright: ignore[reportAttributeAccessIssue]
        try:
            await asyncio.gather(*(parser.credential for _ in range(5)))
        finally:
            await parser.aclose()
        return fake.refresh_calls

    assert asyncio.run(run()) == 1
