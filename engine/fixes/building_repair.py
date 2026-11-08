"""Universal Building Floor Repair Engine module (`engine.fixes.building_repair`).

Adopts all verified floor/building repair rules directly into the engine:
1. Material deduplication (-TwoSided vs non-TwoSided pointing to the same texture file) & untextured
   `FrontColor` gap-filling wall/floor tile reassignment with projected continuous UVs.
2. Pre-fix and post-merge iterative closing of rectangular wall-cap/corner notches bounded by an open
   cap edge and uncapped perpendicular wall rims.
3. Doorway soffit extraction from `stage_solidify` without ever deleting or shrinking original input
   faces (`replaced_input` preserved 100%, hanging staircase extrusions excluded).
4. Open-room interior/facade wall & cap rescue in `stage_hidden` + exact unrounded plane-cluster
   coplanar overlap deduplication (upward-facing floor/tread surfaces beat downward-facing buried
   wall bottom end-caps; dominant plane material beats minority perpendicular wall end-caps).
5. Single-layer opposite-normal (+n vs -n) coplanar wall tile unification with continuous UV projection,
   followed by `merge_regions` and final exact plane-cluster coplanar overlap removal.
"""
from __future__ import annotations

from collections.abc import Iterable
import copy
from pathlib import Path
import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

from engine.fixes.merge import merge_regions
from engine.fixes.pipeline import FIX_STAGES, FixProfile, finish_fix, start_fix
from engine.fixes.remove import remove_faces
from engine.io.mtl import parse_mtl, texture_flatness
from engine.model import MeshData
from engine.pipeline import analyse_topology, flat_material_indices
from engine.rays.caster import EmbreeCaster
from engine.topo.planes import face_normals, plane_basis
from engine.vis.exposure import BARY, EPS_IN

REPAIR_STAGE_ORDER: tuple[str, ...] = (
    "prepare_materials",
    "cavity_liners",
    "pre_dedup",
    "hidden",
    "flip",
    "solidify",
    "holes",
    "coplanar_overlaps",
    "unify_normals",
    "merge",
    "restore_visible_surfaces",
)


def normalize_enabled_stages(enabled_stages: Iterable[str] | None = None) -> frozenset[str]:
    """Return validated set of enabled repair stage names (defaults to all stages in REPAIR_STAGE_ORDER)."""
    if enabled_stages is None:
        return frozenset(REPAIR_STAGE_ORDER)
    chosen = frozenset(str(s).strip() for s in enabled_stages if str(s).strip())
    unknown = chosen - frozenset(REPAIR_STAGE_ORDER)
    if unknown:
        raise ValueError(
            f"Unknown building repair stage(s): {sorted(unknown)}. Valid stages: {list(REPAIR_STAGE_ORDER)}"
        )
    return chosen


def cluster_coplanar_faces(
    positions: np.ndarray,
    face_v: np.ndarray,
    fn: np.ndarray,
    valid_mask: np.ndarray,
    normal_dot_tol: float = 0.998,
    dist_tol: float = 0.75,
) -> list[tuple[np.ndarray, list[int]]]:
    """Cluster faces into exact geometric planes without rounding-boundary bucket splits."""
    pts = positions[face_v]
    fids = np.flatnonzero(valid_mask & (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) >= 0.5))
    if len(fids) == 0:
        return []

    # Canonicalize unsigned normals so +n and -n point into the same hemisphere
    cn_arr = fn[fids].copy()
    for idx in range(len(fids)):
        n = cn_arr[idx]
        for k in range(3):
            if abs(float(n[k])) > 0.1:
                if float(n[k]) < 0:
                    cn_arr[idx] = -n
                break

    # Seed plane clusters from largest triangles first so cluster normals are never skewed by tiny slivers
    tri_f = pts[fids]
    areas = 0.5 * np.linalg.norm(np.cross(tri_f[:, 1] - tri_f[:, 0], tri_f[:, 2] - tri_f[:, 0]), axis=1)
    order = np.argsort(-areas, kind="stable")
    clusters: list[tuple[np.ndarray, np.ndarray, list[int]]] = []
    buckets: dict[tuple[float, float, float], list[int]] = {}
    for idx in order:
        f = int(fids[idx])
        cn = cn_arr[idx]
        p0 = pts[f].mean(axis=0)
        nb = (round(float(cn[0]), 1), round(float(cn[1]), 1), round(float(cn[2]), 1))
        matched = False
        for dx in (-0.1, 0.0, 0.1):
            for dy in (-0.1, 0.0, 0.1):
                for dz in (-0.1, 0.0, 0.1):
                    key = (round(nb[0] + dx, 1), round(nb[1] + dy, 1), round(nb[2] + dz, 1))
                    for c_idx in buckets.get(key, ()):
                        c_n, c_p0, c_list = clusters[c_idx]
                        if float(np.dot(cn, c_n)) >= normal_dot_tol and abs(float(np.dot(p0 - c_p0, c_n))) <= dist_tol:
                            c_list.append(f)
                            matched = True
                            break
                    if matched:
                        break
                if matched:
                    break
            if matched:
                break
        if not matched:
            new_cid = len(clusters)
            clusters.append((cn, p0, [f]))
            buckets.setdefault(nb, []).append(new_cid)

    return [(c_n, c_list) for c_n, _, c_list in clusters]


