from collections.abc import Callable, Generator
import contextlib
from functools import partial

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)


@contextlib.contextmanager
def rich_progress(
    desc: str, total: int | None = None
) -> Generator[Callable[..., None], None, None]:
    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task_id = progress.add_task(description=desc, total=total)
        yield partial(progress.update, task_id)
