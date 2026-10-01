from bs4 import BeautifulSoup
import pytest
from render_test_support import ROOT

from nonebot_plugin_parser_lite.data import QuoteContent
from nonebot_plugin_parser_lite.parsers.douban.util import parse_rich_content as douban
from nonebot_plugin_parser_lite.parsers.heybox.model import extract_from_html as heybox
from nonebot_plugin_parser_lite.parsers.hupu.util import parse_rich_content as hupu
from nonebot_plugin_parser_lite.parsers.linuxdo.util import (
    parse_rich_content as linuxdo,
)
from nonebot_plugin_parser_lite.parsers.weibo.util import (
    weibo_long_html_to_raw as weibo,
)
from nonebot_plugin_parser_lite.utils.format import html_to_text, iter_html_content


@pytest.mark.parametrize("parser", [douban, heybox, hupu, weibo, html_to_text])
@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<p>A</p><blockquote><p>B</p></blockquote>", "A\nB"),
        ("<p>A<br><br>B</p>", "A\n\nB"),
        ("<p>A</p><blockquote><p><br><br>B</p></blockquote>", "A\n\nB"),
        ("<p><br>A<br></p>", "\nA\n"),
        ("<blockquote><p>A</p></blockquote>B", "A\nB"),
        ("<p>A</p>B", "A\nB"),
        ("<p>A<br></p><p>B</p>", "A\nB"),
    ],
)
def test_block_boundaries_and_explicit_line_breaks(parser, html, expected):
    result = parser(html)
    text = (
        result
        if isinstance(result, str)
        else "".join(item for item in result if isinstance(item, str))
    )
    assert text == expected


def test_html_image_boundary_keeps_explicit_breaks():
    result = douban('<p>A<br><br><img src="https://example.com/i.png"><br>B</p>')
    assert result[0] == "A\n\n"
    assert not isinstance(result[1], str)
    assert result[2] == "\nB"


def test_repository_hupu_sample_retains_each_link_as_one_paragraph():
    import json

    sample = json.loads((ROOT / "api_txt/hupu/topic.json").read_text())
    html = sample["offline_data"]["data"]["content"]
    anchors = BeautifulSoup(html, "html.parser").find_all("a")
    expected = [f"{a.get_text()} ({a['href']})" for a in anchors]
    result = hupu(html)
    assert (
        "".join(item for item in result if isinstance(item, str)).splitlines()
        == expected
    )


def test_closing_boundaries_do_not_leak_skipped_quote_content():
    result = linuxdo(
        '<aside class="quote"><blockquote><p>引用</p></blockquote></aside>'
        "<p>正文</p>后文"
    )
    quotes = [item for item in result if isinstance(item, QuoteContent)]
    assert len(quotes) == 1
    assert quotes[0].text == "引用"
    assert "".join(item for item in result if isinstance(item, str)) == "正文\n后文"


def test_html_traversal_preserves_original_tree():
    soup = BeautifulSoup("<blockquote><p>A</p></blockquote>B", "html.parser")
    original = str(soup)
    list(iter_html_content(soup))
    assert str(soup) == original
