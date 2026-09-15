"""Check built distributions without importing the NoneBot plugin."""

from email.parser import BytesParser
from pathlib import Path
import re
import tarfile
import tomllib
from zipfile import ZipFile

from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "nonebot_plugin_parser_lite"


def verify() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    version = project["version"]
    original_init = (ROOT / "src" / PACKAGE / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'"version"\s*:\s*"([^"]+)"', original_init)
    assert match is not None
    assert Version(match[1]) == Version(version), "Plugin/package version mismatch"

    stem = f"{PACKAGE}-{version}"
    with ZipFile(ROOT / "dist" / f"{stem}-py3-none-any.whl") as wheel:
        _extracted_from_verify_13(wheel, stem, project)


# TODO Rename this here and in `verify`
def _extracted_from_verify_13(wheel, stem, project):
    assert not any(name.endswith((".proto", ".pyi")) for name in wheel.namelist())
    metadata = BytesParser().parsebytes(wheel.read(f"{stem}.dist-info/METADATA"))
    assert metadata["Name"] == project["name"]
    assert metadata["Requires-Python"] == project["requires-python"]
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    expected_dependencies = {
        str(Requirement(line))
        for line in requirements.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    actual_dependencies = {
        str(Requirement(value)) for value in metadata.get_all("Requires-Dist", [])
    }
    assert actual_dependencies == expected_dependencies, "Dependency mismatch"

    with tarfile.open(ROOT / "dist" / f"{stem}.tar.gz") as sdist:
        assert not any(name.endswith((".proto", ".pyi")) for name in sdist.getnames())
        assert f"{stem}/requirements.txt" in sdist.getnames()
        for path in (ROOT / "src" / PACKAGE).rglob("*"):
            if not path.is_file() or path.suffix not in {
                ".py",
                ".jinja",
                ".css",
                ".json",
                ".desc",
            }:
                continue
            relative = path.relative_to(ROOT / "src").as_posix()
            assert wheel.read(relative) == path.read_bytes(), relative
            member = sdist.extractfile(f"{stem}/src/{relative}")
            assert member is not None, relative
            assert member.read() == path.read_bytes(), relative


if __name__ == "__main__":
    verify()
