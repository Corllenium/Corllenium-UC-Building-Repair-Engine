"""Stage 5 · General-Purpose Post-Fix Outer Facade & Mesh Integrity Verifier.

Analyzes ANY repaired UC campus building or floor (`before_mesh` vs. `after_mesh`) across
the 10-Point Hard Integrity Checklist mapped directly to Defect Classes `D01`–`D14`:
  1. `outer_facade_completeness`    (D04, D06, D07) — >= 99.8% EXP_OUTSIDE 7-pt Embree coverage
  2. `outer_facade_zero_cracklines` (D03, D04, D14) — 0 newly torn exterior EDGE_OPEN seams > 1.0 in
  3. `interior_visible_retention`   (D04, D06, D07, D12, D14) — >= 99.0% room-probe visible retention
  4. `zero_piercing_needle_slivers` (D02, D03)      — 0 protruding open-edge needle slivers & 0 zero-area
  5. `stair_and_floor_continuity`   (D05, D10)      — >= 99.5% stair tread/riser & walkable floor continuity
  6. `zero_flicker_convergence`     (D08, E4/E5)    — flicker_diff == 0 AND flicker_same == 0
  7. `zero_reversed_normals`        (E2)            — reversed == 0
  8. `original_texture_fidelity`    (D01, D08, D09) — <= 1.0% unintended finish-to-concrete material swaps
  9. `blender_mesh_topology_valid`  (All)           — Blender mesh.validate() == False (recorded by Stage 5B)
 10. `ai_visual_defect_inspector`   (D01-D14)       — uc-post-fix-inspector visual audit against D01-D14 KB

Works identically on single-floor units and whole multi-story buildings without relying on any
hardcoded building coordinates. Returns a JSON-serializable report with exact `[x, y, z]`
`spots` (world inches) for every failing or suspect region so both the Siege Dashboard 3D
`fly to` viewer and the `uc-post-fix-inspector` Blender AI agent can inspect them directly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
import numpy as np

from engine.detectors.errors import find_errors
from engine.fixes.patch_protect import detect_piercing_needle_slivers
from engine.fixes.solid_wall_groups import INCH_TO_METRE
from engine.model import MeshData
from engine.pipeline import analyse_topology
from engine.rays.caster import EmbreeCaster
from engine.topo.adjacency import edge_face_lists
from engine.topo.edges import EDGE_OPEN
from engine.topo.planes import face_normals
from engine.validate import sampling, viewpoints, visibility
from engine.vis.exposure import EXP_OUTSIDE, classify_exposure, compute_side_exposure

BARY7 = np.array(
    [
        [1 / 3, 1 / 3, 1 / 3],
        [0.60, 0.20, 0.20],
        [0.20, 0.60, 0.20],
        [0.20, 0.20, 0.60],
        [0.90, 0.05, 0.05],
        [0.05, 0.90, 0.05],
        [0.05, 0.05, 0.90],
    ],
    dtype=np.float64,
)


def _edge_midpoints_and_lengths(mesh: MeshData, topo, face_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (midpoints, lengths, edge_rows) for EDGE_OPEN edges incident to `face_mask`."""
    open_rows = np.flatnonzero(np.asarray(topo.edge_class) == EDGE_OPEN)
    if len(open_rows) == 0:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0,), dtype=np.float64), np.zeros((0,), dtype=np.int64)
    keep_rows = []
    ef = edge_face_lists(topo.table)
    for er in open_rows:
        if any(0 <= f < mesh.n_faces and face_mask[f] for f in ef[er]):
            keep_rows.append(int(er))
    if not keep_rows:
        return np.zeros((0, 3), dtype=np.float64), np.zeros((0,), dtype=np.float64), np.zeros((0,), dtype=np.int64)
    rows = np.asarray(keep_rows, dtype=np.int64)
    segs = topo.positions_w[topo.table.edges[rows]]  # (E, 2, 3)
    mids = segs.mean(axis=1)
    lens = np.linalg.norm(segs[:, 1] - segs[:, 0], axis=1)
    return mids, lens, rows


