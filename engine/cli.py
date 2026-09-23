"""Command-line entry point for the automatic fix pipeline.

`python -m engine.cli fix <snapshot_dir> [--accept-slit] [--out data/output]`
    Runs `engine.fixes.pipeline.fix_object` on the snapshot and writes, under `<out>/<name>/`:
    `<name>.fixed.obj` (triangles -- the file for Unity), `<name>.fixed.ngon.obj` (polygons, a
    viewer/documentation artifact), a copy of `materials.mtl` and `tex/`, `report.json` (every
    number in `FixResult`, both guard reports per view, the profile, the input sha256), and
    `guard_<view>.png` before/after/difference triptychs for 6 axis views. Exit code 0 when
    `passed`, 2 otherwise.

`python -m engine.cli preview-data <snapshot_dir> --out preview/data`
    Writes the JSON `preview/index.html` reads (see `spike/12_export_preview.py` for the shape
    this mirrors), with AFTER built from the REAL fixed mesh and the REAL guard numbers, and
    `stats` extended with the new counts (flipped, thin_sheets, one_sided_holes_before/after,
    outline_edges_after, unavoidable_diagonals_after, guard_passed).

A snapshot directory is the layout `engine.io.snapshot.snapshot_object` produces: one `<name>.obj`,
`materials.mtl`, and a `tex/` folder of the textures it references.

`engine/` imports nothing from `api`, `spike`, fastapi, sqlalchemy; `trimesh`/`embreex` stay
confined to `engine/rays/` -- this module never imports them directly, only through
`engine.rays.caster.ReusableCaster`/`EmbreeCaster`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from engine.fixes.pipeline import FixProfile, FixResult, fix_object
from engine.guard.compare import GuardReport, ViewVerdict, classify_pixels, face_planes
from engine.guard.render import save_triptych
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.io.mtl import MtlMaterial, parse_mtl, texture_flatness
from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj, write_obj_polygons
from engine.io.snapshot import sha256_file
from engine.model import MeshData
from engine.pipeline import Topology, analyse_topology, flat_material_indices
from engine.rays.caster import ReusableCaster
from engine.topo.adjacency import build_edge_table, edge_face_lists
from engine.topo.weld import weld_exact

#: The 6 axis-aligned views (of the 26 the guard itself uses) reported as before/after/diff PNGs.
_AXIS_VIEWS = [v for v in VIEWS_26 if sum(1 for c in (round(x) for x in v) if c != 0) == 1]


def _axis_name(view) -> str:
    base = [round(c) for c in view]
    i = next(i for i, c in enumerate(base) if c != 0)
    return f"{'+' if base[i] > 0 else '-'}{'xyz'[i]}"


def _face_normals(positions: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tri = positions[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(n, axis=1)
    out = np.zeros_like(n)
    safe = length > 0.0
    out[safe] = n[safe] / length[safe, None]
    return out


# --------------------------------------------------------------------------------- snapshot load


def _load_snapshot(snapshot_dir: Path) -> tuple[Path, MeshData, dict[str, float], dict[str, MtlMaterial]]:
    """`(obj_path, mesh, flatness, mtl_materials)`. `flatness` is per-material texture std, from
    `engine.io.mtl.parse_mtl` + `texture_flatness`, exactly like `engine.io.snapshot` computes it
    -- but re-derived from the snapshot's own `materials.mtl`/`tex/` rather than requiring a
    `SnapshotResult`, so this works on any directory laid out like one."""
    snapshot_dir = Path(snapshot_dir)
    obj_paths = sorted(snapshot_dir.glob("*.obj"))
    if len(obj_paths) != 1:
        raise ValueError(f"{snapshot_dir}: expected exactly one .obj file, found {len(obj_paths)}")
    obj_path = obj_paths[0]
    mesh = read_obj(obj_path)

    mtl_materials: dict[str, MtlMaterial] = {}
    flatness: dict[str, float] = {}
    mtl_path = snapshot_dir / "materials.mtl"
    if mtl_path.exists():
        mtl_materials = parse_mtl(mtl_path)
        for name, mat in mtl_materials.items():
            if mat.map_kd:
                tex_path = snapshot_dir / mat.map_kd
                if tex_path.exists():
                    flatness[name] = texture_flatness(tex_path)
    return obj_path, mesh, flatness, mtl_materials


def _copy_assets(snapshot_dir: Path, out_dir: Path) -> None:
    mtl_src = snapshot_dir / "materials.mtl"
    if mtl_src.exists():
        shutil.copyfile(mtl_src, out_dir / "materials.mtl")
    tex_src = snapshot_dir / "tex"
    if tex_src.is_dir():
        tex_dst = out_dir / "tex"
        if tex_dst.exists():
            shutil.rmtree(tex_dst)
        shutil.copytree(tex_src, tex_dst)


# --------------------------------------------------------------------------------------- report


def _view_verdict_dict(v: ViewVerdict) -> dict:
    return {"view": list(v.view), "model_px": v.model_px, "holes": v.holes,
            "moved_same_flat": v.moved_same_flat, "moved_other": v.moved_other,
            "material_changed": v.material_changed, "edge_flicker": v.edge_flicker}


def _guard_report_dict(g: GuardReport) -> dict:
    return {"passed": g.passed, "totals": g.totals, "views": [_view_verdict_dict(v) for v in g.views]}


def _profile_dict(p: FixProfile) -> dict:
    return {"n_dirs": p.n_dirs, "slit_threshold": p.slit_threshold, "accept_slit": p.accept_slit,
            "flat_texture_std": p.flat_texture_std, "guard_size": list(p.guard_size),
            "edge_flicker_cap_final": p.edge_flicker_cap_final}


def _build_report(name: str, obj_path: Path, mesh: MeshData, result: FixResult,
                   profile: FixProfile) -> dict:
    """Every number in `FixResult`, both guard reports (per view), the profile, and the input
    file's sha256 -- so report.json fully explains what a run did without re-running it."""
    return {
        "name": name,
        "input_sha256": sha256_file(obj_path),
        "profile": _profile_dict(profile),
        "tris_before": mesh.n_faces,
        "tris_after": result.mesh.n_faces,
        "materials_before": len(mesh.materials),
        "materials_after": len(result.mesh.materials),
        "n_hidden_candidates": result.n_hidden_candidates,
        "n_restored_by_guard": result.n_restored_by_guard,
        "n_removed_hidden": result.n_removed_hidden,
        "n_removed_slit": result.n_removed_slit,
        "n_zero_area_dropped": result.n_zero_area_dropped,
        "n_degenerate_restored": result.n_degenerate_restored,
        "n_flipped": int(result.flipped.sum()),
        "n_thin_sheets": int(result.thin_sheets.sum()),
        "one_sided_holes_before": result.one_sided_holes_before,
        "one_sided_holes_after": result.one_sided_holes_after,
        "feedback_history": result.feedback_history,
        "guard_after_removal": _guard_report_dict(result.guard_after_removal),
        "guard_final": _guard_report_dict(result.guard_final),
        "merge_report": dict(result.merge_report),
        "invariants": result.invariants,
        "passed": result.passed,
    }


