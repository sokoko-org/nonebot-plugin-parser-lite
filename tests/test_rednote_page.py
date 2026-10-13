import json

import httpx
import pytest
from render_test_support import pconfig

from nonebot_plugin_parser_lite.data import ImageContent
from nonebot_plugin_parser_lite.exception import ParseException
from nonebot_plugin_parser_lite.parsers.rednote import RedNoteParser
from nonebot_plugin_parser_lite.parsers.rednote.page_state import (
    NotePageUnavailable,
    note_page_state,
)


@pytest.mark.parametrize(
    ("url", "html"),
    [
        ("https://example.test/404", "<html>not found</html>"),
        ("https://example.test/login", "<html>login</html>"),
        ("https://example.test/note", "<html>security check</html>"),
        ("https://example.test/note", '<script>window.__INITIAL_STATE__={"noteData":{"data":{}}}</script>'),
        ("https://example.test/note", '<script>window.__INITIAL_STATE__={"noteData":{"data":{"noteData":{}}}}</script>'),
        ("https://example.test/note", "<script>window.__INITIAL_STATE__=undefined;</script>"),
    ],
)
def test_unavailable_note_has_readable_error(url, html):
    with pytest.raises(NotePageUnavailable, match="正文"):
        note_page_state(html, url)


def test_state_preserves_undefined_in_strings():
    raw = json.dumps({"noteData": {"data": {
        "noteData": {"title": 'undefined 与 "undefined"'}, "other": None,
    }}}).replace('"other": null', '"other": undefined')
    html = f"<script>window.__INITIAL_STATE__ = {raw};</script>"
    state = json.loads(note_page_state(html, "https://example.test/note"))
    assert state["noteData"]["data"]["noteData"]["title"] == 'undefined 与 "undefined"'
    assert state["noteData"]["data"]["other"] is None


@pytest.mark.asyncio
async def test_captcha_redirect_does_not_report_deleted_note():
    def response(request):
        if request.url.path == "/website-login/captcha":
            return httpx.Response(200, text="<html>captcha</html>")
        return httpx.Response(302, headers={"Location": "/website-login/captcha"})

    parser = RedNoteParser()
    await parser.aclose()
    parser.httpx = httpx.AsyncClient(
        transport=httpx.MockTransport(response), follow_redirects=True
    )
    try:
        keyword, searched = parser.search_url(
            "https://www.xiaohongshu.com/explore/123?xsec_token=test"
        )
        with pytest.raises(ParseException, match="验证码"):
            await parser.parse(keyword, searched)
    finally:
        await parser.aclose()


@pytest.mark.asyncio
async def test_note_parser_uses_consistent_safari_user_agent(monkeypatch):
    note = {
        "title": "真实笔记",
        "desc": "undefined 保留",
        "user": {"nickName": "作者", "avatar": "https://example.test/avatar", "userId": "1"},
        "lastUpdateTime": 1700000000000,
        "interactInfo": {"likedCount": "1", "collectedCount": "2", "commentCount": "0", "shareCount": "3"},
        "cover": {"fileId": "cover"},
        "imageList": [{"fileId": "image"}],
    }
    html = "<script>window.__INITIAL_STATE__ = " + json.dumps(
        {"noteData": {"data": {"noteData": note}}}
    ) + ";</script>"

    def response(request):
        assert "iPhone" in request.headers["User-Agent"]
        assert "Safari/" in request.headers["User-Agent"]
        assert "Edg/" not in request.headers["User-Agent"]
        assert request.url.params["xsec_token"] == "test="
        return httpx.Response(200, text=html)

    monkeypatch.setattr(pconfig, "plite_max_comments", 0)
    parser = RedNoteParser()
    await parser.aclose()
    parser.httpx = httpx.AsyncClient(transport=httpx.MockTransport(response))
    try:
        keyword, searched = parser.search_url(
            "https://www.xiaohongshu.com/discovery/item/123?xsec_token=test=&xsec_source=pc_share"
        )
        result = await parser.parse(keyword, searched)
        assert result.title == "真实笔记"
        assert result.author.name == "作者"
        assert sum(isinstance(item, ImageContent) for item in result.content) == 1
    finally:
        await parser.aclose()
