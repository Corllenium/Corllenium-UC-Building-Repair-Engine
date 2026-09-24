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
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path

import engine
from engine.io.atomic import atomic_write_text
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file

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
    # trailing fields, defaulted so older state files (without them) still load -- new fields
    # after `error` keep this dataclass's positional order stable for callers that rely on it.
    snapshot_dir: str = ""
    profile_sha256: str = ""


_RESULT_FIELDS = {f.name for f in fields(BatchResult)}


def discover_items(snapshot_root: Path, building: str) -> list[BatchItem]:
    """Every `ok`/`unlisted` row of `<snapshot_root>/<building>/ingest_manifest.json`."""
    path = Path(snapshot_root) / building / "ingest_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return [BatchItem(r["canonical"], Path(r["snapshot_dir"])) for r in manifest["rows"]
            if r["status"] in ("ok", "unlisted")]


def object_name(snapshot_dir: Path) -> str:
    """The folder name `cmd_fix` writes under: `read_obj`'s own name for the snapshot's single
    OBJ (its `o`/`g` line, falling back to the file stem) -- exactly what `cmd_fix` uses, so a
    hand-rolled parser here can never drift from it."""
    objs = sorted(Path(snapshot_dir).glob("*.obj"))
    if len(objs) != 1:
        raise ValueError(f"{snapshot_dir}: expected exactly one .obj file, found {len(objs)}")
    return read_obj(objs[0]).name


def run_fix_subprocess(snapshot_dir: Path, out_root: Path, profile_path: Path | None,
                       python: str = sys.executable) -> int:
    cmd = [python, "-m", "engine.cli", "fix", str(snapshot_dir), "--out", str(out_root)]
    if profile_path:
        cmd += ["--profile", str(profile_path)]
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_state(state_path: Path) -> dict[str, dict]:
    """The saved `objects` map, schema-checked and with any key a CURRENT `BatchResult` does not
    have dropped from each record -- so a state file a newer engine wrote (extra fields) still
    loads here instead of crashing the final `BatchResult(**record)` reconstruction."""
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if data.get("schema") != BATCH_SCHEMA:
        raise ValueError(f"{state_path}: expected schema {BATCH_SCHEMA!r}, found {data.get('schema')!r}")
    return {canonical: {k: v for k, v in rec.items() if k in _RESULT_FIELDS}
            for canonical, rec in data.get("objects", {}).items()}


def run_batch(items: list[BatchItem], out_root, jobs: int = 1, profile_path=None, state_path=None,
              resume: bool = True, runner=run_fix_subprocess) -> list[BatchResult]:
    out_root = Path(out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    profile_path = Path(profile_path).resolve() if profile_path else None
    profile_sha256 = sha256_file(profile_path) if profile_path else ""
    items = [replace(i, snapshot_dir=Path(i.snapshot_dir).resolve()) for i in items]
    state_path = Path(state_path).resolve() if state_path else out_root / "batch_state.json"

    # A5: refuse duplicate output names or duplicate canonicals BEFORE any work is submitted --
    # nothing runs and no state is written, so a batch never partially clobbers one output folder
    # with two different objects. An item whose name can't even be computed is not a duplicate of
    # anything -- it is left for `one()` to fail (and record) individually, exactly like any other
    # per-item error, instead of a single bad snapshot aborting validation for the whole batch.
    canonical_seen: set[str] = set()
    name_owner: dict[str, str] = {}
    for i in items:
        if i.canonical in canonical_seen:
            raise ValueError(f"duplicate canonical: {i.canonical!r}")
        canonical_seen.add(i.canonical)
        try:
            name = object_name(i.snapshot_dir)
        except Exception:
            continue
        if name in name_owner:
            raise ValueError(f"duplicate output name {name!r}: {name_owner[name]!r} and {i.canonical!r}")
        name_owner[name] = i.canonical

    state: dict[str, dict] = {}
    if resume and state_path.exists():
        state = _load_state(state_path)
    lock = threading.Lock()

    def save() -> None:
        atomic_write_text(state_path, json.dumps({"schema": BATCH_SCHEMA, "objects": state}, indent=2))

    def _is_still_valid(item: BatchItem) -> bool:
        """A recorded PASS is only trustworthy for resume when it is for the SAME snapshot and
        the SAME profile -- a record from an older engine, missing either key, is stale."""
        rec = state.get(item.canonical)
        if not rec:
            return False
        return (rec.get("exit_code") == 0 and rec.get("passed") is True
                and rec.get("snapshot_dir") == str(item.snapshot_dir)
                and rec.get("profile_sha256") == profile_sha256)

    todo = [i for i in items if not (resume and _is_still_valid(i))]
    stop_event = threading.Event()

    def one(item: BatchItem) -> None:
        started = _now()
        out_dir = ""     # A8: "" only until we actually know it
        code = -1         # A8: -1 only until the runner actually returns a real exit code
        try:
            out_dir = str(out_root / object_name(item.snapshot_dir))   # A1/A4: before launching
            report_path = Path(out_dir) / "report.json"
            report_path.unlink(missing_ok=True)   # A1: a stale PASS must never survive a crash
            code = runner(item.snapshot_dir, out_root, profile_path)
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
            passed = (code == 0) and bool(report.get("passed"))
            res = BatchResult(item.canonical, code, out_dir, passed, started, _now(),
                              snapshot_dir=str(item.snapshot_dir), profile_sha256=profile_sha256)
        except Exception as exc:
            res = BatchResult(item.canonical, code, out_dir, False, started, _now(),
                              error=f"{type(exc).__name__}: {exc}",
                              snapshot_dir=str(item.snapshot_dir), profile_sha256=profile_sha256)
        with lock:
            state[item.canonical] = asdict(res)
            save()

    def guarded(item: BatchItem) -> None:
        # A7: once a fatal (non-`Exception`) signal has stopped the batch, an item a worker
        # thread had already dequeued must not still launch a subprocess -- checking the flag
        # is the only way to make that true DETERMINISTICALLY: `ThreadPoolExecutor.shutdown(...,
        # cancel_futures=True)` below only reaches futures still sitting in the queue, and by the
        # time the main thread notices the failure and calls it, the SAME worker thread that just
        # raised may already have dequeued the next item.
        if stop_event.is_set():
            return
        try:
            one(item)
        except BaseException:
            stop_event.set()
            raise

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        try:
            for fut in as_completed([ex.submit(guarded, i) for i in todo]):
                fut.result()
        except BaseException:
            # Ctrl-C (or any other fatal signal a runner surfaces) stops the batch -- without
            # this, leaving the `with` block via an exception still runs the executor's default
            # `shutdown(wait=True)`, which drains every already-queued item to completion first.
            ex.shutdown(wait=False, cancel_futures=True)
            raise
    save()
    return [BatchResult(**state[i.canonical]) for i in items if i.canonical in state]