def fill_wall_cap_notches(mesh: MeshData) -> tuple[MeshData, int]:
    """Close block-sized right-triangle wall-cap notches bounded by an open cap edge and uncapped wall rims."""
    flat_all = frozenset(range(len(mesh.materials)))
    topo = analyse_topology(mesh, flat_all)
    pw = topo.positions_w
    fw = topo.face_w
    fn = face_normals(pw, fw, topo.ok)
    pts = pw[fw]
    z_mean = pts[:, :, 2].mean(axis=1)
    z_max = pts[:, :, 2].max(axis=1)

    z_floor = float(pts[:, :, 2].min()) + 5.0
    horiz = topo.ok & (np.abs(fn[:, 2]) > 0.95) & (z_mean > z_floor)
    vert = topo.ok & (np.abs(fn[:, 2]) < 0.15) & (z_max > z_floor)

    from collections import defaultdict

    cap_edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for f in np.flatnonzero(horiz):
        a, b, c = int(fw[f, 0]), int(fw[f, 1]), int(fw[f, 2])
        for u, v in ((a, b), (b, c), (c, a)):
            if u != v:
                e = (u, v) if u < v else (v, u)
                cap_edge_faces[e].append(int(f))

    open_cap_edges: dict[tuple[int, int], int] = {
        e: flist[0] for e, flist in cap_edge_faces.items() if len(flist) == 1
    }

    rim_edge_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for f in np.flatnonzero(vert):
        tri_v = fw[f]
        tri_z = pw[tri_v, 2]
        z_top = float(tri_z.max())
        top_vs = [int(tri_v[i]) for i in range(3) if abs(float(tri_z[i]) - z_top) < 0.2]
        if len(top_vs) == 2 and top_vs[0] != top_vs[1]:
            u, v = top_vs[0], top_vs[1]
            e = (u, v) if u < v else (v, u)
            rim_edge_faces[e].append(int(f))

    uncapped_rim_adj: dict[int, set[int]] = defaultdict(set)
    for e in rim_edge_faces:
        if e not in cap_edge_faces:
            u, v = e
            uncapped_rim_adj[u].add(v)
            uncapped_rim_adj[v].add(u)

    w_to_orig: dict[int, int] = {}
    for f in range(mesh.n_faces):
        for k in range(3):
            w_id = int(fw[f, k])
            if w_id not in w_to_orig:
                w_to_orig[w_id] = int(mesh.face_v[f, k])

    new_face_v: list[list[int]] = []
    new_face_vt: list[list[int]] = []
    new_face_vn: list[list[int]] = []
    new_face_mat: list[int] = []
    new_uvs: list[np.ndarray] = []
    next_uv_idx = len(mesh.uvs)
    added_tris_welded: set[tuple[int, ...]] = set()

    for (u, v), nbr_f in open_cap_edges.items():
        len_uv = float(np.linalg.norm(pw[u] - pw[v]))
        if len_uv < 5.0 or len_uv > 120.0:
            continue
        common_ws = (uncapped_rim_adj.get(u, set()) & uncapped_rim_adj.get(v, set())) | (
            uncapped_rim_adj.get(u, set())
            & {w for (a, b) in open_cap_edges for w in (a, b) if (a == v or b == v) and w != v}
        ) | (
            uncapped_rim_adj.get(v, set())
            & {w for (a, b) in open_cap_edges for w in (a, b) if (a == u or b == u) and w != u}
        )
        for w in common_ws:
            if w in (u, v):
                continue
            tri_key = tuple(sorted((u, v, w)))
            if tri_key in added_tris_welded or tri_key in {tuple(sorted(fw[f].tolist())) for f in np.flatnonzero(horiz)}:
                continue
            p_u, p_v, p_w = pw[u], pw[v], pw[w]
            if abs(float(p_w[2] - p_u[2])) > 0.25 or abs(float(p_w[2] - p_v[2])) > 0.25:
                continue
            d_uw = float(np.linalg.norm(p_u - p_w))
            d_vw = float(np.linalg.norm(p_v - p_w))
            if max(d_uw, d_vw) > 90.0 or min(d_uw, d_vw) < 5.0:
                continue
            cross_vec = np.cross(p_v - p_u, p_w - p_u)
            area = 0.5 * float(np.linalg.norm(cross_vec))
            if area < 25.0 or area > 3500.0:
                continue

            nbr_v = fw[nbr_f].tolist()
            orient_w = [u, v, w]
            for i in range(3):
                a, b = nbr_v[i], nbr_v[(i + 1) % 3]
                if (a == u and b == v) or (a == v and b == u):
                    orient_w = [b, a, w]
                    break
            c_new = np.cross(pw[orient_w[1]] - pw[orient_w[0]], pw[orient_w[2]] - pw[orient_w[0]])
            if float(c_new[2]) * float(fn[nbr_f, 2]) < 0:
                orient_w = [orient_w[1], orient_w[0], orient_w[2]]

            orig_v = [w_to_orig[x] for x in orient_w]
            mat_id = int(mesh.face_material[nbr_f])
            nbr_vt_ids = mesh.face_vt[nbr_f]
            if (nbr_vt_ids >= 0).all() and len(mesh.uvs) > 0:
                p_nbr = mesh.positions[mesh.face_v[nbr_f]]
                uv_nbr = mesh.uvs[nbr_vt_ids]
                b1, b2 = plane_basis(fn[nbr_f])
                xy_nbr = np.stack([(p_nbr - p_nbr[0]) @ b1, (p_nbr - p_nbr[0]) @ b2], axis=-1)
                A = np.column_stack([xy_nbr, np.ones(3)])
                try:
                    sol, _, _, _ = np.linalg.lstsq(A, uv_nbr, rcond=None)
                    tri_pos = pw[orient_w]
                    xy_new = np.stack([(tri_pos - p_nbr[0]) @ b1, (tri_pos - p_nbr[0]) @ b2], axis=-1)
                    uv_new = np.column_stack([xy_new, np.ones(3)]) @ sol
                    vt_new = [next_uv_idx, next_uv_idx + 1, next_uv_idx + 2]
                    next_uv_idx += 3
                    new_uvs.append(uv_new)
                except Exception:
                    vt_new = [int(nbr_vt_ids[0]), int(nbr_vt_ids[1]), int(nbr_vt_ids[2])]
            else:
                vt_new = [-1, -1, -1]

            vn_id = int(mesh.face_vn[nbr_f, 0]) if len(mesh.face_vn) else -1
            new_face_v.append(orig_v)
            new_face_vt.append(vt_new)
            new_face_vn.append([vn_id, vn_id, vn_id])
            new_face_mat.append(mat_id)
            added_tris_welded.add(tri_key)

    if not new_face_v:
        return mesh, 0

    out = copy.deepcopy(mesh)
    out.face_v = np.vstack([mesh.face_v, np.asarray(new_face_v, dtype=np.int64)])
    out.face_vt = np.vstack([mesh.face_vt, np.asarray(new_face_vt, dtype=np.int64)])
    out.face_vn = np.vstack([mesh.face_vn, np.asarray(new_face_vn, dtype=np.int64)])
    out.face_material = np.concatenate([mesh.face_material, np.asarray(new_face_mat, dtype=np.int64)])
    out.face_line = np.concatenate([mesh.face_line, np.zeros(len(new_face_v), dtype=np.int64)])
    if new_uvs:
        out.uvs = np.vstack([mesh.uvs, *new_uvs])
    return out, len(new_face_v)


