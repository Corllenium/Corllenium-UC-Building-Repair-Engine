"""Keep the mirror Unity project's copy of the owner's CampusModelImporter.cs identical to the real one.

The owner's project is READ only. The mirror refuses to check anything when its copy differs, so a change the owner
makes cannot leave the import check out of date.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

OWNER_PROJECT = Path("D:/PROJECTS/UC/01-UNITY/UC-Campus")
MIRROR = Path(__file__).resolve().parents[1] / "unity" / "ImportMirror"


def owner_importer() -> Path:
    return OWNER_PROJECT / "Assets" / "Editor" / "CampusModelImporter.cs"


def _sha(p: Path) -> str:
    # A UTF-8 BOM (which Unity may add or strip) must not change the hash; line endings do (CRLF kept byte-exact),
    # matching the C# exporter's File.ReadAllText -> UTF-8 bytes.
    return hashlib.sha256(p.read_bytes().decode("utf-8-sig").encode("utf-8")).hexdigest()


def _copy_path(mirror: Path) -> Path:
    return mirror / "Assets" / "Editor" / "CampusModelImporter.cs"


def sync(mirror: Path, owner: Path) -> str:
    dst = _copy_path(mirror)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(owner, dst)                     # reads the owner's file, writes only the mirror
    sha = _sha(dst)
    (mirror / "importer.sha256").write_text(sha + "\n", encoding="ascii")
    return sha


def check(mirror: Path, owner: Path) -> tuple[bool, str, str]:
    dst = _copy_path(mirror)
    have = _sha(dst) if dst.is_file() else ""
    want = _sha(owner)
    return have == want, have, want


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["sync", "check"])
    a = ap.parse_args(argv)
    if a.cmd == "sync":
        print(sync(MIRROR, owner_importer()))
        return 0
    ok, have, want = check(MIRROR, owner_importer())
    print(("OK " if ok else "STALE ") + f"mirror={have or '(none)'} owner={want}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
