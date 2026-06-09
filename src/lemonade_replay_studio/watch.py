from __future__ import annotations

import time
from pathlib import Path
from typing import Callable


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm"}


def wait_until_stable(path: Path, *, stable_seconds: float = 3.0, poll_seconds: float = 1.0) -> None:
    last_size = -1
    stable_for = 0.0
    while stable_for < stable_seconds:
        size = path.stat().st_size
        if size == last_size:
            stable_for += poll_seconds
        else:
            stable_for = 0.0
            last_size = size
        time.sleep(poll_seconds)


def watch_folder(
    folder: Path,
    *,
    on_file: Callable[[Path], None],
    poll_seconds: float = 2.0,
    once: bool = False,
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    seen = {path.resolve() for path in folder.iterdir() if path.is_file()}
    while True:
        current = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS]
        for path in current:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            wait_until_stable(path)
            on_file(path)
            if once:
                return
        time.sleep(poll_seconds)

