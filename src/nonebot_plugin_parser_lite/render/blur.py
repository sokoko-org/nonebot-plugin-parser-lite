"""限制原生 CSS 模糊，并为长图分段计算保守的重叠范围。"""

from base64 import b64decode
from pathlib import Path
from typing import Any
from urllib.parse import unquote_to_bytes, urljoin, urlsplit
from urllib.request import url2pathname

from bs4 import BeautifulSoup
import tinycss2
from tinycss2.ast import AtRule, DimensionToken, FunctionBlock, NumberToken

MAX_BLUR_RADIUS = 128


class BlurStyles:
    """在 CSS 变量解析前包裹 blur 参数，实际约束交给 CSS clamp。"""

    def __init__(self, limit: int, resources: dict[str, bytes]):
        self.limit = limit
        self.resources = resources
        self.radius: float = 0
        self._visited: set[str] = set()

    def _rewrite(self, tokens: list[Any]) -> None:
        for token in tokens:
            if isinstance(token, FunctionBlock):
                if token.lower_name == "blur":
                    arguments = [
                        arg
                        for arg in token.arguments
                        if arg.type not in {"whitespace", "comment"}
                    ]
                    radius = self.limit
                    if not arguments:
                        radius = 0
                    elif len(arguments) == 1:
                        arg = arguments[0]
                        if isinstance(arg, DimensionToken) and arg.lower_unit == "px":
                            radius = min(self.limit, max(0, arg.value))
                        elif isinstance(arg, NumberToken) and arg.value == 0:
                            radius = 0
                    self.radius = max(self.radius, radius)
                    value = tinycss2.serialize(token.arguments) if arguments else "0px"
                    token.arguments = tinycss2.parse_component_value_list(
                        f"clamp(0px, {value}, {self.limit}px)"
                    )
                else:
                    self._rewrite(token.arguments)
            else:
                for attribute in ("prelude", "content"):
                    children = getattr(token, attribute, None)
                    if children:
                        self._rewrite(children)

    def _stylesheet(self, rules: list[Any], base_url: str) -> str:
        for rule in rules:
            if isinstance(rule, AtRule) and rule.lower_at_keyword == "import":
                args = [
                    token
                    for token in rule.prelude
                    if token.type not in {"whitespace", "comment"}
                ]
                if not args:
                    continue
                target = args[0]
                if isinstance(target, FunctionBlock) and target.lower_name == "url":
                    args = [
                        token for token in target.arguments if token.type == "string"
                    ]
                    if not args:
                        continue
                    target = args[0]
                if target.type in {"url", "string"}:
                    self._load(urljoin(base_url, target.value))
        self._rewrite(rules)
        return tinycss2.serialize(rules)

    def _load(self, url: str) -> None:
        if url in self._visited:
            return
        self._visited.add(url)
        data = self.resources.get(url)
        if data is None:
            parsed = urlsplit(url)
            if parsed.scheme == "file":
                path = url2pathname(parsed.path)
                if parsed.netloc and parsed.netloc != "localhost":
                    path = f"//{parsed.netloc}{path}"
                try:
                    data = Path(path).read_bytes()
                except OSError:
                    return  # 与 Blitz 一致，忽略不可读取的样式表。
            elif parsed.scheme == "data":
                header, separator, payload = url.partition(",")
                if not separator:
                    return
                data = unquote_to_bytes(payload)
                if header.lower().endswith(";base64"):
                    data = b64decode(data)
            else:
                return  # 渲染器不加载 HTTP(S) 资源。
        rules, encoding = tinycss2.parse_stylesheet_bytes(data)
        css = self._stylesheet(rules, url)
        self.resources[url] = css.encode(encoding.name)

    def apply(self, page: BeautifulSoup, base_url: str) -> None:
        base = page.find("base", href=True)
        if base:
            base_url = urljoin(base_url, str(base["href"]))
        for link in page.select('link[rel~="stylesheet"][href]'):
            self._load(urljoin(base_url, str(link["href"])))
        for style in page.find_all("style"):
            style.string = self._stylesheet(
                tinycss2.parse_stylesheet(style.get_text()), base_url
            )
        for element in page.select("[style]"):
            tokens = tinycss2.parse_component_value_list(str(element["style"]))
            self._rewrite(tokens)
            element["style"] = tinycss2.serialize(tokens)
