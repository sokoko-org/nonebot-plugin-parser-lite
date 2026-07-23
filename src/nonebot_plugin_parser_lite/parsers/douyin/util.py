"""从抖音 HTML 提取 React Flight / RSC 数据

Next.js 把页面数据塞进 self.__pace_f.push([...])。长字符串会被拆成
独立文本块（a:Txxxx, + 下一条 push），主 JSON 里只留 `$a` 这类引用。

ref https://github.com/vercel/next.js/discussions/42170
"""

import json
import re
from typing import Any

import json_repair

_PUSH_KEY = "self.__pace_f.push("
_TEXT_ANN = re.compile(r"^T([0-9a-fA-F]+),$")
_REF = re.compile(r"^\$([0-9a-zA-Z]+)$")
_SKIP_REF_PREFIXES = ("L", "S")
_SKIP_REF_IDS = frozenset({"undefined", "$", ""})
_JSON_STARTS = frozenset('{["')
_JS_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    '"': '"',
    "\\": "\\",
    "/": "/",
    "'": "'",
}
# note 路径：超过此长度且非 row7 / 非文本块正文时不反转义
_LARGE_RAW = 80_000


def _skip_ws(source: str, index: int) -> int:
    length = len(source)
    while index < length and source[index].isspace():
        index += 1
    return index


def _read_int(source: str, index: int) -> tuple[int, int]:
    start = index
    length = len(source)
    while index < length and source[index].isdigit():
        index += 1
    if start == index:
        raise ValueError(f"expected int at {index}: {source[index : index + 20]!r}")
    return int(source[start:index]), index


def _skip_comma(source: str, index: int) -> int:
    index = _skip_ws(source, index)
    if index < len(source) and source[index] == ",":
        index += 1
    return _skip_ws(source, index)


def _js_string_end(source: str, content_start: int) -> int:
    """返回闭引号下标；用 find 在 C 层跳转。"""
    index = content_start
    while True:
        quote_at = source.find('"', index)
        if quote_at < 0:
            raise ValueError("unterminated JS string in pace_f push")
        slash_at = source.find("\\", index)
        if slash_at < 0 or quote_at < slash_at:
            return quote_at
        index = slash_at + 2


def _js_unescape_manual(value: str) -> str:
    out: list[str] = []
    i = 0
    length = len(value)
    while i < length:
        char = value[i]
        if char != "\\" or i + 1 >= length:
            out.append(char)
            i += 1
            continue
        nxt = value[i + 1]
        if nxt in _JS_ESCAPES:
            out.append(_JS_ESCAPES[nxt])
            i += 2
        elif nxt == "u" and i + 5 < length:
            out.append(chr(int(value[i + 2 : i + 6], 16)))
            i += 6
        else:
            out.append(nxt)
            i += 2
    return "".join(out)


def _js_unescape(value: str) -> str:
    if "\\" not in value:
        return value
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return _js_unescape_manual(value)


