"""Universal Any-Shape New Mesh Hole Detector (`engine.validate.hole_detector`).

Catches destroyed-mesh holes of ANY shape or size across exterior walls, interior walls,
baseboards, floors, ceilings, and ground slabs — including small corner triangles, hairline
edge slits, rectangular notches, trapezoids, and irregular polygon holes that fixed-point
surface sampling (`_coverage_7pt`) can miss.

Algorithm (zero hardcoded coordinates — works on any single floor or whole building):
  1. Extract ALL `EDGE_OPEN` boundary edges on `AFTER` and `BEFORE`.
  2. Subtract real `BEFORE` architectural openings (doorways, windows, roof/floor rims)
     using a 3D spatial bucket lookup on edge midpoints (`1.5 in` tolerance).
  3. Probe `0.6 in` across each candidate NEW open edge (stepping outward from its host
     triangle in the host plane) against `AFTER` via Embree:
       - If an in-plane solid face covers the stepped point -> benign T-junction seam (ignore).
       - If NO surface covers the stepped point -> confirmed VOID-LEAK HOLE EDGE!
  4. Group connected void-leak hole edges into loops / slits and classify shape:
       - `edge_slit`     (1–2 edges)
       - `triangle_hole` (3 edges, closed or open)
       - `quad_notch`    (4 edges)
       - `polygon_hole`  (5+ edges)
  5. Return exact counts, incident `after` face IDs, 3D edge segments, and `[x, y, z]` spots.
"""
from __future__ import annotations

from collections import defaultdict
import numpy as np

from engine.model import MeshData
from engine.pipeline import analyse_topology
from engine.rays.caster import EmbreeCaster
from engine.topo.adjacency import edge_face_lists
from engine.topo.edges import EDGE_OPEN
from engine.topo.planes import face_normals


