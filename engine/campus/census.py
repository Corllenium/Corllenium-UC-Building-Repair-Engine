"""Census of what is wrong with every floor/element unit before fixing (spec 2026-10-03, P0 task 12).

Records:
- `find_errors` counts;
- stage timings (topology, exposure, double_layers, fragments, assemble);
- peak memory (Windows PeakWorkingSetSize through ctypes);
- machine load (other python.exe and msedge.exe processes, CPU times via GetSystemTimes);
- flicker split: pairs x {same look, diff look} x {opposite, same facing};
- fix plan per unit: order E8 -> E3 -> E1 -> E2 -> E4 -> E5 -> E6 -> E7.

Outputs:
- census.json
- errors/<unit>.json (format matching engine.cli errors)
- census.md (markdown table)
"""
from __future__ import annotations

import argparse
import collections
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence

from engine.detectors.errors import find_errors
from engine.io.obj_reader import read_obj
from engine.model import MeshData
from engine.io.protected import refuse_protected
from engine.campus.materials import _material_name as _mat_name, split_flicker_pairs
from engine.campus.winprobe import get_machine_load, get_process_peak_memory_mb


# ---------------------------------------------------------------------- Building Classifier


def unit_building(unit_name: str) -> str:
    """Infer building name from unit or snapshot name using inventory prefix table."""
    from engine.campus.inventory import building_of
    return building_of(unit_name)


# ---------------------------------------------------------------------- Flicker Split


#: relative to the working directory, as every other campus command's defaults (run from the main checkout,
#: which holds data/; from a worktree pass --materials)
DEFAULT_MATERIALS_PATH = Path("data/campus/materials.json")


class FlickerSplit(dict):
    """Flicker split counts by {same look, diff look} x {opposite, same facing}."""

    def __getitem__(self, key: str) -> Any:
        if key == "same_look_same_facing":
            return super().__getitem__("same_look_same")
        if key == "diff_look_same_facing":
            return super().__getitem__("diff_look_same")
        if key == "same_look":
            return super().__getitem__("same_look_opposite") + super().__getitem__("same_look_same")
        if key == "diff_look":
            return super().__getitem__("diff_look_opposite") + super().__getitem__("diff_look_same")
        if key == "total":
            return sum(super().values())
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