# --------------------------------------------------------------------------------- guard images


def _write_guard_images(mesh: MeshData, result: FixResult, profile: FixProfile,
                        flat_materials: frozenset, topo: Topology, positions_c: np.ndarray,
                        out_dir: Path) -> None:
    """One `guard_<view>.png` triptych per axis view: BEFORE (original mesh, shaded), AFTER
    (final shipped mesh, shaded), DIFF (failures red, tolerated moves amber). A diagnostic image,
    not the authoritative numbers -- it uses the plain 3x3-neighbourhood flicker test (no
    sub-pixel coverage probe), so a handful of borderline silhouette pixels the real
    (coverage-checked) `guard_final` tolerated may still show red here; report.json's own numbers
    are always the real `guard_final`/`guard_after_removal`, not re-derived from these images."""
    _, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    face_w_before = topo.face_w
    ids_before = np.arange(len(face_w_before), dtype=np.int64)
    normals_before = _face_normals(positions_c, face_w_before)

    face_w_after = remap[result.mesh.face_v]
    ids_after = np.arange(len(face_w_after), dtype=np.int64)
    normals_after = _face_normals(positions_c, face_w_after)

    planes_before = face_planes(positions_c, face_w_before)
    planes_after = face_planes(positions_c, face_w_after)
    depth_tol = 1.5 * float(topo.quanta.max())

    caster_before = ReusableCaster()
    caster_after = ReusableCaster()
    for view in _AXIS_VIEWS:
        before = ortho_first_hit(positions_c, face_w_before, ids_before, view, positions_c,
                                 profile.guard_size, caster_before)
        after = ortho_first_hit(positions_c, face_w_after, ids_after, view, positions_c,
                                profile.guard_size, caster_after)
        codes = classify_pixels(
            before.depth, before.tri, after.depth, after.tri, mesh.face_material,
            result.mesh.face_material, flat_materials, depth_tol, origins=before.origins,
            direction=before.direction, plane_before=planes_before, plane_after=planes_after)
        path = out_dir / f"guard_{_axis_name(view)}.png"
        save_triptych(path, before, after, codes, normals_before=normals_before,
                     normals_after=normals_after)


