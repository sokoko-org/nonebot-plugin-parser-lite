"""生成独立分支"""

import argparse
import ast
from pathlib import Path
import re
import shutil

PACKAGE = Path("src/nonebot_plugin_parser_lite")
TEMPLATES = Path("scripts/standalone_templates")


def migration_log(message: str) -> None:
    print(f"[standalone] {message}")  # noqa: T201


def is_nonebot_module(module: str) -> bool:
    top_level = module.split(".", 1)[0]
    return top_level != "nonebot_plugin_parser_lite" and (
        top_level == "nonebot" or top_level.startswith("nonebot_plugin_")
    )


def is_nonebot_distribution(name: str) -> bool:
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    return normalized == "nonebot2" or normalized.startswith("nonebot-plugin-")


def replace_statement(text: str, node: ast.stmt, replacement: str) -> str:
    if node.end_lineno is None:
        raise RuntimeError("Python AST node has no end position")
    lines = text.splitlines(keepends=True)
    if replacement and not replacement.endswith("\n"):
        replacement += "\n"
    return (
        "".join(lines[: node.lineno - 1])
        + replacement
        + "".join(lines[node.end_lineno :])
    )


def assigned_names(node: ast.stmt) -> set[str]:
    if isinstance(node, ast.Assign):
        return {target.id for target in node.targets if isinstance(target, ast.Name)}
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    return set()


