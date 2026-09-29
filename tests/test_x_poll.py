import asyncio
import json

from msgspec import convert
from render_test_support import ROOT

from nonebot_plugin_parser_lite.data import ImageContent, PollContent, QuoteContent
from nonebot_plugin_parser_lite.parsers.x import XParser
from nonebot_plugin_parser_lite.parsers.x.model import TweetEntry


def _entry(name: str) -> TweetEntry:
    raw = json.loads((ROOT / "api_txt/x" / name).read_text(encoding="utf-8"))
    return convert(raw["data"]["tweetResult"], TweetEntry)


def test_image_poll_and_translation():
    parser = XParser()
    parser.cookies = None
    result = asyncio.run(parser.collect_data(_entry("poll_image.json")))

    images = [item for item in result.content if isinstance(item, ImageContent)]
    assert not images
    polls = [item for item in result.content if isinstance(item, PollContent)]
    quotes = [item for item in result.content if isinstance(item, QuoteContent)]
    assert all(option.image is not None for option in polls[0].options)
    assert polls[0].options[0].image.url.endswith("name=orig")
    assert len(polls) == 1
    assert [option.votes for option in polls[0].options] == [654, 613, 568, 914]
    assert polls[0].options[0].text == "試着室"
    assert polls[0].closed
    assert polls[0].close_at is not None
    assert len(polls[0].close_at) == len("2026-09-28 01:40")
    assert len(quotes) == 1
    assert "如果要系列化的话" in quotes[0].text
    assert "1. 试衣间" in quotes[0].text


def test_translation_ignores_is_translatable_and_article():
    parser = XParser()
    entry = _entry("poll_image.json")
    tweet = entry.result.as_tweet
    tweet.is_translatable = False
    assert parser._should_translate(tweet, None)

    article = _entry("article.json").result.as_tweet
    article.legacy.lang = "en"
    assert not parser._should_translate(article, None)