def prepare_building_materials(mesh: MeshData, mtl_dict: dict) -> MeshData:
    """Deduplicate identical-texture materials and reassign untextured FrontColor gap-filling wall tiles."""
    out = copy.deepcopy(mesh)
    tex_to_canon_mat: dict[str, int] = {}
    mat_remap = np.arange(len(out.materials), dtype=np.int64)
    untextured_mats: set[int] = set()
    for i, mname in enumerate(out.materials):
        mat_obj = mtl_dict.get(mname)
        if mat_obj and mat_obj.map_kd:
            tex_file = mat_obj.map_kd.split()[-1]
            if tex_file in tex_to_canon_mat:
                mat_remap[i] = tex_to_canon_mat[tex_file]
            else:
                tex_to_canon_mat[tex_file] = i
        else:
            untextured_mats.add(i)

    out.face_material = mat_remap[out.face_material]
    if not untextured_mats:
        return out

    pts = out.positions[out.face_v]
    fn = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
    clusters = cluster_coplanar_faces(out.positions, out.face_v, fn, np.ones(out.n_faces, dtype=bool))

    drop_untex = np.zeros(out.n_faces, dtype=bool)
    new_uvs: list[np.ndarray] = []
    next_uv_idx = len(out.uvs)

    for cn, fids in clusters:
        untex_fids = [f for f in fids if int(out.face_material[f]) in untextured_mats]
        tex_fids = [f for f in fids if int(out.face_material[f]) not in untextured_mats]
        if not untex_fids:
            continue
        if not tex_fids:
            continue

        u_ax, v_ax = plane_basis(cn)
        tex_polys = []
        mat_to_fids: dict[int, list[int]] = {}
        for tf in tex_fids:
            p2 = np.stack([pts[tf] @ u_ax, pts[tf] @ v_ax], axis=-1)
            poly = Polygon(p2)
            if poly.is_valid and poly.area > 0.1:
                m_id = int(out.face_material[tf])
                tex_polys.append((tf, m_id, poly))
                mat_to_fids.setdefault(m_id, []).append(tf)

        if not tex_polys:
            continue

        tex_union = unary_union([p for _, _, p in tex_polys])
        untex_keep_polys = []
        for uf in untex_fids:
            uf_p2 = np.stack([pts[uf] @ u_ax, pts[uf] @ v_ax], axis=-1)
            uf_poly = Polygon(uf_p2)
            if not uf_poly.is_valid or uf_poly.area <= 0.1:
                drop_untex[uf] = True
                continue
            if float(uf_poly.intersection(tex_union).area) > 0.25 * float(uf_poly.area):
                drop_untex[uf] = True
            else:
                untex_keep_polys.append((uf, uf_p2, uf_poly))

        if untex_keep_polys:
            patch_union = unary_union([p for _, _, p in untex_keep_polys]).buffer(0.5)
            shared_by_mat: dict[int, float] = {}
            for _, m_id, tp in tex_polys:
                if tp.intersects(patch_union):
                    shared_by_mat[m_id] = shared_by_mat.get(m_id, 0.0) + float(tp.boundary.intersection(patch_union).length)
            dom_mat = max(shared_by_mat, key=lambda m: shared_by_mat[m]) if shared_by_mat else max(mat_to_fids, key=lambda m: len(mat_to_fids[m]))
            ref_fids = mat_to_fids[dom_mat]
            xy_list, uv_list = [], []
            for rf in ref_fids:
                vt_ids = out.face_vt[rf]
                if (vt_ids >= 0).all() and len(out.uvs) > 0:
                    rf_p2 = np.stack([pts[rf] @ u_ax, pts[rf] @ v_ax], axis=-1)
                    xy_list.append(rf_p2)
                    uv_list.append(out.uvs[vt_ids])
            sol = None
            if xy_list:
                X = np.vstack(xy_list)
                U = np.vstack(uv_list)
                A = np.column_stack([X, np.ones(len(X))])
                try:
                    sol, _, _, _ = np.linalg.lstsq(A, U, rcond=None)
                except Exception:
                    sol = None
            dom_signs = [1 if float(np.dot(fn[rf], cn)) >= 0 else -1 for rf in ref_fids]
            dom_sign = 1 if sum(dom_signs) >= 0 else -1
            for uf, uf_p2, _ in untex_keep_polys:
                out.face_material[uf] = dom_mat
                uf_sign = 1 if float(np.dot(fn[uf], cn)) >= 0 else -1
                if uf_sign != dom_sign:
                    out.face_v[uf] = out.face_v[uf, [1, 0, 2]]
                    uf_p2 = uf_p2[[1, 0, 2]]
                if sol is not None:
                    uv_new = np.column_stack([uf_p2, np.ones(3)]) @ sol
                    out.face_vt[uf] = [next_uv_idx, next_uv_idx + 1, next_uv_idx + 2]
                    next_uv_idx += 3
                    new_uvs.append(uv_new)

    if new_uvs:
        out.uvs = np.vstack([out.uvs, *new_uvs])
    if drop_untex.any():
        out, _ = remove_faces(out, drop_untex)
    return out


def unify_single_layer_coplanar_normals(mesh: MeshData) -> MeshData:
    """Unify single-layer coplanar same-material normals (+n vs -n) where minority-normal tiles do not overlap majority-normal tiles."""
    out = copy.deepcopy(mesh)
    pts = out.positions[out.face_v]
    fn = face_normals(out.positions, out.face_v, np.ones(out.n_faces, dtype=bool))
    clusters = cluster_coplanar_faces(out.positions, out.face_v, fn, np.ones(out.n_faces, dtype=bool))

    new_uvs: list[np.ndarray] = []
    next_uv_idx = len(out.uvs)

    for cn, fids in clusters:
        by_mat: dict[int, list[int]] = {}
        for f in fids:
            by_mat.setdefault(int(out.face_material[f]), []).append(f)
        u_ax, v_ax = plane_basis(cn)
        for mat_id, mfids in by_mat.items():
            pos_f = [f for f in mfids if float(np.dot(fn[f], cn)) >= 0]
            neg_f = [f for f in mfids if float(np.dot(fn[f], cn)) < 0]
            if not pos_f or not neg_f:
                continue
            pos_polys = [Polygon(np.stack([pts[f] @ u_ax, pts[f] @ v_ax], axis=-1)) for f in pos_f]
            neg_polys = [Polygon(np.stack([pts[f] @ u_ax, pts[f] @ v_ax], axis=-1)) for f in neg_f]
            pos_u = unary_union([p for p in pos_polys if p.is_valid and p.area > 0.1])
            neg_u = unary_union([p for p in neg_polys if p.is_valid and p.area > 0.1])
            if pos_u.is_empty or neg_u.is_empty:
                continue
            maj_fids, min_fids, maj_u = (pos_f, neg_f, pos_u) if pos_u.area >= neg_u.area else (neg_f, pos_f, neg_u)
            xy_l, uv_l = [], []
            for rf in maj_fids:
                vt_ids = out.face_vt[rf]
                if (vt_ids >= 0).all() and len(out.uvs) > 0:
                    rf_p2 = np.stack([pts[rf] @ u_ax, pts[rf] @ v_ax], axis=-1)
                    if rf_p2.shape == (3, 2) and np.linalg.matrix_rank(rf_p2[1:] - rf_p2[0]) == 2:
                        xy_l.append(rf_p2)
                        uv_l.append(out.uvs[vt_ids])
                        break
            sol = None
            if xy_l:
                A = np.column_stack([xy_l[0], np.ones(3)])
                try:
                    sol = np.linalg.solve(A, uv_l[0])
                except Exception:
                    sol = None
            for mf in min_fids:
                mp2 = np.stack([pts[mf] @ u_ax, pts[mf] @ v_ax], axis=-1)
                mpoly = Polygon(mp2)
                if not mpoly.is_valid or mpoly.area <= 0.1:
                    continue
                if float(mpoly.intersection(maj_u).area) < 0.15 * float(mpoly.area):
                    out.face_v[mf] = out.face_v[mf, [1, 0, 2]]
                    out.face_vn[mf] = out.face_vn[mf, [1, 0, 2]]
                    mp2_flipped = mp2[[1, 0, 2]]
                    if sol is not None:
                        uv_new = np.column_stack([mp2_flipped, np.ones(3)]) @ sol
                        out.face_vt[mf] = [next_uv_idx, next_uv_idx + 1, next_uv_idx + 2]
                        next_uv_idx += 3
                        new_uvs.append(uv_new)
                    else:
                        out.face_vt[mf] = out.face_vt[mf, [1, 0, 2]]

    if new_uvs:
        out.uvs = np.vstack([out.uvs, *new_uvs])
    return out


