"""验证独立分支是否可以工作"""

import argparse
import ast
import asyncio
import importlib.abc
from pathlib import Path
import re
import shutil
import sys
import tempfile


def is_nonebot_module(module: str) -> bool:
    top_level = module.split(".", 1)[0]
    return top_level != "nonebot_plugin_parser_lite" and (
        top_level == "nonebot" or top_level.startswith("nonebot_plugin_")
    )


def is_nonebot_distribution(name: str) -> bool:
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    return normalized == "nonebot2" or normalized.startswith("nonebot-plugin-")


def fail(messages: list[str]) -> None:
    if messages:
        raise SystemExit("Standalone verification failed:\n  " + "\n  ".join(messages))


def static_checks(root: Path) -> None:
    errors: list[str] = []
    package = root / "src/nonebot_plugin_parser_lite"
    for path in (package / "render", package / "utils/browser.py"):
        if path.exists() or path.is_symlink():
            errors.append(
                f"{path.relative_to(root)} is still present in the standalone tree"
            )
    generated_bilibili = package / "utils/bilibili/bilibili"
    for path in package.rglob("*.py"):
        if generated_bilibili in path.parents:
            continue
        if path.is_symlink() and not path.exists():
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            compile(source, str(path), "exec")
        except (SyntaxError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            errors.extend(
                f"{path.relative_to(root)}:{node.lineno} imports {module}"  # pyright: ignore[reportAttributeAccessIssue]
                for module in modules
                if is_nonebot_module(module)
            )
    for manifest in (root / "requirements.txt",):
        manifest_lines = manifest.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(manifest_lines, 1):
            stripped = line.strip().lower()
            if stripped.startswith("#"):
                continue
            name = re.split(r"[<>=!~\[; ]", stripped, maxsplit=1)[0]
            if is_nonebot_distribution(name):
                errors.append(f"{manifest.name}:{lineno} contains {line.strip()!r}")
            if name in {"jinja2", "playwright"}:
                errors.append(f"{manifest.name}:{lineno} contains rendering dependency")
    fail(errors)


class NoneBotBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        if is_nonebot_module(fullname):
            raise ModuleNotFoundError(f"blocked framework import: {fullname}")
        return None


def import_checks(root: Path) -> None:
    temporary_project = tempfile.TemporaryDirectory(prefix="parser-lite-copy-test-")
    project_root = Path(temporary_project.name)
    shutil.copytree(
        root / "src/nonebot_plugin_parser_lite",
        project_root / "nonebot_plugin_parser_lite",
    )
    sys.path.insert(0, str(project_root))
    sys.meta_path.insert(0, NoneBotBlocker())

    importlib.import_module("nonebot_plugin_parser_lite")

    unexpectedly_loaded = [
        name
        for name in sys.modules
        if name.startswith("nonebot_plugin_parser_lite.parsers.")
    ]
    fail([f"root import eagerly loaded {name}" for name in unexpectedly_loaded])

    package = importlib.import_module("nonebot_plugin_parser_lite")
    ParseStep = package.ParseStep
    Parser = package.Parser
    BilibiliParser = importlib.import_module(
        "nonebot_plugin_parser_lite.parsers.bilibili"
    ).BilibiliParser
    other_platforms = {
        name.split(".")[2]
        for name in sys.modules
        if name.startswith("nonebot_plugin_parser_lite.parsers.")
        and len(name.split(".")) > 2
        and name.split(".")[2] not in {"base", "bilibili"}
    }
    fail([f"single-platform import also loaded {name}" for name in other_platforms])

    if ParseStep.MATCH.value != "match":
        fail(["ParseStep export is invalid"])
    if any(step.value in {"resolve", "render"} for step in ParseStep):
        fail(["standalone parser still exposes rendering steps"])
    parser = Parser([BilibiliParser])
    matched = parser.match("分享 https://www.bilibili.com/video/BV1xx411c7mD 给你")
    if matched.parser_type is not BilibiliParser or "bilibili.com" not in matched.url:
        fail(["text matching returned an unexpected result"])
    discovered = Parser().match("分享 https://www.bilibili.com/video/BV1xx411c7mD 给你")
    if discovered.parser_type is not BilibiliParser:
        fail(["lazy all-platform discovery returned an unexpected parser"])
    try:
        parser.match(123)  # type: ignore[arg-type]
    except TypeError:
        pass
    else:
        fail(["non-text parser input was accepted"])

    base = importlib.import_module("nonebot_plugin_parser_lite.parsers.base")
    data = importlib.import_module("nonebot_plugin_parser_lite.data")
    parse_calls = 0

    class OfflinePlatform(data.Platform):
        async def get_logo_path(self):
            return None

    class OfflineParser(base.BaseParser):
        platform = OfflinePlatform(name="offline", display_name="Offline")

        @base.handle("example.test", r"https://example\.test/[^\s]+")
        async def parse_example(self, searched):
            nonlocal parse_calls
            parse_calls += 1
            return self.result(
                author=data.Author(name="tester"),
                url=searched.url,
                content=["offline-result"],
            )

    async def verify_parse_stage() -> None:
        async with Parser([OfflineParser]) as offline:
            text = "input https://example.test/item"
            result = await offline.parse(text)
            if result.content != ["offline-result"]:
                fail(["offline parse stage returned an unexpected result"])
            cached = await offline.parse(text)
            if cached is not result or parse_calls != 1:
                fail(["parse result cache did not reuse the first result"])
            scheduler = importlib.import_module(
                "nonebot_plugin_parser_lite.utils.scheduler"
            ).scheduler
            if "parser-clean-local-cache" not in scheduler.job_ids:
                fail(["periodic cache cleanup was not scheduled on the running loop"])
            package.clear_result_cache()
            await offline.parse(text)
            if parse_calls != 2:
                fail(["clearing the parse result cache had no effect"])

        await package.shutdown_runtime()

    asyncio.run(verify_parse_stage())

    for module in (
        "config",
        "data",
        "download",
        "helper",
        "matchers",
    ):
        importlib.import_module(f"nonebot_plugin_parser_lite.{module}")

    config = importlib.import_module("nonebot_plugin_parser_lite.config")
    paths = importlib.import_module("nonebot_plugin_parser_lite.path")
    if config.pconfig.data_dir != paths.data_dir:
        fail(["standalone config and path module use different data directories"])

    if any(is_nonebot_module(name) for name in sys.modules):
        fail(["a framework package was loaded during smoke imports"])
    temporary_project.cleanup()
    print("Standalone copy-only import and parser checks passed")  # noqa: T201


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--imports", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    static_checks(root)
    if args.imports:
        import_checks(root)
    else:
        print("Standalone static checks passed")  # noqa: T201


if __name__ == "__main__":
    main()
