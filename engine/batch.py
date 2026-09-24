"""Run `engine.cli fix` over every snapshot an ingest produced, one subprocess per object.

A subprocess per floor keeps the guard's memory (26 views of a 20k-triangle floor, plus the
solidify and merge passes) from accumulating across objects, and lets `jobs` floors run at once.
`batch_state.json` records every finished object so a re-run skips what already passed.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import engine

BATCH_SCHEMA = "corllenium.batch/1"
REPO_ROOT = Path(engine.__file__).resolve().parents[1]


@dataclass
class BatchItem:
    canonical: str
    snapshot_dir: Path


@dataclass
class BatchResult:
    canonical: str
    exit_code: int
    out_dir: str
    passed: bool
    started: str
    finished: str
    error: str = ""


def discover_items(snapshot_root: Path, building: str) -> list[BatchItem]:
    """Every `ok`/`unlisted` row of `<snapshot_root>/<building>/ingest_manifest.json`."""
    path = Path(snapshot_root) / building / "ingest_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return [BatchItem(r["canonical"], Path(r["snapshot_dir"])) for r in manifest["rows"]
            if r["status"] in ("ok", "unlisted")]


def object_name(snapshot_dir: Path) -> str:
    """The folder name `cmd_fix` writes under: the `o` name of the snapshot's single OBJ (the
    split export sets it to the file stem), falling back to the stem when there is no `o` line."""
    objs = sorted(Path(snapshot_dir).glob("*.obj"))
    if len(objs) != 1:
        raise ValueError(f"{snapshot_dir}: expected exactly one .obj file, found {len(objs)}")
    with objs[0].open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("o "):
                return line[2:].strip()
    return objs[0].stem


def run_fix_subprocess(snapshot_dir: Path, out_root: Path, profile_path: Path | None,
                       python: str = sys.executable) -> int:
    cmd = [python, "-m", "engine.cli", "fix", str(snapshot_dir), "--out", str(out_root)]
    if profile_path:
        cmd += ["--profile", str(profile_path)]
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_batch(items: list[BatchItem], out_root, jobs: int = 1, profile_path=None, state_path=None,
              resume: bool = True, runner=run_fix_subprocess) -> list[BatchResult]:
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    state_path = Path(state_path) if state_path else out_root / "batch_state.json"
    state: dict[str, dict] = {}
    if resume and state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8")).get("objects", {})
    lock = threading.Lock()

    def save() -> None:
        state_path.write_text(json.dumps({"schema": BATCH_SCHEMA, "objects": state}, indent=2),
                              encoding="utf-8")

    todo = [i for i in items if not (resume and state.get(i.canonical, {}).get("exit_code") == 0)]

    def one(item: BatchItem) -> None:
        started = _now()
        try:
            code = runner(item.snapshot_dir, out_root, profile_path)
            out_dir = out_root / object_name(item.snapshot_dir)
            report = out_dir / "report.json"
            passed = False
            if report.exists():
                passed = bool(json.loads(report.read_text(encoding="utf-8")).get("passed"))
            res = BatchResult(item.canonical, code, str(out_dir), passed, started, _now())
        except Exception as exc:
            res = BatchResult(item.canonical, -1, str(out_root / item.snapshot_dir.name), False,
                              started, _now(), error=f"{type(exc).__name__}: {exc}")
        with lock:
            state[item.canonical] = asdict(res)
            save()

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        for fut in as_completed([ex.submit(one, i) for i in todo]):
            fut.result()
    save()
    return [BatchResult(**state[i.canonical]) for i in items if i.canonical in state]
