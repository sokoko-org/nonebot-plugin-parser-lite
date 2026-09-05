from collections.abc import Iterable
from datetime import datetime

from msgspec import DecodeError, Struct, ValidationError
from msgspec.json import decode as decode_json

from ...creator import Creator
from ...data import ContentItem, ParseResult
from ...utils.bilibili.bilibili.app.dynamic.v2 import dynamic_pb2
from ...utils.bilibili.bilibili.app.dynamic.v2.dynamic_pb2 import (
    DescType,
    DynDetailReply,
)
from ...utils.format import format_num


class LivePlayInfo(Struct):
    room_id: int
    title: str
    cover: str
    link: str


class LiveRcmdContent(Struct):
    live_play_info: LivePlayInfo


def _parse_timestamp(label: str) -> int | None:
    try:
        date_label = label.split(" · ", 1)[0]
        return int(datetime.strptime(date_label, "%Y年%m月%d日 %H:%M").timestamp())
    except ValueError:
        return None


def _description_items(module_desc: dynamic_pb2.ModuleDesc) -> list[ContentItem]:
    items: list[ContentItem] = []
    for desc in module_desc.desc:
        if desc.type == DescType.desc_type_emoji:
            if url := desc.uri or desc.icon_url:
                items.append(
                    Creator.sticker(
                        url=url,
                        size="small" if desc.emoji_size == 1 else "medium",
                        desc=desc.text or None,
                    )
                )
                continue
        if desc.text:
            items.append(desc.text)

    return items or ([module_desc.text] if module_desc.text else [])


def _apply_stat(result: ParseResult, stat: dynamic_pb2.ModuleStat) -> None:
    if stat.repost:
        result.stats.share_count = format_num(stat.repost)
    if stat.like:
        result.stats.like_count = format_num(stat.like)
    if stat.reply:
        result.stats.comment_count = format_num(stat.reply)


def _video_url(bvid: str, avid: int) -> str | None:
    if bvid:
        return f"https://www.bilibili.com/video/{bvid}"
    return f"https://www.bilibili.com/video/av{avid}" if avid else None


def _append_archive(result: ParseResult, archive: dynamic_pb2.MdlDynArchive) -> None:
    if archive.title and result.title is None:
        result.title = archive.title
    if archive.jump_url.startswith("http"):
        result.url = archive.jump_url
    elif archive_url := _video_url(archive.bvid, archive.avid):
        result.url = archive_url
    if archive.cover:
        result.content.append(Creator.graphic(url=archive.cover))


def _text_node_items(
    nodes: Iterable[dynamic_pb2.TextNode],
) -> list[ContentItem]:
    """按 TextNode oneof 顺序渲染段落文本和表情"""
    items: list[ContentItem] = []
    text_buffer: list[str] = []

    def flush() -> None:
        if text_buffer:
            items.append("".join(text_buffer))
            text_buffer.clear()

    for node in nodes:
        kind = node.WhichOneof("text")
        if kind == "emote":
            flush()
            emote = node.emote
            if emote.emote_url:
                desc = emote.raw_text.words if emote.HasField("raw_text") else None
                items.append(Creator.sticker(emote.emote_url, "small", desc))
            elif emote.HasField("raw_text"):
                text_buffer.append(emote.raw_text.words)
            elif node.raw_text:
                text_buffer.append(node.raw_text)
        elif kind == "word":
            if node.word.words:
                text_buffer.append(node.word.words)
        elif kind == "link":
            text_buffer.append(_link_text(node))
        elif node.raw_text:
            text_buffer.append(node.raw_text)
    flush()
    return items


def _text_node_plain_text(nodes: Iterable[dynamic_pb2.TextNode]) -> str:
    """提取文本节点中的原始文字，并保留节点携带的换行。"""
    parts: list[str] = []
    for node in nodes:
        kind = node.WhichOneof("text")
        if kind == "word":
            parts.append(node.word.words)
        elif kind == "link":
            parts.append(_link_text(node))
        elif kind == "emote" and node.emote.HasField("raw_text"):
            parts.append(node.emote.raw_text.words)
        elif node.raw_text:
            parts.append(node.raw_text)
    return "".join(parts)


