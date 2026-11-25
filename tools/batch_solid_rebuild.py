"""Batch runner and 6-gate QA harness for Engine v2 (`solid_cutaway_rebuild`)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
import trimesh

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.fixes.solid_cutaway_rebuild import (  # noqa: E402
    _clean_shapely,
    _count_non_ortho_edges,
    _is_clean_angled_tread,
    _iter_polygons,
    load_raw_floor_obj,
    run_solid_rebuild,
)

DEFAULT_SRC_ROOT = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair\Exports\Repaired-Buildings-20261015\ByBuilding")
DEFAULT_OUT_ROOT = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair\02_STAGING_DEVELOPMENT\SolidRebuild")


def _is_non_interior_folder(name: str) -> bool:
    """Return True for rooftops (Floor_RF/*Roof*) and exterior Sidewalk_* folders excluded from interior design."""
    low = name.strip().lower()
    return low == "floor_rf" or low.endswith("_rf") or low.startswith("roof") or low.startswith("sidewalk")


def audit_rebuilt_glb(
    glb_path: Path,
    src_obj: Path,
    out_dir: Path,
    report_audit: dict[str, Any],
    passed_flag: bool,
) -> dict[str, Any]:
    """Run all 6 automated Engine v2 QA gates against a rebuilt floor package."""
    sc = trimesh.load(glb_path, force="scene")
    raw = load_raw_floor_obj(src_obj)

    # Gate 1: Watertight & manifold topology
    watertight_ok = bool(
        passed_flag
        and report_audit.get("all_watertight")
        and int(report_audit.get("total_open_edges", 1)) == 0
        and int(report_audit.get("total_nonmanifold_edges", 1)) == 0
        and int(report_audit.get("narrow_wall_gaps", 1)) == 0
    )

    # Gate 2: Zero prematurely stepped/chopped __Upper walls & columns
    stepped_upper: list[dict[str, Any]] = []
    for n, g in sorted(sc.geometry.items()):
        if not ((n.startswith("Wall_") or n.startswith("Column_")) and "__Upper" in n):
            continue
        fn = g.face_normals
        fc = g.vertices[g.faces].mean(axis=1)
        up = fn[:, 1] > 0.9
        if not up.any():
            continue
        max_y = float(g.bounds[1][1])
        mid_m = up & (fc[:, 1] < max_y - 0.3)
        if mid_m.any():
            a_mid = float(g.area_faces[mid_m].sum())
            if a_mid > 0.25:
                stepped_upper.append({"node": n, "a_mid": round(a_mid, 3)})

    # Gate 3: Zero non-orthogonal notched single-step stair treads
    non_ortho_steps: list[dict[str, Any]] = []
    stair_geoms = [g for n, g in sc.geometry.items() if n.startswith("Stairs_") and "Parapet" not in n]
    if stair_geoms:
        st_all = trimesh.util.concatenate(stair_geoms) if len(stair_geoms) > 1 else stair_geoms[0]
        fc = st_all.vertices[st_all.faces].mean(axis=1)
        fn = st_all.face_normals
        by_y: dict[float, list[Polygon]] = {}
        for f, yv in zip(st_all.faces[fn[:, 1] > 0.95], fc[fn[:, 1] > 0.95, 1]):
            yr = round(round(float(yv) / 0.05) * 0.05, 3)
            p = Polygon(st_all.vertices[f][:, [0, 2]]).buffer(0)
            if p.area > 1e-4:
                by_y.setdefault(yr, []).append(p)
        for yr, plist in sorted(by_y.items()):
            for g in _iter_polygons(_clean_shapely(unary_union(plist), 0.004)):
                min_dim = min(g.bounds[2] - g.bounds[0], g.bounds[3] - g.bounds[1])
                if g.area <= 4.5 and min_dim <= 1.25:
                    no = 0 if _is_clean_angled_tread(g) else _count_non_ortho_edges(g)
                    if no > 0:
                        non_ortho_steps.append({"y": yr, "non_ortho_edges": no})

    # Gate 4: Zero same-direction Parapet vs Wall/Column/Overhead Z-fighting overlaps
    parapet_meshes = [g for n, g in sc.geometry.items() if "Parapet" in n]
    other_meshes = [
        g for n, g in sc.geometry.items()
        if n.startswith("Wall_") or n.startswith("Column_") or n.startswith("OverheadBeams_")
    ]
    parapet_zfight = 0
    if parapet_meshes and other_meshes:
        pm = trimesh.util.concatenate(parapet_meshes) if len(parapet_meshes) > 1 else parapet_meshes[0]
        om = trimesh.util.concatenate(other_meshes) if len(other_meshes) > 1 else other_meshes[0]
        pfc = pm.vertices[pm.faces].mean(axis=1)
        ofc = om.vertices[om.faces].mean(axis=1)
        pfn = pm.face_normals
        ofn = om.face_normals
        for i in range(0, len(pfc), 500):
            d = np.linalg.norm(pfc[i : i + 500, None, :] - ofc[None, :, :], axis=2)
            dot = np.einsum("ik,jk->ij", pfn[i : i + 500], ofn)
            parapet_zfight += int(((d < 0.045) & (dot > 0.95)).sum())

    # Gate 5: Overhead lintels bounded (zero huge roof slab leakage)
    ov_gs = [g for n, g in sc.geometry.items() if n.startswith("OverheadBeams_")]
    overhead_top_area = 0.0
    if ov_gs:
        ovm = trimesh.util.concatenate(ov_gs) if len(ov_gs) > 1 else ov_gs[0]
        overhead_top_area = round(float(ovm.area_faces[ovm.face_normals[:, 1] > 0.9].sum()), 2)
    overhead_ok = overhead_top_area <= 65.0

    # Gate 6: Required Unity & manifest outputs exist and are non-empty
    stem = src_obj.stem
    req_files = [
        out_dir / f"{stem}.solid_rebuild.unity.obj",
        out_dir / "materials.mtl",
        out_dir / "rebuild_manifest.json",
        out_dir / "watertight_audit.json",
    ]
    unity_outputs_ok = all(p.is_file() and p.stat().st_size > 0 for p in req_files)

    gates = {
        "watertight": watertight_ok,
        "stepped_upper": len(stepped_upper) == 0,
        "non_ortho_steps": len(non_ortho_steps) == 0,
        "parapet_zfight": parapet_zfight == 0,
        "overhead_bounds": overhead_ok,
        "unity_outputs": unity_outputs_ok,
    }
    return {
        "all_passed": all(gates.values()),
        "gates": gates,
        "metrics": {
            "floor_y": round(float(raw.floor_y), 3),
            "ceil_y": round(float(raw.ceil_y), 3),
            "nodes": len(report_audit.get("nodes", [])),
            "open_edges": int(report_audit.get("total_open_edges", 0)),
            "nonmanifold_edges": int(report_audit.get("total_nonmanifold_edges", 0)),
            "narrow_wall_gaps": int(report_audit.get("narrow_wall_gaps", 0)),
            "stepped_upper": stepped_upper,
            "non_ortho_steps": non_ortho_steps,
            "parapet_zfight": parapet_zfight,
            "overhead_top_area": overhead_top_area,
            "floor_raised_nodes": [n for n in sc.geometry if "Raised" in n],
        },
    }


def _stage_to_dashboard(src_obj: Path, out_dir: Path, glb_path: Path | None, obj_path: Path | None, dash_dir: Path) -> None:
    dash_dir.mkdir(parents=True, exist_ok=True)
    base = src_obj.name[:-len(".fixed.obj")] if src_obj.name.endswith(".fixed.obj") else src_obj.stem
    if glb_path and glb_path.is_file():
        shutil.copy2(glb_path, dash_dir / f"{base}.solid_rebuild.glb")
    if obj_path and obj_path.is_file():
        shutil.copy2(obj_path, dash_dir / f"{base}.solid_rebuild.unity.obj")
    for name in ("materials.mtl", "rebuild_manifest.json", "watertight_audit.json"):
        fp = out_dir / name
        if fp.is_file():
            shutil.copy2(fp, dash_dir / name)
    tex_src = out_dir / "textures"
    if tex_src.is_dir():
        tex_dst = dash_dir / "textures"
        tex_dst.mkdir(parents=True, exist_ok=True)
        for tf in tex_src.iterdir():
            if tf.is_file():
                shutil.copy2(tf, tex_dst / tf.name)


def run_batch_rebuild(
    src_root: Path,
    out_root: Path,
    building: str,
    floors: list[str] | None = None,
    stage_dashboard_dir: Path | None = None,
) -> dict[str, Any]:
    """Rebuild and QA-audit every selected building/floor package."""
    buildings = sorted(p.name for p in src_root.iterdir() if p.is_dir()) if building.upper() == "ALL" else [building]
    overall: dict[str, Any] = {"all_passed": True, "buildings": {}}

    for bname in buildings:
        b_src = src_root / bname
        if not b_src.is_dir():
            raise FileNotFoundError(f"Building source folder not found: {b_src}")
        fixed_objs = sorted(b_src.rglob("*.fixed.obj"))
        if floors:
            want = set(floors)
            fixed_objs = [p for p in fixed_objs if p.parent.name in want]
        else:
            fixed_objs = [p for p in fixed_objs if not _is_non_interior_folder(p.parent.name)]
        if not fixed_objs:
            raise FileNotFoundError(f"No *.fixed.obj files found under {b_src} for floors={floors}")

        b_out = out_root / bname
        b_out.mkdir(parents=True, exist_ok=True)
        floor_results: list[dict[str, Any]] = []
        b_passed = True

        for src_obj in fixed_objs:
            floor_name = src_obj.parent.name
            floor_out = b_out / floor_name
            rep = run_solid_rebuild(src_obj, floor_out, low_cut_m=1.25, plinth_m=0.04, export_glb=True)
            assert rep.glb_path is not None
            qa = audit_rebuilt_glb(rep.glb_path, src_obj, floor_out, rep.audit, rep.passed)
            if not qa["all_passed"]:
                b_passed = False
            if stage_dashboard_dir is not None:
                _stage_to_dashboard(src_obj, floor_out, rep.glb_path, rep.obj_path, stage_dashboard_dir / bname)
            floor_results.append({
                "floor": floor_name,
                "source_obj": str(src_obj),
                "out_dir": str(floor_out),
                **qa,
            })

        b_report = {
            "building": bname,
            "all_passed": b_passed,
            "floor_count": len(floor_results),
            "floors": floor_results,
        }
        (b_out / "batch_qa_report.json").write_text(json.dumps(b_report, indent=2) + "\n", encoding="utf-8")
        overall["buildings"][bname] = b_report
        if not b_passed:
            overall["all_passed"] = False

    return overall


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch Engine v2 solid rebuild & 6-gate QA harness")
    parser.add_argument("--building", required=True, help="Building folder name (e.g. CHTM) or ALL")
    parser.add_argument("--floors", nargs="*", default=None, help="Optional floor subfolder names (e.g. Floor_4F Floor_5F)")
    parser.add_argument("--src-root", type=Path, default=DEFAULT_SRC_ROOT)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--stage-dashboard-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    summary = run_batch_rebuild(
        src_root=args.src_root,
        out_root=args.out_root,
        building=args.building,
        floors=args.floors,
        stage_dashboard_dir=args.stage_dashboard_dir,
    )
    for bname, brep in summary["buildings"].items():
        print(f"[{bname}] all_passed={brep['all_passed']} floors={brep['floor_count']}")
        for fl in brep["floors"]:
            print(
                f"  - {fl['floor']}: passed={fl['all_passed']} gates={fl['gates']} "
                f"open={fl['metrics']['open_edges']} stepped={len(fl['metrics']['stepped_upper'])} "
                f"non_ortho={len(fl['metrics']['non_ortho_steps'])} zfight={fl['metrics']['parapet_zfight']}"
            )
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
