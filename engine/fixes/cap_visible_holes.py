"""Planar Visible-Hole Auto-Capper (`engine.fixes.cap_visible_holes`).

Closes verified planar void-leak loops returned by `engine.validate.hole_detector.detect_new_mesh_holes`
(`triangle_hole`, `quad_notch`, `polygon_hole`) strictly under AGENTS.md §4 E8 (narrow flat fill):
- Uses ONLY existing loop vertices (never invents or moves a vertex).
- Requires every loop vertex to lie within `max_plane_dev_in` of the dominant host plane.
- Inherits the dominant host material, outward normal winding, and affine-fitted host UVs.
"""
from __future__ import annotations

import copy
import numpy as np
import shapely
from shapely.geometry import Polygon

from engine.model import MeshData
from engine.topo.planes import face_normals, plane_basis
from engine.validate.hole_detector import detect_new_mesh_holes


def _dominant_host_plane(
    mesh: MeshData,
    fn: np.ndarray,
    host_faces: list[int],
) -> tuple[np.ndarray, np.ndarray, int, list[int]] | None:
    """Return (plane_origin, unit_normal, dominant_material, matching_host_faces)."""
    valid_hosts = [
        f for f in host_faces
        if 0 <= f < mesh.n_faces and (not np.isnan(fn[f]).any()) and float(np.linalg.norm(fn[f])) > 0.5
    ]
    if not valid_hosts:
        return None

    pts = mesh.positions[mesh.face_v[valid_hosts]]
    areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)
    # Cluster host normals around the largest-area host face so perpendicular corner faces don't skew the plane
    seed_idx = int(np.argmax(areas))
    seed_n = fn[valid_hosts[seed_idx]]

    aligned_hosts: list[int] = []
    aligned_areas: list[float] = []
    mat_weights: dict[int, float] = {}
    for k, hf in enumerate(valid_hosts):
        if float(np.dot(fn[hf], seed_n)) >= 0.96:
            aligned_hosts.append(hf)
            a = float(areas[k])
            aligned_areas.append(a)
            m = int(mesh.face_material[hf])
            mat_weights[m] = mat_weights.get(m, 0.0) + a

    if not aligned_hosts:
        return None
    w_arr = np.asarray(aligned_areas, dtype=np.float64)
    w_sum = float(w_arr.sum())
    if w_sum <= 1e-9:
        return None

    n_avg = (fn[aligned_hosts] * w_arr[:, None]).sum(axis=0)
    n_len = float(np.linalg.norm(n_avg))
    if n_len < 1e-6:
        return None
    n_avg /= n_len

    centers = mesh.positions[mesh.face_v[aligned_hosts]].mean(axis=1)
    origin = (centers * w_arr[:, None]).sum(axis=0) / w_sum
    dom_mat = max(mat_weights, key=lambda m: mat_weights[m])
    return origin, n_avg, dom_mat, aligned_hosts


def _fit_host_uv_affine(
    mesh: MeshData,
    host_faces: list[int],
    dom_mat: int,
    origin: np.ndarray,
    u_ax: np.ndarray,
    v_ax: np.ndarray,
) -> np.ndarray | None:
    if mesh.uvs is None or len(mesh.uvs) == 0 or mesh.face_vt is None:
        return None
    xy_rows: list[np.ndarray] = []
    uv_rows: list[np.ndarray] = []
    for hf in host_faces:
        if int(mesh.face_material[hf]) != dom_mat:
            continue
        vt = mesh.face_vt[hf]
        if not (vt >= 0).all():
            continue
        p3 = mesh.positions[mesh.face_v[hf]] - origin
        xy = np.column_stack([p3 @ u_ax, p3 @ v_ax])
        xy_rows.append(xy)
        uv_rows.append(mesh.uvs[vt])
    if not xy_rows:
        return None
    X = np.vstack(xy_rows)
    U = np.vstack(uv_rows)
    A = np.column_stack([X, np.ones(len(X), dtype=np.float64)])
    try:
        sol, _, _, _ = np.linalg.lstsq(A, U, rcond=None)
        return sol
    except Exception:
        return None