def _triangulate_clipped_face(
    pts_f: np.ndarray,
    p2_f: np.ndarray,
    orig_fv: np.ndarray,
    orig_fvt: np.ndarray,
    uvs_f: np.ndarray | None,
    f_normal: np.ndarray,
    f_mat: int,
    rem_geom,
    next_v_idx: int,
    next_vt_idx: int,
) -> tuple[list[np.ndarray], list[np.ndarray], list[list[int]], list[list[int]], list[int], int, int]:
    """Triangulate a 2D clipped polygon `rem_geom` inside triangle `pts_f` with exact barycentric 3D/UV interpolation."""
    new_pos: list[np.ndarray] = []
    new_uv: list[np.ndarray] = []
    new_fv: list[list[int]] = []
    new_fvt: list[list[int]] = []
    new_fmat: list[int] = []

    try:
        simp_geom = rem_geom.simplify(0.02, preserve_topology=True).buffer(0)
        if not simp_geom.is_empty and float(simp_geom.area) >= 15.0:
            rem_geom = simp_geom
        cdt = shapely.constrained_delaunay_triangles(rem_geom)
        parts = list(cdt.geoms) if hasattr(cdt, "geoms") else [cdt]
        valid_parts = [p for p in parts if isinstance(p, Polygon) and p.is_valid and float(p.area) >= 2.0]
        if not valid_parts:
            return new_pos, new_uv, new_fv, new_fvt, new_fmat, next_v_idx, next_vt_idx
    except Exception:
        return new_pos, new_uv, new_fv, new_fvt, new_fmat, next_v_idx, next_vt_idx

    q0, q1, q2 = p2_f
    v0_2d = q1 - q0
    v1_2d = q2 - q0
    det = float(v0_2d[0] * v1_2d[1] - v0_2d[1] * v1_2d[0])
    if abs(det) < 1e-6:
        return new_pos, new_uv, new_fv, new_fvt, new_fmat, next_v_idx, next_vt_idx

    P0, P1, P2 = pts_f
    has_uvs = uvs_f is not None
    if has_uvs:
        UV0, UV1, UV2 = uvs_f
    else:
        UV0 = UV1 = UV2 = np.zeros(2, dtype=np.float64)

    vert_cache: dict[tuple[float, float], tuple[int, int, np.ndarray]] = {}
    for part in valid_parts:
        tri_xy = np.asarray(part.exterior.coords[:3], dtype=np.float64)
        if len(tri_xy) < 3:
            continue
        tri_v: list[int] = []
        tri_vt: list[int] = []
        tri_p3d: list[np.ndarray] = []
        for qx, qy in tri_xy:
            q_pt = np.array([qx, qy], dtype=np.float64)
            d_orig = np.linalg.norm(p2_f - q_pt[None, :], axis=1)
            k_min = int(np.argmin(d_orig))
            if float(d_orig[k_min]) <= 0.05 and int(orig_fv[k_min]) >= 0:
                vi = int(orig_fv[k_min])
                vti = int(orig_fvt[k_min])
                p3d = pts_f[k_min]
            else:
                key = (round(float(qx), 3), round(float(qy), 3))
                if key in vert_cache:
                    vi, vti, p3d = vert_cache[key]
                else:
                    v2_2d = q_pt - q0
                    l1 = float(v2_2d[0] * v1_2d[1] - v2_2d[1] * v1_2d[0]) / det
                    l2 = float(v0_2d[0] * v2_2d[1] - v0_2d[1] * v2_2d[0]) / det
                    l0 = 1.0 - l1 - l2
                    p3d = np.round(l0 * P0 + l1 * P1 + l2 * P2, 2)
                    vi = next_v_idx
                    next_v_idx += 1
                    new_pos.append(p3d)
                    if has_uvs:
                        uv2d = l0 * UV0 + l1 * UV1 + l2 * UV2
                        vti = next_vt_idx
                        next_vt_idx += 1
                        new_uv.append(uv2d)
                    else:
                        vti = -1
                    vert_cache[key] = (vi, vti, p3d)
            tri_v.append(vi)
            tri_vt.append(vti)
            tri_p3d.append(p3d)

        if len({tri_v[0], tri_v[1], tri_v[2]}) < 3:
            continue
        cr = np.cross(tri_p3d[1] - tri_p3d[0], tri_p3d[2] - tri_p3d[0])
        if float(np.linalg.norm(cr)) < 1e-3:
            continue
        if float(np.dot(cr, f_normal)) < 0.0:
            tri_v = [tri_v[0], tri_v[2], tri_v[1]]
            tri_vt = [tri_vt[0], tri_vt[2], tri_vt[1]]
        new_fv.append(tri_v)
        new_fvt.append(tri_vt)
        new_fmat.append(f_mat)

    return new_pos, new_uv, new_fv, new_fvt, new_fmat, next_v_idx, next_vt_idx


