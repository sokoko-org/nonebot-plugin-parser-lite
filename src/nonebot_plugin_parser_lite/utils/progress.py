import threading
from rich.progress import (
    Progress,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TaskID as TaskID,
)


class ProgressManager:
    _instance = None
    _lock = threading.Lock()
    _active_tasks = 0

    @classmethod
    def get_progress(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = Progress(
                        "[progress.description]{task.description}",
                        BarColumn(),
                        "[progress.percentage]{task.percentage:>3.0f}%",
                        DownloadColumn(),
                        TransferSpeedColumn(),
                        TimeElapsedColumn(),
                        TimeRemainingColumn(),
                        auto_refresh=True,
                    )
        return cls._instance

    @classmethod
    def start_task(cls):
        with cls._lock:
            if cls._active_tasks == 0:
                cls.get_progress().start()
            cls._active_tasks += 1

    @classmethod
    def stop_task(cls):
        with cls._lock:
            cls._active_tasks -= 1
            if cls._active_tasks <= 0:
                cls.get_progress().stop()
                cls._active_tasks = 0