def ensure_config_imports(text: str) -> str:
    tree = ast.parse(text)
    imported_modules = {
        alias.asname or alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    typing_names = {
        alias.asname or alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "typing"
        for alias in node.names
    }
    imports = []
    if "json" not in imported_modules:
        imports.append("import json")
    if "os" not in imported_modules:
        imports.append("import os")
    if "Any" not in typing_names:
        imports.append("from typing import Any")
    if not imports:
        return text

    insertion_line = 0
    for node in tree.body:
        is_docstring = (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
        is_future = isinstance(node, ast.ImportFrom) and node.module == "__future__"
        if not (is_docstring or is_future):
            break
        insertion_line = node.end_lineno or insertion_line

    lines = text.splitlines(keepends=True)
    block = "\n".join(imports) + "\n\n"
    return "".join(lines[:insertion_line]) + block + "".join(lines[insertion_line:])


def copy_template(
    root: Path,
    template: str,
    destination: Path,
    replacements: dict[str, str] | None = None,
) -> None:
    source = root / TEMPLATES / template
    target = root / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    if replacements is None:
        shutil.copyfile(source, target)
    else:
        content = source.read_text(encoding="utf-8")
        for marker, value in replacements.items():
            content = content.replace(marker, value)
        target.write_text(content, encoding="utf-8")
    migration_log(f"写入独立实现: {destination.as_posix()}")


def rewrite_config(root: Path) -> None:
    path = root / PACKAGE / "config.py"
    text = path.read_text(encoding="utf-8")
    framework_names = {"get_driver", "get_plugin_config"}
    found_names: set[str] = set()
    tree = ast.parse(text, filename=str(path))
    framework_imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "nonebot"
    ]
    for node in reversed(framework_imports):
        removed = [alias for alias in node.names if alias.name in framework_names]
        if not removed:
            continue
        found_names.update(alias.name for alias in removed)
        remaining = [alias for alias in node.names if alias.name not in framework_names]
        replacement = ""
        if remaining:
            replacement = ast.unparse(
                ast.ImportFrom(module=node.module, names=remaining, level=node.level)
            )
        text = replace_statement(text, node, replacement)
    if found_names != framework_names:
        missing = ", ".join(sorted(framework_names - found_names))
        raise RuntimeError(f"{path}: missing NoneBot configuration imports: {missing}")

    text = ensure_config_imports(text)
    tree = ast.parse(text, filename=str(path))
    runtime_names = {"_driver", "pconfig", "gconfig", "_nickname"}
    runtime_indexes = [
        index
        for index, node in enumerate(tree.body)
        if assigned_names(node) & runtime_names
    ]
    if not runtime_indexes or all(
        "pconfig" not in assigned_names(node) for node in tree.body
    ):
        raise RuntimeError(f"{path}: could not locate configuration runtime")
    runtime_index = min(runtime_indexes)
    for node in tree.body[runtime_index:]:
        is_runtime_assignment = (
            bool(assigned_names(node)) and assigned_names(node) <= runtime_names
        )
        is_assignment_docstring = (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
        if not (is_runtime_assignment or is_assignment_docstring):
            raise RuntimeError(f"{path}: configuration runtime is not at end of module")

    footer = root / TEMPLATES / "config_footer.py.tmpl"
    runtime_line = tree.body[runtime_index].lineno - 1
    prefix = "".join(text.splitlines(keepends=True)[:runtime_line]).rstrip()
    text = prefix + "\n\n" + footer.read_text(encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    migration_log(f"迁移配置运行时: {path.relative_to(root).as_posix()}")


def rewrite_logging(root: Path) -> None:
    package = root / PACKAGE
    for path in package.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        original = text
        parent_parts = path.parent.relative_to(package).parts
        target_parts = ("utils", "log")
        common = 0
        for current, target in zip(parent_parts, target_parts, strict=False):
            if current != target:
                break
            common += 1
        level = len(parent_parts) - common + 1
        suffix = ".".join(target_parts[common:])
        module = "." * level + suffix
        tree = ast.parse(text, filename=str(path))
        logger_imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module in {"nonebot", "nonebot.log"}
            and any(alias.name == "logger" for alias in node.names)
        ]
        for node in sorted(logger_imports, key=lambda item: item.lineno, reverse=True):
            indent = text.splitlines()[node.lineno - 1][: node.col_offset]
            logger_alias = next(alias for alias in node.names if alias.name == "logger")
            logger_name = (
                f"logger as {logger_alias.asname}" if logger_alias.asname else "logger"
            )
            replacement_lines = []
            remaining = [alias for alias in node.names if alias.name != "logger"]
            if remaining:
                replacement_lines.append(
                    ast.unparse(
                        ast.ImportFrom(
                            module=node.module,
                            names=remaining,
                            level=node.level,
                        )
                    )
                )
            replacement_lines.append(f"from {module} import {logger_name}")
            replacement = "\n".join(f"{indent}{line}" for line in replacement_lines)
            text = replace_statement(text, node, replacement)
        path.write_text(text, encoding="utf-8")
        if text != original:
            migration_log(
                f"迁移日志导入: {path.relative_to(root).as_posix()} -> {module}"
            )


def rewrite_bilibili_scheduler(root: Path) -> None:
    path = root / PACKAGE / "parsers/bilibili/__init__.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    scheduler_blocks = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and any(
            isinstance(child, ast.ImportFrom)
            and child.module == "nonebot_plugin_apscheduler"
            for child in ast.walk(node)
        )
    ]
    if len(scheduler_blocks) != 1:
        raise RuntimeError(
            f"{path}: expected one NoneBot scheduler block, found "
            f"{len(scheduler_blocks)}"
        )
    block = scheduler_blocks[0]
    indent = text.splitlines()[block.lineno - 1][: block.col_offset]
    replacement = "\n".join(
        f"{indent}{line}" if line else ""
        for line in (
            "if not self._black_list_job_added:",
            "    from ...utils.scheduler import scheduler",
            "",
            "    scheduler.add_job(",
            "        self.load_black_list,",
            "        seconds=60 * 60,",
            '        id="sync-bili-black-list",',
            "    )",
            "    self._black_list_job_added = True",
            '    logger.info("已注册 B 站黑名单异步同步任务（每 1 小时刷新一次）")',
        )
    )
    text = replace_statement(text, block, replacement)
    path.write_text(text, encoding="utf-8")
    migration_log(
        f"迁移定时任务: {path.relative_to(root).as_posix()} -> asyncio scheduler"
    )


def remove_rendering_runtime(root: Path) -> None:
    targets = (
        root / PACKAGE / "render",
        root / PACKAGE / "utils/browser.py",
    )
    for target in targets:
        if not target.exists() and not target.is_symlink():
            continue
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
        migration_log(f"移除独立版渲染运行时: {target.relative_to(root).as_posix()}")