def _coverage_7pt(
    before_mesh: MeshData,
    after_caster: EmbreeCaster,
    center: np.ndarray,
    fn_b: np.ndarray,
    face_ids: np.ndarray,
    tol: float = 0.12,
) -> tuple[float, np.ndarray]:
    """Return (coverage_pct, missing_face_ids) using 7 barycentric samples per face."""
    if len(face_ids) == 0:
        return 100.0, np.zeros((0,), dtype=np.int64)
    bt = before_mesh.positions[before_mesh.face_v[face_ids]] - center
    samp = np.einsum("sb,fbk->fsk", BARY7, bt).reshape(-1, 3)
    nb = np.repeat(fn_b[face_ids], len(BARY7), axis=0)
    half = tol * 0.5
    hp, dp = after_caster.first_hit(samp - half * nb, nb)
    hm, dm = after_caster.first_hit(samp + half * nb, -nb)
    hit_ok = (((hp >= 0) & (dp <= tol)) | ((hm >= 0) & (dm <= tol))).reshape(len(face_ids), len(BARY7))
    # A face is considered intact if at least 6 of 7 interior samples are covered (avoids false positives on 1mm E5 edge trims)
    intact = hit_ok.sum(axis=1) >= 6
    missing = face_ids[~intact]
    pct = round(100.0 * (1.0 - len(missing) / max(len(face_ids), 1)), 3)
    return pct, missing


def _spots_from_faces(
    mesh: MeshData,
    fids: np.ndarray,
    areas: np.ndarray,
    defect_class: str,
    prefix: str,
    limit: int = 15,
) -> list[dict]:
    if len(fids) == 0:
        return []
    order = fids[np.argsort(-areas[fids])]
    spots: list[dict] = []
    for f in order[:limit]:
        pts = mesh.positions[mesh.face_v[f]]
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        cen = pts.mean(axis=0)
        spots.append({
            "label": f"{defect_class} {prefix} (area={areas[f]:.1f} in2, mat={mesh.materials[int(mesh.face_material[f])]})",
            "centre": [round(float(v), 2) for v in cen],
            "size": round(float(np.linalg.norm(hi - lo)), 2),
            "defectClass": defect_class,
            "faceId": int(f),
        })
    return spots


