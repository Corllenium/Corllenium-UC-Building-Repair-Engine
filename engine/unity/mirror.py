"""Route A: import an engine build in the mirror Unity project, headless, and return Unity's dump.

The owner's project is never touched. The run is refused when the mirror's copy of the owner's importer is stale.
Unity is stopped only by its own PID tree, and the dump's sidecar is written last by the exporter, so a dead run
never leaves a dump that reads as valid.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from tools.unity_mirror import MIRROR, check, owner_importer

DEFAULT_UNITY = Path("D:/SOFTWARE/UNITY/Unity Hub/Editor/6000.4.7f1/Editor/Unity.exe")
STAGE = "Assets/Models/Campus/_check"


class MirrorError(RuntimeError):
    """The mirror import could not produce a trustworthy dump."""


def _importer_ok():
    return check(MIRROR, owner_importer())


def _kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)   # by PID only


def _stage(build_obj: Path, name: str) -> Path:
    dst = MIRROR / STAGE / name
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    staged_obj = dst / f"{name}.obj"
    shutil.copyfile(build_obj, staged_obj)
    mtl = build_obj.with_suffix(".mtl")
    if not mtl.is_file() and (build_obj.parent / "materials.mtl").is_file():
        mtl = build_obj.parent / "materials.mtl"
    if mtl.is_file():
        shutil.copyfile(mtl, dst / f"{name}.mtl")
        if mtl.name != f"{name}.mtl":
            shutil.copyfile(mtl, dst / mtl.name)
    else:
        text = staged_obj.read_text(encoding="utf-8", errors="replace")
        mats = list(dict.fromkeys(
            line.split(None, 1)[1].strip()
            for line in text.splitlines()
            if line.startswith("usemtl ") and len(line.split(None, 1)) > 1
        ))
        if mats:
            if not any(line.startswith("mtllib ") for line in text.splitlines()):
                staged_obj.write_text(f"mtllib {name}.mtl\n" + text, encoding="utf-8")
            (dst / f"{name}.mtl").write_text(
                "".join(f"newmtl {m}\nKd 0.8 0.8 0.8\n\n" for m in mats),
                encoding="utf-8",
            )
    tex = build_obj.parent / "tex"
    if tex.is_dir():
        shutil.copytree(tex, dst / "tex")
    return dst


def mirror_import(build_obj: Path, out_dir: Path, *, overrides: dict | None = None,
                  unity_exe: Path | None = None, timeout_s: int = 1800) -> Path:
    ok, have, want = _importer_ok()
    if not ok:
        raise MirrorError(f"mirror importer copy is stale: mirror {have or '(none)'} != owner {want}; "
                          f"run tools/unity_mirror.py sync")
    exe = Path(unity_exe or os.environ.get("UC_UNITY_EXE", DEFAULT_UNITY))
    if not exe.is_file():
        raise MirrorError(f"Unity not found at {exe}")
    name = Path(build_obj).stem.replace(" ", "_")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{name}.*"):
        old.unlink()
    _stage(Path(build_obj), name)
    (MIRROR / "overrides.json").write_text(json.dumps(overrides or {}), encoding="utf-8")
    log = out_dir / f"{name}.unity.log"
    cmd = [str(exe), "-batchmode", "-nographics", "-quit", "-projectPath", str(MIRROR),
           "-executeMethod", "UcFloorExport.ExportFromCli", "-ucAsset", f"{STAGE}/{name}/{name}.obj",
           "-ucOut", str(out_dir), "-ucName", name, "-logFile", str(log)]
    proc = subprocess.Popen(cmd)
    try:
        code = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        raise MirrorError(f"Unity timed out after {timeout_s} s (killed PID {proc.pid} only)")
    tail = "\n".join(log.read_text(errors="replace").splitlines()[-40:]) if log.is_file() else "(no log)"
    if code != 0:
        raise MirrorError(f"Unity exited {code}:\n{tail}")
    dump = out_dir / f"{name}.obj"
    if not (out_dir / f"{name}.unity.json").is_file():
        raise MirrorError(f"Unity finished but wrote no sidecar:\n{tail}")
    return dump
