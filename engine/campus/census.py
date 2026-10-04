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


# ---------------------------------------------------------------------- Machine Load & Memory


def _get_system_times_nt() -> dict[str, int]:
    ctypes = __import__("ctypes")
    wintypes = __import__("ctypes.wintypes", fromlist=["wintypes"])

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    def _ft(ft: FILETIME) -> int:
        return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

    kernel32 = ctypes.WinDLL("kernel32")
    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    if kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return {"idle": _ft(idle), "kernel": _ft(kernel), "user": _ft(user)}
    return {}


def _count_processes_nt() -> tuple[int, int]:
    """Count (other python.exe, msedge.exe) processes."""
    ctypes = __import__("ctypes")
    wintypes = __import__("ctypes.wintypes", fromlist=["wintypes"])
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32")
    h = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h == wintypes.HANDLE(-1).value:
        return 0, 0
    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
    py_count = 0
    edge_count = 0
    cur_pid = kernel32.GetCurrentProcessId()
    success = kernel32.Process32First(h, ctypes.byref(pe))
    while success:
        exe = pe.szExeFile.decode("ascii", errors="ignore").lower()
        if exe == "python.exe":
            if pe.th32ProcessID != cur_pid:
                py_count += 1
        elif exe == "msedge.exe":
            edge_count += 1
        success = kernel32.Process32Next(h, ctypes.byref(pe))
    kernel32.CloseHandle(h)
    return py_count, edge_count


def get_machine_load() -> dict[str, Any]:
    """Snapshot of machine load (other python/edge processes, CPU times)."""
    if os.name == "nt":
        py_count, edge_count = _count_processes_nt()
        times = _get_system_times_nt()
        return {
            "python_processes": py_count,
            "msedge_processes": edge_count,
            "system_times": times,
        }
    return {"python_processes": 0, "msedge_processes": 0, "system_times": {}}


def get_process_peak_memory_mb() -> float:
    """Current process's peak working set size in MB via Windows GetProcessMemoryInfo."""
    if os.name != "nt":
        return 0.0
    ctypes = __import__("ctypes")
    wintypes = __import__("ctypes.wintypes", fromlist=["wintypes"])

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return round(counters.PeakWorkingSetSize / (1024 * 1024), 1)
    return 0.0


# ---------------------------------------------------------------------- Building Classifier


def unit_building(unit_name: str) -> str:
    """Infer building name from unit or snapshot name."""
    norm = unit_name.upper()
    if norm.startswith("ARCHITECTURE"):
        return "ARCHITECTURE"
    if norm.startswith("BRS"):
        return "BRS"
    if norm.startswith("CHTM"):
        return "CHTM"
    if norm.startswith("EDS"):
        return "EDS"
    if norm.startswith("GYMNASIUM"):
        return "GYMNASIUM"
    if norm.startswith("MAIN_INFR") or norm.startswith("MAIN INFR"):
        return "MAIN_INFRA"
    if norm.startswith("MAIN"):
        return "MAIN"
    if norm.startswith("PE"):
        return "PE"
    if norm.startswith("SCIENCE"):
        return "SCIENCE_A"
    return "SITE"


# ---------------------------------------------------------------------- Flicker Split


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

    materials_map: dict[str, dict] = {}
    if isinstance(materials, dict):
        materials_map = materials.get("materials", materials)
    elif materials is not None:
        mat_path = Path(materials)
        if mat_path.is_file():
            data = json.loads(mat_path.read_text(encoding="utf-8"))
            materials_map = data.get("materials", data)
    else:
        repo_root = Path(__file__).resolve().parents[2]
        mat_path = repo_root / "data" / "campus" / "materials.json"
        if mat_path.is_file():
            data = json.loads(mat_path.read_text(encoding="utf-8"))
            materials_map = data.get("materials", data)

    same_opp = 0
    same_same = 0
    diff_opp = 0
    diff_same = 0

    face_mats = mesh.face_material
    mat_names = mesh.materials

    for item in pair_list:
        i, j, _shared, opp = item[0], item[1], item[2], bool(item[3])
        mat_idx_i = int(face_mats[i]) if i < len(face_mats) else 0
        mat_idx_j = int(face_mats[j]) if j < len(face_mats) else 0

        name_i = mat_names[mat_idx_i] if mat_idx_i < len(mat_names) else str(mat_idx_i)
        name_j = mat_names[mat_idx_j] if mat_idx_j < len(mat_names) else str(mat_idx_j)

        look_i = materials_map.get(name_i, {}).get("look", name_i)
        look_j = materials_map.get(name_j, {}).get("look", name_j)

        same_look = (look_i == look_j)

        if same_look:
            if opp:
                same_opp += 1
            else:
                same_same += 1
        else:
            if opp:
                diff_opp += 1
            else:
                diff_same += 1

    return FlickerSplit({
        "same_look_opposite": same_opp,
        "same_look_same": same_same,
        "diff_look_opposite": diff_opp,
        "diff_look_same": diff_same,
    })