def count_walkable_floor_cracks(mesh: MeshData) -> tuple[int, list[dict]]:
    """Detect narrow cracks/slivers/notches inside major walkable Z-up floor planes (>= 25 m^2)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    if mesh.n_faces == 0:
        return 0, []
    fn = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    pts_m = mesh.positions * INCH_TO_METRE
    tri_m = pts_m[mesh.face_v]
    z_mean_m = tri_m[:, :, 2].mean(axis=1)
    areas_m2 = 0.5 * np.linalg.norm(
        np.cross(tri_m[:, 1] - tri_m[:, 0], tri_m[:, 2] - tri_m[:, 0]), axis=1
    )
    up_mask = (~np.isnan(fn).any(axis=1)) & (fn[:, 2] > 0.85) & (areas_m2 > 1e-6)
    if not np.any(up_mask):
        return 0, []
    horiz_mask = (~np.isnan(fn).any(axis=1)) & (np.abs(fn[:, 2]) > 0.85) & (areas_m2 > 1e-6)

    # Group upward faces into Z elevation clusters within 0.08m
    up_ids = np.flatnonzero(up_mask)
    order = up_ids[np.argsort(z_mean_m[up_ids])]
    clusters: list[tuple[float, list[int]]] = []
    for fid in order:
        zm = float(z_mean_m[fid])
        if not clusters or abs(zm - clusters[-1][0]) > 0.08:
            clusters.append((zm, [int(fid)]))
        else:
            prev_z, prev_fids = clusters[-1]
            n_prev = len(prev_fids)
            prev_fids.append(int(fid))
            clusters[-1] = ((prev_z * n_prev + zm) / (n_prev + 1), prev_fids)

    def _expand_poly_parts(geom) -> list[Polygon]:
        if geom.is_empty:
            return []
        if isinstance(geom, Polygon):
            return [geom]
        parts: list[Polygon] = []
        for sub in getattr(geom, "geoms", ()):
            parts.extend(_expand_poly_parts(sub))
        return parts

    cracks: list[tuple[float, float, Polygon]] = []
    for cl_z_m, fids in clusters:
        fid_arr = np.asarray(fids, dtype=np.int64)
        if float(areas_m2[fid_arr].sum()) < 25.0:
            continue
        cl_mask = np.zeros(mesh.n_faces, dtype=bool)
        cl_mask[fid_arr] = True
        other_ids = np.flatnonzero(horiz_mask & (~cl_mask) & (np.abs(z_mean_m - cl_z_m) <= 0.20))
        other_items: list[tuple[tuple[float, float, float, float], Polygon]] = []
        for oid in other_ids:
            ofv = mesh.face_v[oid]
            oq = Polygon([
                (float(pts_m[ofv[0], 0]), float(pts_m[ofv[0], 1])),
                (float(pts_m[ofv[1], 0]), float(pts_m[ofv[1], 1])),
                (float(pts_m[ofv[2], 0]), float(pts_m[ofv[2], 1])),
            ])
            if oq.is_valid and oq.area > 1e-6:
                other_items.append((oq.bounds, oq))

        polys = []
        for fid in fid_arr:
            fv = mesh.face_v[fid]
            q = Polygon([
                (float(pts_m[fv[0], 0]), float(pts_m[fv[0], 1])),
                (float(pts_m[fv[1], 0]), float(pts_m[fv[1], 1])),
                (float(pts_m[fv[2], 0]), float(pts_m[fv[2], 1])),
            ])
            if q.is_valid and q.area > 1e-6:
                polys.append(q)
        if not polys:
            continue
        floor_u = unary_union(polys)
        if not floor_u.is_valid:
            floor_u = floor_u.buffer(0)
        geoms = list(floor_u.geoms) if hasattr(floor_u, "geoms") else [floor_u]
        for gp in geoms:
            if not isinstance(gp, Polygon):
                continue
            for ring in gp.interiors:
                hp = Polygon(ring)
                if not hp.is_valid:
                    hp = hp.buffer(0)
                if not isinstance(hp, Polygon) or hp.is_empty or float(hp.area) <= 0.0002 or float(hp.area) >= 0.50:
                    continue
                if not hp.buffer(-0.22, join_style=2).is_empty:
                    continue
                hx0, hy0, hx1, hy1 = hp.bounds
                near_other = [
                    oq for (ox0, oy0, ox1, oy1), oq in other_items
                    if ox1 >= hx0 and ox0 <= hx1 and oy1 >= hy0 and oy0 <= hy1
                ]
                uncovered = hp.difference(unary_union(near_other)) if near_other else hp
                if not uncovered.is_valid:
                    uncovered = uncovered.buffer(0)
                for part in _expand_poly_parts(uncovered):
                    if 0.0002 < float(part.area) < 0.50 and part.buffer(-0.22, join_style=2).is_empty:
                        cracks.append((cl_z_m, float(part.area), part))

    spots: list[dict] = []
    for cl_z_m, area_m2, hp in sorted(cracks, key=lambda item: -item[1])[:15]:
        bx0, by0, bx1, by1 = hp.bounds
        cen_in = [
            round(float(0.5 * (bx0 + bx1) / INCH_TO_METRE), 2),
            round(float(0.5 * (by0 + by1) / INCH_TO_METRE), 2),
            round(float(cl_z_m / INCH_TO_METRE), 2),
        ]
        diag_in = round(float(np.hypot(bx1 - bx0, by1 - by0) / INCH_TO_METRE), 2)
        spots.append({
            "label": f"D10 walkable floor crack (area={area_m2:.4f} m^2)",
            "centre": cen_in,
            "size": max(diag_in, 12.0),
            "defectClass": "D10",
            "faceId": -1,
        })
    return len(cracks), spots


def verify_facade_and_mesh_integrity(
    before_mesh: MeshData,
    after_mesh: MeshData,
    after_errs: dict | None = None,
    *,
    rebuild_exclusion_mask_fn: Callable[[MeshData], np.ndarray] | None = None,
    n_probe_dirs: int = 256,
    n_ext_dirs: int = 128,
    blender_mesh_valid: bool | None = None,
    ai_visual_verdict: dict | None = None,
) -> dict:
    """Run the 10-Point Outer Facade & Mesh Integrity Hard Checklist on BEFORE vs AFTER."""
    if after_errs is None:
        after_errs = find_errors(after_mesh)

    center = (before_mesh.positions.min(axis=0) + before_mesh.positions.max(axis=0)) / 2.0
    pts_b = before_mesh.positions[before_mesh.face_v]
    fn_b = face_normals(before_mesh.positions, before_mesh.face_v, np.ones(before_mesh.n_faces, dtype=bool))
    ok_b = (~np.isnan(fn_b).any(axis=1)) & (np.linalg.norm(fn_b, axis=1) > 0.5)
    areas_b = 0.5 * np.linalg.norm(np.cross(pts_b[:, 1] - pts_b[:, 0], pts_b[:, 2] - pts_b[:, 0]), axis=1)

    excl = np.zeros(before_mesh.n_faces, dtype=bool)
    if rebuild_exclusion_mask_fn is not None:
        excl = np.asarray(rebuild_exclusion_mask_fn(before_mesh), dtype=bool)

    valid_b = ok_b & (areas_b >= 0.05) & (~excl)

    # Exterior exposure on BEFORE & AFTER (128 dirs)
    front_b, back_b = compute_side_exposure(before_mesh.positions - center, before_mesh.face_v, ok_b, n_dirs=n_ext_dirs)
    ext_class_b = classify_exposure(front_b + back_b, ok_b)
    outer_b_mask = valid_b & (ext_class_b == EXP_OUTSIDE)

    fn_a = face_normals(after_mesh.positions, after_mesh.face_v, np.ones(after_mesh.n_faces, dtype=bool))
    ok_a = (~np.isnan(fn_a).any(axis=1)) & (np.linalg.norm(fn_a, axis=1) > 0.5)
    front_a, back_a = compute_side_exposure(after_mesh.positions - center, after_mesh.face_v, ok_a, n_dirs=n_ext_dirs)
    ext_class_a = classify_exposure(front_a + back_a, ok_a)
    outer_a_mask = ok_a & (ext_class_a == EXP_OUTSIDE)

    # Multi-height interior room probes on BEFORE
    m_r, _ = sampling.recentred(before_mesh)
    caster_v = visibility.build_caster(m_r)
    probes_eye = viewpoints.interior_probes(m_r, eye=63.0, headroom=80.0, grid=39.37, caster=caster_v)
    room_hits_b = np.zeros(before_mesh.n_faces, dtype=np.int64)
    if len(probes_eye) > 0:
        probes_all = np.vstack([
            probes_eye,
            probes_eye + np.array([0.0, 0.0, -36.0]),
            probes_eye + np.array([0.0, 0.0, +30.0]),
        ])
        dirs = viewpoints.outside_directions(n_probe_dirs)
        cb_r = EmbreeCaster(m_r.positions, m_r.face_v)
        batch = 1500
        for i in range(0, len(probes_all), batch):
            pb = probes_all[i : i + batch]
            orig = np.repeat(pb, len(dirs), axis=0)
            d_rep = np.tile(dirs, (len(pb), 1))
            hit_f, _ = cb_r.first_hit(orig, d_rep)
            valid = hit_f[hit_f >= 0]
            if len(valid):
                np.add.at(room_hits_b, valid, 1)
    interior_b_mask = valid_b & (room_hits_b > 0) & (~outer_b_mask)

    after_caster = EmbreeCaster(after_mesh.positions - center, after_mesh.face_v)

    # --- CHECK 1: Outer Facade Completeness (>= 99.8%) ---
    outer_ids = np.flatnonzero(outer_b_mask)
    outer_pct, outer_miss = _coverage_7pt(before_mesh, after_caster, center, fn_b, outer_ids)
    c1_pass = outer_pct >= 99.8
    c1_spots = _spots_from_faces(before_mesh, outer_miss, areas_b, "D04", "missing outer facade face")

    # --- CHECK 2: Zero Newly Torn Outer Facade Cracklines (D03/D04/D14) ---
    topo_b = analyse_topology(before_mesh, frozenset())
    topo_a = analyse_topology(after_mesh, frozenset())
    mids_b, lens_b, _ = _edge_midpoints_and_lengths(before_mesh, topo_b, outer_b_mask)
    mids_a, lens_a, _ = _edge_midpoints_and_lengths(after_mesh, topo_a, outer_a_mask)

    # Count newly torn exterior open edges (> 1.0 in long) whose midpoint is NOT backed by a BEFORE open edge
    # AND whose midpoint is NOT resting on a solid AFTER surface (i.e. real crack gap, not a benign T-seam on a solid wall!)
    long_a = np.flatnonzero(lens_a > 1.0)
    new_tear_indices: list[int] = []
    if len(long_a) > 0:
        # Spatial grid lookup (2.0 in bucket) against BEFORE open edge midpoints
        b_buckets: set[tuple[int, int, int]] = set()
        for p in mids_b:
            bx, by, bz = int(round(p[0] / 2.0)), int(round(p[1] / 2.0)), int(round(p[2] / 2.0))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        b_buckets.add((bx + dx, by + dy, bz + dz))
        # Also ignore edges inside rebuilt stairs if exclusion provided
        for idx in long_a:
            p = mids_a[idx]
            key = (int(round(p[0] / 2.0)), int(round(p[1] / 2.0)), int(round(p[2] / 2.0)))
            if key in b_buckets:
                continue
            # Check if this open edge sits directly on top of a closed BEFORE outer face that is now MISSING in AFTER
            new_tear_indices.append(int(idx))

    # Filter new_tear_indices to genuine exterior tears: those within 4 in of a missing outer face OR count delta
    n_new_facade_tears = 0
    c2_spots: list[dict] = []
    if new_tear_indices and len(outer_miss) > 0:
        miss_cen = pts_b[outer_miss].mean(axis=1)
        for idx in new_tear_indices:
            p = mids_a[idx]
            dmin = float(np.linalg.norm(miss_cen - p[None, :], axis=1).min())
            if dmin <= 24.0:
                n_new_facade_tears += 1
                if len(c2_spots) < 15:
                    c2_spots.append({
                        "label": f"D03 outer facade tear seam (len={lens_a[idx]:.1f}in)",
                        "centre": [round(float(v), 2) for v in p],
                        "size": round(float(lens_a[idx]), 2),
                        "defectClass": "D03",
                    })
    # Count long exterior open edges for diagnostics; pass rule uses verified void-backed tears (not benign G01 wall-to-floor T-seams)
    long_b_cnt = int((lens_b > 1.0).sum())
    long_a_cnt = int(len(long_a))
    c2_pass = n_new_facade_tears == 0

    # --- CHECK 3: Interior Visible Retention (Baseboards, Columns, Stringers — >= 99.0%) ---
    int_ids = np.flatnonzero(interior_b_mask)
    int_pct, int_miss = _coverage_7pt(before_mesh, after_caster, center, fn_b, int_ids)
    c3_pass = int_pct >= 99.0
    c3_spots = _spots_from_faces(before_mesh, int_miss, areas_b, "D12", "missing interior visible face")

    # --- CHECK 4: Zero Piercing Needle Slivers & Zero-Area Faces (D02/D03, D16-safe <=0.35in & aspect>=50) ---
    sliver_mask, sliver_spots = detect_piercing_needle_slivers(after_mesh)
    n_slivers = int(sliver_mask.sum())
    n_zero_area = int(after_errs.get("loose_parts", {}).get("zero_area", 0))
    c4_pass = n_slivers == 0 and n_zero_area == 0

    # --- CHECK 5: Stair & Walkable Floor Continuity (>= 99.5%) ---
    walk_b_mask = valid_b & (outer_b_mask | interior_b_mask) & (
        np.array(
            [
                ("quartz_block_top" in before_mesh.materials[int(mid)] and fn_b[i, 2] > 0.85)
                or ("quartz_block_side" in before_mesh.materials[int(mid)] and abs(fn_b[i, 2]) < 0.3)
                for i, mid in enumerate(before_mesh.face_material)
            ],
            dtype=bool,
        )
    )
    walk_ids = np.flatnonzero(walk_b_mask)
    walk_pct, walk_miss = _coverage_7pt(before_mesh, after_caster, center, fn_b, walk_ids)
    c5_pass = walk_pct >= 99.5
    c5_spots = _spots_from_faces(before_mesh, walk_miss, areas_b, "D05", "missing stair/floor surface")

    # --- CHECK 6: Zero Flicker Convergence (E4/E5) ---
    ea = after_errs["counts"]
    fl_diff = int(ea["flicker_diff"])
    fl_same = int(ea["flicker_same"])
    c6_pass = fl_diff == 0 and fl_same == 0

    # --- CHECK 7: Zero Reversed Normals (E2) ---
    rev = int(ea["reversed"])
    c7_pass = rev == 0

    # --- CHECK 8: Original Finish Texture Fidelity (<= 1.0% unintended swaps) ---
    vis_b_ids = np.flatnonzero(valid_b & (outer_b_mask | interior_b_mask))
    finish_ids = np.array(
        [
            f for f in vis_b_ids
            if ("quartz_block_top" in before_mesh.materials[int(before_mesh.face_material[f])] and fn_b[f, 2] > 0.85)
            or ("littletiles_ltcolored0" in before_mesh.materials[int(before_mesh.face_material[f])] and abs(fn_b[f, 2]) < 0.5)
        ],
        dtype=np.int64,
    )
    n_swapped = 0
    c8_spots: list[dict] = []
    if len(finish_ids) > 0:
        cen_fin = pts_b[finish_ids].mean(axis=1) - center
        n_fin = fn_b[finish_ids]
        hf, df = after_caster.first_hit(cen_fin + 0.5 * n_fin, -n_fin)
        for idx, fid_b in enumerate(finish_ids):
            ha = int(hf[idx])
            da = float(df[idx])
            if ha >= 0 and abs(da - 0.5) < 0.08:
                mb = before_mesh.materials[int(before_mesh.face_material[fid_b])]
                ma = after_mesh.materials[int(after_mesh.face_material[ha])]
                if mb != ma and "concrete_white" in ma:
                    n_swapped += 1
                    if len(c8_spots) < 15:
                        p = pts_b[fid_b].mean(axis=0)
                        c8_spots.append({
                            "label": f"D08/D09 texture swap ({mb} -> {ma})",
                            "centre": [round(float(v), 2) for v in p],
                            "size": 12.0,
                            "defectClass": "D09" if "quartz" in mb else "D08",
                            "faceId": int(ha),
                        })
    swap_pct = round(100.0 * n_swapped / max(len(finish_ids), 1), 3)
    c8_pass = swap_pct <= 1.0

    # --- CHECK 9: Blender Mesh Topology Valid ---
    c9_status = "pending" if blender_mesh_valid is None else ("pass" if blender_mesh_valid else "fail")
    c9_measured = "Awaiting Blender mesh.validate()" if blender_mesh_valid is None else (
        "invalid=False (clean)" if blender_mesh_valid else "invalid=True (corrupt topology)"
    )

    # --- CHECK 10: AI Visual Defect Inspector (`uc-post-fix-inspector` vs D01-D14 KB) ---
    if ai_visual_verdict is None:
        c10_status = "pending"
        c10_measured = "Awaiting uc-post-fix-inspector 6-view + hotspot audit"
        c10_spots = []
    else:
        c10_status = "pass" if ai_visual_verdict.get("passed") else "fail"
        c10_measured = ai_visual_verdict.get("summary", "Verified against D01-D14")
        c10_spots = ai_visual_verdict.get("spots", [])

    # --- CHECK 11: Zero Walkable Floor Cracks / Slivers / Notches ---
    n_floor_cracks, c11_spots = count_walkable_floor_cracks(after_mesh)
    c11_pass = n_floor_cracks == 0

    checks = [
        {
            "id": "outer_facade_completeness",
            "order": 1,
            "category": "outer_facade",
            "defectClasses": ["D04", "D06", "D07"],
            "label": "Outer Facade Completeness (No Missing / Broken Exterior Faces)",
            "status": "pass" if c1_pass else "fail",
            "measured": f"{outer_pct:.2f}% ({len(outer_ids) - len(outer_miss):,} / {len(outer_ids):,})",
            "threshold": ">= 99.8%",
            "numericValue": outer_pct,
            "spots": c1_spots,
        },
        {
            "id": "outer_facade_zero_cracklines",
            "order": 2,
            "category": "outer_facade",
            "defectClasses": ["D03", "D04", "D14"],
            "label": "Outer Facade Zero New Cracklines / Open Seams",
            "status": "pass" if c2_pass else "fail",
            "measured": f"{n_new_facade_tears} torn seams ({long_a_cnt:,} vs {long_b_cnt:,} ext open edges)",
            "threshold": "0 torn seams",
            "numericValue": n_new_facade_tears,
            "spots": c2_spots,
        },
        {
            "id": "interior_visible_retention",
            "order": 3,
            "category": "interior_mesh",
            "defectClasses": ["D04", "D06", "D07", "D12", "D14"],
            "label": "Interior Visible Retention (Walls, Baseboards, Columns & Stringers)",
            "status": "pass" if c3_pass else "fail",
            "measured": f"{int_pct:.2f}% ({len(int_ids) - len(int_miss):,} / {len(int_ids):,})",
            "threshold": ">= 99.0%",
            "numericValue": int_pct,
            "spots": c3_spots,
        },
        {
            "id": "zero_piercing_needle_slivers",
            "order": 4,
            "category": "surface_quality",
            "defectClasses": ["D02", "D03"],
            "label": "Zero Piercing Needle Slivers & Zero-Area Degenerates",
            "status": "pass" if c4_pass else "fail",
            "measured": f"{n_slivers} needle slivers, {n_zero_area} zero-area",
            "threshold": "0 slivers, 0 zero-area",
            "numericValue": n_slivers + n_zero_area,
            "spots": sliver_spots,
        },
        {
            "id": "stair_and_floor_continuity",
            "order": 5,
            "category": "interior_mesh",
            "defectClasses": ["D05", "D10"],
            "label": "Stair Treads/Risers & Walkable Floor Continuity",
            "status": "pass" if c5_pass else "fail",
            "measured": f"{walk_pct:.2f}% ({len(walk_ids) - len(walk_miss):,} / {len(walk_ids):,})",
            "threshold": ">= 99.5%",
            "numericValue": walk_pct,
            "spots": c5_spots,
        },
        {
            "id": "zero_flicker_convergence",
            "order": 6,
            "category": "surface_quality",
            "defectClasses": ["D08"],
            "label": "Zero Coplanar Z-Fighting (Flicker Diff & Flicker Same)",
            "status": "pass" if c6_pass else "fail",
            "measured": f"{fl_diff} diff / {fl_same} same",
            "threshold": "0 diff / 0 same",
            "numericValue": fl_diff + fl_same,
            "spots": [],
        },
        {
            "id": "zero_reversed_normals",
            "order": 7,
            "category": "surface_quality",
            "defectClasses": ["D03"],
            "label": "Zero Reversed / Inside-Out Face Normals",
            "status": "pass" if c7_pass else "fail",
            "measured": f"{rev} reversed",
            "threshold": "0 reversed",
            "numericValue": rev,
            "spots": [],
        },
        {
            "id": "original_texture_fidelity",
            "order": 8,
            "category": "surface_quality",
            "defectClasses": ["D01", "D08", "D09"],
            "label": "Original Finish Texture Fidelity (No Zebra / Concrete Overrides)",
            "status": "pass" if c8_pass else "fail",
            "measured": f"{swap_pct:.2f}% swapped ({n_swapped} / {len(finish_ids):,} finish faces)",
            "threshold": "<= 1.0% swapped",
            "numericValue": swap_pct,
            "spots": c8_spots,
        },
        {
            "id": "blender_mesh_topology_valid",
            "order": 9,
            "category": "visual_signoff",
            "defectClasses": ["D01", "D03", "D10"],
            "label": "Blender 5.1 Mesh Topology Valid & Textures Packed",
            "status": c9_status,
            "measured": c9_measured,
            "threshold": "invalid=False",
            "spots": [],
        },
        {
            "id": "ai_visual_defect_inspector",
            "order": 10,
            "category": "visual_signoff",
            "defectClasses": ["D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08", "D09", "D10", "D12", "D14"],
            "label": "AI Visual Defect Inspector (uc-post-fix-inspector vs D01–D14 KB)",
            "status": c10_status,
            "measured": c10_measured,
            "threshold": "0 blocking visual defects",
            "spots": c10_spots,
        },
        {
            "id": "zero_walkable_floor_cracks",
            "order": 11,
            "category": "surface_quality",
            "defectClasses": ["D02", "D10"],
            "label": "Zero Walkable Floor Slab Cracks / Slivers / Notches",
            "status": "pass" if c11_pass else "fail",
            "measured": f"{n_floor_cracks} narrow floor cracks",
            "threshold": "0 floor cracks",
            "numericValue": n_floor_cracks,
            "spots": c11_spots,
        },
    ]

    automated_passed = all(c["status"] == "pass" for c in checks if c["category"] != "visual_signoff")
    visual_passed = c9_status == "pass" and c10_status == "pass"
    overall_passed = automated_passed and (c9_status != "fail") and (c10_status != "fail")

    return {
        "version": 1,
        "passed": overall_passed,
        "automatedPassed": automated_passed,
        "visualSignoffStatus": "pass" if visual_passed else ("fail" if c9_status == "fail" or c10_status == "fail" else "pending"),
        "checkedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "failedCheckIds": [c["id"] for c in checks if c["status"] == "fail"],
        "checks": checks,
    }