def _loads(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return json_repair.loads(value, skip_json_loads=True)


def _maybe_load_json(value: str) -> Any:
    stripped = value.strip()
    if not stripped or stripped[0] not in _JSON_STARTS:
        return value
    try:
        return _loads(stripped)
    except Exception:
        return value


def _ingest_payload(
    rows: dict[str, Any], payload: str, pending_text_id: str | None
) -> str | None:
    """把一条 Flight payload 写入 rows，返回新的 pending 文本块 id"""
    if pending_text_id is not None:
        rows[pending_text_id] = payload
        return None

    lines = payload.split("\n")
    for line_index, line in enumerate(lines):
        if not line or ":" not in line:
            continue
        row_id, rest = line.split(":", 1)
        ann = _TEXT_ANN.fullmatch(rest)
        if not ann:
            rows[row_id] = rest
            continue

        expected = int(ann.group(1), 16)
        remaining = "\n".join(lines[line_index + 1 :])
        if remaining and len(remaining.encode("utf-8")) == expected:
            rows[row_id] = remaining
            return None
        return row_id
    return None


def parse_rsc_rows(html: str, *, keep_large: bool = False) -> dict[str, Any]:
    """解析 HTML 中 React Flight row

    :param keep_large: 是否保留与 note 无关的超大 JS 字符串反转义
        - `False` :跳过与 note 无关的超大 JS 字符串反转义。
        - `True`: 保留全部 row
    """
    rows: dict[str, Any] = {}
    pending_text_id: str | None = None
    start = 0
    key_len = len(_PUSH_KEY)
    html_len = len(html)

    while True:
        idx = html.find(_PUSH_KEY, start)
        if idx < 0:
            break

        index = _skip_ws(html, idx + key_len)
        if index >= html_len or html[index] != "[":
            start = idx + key_len
            continue

        try:
            index = _skip_ws(html, index + 1)
            typ, index = _read_int(html, index)
            index = _skip_comma(html, index)
            if index >= html_len or html[index] != '"':
                start = idx + key_len
                continue

            content_start = index + 1
            close_quote = _js_string_end(html, content_start)
            raw = html[content_start:close_quote]
            start = close_quote + 1

            if typ != 1:
                continue

            if (
                keep_large
                or pending_text_id is not None
                or len(raw) < _LARGE_RAW
                or raw.startswith("7:")
            ):
                pending_text_id = _ingest_payload(
                    rows, _js_unescape(raw), pending_text_id
                )
            else:
                continue

        except ValueError:
            start = idx + key_len

    if pending_text_id is not None:
        raise ValueError(f"RSC 文本块未闭合: id={pending_text_id}")
    return rows


def _should_resolve_ref(ref_id: str) -> bool:
    return ref_id not in _SKIP_REF_IDS and not ref_id.startswith(_SKIP_REF_PREFIXES)


def resolve_rsc_refs(
    obj: Any,
    rows: dict[str, Any],
    *,
    _seen: set[str] | None = None,
) -> Any:
    """递归解析 `$a` / `$8` 等引用"""
    if _seen is None:
        _seen = set()

    if isinstance(obj, dict):
        return {k: resolve_rsc_refs(v, rows, _seen=_seen) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_rsc_refs(v, rows, _seen=_seen) for v in obj]
    if not isinstance(obj, str):
        return obj

    matched = _REF.fullmatch(obj)
    if not matched:
        return obj

    ref_id = matched.group(1)
    if not _should_resolve_ref(ref_id) or ref_id not in rows or ref_id in _seen:
        return obj

    _seen.add(ref_id)
    try:
        value = rows[ref_id]
        if isinstance(value, str):
            value = _maybe_load_json(value)
        if isinstance(value, str):
            return value
        return resolve_rsc_refs(value, rows, _seen=_seen)
    finally:
        _seen.discard(ref_id)


def materialize_row(rows: dict[str, Any], row_id: str) -> Any:
    """取某一 row 并做解析和引用回填"""
    if row_id not in rows:
        raise KeyError(f"RSC row 不存在: {row_id}")
    raw = rows[row_id]
    value = _maybe_load_json(raw) if isinstance(raw, str) else raw
    return resolve_rsc_refs(value, rows)


def _is_opaque_row(raw: str) -> bool:
    stripped = raw.strip()
    return (
        stripped.startswith("I{")
        or stripped.startswith("$S")
        or stripped.startswith("$")
    )


def parse_rsc(html: str) -> dict[str, Any]:
    """解析页面全部 RSC row

    返回 ``{"rows": {id: raw}, "resolved": {id: value}}``
    """
    rows = parse_rsc_rows(html, keep_large=True)
    resolved: dict[str, Any] = {}
    for row_id, raw in rows.items():
        if not isinstance(raw, str) or _is_opaque_row(raw):
            resolved[row_id] = raw
            continue
        if raw.strip()[:1] in _JSON_STARTS:
            try:
                resolved[row_id] = materialize_row(rows, row_id)
            except Exception:
                resolved[row_id] = raw
        else:
            resolved[row_id] = raw
    return {"rows": rows, "resolved": resolved}


def _note_from_row_value(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and len(value) >= 4 and isinstance(value[3], dict):
        note = value[3]
    elif isinstance(value, dict):
        note = value
    else:
        raise ValueError(f"row 7 形态异常: {type(value).__name__}")
    if "aweme" not in note:
        raise ValueError("note 数据缺少 aweme 字段")
    return note


def extract_note_from_rsc(rsc: dict[str, Any]) -> dict[str, Any]:
    """从已解析 RSC 中取出 note (row 7)"""
    if "7" in rsc.get("resolved", {}):
        value = rsc["resolved"]["7"]
    elif "7" in rsc["rows"]:
        value = materialize_row(rsc["rows"], "7")
    else:
        raise ValueError("未找到 note 数据 row 7")
    return _note_from_row_value(value)


def parse_note_html(html: str) -> dict[str, Any]:
    """解析 note 页 HTML"""
    rows = parse_rsc_rows(html, keep_large=False)
    if "7" not in rows:
        raise ValueError("未找到 note 数据 row 7")
    return _note_from_row_value(materialize_row(rows, "7"))
