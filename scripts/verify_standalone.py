"""验证独立分支是否可以工作"""

import argparse
from importlib import import_module
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def fail(messages: list[str]) -> None:
    if messages:
        raise SystemExit("Standalone verification failed:\n  " + "\n  ".join(messages))


def static_checks(root: Path) -> None:
    package = root / "src/nonebot_plugin_parser_lite"
    errors: list[str] = []
    for path in package.rglob("*.py"):
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
        except (SyntaxError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
    fail(errors)


def import_checks(root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="parser-lite-copy-test-") as directory:
        shutil.copytree(
            root / "src/nonebot_plugin_parser_lite",
            Path(directory) / "nonebot_plugin_parser_lite",
        )
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import asyncio, runpy, sys; sys.path.insert(0, sys.argv[1]); "
                "asyncio.run(runpy.run_path(sys.argv[2])['verify_pipeline']())",
                directory,
                str(Path(__file__).resolve()),
            ],
            check=True,
        )
    print("Standalone input and output checks passed")  # noqa: T201


def disable_checks(root: Path) -> None:
    """Disabled platforms must be skipped before they reach import_module."""
    program = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import nonebot_plugin_parser_lite as package; "
        "import nonebot_plugin_parser_lite.parsers as registry; "
        "package.configure(plite_disabled_platforms=[n for n in sys.argv[2].split(',') if n]); "
        "print(len(package.Parser()._types())); print(len(registry.__all__)); "
        "names = {m.split('.')[2] for m in sys.modules "
        "if m.startswith('nonebot_plugin_parser_lite.parsers.')}; "
        "print(','.join(sorted(n for n in sys.argv[3:] if n in names)))"
    )
    # Probed by module name, disabled by platform value: fiveeplay is "5eplay"
    probes = ("qqmusic", "fiveeplay")
    cases = (("", {"qqmusic", "fiveeplay"}), ("qqmusic,5eplay", set()))
    errors: list[str] = []
    for disabled, expected_loaded in cases:
        result = subprocess.run(
            [sys.executable, "-c", program, str(root / "src"), disabled, *probes],
            capture_output=True,
            text=True,
            check=False,
        )
        label = disabled or "none"
        if result.returncode != 0:
            errors.append(f"disabled={label}: {result.stderr.strip()[-160:]}")
            continue
        loaded, size, imported = (line.strip() for line in result.stdout.splitlines())
        expected = int(size) - len([name for name in disabled.split(",") if name])
        if int(loaded) != expected:
            errors.append(
                f"disabled={label}: loaded {loaded} of {size}, expected {expected}"
            )
        imported_names = {name for name in imported.split(",") if name}
        if imported_names != expected_loaded:
            errors.append(
                f"disabled={label}: imported {sorted(imported_names) or 'nothing'}, "
                f"expected {sorted(expected_loaded) or 'nothing'}"
            )
    # Disabling after a platform is already cached must still drop it from the
    # registry: sys.modules cannot be undone, so the skip has to cover cache hits.
    reload_program = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import nonebot_plugin_parser_lite as package; "
        "import nonebot_plugin_parser_lite.parsers as registry; "
        "print(len(registry.load_all())); "
        "package.configure(plite_disabled_platforms=['qqmusic', '5eplay']); "
        "types = registry.load_all(); print(len(types)); "
        "print(','.join(sorted(str(t.platform.name) for t in types "
        "if str(t.platform.name) in {'qqmusic', '5eplay'})))"
    )
    result = subprocess.run(
        [sys.executable, "-c", reload_program, str(root / "src")],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        errors.append(f"reload: {result.stderr.strip()[-160:]}")
    else:
        before, after, cached = (line.strip() for line in result.stdout.splitlines())
        if int(before) - int(after) != 2:
            errors.append(f"reload: {before} -> {after} parsers, expected 2 fewer")
        if cached:
            errors.append(f"reload: disabled platforms still returned: {cached}")
    fail(errors)
    print("Standalone disabled-platform checks passed")  # noqa: T201


async def verify_pipeline() -> None:
    package = import_module("nonebot_plugin_parser_lite")
    ParseStep = package.ParseStep
    Parser = package.Parser
    package.configure(plite_render_format="jpeg")
    for path in ("video/BV1xx411c7mD", "zh-Hans/video/BV1xx411c7mD"):
        matched = package.match(f"分享 https://www.bilibili.com/{path}?p=2 给你")
        if (
            matched.parser_type.platform.name != "bilibili"
            or matched.searched["bvid"] != "BV1xx411c7mD"
            or matched.params.get("p") != "2"
        ):
            fail(["text matching returned an unexpected video or page"])

    base = import_module("nonebot_plugin_parser_lite.parsers.base")
    data = import_module("nonebot_plugin_parser_lite.data")

    class OfflinePlatform(data.Platform):
        async def get_logo_path(self):
            return None

    class OfflineParser(base.BaseParser):
        platform = OfflinePlatform(name="offline", display_name="Offline")

        @base.handle("example.test", r"https://example\.test/[^\s]+")
        async def parse_example(self, searched):
            return self.result(
                author=data.Author(name="tester"),
                url=searched.url,
                content=["offline-result"],
            )

    async with Parser([OfflineParser]) as offline:
        url = "https://example.test/item"
        text = f"input {url}"
        matched = await offline.parse(text, until=ParseStep.MATCH)
        if matched.parser_type is not OfflineParser or matched.text != text:
            fail(["match stage returned an unexpected parser or input text"])
        result = await offline.parse(matched)
        if (
            result.url != url
            or result.author.name != "tester"
            or result.content != ["offline-result"]
        ):
            fail(["parse stage returned an unexpected result"])
        resolved = await offline.parse(result, until=ParseStep.RESOLVE)
        resolved = json.loads(json.dumps(resolved))
        if (
            resolved["post"]["url"] != url
            or resolved["post"]["author"]["name"] != "tester"
            or resolved["post"]["content"][0]["text"] != "offline-result"
        ):
            fail(["resolve stage returned unexpected rendering data"])
        rendered = await offline.parse(result, until=ParseStep.RENDER)
        from PIL import Image

        if rendered.result.url != url or rendered.result.content != ["offline-result"]:
            fail(["render stage did not preserve the parsed post"])
        with Image.open(BytesIO(rendered.image)) as image:
            image.load()
            if rendered.image_format != "jpeg" or image.format != "JPEG":
                fail(["render stage did not produce a valid JPEG image"])

        package.configure(plite_render_format="webp")
        rendered = await package.parse(
            text, until="render", parser_types=[OfflineParser], image_format="jpeg"
        )
        with Image.open(BytesIO(rendered.image)) as image:
            image.load()
            if rendered.image_format != "jpeg" or image.format != "JPEG":
                fail(["parse entry point did not produce a valid JPEG image"])

    await package.shutdown_runtime()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--imports", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    static_checks(root)
    if args.imports:
        import_checks(root)
        disable_checks(root)
    else:
        print("Standalone static checks passed")  # noqa: T201


if __name__ == "__main__":
    main()
