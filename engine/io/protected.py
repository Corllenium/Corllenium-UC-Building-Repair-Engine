"""The one output-path guard (AGENTS.md section 3): no writer puts a file in the CHECKPOINT-17 export, the owner's
campus master folder or the CHECKPOINT-17 backup. Every module and command that writes uses `refuse_protected`."""
from __future__ import annotations

import os

#: Folders nothing is ever written in, matched on the resolved path (upper case, backslashes).
PROTECTED = ("CHECKPOINT-17-BACKUP", r"PROJECTS\UC\02-SKETCHUP", "UC ENVIRONMENT BUILDING")


def refuse_protected(path) -> None:
    """Raise ValueError when `path` lies in a protected folder, judged on the resolved absolute path (so `..`, a
    relative path or a junction cannot get round it). Nothing is created or touched."""
    text = os.path.normcase(os.path.realpath(os.path.abspath(str(path)))).replace("/", "\\").upper()
    for p in PROTECTED:
        if p.upper() in text:
            raise ValueError(f"refusing to write {path}: it lies in a protected folder ({p})")