def remove_coplanar_overlaps(
    mesh: MeshData,
    overlap_ratio: float = 0.20,
    drop_only: bool = False,
    dist_tol: float = 0.03,
) -> tuple[MeshData, int]:
    """Remove coplanar overlapping duplicate/end-cap triangles and optionally clip partial overlaps.

    Uses strict true-plane `dist_tol=0.03` inches and signed-normal separation when `drop_only=True`
    so thin object parts (railings, balusters, planter bases, window frames) never have parallel faces
    collapsed across a gap or partially-covered corner triangles dropped.
    """
    pts = mesh.positions[mesh.face_v]
    fn = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    clusters = cluster_coplanar_faces(
        mesh.positions,
        mesh.face_v,
        fn,
        np.ones(mesh.n_faces, dtype=bool),
        normal_dot_tol=0.999,
        dist_tol=dist_tol if drop_only else 0.75,
    )

    drop_mask = np.zeros(mesh.n_faces, dtype=bool)
    new_pos_list: list[np.ndarray] = []
    new_uv_list: list[np.ndarray] = []
    new_fv_list: list[list[int]] = []
    new_fvt_list: list[list[int]] = []
    new_fmat_list: list[int] = []
    has_uvs = mesh.uvs is not None and len(mesh.uvs) > 0 and mesh.face_vt is not None
    next_v_idx = len(mesh.positions)
    next_vt_idx = len(mesh.uvs) if has_uvs else 0

    for cn, fids in clusters:
        if len(fids) < 2:
            continue
        u_ax, v_ax = plane_basis(cn)
        # When drop_only=True, separate +cn and -cn so opposite-normal faces never drop each other
        if drop_only:
            sub_groups = [
                [f for f in fids if float(np.dot(fn[f], cn)) >= 0.0],
                [f for f in fids if float(np.dot(fn[f], cn)) < 0.0],
            ]
        else:
            sub_groups = [fids]

        for g_fids in sub_groups:
            if len(g_fids) < 2:
                continue
            mat_area: dict[int, float] = {}
            poly_p: dict[int, Polygon] = {}
            p2_map: dict[int, np.ndarray] = {}
            for f in g_fids:
                p2 = np.stack([pts[f] @ u_ax, pts[f] @ v_ax], axis=-1)
                poly = Polygon(p2)
                if poly.is_valid and poly.area > 1e-4:
                    poly_p[f] = poly
                    p2_map[f] = p2
                    m_id = int(mesh.face_material[f])
                    mat_area[m_id] = mat_area.get(m_id, 0.0) + float(poly.area)
            is_hs = abs(float(cn[2])) > 0.5
            fids_sorted = sorted(
                [f for f in g_fids if f in poly_p],
                key=lambda f: (
                    (1 if float(fn[f, 2]) > 0.0 else 0) if is_hs else 1,
                    round(mat_area.get(int(mesh.face_material[f]), 0.0), 1),
                    float(poly_p[f].area),
                ),
                reverse=True,
            )
            cov_u = Polygon()
            for f in fids_sorted:
                pl = poly_p[f]
                area_f = float(pl.area)
                ovl = float(pl.intersection(cov_u).area) if not cov_u.is_empty else 0.0
                if drop_only:
                    # Strictly drop ONLY if >= 99.5% of the triangle is covered AND uncovered area <= 0.02 sq in
                    rem_area = area_f - ovl
                    if ovl >= 0.995 * area_f and rem_area <= 0.02:
                        drop_mask[f] = True
                        continue
                    cov_u = cov_u.union(pl) if not cov_u.is_empty else pl
                    continue
                if ovl > overlap_ratio * area_f or ovl > 5.0:
                    rem_area = area_f - ovl
                    if rem_area < 20.0 or ovl >= 0.88 * area_f:
                        drop_mask[f] = True
                        continue
                    rem_geom = pl.difference(cov_u).buffer(0)
                    if rem_geom.is_empty or float(rem_geom.area) < 20.0:
                        drop_mask[f] = True
                        continue
                    orig_fvt = mesh.face_vt[f] if has_uvs else np.array([-1, -1, -1], dtype=np.int64)
                    uvs_f = mesh.uvs[orig_fvt] if (has_uvs and (orig_fvt >= 0).all()) else None
                    npos, nuv, nfv, nfvt, nfmat, next_v_idx, next_vt_idx = _triangulate_clipped_face(
                        pts[f], p2_map[f], mesh.face_v[f], orig_fvt, uvs_f, fn[f], int(mesh.face_material[f]),
                        rem_geom, next_v_idx, next_vt_idx,
                    )
                    if nfv:
                        drop_mask[f] = True
                        new_pos_list.extend(npos)
                        new_uv_list.extend(nuv)
                        new_fv_list.extend(nfv)
                        new_fvt_list.extend(nfvt)
                        new_fmat_list.extend(nfmat)
                        cov_u = cov_u.union(pl) if not cov_u.is_empty else pl
                    continue

                cov_u = cov_u.union(pl) if not cov_u.is_empty else pl

    if not drop_mask.any() and not new_fv_list:
        return mesh, 0
    out, _ = remove_faces(mesh, drop_mask)
    if new_fv_list:
        if new_pos_list:
            out.positions = np.vstack([out.positions, np.asarray(new_pos_list, dtype=np.float64)])
        if has_uvs and new_uv_list:
            out.uvs = np.vstack([out.uvs, np.asarray(new_uv_list, dtype=np.float64)])
        out.face_v = np.vstack([out.face_v, np.asarray(new_fv_list, dtype=np.int64)])
        if out.face_vt is not None:
            out.face_vt = np.vstack([out.face_vt, np.asarray(new_fvt_list, dtype=np.int64)])
        if out.face_vn is not None:
            out.face_vn = np.vstack([out.face_vn, np.full((len(new_fv_list), 3), -1, dtype=np.int64)])
        out.face_material = np.concatenate([out.face_material, np.asarray(new_fmat_list, dtype=np.int64)])
        out.face_line = np.concatenate([out.face_line, np.zeros(len(new_fv_list), dtype=np.int64)])
    return out, int(drop_mask.sum())


def restore_missing_visible_wall_faces(
    ref_mesh: MeshData,
    repaired_mesh: MeshData,
    visible_wall_mask: np.ndarray,
    min_missing_area: float = 35.0,
) -> tuple[MeshData, int]:
    """Restore any visible vertical wall region from `ref_mesh` that is uncovered in `repaired_mesh`."""
    pts_b = ref_mesh.positions[ref_mesh.face_v]
    fn_b = face_normals(ref_mesh.positions, ref_mesh.face_v, np.ones(ref_mesh.n_faces, dtype=bool))
    pts_a = repaired_mesh.positions[repaired_mesh.face_v]
    fn_a = face_normals(repaired_mesh.positions, repaired_mesh.face_v, np.ones(repaired_mesh.n_faces, dtype=bool))

    all_pos = np.vstack([ref_mesh.positions, repaired_mesh.positions])
    all_fv = np.vstack([ref_mesh.face_v, repaired_mesh.face_v + len(ref_mesh.positions)])
    all_fn = np.vstack([fn_b, fn_a])
    valid_all = np.concatenate([visible_wall_mask, np.ones(repaired_mesh.n_faces, dtype=bool)])
    clusters = cluster_coplanar_faces(all_pos, all_fv, all_fn, valid_all)

    has_uvs = (
        repaired_mesh.uvs is not None
        and len(repaired_mesh.uvs) > 0
        and repaired_mesh.face_vt is not None
        and ref_mesh.uvs is not None
        and len(ref_mesh.uvs) > 0
        and ref_mesh.face_vt is not None
    )
    next_v_idx = len(repaired_mesh.positions)
    next_vt_idx = len(repaired_mesh.uvs) if has_uvs else 0
    new_pos_list: list[np.ndarray] = []
    new_uv_list: list[np.ndarray] = []
    new_fv_list: list[list[int]] = []
    new_fvt_list: list[list[int]] = []
    new_fmat_list: list[int] = []
    n_restored = 0

    for cn, fids in clusters:
        is_horiz = abs(float(cn[2])) > 0.5
        bfids = [f for f in fids if f < ref_mesh.n_faces and visible_wall_mask[f]]
        afids = [f - ref_mesh.n_faces for f in fids if f >= ref_mesh.n_faces]
        if not bfids:
            continue
        u_ax, v_ax = plane_basis(cn)
        a_polys: list[Polygon] = []
        pos_area = 0.0
        neg_area = 0.0
        for af in afids:
            p = Polygon(np.stack([pts_a[af] @ u_ax, pts_a[af] @ v_ax], axis=-1))
            if p.is_valid and p.area > 0.5:
                a_polys.append(p)
                if float(np.dot(fn_a[af], cn)) >= 0.0:
                    pos_area += float(p.area)
                else:
                    neg_area += float(p.area)
        a_u = unary_union(a_polys) if a_polys else Polygon()
        if is_horiz:
            dom_normal = cn if float(cn[2]) > 0.0 else -cn
        else:
            dom_normal = cn if pos_area >= neg_area else -cn

        for bf in bfids:
            p2 = np.stack([pts_b[bf] @ u_ax, pts_b[bf] @ v_ax], axis=-1)
            pl = Polygon(p2)
            if not pl.is_valid or float(pl.area) < min_missing_area:
                continue
            rem_geom = pl.difference(a_u).buffer(0) if not a_u.is_empty else pl
            if rem_geom.is_empty or float(rem_geom.area) < min_missing_area or float(rem_geom.area) < 0.25 * float(pl.area):
                continue
            orig_fvt = ref_mesh.face_vt[bf] if has_uvs else np.array([-1, -1, -1], dtype=np.int64)
            uvs_f = ref_mesh.uvs[orig_fvt] if (has_uvs and (orig_fvt >= 0).all()) else None
            target_n = dom_normal if len(afids) > 0 else fn_b[bf]
            npos, nuv, nfv, nfvt, nfmat, next_v_idx, next_vt_idx = _triangulate_clipped_face(
                pts_b[bf],
                p2,
                np.array([-1, -1, -1], dtype=np.int64),
                np.array([-1, -1, -1], dtype=np.int64),
                uvs_f,
                target_n,
                int(ref_mesh.face_material[bf]),
                rem_geom,
                next_v_idx,
                next_vt_idx,
            )
            if nfv:
                new_pos_list.extend(npos)
                new_uv_list.extend(nuv)
                new_fv_list.extend(nfv)
                new_fvt_list.extend(nfvt)
                new_fmat_list.extend(nfmat)
                a_u = a_u.union(rem_geom) if not a_u.is_empty else rem_geom
                n_restored += 1

    if not new_fv_list:
        return repaired_mesh, 0
    out = copy.deepcopy(repaired_mesh)
    if new_pos_list:
        out.positions = np.vstack([out.positions, np.asarray(new_pos_list, dtype=np.float64)])
    if has_uvs and new_uv_list:
        out.uvs = np.vstack([out.uvs, np.asarray(new_uv_list, dtype=np.float64)])
    out.face_v = np.vstack([out.face_v, np.asarray(new_fv_list, dtype=np.int64)])
    if out.face_vt is not None:
        out.face_vt = np.vstack([out.face_vt, np.asarray(new_fvt_list, dtype=np.int64)])
    if out.face_vn is not None:
        out.face_vn = np.vstack([out.face_vn, np.full((len(new_fv_list), 3), -1, dtype=np.int64)])
    out.face_material = np.concatenate([out.face_material, np.asarray(new_fmat_list, dtype=np.int64)])
    out.face_line = np.concatenate([out.face_line, np.zeros(len(new_fv_list), dtype=np.int64)])
    return out, n_restored


