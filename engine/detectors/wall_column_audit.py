"""Wall & Column Cutaway Readiness and G01/G02 Health Audit (`engine.detectors.wall_column_audit`).

Measures every wall/column defect that breaks Homescape-style display/hide transitions and Unity 6 URP:
- Trapped internal wall cavity faces (D11/D15): vertical faces hitting another surface < 0.85 m on BOTH sides
- Non-manifold wall edges (internal hollow-wall ribs/partitions)
- Open wall edges (D03/D04/D14 unsealed caps/jambs/notches)
- Reversed wall normals (E2, breaks Unity URP _Cull = Back & UCDollhouseCutaway facing check)
- Overhead beam / door lintel faces (min height > 1.5 m above local floor)
- Diagonal full-height spanning wall triangles (> 1.5 m vertical span)
- Near-coplanar Z-fighting pairs (0.01–0.25 in) & cross-plane T-junction cracks
- Per-group solid watertightness (`open_edges == 0`, `nonmanifold_edges == 0`, `signed_volume > 0`)
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
import numpy as np

from engine.detectors.errors import find_errors
from engine.fixes.pipeline import FixProfile
from engine.model import MeshData
from engine.pipeline import analyse_topology, topology_stats
from engine.rays.caster import EmbreeCaster
from engine.topo.adjacency import build_edge_table, degenerate_mask, edge_face_lists
from engine.topo.edges import EDGE_NONMANIFOLD, EDGE_OPEN, EDGE_TJUNCTION
from engine.topo.planes import face_normals
from engine.topo.weld import weld_exact
from engine.validate.unity_preflight import detect_near_coplanar_zfight

INCH_TO_METRE = 0.0254


def _detect_frame(mesh: MeshData) -> tuple[int, float, str]:
    """Return (up_axis, scale_to_metres, frame_label)."""
    lo, hi = mesh.bbox()
    size = hi - lo
    if getattr(mesh, "units", "inches") == "metres" or (
        float(size[1]) < float(size[0]) and float(size[1]) < float(size[2]) and float(size.max()) < 250.0
    ):
        return 1, 1.0, "Y-up (metres)"
    return 2, INCH_TO_METRE, "Z-up (inches)"


def signed_volume(positions: np.ndarray, face_v: np.ndarray) -> float:
    """Signed volume of a closed triangle mesh (positive = outward-facing winding)."""
    if len(face_v) == 0:
        return 0.0
    # Center to avoid catastrophic cancellation in large survey/CKPT17 coordinates
    c = positions[face_v].reshape(-1, 3).mean(axis=0)
    tri = positions[face_v] - c
    return float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)


def _group_solid_metrics(mesh: MeshData, face_ids: np.ndarray, up_axis: int) -> dict:
    sub_fv = mesh.face_v[face_ids]
    used, inv = np.unique(sub_fv, return_inverse=True)
    sub_pos = mesh.positions[used]
    sub_f = inv.reshape(-1, 3)

    pos_w, remap = weld_exact(sub_pos, mesh.coord_decimals)
    fw = remap[sub_f]
    ok = ~degenerate_mask(pos_w, fw)
    table = build_edge_table(fw, ok)
    ef = edge_face_lists(table)
    open_e = sum(1 for fl in ef if len(fl) == 1)
    nonman_e = sum(1 for fl in ef if len(fl) > 2)
    vol = signed_volume(pos_w, fw[ok])
    # In Y-up Unity coordinates exported with -X flip, determinant is +1 so signed_volume > 0 is outward too
    watertight = (open_e == 0) and (nonman_e == 0) and (vol > 0.0)
    lo, hi = sub_pos.min(axis=0), sub_pos.max(axis=0)
    return {
        "tris": int(len(face_ids)),
        "open_edges": int(open_e),
        "nonmanifold_edges": int(nonman_e),
        "signed_volume": round(float(vol), 4),
        "watertight": bool(watertight),
        "bbox_min": [round(float(v), 3) for v in lo],
        "bbox_max": [round(float(v), 3) for v in hi],
    }


def audit_wall_column_health(
    mesh: MeshData,
    *,
    face_groups: Sequence[str] | None = None,
    profile: FixProfile | None = None,
    cavity_dist_m: float = 0.85,
) -> dict:
    """Measure wall/column cutaway health, internal cavity debris, and per-group watertightness."""
    if mesh.n_faces == 0:
        return {"frame": "empty", "counts": {}, "per_group_solids": {}, "spots": []}

    up_axis, scale_m, frame_label = _detect_frame(mesh)
    prof = profile or FixProfile(guard_size=(256, 256), n_dirs=64)
    topo = analyse_topology(mesh)
    stats = topology_stats(topo)
    errs = find_errors(mesh, profile=prof)
    zfight = detect_near_coplanar_zfight(mesh, min_dist_in=0.01, max_dist_in=0.25)

    fn = face_normals(topo.positions_w, topo.face_w, topo.ok)
    pts = topo.positions_w[topo.face_w]
    lo, hi = topo.positions_w.min(axis=0), topo.positions_w.max(axis=0)

    up_nz = np.abs(fn[:, up_axis])
    vert_mask = topo.ok & (up_nz < 0.25)
    horiz_mask = topo.ok & (up_nz > 0.75)

    h_vals = pts[:, :, up_axis]
    h_min_rel_m = (h_vals.min(axis=1) - float(lo[up_axis])) * scale_m
    h_span_m = (h_vals.max(axis=1) - h_vals.min(axis=1)) * scale_m

    diag_span_tris = int((vert_mask & (h_span_m > 1.5)).sum())
    overhead_faces = int((topo.ok & (h_min_rel_m > 1.5)).sum())

    # Open / non-manifold / T-junction edges touching vertical wall/column faces
    ef = edge_face_lists(topo.table)
    wall_open = 0
    wall_nonman = 0
    wall_tjunc = 0
    for ei, fl in enumerate(ef):
        if not any(vert_mask[f] for f in fl):
            continue
        ec = topo.edge_class[ei]
        if ec == EDGE_OPEN:
            wall_open += 1
        elif ec == EDGE_NONMANIFOLD:
            wall_nonman += 1
        elif ec == EDGE_TJUNCTION:
            wall_tjunc += 1

    # Ray-cavity test: vertical faces trapped < cavity_dist_m on BOTH +n and -n (D11/D15 internal ribs)
    v_ids = np.flatnonzero(vert_mask)
    trapped_ids: list[int] = []
    if len(v_ids) > 0:
        caster = EmbreeCaster(topo.positions_w, topo.face_w[topo.ok])
        v_cent = pts[v_ids].mean(axis=1)
        v_n = fn[v_ids]
        eps = 0.01 / scale_m
        _, tf = caster.first_hit(v_cent + eps * v_n, v_n)
        _, tb = caster.first_hit(v_cent - eps * v_n, -v_n)
        trapped_mask = (tf * scale_m < cavity_dist_m) & (tb * scale_m < cavity_dist_m)
        trapped_ids = [int(v_ids[i]) for i in np.flatnonzero(trapped_mask)]

    rev_set = set(errs["faces"].get("reversed", ()))
    reversed_wall = sum(1 for f in v_ids.tolist() if f in rev_set)

    per_group: dict[str, dict] = {}
    if face_groups is not None and len(face_groups) == mesh.n_faces:
        by_g: dict[str, list[int]] = defaultdict(list)
        for fi, gname in enumerate(face_groups):
            by_g[str(gname)].append(fi)
        for gname in sorted(by_g):
            per_group[gname] = _group_solid_metrics(mesh, np.asarray(by_g[gname], dtype=np.int64), up_axis)

    spots: list[dict] = []
    for fid in trapped_ids[:16]:
        cen = pts[fid].mean(axis=0)
        spots.append(
            {
                "label": f"D11/D15 trapped wall cavity face #{fid}",
                "centre": [round(float(v), 2) for v in cen],
                "faceId": fid,
                "defectClass": "D11",
            }
        )

    return {
        "frame": frame_label,
        "bbox_size_m": [round(float(v * scale_m), 3) for v in (hi - lo)],
        "counts": {
            "faces": int(mesh.n_faces),
            "vertical_faces": int(vert_mask.sum()),
            "horizontal_faces": int(horiz_mask.sum()),
            "trapped_cavity_faces": int(len(trapped_ids)),
            "nonmanifold_wall_edges": int(wall_nonman),
            "open_wall_edges": int(wall_open),
            "tjunction_wall_edges": int(wall_tjunc),
            "reversed_wall_normals": int(reversed_wall),
            "reversed_total": int(errs["counts"]["reversed"]),
            "hidden_total": int(errs["counts"]["hidden"]),
            "flicker_diff": int(errs["counts"]["flicker_diff"]),
            "flicker_same": int(errs["counts"]["flicker_same"]),
            "near_coplanar_zfight_pairs": int(zfight["pair_count"]),
            "t_junction_cracks": int(stats["edges_with_t_vertices"]),
            "zero_area_faces": int(stats["zero_area_faces"]),
            "overhead_beam_lintel_faces": int(overhead_faces),
            "diagonal_spanning_wall_tris": int(diag_span_tris),
        },
        "per_group_solids": per_group,
        "spots": spots,
    }