# --------------------------------------------------------------------------------- fix command


def cmd_fix(snapshot_dir: Path, out_root: Path, accept_slit: bool,
            profile: FixProfile | None = None) -> int:
    obj_path, mesh, flatness, _mtl_materials = _load_snapshot(snapshot_dir)
    if profile is None:
        profile = FixProfile(accept_slit=accept_slit)
    else:
        profile = replace(profile, accept_slit=accept_slit)

    result = fix_object(mesh, flatness, profile)

    name = mesh.name
    out_dir = Path(out_root) / name
    out_dir.mkdir(parents=True, exist_ok=True)

    write_obj(result.mesh, out_dir / f"{name}.fixed.obj")
    write_obj_polygons(result.mesh, result.rings, out_dir / f"{name}.fixed.ngon.obj")
    _copy_assets(snapshot_dir, out_dir)

    flat_materials = flat_material_indices(mesh, flatness, profile.flat_texture_std)
    topo = analyse_topology(mesh, flat_materials)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    positions_c = topo.positions_w - centre
    _write_guard_images(mesh, result, profile, flat_materials, topo, positions_c, out_dir)

    report = _build_report(name, obj_path, mesh, result, profile)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"{name}: {mesh.n_faces} -> {result.mesh.n_faces} tris, passed={result.passed}")
    print(f"  wrote {out_dir}")
    return 0 if result.passed else 2


# --------------------------------------------------------------------------- preview-data command


def _round_flat(a, nd=3) -> list:
    return np.round(np.asarray(a, dtype=float).reshape(-1), nd).tolist()


def _before_edges(topo: Topology, positions_c: np.ndarray, removed: np.ndarray):
    """`(grid, tri_before, outline_before)` segment lists for the ORIGINAL mesh's visible (ok,
    surviving) faces: `grid` is a boundary between a REMOVED (hidden/slit) face and two coplanar
    surviving faces of the same plane region; `tri_before` a boundary between two coplanar
    surviving faces neither of which is removed (an ordinary gridline, nothing hidden behind it);
    `outline_before` everything else (a real shape edge, or the model's own silhouette)."""
    ok = topo.ok
    ok_ids = np.nonzero(ok)[0]
    groups = edge_face_lists(topo.table)
    plabel = topo.face_region

    grid, tri_before, outline_before = [], [], []
    for edge, faces in zip(topo.table.edges, groups):
        visible = [int(f) for f in faces if not removed[f]]
        if not visible:
            continue
        seg = [positions_c[int(edge[0])].tolist(), positions_c[int(edge[1])].tolist()]
        labels = {int(plabel[f]) for f in visible}
        if len(visible) >= 2 and len(labels) == 1 and labels != {-1}:
            (grid if any(removed[f] for f in faces) else tri_before).append(seg)
        else:
            outline_before.append(seg)
    return grid, tri_before, outline_before


def _after_edges(result: FixResult, positions_o: np.ndarray):
    """`(outline_after, tri_after)` segment lists for the FIXED mesh: an edge shared by exactly
    two triangles that came from the SAME merge (`source_faces[i] is source_faces[j]`, the
    identity `engine.fixes.merge` sets up for every triangle of one merged region) is an
    UNAVOIDABLE DIAGONAL -- it exists only because OBJ needs triangles, not because it is a real
    shape edge; everything else (a mesh boundary, a border between two different regions, or a
    border with a copied-through face) is a real OUTLINE edge."""
    n = result.mesh.n_faces
    table = build_edge_table(result.mesh.face_v, np.ones(n, dtype=bool))
    groups = edge_face_lists(table)
    src = result.source_faces

    outline, diagonal = [], []
    for edge, faces in zip(table.edges, groups):
        seg = [positions_o[int(edge[0])].tolist(), positions_o[int(edge[1])].tolist()]
        if len(faces) == 2 and src[int(faces[0])] is src[int(faces[1])]:
            diagonal.append(seg)
        else:
            outline.append(seg)
    return outline, diagonal


def _material_colors(snapshot_dir: Path, materials: list[str], mtl_materials: dict[str, MtlMaterial]) -> list[dict]:
    out = []
    for name in materials:
        rgb = [0.8, 0.8, 0.8]
        mat = mtl_materials.get(name)
        if mat is not None and mat.map_kd:
            tex_path = snapshot_dir / mat.map_kd
            if tex_path.exists():
                mean = np.asarray(Image.open(tex_path).convert("RGB"), dtype=float).reshape(-1, 3).mean(axis=0)
                rgb = [round(float(c) / 255.0, 4) for c in mean]
        out.append({"name": name, "color": rgb})
    return out


