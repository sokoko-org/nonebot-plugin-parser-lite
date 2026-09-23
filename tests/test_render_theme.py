import json

from jinja2 import Environment, FileSystemLoader
import pytest
from render_test_support import (
    ROOT,
    Author,
    ImageContent,
    ParseResult,
    Platform,
    PlatformEnum,
    Renderer,
    ResolvedPathTask,
    SyncPath,
    ThemeManager,
    build_theme_data,
)


@pytest.mark.asyncio
async def test_theme_manager_discovers_external_theme(tmp_path):
    theme_root = tmp_path / "custom"
    theme_root.mkdir()
    (theme_root / "theme.json").write_text(
        '{"schema_version": 1, "id": "custom", "name": "Custom", '
        '"desc": "测试主题", "author": "tester", "version": "2.0.0"}',
        encoding="utf-8",
    )
    (theme_root / "default.html.jinja").write_text("custom", encoding="utf-8")
    (theme_root / "music.html.jinja").write_text("music", encoding="utf-8")
    (theme_root / "netease.html.jinja").write_text("netease", encoding="utf-8")

    partial_root = tmp_path / "partial"
    partial_root.mkdir()
    (partial_root / "theme.json").write_text(
        '{"schema_version": 1, "id": "partial", "name": "Partial"}',
        encoding="utf-8",
    )
    (partial_root / "netease.html.jinja").write_text("netease", encoding="utf-8")

    manager = ThemeManager(
        ROOT / "src/nonebot_plugin_parser_lite/render/templates", # pyright: ignore[reportArgumentType]
        [tmp_path],
    )
    theme = await manager.resolve("custom")

    assert theme.id == "custom"
    assert theme.version == "2.0.0"
    assert theme.desc == "测试主题"
    assert theme.author == "tester"
    assert await theme.template_for("netease") == "netease.html.jinja"
    assert await theme.template_for("qsmusic") == "music.html.jinja"
    assert await theme.template_for("bilibili") == "default.html.jinja"

    partial = await manager.resolve("partial")
    selected = await partial.resolve_template("bilibili")
    assert selected.name == "default.html.jinja"
    assert str(selected.root) == str(
        (ROOT / "src/nonebot_plugin_parser_lite/render/templates").resolve()
    )
    selected_music = await partial.resolve_template("qsmusic")
    assert selected_music.name == "default.html.jinja"
    assert str(selected_music.root) == str(selected.root)

    default_theme = await manager.resolve("default")
    assert await default_theme.template_for("netease") == "default.html.jinja"
    assert (await Renderer()._resolve_theme()).id == "default"


@pytest.mark.asyncio
async def test_music_theme_data_uses_content_for_cover_and_plain_text(monkeypatch):
    async def logo_path(self):
        return SyncPath("logo.webp")

    monkeypatch.setattr(Platform, "get_logo_path", logo_path)
    result = ParseResult(
        platform=Platform(PlatformEnum.NETEASE, "网易云音乐"),
        author=Author("singer"),
        url="https://music.example.com/song/1",
        content=[
            ImageContent(
                path_task=ResolvedPathTask(SyncPath("cover.jpg")),  # type: ignore[arg-type]
            ),
            "[00:01.00]hello",
        ],
        extra={"album": "album"},
    )

    data = await build_theme_data(
        result,
        color_scheme="dark",
        theme_id="default",
        bot_name="bot",
        max_comments=5,
        append_qrcode=False,
    )

    assert [item["type"] for item in data["post"]["content"]] == [
        "cover",
        "text",
    ]
    assert data["post"]["content"][0]["alt"] == "专辑封面"
    assert data["post"]["content"][1]["text"] == "[00:01.00]hello"
    assert "lyric" not in data["post"]["extra"]
    assert data["post"]["extra"]["album"] == "album"