def rewrite_requirements(root: Path) -> list[str]:
    path = root / "requirements.txt"
    lines: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            lines.append(line)
            continue
        name = re.split(r"[<>=!~\[; ]", stripped, maxsplit=1)[0]
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if is_nonebot_distribution(name):
            migration_log(f"移除 NoneBot 依赖: {stripped}")
            continue
        seen.add(normalized)
        lines.append(stripped)

    direct = {
        "httpx": "httpx>=0.27.0,<1.0.0",
        "pydantic": "pydantic>=2.10.0,<3.0.0",
        "typing-extensions": "typing-extensions>=4.12.0",
        "yarl": "yarl>=1.9.0,<2.0.0",
    }
    for normalized, requirement in direct.items():
        if normalized not in seen:
            lines.append(requirement)
            migration_log(f"补充直接依赖: {requirement}")
    requirements = [
        line for line in lines if line and not line.lstrip().startswith("#")
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return requirements


def write_pyproject(root: Path, requirements: list[str], version: str) -> None:
    deps = "\n".join(f'  "{item}",' for item in requirements)
    content = (root / TEMPLATES / "pyproject.toml.tmpl").read_text(encoding="utf-8")
    (root / "pyproject.toml").write_text(
        content.replace("{{DEPENDENCIES}}", deps).replace("{{VERSION}}", version),
        encoding="utf-8",
    )
    migration_log("生成可安装元数据: pyproject.toml")


def audit(root: Path) -> None:
    violations: list[str] = []
    generated_bilibili = root / PACKAGE / "utils/bilibili/bilibili"
    for path in (root / PACKAGE).rglob("*.py"):
        if generated_bilibili in path.parents:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            violations.extend(
                f"{path.relative_to(root)}:{node.lineno}: {module}"  # pyright: ignore[reportAttributeAccessIssue]
                for module in modules
                if is_nonebot_module(module)
            )
    if violations:
        joined = "\n  ".join(violations)
        raise RuntimeError(f"standalone source still imports NoneBot:\n  {joined}")
    migration_log("审计通过: 未发现 NoneBot 模块导入")


def generate(root: Path) -> None:
    root = root.resolve()
    migration_log(f"开始迁移工作树: {root}")
    if not (root / PACKAGE / "parsers/base.py").is_file():
        raise RuntimeError(f"{root} is not a parser-lite main working tree")

    original_init = (root / PACKAGE / "__init__.py").read_text(encoding="utf-8")
    version_match = re.search(r'"version"\s*:\s*"([^"]+)"', original_init)
    if version_match is None:
        raise RuntimeError("could not determine the package version from __init__.py")
    version = version_match[1]

    rewrite_config(root)
    rewrite_logging(root)
    rewrite_bilibili_scheduler(root)
    remove_rendering_runtime(root)

    replacements = {
        "package_init.py.tmpl": PACKAGE / "__init__.py",
        "path.py.tmpl": PACKAGE / "path.py",
        "pipeline.py.tmpl": PACKAGE / "pipeline.py",
        "parsers_init.py.tmpl": PACKAGE / "parsers/__init__.py",
        "log.py.tmpl": PACKAGE / "utils/log.py",
        "scheduler.py.tmpl": PACKAGE / "utils/scheduler.py",
        "helper.py.tmpl": PACKAGE / "helper.py",
        "matchers_init.py.tmpl": PACKAGE / "matchers/__init__.py",
        "matchers_rule.py.tmpl": PACKAGE / "matchers/rule.py",
        "matchers_filter.py.tmpl": PACKAGE / "matchers/filter.py",
        "README.md.tmpl": Path("README.md"),
    }
    for template, destination in replacements.items():
        replacements = (
            {"{{VERSION}}": version}
            if "{{VERSION}}"
            in (root / TEMPLATES / template).read_text(encoding="utf-8")
            else None
        )
        copy_template(root, template, destination, replacements)

    requirements = rewrite_requirements(root)
    write_pyproject(root, requirements, version)
    audit(root)
    migration_log(f"迁移完成: {root}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    generate(args.root)


if __name__ == "__main__":
    main()