# ---------------------------------------------------------------------- Fix Plan Table


FIX_PLAN_TABLE = [
    {"engine": "E8", "kinds": ["open_edges"]},
    {"engine": "E3", "kinds": ["hidden"]},
    {"engine": "E1", "kinds": ["loose"]},
    {"engine": "E2", "kinds": ["reversed"]},
    {"engine": "E4", "kinds": ["same_look"]},
    {"engine": "E5", "kinds": ["diff_look"]},
    {"engine": "E6", "kinds": ["cracks"]},
    {"engine": "E7", "kinds": ["gridlines"]},
]


def compute_fix_plan(counts: dict, flicker_split_data: dict, n_faces: int) -> list[dict]:
    """Compute fix plan per unit in order E8 -> E3 -> E1 -> E2 -> E4 -> E5 -> E6 -> E7."""
    plan: list[dict] = []

    # 1. E8: open_edges
    if counts.get("open_edges", 0) > 0:
        plan.append({"engine": "E8", "kinds": ["open_edges"], "count": int(counts["open_edges"])})

    # 2. E3: hidden
    if counts.get("hidden", 0) > 0:
        plan.append({"engine": "E3", "kinds": ["hidden"], "count": int(counts["hidden"])})

    # 3. E1: loose
    if counts.get("loose", 0) > 0:
        plan.append({"engine": "E1", "kinds": ["loose"], "count": int(counts["loose"])})

    # 4. E2: reversed
    if counts.get("reversed", 0) > 0:
        plan.append({"engine": "E2", "kinds": ["reversed"], "count": int(counts["reversed"])})

    # 5. E4: flicker same look
    same_look = flicker_split_data.get("same_look_opposite", 0) + flicker_split_data.get("same_look_same", 0)
    if same_look > 0:
        plan.append({"engine": "E4", "kinds": ["same_look"], "count": int(same_look)})

    # 6. E5: flicker diff look
    diff_look = flicker_split_data.get("diff_look_opposite", 0) + flicker_split_data.get("diff_look_same", 0)
    if diff_look > 0:
        plan.append({"engine": "E5", "kinds": ["diff_look"], "count": int(diff_look)})

    # 7. E6: cracks
    if counts.get("cracks", 0) > 0:
        plan.append({"engine": "E6", "kinds": ["cracks"], "count": int(counts["cracks"])})

    # 8. E7: gridlines (listed for every unit with faces, count null)
    if n_faces > 0:
        plan.append({"engine": "E7", "kinds": ["gridlines"], "count": None})

    return plan


# ---------------------------------------------------------------------- Markdown Formatter


def format_census_md(rows: list[dict], totals: dict) -> str:
    """Format census table as markdown."""
    lines = [
        "# Campus Error Census",
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
        bldg_rows = [r for r in by_bldg[bldg] if r.get("status") != "timeout"]
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
    materials_path: Path | str | None = None,
) -> dict:
    """Run census over snapshot units."""
    repo_root = Path(__file__).resolve().parents[2]
    out_json = Path(out_json).resolve()

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
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        futures = [
            ex.submit(_process_one_unit, p, errors_dir, timeout_s, mat_arg)
            for p in unit_paths
        ]
        for f in futures:
            rows.append(f.result())

    # Build totals
    kinds = ["flicker_diff", "flicker_same", "reversed", "hidden", "loose", "open_edges", "cracks"]
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    totals = {
        "units": len(rows),
        "triangles": sum(r.get("triangles", 0) for r in ok_rows),
        "counts": {k: sum(r.get("counts", {}).get(k, 0) for r in ok_rows) for k in kinds},
        "seconds": round(sum(r.get("seconds", 0.0) for r in ok_rows), 2),
    }

    units_dict = {r["unit"]: r for r in rows if "unit" in r}
    result_data = {
        "units": units_dict,
        "rows": rows,
        "totals": totals,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result_data, indent=2), encoding="utf-8")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(format_census_md(rows, totals), encoding="utf-8")

    return result_data


# ---------------------------------------------------------------------- CLI Entrypoints


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine.campus.census")
    parser.add_argument("--worker", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--out-res", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--out-err", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--materials", type=Path, default=None, help="materials.json path")
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
    census(
        units=units,
        out_json=args.out,
        jobs=args.jobs,
        timeout_s=args.timeout,
        errors_dir=args.errors_dir,
        out_md=args.md,
        materials_path=args.materials,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