@pytest.mark.asyncio
async def test_builtin_icon_css_is_injected_before_theme_styles():
    html = '<html><head><link rel="stylesheet" href="icon.css" /></head></html>'
    rendered = await Renderer()._inject_fallback_icon_css(html)

    assert '<style data-parser-fallback="icon-css">' in rendered
    assert "--icon-color-view" in rendered
    assert rendered.index("data-parser-fallback") < rendered.index(
        'href="icon.css"'
    )


@pytest.mark.asyncio
async def test_theme_data_is_json_like(monkeypatch):
    async def logo_path(self):
        return SyncPath("logo.webp")

    monkeypatch.setattr(Platform, "get_logo_path", logo_path)
    result = ParseResult(
        platform=Platform(PlatformEnum.BILIBILI, "哔哩哔哩"),
        author=Author("tester"),
        url="https://example.com/post",
        content=[
            "hello",
            ImageContent(
                path_task=ResolvedPathTask(SyncPath("image.png")),  # type: ignore[arg-type]
            ),
        ],
    )

    data = await build_theme_data(
        result,
        color_scheme="dark",
        theme_id="default",
        bot_name="bot",
        max_comments=5,
        append_qrcode=False,
    )

    json.dumps(data)
    assert data["schema_version"] == 1
    assert data["theme"] == "dark"
    assert data["post"]["platform"] == {
        "id": "bilibili",
        "name": "哔哩哔哩",
        "logo": SyncPath("logo.webp").resolve().as_uri(),
    }
    assert [item["type"] for item in data["post"]["content"]] == [
        "text",
        "image",
    ]


@pytest.mark.asyncio
async def test_builtin_template_consumes_theme_data(monkeypatch):
    async def logo_path(self):
        return SyncPath("logo.webp")

    monkeypatch.setattr(Platform, "get_logo_path", logo_path)
    result = ParseResult(
        platform=Platform(PlatformEnum.BILIBILI, "哔哩哔哩"),
        author=Author("tester"),
        url="https://example.com/post",
        content=["hello"],
    )
    data = await build_theme_data(
        result,
        color_scheme="light",
        theme_id="default",
        bot_name="bot",
        max_comments=5,
        append_qrcode=False,
    )
    placeholder = "data:image/gif;base64,placeholder"
    data["post"]["stats"]["extra"] = [
        {"key": "coin", "label": "投币", "value": "2"}
    ]
    data["post"]["content"].extend(
        [
            {
                "type": "cover",
                "src": placeholder,
                "alt": "专辑封面",
                "layout": "grid",
                "is_live": False,
            },
            {"type": "text", "text": "[00:01.00]hello"},
            {"type": "image", "src": placeholder, "layout": "grid", "is_live": False},
            {
                "type": "live_photo",
                "src": placeholder,
                "layout": "grid",
                "is_live": True,
            },
            {"type": "graphic", "src": placeholder, "alt": "说明"},
            {"type": "sticker", "src": None, "size": "small", "description": "表情"},
            {"type": "video", "src": placeholder, "duration": "1:00", "size": "1MB"},
            {"type": "audio", "duration": "0:30", "size": "2MB"},
            {
                "type": "link",
                "url": "https://example.com/link",
                "title": "链接",
                "site_name": "站点",
                "description": "摘要",
                "icon": None,
                "preview": None,
            },
            {
                "type": "quote",
                "text": "引用",
                "title": "来源",
                "url": None,
                "icon": None,
            },
            {
                "type": "poll",
                "title": "投票",
                "options": [{"text": "A", "votes": 1, "percentage": 100.0}],
                "total_votes": 1,
                "total_voters": 1,
                "multiple": False,
                "closed": False,
            },
        ]
    )

    root = ROOT / "src/nonebot_plugin_parser_lite/render/templates"
    env = Environment(
        loader=FileSystemLoader(str(root)),
        enable_async=True,
        autoescape=False,
    )
    html = await env.get_template("default.html.jinja").render_async(data=data)

    assert "hello" in html
    assert "投票" in html
    assert "[00:01.00]hello" in html