def cap_visible_planar_holes(
    before_mesh: MeshData,
    after_mesh: MeshData,
    *,
    visible_only: bool = True,
    max_plane_dev_in: float = 0.15,
    max_loop_area_sqin: float = 15000.0,
) -> tuple[MeshData, dict]:
    """Auto-cap closed planar void-leak loops using existing vertices only (AGENTS.md §4 E8)."""
    before_rep = detect_new_mesh_holes(before_mesh, after_mesh, visible_only=visible_only)
    loops = before_rep.get("loops", [])
    if not loops:
        return after_mesh, {
            "loops_seen": 0,
            "loops_capped": 0,
            "tris_added": 0,
            "holes_before": int(before_rep["holeCount"]),
            "holes_after": int(before_rep["holeCount"]),
            "skipped_reasons": {},
        }

    fn = face_normals(after_mesh.positions, after_mesh.face_v, np.ones(after_mesh.n_faces, dtype=bool))
    existing_tris = {tuple(sorted(row.tolist())) for row in after_mesh.face_v}

    new_fv: list[list[int]] = []
    new_fvt: list[list[int]] = []
    new_fvn: list[list[int]] = []
    new_fmat: list[int] = []
    new_uvs: list[np.ndarray] = []
    has_uvs = after_mesh.uvs is not None and len(after_mesh.uvs) > 0 and after_mesh.face_vt is not None
    next_vt = len(after_mesh.uvs) if has_uvs else 0

    loops_capped = 0
    skipped: dict[str, int] = {}

    def _skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    for loop in loops:
        if not loop.get("closed"):
            _skip("not_closed")
            continue
        vs = [int(v) for v in loop.get("ordered_vertices", [])]
        if len(vs) < 3:
            _skip("too_few_vertices")
            continue
        plane = _dominant_host_plane(after_mesh, fn, loop.get("host_faces", []))
        if plane is None:
            _skip("no_host_plane")
            continue
        origin, n_avg, dom_mat, aligned_hosts = plane
        p3 = after_mesh.positions[vs]
        devs = np.abs((p3 - origin) @ n_avg)
        if float(devs.max()) > max_plane_dev_in:
            _skip("non_planar")
            continue

        u_ax, v_ax = plane_basis(n_avg)
        rel = p3 - origin
        p2 = np.column_stack([rel @ u_ax, rel @ v_ax])
        poly = Polygon(p2)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.geom_type != "Polygon" or float(poly.area) <= 0.05:
            _skip("invalid_polygon")
            continue
        if float(poly.area) > max_loop_area_sqin:
            _skip("exceeds_max_area")
            continue

        # Triangulate strictly on existing loop vertices
        if len(vs) == 3:
            tri_v_lists = [vs]
        else:
            try:
                cdt = shapely.constrained_delaunay_triangles(poly)
                parts = list(cdt.geoms) if hasattr(cdt, "geoms") else [cdt]
            except Exception:
                _skip("cdt_failed")
                continue
            tri_v_lists = []
            mapping_ok = True
            for part in parts:
                if not isinstance(part, Polygon) or part.is_empty or float(part.area) <= 1e-4:
                    continue
                if not poly.contains(part.representative_point()):
                    continue
                coords = np.asarray(part.exterior.coords[:3], dtype=np.float64)
                if len(coords) < 3:
                    continue
                mapped: list[int] = []
                for q in coords:
                    dists = np.linalg.norm(p2 - q[None, :], axis=1)
                    k_min = int(np.argmin(dists))
                    if float(dists[k_min]) > 0.05:
                        mapping_ok = False
                        break
                    mapped.append(vs[k_min])
                if not mapping_ok or len(set(mapped)) < 3:
                    mapping_ok = False
                    break
                tri_v_lists.append(mapped)
            if not mapping_ok or not tri_v_lists:
                _skip("vertex_remap_failed")
                continue

        uv_sol = _fit_host_uv_affine(after_mesh, aligned_hosts, dom_mat, origin, u_ax, v_ax)
        added_here = 0
        for tri in tri_v_lists:
            key = tuple(sorted(tri))
            if key in existing_tris:
                continue
            tp = after_mesh.positions[tri]
            cr = np.cross(tp[1] - tp[0], tp[2] - tp[0])
            if float(np.linalg.norm(cr)) <= 1e-6:
                continue
            if float(np.dot(cr, n_avg)) < 0.0:
                tri = [tri[0], tri[2], tri[1]]
                tp = after_mesh.positions[tri]

            if uv_sol is not None:
                t_rel = tp - origin
                t_xy = np.column_stack([t_rel @ u_ax, t_rel @ v_ax])
                uv_tri = np.column_stack([t_xy, np.ones(3, dtype=np.float64)]) @ uv_sol
                vt_ids = [next_vt, next_vt + 1, next_vt + 2]
                next_vt += 3
                new_uvs.append(uv_tri)
            else:
                vt_ids = [-1, -1, -1]

            new_fv.append(tri)
            new_fvt.append(vt_ids)
            new_fvn.append([-1, -1, -1])
            new_fmat.append(dom_mat)
            existing_tris.add(key)
            added_here += 1

        if added_here > 0:
            loops_capped += 1

    if not new_fv:
        return after_mesh, {
            "loops_seen": len(loops),
            "loops_capped": 0,
            "tris_added": 0,
            "holes_before": int(before_rep["holeCount"]),
            "holes_after": int(before_rep["holeCount"]),
            "skipped_reasons": skipped,
        }

    out = copy.deepcopy(after_mesh)
    out.face_v = np.vstack([out.face_v, np.asarray(new_fv, dtype=np.int64)])
    out.face_vt = np.vstack([out.face_vt, np.asarray(new_fvt, dtype=np.int64)])
    out.face_vn = np.vstack([out.face_vn, np.asarray(new_fvn, dtype=np.int64)])
    out.face_material = np.concatenate([out.face_material, np.asarray(new_fmat, dtype=np.int64)])
    out.face_line = np.concatenate([out.face_line, np.zeros(len(new_fv), dtype=np.int64)])
    if new_uvs and out.uvs is not None:
        out.uvs = np.vstack([out.uvs, *new_uvs])

    after_rep = detect_new_mesh_holes(before_mesh, out, visible_only=visible_only)
    return out, {
        "loops_seen": len(loops),
        "loops_capped": loops_capped,
        "tris_added": len(new_fv),
        "holes_before": int(before_rep["holeCount"]),
        "holes_after": int(after_rep["holeCount"]),
        "skipped_reasons": skipped,
    }
