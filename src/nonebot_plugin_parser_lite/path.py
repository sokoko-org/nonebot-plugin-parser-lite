import os
from pathlib import Path as SyncPath

from anyio import Path

base_dir = SyncPath(
    os.getenv("PARSER_LITE_BASE_DIR", SyncPath.cwd() / ".parser-lite")
).resolve()
cache_dir = Path(base_dir / "cache")
config_dir = Path(base_dir / "config")
data_dir = Path(base_dir / "data")