def _open_edge_records(mesh: MeshData) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (segs (E,2,3), mids (E,3), lens (E,), host_face (E,)) for all EDGE_OPEN edges."""
    topo = analyse_topology(mesh, frozenset())
    open_rows = np.flatnonzero(np.asarray(topo.edge_class) == EDGE_OPEN)
    if len(open_rows) == 0:
        return (
            np.zeros((0, 2, 3), dtype=np.float64),
            np.zeros((0, 3), dtype=np.float64),
            np.zeros((0,), dtype=np.float64),
            np.zeros((0,), dtype=np.int64),
        )
    ef = edge_face_lists(topo.table)
    segs = topo.positions_w[topo.table.edges[open_rows]]  # (E, 2, 3)
    mids = segs.mean(axis=1)
    lens = np.linalg.norm(segs[:, 1] - segs[:, 0], axis=1)
    hosts = np.full(len(open_rows), -1, dtype=np.int64)
    for idx, er in enumerate(open_rows):
        fl = ef[er]
        if len(fl) > 0:
            hosts[idx] = int(fl[0])
    return segs, mids, lens, hosts


def detect_new_mesh_holes(
    before_mesh: MeshData,
    after_mesh: MeshData,
    *,
    min_edge_len_in: float = 0.25,
    before_match_tol_in: float = 1.5,
    probe_step_in: float = 0.6,
    plane_hit_tol_in: float = 0.20,
    max_spots: int = 24,
    visible_only: bool = True,
    visible_host_mask: np.ndarray | None = None,
) -> dict:
    """Detect newly created void-leaking mesh holes of any shape/size on `after_mesh` vs `before_mesh`.

    When `visible_only=True` (default), restricts reported holes to faces visible from outside
    (`EXP_OUTSIDE`) or interior rooms so cleaned hollow-wall internal cavity seams (`G01`)
    do not pollute visible hole alerts.
    """
    _, mids_b, _, _ = _open_edge_records(before_mesh)
    segs_a, mids_a, lens_a, hosts_a = _open_edge_records(after_mesh)

    if len(segs_a) == 0:
        return {
            "holeCount": 0,
            "voidLeakEdgeCount": 0,
            "byShape": {"edge_slit": 0, "triangle_hole": 0, "quad_notch": 0, "polygon_hole": 0},
            "holeFaceIds": [],
            "spots": [],
        }

    # Optional visibility filter (outer facade + room-visible interior faces only)
    vis_mask: np.ndarray | None = None
    if visible_host_mask is not None:
        vis_mask = np.asarray(visible_host_mask, dtype=bool)
    elif visible_only and after_mesh.n_faces > 0:
        from engine.validate import sampling, viewpoints, visibility
        from engine.vis.exposure import EXP_OUTSIDE, classify_exposure, compute_side_exposure

        fn_v = face_normals(after_mesh.positions, after_mesh.face_v, np.ones(after_mesh.n_faces, dtype=bool))
        ok_v = (~np.isnan(fn_v).any(axis=1)) & (np.linalg.norm(fn_v, axis=1) > 0.5)
        cen_v = 0.5 * (after_mesh.positions.min(axis=0) + after_mesh.positions.max(axis=0))
        ef_v, eb_v = compute_side_exposure(after_mesh.positions - cen_v, after_mesh.face_v, ok_v, n_dirs=64)
        vis_mask = ok_v & (classify_exposure(ef_v + eb_v, ok_v) == EXP_OUTSIDE)

        m_r, _ = sampling.recentred(after_mesh)
        caster_v = visibility.build_caster(m_r)
        probes_eye = viewpoints.interior_probes(m_r, eye=63.0, headroom=80.0, grid=39.37, caster=caster_v)
        if len(probes_eye) > 0:
            probes_all = np.vstack([
                probes_eye,
                probes_eye + np.array([0.0, 0.0, -36.0]),
                probes_eye + np.array([0.0, 0.0, +30.0]),
            ])
            dirs_p = viewpoints.outside_directions(64)
            ca_r = EmbreeCaster(m_r.positions, m_r.face_v)
            for i in range(0, len(probes_all), 1500):
                pb = probes_all[i : i + 1500]
                orig = np.repeat(pb, len(dirs_p), axis=0)
                d_rep = np.tile(dirs_p, (len(pb), 1))
                hit_f, _ = ca_r.first_hit(orig, d_rep)
                valid_h = hit_f[hit_f >= 0]
                if len(valid_h):
                    vis_mask[valid_h] = True

    # Build 3D spatial bucket set of BEFORE open-edge midpoints (real doors/windows/perimeters)
    cell = max(before_match_tol_in, 0.5)
    b_buckets: set[tuple[int, int, int]] = set()
    for p in mids_b:
        bx, by, bz = int(round(p[0] / cell)), int(round(p[1] / cell)), int(round(p[2] / cell))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    b_buckets.add((bx + dx, by + dy, bz + dz))

    cand_idx: list[int] = []
    for i in range(len(segs_a)):
        hf = int(hosts_a[i])
        if lens_a[i] < min_edge_len_in or hf < 0 or hf >= after_mesh.n_faces:
            continue
        if vis_mask is not None and not vis_mask[hf]:
            continue
        p = mids_a[i]
        key = (int(round(p[0] / cell)), int(round(p[1] / cell)), int(round(p[2] / cell)))
        if key not in b_buckets:
            cand_idx.append(i)

    if not cand_idx:
        return {
            "holeCount": 0,
            "voidLeakEdgeCount": 0,
            "byShape": {"edge_slit": 0, "triangle_hole": 0, "quad_notch": 0, "polygon_hole": 0},
            "holeFaceIds": [],
            "spots": [],
        }

    cand_arr = np.asarray(cand_idx, dtype=np.int64)
    fn_a = face_normals(after_mesh.positions, after_mesh.face_v, np.ones(after_mesh.n_faces, dtype=bool))
    pts_a = after_mesh.positions[after_mesh.face_v]
    center = 0.5 * (before_mesh.positions.min(axis=0) + before_mesh.positions.max(axis=0))
    caster_a = EmbreeCaster(after_mesh.positions - center, after_mesh.face_v)
    caster_b = EmbreeCaster(before_mesh.positions - center, before_mesh.face_v)

    # For each candidate new open edge, step `probe_step_in` OUTWARD from its host triangle in the host plane
    # and ray-test along +/- normal against BOTH `after` and `before`:
    #   - If covered in `after` -> benign T-junction seam (ignore)
    #   - If NOT covered in `before` either -> clean wall-to-floor/column corner junction where a buried cap was removed (NOT a hole!)
    #   - If solidly covered in `before` AND missing in `after` -> 100% CONFIRMED DESTROYED-MESH HOLE (any shape/size)!
    probe_pts: list[np.ndarray] = []
    probe_ns: list[np.ndarray] = []
    valid_cands: list[int] = []

    for ci in cand_arr:
        hf = int(hosts_a[ci])
        n = fn_a[hf]
        if np.isnan(n).any() or np.linalg.norm(n) < 0.5:
            continue
        p0, p1 = segs_a[ci, 0], segs_a[ci, 1]
        mid = 0.5 * (p0 + p1)
        e_vec = p1 - p0
        e_len = float(np.linalg.norm(e_vec))
        if e_len < 1e-6:
            continue
        e_dir = e_vec / e_len
        # Outward in-plane perpendicular pointing AWAY from the host triangle's centroid
        perp = np.cross(n, e_dir)
        plen = float(np.linalg.norm(perp))
        if plen < 1e-6:
            continue
        perp /= plen
        tri_cen = pts_a[hf].mean(axis=0)
        if float(np.dot(perp, tri_cen - mid)) > 0.0:
            perp = -perp

        step = min(probe_step_in, max(0.15, 0.35 * e_len))
        probe_pts.append((mid + step * perp) - center)
        probe_ns.append(n)
        valid_cands.append(int(ci))

    if not valid_cands:
        return {
            "holeCount": 0,
            "voidLeakEdgeCount": 0,
            "byShape": {"edge_slit": 0, "triangle_hole": 0, "quad_notch": 0, "polygon_hole": 0},
            "holeFaceIds": [],
            "spots": [],
        }

    p_arr = np.asarray(probe_pts, dtype=np.float64)
    n_arr = np.asarray(probe_ns, dtype=np.float64)
    half = plane_hit_tol_in * 0.5
    hp_a, dp_a = caster_a.first_hit(p_arr - half * n_arr, n_arr)
    hm_a, dm_a = caster_a.first_hit(p_arr + half * n_arr, -n_arr)
    covered_after = ((hp_a >= 0) & (dp_a <= plane_hit_tol_in)) | ((hm_a >= 0) & (dm_a <= plane_hit_tol_in))

    hp_b, dp_b = caster_b.first_hit(p_arr - half * n_arr, n_arr)
    hm_b, dm_b = caster_b.first_hit(p_arr + half * n_arr, -n_arr)
    existed_before = ((hp_b >= 0) & (dp_b <= plane_hit_tol_in)) | ((hm_b >= 0) & (dm_b <= plane_hit_tol_in))

    leak_cands = [valid_cands[k] for k in range(len(valid_cands)) if (not covered_after[k]) and existed_before[k]]

    if not leak_cands:
        return {
            "holeCount": 0,
            "voidLeakEdgeCount": 0,
            "byShape": {"edge_slit": 0, "triangle_hole": 0, "quad_notch": 0, "polygon_hole": 0},
            "holeFaceIds": [],
            "spots": [],
        }

    # Group connected void-leak edges into hole loops / slits via quantized endpoint vertices (0.20 in)
    q = 5.0  # 1 / 0.20 in
    v_to_edges: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    edge_vkeys: dict[int, tuple[tuple[int, int, int], tuple[int, int, int]]] = {}
    for ci in leak_cands:
        k0 = tuple(np.round(segs_a[ci, 0] * q).astype(np.int64).tolist())
        k1 = tuple(np.round(segs_a[ci, 1] * q).astype(np.int64).tolist())
        edge_vkeys[ci] = (k0, k1)
        v_to_edges[k0].append(ci)
        v_to_edges[k1].append(ci)

    visited: set[int] = set()
    components: list[list[int]] = []
    for ci in leak_cands:
        if ci in visited:
            continue
        comp: list[int] = []
        stack = [ci]
        visited.add(ci)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            k0, k1 = edge_vkeys[cur]
            for vk in (k0, k1):
                for nb in v_to_edges[vk]:
                    if nb not in visited:
                        visited.add(nb)
                        stack.append(nb)
        components.append(comp)

    by_shape = {"edge_slit": 0, "triangle_hole": 0, "quad_notch": 0, "polygon_hole": 0}
    hole_faces: set[int] = set()
    spot_rows: list[tuple[float, dict]] = []

    for comp in components:
        n_e = len(comp)
        if n_e <= 2:
            shape = "edge_slit"
        elif n_e == 3:
            shape = "triangle_hole"
        elif n_e == 4:
            shape = "quad_notch"
        else:
            shape = "polygon_hole"
        by_shape[shape] += 1

        comp_mids = mids_a[comp]
        perim = float(lens_a[comp].sum())
        cen = comp_mids.mean(axis=0)
        for ci in comp:
            hole_faces.add(int(hosts_a[ci]))
        spot_rows.append(
            (
                perim,
                {
                    "label": f"New {shape} ({n_e} edges, perimeter={perim:.1f}in)",
                    "centre": [round(float(v), 2) for v in cen],
                    "size": round(perim, 2),
                    "shape": shape,
                    "edgeCount": n_e,
                    "defectClass": "D14",
                },
            )
        )

    spot_rows.sort(key=lambda r: -r[0])
    return {
        "holeCount": len(components),
        "voidLeakEdgeCount": len(leak_cands),
        "byShape": by_shape,
        "holeFaceIds": sorted(hole_faces),
        "spots": [s for _, s in spot_rows[:max_spots]],
    }
