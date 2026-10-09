"""The one output-path guard (AGENTS.md section 3): no writer puts a file in the CHECKPOINT-17 export, the owner's
campus master folder or the CHECKPOINT-17 backup. Every module and command that writes uses `refuse_protected`."""
from __future__ import annotations

import os
from pathlib import Path

#: Folders nothing is ever written in, matched on the resolved path (upper case, backslashes).
PROTECTED = ("CHECKPOINT-17-BACKUP", r"PROJECTS\UC\02-SKETCHUP", "UC ENVIRONMENT BUILDING")


def refuse_protected(path) -> None:
    """Raise ValueError when `path` lies in a protected folder, judged on the resolved absolute path (so `..`, a
    relative path or a junction cannot get round it). Nothing is created or touched."""
    text = os.path.normcase(os.path.realpath(os.path.abspath(str(path)))).replace("/", "\\").upper()
    for p in PROTECTED:
        if p.upper() in text:
            raise ValueError(f"refusing to write {path}: it lies in a protected folder ({p})")


def refuse_master(path) -> None:
    """The owner's campus model, under 02-SKETCHUP/current, is never opened (AGENTS.md). Used by
    `engine.io.skp_reader.walk_skp` itself and by `engine.campus.skp_check`."""
    parts = [p.lower() for p in Path(path).resolve().parts]
    if any(a == "02-sketchup" and b == "current" for a, b in zip(parts, parts[1:])):
        raise ValueError(f"refusing to open the CHECKPOINT-17 master (under 02-SKETCHUP/current): {path}")
