"""Check built distributions without importing the NoneBot plugin."""

import argparse
from email.parser import BytesParser
from pathlib import Path
import tarfile
import tomllib
from zipfile import ZipFile

from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]


def verify(dist_dir: Path) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    version = project["version"]
    stem = f"{project['name'].replace('-', '_')}-{version}"
    wheels = list(dist_dir.glob(f"{stem}-*.whl"))
    sdists = list(dist_dir.glob(f"{stem}.tar.gz"))
    assert wheels or sdists, f"No distributions found for {stem}"
    requirements = project.get("dependencies")
    if requirements is None:
        requirements = (
            (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        )
    expected_dependencies = {
        str(Requirement(line))
        for line in requirements
        if line.strip() and not line.lstrip().startswith("#")
    }

    def verify_metadata(content: bytes) -> None:
        metadata = BytesParser().parsebytes(content)
        assert metadata["Name"] == project["name"]
        assert Version(metadata["Version"]) == Version(version)
        assert metadata["Requires-Python"] == project["requires-python"]
        assert {
            str(Requirement(value)) for value in metadata.get_all("Requires-Dist", [])
        } == expected_dependencies, "Dependency mismatch"

    for path in wheels:
        with ZipFile(path) as wheel:
            assert not any(
                name.endswith((".proto", ".pyi", ".rs", "Cargo.toml", "Cargo.lock"))
                for name in wheel.namelist()
            )
            verify_metadata(wheel.read(f"{stem}.dist-info/METADATA"))

    for path in sdists:
        with tarfile.open(path) as sdist:
            assert not any(
                name.endswith((".proto", ".pyi")) for name in sdist.getnames()
            )
            metadata = sdist.extractfile(f"{stem}/PKG-INFO")
            assert metadata is not None, "Source distribution metadata missing"
            verify_metadata(metadata.read())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    verify(parser.parse_args().dist_dir)
