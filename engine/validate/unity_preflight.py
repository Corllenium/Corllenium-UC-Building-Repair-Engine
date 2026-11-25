"""Unity 6 URP Near-Coplanar Z-Fighting Guard (`0.01–0.25 in`) & Export Pre-Flight Gate
(`engine.validate.unity_preflight`).

Addresses the Unity 6 URP/WebGL triangle hazards recorded in the handoff:
1. Near-coplanar face pairs separated by `0.01–0.25 in` (`0.25–6.35 mm`) that pass exact `0.000 in`
   coplanar checks in Blender but z-fight violently at 20–100 m in Unity depth buffers (`Near Clip = 0.05`).
2. Single-sided backface culling (`_Cull = Back`) requiring `reversed == 0`.
3. Zero-area faces, sub-2 mm PhysX MeshCollider / shadow-acne slivers (respecting the Zero-Hole Safety Law
   so real architectural railings/trim are reported separately), metre Y-up scale, and valid topology.
"""
from __future__ import annotations

from collections import defaultdict
import numpy as np
from shapely.geometry import Polygon

from engine.detectors.errors import find_errors
from engine.fixes.patch_protect import _tri_geometry_stats, detect_piercing_needle_slivers
from engine.fixes.pipeline import FixProfile
from engine.fixes.remove import remove_faces
from engine.model import MeshData
from engine.topo.planes import face_normals, plane_basis

INCH_TO_METRE = 0.0254


def _finish_tier(mat_name: str) -> int:
    """Priority tier matching building_repair.py: finish textures beat raw buried concrete."""
    low = mat_name.lower()
    if any(k in low for k in ("quartz", "glass", "iron", "prismarine", "metal", "wood", "tile", "brick", "wool")):
        return 2
    if "littletiles" in low:
        return 1
    return 0


def _scale_to_inches(mesh: MeshData) -> float:
    units = getattr(mesh, "units", None)
    if units == "metres":
        return 1.0 / INCH_TO_METRE
    if units == "inches":
        return 1.0
    lo, hi = mesh.bbox()
    max_ext = float((hi - lo).max())
    if max_ext > 0.0 and max_ext < 120.0:
        return 1.0 / INCH_TO_METRE
    return 1.0


