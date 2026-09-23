from collections.abc import Iterable
from dataclasses import dataclass
import json
import re
from typing import Any

from anyio import Path

from ..path import data_dir

THEME_SCHEMA_VERSION = 1
THEME_MANIFEST = "theme.json"
THEME_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
MUSIC_PLATFORMS = frozenset({"kugou", "netease", "kuwo", "qsmusic"})


class ThemeError(ValueError):
    """主题目录或清单无效"""


@dataclass(frozen=True, slots=True)
class ThemeManifest:
    """主题清单中对运行时有意义的字段"""

    id: str
    name: str
    version: str
    desc: str = ""
    author: str = ""


@dataclass(frozen=True, slots=True)
class ThemeTemplate:
    """最终选中的模板及其静态资源根目录"""

    name: str
    root: Path

    @property
    def base_url(self) -> str:
        return f"{self.root.as_uri().rstrip('/')}/"


@dataclass(frozen=True, slots=True)
class ThemeDefinition:
    """一个可渲染主题及其文件根目录"""

    manifest: ThemeManifest
    root: Path
    fallback_root: Path | None = None

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def desc(self) -> str:
        return self.manifest.desc

    @property
    def author(self) -> str:
        return self.manifest.author

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def base_url(self) -> str:
        """返回主题目录 URL"""
        return f"{self.root.as_uri().rstrip('/')}/"

    async def resolve_template(self, platform: str) -> ThemeTemplate:
        """按平台、音乐模板、主题默认模板和内置默认模板选择模板"""
        candidates = [f"{platform}.html.jinja" if platform else ""]
        if platform in MUSIC_PLATFORMS:
            candidates.append("music.html.jinja")
        candidates.append("default.html.jinja")

        for candidate in candidates:
            if not candidate or not _is_safe_relative_path(candidate):
                continue
            if await (self.root / candidate).is_file():
                return ThemeTemplate(candidate, self.root)

        if self.fallback_root is not None:
            default_template = self.fallback_root / "default.html.jinja"
            if await default_template.is_file():
                return ThemeTemplate("default.html.jinja", self.fallback_root)

        raise ThemeError(f"主题 {self.id!r} 缺少可用模板")

    async def template_for(self, platform: str) -> str:
        """返回选中模板文件名"""
        return (await self.resolve_template(platform)).name


class ThemeManager:
    """发现并选择内置或用户目录中的主题

    ``theme_dirs`` 中的目录既可以直接指向一个主题目录，也可以指向
    包含多个主题子目录的目录
    """

    def __init__(
        self,
        builtin_dir: str | Path,
        theme_dirs: Iterable[str | Path] = (),
    ) -> None:
        self.builtin_dir = Path(builtin_dir)
        roots = [Path(path) for path in theme_dirs]
        roots.append(data_dir / "themes")
        roots.append(self.builtin_dir)
        self.search_roots = tuple(roots)

    async def list_themes(self) -> list[ThemeDefinition]:
        """返回按搜索优先级去重后的主题列表"""
        builtin_root = await self.builtin_dir.resolve()
        themes: dict[str, ThemeDefinition] = {}
        for root in await _unique_paths(self.search_roots):
            for theme in await _discover_root(root, builtin_root):
                themes.setdefault(theme.id, theme)
        return list(themes.values())

    async def resolve(self, theme_id: str) -> ThemeDefinition:
        """按 ID 选择主题，找不到时回退到内置 default"""
        themes = {theme.id: theme for theme in await self.list_themes()}
        selected = themes.get(theme_id) or themes.get("default")
        if selected is None:
            raise ThemeError("未找到可用主题，也没有内置 default 主题")
        return selected


async def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        path = await (await path.expanduser()).resolve()
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


async def _discover_root(root: Path, builtin_root: Path) -> list[ThemeDefinition]:
    if not await root.is_dir():
        return []
    if await (root / THEME_MANIFEST).is_file():
        theme = await _load_theme(root, builtin_root)
        return [theme] if theme else []

    themes: list[ThemeDefinition] = []
    children = [child async for child in root.iterdir()]
    for child in sorted(children, key=lambda path: path.name):
        if await child.is_dir() and await (child / THEME_MANIFEST).is_file():
            theme = await _load_theme(child, builtin_root)
            if theme:
                themes.append(theme)
    return themes


async def _load_theme(root: Path, builtin_root: Path) -> ThemeDefinition | None:
    try:
        payload: Any = json.loads(
            await (root / THEME_MANIFEST).read_text(encoding="utf-8")
        )
        if not isinstance(payload, dict):
            raise ThemeError("主题清单必须是 JSON 对象")

        schema_version = payload.get("schema_version", THEME_SCHEMA_VERSION)
        if schema_version != THEME_SCHEMA_VERSION:
            raise ThemeError(
                f"不支持的主题数据版本: {schema_version!r}，"
                f"当前版本为 {THEME_SCHEMA_VERSION}"
            )

        theme_id = payload.get("id")
        if not isinstance(theme_id, str) or not THEME_ID_PATTERN.fullmatch(theme_id):
            raise ThemeError("主题 id 只能包含小写字母、数字、点、下划线和短横线")

        resolved_root = await root.resolve()
        return ThemeDefinition(
            manifest=ThemeManifest(
                id=theme_id,
                name=_string_field(payload, "name", theme_id),
                version=_string_field(payload, "version", "0.0.0"),
                desc=_string_field(payload, "desc", ""),
                author=_string_field(payload, "author", ""),
            ),
            root=resolved_root,
            fallback_root=None if resolved_root == builtin_root else builtin_root,
        )
    except (OSError, json.JSONDecodeError, ThemeError):
        # 单个损坏主题不应阻断内置主题和其他主题的发现。
        return None


def _string_field(payload: dict[str, Any], key: str, default: str) -> str:
    value = payload.get(key, default)
    return value if isinstance(value, str) and value else default


def _is_safe_relative_path(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts
