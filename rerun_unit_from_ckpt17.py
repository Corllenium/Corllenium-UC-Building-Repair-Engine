"""Rerun one floor unit fresh from its CHECKPOINT-17 Unity export through the Repair Engine,
then apply the strict validator plus an explicit FLOOR / CEILING guard.

Why: the earlier Main 2nd Floor output deleted walkable floor (18,027 -> 16,189 sq ft of upward
floor surface). Floor slabs sit on top of other geometry (min clearance ~0), so the generic
"visible surface" rule did not protect them. This script protects every horizontal face that a
player can see (up-facing with open air above, down-facing with open air below) and restores any
such CKPT17 face that the engine output does not cover at all 7 sample points (+-0.04 in).

Output is 100% CKPT17 geometry repaired by the engine (restored faces are original CKPT17 faces).

Usage:
    python rerun_unit_from_ckpt17.py Main_2nd_Floor_obj Main Model-Floor_02
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

from engine.campus.checkpoint_push import convert_unity_to_ckpt17_coords
from engine.fixes.building_repair import compact_mesh, repair_building_floor_mesh
from engine.io.mtl import parse_mtl
from engine.io.obj_reader import read_obj
from engine.model import MeshData
from engine.rays.caster import EmbreeCaster
from engine.topo.planes import face_normals
from repair_all_units_strict_validator import (
    BARY7,
    UNIT_ALIASES,
    WT_MODELS,
    _append_before_faces,
    repair_and_validate_unit,
    sync_after_to_all_siege,
)
from smooth_restore_architecture import compact_obj_bytes

REPO04 = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair")
SRC_ROOT = REPO04 / "Exports/Unity-Buildings-20261014/ByBuilding"
EXP_ROOT = REPO04 / "Exports/Repaired-Buildings-20261015/ByBuilding"
SQFT = 144.0


def horiz_area(m: MeshData) -> tuple[float, float, float]:
    p = m.positions[m.face_v]
    fn = face_normals(m.positions, m.face_v, np.ones(m.n_faces, dtype=bool))
    a = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    return a[fn[:, 2] > 0.9].sum() / SQFT, a[fn[:, 2] < -0.9].sum() / SQFT, a.sum() / SQFT


def drop_flipped_horizontals(b: MeshData, a: MeshData) -> tuple[MeshData, int]:
    """Drop horizontal faces in `a` whose facing direction does not exist in CKPT17 at that spot.

    The engine sometimes keeps a floor slab with its normal pointing DOWN where CKPT17 has it
    pointing UP (players stand on it). Such faces render dark and look deleted. A horizontal face
    in `a` is kept only if CKPT17 has a same-direction face under at least 3 of its 4 samples.
    """
    from engine.fixes.remove import remove_faces

    center = (b.positions.min(axis=0) + b.positions.max(axis=0)) / 2.0
    fn_b = face_normals(b.positions, b.face_v, np.ones(b.n_faces, dtype=bool))
    ok_b = np.flatnonzero((~np.isnan(fn_b).any(axis=1)) & (np.linalg.norm(fn_b, axis=1) > 0.5))
    cb = EmbreeCaster(b.positions - center, b.face_v[ok_b])
    at = a.positions[a.face_v] - center
    fn_a = face_normals(a.positions, a.face_v, np.ones(a.n_faces, dtype=bool))
    h = np.flatnonzero((~np.isnan(fn_a).any(axis=1)) & (np.abs(fn_a[:, 2]) > 0.9))
    if len(h) == 0:
        return a, 0
    s = np.einsum("sb,fbk->fsk", BARY7[:4], at[h]).reshape(-1, 3)
    n = np.repeat(fn_a[h], 4, axis=0)
    same = np.zeros(len(s), dtype=bool)
    for sign in (1.0, -1.0):
        ih, th = cb.first_hit(s + sign * 0.045 * n, -sign * n)
        c = np.flatnonzero((ih >= 0) & (np.abs(th - 0.045) <= 0.04))
        fh = ok_b[ih[c]]
        good = np.einsum("ij,ij->i", n[c], fn_b[fh]) >= 0.98  # signed: same facing direction
        same[c[good]] = True
    drop = np.zeros(a.n_faces, dtype=bool)
    drop[h[same.reshape(len(h), 4).sum(axis=1) < 3]] = True
    if not drop.any():
        return a, 0
    a, _ = remove_faces(a, drop)
    a, _ = compact_mesh(a, {})
    return a, int(drop.sum())


def _level_unions(m: MeshData) -> dict[tuple[int, float], object]:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    p = m.positions[m.face_v]
    fn = face_normals(m.positions, m.face_v, np.ones(m.n_faces, dtype=bool))
    d: dict[tuple[int, float], list] = {}
    for f in np.flatnonzero(np.abs(fn[:, 2]) > 0.9):
        pl = Polygon(p[f, :, :2])
        if pl.is_valid and pl.area > 1e-4:
            d.setdefault((1 if fn[f, 2] > 0 else -1, round(float(p[f, :, 2].mean()), 1)), []).append(pl)
    return {k: unary_union(v) for k, v in d.items()}


def orient_horizontals(b: MeshData, a: MeshData) -> tuple[MeshData, int]:
    """Make every horizontal face in `a` face the same way CKPT17 faces at that spot.

    Where CKPT17 has only an up-facing floor, the face must point up (players stand on it);
    where only down-facing, it must point down. Where CKPT17 has both (back-to-back), the engine's
    choice is kept. Geometry, UVs and materials are unchanged; only the winding is reversed.
    """
    from shapely.geometry import Polygon

    U = _level_unions(b)
    p = a.positions[a.face_v]
    fn = face_normals(a.positions, a.face_v, np.ones(a.n_faces, dtype=bool))
    n_flip = 0
    for f in np.flatnonzero(np.abs(fn[:, 2]) > 0.9):
        pl = Polygon(p[f, :, :2])
        if not pl.is_valid or pl.area <= 1e-4:
            continue
        z = round(float(p[f, :, 2].mean()), 1)
        cur = 1 if fn[f, 2] > 0 else -1
        same = U.get((cur, z))
        opp = U.get((-cur, z))
        a_same = pl.intersection(same).area if same is not None else 0.0
        a_opp = pl.intersection(opp).area if opp is not None else 0.0
        if a_opp > 0.5 * pl.area and a_same < 0.1 * pl.area:
            a.face_v[f] = a.face_v[f, [0, 2, 1]]
            if a.face_vt is not None and len(a.face_vt) == a.n_faces:
                a.face_vt[f] = a.face_vt[f, [0, 2, 1]]
            n_flip += 1
    return a, n_flip


def missing_by_direction(b: MeshData, a: MeshData) -> tuple[float, float]:
    """Sq ft of CKPT17 floor (up) / ceiling (down) not present in `a` facing the same way."""
    from shapely.geometry import Polygon

    B, A = _level_unions(b), _level_unions(a)
    out = {1: 0.0, -1: 0.0}
    for k, g in B.items():
        out[k[0]] += g.difference(A.get(k, Polygon())).area / SQFT
    return out[1], out[-1]


def restore_visible_back_to_back(b: MeshData, a: MeshData) -> tuple[MeshData, int, int]:
    """Zero-thickness slabs in CKPT17 carry an up face (floor) and a down face (ceiling) at the
    same height. The engine keeps only one, so the floor vanishes from above or the ceiling from
    below. Owner rule: nothing visible is deleted. Restore every CKPT17 horizontal face whose own
    side has open air (> 3 in) and which `a` does not show facing that way.

    Returns (mesh, n_restored, n_restored_with_different_look_than_other_side).
    """
    from shapely.geometry import Polygon

    center = (b.positions.min(axis=0) + b.positions.max(axis=0)) / 2.0
    bt = b.positions[b.face_v] - center
    fn = face_normals(b.positions, b.face_v, np.ones(b.n_faces, dtype=bool))
    ar = 0.5 * np.linalg.norm(np.cross(bt[:, 1] - bt[:, 0], bt[:, 2] - bt[:, 0]), axis=1)
    ok = np.flatnonzero((~np.isnan(fn).any(axis=1)) & (ar > 0.005))
    h = np.flatnonzero((~np.isnan(fn).any(axis=1)) & (ar > 0.005) & (np.abs(fn[:, 2]) > 0.9))
    if len(h) == 0:
        return a, 0, 0
    cb = EmbreeCaster(b.positions - center, b.face_v[ok])
    s = np.einsum("sb,fbk->fsk", BARY7[:4], bt[h]).reshape(-1, 3)
    n = np.repeat(fn[h], 4, axis=0)
    _, t = cb.first_hit(s + 0.08 * n, n)
    vis = h[t.reshape(len(h), 4).max(axis=1) > 3.0]

    A = _level_unions(a)
    Bm = {}  # material of the opposite CKPT17 side, per level, for look comparison
    p = b.positions[b.face_v]
    restore = []
    for f in vis:
        d = 1 if fn[f, 2] > 0 else -1
        z = round(float(p[f, :, 2].mean()), 1)
        pl = Polygon(p[f, :, :2])
        if not pl.is_valid or pl.area <= 1e-4:
            continue
        g = A.get((d, z))
        if g is None or pl.difference(g).area > 0.5 * pl.area:
            restore.append(int(f))
    if not restore:
        return a, 0, 0
    restore = np.asarray(restore, dtype=np.int64)

    # Look check: does the restored face differ in material from the face kept on the other side?
    a_p = a.positions[a.face_v]
    a_fn = face_normals(a.positions, a.face_v, np.ones(a.n_faces, dtype=bool))
    ca = EmbreeCaster(a.positions - center, a.face_v)
    cent = bt[restore].mean(axis=1)
    ih, th = ca.first_hit(cent + 0.05 * fn[restore], -fn[restore])
    diff_look = 0
    for i, f in enumerate(restore):
        if ih[i] >= 0 and th[i] <= 0.1:
            if a.materials[int(a.face_material[ih[i]])] != b.materials[int(b.face_material[f])]:
                diff_look += 1
    a = _append_before_faces(a, b, restore)
    a, _ = compact_mesh(a, {})
    return a, int(len(restore)), diff_look


def floor_guard(b: MeshData, a: MeshData) -> tuple[MeshData, int]:
    """Restore every visible CKPT17 floor (up) / ceiling (down) face not covered 7/7 in `a`."""
    center = (b.positions.min(axis=0) + b.positions.max(axis=0)) / 2.0
    bt = b.positions[b.face_v] - center
    fn_b = face_normals(b.positions, b.face_v, np.ones(b.n_faces, dtype=bool))
    area = 0.5 * np.linalg.norm(np.cross(bt[:, 1] - bt[:, 0], bt[:, 2] - bt[:, 0]), axis=1)
    ok = (~np.isnan(fn_b).any(axis=1)) & (np.linalg.norm(fn_b, axis=1) > 0.5) & (area > 0.005)
    horiz = ok & (np.abs(fn_b[:, 2]) > 0.9)
    ok_ids = np.flatnonzero(ok)
    h_ids = np.flatnonzero(horiz)
    if len(h_ids) == 0:
        return a, 0

    # Open air on the face's own side (above an up-floor, below a ceiling)?
    cb = EmbreeCaster(b.positions - center, b.face_v[ok_ids])
    samp = np.einsum("sb,fbk->fsk", BARY7[:4], bt[h_ids]).reshape(-1, 3)
    n4 = np.repeat(fn_b[h_ids], 4, axis=0)
    _, t_front = cb.first_hit(samp + 0.08 * n4, n4)
    front_open = t_front.reshape(len(h_ids), 4).max(axis=1)
    visible = h_ids[front_open > 3.0]  # 3 in of air in front = a surface you can see / walk on

    # 7-point coverage in the repaired mesh
    fn_a = face_normals(a.positions, a.face_v, np.ones(a.n_faces, dtype=bool))
    ok_a = np.flatnonzero((~np.isnan(fn_a).any(axis=1)) & (np.linalg.norm(fn_a, axis=1) > 0.5))
    ca = EmbreeCaster(a.positions - center, a.face_v[ok_a])
    s7 = np.einsum("sb,fbk->fsk", BARY7, bt[visible]).reshape(-1, 3)
    n7 = np.repeat(fn_b[visible], 7, axis=0)
    hit = np.zeros(len(s7), dtype=bool)
    for sign in (1.0, -1.0):
        ih, th = ca.first_hit(s7 + sign * 0.045 * n7, -sign * n7)
        c = np.flatnonzero((ih >= 0) & (np.abs(th - 0.045) <= 0.04))
        fh = ok_a[ih[c]]
        good = np.abs(np.einsum("ij,ij->i", n7[c], fn_a[fh])) >= 0.985
        hit[c[good]] = True
    missing = visible[~hit.reshape(len(visible), 7).all(axis=1)]
    if len(missing) == 0:
        return a, 0
    a = _append_before_faces(a, b, missing)
    a, _ = compact_mesh(a, {})
    return a, int(len(missing))


def main(uid: str, bldg: str, floor: str, source: str = "ckpt17") -> None:
    src_dir = SRC_ROOT / bldg / floor
    if source == "r5":
        # Owner 2026-11-11: the SketchUp R5 clean import (capms r5.skp slice) has the floors and parts
        # that the CHECKPOINT-17 export lacks. Repair that instead; it is also the guard reference.
        obj_p, mtl_p = WT_MODELS / uid / "skp_ref.obj", WT_MODELS / uid / "materials.mtl"
        before_name = "skp_ref.obj"
        print(f"=== Rerun {uid} from SKETCHUP R5 clean import: {obj_p}", flush=True)
        ckpt = read_obj(obj_p)
    else:
        obj_p, mtl_p = src_dir / f"{uid}.obj", src_dir / f"{uid}.mtl"
        before_name = "before.obj"
        print(f"=== Rerun {uid} from CHECKPOINT-17: {obj_p}", flush=True)
        ckpt = read_obj(obj_p)
        ckpt.positions = np.round(convert_unity_to_ckpt17_coords(ckpt.positions), 4)
    before = read_obj(WT_MODELS / uid / before_name)
    if before.n_faces != ckpt.n_faces:
        print(f"  [WARN] dashboard {before_name} ({before.n_faces}) != source ({ckpt.n_faces})", flush=True)

    # 1. Full engine pipeline on the source
    repaired, _rings, stats = repair_building_floor_mesh(ckpt, mtl_p)
    repaired, _ = compact_mesh(repaired, {})
    print(f"  engine: {ckpt.n_faces:,} -> {repaired.n_faces:,} tris | {json.dumps({k: v for k, v in stats.items() if k != 'merge_report'})}", flush=True)

    # Materials must match the source names for _append_before_faces
    # 2. Orientation fix + hole guard against the source (same CKPT17 frame)
    repaired, n_flip0 = orient_horizontals(before, repaired)
    repaired, n_floor = floor_guard(before, repaired)
    print(f"  floor guard: re-oriented {n_flip0:,} upside-down floor/ceiling faces, restored {n_floor:,} missing -> {repaired.n_faces:,} tris", flush=True)

    fn_out = face_normals(repaired.positions, repaired.face_v, np.ones(repaired.n_faces, dtype=bool))
    repaired.normals = np.round(fn_out, 4)
    repaired.face_vn = np.repeat(np.arange(repaired.n_faces, dtype=np.int64)[:, None], 3, axis=1)
    sync_after_to_all_siege(uid, compact_obj_bytes(repaired))

    # 3. Strict validator (13-pt phantom bridges, 7-pt small parts, R5 zero-loss) on the new after.obj
    res = repair_and_validate_unit(bldg.upper(), uid, before_name=before_name)
    print(f"  strict validator: {res}", flush=True)

    # 4. Final orientation + hole pass, then measurements
    after = read_obj(WT_MODELS / uid / "after.obj")
    after, n_flipped = orient_horizontals(before, after)
    after, n_floor2 = floor_guard(before, after)
    after, n_b2b, n_b2b_diff = restore_visible_back_to_back(before, after)
    print(f"  final pass: re-oriented {n_flipped:,}, restored {n_floor2:,} holes, restored {n_b2b:,} visible back-to-back floor/ceiling sides ({n_b2b_diff:,} with a different look than the other side)", flush=True)
    n_floor2 += n_b2b
    if n_floor2 or n_flipped:
        fn_out = face_normals(after.positions, after.face_v, np.ones(after.n_faces, dtype=bool))
        after.normals = np.round(fn_out, 4)
        after.face_vn = np.repeat(np.arange(after.n_faces, dtype=np.int64)[:, None], 3, axis=1)
        sync_after_to_all_siege(uid, compact_obj_bytes(after))
    _, n_left = floor_guard(before, after)
    miss_up, miss_dn = missing_by_direction(before, after)

    bu, bd, bt = horiz_area(before)
    au, ad, at = horiz_area(after)
    src_lbl = "R5" if source == "r5" else "CKPT17"
    print(f"  {src_lbl:6s} : floor_up={bu:9.1f} sqft  ceiling_down={bd:9.1f} sqft  total={bt:9.1f} sqft  tris={before.n_faces:,}", flush=True)
    print(f"  REPAIR : floor_up={au:9.1f} sqft  ceiling_down={ad:9.1f} sqft  total={at:9.1f} sqft  tris={after.n_faces:,}", flush=True)
    print(f"  {src_lbl} floor area missing/upside-down: {miss_up:.1f} sqft | ceiling area missing/upside-down: {miss_dn:.1f} sqft | uncovered visible horizontals: {n_left}", flush=True)

    out_bytes = (WT_MODELS / uid / "after.obj").read_bytes()
    exp = EXP_ROOT / bldg / floor
    if exp.exists():
        (exp / f"{uid}.fixed.obj").write_bytes(out_bytes)
        rp = exp / f"{uid}.report.json"
        rep = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
        rep.update({
            "unit": uid, "source": str(obj_p), "source_kind": "sketchup_r5_clean_import" if source == "r5" else "checkpoint17_export",
            "rerun_from_ckpt17": source != "r5",
            "tris_before": int(before.n_faces), "tris_after": int(after.n_faces),
            "floor_up_sqft_before": round(bu, 1), "floor_up_sqft_after": round(au, 1),
            "ceiling_down_sqft_before": round(bd, 1), "ceiling_down_sqft_after": round(ad, 1),
            "floor_guard_restored": int(n_floor + n_floor2), "visible_floor_faces_uncovered": int(n_left),
            "upside_down_reoriented": int(n_flip0 + n_flipped),
            "back_to_back_sides_restored": int(n_b2b),
            "back_to_back_sides_different_look_owner_review": int(n_b2b_diff),
            "floor_sqft_missing_or_upside_down": round(miss_up, 1),
            "ceiling_sqft_missing_or_upside_down": round(miss_dn, 1),
        })
        rp.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {exp / (uid + '.fixed.obj')}", flush=True)
    for alias in UNIT_ALIASES.get(uid, []):
        sync_after_to_all_siege(alias, out_bytes)


if __name__ == "__main__":
    main(*(sys.argv[1:5] if len(sys.argv) >= 4 else ("Main_2nd_Floor_obj", "Main", "Model-Floor_02")))
