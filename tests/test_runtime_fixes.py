from render_test_support import ROOT  # noqa: F401  初始化插件包导入环境

from nonebot_plugin_parser_lite.data import (
    GraphicContent,
    VideoContent,
)
from nonebot_plugin_parser_lite.parsers.hupu.util import (
    parse_rich_content as parse_hupu,
)
from nonebot_plugin_parser_lite.parsers.linuxdo.util import (
    parse_rich_content as parse_linuxdo,
)


def _texts(items) -> str:
    return "".join(item for item in items if isinstance(item, str))


def test_linuxdo_keeps_text_equal_to_quote_content():
    html = (
        '<aside class="quote"><blockquote><p>quoted</p></blockquote></aside>'
        "<p>quoted</p>"
    )
    assert "quoted" in _texts(parse_linuxdo(html))


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


def test_kuaishou_gifshow_url_keeps_host():
    from nonebot_plugin_parser_lite.parsers.kuaishou import KuaiShouParser

    keyword, searched = KuaiShouParser.search_url(
        "https://m.gifshow.com/fw/photo/3x123abc"
    )
    assert keyword == "m.gifshow.com"
    assert searched.url == "m.gifshow.com/fw/photo/3x123abc"