def compact_mesh(mesh: MeshData, rings: dict | None = None) -> tuple[MeshData, dict]:
    """Strip unreferenced vertices, UVs, and normals from mesh and remap rings."""
    out = copy.deepcopy(mesh)
    rings_out = copy.deepcopy(rings) if rings else {}

    used_v = set(np.unique(out.face_v[out.face_v >= 0]).tolist())
    for r in rings_out.values():
        if r is not None:
            used_v.update(int(x) for x in r.get("outer", ()))
            for inn in r.get("inners", ()):
                used_v.update(int(x) for x in inn)
    if used_v:
        sorted_v = np.array(sorted(used_v), dtype=np.int64)
        v_map = np.full(len(out.positions), -1, dtype=np.int64)
        v_map[sorted_v] = np.arange(len(sorted_v), dtype=np.int64)
        out.positions = out.positions[sorted_v]
        out.face_v = v_map[out.face_v]
        seen_ring_ids: set[int] = set()
        for r in rings_out.values():
            if r is not None and id(r) not in seen_ring_ids:
                seen_ring_ids.add(id(r))
                r["outer"] = [int(v_map[int(x)]) for x in r.get("outer", ())]
                r["inners"] = [[int(v_map[int(x)]) for x in inn] for inn in r.get("inners", ())]

    if out.uvs is not None and len(out.uvs) > 0 and out.face_vt is not None:
        valid_vt = out.face_vt[out.face_vt >= 0]
        if len(valid_vt) > 0:
            sorted_vt = np.unique(valid_vt)
            vt_map = np.full(len(out.uvs), -1, dtype=np.int64)
            vt_map[sorted_vt] = np.arange(len(sorted_vt), dtype=np.int64)
            out.uvs = out.uvs[sorted_vt]
            mask_vt = out.face_vt >= 0
            out.face_vt = np.where(mask_vt, vt_map[np.maximum(out.face_vt, 0)], -1)
        else:
            out.uvs = np.zeros((0, 2), dtype=np.float64)

    if out.normals is not None and len(out.normals) > 0 and out.face_vn is not None:
        valid_vn = out.face_vn[out.face_vn >= 0]
        if len(valid_vn) > 0:
            sorted_vn = np.unique(valid_vn)
            vn_map = np.full(len(out.normals), -1, dtype=np.int64)
            vn_map[sorted_vn] = np.arange(len(sorted_vn), dtype=np.int64)
            out.normals = out.normals[sorted_vn]
            mask_vn = out.face_vn >= 0
            out.face_vn = np.where(mask_vn, vn_map[np.maximum(out.face_vn, 0)], -1)
        else:
            out.normals = np.zeros((0, 3), dtype=np.float64)

    return out, rings_out


def remove_cavity_liner_backfaces(mesh: MeshData) -> tuple[MeshData, int]:
    """Drop inward-facing cavity-liner backfaces that are covered by outward-facing faces on the same plane."""
    pts = mesh.positions[mesh.face_v]
    fn = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    ok = (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) > 0.5)
    if not ok.any():
        return mesh, 0
    caster = EmbreeCaster(mesh.positions, mesh.face_v[ok])
    pts_f = np.einsum("sb,fbk->fsk", BARY, pts) + 1.0 * fn[:, None, :]
    dirs_f = np.repeat(fn[:, None, :], len(BARY), axis=1).reshape(-1, 3)
    _, t_f = caster.first_hit(pts_f.reshape(-1, 3), dirs_f)
    tf_med = np.median(t_f.reshape(mesh.n_faces, len(BARY)), axis=1)

    clusters = cluster_coplanar_faces(mesh.positions, mesh.face_v, fn, ok)
    drop_liner = np.zeros(mesh.n_faces, dtype=bool)
    for cn, fids in clusters:
        if len(fids) < 2:
            continue
        u_ax, v_ax = plane_basis(cn)
        pos_f = [f for f in fids if float(np.dot(fn[f], cn)) >= 0]
        neg_f = [f for f in fids if float(np.dot(fn[f], cn)) < 0]
        if not pos_f or not neg_f:
            continue
        pos_polys = {f: Polygon(np.stack([pts[f] @ u_ax, pts[f] @ v_ax], axis=-1)) for f in pos_f}
        neg_polys = {f: Polygon(np.stack([pts[f] @ u_ax, pts[f] @ v_ax], axis=-1)) for f in neg_f}
        pos_u = unary_union([p for p in pos_polys.values() if p.is_valid and p.area > 0.1])
        neg_u = unary_union([p for p in neg_polys.values() if p.is_valid and p.area > 0.1])
        if pos_u.is_empty or neg_u.is_empty:
            continue
        for nf, npoly in neg_polys.items():
            if npoly.is_valid and npoly.area > 0.1 and float(tf_med[nf]) < 22.0:
                if float(npoly.intersection(pos_u).area) >= 0.80 * float(npoly.area):
                    drop_liner[nf] = True
        for pf, ppoly in pos_polys.items():
            if ppoly.is_valid and ppoly.area > 0.1 and float(tf_med[pf]) < 22.0 and not drop_liner[pf]:
                if float(ppoly.intersection(neg_u).area) >= 0.80 * float(ppoly.area):
                    drop_liner[pf] = True

    if not drop_liner.any():
        return mesh, 0
    out, _ = remove_faces(mesh, drop_liner)
    return out, int(drop_liner.sum())


