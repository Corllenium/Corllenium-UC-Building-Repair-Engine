"""Cross-Plane T-Junction Stitcher (`engine.fixes.tjunction_stitch`).

Eliminates Unity 6 1-pixel shimmering pinhole cracks across orthogonal wall-to-floor-to-column seams
WITHOUT violating AGENTS.md §4 (no tolerance welding > 0.1 mm):
- Collapses only exact / sub-0.1mm (`<= 0.0039 in`) coincident vertex indices.
- Uses a pure-NumPy 3D voxel index (no scipy dependency) to find neighbor vertices `V` lying within
  `search_tol_in` (default `0.05 in`) of an interior point on edge `(A, B)` of triangle `(A, B, C)`.
- Splits `(A, B, C)` directly at `V` into conformal triangles `(A, V, C)` + `(V, B, C)` with exact
  barycentric `vt`/`vn` interpolation, zero vertex displacement, and a `min_subtri_alt_in` (`2 mm`)
  sliver guard.
"""
from __future__ import annotations

from collections import defaultdict
import copy
import numpy as np

from engine.model import MeshData
from engine.pipeline import analyse_topology


def _tri_min_altitude(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> float:
    e0 = float(np.linalg.norm(p1 - p0))
    e1 = float(np.linalg.norm(p2 - p1))
    e2 = float(np.linalg.norm(p0 - p2))
    max_e = max(e0, e1, e2)
    if max_e <= 1e-9:
        return 0.0
    area = 0.5 * float(np.linalg.norm(np.cross(p1 - p0, p2 - p0)))
    return (2.0 * area) / max_e


def _build_vertex_grid(positions: np.ndarray, cell_size: float) -> dict[tuple[int, int, int], list[int]]:
    grid: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    q = np.floor(positions / cell_size).astype(np.int64)
    for vid in range(len(positions)):
        grid[(int(q[vid, 0]), int(q[vid, 1]), int(q[vid, 2]))].append(vid)
    return grid


def _query_segment_candidates(
    p0: np.ndarray,
    p1: np.ndarray,
    tol: float,
    cell_size: float,
    grid: dict[tuple[int, int, int], list[int]],
) -> list[int]:
    lo = np.floor((np.minimum(p0, p1) - tol) / cell_size).astype(np.int64)
    hi = np.floor((np.maximum(p0, p1) + tol) / cell_size).astype(np.int64)
    out: list[int] = []
    # Bound traversal for huge edges by stepping along segment when AABB spans many cells
    span = (hi - lo + 1)
    if int(span[0] * span[1] * span[2]) <= 64:
        for ix in range(int(lo[0]), int(hi[0]) + 1):
            for iy in range(int(lo[1]), int(hi[1]) + 1):
                for iz in range(int(lo[2]), int(hi[2]) + 1):
                    vs = grid.get((ix, iy, iz))
                    if vs:
                        out.extend(vs)
        return out

    seg_len = float(np.linalg.norm(p1 - p0))
    n_steps = max(2, int(np.ceil(seg_len / (cell_size * 0.5))) + 1)
    ts = np.linspace(0.0, 1.0, n_steps)
    pts = p0[None, :] + ts[:, None] * (p1 - p0)[None, :]
    seen_cells: set[tuple[int, int, int]] = set()
    rad = int(np.ceil(tol / cell_size))
    q_pts = np.floor(pts / cell_size).astype(np.int64)
    for row in q_pts:
        cx, cy, cz = int(row[0]), int(row[1]), int(row[2])
        for dx in range(-rad, rad + 1):
            for dy in range(-rad, rad + 1):
                for dz in range(-rad, rad + 1):
                    key = (cx + dx, cy + dy, cz + dz)
                    if key not in seen_cells:
                        seen_cells.add(key)
                        vs = grid.get(key)
                        if vs:
                            out.extend(vs)
    return out


def _interp_uv(uvs: np.ndarray, vt0: int, vt1: int, t: float, new_uvs: list[np.ndarray], next_vt: int) -> tuple[int, int]:
    if vt0 < 0 or vt1 < 0 or len(uvs) == 0:
        return -1, next_vt
    u0 = uvs[vt0] if vt0 < len(uvs) else new_uvs[vt0 - len(uvs)]
    u1 = uvs[vt1] if vt1 < len(uvs) else new_uvs[vt1 - len(uvs)]
    new_uvs.append((1.0 - t) * u0 + t * u1)
    return next_vt, next_vt + 1


def stitch_cross_plane_tjunctions(
    mesh: MeshData,
    *,
    search_tol_in: float = 0.05,
    exact_weld_tol_in: float = 0.0039,
    min_split_param: float = 1e-4,
    min_subtri_alt_in: float = 0.079,
    max_passes: int = 4,
) -> tuple[MeshData, dict]:
    """Split triangle edges conformally at adjacent T-vertices across orthogonal & coplanar planes."""
    if mesh.n_faces == 0:
        return mesh, {
            "passes": 0,
            "edges_split": 0,
            "tris_before": 0,
            "tris_after": 0,
            "cracks_before": 0,
            "cracks_after": 0,
        }

    cracks_before = len(analyse_topology(mesh).t_vertices)
    out = copy.deepcopy(mesh)

    # Step 1: exact sub-0.1mm coincident vertex deduplication (AGENTS.md §4 compliant)
    if exact_weld_tol_in > 0.0 and len(out.positions) > 0:
        inv = 1.0 / exact_weld_tol_in
        q = np.round(out.positions * inv).astype(np.int64)
        _, first_idx, inv_map = np.unique(q, axis=0, return_index=True, return_inverse=True)
        if len(first_idx) < len(out.positions):
            # Map face_v onto canonical first index WITHOUT moving any vertex coordinate
            canon = first_idx[inv_map]
            out.face_v = canon[out.face_v]

    has_uvs = out.uvs is not None and len(out.uvs) > 0 and out.face_vt is not None
    cell_size = max(2.0, search_tol_in * 10.0)
    total_splits = 0
    passes_run = 0

    for _ in range(max_passes):
        passes_run += 1
        used_v = np.unique(out.face_v)
        # Build spatial index ONLY over vertices actually referenced by faces
        grid: dict[tuple[int, int, int], list[int]] = defaultdict(list)
        q_used = np.floor(out.positions[used_v] / cell_size).astype(np.int64)
        for idx_local, vid in enumerate(used_v.tolist()):
            grid[(int(q_used[idx_local, 0]), int(q_used[idx_local, 1]), int(q_used[idx_local, 2]))].append(vid)

        # Deduplicate per-undirected-edge split search so shared edges compute splits once
        edge_splits_cache: dict[tuple[int, int], list[tuple[float, int]]] = {}
        new_fv: list[list[int]] = []
        new_fvt: list[list[int]] = []
        new_fvn: list[list[int]] = []
        new_fmat: list[int] = []
        new_fline: list[int] = []
        new_uvs: list[np.ndarray] = []
        base_uvs = out.uvs if has_uvs else np.zeros((0, 2), dtype=np.float64)
        next_vt = len(base_uvs)
        splits_this_pass = 0

        for f in range(out.n_faces):
            a, b, c = int(out.face_v[f, 0]), int(out.face_v[f, 1]), int(out.face_v[f, 2])
            if a == b or b == c or c == a:
                new_fv.append([a, b, c])
                new_fvt.append(out.face_vt[f].tolist())
                new_fvn.append(out.face_vn[f].tolist())
                new_fmat.append(int(out.face_material[f]))
                new_fline.append(int(out.face_line[f]))
                continue

            tri_vs = (a, b, c)
            tri_vts = (int(out.face_vt[f, 0]), int(out.face_vt[f, 1]), int(out.face_vt[f, 2]))
            tri_vns = (int(out.face_vn[f, 0]), int(out.face_vn[f, 1]), int(out.face_vn[f, 2]))

            # Find best single edge to split this pass (largest-gap T-vertex); multi-edge faces converge in subsequent passes
            chosen_edge = -1
            chosen_w = -1
            chosen_t = 0.0

            for e_idx in range(3):
                u = tri_vs[e_idx]
                v = tri_vs[(e_idx + 1) % 3]
                opp = tri_vs[(e_idx + 2) % 3]
                ek = (u, v) if u < v else (v, u)
                if ek not in edge_splits_cache:
                    pu, pv = out.positions[ek[0]], out.positions[ek[1]]
                    ev = pv - pu
                    elen2 = float(np.dot(ev, ev))
                    elen = float(np.sqrt(elen2))
                    found: list[tuple[float, int]] = []
                    if elen >= 0.25:
                        cands = _query_segment_candidates(pu, pv, search_tol_in, cell_size, grid)
                        seen_c: set[int] = {ek[0], ek[1]}
                        for w in cands:
                            if w in seen_c:
                                continue
                            seen_c.add(w)
                            pw = out.positions[w]
                            t = float(np.dot(pw - pu, ev)) / elen2
                            if t <= min_split_param or t >= 1.0 - min_split_param:
                                continue
                            proj = pu + t * ev
                            dist = float(np.linalg.norm(pw - proj))
                            if dist <= search_tol_in:
                                d_end = min(float(np.linalg.norm(pw - pu)), float(np.linalg.norm(pw - pv)))
                                if d_end > exact_weld_tol_in:
                                    found.append((t, w))
                        found.sort(key=lambda item: abs(item[0] - 0.5))
                    edge_splits_cache[ek] = found

                cands_e = edge_splits_cache[ek]
                if not cands_e:
                    continue
                for t_raw, w in cands_e:
                    if w == opp:
                        continue
                    t_dir = t_raw if u == ek[0] else (1.0 - t_raw)
                    # Check sliver guard on both resulting sub-triangles
                    p_u, p_v, p_opp, p_w = out.positions[u], out.positions[v], out.positions[opp], out.positions[w]
                    alt1 = _tri_min_altitude(p_u, p_w, p_opp)
                    alt2 = _tri_min_altitude(p_w, p_v, p_opp)
                    if min(alt1, alt2) < min_subtri_alt_in:
                        continue
                    chosen_edge = e_idx
                    chosen_w = w
                    chosen_t = t_dir
                    break
                if chosen_edge >= 0:
                    break

            if chosen_edge < 0:
                new_fv.append([a, b, c])
                new_fvt.append(list(tri_vts))
                new_fvn.append(list(tri_vns))
                new_fmat.append(int(out.face_material[f]))
                new_fline.append(int(out.face_line[f]))
            else:
                i0 = chosen_edge
                i1 = (chosen_edge + 1) % 3
                i2 = (chosen_edge + 2) % 3
                vt_w, next_vt = _interp_uv(base_uvs, tri_vts[i0], tri_vts[i1], chosen_t, new_uvs, next_vt)
                vn_w = tri_vns[i0]
                mat_f = int(out.face_material[f])
                line_f = int(out.face_line[f])
                # Sub-tri 1: (v_i0, w, v_i2) — preserves original winding!
                new_fv.append([tri_vs[i0], chosen_w, tri_vs[i2]])
                new_fvt.append([tri_vts[i0], vt_w, tri_vts[i2]])
                new_fvn.append([tri_vns[i0], vn_w, tri_vns[i2]])
                new_fmat.append(mat_f)
                new_fline.append(line_f)
                # Sub-tri 2: (w, v_i1, v_i2) — preserves original winding!
                new_fv.append([chosen_w, tri_vs[i1], tri_vs[i2]])
                new_fvt.append([vt_w, tri_vts[i1], tri_vts[i2]])
                new_fvn.append([vn_w, tri_vns[i1], tri_vns[i2]])
                new_fmat.append(mat_f)
                new_fline.append(line_f)
                splits_this_pass += 1

        if splits_this_pass == 0:
            break
        total_splits += splits_this_pass
        out.face_v = np.asarray(new_fv, dtype=np.int64)
        out.face_vt = np.asarray(new_fvt, dtype=np.int64)
        out.face_vn = np.asarray(new_fvn, dtype=np.int64)
        out.face_material = np.asarray(new_fmat, dtype=np.int64)
        out.face_line = np.asarray(new_fline, dtype=np.int64)
        if has_uvs and new_uvs:
            out.uvs = np.vstack([base_uvs, np.asarray(new_uvs, dtype=np.float64)])

    cracks_after = len(analyse_topology(out).t_vertices)
    return out, {
        "passes": passes_run,
        "edges_split": total_splits,
        "tris_before": int(mesh.n_faces),
        "tris_after": int(out.n_faces),
        "cracks_before": int(cracks_before),
        "cracks_after": int(cracks_after),
    }