def detect_near_coplanar_zfight(
    mesh: MeshData,
    *,
    min_dist_in: float = 0.01,
    max_dist_in: float = 0.25,
    normal_dot_min: float = 0.995,
    min_overlap_sqin: float = 1.0,
    max_spots: int = 24,
) -> dict:
    """Detect parallel overlapping triangle pairs separated by `[min_dist_in, max_dist_in]` inches."""
    if mesh.n_faces < 2:
        return {"pair_count": 0, "pairs": [], "face_ids": [], "spots": []}

    scale_in = _scale_to_inches(mesh)
    pos = mesh.positions * scale_in
    pts = pos[mesh.face_v]
    fn = face_normals(pos, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)
    ok = (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) > 0.5) & (areas >= 0.05)

    fids = np.flatnonzero(ok)
    if len(fids) < 2:
        return {"pair_count": 0, "pairs": [], "face_ids": [], "spots": []}

    # Canonical hemisphere normal so +n and -n share normal buckets
    cn = fn[fids].copy()
    for i in range(len(fids)):
        n = cn[i]
        for k in range(3):
            if abs(float(n[k])) > 0.1:
                if float(n[k]) < 0.0:
                    cn[i] = -n
                break

    # Bucket by quantized normal direction + plane offset slab (width = max_dist_in + 0.05)
    slab = max(max_dist_in + 0.05, 0.30)
    buckets: dict[tuple[int, int, int, int], list[int]] = defaultdict(list)
    centroids = pts[fids].mean(axis=1)
    offsets = np.einsum("ij,ij->i", centroids, cn)

    for idx_local in range(len(fids)):
        n = cn[idx_local]
        nb = (int(round(float(n[0]) * 10)), int(round(float(n[1]) * 10)), int(round(float(n[2]) * 10)))
        sb = int(np.floor(float(offsets[idx_local]) / slab))
        buckets[(nb[0], nb[1], nb[2], sb)].append(idx_local)

    pairs: list[tuple[int, int, float, float]] = []
    seen_pairs: set[tuple[int, int]] = set()
    affected: set[int] = set()
    spots: list[dict] = []

    for (nx, ny, nz, sb), members in buckets.items():
        # Compare within slab AND against next slab (sb + 1) to catch boundary-straddling pairs
        nbrs = members + buckets.get((nx, ny, nz, sb + 1), [])
        if len(nbrs) < 2:
            continue
        # Use first member's canonical normal as local projection basis
        ref_n = cn[members[0]]
        u_ax, v_ax = plane_basis(ref_n)

        # Precompute 2D AABBs for fast rejection
        p2_cache: dict[int, tuple[np.ndarray, float, float, float, float]] = {}
        for m_i in nbrs:
            if m_i in p2_cache:
                continue
            f = int(fids[m_i])
            p2 = np.column_stack([pts[f] @ u_ax, pts[f] @ v_ax])
            p2_cache[m_i] = (
                p2,
                float(p2[:, 0].min()),
                float(p2[:, 0].max()),
                float(p2[:, 1].min()),
                float(p2[:, 1].max()),
            )

        poly_cache: dict[int, Polygon | None] = {}
        n_m = len(members)
        for a_idx in range(n_m):
            ia = members[a_idx]
            fa = int(fids[ia])
            p2a, ax0, ax1, ay0, ay1 = p2_cache[ia]
            na = cn[ia]
            oa = float(offsets[ia])
            for b_idx in range(a_idx + 1, len(nbrs)):
                ib = nbrs[b_idx]
                fb = int(fids[ib])
                if fa == fb:
                    continue
                pk = (fa, fb) if fa < fb else (fb, fa)
                if pk in seen_pairs:
                    continue
                if float(np.dot(na, cn[ib])) < normal_dot_min:
                    continue
                dist = abs(oa - float(offsets[ib]))
                if dist < min_dist_in or dist > max_dist_in:
                    continue
                p2b, bx0, bx1, by0, by1 = p2_cache[ib]
                if ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0:
                    continue
                if ia not in poly_cache:
                    pa = Polygon(p2a)
                    poly_cache[ia] = pa if (pa.is_valid and pa.area > 0.05) else None
                if ib not in poly_cache:
                    pb = Polygon(p2b)
                    poly_cache[ib] = pb if (pb.is_valid and pb.area > 0.05) else None
                pa, pb = poly_cache[ia], poly_cache[ib]
                if pa is None or pb is None:
                    continue
                ovl = float(pa.intersection(pb).area)
                if ovl >= min_overlap_sqin:
                    seen_pairs.add(pk)
                    pairs.append((pk[0], pk[1], round(dist, 4), round(ovl, 2)))
                    affected.add(pk[0])
                    affected.add(pk[1])

    pairs.sort(key=lambda r: (-r[3], r[2]))
    for fa, fb, dist, ovl in pairs[:max_spots]:
        cen = 0.5 * (pos[mesh.face_v[fa]].mean(axis=0) + pos[mesh.face_v[fb]].mean(axis=0))
        spots.append(
            {
                "label": f"Near-coplanar Z-fight (gap={dist:.3f}in, overlap={ovl:.1f}sqin)",
                "centre": [round(float(v), 2) for v in cen],
                "size": round(float(np.sqrt(max(ovl, 1.0))), 2),
                "faces": [fa, fb],
            }
        )

    return {
        "pair_count": len(pairs),
        "pairs": pairs,
        "face_ids": sorted(affected),
        "spots": spots,
    }


def resolve_near_coplanar_zfight(
    mesh: MeshData,
    *,
    visible_mask: np.ndarray | None = None,
    min_dist_in: float = 0.01,
    max_dist_in: float = 0.25,
    min_overlap_sqin: float = 1.0,
) -> tuple[MeshData, dict]:
    """Drop the lower-priority buried twin of each near-coplanar Z-fighting pair."""
    det = detect_near_coplanar_zfight(
        mesh,
        min_dist_in=min_dist_in,
        max_dist_in=max_dist_in,
        min_overlap_sqin=min_overlap_sqin,
    )
    if det["pair_count"] == 0:
        return mesh, {"pairs_before": 0, "faces_dropped": 0, "pairs_after": 0}

    scale_in = _scale_to_inches(mesh)
    pos = mesh.positions * scale_in
    pts = pos[mesh.face_v]
    areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)

    def _rank(f: int) -> tuple[int, int, float]:
        vis = 1 if (visible_mask is not None and bool(visible_mask[f])) else 0
        m_idx = int(mesh.face_material[f])
        m_name = mesh.materials[m_idx] if 0 <= m_idx < len(mesh.materials) else ""
        return (vis, _finish_tier(m_name), float(areas[f]))

    drop = np.zeros(mesh.n_faces, dtype=bool)
    for fa, fb, _dist, ovl in det["pairs"]:
        if drop[fa] or drop[fb]:
            continue
        # Only drop a face when the overlap covers a substantial fraction of the losing face
        ra, rb = _rank(fa), _rank(fb)
        loser = fb if ra >= rb else fa
        if ovl >= 0.45 * float(areas[loser]):
            drop[loser] = True

    if not drop.any():
        return mesh, {"pairs_before": det["pair_count"], "faces_dropped": 0, "pairs_after": det["pair_count"]}

    cleaned, _ = remove_faces(mesh, drop)
    after = detect_near_coplanar_zfight(
        cleaned,
        min_dist_in=min_dist_in,
        max_dist_in=max_dist_in,
        min_overlap_sqin=min_overlap_sqin,
    )
    return cleaned, {
        "pairs_before": det["pair_count"],
        "faces_dropped": int(drop.sum()),
        "pairs_after": after["pair_count"],
    }