def flicker_split(
    mesh: MeshData,
    pairs: list | None = None,
    materials: dict | Path | str | None = None,
) -> FlickerSplit:
    """Partition flicker pairs into 4 buckets by material look and winding."""
    pair_list = pairs
    if pair_list is None:
        errs = find_errors(mesh)
        pair_list = errs.get("flicker_pairs", [])

    materials_map: dict[str, Any]
    if isinstance(materials, dict):
        materials_map = materials.get("materials", materials)
    elif materials is not None:
        mat_path = Path(materials)
        if not mat_path.is_file():
            raise FileNotFoundError(f"Materials map not found: {mat_path.resolve()} (pass --materials)")
        data = json.loads(mat_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Invalid materials JSON in {mat_path}")
        materials_map = data.get("materials", data)
    else:
        mat_path = DEFAULT_MATERIALS_PATH
        if not mat_path.is_file():
            raise FileNotFoundError(f"Default materials map not found: {mat_path}")
        data = json.loads(mat_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Invalid materials JSON in {mat_path}")
        materials_map = data.get("materials", data)

    if not isinstance(materials_map, dict):
        raise ValueError("Materials map is not a dictionary")
    if not materials_map:
        raise ValueError("Materials map is empty")

    for name in {_mat_name(mesh, f) for item in pair_list for f in (item[0], item[1])}:
        if name not in materials_map:
            raise KeyError(f"Material {name!r} not found in materials map")
        info = materials_map[name]
        if not (info.get("look") if isinstance(info, dict) else info):
            raise ValueError(f"Material {name!r} has no 'look' in materials map")

    # the look split itself is the shared one (engine.campus.materials), which E4/E5 and the colour export use
    same_pairs, diff_pairs = split_flicker_pairs(mesh, pair_list, materials_map)
    same_opp = sum(1 for item in same_pairs if bool(item[3]))
    same_same = len(same_pairs) - same_opp
    diff_opp = sum(1 for item in diff_pairs if bool(item[3]))
    diff_same = len(diff_pairs) - diff_opp

    return FlickerSplit({
        "same_look_opposite": same_opp,
        "same_look_same": same_same,
        "diff_look_opposite": diff_opp,
        "diff_look_same": diff_same,
    })


# ---------------------------------------------------------------------- Fix Plan Table


FIX_PLAN_TABLE = [
    {"engine": "E8", "kinds": ["open_edges"], "unit": "edges"},
    {"engine": "E3", "kinds": ["hidden"], "unit": "faces"},
    {"engine": "E1", "kinds": ["loose"], "unit": "faces"},
    {"engine": "E2", "kinds": ["reversed"], "unit": "faces"},
    {"engine": "E4", "kinds": ["same_look"], "unit": "pairs"},
    {"engine": "E5", "kinds": ["diff_look"], "unit": "pairs"},
    {"engine": "E6", "kinds": ["cracks"], "unit": "points"},
    {"engine": "E7", "kinds": ["gridlines"], "unit": "faces"},
]


def compute_fix_plan(counts: dict, flicker_split_data: dict, n_faces: int) -> list[dict]:
    """Compute fix plan per unit through FIX_PLAN_TABLE in order E8 -> E3 -> E1 -> E2 -> E4 -> E5 -> E6 -> E7."""
    plan: list[dict] = []
    same_look = int(flicker_split_data.get("same_look_opposite", 0) + flicker_split_data.get("same_look_same", 0))
    diff_look = int(flicker_split_data.get("diff_look_opposite", 0) + flicker_split_data.get("diff_look_same", 0))

    engine_counts = {
        "E8": int(counts.get("open_edges", 0)),
        "E3": int(counts.get("hidden", 0)),
        "E1": int(counts.get("loose", 0)),
        "E2": int(counts.get("reversed", 0)),
        "E4": same_look,
        "E5": diff_look,
        "E6": int(counts.get("cracks", 0)),
        "E7": None if n_faces > 0 else 0,
    }

    for entry in FIX_PLAN_TABLE:
        eng = entry["engine"]
        cnt = engine_counts.get(eng, 0)
        if eng == "E7":
            if cnt is None:
                plan.append({
                    "engine": eng,
                    "kinds": list(entry["kinds"]),
                    "count": None,
                    "unit": entry["unit"],
                })
        elif cnt > 0:
            plan.append({
                "engine": eng,
                "kinds": list(entry["kinds"]),
                "count": cnt,
                "unit": entry["unit"],
            })

    return plan


# ---------------------------------------------------------------------- Markdown Formatter


def format_census_md(rows: list[dict], totals: dict) -> str:
    """Format census table as markdown."""
    lines = [
        "# Campus Error Census",
        "",
        "Note: The flicker columns (`flicker_diff`, `flicker_same`) are faces by material; "
        "the fix plan's E4/E5 are pairs by look.",
        "",
        "| Building | Unit | Triangles | flicker_diff | flicker_same | reversed | hidden | loose | open_edges | cracks | Seconds | Peak MB |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    kinds = ["flicker_diff", "flicker_same", "reversed", "hidden", "loose", "open_edges", "cracks"]
    by_bldg: dict[str, list[dict]] = collections.defaultdict(list)

    for r in sorted(rows, key=lambda x: (x.get("building", ""), x.get("unit", ""))):
        bldg = r.get("building", "UNKNOWN")
        by_bldg[bldg].append(r)
        unit = r.get("unit", "")
        if r.get("status") == "timeout":
            lines.append(f"| {bldg} | {unit} | - | - | - | - | - | - | - | - | TIMEOUT | - |")
            continue
        if r.get("status") == "error":
            lines.append(f"| {bldg} | {unit} | - | - | - | - | - | - | - | - | ERROR | - |")
            continue
        tris = f"{r.get('triangles', 0):,}"
        counts = r.get("counts", {})
        cnt_strs = [f"{counts.get(k, 0):,}" for k in kinds]
        secs = f"{r.get('seconds', 0.0):.2f}"
        peak = f"{r.get('peak_mb', 0.0):.1f}"
        lines.append(f"| {bldg} | {unit} | {tris} | {' | '.join(cnt_strs)} | {secs} | {peak} |")

    lines.extend([
        "",
        "## Totals by Building",
        "",
        "| Building | Units | Triangles | flicker_diff | flicker_same | reversed | hidden | loose | open_edges | cracks |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for bldg in sorted(by_bldg.keys()):
        bldg_rows = [r for r in by_bldg[bldg] if r.get("status") == "ok"]
        b_units = len(by_bldg[bldg])
        b_tris = sum(r.get("triangles", 0) for r in bldg_rows)
        b_cnts = [sum(r.get("counts", {}).get(k, 0) for r in bldg_rows) for k in kinds]
        cnt_strs = [f"{c:,}" for c in b_cnts]
        lines.append(f"| {bldg} | {b_units} | {b_tris:,} | {' | '.join(cnt_strs)} |")

    tot_units = totals.get("units", len(rows))
    tot_tris = f"{totals.get('triangles', 0):,}"
    tot_cnts = totals.get("counts", {})
    cnt_strs = [f"{tot_cnts.get(k, 0):,}" for k in kinds]
    lines.append(f"| **Total** | **{tot_units}** | **{tot_tris}** | {' | '.join(cnt_strs)} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------- Worker Execution


def _load_snapshot_mesh(snapshot_dir: Path) -> tuple[Path, MeshData]:
    snapshot_dir = Path(snapshot_dir)
    objs = sorted(snapshot_dir.glob("*.obj"))
    if len(objs) != 1:
        raise ValueError(f"{snapshot_dir}: expected exactly one .obj file, found {len(objs)}")
    return objs[0], read_obj(objs[0])


def _run_worker(snap_dir: Path, out_res: Path, out_err: Path, materials: Path | None = None) -> int:
    load_start = get_machine_load()
    t0 = time.perf_counter()

    obj_path, mesh = _load_snapshot_mesh(snap_dir)
    unit_name = obj_path.stem
    bldg = unit_building(unit_name)

    timings: dict[str, float] = {}
    errors = find_errors(mesh, timings=timings)

    # Write errors.json
    out_err.parent.mkdir(parents=True, exist_ok=True)
    out_err.write_text(json.dumps(errors), encoding="utf-8")

    split_res = flicker_split(mesh, errors.get("flicker_pairs", []), materials=materials)
    plan = compute_fix_plan(errors["counts"], split_res, mesh.n_faces)

    peak_mb = get_process_peak_memory_mb()
    load_end = get_machine_load()
    elapsed = round(time.perf_counter() - t0, 3)

    result = {
        "unit": unit_name,
        "building": bldg,
        "status": "ok",
        "triangles": int(mesh.n_faces),
        "seconds": elapsed,
        "peak_mb": peak_mb,
        "counts": errors["counts"],
        "loose_parts": errors.get("loose_parts", {}),
        "flicker_split": split_res,
        "timings": {k: round(v, 4) for k, v in timings.items()},
        "load": {"start": load_start, "end": load_end},
        "fix_plan": plan,
    }

    out_res.parent.mkdir(parents=True, exist_ok=True)
    out_res.write_text(json.dumps(result), encoding="utf-8")
    return 0


def _process_one_unit(
    snap_dir: Path,
    errors_dir: Path,
    timeout_s: float,
    materials: Path | None = None,
) -> dict:
    snap_dir = Path(snap_dir).resolve()
    objs = sorted(snap_dir.glob("*.obj"))
    unit_name = objs[0].stem if objs else snap_dir.name
    bldg = unit_building(unit_name)

    err_file = errors_dir / f"{unit_name}.json"
    repo_root = Path(__file__).resolve().parents[2]

    with tempfile.TemporaryDirectory(prefix="census_unit_") as tmp_dir:
        tmp_res = Path(tmp_dir) / "res.json"
        tmp_err = Path(tmp_dir) / "err.json"

        cmd = [
            sys.executable,
            "-m",
            "engine.campus.census",
            "--worker",
            str(snap_dir),
            "--out-res",
            str(tmp_res),
            "--out-err",
            str(tmp_err),
        ]
        if materials is not None:
            cmd.extend(["--materials", str(materials)])

        env = {
            **os.environ,
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "PYTHONPATH": os.pathsep.join(filter(None, [str(repo_root), os.environ.get("PYTHONPATH", "")])),
        }

        try:
            done = subprocess.run(cmd, env=env, timeout=timeout_s, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            return {"unit": unit_name, "building": bldg, "status": "timeout"}

        if done.returncode != 0:
            err_msg = done.stderr.strip() or f"process exited with {done.returncode}"
            return {"unit": unit_name, "building": bldg, "status": "error", "error": err_msg}

        if not tmp_res.is_file():
            return {"unit": unit_name, "building": bldg, "status": "error", "error": "no result written"}

        if tmp_err.is_file():
            err_file.parent.mkdir(parents=True, exist_ok=True)
            err_file.write_text(tmp_err.read_text(encoding="utf-8"), encoding="utf-8")

        return json.loads(tmp_res.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------- Main API


def census(
    units: Sequence[Path | str] | None = None,
    out_json: Path | str = Path("data/campus/census.json"),
    jobs: int = 4,
    timeout_s: float = 1800.0,
    errors_dir: Path | str | None = None,
    out_md: Path | str | None = None,
    materials_path: Path | str | None = DEFAULT_MATERIALS_PATH,
) -> dict:
    """Run census over snapshot units."""
    repo_root = Path(__file__).resolve().parents[2]
    out_json = Path(out_json).resolve()
    for written in (out_json, errors_dir, out_md):
        if written is not None:
            refuse_protected(written)

    if errors_dir is None:
        errors_dir = out_json.parent / "errors"
    else:
        errors_dir = Path(errors_dir).resolve()
    errors_dir.mkdir(parents=True, exist_ok=True)

    if out_md is None:
        if out_json.parent.name == "campus":
            out_md = repo_root / "docs" / "superpowers" / "records" / "campus" / "census.md"
        else:
            out_md = out_json.parent / "census.md"
    else:
        out_md = Path(out_md).resolve()

    if units is None:
        src_json = repo_root / "data" / "campus" / "source.json"
        if not src_json.is_file():
            raise FileNotFoundError(f"Source file not found: {src_json}")
        src_data = json.loads(src_json.read_text(encoding="utf-8"))
        unit_paths = [Path(s["dir"]) for s in src_data.get("snapshots", [])]
    else:
        unit_paths = [Path(u) for u in units]

    mat_arg = Path(materials_path).resolve() if materials_path is not None else None

    # Process units in parallel using ThreadPoolExecutor
    import threading
    from concurrent.futures import as_completed

    t_start = time.perf_counter()
    rows: list[dict] = []
    kinds = ["flicker_diff", "flicker_same", "reversed", "hidden", "loose", "open_edges", "cracks"]
    write_lock = threading.Lock()

    def _save_atomic(current_rows: list[dict], wall_sec: float) -> dict:
        sorted_rows = sorted(current_rows, key=lambda x: (x.get("building", ""), x.get("unit", "")))
        ok_r = [r for r in sorted_rows if r.get("status") == "ok"]
        st_counts = collections.Counter(r.get("status", "unknown") for r in sorted_rows)
        curr_totals = {
            "units": len(sorted_rows),
            "ok": st_counts.get("ok", 0),
            "timeout": st_counts.get("timeout", 0),
            "error": st_counts.get("error", 0),
            "triangles": sum(r.get("triangles", 0) for r in ok_r),
            "counts": {k: sum(r.get("counts", {}).get(k, 0) for r in ok_r) for k in kinds},
            "seconds": round(sum(r.get("seconds", 0.0) for r in ok_r), 2),
            "wall_seconds": round(wall_sec, 2),
        }
        units_d = {r["unit"]: r for r in sorted_rows if "unit" in r}
        res_data = {
            "units": units_d,
            "rows": sorted_rows,
            "totals": curr_totals,
        }
        tmp_p = out_json.with_name(f".{out_json.name}.tmp")
        tmp_p.write_text(json.dumps(res_data, indent=2), encoding="utf-8")
        os.replace(tmp_p, out_json)
        return res_data

    out_json.parent.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        future_map = {
            ex.submit(_process_one_unit, p, errors_dir, timeout_s, mat_arg): p
            for p in unit_paths
        }
        for f in as_completed(future_map):
            res_unit = f.result()
            with write_lock:
                rows.append(res_unit)
                _save_atomic(rows, time.perf_counter() - t_start)

    wall_seconds = time.perf_counter() - t_start
    result_data = _save_atomic(rows, wall_seconds)
    totals = result_data["totals"]

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(format_census_md(result_data["rows"], totals), encoding="utf-8")

    return result_data


# ---------------------------------------------------------------------- CLI Entrypoints


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine.campus.census")
    parser.add_argument("--worker", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--out-res", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--out-err", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--materials", type=Path, default=DEFAULT_MATERIALS_PATH, help="materials.json path")
    parser.add_argument("units", nargs="*", default=None, help="snapshot paths")
    parser.add_argument("--out", type=Path, default=Path("data/campus/census.json"), help="output json")
    parser.add_argument("--errors-dir", type=Path, default=None, help="errors dir")
    parser.add_argument("--md", type=Path, default=None, help="output markdown")
    parser.add_argument("--jobs", type=int, default=4, help="worker processes")
    parser.add_argument("--timeout", type=float, default=1800.0, help="timeout per unit in seconds")

    args = parser.parse_args(argv)

    if args.worker is not None:
        if args.out_res is None or args.out_err is None:
            parser.error("--worker requires --out-res and --out-err")
        return _run_worker(args.worker, args.out_res, args.out_err, args.materials)

    units = [Path(u) for u in args.units] if args.units else None
    res = census(
        units=units,
        out_json=args.out,
        jobs=args.jobs,
        timeout_s=args.timeout,
        errors_dir=args.errors_dir,
        out_md=args.md,
        materials_path=args.materials,
    )
    totals = res["totals"]
    wall_sec = totals.get("wall_seconds", totals["seconds"])
    print(f"census completed: {totals['units']} units ({totals['ok']} ok, {totals['timeout']} timeout, {totals['error']} error), "
          f"{totals['triangles']:,} triangles in {wall_sec:.2f} s wall ({totals['seconds']:.2f} s unit sum) -> {args.out}")
    if totals.get("error", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
