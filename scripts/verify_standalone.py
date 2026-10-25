"""验证独立分支是否可以工作"""

import argparse
import asyncio
from importlib import import_module
from io import BytesIO
import json
from pathlib import Path
import shutil
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
        sys.path.insert(0, directory)
        asyncio.run(verify_pipeline())
    print("Standalone input and output checks passed")  # noqa: T201


async def verify_pipeline() -> None:
    package = import_module("nonebot_plugin_parser_lite")
    ParseStep = package.ParseStep
    Parser = package.Parser
    package.configure(plite_render_format="jpeg")
    url = "bilibili.com/video/BV1xx411c7mD"
    if not package.match(f"分享 https://www.{url} 给你").url.endswith(url):
        fail(["text matching returned an unexpected result"])

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
        if matched.url != url:
            fail(["match stage returned an unexpected URL"])
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
    else:
        print("Standalone static checks passed")  # noqa: T201


if __name__ == "__main__":
    main()
