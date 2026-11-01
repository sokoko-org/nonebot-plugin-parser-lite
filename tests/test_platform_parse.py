"""平台整体解析测试：用真实 API 样本喂给 parser，只断言产出的 ParseResult 整体正确。

不验证请求 query 形状、不逐个覆盖错误分支，样本来自 api_txt/<平台>/。
"""

import asyncio

from api_fixture import attach, mock_transport, stub_head_size
import httpx
import pytest

from nonebot_plugin_parser_lite.data import (
    GraphicContent,
    ImageContent,
    MediaContent,
    ParseResult,
    VideoContent,
)


def _run(parser, url: str) -> ParseResult:
    keyword, searched = type(parser).search_url(url)
    try:
        return asyncio.run(parser.parse(keyword, searched))
    finally:
        asyncio.run(parser.httpx.aclose())


def test_wmpvp_post(monkeypatch):
    from nonebot_plugin_parser_lite.parsers.wmpvp import WMPVPParser

    stub_head_size(monkeypatch)
    parser = WMPVPParser()
    attach(
        parser,
        mock_transport(
            "wmpvp",
            [
                ("getPostById", "post.json"),
                ("getCommentList", "post_comment.json"),
            ],
        ),
    )
    result = _run(parser, "https://news.wmpvp.com/community-detail.html?id=375290247")

    assert result.title
    assert result.author.name
    assert any(isinstance(c, str) and c for c in result.content)


def test_wmpvp_video(monkeypatch):
    from nonebot_plugin_parser_lite.parsers.wmpvp import WMPVPParser

    stub_head_size(monkeypatch)
    parser = WMPVPParser()
    attach(
        parser,
        mock_transport(
            "wmpvp",
            [
                ("getPostById", "video.json"),
                ("getCommentList", "video_comment.json"),
            ],
        ),
    )
    result = _run(parser, "https://news.wmpvp.com/community-detail.html?id=376026294")

    assert result.title
    assert any(isinstance(c, VideoContent) for c in result.content)


def test_zhihu_article(monkeypatch):
    from nonebot_plugin_parser_lite.parsers.zhihu import ZhiHuParser

    stub_head_size(monkeypatch)
    parser = ZhiHuParser()
    attach(
        parser,
        mock_transport(
            "zhihu",
            [
                ("root_comment", "article_root_comment.json"),
                ("/articles/", "article.json"),
            ],
        ),
    )
    result = _run(parser, "https://zhuanlan.zhihu.com/p/123456789")

    assert result.title
    assert result.author.name
    assert result.comments


def test_weibo_status(monkeypatch):
    from nonebot_plugin_parser_lite.parsers.weibo import WeiBoParser
    from nonebot_plugin_parser_lite.parsers.weibo.auth import AuthHelper

    stub_head_size(monkeypatch)
    transport = mock_transport(
        "weibo",
        [
            ("statuses/show", "statused_text.json"),
            ("comments/hotflow", "statuses_comment.json"),
        ],
    )
    monkeypatch.setattr(AuthHelper, "SESSION", httpx.AsyncClient(transport=transport))
    monkeypatch.setattr(AuthHelper, "get_headers", staticmethod(_empty_headers))

    parser = WeiBoParser()
    result = asyncio.run(parser.parse_weibo_id("5212345678901234"))

    assert result.author.name
    assert result.content


async def _empty_headers() -> dict[str, str]:
    return {}


def test_weibo_image_status(monkeypatch):
    from nonebot_plugin_parser_lite.parsers.weibo import WeiBoParser
    from nonebot_plugin_parser_lite.parsers.weibo.auth import AuthHelper

    stub_head_size(monkeypatch)
    transport = mock_transport(
        "weibo",
        [
            ("statuses/show", "statuses_image.json"),
            ("statuses/extend", "statuses_long.json"),
            ("comments/hotflow", "statuses_comment.json"),
        ],
    )
    monkeypatch.setattr(AuthHelper, "SESSION", httpx.AsyncClient(transport=transport))
    monkeypatch.setattr(AuthHelper, "get_headers", staticmethod(_empty_headers))

    parser = WeiBoParser()
    result = asyncio.run(parser.parse_weibo_id("5212345678901234"))

    media = [c for c in result.content if isinstance(c, MediaContent)]
    assert any(isinstance(c, ImageContent) for c in media)


@pytest.fixture(autouse=True)
def _restore_weibo_session():
    yield
    from nonebot_plugin_parser_lite.parsers.weibo.auth import AuthHelper

    asyncio.run(AuthHelper.SESSION.aclose())


def test_taptap_image_moment(monkeypatch):
    from nonebot_plugin_parser_lite.parsers.taptap import TapTapParser

    stub_head_size(monkeypatch)
    parser = TapTapParser()
    attach(
        parser,
        mock_transport(
            "taptap",
            [
                ("moment/v3/detail", "moment_image.json"),
                ("moment-comment", "comment.json"),
            ],
        ),
    )
    result = _run(parser, "https://www.taptap.cn/moment/123456")

    assert result.author.name
    assert any(isinstance(c, ImageContent) for c in result.content)


def test_taptap_video_moment(monkeypatch):
    from nonebot_plugin_parser_lite.parsers.taptap import TapTapParser

    stub_head_size(monkeypatch)
    parser = TapTapParser()
    attach(
        parser,
        mock_transport(
            "taptap",
            [
                ("moment/v3/detail", "moment_video.json"),
                ("video-resource", "video.json"),
                ("moment-comment", "comment.json"),
            ],
        ),
    )
    result = _run(parser, "https://www.taptap.cn/moment/123456")

    assert any(isinstance(c, VideoContent) for c in result.content)


def test_x_tweet(monkeypatch):
    from nonebot_plugin_parser_lite.parsers.x import XParser

    stub_head_size(monkeypatch)
    parser = XParser()
    parser.cookies = None
    attach(
        parser,
        mock_transport(
            "x",
            [("TweetResultByRestId", "poll_image.json")],
        ),
    )
    monkeypatch.setattr(
        XParser, "ensure_guest_token", _guest_token, raising=False
    )
    result = _run(parser, "https://x.com/someone/status/123456")

    assert result.author.name
    assert result.content


async def _guest_token(self) -> str:
    return "guest"


def test_douban_horizontal_topic(monkeypatch):
    from nonebot_plugin_parser_lite.parsers.douban import DoubanParser

    stub_head_size(monkeypatch)
    parser = DoubanParser()
    attach(
        parser,
        mock_transport(
            "douban",
            [
                ("/comments", "comment_text.json"),
                ("/topic/", "horizontal.json"),
            ],
        ),
    )
    result = _run(parser, "https://m.douban.com/group/topic/490753319")

    assert result.title
    assert result.author.name
    assert result.timestamp
    assert any(isinstance(c, ImageContent) for c in result.content)


def test_douban_vertical_topic(monkeypatch):
    from nonebot_plugin_parser_lite.parsers.douban import DoubanParser

    stub_head_size(monkeypatch)
    parser = DoubanParser()
    attach(
        parser,
        mock_transport(
            "douban",
            [
                ("/comments", "comment_pic.json"),
                ("/topic/", "vertical.json"),
            ],
        ),
    )
    result = _run(parser, "https://m.douban.com/group/topic/472573751")

    assert result.title
    assert any(isinstance(c, GraphicContent) for c in result.content)
    assert result.comments