def run_unity_preflight_gate(
    mesh: MeshData,
    *,
    expected_units: str = "metres",
    min_alt_mm: float = 2.0,
    profile: FixProfile | None = None,
) -> dict:
    """Run the Unity 6 URP Export Pre-Flight Gate on a candidate floor/building mesh."""
    if mesh.n_faces == 0:
        return {"passed": False, "reason": "empty_mesh", "checks": {}, "counts": {}, "spots": []}

    finite_ok = bool(np.isfinite(mesh.positions).all())
    idx_ok = bool((mesh.face_v >= 0).all() and (mesh.face_v < len(mesh.positions)).all())
    no_self_dup = bool(
        ((mesh.face_v[:, 0] != mesh.face_v[:, 1])
         & (mesh.face_v[:, 1] != mesh.face_v[:, 2])
         & (mesh.face_v[:, 2] != mesh.face_v[:, 0])).all()
    )
    canon_tris = np.sort(mesh.face_v, axis=1)
    dup_tris = int(len(canon_tris) - len(np.unique(canon_tris, axis=0)))
    topo_valid = finite_ok and idx_ok and no_self_dup and (dup_tris == 0)

    lo, hi = mesh.bbox()
    size = hi - lo
    if expected_units == "metres":
        # Unity Y-up metres: typical floor/building height Y in [0.5m, 80m], horizontal X/Z <= 250m
        scale_ok = bool(0.2 <= float(size[1]) <= 80.0 and float(max(size[0], size[2])) <= 250.0)
        scale_to_mm = 1000.0
    else:
        scale_ok = bool(10.0 <= float(size[2]) <= 3200.0)
        scale_to_mm = 25.4

    prof = profile or FixProfile(guard_size=(256, 256), n_dirs=64)
    errs = find_errors(mesh, profile=prof)
    zfight = detect_near_coplanar_zfight(mesh, min_dist_in=0.01, max_dist_in=0.25)

    areas, _max_e, min_alt = _tri_geometry_stats(mesh.positions, mesh.face_v)
    min_alt_mm_arr = min_alt * scale_to_mm
    zero_area_count = int(errs["loose_parts"]["zero_area"])
    reversed_count = int(errs["counts"]["reversed"])
    flicker_diff = int(errs["counts"]["flicker_diff"])
    flicker_same = int(errs["counts"]["flicker_same"])

    # Distinguish unprotected needle slivers (D02) from protected thin architectural bars (D16)
    sliver_mask, sliver_spots = detect_piercing_needle_slivers(mesh)
    sub_2mm_all = int((min_alt_mm_arr < min_alt_mm).sum())
    sub_2mm_unprotected = int(((min_alt_mm_arr < min_alt_mm) & sliver_mask).sum())

    checks = {
        "scale_and_up_axis": {
            "passed": scale_ok,
            "expected_units": expected_units,
            "bbox_size": [round(float(v), 3) for v in size],
        },
        "zero_reversed_normals": {
            "passed": reversed_count == 0,
            "count": reversed_count,
        },
        "zero_area_faces": {
            "passed": zero_area_count == 0,
            "count": zero_area_count,
        },
        "zero_exact_flicker": {
            "passed": (flicker_diff == 0 and flicker_same == 0),
            "flicker_diff": flicker_diff,
            "flicker_same": flicker_same,
        },
        "zero_near_coplanar_zfight": {
            "passed": zfight["pair_count"] == 0,
            "pair_count": zfight["pair_count"],
        },
        "min_altitude_gate": {
            "passed": sub_2mm_unprotected == 0,
            "threshold_mm": min_alt_mm,
            "sub_threshold_total": sub_2mm_all,
            "sub_threshold_unprotected_slivers": sub_2mm_unprotected,
        },
        "topology_valid": {
            "passed": topo_valid,
            "finite_positions": finite_ok,
            "valid_indices": idx_ok,
            "no_degenerate_indices": no_self_dup,
            "duplicate_triangles": dup_tris,
        },
    }
    passed = all(c["passed"] for c in checks.values())
    return {
        "passed": passed,
        "checks": checks,
        "counts": {
            "faces": int(mesh.n_faces),
            "vertices": int(len(mesh.positions)),
            "reversed": reversed_count,
            "zero_area": zero_area_count,
            "flicker_diff": flicker_diff,
            "flicker_same": flicker_same,
            "near_coplanar_zfight": int(zfight["pair_count"]),
            "cracks": int(errs["counts"]["cracks"]),
            "sub_2mm_total": sub_2mm_all,
            "sub_2mm_unprotected": sub_2mm_unprotected,
        },
        "spots": (zfight["spots"] + sliver_spots)[:24],
    }
