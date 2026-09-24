"""A small, Windows-safe atomic text write: write to a sibling `.tmp` file, then `os.replace` it
over the destination. `os.replace` is atomic on both POSIX and Windows, but on Windows it raises
`PermissionError` -- instead of the silent success POSIX gives -- when another process (an
editor, a virus scanner, a second CLI instance reading `batch_state.json`) has the destination
open for read. A handful of quick retries makes that transient reader a non-issue instead of a
crash.
"""
from __future__ import annotations

import os
import time
from pathlib import Path


def atomic_write_text(path, text: str, *, encoding: str = "utf-8", retries: int = 5,
                      retry_delay_s: float = 0.2, sleep=time.sleep) -> None:
    """Write `text` to `path` atomically: never leaves `path` holding a partial write, and never
    leaves the `.tmp` file behind on success. Retries `os.replace` up to `retries` times, sleeping
    `retry_delay_s` between attempts, when it raises `PermissionError`; re-raises on the last."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    for attempt in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            sleep(retry_delay_s)