def _link_text(node: dynamic_pb2.TextNode) -> str:
    if node.link.show_text.words:
        return node.link.show_text.words
    return node.raw_text or node.link.link


def _append_paragraph(
    result: ParseResult,
    module_paragraph: dynamic_pb2.ModuleParagraph,
    *,
    paragraph_break: bool = False,
) -> None:
    if not module_paragraph.HasField("paragraph"):
        return
    paragraph = module_paragraph.paragraph
    content_type = paragraph.WhichOneof("content")
    if content_type == "text":
        if module_paragraph.is_article_title:
            if result.title is None:
                result.title = _text_node_plain_text(paragraph.text.nodes) or None
            return
        items = _text_node_items(paragraph.text.nodes)
        if paragraph_break:
            items.append("\n")
        result.content.extend(items)
    elif content_type == "pic":
        if paragraph.pic.HasField("pics"):
            for item in paragraph.pic.pics.items:
                if item.src:
                    result.content.append(Creator.image(url=item.src))
    elif content_type == "line" and paragraph.line.HasField("pic"):
        if paragraph.line.pic.src:
            result.content.append(Creator.image(url=paragraph.line.pic.src))


def _append_opus_summary(
    result: ParseResult, summary: dynamic_pb2.ModuleOpusSummary
) -> None:
    for paragraph in (summary.title, summary.summary):
        if paragraph and paragraph.WhichOneof("content") == "text":
            result.content.extend(_text_node_items(paragraph.text.nodes))
    for item in summary.covers:
        if item.src:
            result.content.append(Creator.image(url=item.src))


def _append_forward(
    result: ParseResult, payload: dynamic_pb2.MdlDynForward, seen: set[int]
) -> None:
    if not payload.HasField("item"):
        return
    repost = ParseResult(
        platform=result.platform,
        author=Creator.author(name=""),
        url="",
        content=[],
    )
    _build_item(repost, payload.item, seen)
    result.repost = repost
    if result.title is None:
        result.title = "转发动态"


def _append_pgc(result: ParseResult, payload: dynamic_pb2.MdlDynPGC) -> None:
    if payload.title and result.title is None:
        result.title = payload.title
    if payload.cover:
        result.content.append(Creator.image(url=payload.cover))


def _append_draw(result: ParseResult, payload: dynamic_pb2.MdlDynDraw) -> None:
    for item in payload.items:
        if item.src:
            result.content.append(Creator.image(url=item.src))


def _append_article(result: ParseResult, payload: dynamic_pb2.MdlDynArticle) -> None:
    if payload.title and result.title is None:
        result.title = payload.title
    if payload.desc:
        result.content.append(payload.desc)
    for cover in payload.covers:
        if cover:
            result.content.append(Creator.image(url=cover))


def _append_common(result: ParseResult, payload: dynamic_pb2.MdlDynCommon) -> None:
    if payload.title and result.title is None:
        result.title = payload.title
    if payload.desc:
        result.content.append(payload.desc)
    if payload.cover:
        result.content.append(Creator.image(url=payload.cover))


def _append_live(result: ParseResult, payload: dynamic_pb2.MdlDynLive) -> None:
    if payload.title and result.title is None:
        result.title = payload.title
    if payload.uri.startswith("http"):
        result.url = payload.uri
    elif payload.id:
        result.url = f"https://live.bilibili.com/{payload.id}"
    if payload.cover:
        result.content.append(Creator.graphic(url=payload.cover))


def _append_live_rcmd(result: ParseResult, payload: dynamic_pb2.MdlDynLiveRcmd) -> None:
    if not payload.content:
        return
    try:
        live = decode_json(payload.content, type=LiveRcmdContent)
    except (DecodeError, ValidationError):
        return
    info = live.live_play_info
    if info.title and result.title is None:
        result.title = info.title
    if info.link:
        result.url = info.link.split("?")[0]
    elif info.room_id:
        result.url = f"https://live.bilibili.com/{info.room_id}"
    if info.cover:
        result.content.append(Creator.graphic(url=info.cover))