def repair_building_floor_mesh(
    in_mesh_ckpt: MeshData,
    mtl_path: Path,
    enabled_stages: Iterable[str] | None = None,
) -> tuple[MeshData, dict | list, dict]:
    """Run the universal building/floor repair pipeline on a CKPT17-coordinate MeshData.

    Supports stage-selectable execution (`enabled_stages`) for targeted loopback re-runs when
    reviewing models in Blender Staging or the Siege Dashboard.
    """
    active_stages = normalize_enabled_stages(enabled_stages)
    mtl_dict = parse_mtl(mtl_path)
    if "prepare_materials" in active_stages:
        mesh_prep = prepare_building_materials(in_mesh_ckpt, mtl_dict)
    else:
        mesh_prep = copy.deepcopy(in_mesh_ckpt)
    mesh_orig_vis = copy.deepcopy(mesh_prep)

    flatness: dict[str, float] = {}
    for name, mat in mtl_dict.items():
        if mat.map_kd:
            tp = (mtl_path.parent / mat.map_kd.split()[-1]).resolve()
            if tp.is_file():
                flatness[name] = min(texture_flatness(tp), 6.0)

    if "cavity_liners" in active_stages:
        mesh_prep, n_liners_dropped = remove_cavity_liner_backfaces(mesh_prep)
    else:
        n_liners_dropped = 0

    if "pre_dedup" in active_stages:
        mesh_prep, n_pre_ovl_dropped = remove_coplanar_overlaps(mesh_prep, overlap_ratio=0.10, drop_only=True)
    else:
        n_pre_ovl_dropped = 0

    if "holes" in active_stages:
        in_mesh_filled, n_notches_before = fill_wall_cap_notches(mesh_prep)
    else:
        in_mesh_filled, n_notches_before = copy.deepcopy(mesh_prep), 0

    z_floor = float(in_mesh_filled.positions[:, 2].min())
    z_ceil = float(in_mesh_filled.positions[:, 2].max())
    soffit_fids: list[int] = []
    if "solidify" in active_stages:
        sol_tmp = dict(FIX_STAGES)["solidify"](
            start_fix(copy.deepcopy(in_mesh_filled), flatness, FixProfile(guard_size=(128, 128)))
        )
        sol_new_mask = np.asarray(sol_tmp.solidify_result.new_faces, dtype=bool)
        n_appended_sol = int(sol_new_mask.sum())
        sol_m = sol_tmp.mesh
        sol_pts = sol_m.positions[sol_m.face_v]
        sol_fn = face_normals(sol_m.positions, sol_m.face_v, np.ones(sol_m.n_faces, dtype=bool))
        soffit_fids = [
            f for f in range(sol_m.n_faces - n_appended_sol, sol_m.n_faces)
            if sol_fn[f, 2] < -0.95
            and (z_floor + 60.0) < float(sol_pts[f, :, 2].mean()) < (z_ceil - 5.0)
        ]
        if soffit_fids:
            v_off = len(in_mesh_filled.positions)
            vt_off = len(in_mesh_filled.uvs) if in_mesh_filled.uvs is not None else 0
            in_mesh_filled.positions = np.vstack([in_mesh_filled.positions, sol_m.positions[sol_m.face_v[soffit_fids]].reshape(-1, 3)])
            new_fv = np.arange(v_off, v_off + 3 * len(soffit_fids), dtype=np.int64).reshape(-1, 3)
            in_mesh_filled.face_v = np.vstack([in_mesh_filled.face_v, new_fv])
            if in_mesh_filled.uvs is not None and sol_m.uvs is not None and sol_m.face_vt is not None:
                in_mesh_filled.uvs = np.vstack([in_mesh_filled.uvs, sol_m.uvs[sol_m.face_vt[soffit_fids]].reshape(-1, 2)])
                new_fvt = np.arange(vt_off, vt_off + 3 * len(soffit_fids), dtype=np.int64).reshape(-1, 3)
                in_mesh_filled.face_vt = np.vstack([in_mesh_filled.face_vt, new_fvt])
            in_mesh_filled.face_material = np.concatenate([in_mesh_filled.face_material, sol_m.face_material[soffit_fids]])
            in_mesh_filled.face_vn = np.vstack([in_mesh_filled.face_vn, np.full((len(soffit_fids), 3), -1, dtype=np.int64)])
            in_mesh_filled.face_line = np.concatenate([in_mesh_filled.face_line, np.zeros(len(soffit_fids), dtype=np.int64)])

    state = start_fix(in_mesh_filled, flatness, FixProfile(solidify=False, guard_size=(256, 256)))
    for st_name, st_fn in FIX_STAGES:
        if st_name == "merge":
            continue
        state = st_fn(state)
        if st_name == "hidden":
            if "hidden" not in active_stages:
                state.removed_hidden_full[:] = False
                state.removed_pass1[:] = False
                state.n_removed_hidden = 0
                continue
            ref_m = state.mesh
            topo_ref = state.topo
            fn_ref = face_normals(topo_ref.positions_w, topo_ref.face_w, topo_ref.ok)
            pts_face = topo_ref.positions_w[topo_ref.face_w]
            z_min = pts_face[:, :, 2].min(axis=1)
            z_mean = pts_face[:, :, 2].mean(axis=1)

            caster = EmbreeCaster(state.positions_c, topo_ref.face_w[topo_ref.ok])
            tri_c = state.positions_c[topo_ref.face_w]
            pts_f = np.einsum("sb,fbk->fsk", BARY, tri_c) + 1.0 * fn_ref[:, None, :]
            pts_b = np.einsum("sb,fbk->fsk", BARY, tri_c) - 1.0 * fn_ref[:, None, :]
            dirs_f = np.repeat(fn_ref[:, None, :], len(BARY), axis=1).reshape(-1, 3)
            _, t_f = caster.first_hit(pts_f.reshape(-1, 3), dirs_f)
            _, t_b = caster.first_hit(pts_b.reshape(-1, 3), -dirs_f)
            tf_med = np.median(t_f.reshape(ref_m.n_faces, len(BARY)), axis=1)
            tb_med = np.median(t_b.reshape(ref_m.n_faces, len(BARY)), axis=1)
            max_t_either = np.maximum(tf_med, tb_med)
            t_up = np.where(fn_ref[:, 2] >= 0.0, tf_med, tb_med)

            is_vert_wall = (np.abs(fn_ref[:, 2]) < 0.95) & (z_min >= z_floor - 0.5)
            is_elev_cap = (np.abs(fn_ref[:, 2]) >= 0.95) & (z_mean > z_floor + 5.0) & (t_up > 18.0)
            is_wall_or_cap = is_vert_wall | is_elev_cap

            kept_now = ~state.removed_hidden_full
            has_open_room_air = is_vert_wall & (max_t_either > 22.0)
            active_wall_regs = set(
                topo_ref.face_region[(kept_now | has_open_room_air) & is_wall_or_cap].tolist()
            )
            active_wall_regs.discard(-1)

            cand_rescue = (
                state.removed_hidden_full
                & is_wall_or_cap
                & (has_open_room_air | np.isin(topo_ref.face_region, list(active_wall_regs)))
            )

            clusters = cluster_coplanar_faces(topo_ref.positions_w, topo_ref.face_w, fn_ref, topo_ref.ok)
            rescue_mask = np.zeros(ref_m.n_faces, dtype=bool)
            drop_endcap_mask = np.zeros(ref_m.n_faces, dtype=bool)

            for cn, fids_on_p in clusters:
                u_ax, v_ax = plane_basis(cn)
                mat_plane_area: dict[int, float] = {}
                poly_map: dict[int, Polygon] = {}
                for f in fids_on_p:
                    p2 = np.stack([pts_face[f] @ u_ax, pts_face[f] @ v_ax], axis=-1)
                    poly = Polygon(p2)
                    if poly.is_valid and poly.area > 0.1:
                        poly_map[f] = poly
                        m_id = int(ref_m.face_material[f])
                        mat_plane_area[m_id] = mat_plane_area.get(m_id, 0.0) + float(poly.area)

                is_horiz_or_slope = abs(float(cn[2])) > 0.5

                def _plane_priority(f: int) -> tuple[int, float, float]:
                    up_flag = (1 if float(fn_ref[f, 2]) > 0.0 else 0) if is_horiz_or_slope else 1
                    m_area = round(mat_plane_area.get(int(ref_m.face_material[f]), 0.0), 1)
                    return (up_flag, m_area, float(poly_map[f].area))

                kfids = sorted(
                    [f for f in fids_on_p if kept_now[f] and f in poly_map],
                    key=_plane_priority,
                    reverse=True,
                )
                cfids = sorted(
                    [f for f in fids_on_p if cand_rescue[f] and f in poly_map],
                    key=_plane_priority,
                    reverse=True,
                )

                covered_union = Polygon()
                for kf in kfids:
                    kpoly = poly_map[kf]
                    km = int(ref_m.face_material[kf])
                    dom_cand_polys = [
                        poly_map[cf]
                        for cf in cfids
                        if mat_plane_area.get(int(ref_m.face_material[cf]), 0.0) > 1.5 * mat_plane_area.get(km, 0.0)
                    ]
                    if dom_cand_polys:
                        dom_u = unary_union(dom_cand_polys)
                        if float(kpoly.intersection(dom_u).area) > 0.80 * float(kpoly.area):
                            drop_endcap_mask[kf] = True
                            continue
                    ovl_k = float(kpoly.intersection(covered_union).area) if not covered_union.is_empty else 0.0
                    if ovl_k > 0.15 * float(kpoly.area):
                        drop_endcap_mask[kf] = True
                        continue
                    covered_union = covered_union.union(kpoly) if not covered_union.is_empty else kpoly

                for cf in cfids:
                    c_poly = poly_map[cf]
                    ovl_a = float(c_poly.intersection(covered_union).area) if not covered_union.is_empty else 0.0
                    if ovl_a > 0.10 * float(c_poly.area):
                        continue
                    rescue_mask[cf] = True
                    covered_union = covered_union.union(c_poly) if not covered_union.is_empty else c_poly

            state.removed_hidden_full = (state.removed_hidden_full & (~rescue_mask)) | drop_endcap_mask
            state.removed_pass1 = (state.removed_pass1 & (~rescue_mask)) | drop_endcap_mask
            state.n_removed_hidden = int(state.removed_hidden_full.sum())

    repaired = state.mesh_overlapped if state.mesh_overlapped is not None else state.mesh
    if "unify_normals" in active_stages:
        repaired = unify_single_layer_coplanar_normals(repaired)
    if "coplanar_overlaps" in active_stages:
        repaired, _ = remove_coplanar_overlaps(repaired, overlap_ratio=0.10, drop_only=True)

    res_rings: dict | list = {}
    merge_report: dict = {}
    if "merge" in active_stages:
        flat_mats = flat_material_indices(repaired, flatness)
        topo_uni = analyse_topology(repaired, flat_mats)
        m_res = merge_regions(repaired, topo_uni, flat_mats)
        repaired = m_res.mesh
        res_rings = m_res.rings
        merge_report = m_res.report

    total_post_notches = 0
    if "holes" in active_stages:
        for _ in range(3):
            repaired, n_post = fill_wall_cap_notches(repaired)
            if n_post == 0:
                break
            total_post_notches += n_post
        if total_post_notches > 0 and "merge" in active_stages:
            flat_mats = flat_material_indices(repaired, flatness)
            topo_post = analyse_topology(repaired, flat_mats)
            m_res_post = merge_regions(repaired, topo_post, flat_mats)
            repaired = m_res_post.mesh
            res_rings = m_res_post.rings
            merge_report = m_res_post.report

    n_dropped_fin = 0
    if "coplanar_overlaps" in active_stages:
        repaired, n_dropped_fin = remove_coplanar_overlaps(repaired, overlap_ratio=0.05, drop_only=True)

    n_restored_walls = 0
    if "restore_visible_surfaces" in active_stages:
        pts_orig = mesh_orig_vis.positions[mesh_orig_vis.face_v]
        fn_orig = face_normals(mesh_orig_vis.positions, mesh_orig_vis.face_v, np.ones(mesh_orig_vis.n_faces, dtype=bool))
        ok_orig = (~np.isnan(fn_orig).any(axis=1)) & (np.linalg.norm(fn_orig, axis=1) > 0.5)
        caster_orig = EmbreeCaster(mesh_orig_vis.positions, mesh_orig_vis.face_v[ok_orig])
        pf_orig = np.einsum("sb,fbk->fsk", BARY, pts_orig) + 1.0 * fn_orig[:, None, :]
        pb_orig = np.einsum("sb,fbk->fsk", BARY, pts_orig) - 1.0 * fn_orig[:, None, :]
        df_orig = np.repeat(fn_orig[:, None, :], len(BARY), axis=1).reshape(-1, 3)
        _, tf_o = caster_orig.first_hit(pf_orig.reshape(-1, 3), df_orig)
        _, tb_o = caster_orig.first_hit(pb_orig.reshape(-1, 3), -df_orig)
        tf_o_max = tf_o.reshape(mesh_orig_vis.n_faces, len(BARY)).max(axis=1)
        tb_o_max = tb_o.reshape(mesh_orig_vis.n_faces, len(BARY)).max(axis=1)
        tup_o = np.where(fn_orig[:, 2] >= 0.0, tf_o_max, tb_o_max)
        vis_surface_mask = ok_orig & (
            ((np.abs(fn_orig[:, 2]) > 0.5) & np.isinf(tup_o))
            | ((np.abs(fn_orig[:, 2]) <= 0.5) & (np.maximum(tf_o_max, tb_o_max) > 40.0))
        )
        repaired, n_restored_walls = restore_missing_visible_wall_faces(
            mesh_orig_vis, repaired, vis_surface_mask, min_missing_area=20.0
        )

    if (n_dropped_fin > 0 or n_restored_walls > 0) and "merge" in active_stages:
        flat_mats = flat_material_indices(repaired, flatness)
        topo_fin = analyse_topology(repaired, flat_mats)
        m_res_fin = merge_regions(repaired, topo_fin, flat_mats)
        repaired = m_res_fin.mesh
        res_rings = m_res_fin.rings
        merge_report = m_res_fin.report

    repaired, res_rings = compact_mesh(repaired, res_rings)

    stats = {
        "n_removed_hidden": int(state.n_removed_hidden + n_liners_dropped + n_pre_ovl_dropped),
        "n_solidified": len(soffit_fids),
        "n_holes_filled": int(n_notches_before + total_post_notches),
        "n_flipped": int(getattr(state, "n_flipped", 0)),
        "merge_report": merge_report,
        "enabled_stages": [s for s in REPAIR_STAGE_ORDER if s in active_stages],
    }
    return repaired, res_rings, stats