def cmd_preview_data(snapshot_dir: Path, out_dir: Path, profile: FixProfile | None = None) -> int:
    obj_path, mesh, flatness, mtl_materials = _load_snapshot(snapshot_dir)
    if profile is None:
        profile = FixProfile()
    result = fix_object(mesh, flatness, profile)

    flat_materials = flat_material_indices(mesh, flatness, profile.flat_texture_std)
    topo = analyse_topology(mesh, flat_materials)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    positions_c_w = topo.positions_w - centre       # welded frame: BEFORE (topo.face_w indexes it)
    positions_c_o = mesh.positions - centre          # original frame: AFTER (result.mesh.face_v indexes it)

    ok_ids = np.nonzero(topo.ok)[0]
    removed = result.removed_hidden | result.removed_slit
    before_tri = positions_c_w[topo.face_w[ok_ids]]
    before_mat = mesh.face_material[ok_ids]
    before_hidden = removed[ok_ids].astype(int)

    after_tri = positions_c_o[result.mesh.face_v]
    after_mat = result.mesh.face_material

    grid, tri_before, outline_before = _before_edges(topo, positions_c_w, removed)
    outline_after, tri_after = _after_edges(result, positions_c_o)

    guard_final = result.guard_final.totals
    guard_damaged_px = (guard_final["holes"] + guard_final["material_changed"]
                        + guard_final["moved_other"] + guard_final["moved_same_flat"]
                        + guard_final["edge_flicker"])

    data = {
        "name": mesh.name,
        "stats": {
            "tris_total": int(mesh.n_faces),
            "zero_area": int(result.n_zero_area_dropped),
            "before_tris": int(topo.ok.sum()),
            "hidden": int(removed.sum()),
            "after_hidden_removed": int(topo.ok.sum() - removed.sum()),
            "after_merged": int(result.mesh.n_faces),
            "regions": int(result.merge_report.get("regions_merged", 0)),
            "guard_views": len(VIEWS_26),
            "guard_model_px": int(guard_final["model_px"]),
            "guard_damaged_px": int(guard_damaged_px),
            "guard_tol_in": 1.5 * float(topo.quanta.max()),
            "gridline_edges": len(grid),
            "flipped": int(result.flipped.sum()),
            "thin_sheets": int(result.thin_sheets.sum()),
            "one_sided_holes_before": result.one_sided_holes_before,
            "one_sided_holes_after": result.one_sided_holes_after,
            "outline_edges_after": len(outline_after),
            "unavoidable_diagonals_after": len(tri_after),
            "guard_passed": bool(result.guard_final.passed),
        },
        "materials": _material_colors(snapshot_dir, mesh.materials, mtl_materials),
        "before": {"pos": _round_flat(before_tri), "mat": before_mat.tolist(), "hidden": before_hidden.tolist()},
        "after": {"pos": _round_flat(after_tri), "mat": after_mat.tolist()},
        "edges": {"grid": _round_flat(grid), "tri_before": _round_flat(tri_before),
                  "outline_before": _round_flat(outline_before), "outline_after": _round_flat(outline_after),
                  "tri_after": _round_flat(tri_after)},
    }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{mesh.name}.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    index_path = out_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    index = [e for e in index if e.get("name") != mesh.name]
    index.append({"file": f"{mesh.name}.json", "name": mesh.name})
    index_path.write_text(json.dumps(index), encoding="utf-8")

    print(f"{mesh.name}: wrote {out_dir / (mesh.name + '.json')}")
    for k, v in data["stats"].items():
        print(f"  {k}: {v}")
    return 0


# ------------------------------------------------------------------------------------------ main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m engine.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    fix_p = sub.add_parser("fix", help="fix one snapshot, writing the fixed OBJs, report and guard images")
    fix_p.add_argument("snapshot_dir")
    fix_p.add_argument("--accept-slit", action="store_true")
    fix_p.add_argument("--out", default="data/output")

    preview_p = sub.add_parser("preview-data", help="write the JSON preview/index.html reads")
    preview_p.add_argument("snapshot_dir")
    preview_p.add_argument("--out", default="preview/data")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "fix":
        return cmd_fix(Path(args.snapshot_dir), Path(args.out), args.accept_slit)
    if args.command == "preview-data":
        return cmd_preview_data(Path(args.snapshot_dir), Path(args.out))
    return 1


if __name__ == "__main__":
    sys.exit(main())