def _append_music(result: ParseResult, payload: dynamic_pb2.MdlDynMusic) -> None:
    if payload.title and result.title is None:
        result.title = payload.title
    if payload.cover:
        result.content.append(Creator.image(url=payload.cover))


def _append_dynamic_payload(
    result: ParseResult,
    module_dynamic: dynamic_pb2.ModuleDynamic,
    seen: set[int],
) -> None:
    dynamic_type = module_dynamic.WhichOneof("module_item")
    if dynamic_type is None:
        return

    if dynamic_type == "dyn_forward":
        _append_forward(result, module_dynamic.dyn_forward, seen)
    elif dynamic_type == "dyn_archive":
        _append_archive(result, module_dynamic.dyn_archive)
    elif dynamic_type == "dyn_pgc":
        _append_pgc(result, module_dynamic.dyn_pgc)
    elif dynamic_type == "dyn_draw":
        _append_draw(result, module_dynamic.dyn_draw)
    elif dynamic_type == "dyn_article":
        _append_article(result, module_dynamic.dyn_article)
    elif dynamic_type == "dyn_common":
        _append_common(result, module_dynamic.dyn_common)
    elif dynamic_type == "dyn_common_live":
        _append_live(result, module_dynamic.dyn_common_live)
    elif dynamic_type == "dyn_live_rcmd":
        _append_live_rcmd(result, module_dynamic.dyn_live_rcmd)
    elif dynamic_type == "dyn_music":
        _append_music(result, module_dynamic.dyn_music)


def _build_item(
    result: ParseResult, item: dynamic_pb2.DynamicItem, seen: set[int]
) -> None:
    item_id = id(item)
    if item_id in seen:
        return
    seen.add(item_id)

    if item.HasField("extend"):
        extend = item.extend
        if extend.card_url.startswith("http"):
            result.url = extend.card_url
        elif extend.dyn_id_str:
            result.url = f"https://t.bilibili.com/{extend.dyn_id_str}"

    for module in item.modules:
        module_item = module.WhichOneof("module_item")
        if module_item == "module_author":
            author = module.module_author
            result.author = Creator.author(
                name=author.author.name,
                avatar_url=author.author.face,
                id=str(author.mid),
                avatar_cache_key=f"bilibili:{author.mid}",
            )
            if result.timestamp is None:
                result.timestamp = _parse_timestamp(author.ptime_label_text)
        elif module_item == "module_author_forward":
            author = module.module_author_forward
            name = "".join(title.text for title in author.title if title.text)
            result.author = Creator.author(
                name=name.removeprefix("@"),
                avatar_url=author.face_url,
                id=str(author.uid),
                avatar_cache_key=f"bilibili:{author.uid}",
            )
            if result.timestamp is None:
                result.timestamp = _parse_timestamp(author.ptime_label_text)
        elif module_item == "module_desc":
            result.content.extend(_description_items(module.module_desc))
        elif module_item == "module_dynamic":
            _append_dynamic_payload(result, module.module_dynamic, seen)
        elif module_item == "module_stat":
            _apply_stat(result, module.module_stat)
        elif module_item == "module_stat_forward":
            _apply_stat(result, module.module_stat_forward)
        elif module_item == "module_buttom":
            bottom = module.module_buttom
            if bottom.HasField("module_stat"):
                _apply_stat(result, bottom.module_stat)
        elif module_item == "module_opus_summary":
            _append_opus_summary(result, module.module_opus_summary)
        elif module_item == "module_paragraph":
            _append_paragraph(result, module.module_paragraph)


def build_dynamic(result: ParseResult, dyn: DynDetailReply) -> ParseResult:
    """Append a dynamic protobuf response to an existing parse result."""
    if dyn.HasField("item"):
        _build_item(result, dyn.item, set())
    return result
