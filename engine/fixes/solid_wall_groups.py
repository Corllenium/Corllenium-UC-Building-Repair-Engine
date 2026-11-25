"""Solid Wall & Column Repair, Semantic Grouping & Cutaway-Ready Export (`engine.fixes.solid_wall_groups`).

Produces closed, watertight, outward-normal semantic solid groups from any UC campus floor mesh
(starting with CHTM 4F = `Floor_4F` / `CHTM_5ft_floor_obj`), enforcing:
- 2026-11-23 `building_repair.py` stage order, Zero-Hole Safety Law (`patch_protect.py`),
  post-merge overlap cleanup, mandatory `diff_overlay.py` facade self-heal, and Stage 5 10-Point Gate.
- Planar visible-hole auto-capping (`cap_visible_holes.py`), near-coplanar Z-fighting resolution
  (`unity_preflight.py`), and zero-drift cross-plane T-junction stitching (`tjunction_stitch.py`).
- Trapped internal hollow-wall cavity rib removal (`D11`/`D15` -> `G01` clean wall pipelines).
- Semantic grouping: `Floor_Slab`, `OverheadBeams_And_Lintels`, `Glass_Openings`, `Stairs`,
  `Column_01..NN` (`G02` solid unbroken columns), `Wall_Ext_N/S/E/W_XX`, `Wall_Int_XX`.
- Optional clean horizontal cutaway edge loop (`cut_height_m`, default `1.10 m`) so Homescape /
  Three.js / Unity 6 wall display/hide transitions never stretch or split diagonally into triangles.
- Exact CKPT-17 Z-up inches <-> Unity 6 Y-up metres bijection + multi-node textured `.glb` export.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
import copy
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import shapely
from shapely.geometry import Polygon, box as shapely_box
from shapely.ops import unary_union
import trimesh

from engine.detectors.wall_column_audit import audit_wall_column_health, signed_volume

INCH_TO_METRE = 0.0254
METRE_TO_INCH = 1.0 / INCH_TO_METRE


def convert_ckpt17_to_unity_coords(positions_in: np.ndarray) -> np.ndarray:
    """Convert SketchUp CKPT17 (Z-up, inches) positions to Unity Export (Y-up, metres), det = +1."""
    pts = np.asarray(positions_in, dtype=np.float64).reshape(-1, 3)
    return np.column_stack([
        -INCH_TO_METRE * pts[:, 0],
        +INCH_TO_METRE * pts[:, 2],
        +INCH_TO_METRE * pts[:, 1],
    ])


def convert_unity_to_ckpt17_coords(positions_m: np.ndarray) -> np.ndarray:
    """Convert Unity Export (Y-up, metres) positions to SketchUp CKPT17 (Z-up, inches), det = +1."""
    pts = np.asarray(positions_m, dtype=np.float64).reshape(-1, 3)
    return np.column_stack([
        -pts[:, 0] / INCH_TO_METRE,
        +pts[:, 2] / INCH_TO_METRE,
        +pts[:, 1] / INCH_TO_METRE,
    ])
from engine.fixes.building_repair import (
    compact_mesh,
    remove_coplanar_overlaps,
    repair_building_floor_mesh,
)
from engine.fixes.cap_visible_holes import cap_visible_planar_holes
from engine.fixes.orient import ORIENT_FLIP, classify_orientation, flip_faces
from engine.fixes.remove import remove_faces
from engine.fixes.tjunction_stitch import stitch_cross_plane_tjunctions
from engine.io.mtl import parse_mtl
from engine.model import MeshData
from engine.rays.caster import EmbreeCaster
from engine.topo.adjacency import build_edge_table, degenerate_mask, edge_face_lists
from engine.topo.planes import face_normals, plane_basis
from engine.topo.weld import weld_exact
from engine.validate.unity_preflight import (
    resolve_near_coplanar_zfight,
    run_unity_preflight_gate,
)
from engine.vis.exposure import EXP_OUTSIDE, classify_exposure, compute_side_exposure


@dataclass
class SolidWallGroupResult:
    mesh_ckpt17: MeshData
    mesh_unity: MeshData
    face_groups: list[str]
    manifest: dict
    audit_before: dict
    audit_after: dict
    preflight_unity: dict
    stage_stats: dict


def _is_unity_yup_metres(mesh: MeshData) -> bool:
    if getattr(mesh, "units", "inches") == "metres":
        return True
    lo, hi = mesh.bbox()
    size = hi - lo
    return bool(float(size[1]) < float(size[0]) and float(size[1]) < float(size[2]) and float(size.max()) < 250.0)


def _to_ckpt17_mesh(mesh: MeshData) -> MeshData:
    if not _is_unity_yup_metres(mesh):
        out = copy.deepcopy(mesh)
        out.units = "inches"
        return out
    out = copy.deepcopy(mesh)
    out.positions = convert_unity_to_ckpt17_coords(out.positions)
    out.units = "inches"
    out.coord_decimals = max(out.coord_decimals, 2)
    return out


def _to_unity_mesh(mesh_ckpt17: MeshData) -> MeshData:
    out = copy.deepcopy(mesh_ckpt17)
    out.positions = convert_ckpt17_to_unity_coords(out.positions)
    out.normals = np.zeros((0, 3), dtype=np.float64)
    out.face_vn = np.full((out.n_faces, 3), -1, dtype=np.int64)
    out.units = "metres"
    out.coord_decimals = 4
    return out


def _purge_trapped_cavity_faces(
    mesh: MeshData,
    cavity_dist_in: float = 33.5,
    max_passes: int = 3,
) -> tuple[MeshData, int]:
    """Remove BOTH vertical internal cavity ribs AND horizontal trapped wall-cavity shelf fins (D11/D15 -> G01)."""
    cur = mesh
    total_purged = 0
    for _ in range(max_passes):
        if cur.n_faces == 0:
            break
        fn = face_normals(cur.positions, cur.face_v, np.ones(cur.n_faces, dtype=bool))
        ok = (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) > 0.5)
        if not ok.any():
            break

        center = 0.5 * (cur.positions.min(axis=0) + cur.positions.max(axis=0))
        pos_c = cur.positions - center
        pts_c = pos_c[cur.face_v]
        pts_w = cur.positions[cur.face_v]
        lo_z, hi_z = float(cur.positions[:, 2].min()), float(cur.positions[:, 2].max())

        # Protect exterior-exposed faces (EXP_OUTSIDE) unconditionally
        ef, eb = compute_side_exposure(pos_c, cur.face_v, ok, n_dirs=64)
        outside = ok & (classify_exposure(ef + eb, ok) == EXP_OUTSIDE)

        caster = EmbreeCaster(pos_c, cur.face_v[ok])
        drop = np.zeros(cur.n_faces, dtype=bool)
        eps = 0.35  # inches

        # 1. Vertical internal cavity ribs trapped on BOTH normal sides within cavity_dist_in
        vert = ok & (np.abs(fn[:, 2]) < 0.25)
        v_ids = np.flatnonzero(vert)
        if len(v_ids) > 0:
            v_cent = pts_c[v_ids].mean(axis=1)
            v_n = fn[v_ids]
            _, tf = caster.first_hit(v_cent + eps * v_n, v_n)
            _, tb = caster.first_hit(v_cent - eps * v_n, -v_n)
            trapped_v = (tf < cavity_dist_in) & (tb < cavity_dist_in)
            for local_i in np.flatnonzero(trapped_v):
                fid = int(v_ids[local_i])
                if not outside[fid]:
                    drop[fid] = True

        # 2. Horizontal trapped hollow-wall shelf fins (D11/D15) buried inside wall cavities
        z_mid = pts_w[:, :, 2].mean(axis=1)
        horiz_mid = ok & (np.abs(fn[:, 2]) > 0.75) & (~outside) & (z_mid > lo_z + 44.0) & (z_mid < hi_z - 8.0)
        h_ids = np.flatnonzero(horiz_mid)
        if len(h_ids) > 0:
            h_cent = pts_c[h_ids].mean(axis=1)
            m_h = len(h_ids)
            up_d = np.broadcast_to(np.array([[0.0, 0.0, 1.0]]), (m_h, 3)).copy()
            dn_d = np.broadcast_to(np.array([[0.0, 0.0, -1.0]]), (m_h, 3)).copy()
            px_d = np.broadcast_to(np.array([[1.0, 0.0, 0.0]]), (m_h, 3)).copy()
            nx_d = np.broadcast_to(np.array([[-1.0, 0.0, 0.0]]), (m_h, 3)).copy()
            py_d = np.broadcast_to(np.array([[0.0, 1.0, 0.0]]), (m_h, 3)).copy()
            ny_d = np.broadcast_to(np.array([[0.0, -1.0, 0.0]]), (m_h, 3)).copy()

            _, t_up = caster.first_hit(h_cent + eps * up_d, up_d)
            _, t_dn = caster.first_hit(h_cent + eps * dn_d, dn_d)
            _, t_px = caster.first_hit(h_cent + eps * up_d, px_d)
            _, t_nx = caster.first_hit(h_cent + eps * up_d, nx_d)
            _, t_py = caster.first_hit(h_cent + eps * up_d, py_d)
            _, t_ny = caster.first_hit(h_cent + eps * up_d, ny_d)

            trapped_lat = ((t_px < cavity_dist_in) & (t_nx < cavity_dist_in)) | (
                (t_py < cavity_dist_in) & (t_ny < cavity_dist_in)
            )
            trapped_vert = (t_up < 150.0) & (t_dn < 150.0)
            low_exp = (ef[h_ids] + eb[h_ids]) < 0.03
            for local_i in np.flatnonzero(trapped_lat & trapped_vert & low_exp):
                drop[int(h_ids[local_i])] = True

        if not drop.any():
            break
        cur, _ = remove_faces(cur, drop)
        total_purged += int(drop.sum())
    return cur, total_purged


def _dedup_exact_triangles(
    mesh: MeshData,
    face_groups: list[str] | None = None,
) -> tuple[MeshData, list[str] | None, int]:
    """Drop degenerate and exact-duplicate canonical triangles while keeping `face_groups` aligned."""
    if mesh.n_faces == 0:
        return mesh, face_groups, 0
    pos_w, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    fw = remap[mesh.face_v]
    pts = pos_w[fw]
    areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)

    seen: set[tuple[int, int, int]] = set()
    keep = np.zeros(mesh.n_faces, dtype=bool)
    for fi in range(mesh.n_faces):
        v0, v1, v2 = int(fw[fi, 0]), int(fw[fi, 1]), int(fw[fi, 2])
        if v0 == v1 or v1 == v2 or v0 == v2 or float(areas[fi]) <= 1e-6:
            continue
        key = tuple(sorted((v0, v1, v2)))
        if key in seen:
            continue
        seen.add(key)
        keep[fi] = True

    n_dropped = int((~keep).sum())
    if n_dropped == 0:
        return mesh, face_groups, 0
    out, _ = remove_faces(mesh, ~keep)
    new_groups = [g for g, k in zip(face_groups, keep.tolist()) if k] if face_groups is not None else None
    return out, new_groups, n_dropped


def _orient_strictly_outward(
    mesh: MeshData,
    *,
    n_dirs: int = 128,
    max_passes: int = 3,
) -> tuple[MeshData, int]:
    """Iteratively flip inward-facing triangles via 128-direction exposure until reversed == 0."""
    cur = mesh
    total_flipped = 0
    for _ in range(max_passes):
        if cur.n_faces == 0:
            break
        fn = face_normals(cur.positions, cur.face_v, np.ones(cur.n_faces, dtype=bool))
        ok = (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) > 0.5)
        if not ok.any():
            break
        cen = 0.5 * (cur.positions.min(axis=0) + cur.positions.max(axis=0))
        ef, eb = compute_side_exposure(cur.positions - cen, cur.face_v, ok, n_dirs=n_dirs)
        flip_mask = (classify_orientation(ef, eb, ok) == ORIENT_FLIP) & ok
        n_flip = int(flip_mask.sum())
        if n_flip == 0:
            break
        cur = flip_faces(cur, flip_mask)
        total_flipped += n_flip
    return cur, total_flipped


def _resolve_flicker_pairs_with_groups(
    mesh: MeshData,
    face_groups: list[str],
    *,
    max_passes: int = 3,
) -> tuple[MeshData, list[str], int]:
    """Drop remaining 26-view coplanar flicker duplicates while preserving `face_groups` alignment."""
    from engine.fixes.overlap import double_layers
    from engine.fixes.pipeline import FixProfile, guard_depth_tol
    from engine.guard.views import VIEWS_26
    from engine.pipeline import analyse_topology

    cur = mesh
    groups = list(face_groups)
    total_dropped = 0
    profile = FixProfile()
    for _ in range(max_passes):
        if cur.n_faces == 0:
            break
        topo = analyse_topology(cur, frozenset(), coplanar_angle=profile.coplanar_angle, soft_angle=profile.soft_angle)
        pos, faces, ok = topo.positions_w, topo.face_w, topo.ok
        if not ok.any():
            break
        centre = 0.5 * (pos.min(axis=0) + pos.max(axis=0))
        depth_tol = guard_depth_tol(topo.quanta, profile)
        dl = double_layers(pos - centre, faces, depth_tol, VIEWS_26, profile.guard_size, centre=centre)
        pairs = dl.get("pair_list", [])
        if not pairs:
            break

        pts = pos[faces]
        areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)
        ef, eb = compute_side_exposure(pos - centre, faces, ok, n_dirs=32)
        exp_tot = ef + eb

        def _mat_tier(fi: int) -> int:
            mi = int(cur.face_material[fi])
            mname = cur.materials[mi].lower() if 0 <= mi < len(cur.materials) else ""
            if any(k in mname for k in ("quartz", "glass", "iron", "prismarine", "metal", "wood", "tile", "brick", "wool")):
                return 2
            if "littletiles" in mname:
                return 1
            return 0

        drop = np.zeros(cur.n_faces, dtype=bool)
        for a, b, _s, _o in pairs:
            a_i, b_i = int(a), int(b)
            if drop[a_i] or drop[b_i]:
                continue
            sa = (float(exp_tot[a_i]) > 1e-4, _mat_tier(a_i), float(areas[a_i]))
            sb = (float(exp_tot[b_i]) > 1e-4, _mat_tier(b_i), float(areas[b_i]))
            victim = b_i if sa >= sb else a_i
            drop[victim] = True

        if not drop.any():
            break
        cur, _ = remove_faces(cur, drop)
        groups = [g for g, d in zip(groups, drop.tolist()) if not d]
        total_dropped += int(drop.sum())
    return cur, groups, total_dropped


def _compute_local_floor_z_map(mesh: MeshData) -> tuple[float, np.ndarray, tuple[float, float, float, int, int]]:
    """Build a 2D cell map of walkable floor slab top Z (inches) to handle multi-level floors cleanly."""
    lo, hi = mesh.bbox()
    z_min_all = float(lo[2])
    z_max_all = float(hi[2])
    fn = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    pts = mesh.positions[mesh.face_v]
    areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)
    z_mean = pts[:, :, 2].mean(axis=1)

    # Walkable floor tops: upward-facing, non-glass, within lower 45% of floor height
    z_band_hi = z_min_all + 0.45 * max(z_max_all - z_min_all, 1.0)
    is_glass = np.array(
        ["glass" in (mesh.materials[int(m)].lower() if 0 <= int(m) < len(mesh.materials) else "") for m in mesh.face_material],
        dtype=bool,
    )
    walk_mask = (fn[:, 2] > 0.75) & (~is_glass) & (z_mean <= z_band_hi) & (areas > 50.0)
    if not walk_mask.any():
        # Fallback to lowest upward horizontal faces
        walk_mask = (fn[:, 2] > 0.75) & (z_mean <= z_min_all + 80.0) & (areas > 1.0)

    if walk_mask.any():
        # Dominant walkable floor elevation weighted by area (quantized to 2 in bands)
        wz = np.round(z_mean[walk_mask] / 2.0) * 2.0
        wa = areas[walk_mask]
        z_weights: dict[float, float] = defaultdict(float)
        for z_val, a_val in zip(wz.tolist(), wa.tolist()):
            z_weights[z_val] += a_val
        dominant_floor_z = max(z_weights, key=lambda k: z_weights[k])
    else:
        dominant_floor_z = z_min_all

    # 20 in (~0.5 m) 2D grid storing local floor elevation
    cell = 20.0
    x0, y0 = float(lo[0]), float(lo[1])
    nx = max(1, int(np.ceil((float(hi[0]) - x0) / cell)) + 1)
    ny = max(1, int(np.ceil((float(hi[1]) - y0) / cell)) + 1)
    z_grid = np.full((nx, ny), dominant_floor_z, dtype=np.float64)
    a_grid = np.zeros((nx, ny), dtype=np.float64)

    for f in np.flatnonzero(walk_mask):
        fx0, fx1 = float(pts[f, :, 0].min()), float(pts[f, :, 0].max())
        fy0, fy1 = float(pts[f, :, 1].min()), float(pts[f, :, 1].max())
        ix0 = max(0, int((fx0 - x0) / cell))
        ix1 = min(nx - 1, int((fx1 - x0) / cell))
        iy0 = max(0, int((fy0 - y0) / cell))
        iy1 = min(ny - 1, int((fy1 - y0) / cell))
        fz = float(z_mean[f])
        fa = float(areas[f])
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                if fa > a_grid[ix, iy]:
                    a_grid[ix, iy] = fa
                    z_grid[ix, iy] = fz

    return dominant_floor_z, z_grid, (x0, y0, cell, nx, ny)


def _lookup_local_floor_z(
    xy: np.ndarray,
    z_grid: np.ndarray,
    grid_meta: tuple[float, float, float, int, int],
) -> np.ndarray:
    x0, y0, cell, nx, ny = grid_meta
    ix = np.clip(((xy[:, 0] - x0) / cell).astype(np.int64), 0, nx - 1)
    iy = np.clip(((xy[:, 1] - y0) / cell).astype(np.int64), 0, ny - 1)
    return z_grid[ix, iy]


def _slice_mesh_by_z_plane(
    mesh: MeshData,
    face_groups: list[str] | None,
    z_plane_per_face: np.ndarray,
    target_prefixes: tuple[str, ...] | None = ("Wall_",),
    tol: float = 0.20,
) -> tuple[MeshData, list[str], int]:
    """Slice vertical wall triangles cleanly along horizontal `z_plane_per_face` with linear UV interpolation."""
    groups_in = list(face_groups) if face_groups is not None else [""] * mesh.n_faces
    if mesh.n_faces == 0:
        return mesh, groups_in, 0

    fn_all = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    pos_list = mesh.positions.tolist()
    has_uvs = mesh.uvs is not None and len(mesh.uvs) > 0 and mesh.face_vt is not None
    uv_list = mesh.uvs.tolist() if has_uvs else []

    new_fv: list[list[int]] = []
    new_fvt: list[list[int]] = []
    new_fvn: list[list[int]] = []
    new_fmat: list[int] = []
    new_fline: list[int] = []
    new_groups: list[str] = []

    edge_cache: dict[tuple[int, int, int], tuple[int, int]] = {}
    n_sliced = 0

    def _split_edge(v0: int, v1: int, vt0: int, vt1: int, z_cut: float) -> tuple[int, int]:
        z0 = pos_list[v0][2]
        z1 = pos_list[v1][2]
        t = (z_cut - z0) / (z1 - z0)
        key_z = int(round(z_cut * 100.0))
        ek = (v0, v1, key_z) if v0 < v1 else (v1, v0, key_z)
        if ek in edge_cache:
            vi_cached, _ = edge_cache[ek]
            if has_uvs and vt0 >= 0 and vt1 >= 0:
                u0 = uv_list[vt0]
                u1 = uv_list[vt1]
                vti = len(uv_list)
                uv_list.append([u0[0] + t * (u1[0] - u0[0]), u0[1] + t * (u1[1] - u0[1])])
            else:
                vti = -1
            return vi_cached, vti

        p0 = pos_list[v0]
        p1 = pos_list[v1]
        vi = len(pos_list)
        pos_list.append([p0[0] + t * (p1[0] - p0[0]), p0[1] + t * (p1[1] - p0[1]), z_cut])
        if has_uvs and vt0 >= 0 and vt1 >= 0:
            u0 = uv_list[vt0]
            u1 = uv_list[vt1]
            vti = len(uv_list)
            uv_list.append([u0[0] + t * (u1[0] - u0[0]), u0[1] + t * (u1[1] - u0[1])])
        else:
            vti = -1
        edge_cache[ek] = (vi, vti)
        return vi, vti

    def _append_valid(tri_v: list[int], tri_vt: list[int], tri_vn: list[int], mat: int, ln: int, gname: str) -> None:
        if len(set(tri_v)) < 3:
            return
        p0, p1, p2 = pos_list[tri_v[0]], pos_list[tri_v[1]], pos_list[tri_v[2]]
        ax, ay, az = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
        bx, by, bz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
        cx, cy, cz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
        if (cx * cx + cy * cy + cz * cz) <= 1e-10:
            return
        new_fv.append(tri_v)
        new_fvt.append(tri_vt)
        new_fvn.append(tri_vn)
        new_fmat.append(mat)
        new_fline.append(ln)
        new_groups.append(gname)

    for f in range(mesh.n_faces):
        gname = groups_in[f]
        fv = [int(mesh.face_v[f, 0]), int(mesh.face_v[f, 1]), int(mesh.face_v[f, 2])]
        fvt = [int(mesh.face_vt[f, 0]), int(mesh.face_vt[f, 1]), int(mesh.face_vt[f, 2])]
        fvn = [int(mesh.face_vn[f, 0]), int(mesh.face_vn[f, 1]), int(mesh.face_vn[f, 2])]
        mat = int(mesh.face_material[f])
        ln = int(mesh.face_line[f])

        z_cut = float(z_plane_per_face[f])
        eligible = (
            (abs(float(fn_all[f, 2])) < 0.35 if target_prefixes is None else gname.startswith(target_prefixes))
            and np.isfinite(z_cut)
        )
        if not eligible:
            new_fv.append(fv)
            new_fvt.append(fvt)
            new_fvn.append(fvn)
            new_fmat.append(mat)
            new_fline.append(ln)
            new_groups.append(gname)
            continue

        zs = [pos_list[v][2] for v in fv]
        if not (min(zs) < z_cut - tol and max(zs) > z_cut + tol):
            new_fv.append(fv)
            new_fvt.append(fvt)
            new_fvn.append(fvn)
            new_fmat.append(mat)
            new_fline.append(ln)
            new_groups.append(gname)
            continue

        below = [i for i in range(3) if zs[i] < z_cut - 1e-4]
        above = [i for i in range(3) if zs[i] > z_cut + 1e-4]
        on = [i for i in range(3) if abs(zs[i] - z_cut) <= 1e-4]

        if len(on) == 1 and len(below) == 1 and len(above) == 1:
            i0 = on[0]
            i1 = (i0 + 1) % 3
            i2 = (i0 + 2) % 3
            vm, vtm = _split_edge(fv[i1], fv[i2], fvt[i1], fvt[i2], z_cut)
            _append_valid([fv[i0], fv[i1], vm], [fvt[i0], fvt[i1], vtm], [-1, -1, -1], mat, ln, gname)
            _append_valid([fv[i0], vm, fv[i2]], [fvt[i0], vtm, fvt[i2]], [-1, -1, -1], mat, ln, gname)
            n_sliced += 1
            continue

        lone_list = below if len(below) == 1 else above
        if len(lone_list) != 1:
            new_fv.append(fv)
            new_fvt.append(fvt)
            new_fvn.append(fvn)
            new_fmat.append(mat)
            new_fline.append(ln)
            new_groups.append(gname)
            continue

        i0 = lone_list[0]
        i1 = (i0 + 1) % 3
        i2 = (i0 + 2) % 3
        va, vta = _split_edge(fv[i0], fv[i1], fvt[i0], fvt[i1], z_cut)
        vb, vtb = _split_edge(fv[i0], fv[i2], fvt[i0], fvt[i2], z_cut)

        _append_valid([fv[i0], va, vb], [fvt[i0], vta, vtb], [-1, -1, -1], mat, ln, gname)
        _append_valid([va, fv[i1], fv[i2]], [vta, fvt[i1], fvt[i2]], [-1, -1, -1], mat, ln, gname)
        _append_valid([va, fv[i2], vb], [vta, fvt[i2], vtb], [-1, -1, -1], mat, ln, gname)
        n_sliced += 1

    out = copy.deepcopy(mesh)
    out.positions = np.asarray(pos_list, dtype=np.float64)
    if has_uvs:
        out.uvs = np.asarray(uv_list, dtype=np.float64)
    out.face_v = np.asarray(new_fv, dtype=np.int64)
    out.face_vt = np.asarray(new_fvt, dtype=np.int64)
    out.face_vn = np.asarray(new_fvn, dtype=np.int64)
    out.face_material = np.asarray(new_fmat, dtype=np.int64)
    out.face_line = np.asarray(new_fline, dtype=np.int64)
    return out, new_groups, n_sliced


def _seal_group_planar_caps_and_orient(
    mesh: MeshData,
    face_groups: list[str],
    target_prefixes: tuple[str, ...] = ("Column_", "Wall_"),
) -> tuple[MeshData, list[str], dict]:
    """Close genuine global open planar boundary loops on standalone wall/column groups without duplicate seam caps."""
    out = copy.deepcopy(mesh)
    groups_out = list(face_groups)

    # Precompute global welded edges and existing triangle keys so we NEVER cap internal shared seams or duplicate tris
    g_pos_w, g_remap = weld_exact(out.positions, out.coord_decimals)
    g_fw = g_remap[out.face_v]
    g_ok = ~degenerate_mask(g_pos_w, g_fw)
    g_table = build_edge_table(g_fw, g_ok)
    g_ef = edge_face_lists(g_table)
    global_open_edges: set[tuple[int, int]] = set()
    for ei, fl in enumerate(g_ef):
        if len(fl) == 1:
            u, v = int(g_table.edges[ei, 0]), int(g_table.edges[ei, 1])
            global_open_edges.add((u, v) if u < v else (v, u))

    existing_tri_keys: set[tuple[int, int, int]] = {
        tuple(sorted((int(g_fw[fi, 0]), int(g_fw[fi, 1]), int(g_fw[fi, 2]))))
        for fi in range(out.n_faces)
    }

    by_g: dict[str, list[int]] = defaultdict(list)
    for fi, g in enumerate(groups_out):
        by_g[g].append(fi)

    caps_added = 0
    groups_flipped = 0

    for gname, fids in sorted(by_g.items()):
        if not gname.startswith(target_prefixes) or len(fids) < 3:
            continue
        f_arr = np.asarray(fids, dtype=np.int64)
        sub_fv = out.face_v[f_arr]
        used, inv = np.unique(sub_fv, return_inverse=True)
        sub_pos = out.positions[used]
        sub_f = inv.reshape(-1, 3)

        pos_w, remap = weld_exact(sub_pos, out.coord_decimals)
        fw = remap[sub_f]
        ok = ~degenerate_mask(pos_w, fw)
        table = build_edge_table(fw, ok)
        ef = edge_face_lists(table)

        w_to_orig: dict[int, int] = {}
        for local_v, wv in enumerate(remap.tolist()):
            w_to_orig.setdefault(int(wv), int(used[local_v]))

        # Collect open boundary edges of this group that are ALSO globally open (not shared with an adjacent group!)
        open_edges: list[tuple[int, int, int]] = []
        for ei, fl in enumerate(ef):
            if len(fl) == 1:
                wu, wv = int(table.edges[ei, 0]), int(table.edges[ei, 1])
                gu = int(g_remap[w_to_orig[wu]])
                gv = int(g_remap[w_to_orig[wv]])
                gek = (gu, gv) if gu < gv else (gv, gu)
                if gek in global_open_edges:
                    open_edges.append((wu, wv, int(fl[0])))

        if open_edges:
            adj: dict[int, list[tuple[int, int]]] = defaultdict(list)
            for idx_e, (wu, wv, lf) in enumerate(open_edges):
                adj[wu].append((wv, idx_e))
                adj[wv].append((wu, idx_e))

            visited_e: set[int] = set()
            dom_mat = int(np.bincount(out.face_material[f_arr]).argmax())
            added_fvs: list[list[int]] = []

            for start_e in range(len(open_edges)):
                if start_e in visited_e:
                    continue
                comp_e: list[int] = []
                stack = [start_e]
                visited_e.add(start_e)
                while stack:
                    cur = stack.pop()
                    comp_e.append(cur)
                    u0, v0, _ = open_edges[cur]
                    for vtx in (u0, v0):
                        for _nb, nb_e in adj[vtx]:
                            if nb_e not in visited_e:
                                visited_e.add(nb_e)
                                stack.append(nb_e)

                local_adj: dict[int, list[tuple[int, int]]] = defaultdict(list)
                for ei_c in comp_e:
                    u0, v0, _ = open_edges[ei_c]
                    local_adj[u0].append((v0, ei_c))
                    local_adj[v0].append((u0, ei_c))
                if len(local_adj) < 3 or any(len(nbs) != 2 for nbs in local_adj.values()):
                    continue

                start_v = next(iter(local_adj))
                loop_w = [start_v]
                cur_v = start_v
                used_ce: set[int] = set()
                ok_cycle = True
                for _ in range(len(comp_e)):
                    nxt_v = None
                    for nb_v, ce in local_adj[cur_v]:
                        if ce not in used_ce:
                            used_ce.add(ce)
                            nxt_v = nb_v
                            break
                    if nxt_v is None:
                        ok_cycle = False
                        break
                    if nxt_v == start_v:
                        break
                    if nxt_v in loop_w:
                        ok_cycle = False
                        break
                    loop_w.append(nxt_v)
                    cur_v = nxt_v
                if not ok_cycle or len(loop_w) != len(local_adj):
                    continue

                lp = pos_w[loop_w]
                l_cent = lp.mean(axis=0)
                _, _, vh = np.linalg.svd(lp - l_cent, full_matrices=False)
                n_cap = vh[-1]
                n_len = float(np.linalg.norm(n_cap))
                if n_len < 1e-6:
                    continue
                n_cap /= n_len
                if float(np.abs((lp - l_cent) @ n_cap).max()) > 0.35:
                    continue

                g_cent = pos_w.mean(axis=0)
                if float(np.dot(n_cap, l_cent - g_cent)) < 0.0:
                    n_cap = -n_cap

                u_ax, v_ax = plane_basis(n_cap)
                rel = lp - l_cent
                p2 = np.column_stack([rel @ u_ax, rel @ v_ax])
                poly = Polygon(p2)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if poly.is_empty or poly.geom_type != "Polygon" or float(poly.area) <= 0.05:
                    continue

                try:
                    cdt = shapely.constrained_delaunay_triangles(poly)
                    parts = list(cdt.geoms) if hasattr(cdt, "geoms") else [cdt]
                except Exception:
                    continue

                for part in parts:
                    if not isinstance(part, Polygon) or part.is_empty or float(part.area) <= 1e-3:
                        continue
                    if not poly.contains(part.representative_point()):
                        continue
                    coords = np.asarray(part.exterior.coords[:3], dtype=np.float64)
                    if len(coords) < 3:
                        continue
                    tri_orig: list[int] = []
                    valid_map = True
                    for q in coords:
                        dists = np.linalg.norm(p2 - q[None, :], axis=1)
                        k_min = int(np.argmin(dists))
                        if float(dists[k_min]) > 0.15:
                            valid_map = False
                            break
                        tri_orig.append(w_to_orig[loop_w[k_min]])
                    if not valid_map or len(set(tri_orig)) < 3:
                        continue
                    tkey = tuple(sorted((int(g_remap[tri_orig[0]]), int(g_remap[tri_orig[1]]), int(g_remap[tri_orig[2]]))))
                    if tkey in existing_tri_keys:
                        continue
                    tp = out.positions[tri_orig]
                    cr = np.cross(tp[1] - tp[0], tp[2] - tp[0])
                    if float(np.linalg.norm(cr)) < 1e-6:
                        continue
                    if float(np.dot(cr, n_cap)) < 0.0:
                        tri_orig = [tri_orig[0], tri_orig[2], tri_orig[1]]
                    existing_tri_keys.add(tkey)
                    added_fvs.append(tri_orig)

            if added_fvs:
                n_add = len(added_fvs)
                new_start = out.n_faces
                out.face_v = np.vstack([out.face_v, np.asarray(added_fvs, dtype=np.int64)])
                out.face_vt = np.vstack([out.face_vt, np.full((n_add, 3), -1, dtype=np.int64)])
                out.face_vn = np.vstack([out.face_vn, np.full((n_add, 3), -1, dtype=np.int64)])
                out.face_material = np.concatenate([out.face_material, np.full(n_add, dom_mat, dtype=np.int64)])
                out.face_line = np.concatenate([out.face_line, np.zeros(n_add, dtype=np.int64)])
                groups_out.extend([gname] * n_add)
                f_arr = np.concatenate([f_arr, np.arange(new_start, new_start + n_add, dtype=np.int64)])
                caps_added += n_add

        # Enforce positive outward signed volume on closed solid groups
        sub_fv2 = out.face_v[f_arr]
        used2, inv2 = np.unique(sub_fv2, return_inverse=True)
        pos_w2, remap2 = weld_exact(out.positions[used2], out.coord_decimals)
        fw2 = remap2[inv2.reshape(-1, 3)]
        ok2 = ~degenerate_mask(pos_w2, fw2)
        tbl2 = build_edge_table(fw2, ok2)
        ef2 = edge_face_lists(tbl2)
        if all(len(fl) == 2 for fl in ef2):
            vol = signed_volume(pos_w2, fw2[ok2])
            if vol < 0.0:
                out.face_v[f_arr] = out.face_v[f_arr][:, [0, 2, 1]]
                out.face_vt[f_arr] = out.face_vt[f_arr][:, [0, 2, 1]]
                out.face_vn[f_arr] = out.face_vn[f_arr][:, [0, 2, 1]]
                groups_flipped += 1

    return out, groups_out, {"caps_added": caps_added, "groups_flipped": groups_flipped}


def _detect_stair_faces(
    mesh: MeshData,
    fn: np.ndarray,
    pts: np.ndarray,
    local_fz: np.ndarray,
    full_adj: dict[int, list[int]],
    mat_names: list[str],
) -> np.ndarray:
    """Geometrically detect true stepped staircases (ignoring wall top rims, window sills, and prismarine baseboards)."""
    n = mesh.n_faces
    is_stair = np.zeros(n, dtype=bool)
    if n == 0:
        return is_stair

    lo, hi = mesh.bbox()
    z_ceil = float(hi[2])
    areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)
    z_mean = pts[:, :, 2].mean(axis=1)
    x_min, x_max = pts[:, :, 0].min(axis=1), pts[:, :, 0].max(axis=1)
    y_min, y_max = pts[:, :, 1].min(axis=1), pts[:, :, 1].max(axis=1)

    # Candidate stair treads: upward horizontal faces strictly below ceiling/wall-top rims (`z_ceil - 18 in`)
    # and above walkable floor (`local_fz + 3 in`), with compact tread size (each step <= 4.5 m^2)
    cand = [
        f for f in range(n)
        if "glass" not in mat_names[f]
        and "prismarine" not in mat_names[f]
        and float(fn[f, 2]) > 0.75
        and float(local_fz[f]) + 3.0 < float(z_mean[f]) < z_ceil - 18.0
        and 10.0 <= float(areas[f]) <= 7000.0
    ]
    if len(cand) < 5:
        return is_stair

    # Strict stair-step clustering: adjacent steps touch/sit within 6 in horizontally AND step vertically by 3..14 in
    # (or coplanar split triangles of the SAME tread within 1 in horizontally and |dz| <= 1 in)
    m = len(cand)
    c_adj: list[list[int]] = [[] for _ in range(m)]
    for i in range(m):
        fi = cand[i]
        xi0, xi1 = float(x_min[fi]), float(x_max[fi])
        yi0, yi1 = float(y_min[fi]), float(y_max[fi])
        zi = float(z_mean[fi])
        for j in range(i + 1, m):
            fj = cand[j]
            dz = abs(float(z_mean[fj]) - zi)
            if dz > 14.0:
                continue
            pad = 1.5 if dz <= 1.0 else 6.0
            if (
                float(x_max[fj]) >= xi0 - pad and float(x_min[fj]) <= xi1 + pad
                and float(y_max[fj]) >= yi0 - pad and float(y_min[fj]) <= yi1 + pad
            ):
                # Require genuine vertical step or coplanar split tread; never chain flat ledges across gaps
                if dz <= 1.0 or dz >= 2.5:
                    c_adj[i].append(j)
                    c_adj[j].append(i)

    vis = [False] * m
    for i in range(m):
        if vis[i]:
            continue
        comp: list[int] = []
        stk = [i]
        vis[i] = True
        while stk:
            u = stk.pop()
            comp.append(cand[u])
            for v in c_adj[u]:
                if not vis[v]:
                    vis[v] = True
                    stk.append(v)

        z_levels = sorted({round(float(z_mean[f]) / 2.0) * 2.0 for f in comp})
        bx0, bx1 = float(x_min[comp].min()), float(x_max[comp].max())
        by0, by1 = float(y_min[comp].min()), float(y_max[comp].max())
        # Confirmed staircase: >= 5 distinct step Z-levels, >= 36 in climb, compact horizontal footprint (<= 8.5 m)
        if (
            len(z_levels) < 5
            or (z_levels[-1] - z_levels[0]) < 36.0
            or (bx1 - bx0) * INCH_TO_METRE > 8.5
            or (by1 - by0) * INCH_TO_METRE > 8.5
        ):
            continue

        # Expand 1 edge-hop strictly inside the stair 2D bbox and below ceiling rim to grab step risers
        for f in comp:
            is_stair[f] = True
        for f in comp:
            for nb in full_adj[f]:
                if is_stair[nb] or "glass" in mat_names[nb]:
                    continue
                if float(pts[nb, :, 2].max()) >= z_ceil - 12.0:
                    continue
                if float(pts[nb, :, 2].max()) <= float(local_fz[nb]) + 2.5:
                    continue
                if (
                    float(x_min[nb]) >= bx0 - 2.0 and float(x_max[nb]) <= bx1 + 2.0
                    and float(y_min[nb]) >= by0 - 2.0 and float(y_max[nb]) <= by1 + 2.0
                ):
                    is_stair[nb] = True

    return is_stair


def _classify_and_group_faces(
    mesh: MeshData,
    *,
    per_segment: bool = True,
) -> tuple[list[str], np.ndarray, dict]:
    """Classify every triangle into clean semantic solid groups (true stairs, true overhead beams, double-sided walls)."""
    n = mesh.n_faces
    fn = face_normals(mesh.positions, mesh.face_v, np.ones(n, dtype=bool))
    pts = mesh.positions[mesh.face_v]
    lo, hi = mesh.bbox()
    cen_xy = pts[:, :, :2].mean(axis=1)
    z_min = pts[:, :, 2].min(axis=1)
    z_max = pts[:, :, 2].max(axis=1)

    dom_floor_z, z_grid, grid_meta = _compute_local_floor_z_map(mesh)
    local_fz = _lookup_local_floor_z(cen_xy, z_grid, grid_meta)

    center3 = 0.5 * (lo + hi)
    ok = (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) > 0.5)
    ef, eb = compute_side_exposure(mesh.positions - center3, mesh.face_v, ok, n_dirs=64)
    is_outside = ok & (classify_exposure(ef + eb, ok) == EXP_OUTSIDE)

    mat_names = [
        mesh.materials[int(m)].lower() if 0 <= int(m) < len(mesh.materials) else ""
        for m in mesh.face_material
    ]

    # Build full edge adjacency once
    pos_w, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    fw = remap[mesh.face_v]
    table = build_edge_table(fw, ok)
    ef_lists = edge_face_lists(table)
    full_adj: dict[int, list[int]] = defaultdict(list)
    for fl in ef_lists:
        if len(fl) >= 2:
            f0 = int(fl[0])
            for fk in fl[1:]:
                fk_i = int(fk)
                full_adj[f0].append(fk_i)
                full_adj[fk_i].append(f0)

    # Geometric stair detection (prismarine baseboards are NOT stairs!)
    is_stair = _detect_stair_faces(mesh, fn, pts, local_fz, full_adj, mat_names)

    # Build 2D footprint of lower standing walls/columns (fill interior rings so thick column top caps stay inside!)
    is_standing_vert = np.zeros(n, dtype=bool)
    lower_wall_polys = []
    for f in range(n):
        if "glass" in mat_names[f] or is_stair[f]:
            continue
        fz = float(local_fz[f])
        if abs(float(fn[f, 2])) < 0.30 and float(z_min[f]) <= fz + 28.0 and float(z_max[f]) > fz + 20.0:
            is_standing_vert[f] = True
            fx0, fy0 = float(pts[f, :, 0].min()), float(pts[f, :, 1].min())
            fx1, fy1 = float(pts[f, :, 0].max()), float(pts[f, :, 1].max())
            lower_wall_polys.append(shapely_box(fx0 - 6.0, fy0 - 6.0, fx1 + 6.0, fy1 + 6.0))
    if lower_wall_polys:
        raw_fp = unary_union(lower_wall_polys).buffer(8.0)
        fp_parts = list(raw_fp.geoms) if hasattr(raw_fp, "geoms") else [raw_fp]
        # Fill small enclosed interior rings (<= 4 m^2 = 6200 in^2) so hollow column cores stay inside the footprint
        filled_parts = []
        for part in fp_parts:
            if isinstance(part, Polygon) and not part.is_empty:
                kept_holes = [ring for ring in part.interiors if Polygon(ring).area > 6200.0]
                filled_parts.append(Polygon(part.exterior, kept_holes))
        standing_wall_fp = unary_union(filled_parts) if filled_parts else raw_fp
    else:
        standing_wall_fp = Polygon()

    # 1. Assign base architectural roles: Glass_Openings, Floor_Slab, Stairs, OverheadBeams_And_Lintels
    labels = [""] * n
    wall_col_candidates: list[int] = []
    for f in range(n):
        mname = mat_names[f]
        fz = float(local_fz[f])
        f_zmin = float(z_min[f])
        f_zmax = float(z_max[f])
        nz = float(fn[f, 2])

        if "glass" in mname:
            labels[f] = "Glass_Openings"
        elif nz < -0.75 and abs(f_zmin - fz) <= 4.0 and any(is_standing_vert[nb] for nb in full_adj[f]):
            # Bottom contact cap of a standing wall/column at walkable floor level stays on that wall/column!
            wall_col_candidates.append(f)
        elif nz > 0.75 and f_zmin > fz + 20.0 and any(is_standing_vert[nb] for nb in full_adj[f]):
            # Top cap directly closing a standing wall/column rim belongs to that wall/column!
            wall_col_candidates.append(f)
        elif f_zmax <= fz + 2.5:
            # Everything at or below local walkable floor top (including sliced 0..1m perimeter slab skirt)
            labels[f] = "Floor_Slab"
        elif is_stair[f]:
            labels[f] = "Stairs"
        elif f_zmin > fz + 68.9:
            # > +1.75 m above local floor: ONLY overhead beam/lintel if NO standing lower wall directly underneath!
            fc = shapely.Point(float(cen_xy[f, 0]), float(cen_xy[f, 1]))
            if standing_wall_fp.is_empty or not standing_wall_fp.contains(fc):
                labels[f] = "OverheadBeams_And_Lintels"
            else:
                wall_col_candidates.append(f)
        else:
            wall_col_candidates.append(f)

    if not wall_col_candidates:
        return labels, local_fz, {"dominant_floor_z_in": round(dom_floor_z, 2), "columns": 0, "walls_ext": 0, "walls_int": 0}

    # 2. Group wall & column candidates into connected 3D components (keeps both sides + rim + baseboard unified!)
    wc_set = set(wall_col_candidates)
    adj: dict[int, list[int]] = defaultdict(list)
    for fl in ef_lists:
        wc_fl = [int(f) for f in fl if int(f) in wc_set]
        if len(wc_fl) >= 2:
            f0 = wc_fl[0]
            for fk in wc_fl[1:]:
                adj[f0].append(fk)
                adj[fk].append(f0)

    def _connected_subcomps(fids: Sequence[int]) -> list[list[int]]:
        fset = set(fids)
        vis: set[int] = set()
        comps: list[list[int]] = []
        for f in fids:
            if f in vis:
                continue
            c: list[int] = []
            stk = [f]
            vis.add(f)
            while stk:
                cur = stk.pop()
                c.append(cur)
                for nb in adj[cur]:
                    if nb in fset and nb not in vis:
                        vis.add(nb)
                        stk.append(nb)
            comps.append(c)
        comps.sort(key=lambda c: (float(pts[c, :, 0].min()), float(pts[c, :, 1].min())))
        return comps

    components = _connected_subcomps(wall_col_candidates)

    col_count = 0
    ext_count = 0
    int_count = 0
    floor_cx = 0.5 * (float(lo[0]) + float(hi[0]))
    floor_cy = 0.5 * (float(lo[1]) + float(hi[1]))
    floor_dx = max(float(hi[0]) - float(lo[0]), 1.0)
    floor_dy = max(float(hi[1]) - float(lo[1]), 1.0)

    def _cardinal_tag(cx: float, cy: float) -> str:
        nx = (cx - floor_cx) / (0.5 * floor_dx)
        ny = (cy - floor_cy) / (0.5 * floor_dy)
        if abs(nx) >= abs(ny):
            return "E" if nx >= 0 else "W"
        return "N" if ny >= 0 else "S"

    def _distinct_cardinal_dirs(fids: Sequence[int]) -> int:
        dirs: set[str] = set()
        for f in fids:
            if abs(float(fn[f, 2])) < 0.35:
                nx_f, ny_f = float(fn[f, 0]), float(fn[f, 1])
                if abs(nx_f) >= abs(ny_f):
                    dirs.add("+X" if nx_f >= 0 else "-X")
                else:
                    dirs.add("+Y" if ny_f >= 0 else "-Y")
        return len(dirs)

    for comp in components:
        c_pts = pts[comp]
        cx0, cy0 = float(c_pts[:, :, 0].min()), float(c_pts[:, :, 1].min())
        cx1, cy1 = float(c_pts[:, :, 0].max()), float(c_pts[:, :, 1].max())
        cz0, cz1 = float(c_pts[:, :, 2].min()), float(c_pts[:, :, 2].max())
        dx_m = (cx1 - cx0) * INCH_TO_METRE
        dy_m = (cy1 - cy0) * INCH_TO_METRE
        dz_m = (cz1 - cz0) * INCH_TO_METRE

        # Standalone compact pillar -> Column_XX directly
        if dx_m <= 1.65 and dy_m <= 1.65 and min(dx_m, dy_m) >= 0.20 and dz_m >= 1.2 and _distinct_cardinal_dirs(comp) >= 3:
            col_count += 1
            cname = f"Column_{col_count:02d}" if per_segment else "Columns"
            for f in comp:
                labels[f] = cname
            continue

        # Single solid wall run or coarse mode -> keep whole component together
        if not per_segment or (min(dx_m, dy_m) <= 1.25 and max(dx_m, dy_m) <= 30.0):
            ext_frac = float(is_outside[comp].mean())
            if ext_frac >= 0.25:
                ext_count += 1
                side = _cardinal_tag(0.5 * (cx0 + cx1), 0.5 * (cy0 + cy1))
                wname = f"Wall_Ext_{side}_{ext_count:02d}" if per_segment else "Walls_Exterior"
            else:
                int_count += 1
                wname = f"Wall_Int_{int_count:02d}" if per_segment else "Walls_Interior"
            for f in comp:
                labels[f] = wname
            continue

        # Multi-wall connected network: only extract fused columns that genuinely have >= 3 outward vertical sides
        top_polys = []
        for f in comp:
            if abs(float(fn[f, 2])) > 0.75:
                poly = Polygon(pts[f, :, :2])
                if poly.is_valid and float(poly.area) > 4.0:
                    top_polys.append(poly)
        if not top_polys:
            for f in comp:
                if abs(float(fn[f, 2])) < 0.25:
                    fx0, fy0 = float(pts[f, :, 0].min()), float(pts[f, :, 1].min())
                    fx1, fy1 = float(pts[f, :, 0].max()), float(pts[f, :, 1].max())
                    top_polys.append(shapely_box(fx0 - 4.0, fy0 - 4.0, fx1 + 4.0, fy1 + 4.0))

        fp_union = unary_union(top_polys).buffer(0) if top_polys else Polygon()
        opened = fp_union.buffer(-11.0, join_style=2).buffer(11.0, join_style=2) if not fp_union.is_empty else Polygon()
        boss_geoms = list(opened.geoms) if hasattr(opened, "geoms") else ([opened] if not opened.is_empty else [])

        assigned_cols: set[int] = set()
        for bg in sorted(boss_geoms, key=lambda g: (g.bounds[0], g.bounds[1])):
            bx0, by0, bx1, by1 = bg.bounds
            bdx_m = (bx1 - bx0) * INCH_TO_METRE
            bdy_m = (by1 - by0) * INCH_TO_METRE
            aspect = max(bdx_m, bdy_m) / max(min(bdx_m, bdy_m), 1e-3)
            if not (0.45 <= min(bdx_m, bdy_m) and max(bdx_m, bdy_m) <= 1.85 and aspect <= 2.4):
                continue
            cpoly = bg.buffer(4.0, join_style=2)
            cand_col = [
                f for f in comp
                if f not in assigned_cols and cpoly.contains(shapely.Point(float(cen_xy[f, 0]), float(cen_xy[f, 1])))
            ]
            # Only create a fused column if it has >= 3 vertical sides (never a paper-thin 1-sided sheet!)
            if len(cand_col) >= 8 and _distinct_cardinal_dirs(cand_col) >= 3:
                col_count += 1
                cname = f"Column_{col_count:02d}"
                for f in cand_col:
                    labels[f] = cname
                    assigned_cols.add(f)

        rem_faces = [f for f in comp if f not in assigned_cols]
        if not rem_faces:
            continue

        # Partition remaining connected walls cleanly into Exterior Perimeter vs Interior connected sub-components
        # Keep BOTH faces (outer + inner) of each exterior wall thickness in the same exterior bucket!
        band = 42.0  # ~1.07 m perimeter wall thickness envelope
        ext_seed: set[int] = set()
        for f in rem_faces:
            fx, fy = float(cen_xy[f, 0]), float(cen_xy[f, 1])
            if (
                fx <= float(lo[0]) + band
                or fx >= float(hi[0]) - band
                or fy <= float(lo[1]) + band
                or fy >= float(hi[1]) - band
                or bool(is_outside[f])
            ):
                ext_seed.add(f)

        # Group exterior perimeter faces by cardinal side -> connected components
        ext_by_side: dict[str, list[int]] = defaultdict(list)
        int_faces: list[int] = []
        for f in rem_faces:
            if f in ext_seed:
                fx, fy = float(cen_xy[f, 0]), float(cen_xy[f, 1])
                d_w = fx - float(lo[0])
                d_e = float(hi[0]) - fx
                d_s = fy - float(lo[1])
                d_n = float(hi[1]) - fy
                side_min = min((d_w, "W"), (d_e, "E"), (d_s, "S"), (d_n, "N"), key=lambda t: t[0])[1]
                ext_by_side[side_min].append(f)
            else:
                int_faces.append(f)

        for side in ("N", "S", "E", "W"):
            sfids = ext_by_side.get(side, [])
            if not sfids:
                continue
            subcs = _connected_subcomps(sfids)
            # Keep major connected exterior runs separate; merge tiny trim fragments (<20 tris) into nearest run
            major_ext = [c for c in subcs if len(c) >= 20]
            minor_ext = [c for c in subcs if len(c) < 20]
            if not major_ext:
                major_ext = [sfids]
                minor_ext = []
            if minor_ext:
                maj_cens = [pts[c].reshape(-1, 3).mean(axis=0)[:2] for c in major_ext]
                for mc in minor_ext:
                    mc_cen = pts[mc].reshape(-1, 3).mean(axis=0)[:2]
                    best_k = min(range(len(major_ext)), key=lambda k: float(np.linalg.norm(maj_cens[k] - mc_cen)))
                    major_ext[best_k] = major_ext[best_k] + mc
            for subc in major_ext:
                ext_count += 1
                gname = f"Wall_Ext_{side}_{ext_count:02d}"
                for f in subc:
                    labels[f] = gname

        if int_faces:
            subcs = _connected_subcomps(int_faces)
            major_int = [c for c in subcs if len(c) >= 20]
            minor_int = [c for c in subcs if len(c) < 20]
            if not major_int:
                major_int = [int_faces]
                minor_int = []
            if minor_int:
                maj_cens = [pts[c].reshape(-1, 3).mean(axis=0)[:2] for c in major_int]
                for mc in minor_int:
                    mc_cen = pts[mc].reshape(-1, 3).mean(axis=0)[:2]
                    best_k = min(range(len(major_int)), key=lambda k: float(np.linalg.norm(maj_cens[k] - mc_cen)))
                    major_int[best_k] = major_int[best_k] + mc
            for subc in major_int:
                int_count += 1
                gname = f"Wall_Int_{int_count:02d}"
                for f in subc:
                    labels[f] = gname

    # Final consolidation across disconnected tiny wall scraps (<16 tris) so Outliner stays clean & architectural
    by_lbl: dict[str, list[int]] = defaultdict(list)
    for fi, lbl in enumerate(labels):
        by_lbl[lbl].append(fi)
    major_walls = {
        k: pts[v].reshape(-1, 3).mean(axis=0)[:2]
        for k, v in by_lbl.items()
        if k.startswith("Wall_") and len(v) >= 16
    }
    if major_walls:
        for k, v in list(by_lbl.items()):
            if k.startswith("Wall_") and len(v) < 16:
                vcen = pts[v].reshape(-1, 3).mean(axis=0)[:2]
                same_kind = [mk for mk in major_walls if mk[:8] == k[:8]] or list(major_walls)
                best = min(same_kind, key=lambda mk: float(np.linalg.norm(major_walls[mk] - vcen)))
                for fi in v:
                    labels[fi] = best

    col_count = len({g for g in labels if g.startswith("Column_")})
    ext_count = len({g for g in labels if g.startswith("Wall_Ext_")})
    int_count = len({g for g in labels if g.startswith("Wall_Int_")})

    return labels, local_fz, {
        "dominant_floor_z_in": round(dom_floor_z, 2),
        "columns": col_count,
        "walls_ext": ext_count,
        "walls_int": int_count,
    }


def _triangulate_cap_geom_to_trimesh(
    geom,
    y_level: float,
    mat_name: str,
) -> trimesh.Trimesh | None:
    """Triangulate a 2D Shapely (X, Z) polygon/multipolygon into an upward (+Y) Unity Y-up solid cap Trimesh."""
    if geom is None or geom.is_empty:
        return None
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    verts_list: list[list[float]] = []
    for poly in polys:
        if not isinstance(poly, Polygon) or poly.is_empty or float(poly.area) < 0.015:
            continue
        try:
            cdt = shapely.constrained_delaunay_triangles(poly)
            tris = list(cdt.geoms) if hasattr(cdt, "geoms") else [cdt]
        except Exception:
            continue
        for t in tris:
            if not isinstance(t, Polygon) or t.is_empty or float(t.area) < 1e-4:
                continue
            if not poly.contains(t.representative_point()):
                continue
            coords = list(t.exterior.coords)[:3]
            if len(coords) < 3:
                continue
            p0 = np.array([float(coords[0][0]), y_level, float(coords[0][1])], dtype=np.float64)
            p1 = np.array([float(coords[1][0]), y_level, float(coords[1][1])], dtype=np.float64)
            p2 = np.array([float(coords[2][0]), y_level, float(coords[2][1])], dtype=np.float64)
            # Ensure upward +Y normal: cross(p1 - p0, p2 - p0).y > 0
            cr = np.cross(p1 - p0, p2 - p0)
            if abs(float(cr[1])) < 1e-7:
                continue
            if float(cr[1]) < 0.0:
                p1, p2 = p2, p1
            verts_list.extend([p0.tolist(), p1.tolist(), p2.tolist()])

    if not verts_list:
        return None
    verts = np.asarray(verts_list, dtype=np.float64)
    faces = np.arange(len(verts), dtype=np.int64).reshape(-1, 3)
    uv = np.zeros((len(verts), 2), dtype=np.float64)
    pbr = trimesh.visual.material.PBRMaterial(
        name=mat_name,
        baseColorFactor=[152, 156, 152, 255],
        metallicFactor=0.04,
        roughnessFactor=0.90,
        alphaMode="OPAQUE",
        doubleSided=True,
    )
    return trimesh.Trimesh(
        vertices=verts,
        faces=faces,
        visual=trimesh.visual.TextureVisuals(uv=uv, material=pbr),
        process=False,
    )


def _build_solid_cut_cap_meshes(
    mesh_unity: MeshData,
    face_groups: Sequence[str],
) -> dict[str, trimesh.Trimesh]:
    """Build exact 100%-solid flat horizontal cross-section cap meshes (`CutCap_Ext_N/S/E/W` & `CutCap_Interior`)
    so lowered walls & columns are NEVER hollow and Floor mode shows a crisp solid wall-trace indicator."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize

    if mesh_unity.n_faces == 0:
        return {}

    pts = mesh_unity.positions[mesh_unity.face_v]  # (F, 3, 3) Unity Y-up metres
    v01 = pts[:, 1] - pts[:, 0]
    v02 = pts[:, 2] - pts[:, 0]
    cr = np.cross(v01, v02)
    lens = np.linalg.norm(cr, axis=1)
    ok = lens > 1e-8
    fn = np.zeros_like(cr)
    fn[ok] = cr[ok] / lens[ok, None]
    areas = 0.5 * lens

    # Determine dominant walkable Floor_Slab top elevation Y (metres)
    floor_up_ids = [
        fi for fi, g in enumerate(face_groups)
        if g == "Floor_Slab" and ok[fi] and float(fn[fi, 1]) > 0.75 and float(areas[fi]) > 0.05
    ]
    if floor_up_ids:
        y_vals = pts[floor_up_ids, :, 1].mean(axis=1)
        y_bins: dict[float, float] = defaultdict(float)
        for yv, av in zip(np.round(y_vals, 2).tolist(), areas[floor_up_ids].tolist()):
            y_bins[yv] += av
        y_floor_top = max(y_bins, key=lambda k: y_bins[k])
    else:
        y_floor_top = float(mesh_unity.bbox()[0][1])

    wc_ids = [fi for fi, g in enumerate(face_groups) if g.startswith(("Wall_", "Column_")) and ok[fi]]
    if len(wc_ids) < 4:
        return {}

    wc_arr = np.asarray(wc_ids, dtype=np.int64)
    wc_pts = pts[wc_arr]
    wc_fn = fn[wc_arr]
    y_max_all = float(wc_pts[:, :, 1].max())
    wall_h = y_max_all - y_floor_top
    if wall_h < 0.8:
        return {}

    # 1. Exact 2D wall/column top-cap footprint (`wall_top_union`)
    top_thresh = y_floor_top + max(1.2, wall_h * 0.65)
    top_polys = []
    for k in range(len(wc_arr)):
        if float(wc_fn[k, 1]) > 0.75 and float(wc_pts[k, :, 1].mean()) >= top_thresh:
            p = Polygon([
                (float(wc_pts[k, 0, 0]), float(wc_pts[k, 0, 2])),
                (float(wc_pts[k, 1, 0]), float(wc_pts[k, 1, 2])),
                (float(wc_pts[k, 2, 0]), float(wc_pts[k, 2, 2])),
            ])
            if p.is_valid and float(p.area) > 0.001:
                top_polys.append(p)
    if not top_polys:
        return {}
    wall_top_raw = unary_union(top_polys).buffer(0.015)
    # Strip wide stairwell roof / overhang slabs (>1.80m x 1.80m) so CutCap_* covers ONLY true walls & columns!
    wide_roofs = wall_top_raw.buffer(-0.90, join_style=2).buffer(0.95, join_style=2)
    wall_top_union = wall_top_raw.difference(wide_roofs).buffer(0) if not wide_roofs.is_empty else wall_top_raw
    if wall_top_union.is_empty:
        wall_top_union = wall_top_raw

    # 2. Slice vertical wall/column faces at y_slice (0.75m above floor top, above raised rooms & below window sills)
    y_slice = y_floor_top + min(0.75, wall_h * 0.35)
    segs_2d: list[LineString] = []
    inward_quads: list[Polygon] = []
    for k in range(len(wc_arr)):
        if abs(float(wc_fn[k, 1])) >= 0.30:
            continue
        tri = wc_pts[k]
        ymin_t, ymax_t = float(tri[:, 1].min()), float(tri[:, 1].max())
        if not (ymin_t < y_slice - 0.015 and ymax_t > y_slice + 0.015):
            continue
        n2 = np.array([float(wc_fn[k, 0]), float(wc_fn[k, 2])], dtype=np.float64)
        nl = float(np.linalg.norm(n2))
        if nl < 0.5:
            continue
        n2 /= nl
        hits = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            ya, yb = float(tri[a, 1]), float(tri[b, 1])
            if (ya <= y_slice < yb) or (yb <= y_slice < ya):
                t = (y_slice - ya) / (yb - ya)
                p = tri[a] + t * (tri[b] - tri[a])
                hits.append((float(p[0]), float(p[2])))
        if len(hits) != 2:
            continue
        (x0s, z0s), (x1s, z1s) = hits
        if float(np.hypot(x1s - x0s, z1s - z0s)) <= 0.01:
            continue
        p0_r = (round(x0s, 2), round(z0s, 2))
        p1_r = (round(x1s, 2), round(z1s, 2))
        if p0_r != p1_r:
            segs_2d.append(LineString([p0_r, p1_r]))
        # Extrude inward along -outward_normal (clipped strictly to wall_top_union so doorways stay 100% open!)
        d_in = 0.85
        q = Polygon([
            (x0s, z0s),
            (x1s, z1s),
            (x1s - n2[0] * d_in, z1s - n2[1] * d_in),
            (x0s - n2[0] * d_in, z0s - n2[1] * d_in),
        ])
        if q.is_valid and float(q.area) > 0.002:
            inward_quads.append(q)

    closed_polys = []
    if segs_2d:
        for p in polygonize(unary_union(segs_2d)):
            if float(p.area) >= 0.01 and (float(p.intersection(wall_top_union).area) / max(float(p.area), 1e-6)) > 0.45:
                closed_polys.append(p)

    inward_u = unary_union(inward_quads).buffer(0).intersection(wall_top_union) if inward_quads else Polygon()
    cap_all = unary_union(closed_polys + ([inward_u] if not inward_u.is_empty else []))
    if cap_all.is_empty:
        return {}
    cap_all = cap_all.buffer(0.015, join_style=2).buffer(-0.015, join_style=2)
    cap_parts = list(cap_all.geoms) if hasattr(cap_all, "geoms") else [cap_all]
    cap_all = unary_union([p for p in cap_parts if isinstance(p, Polygon) and float(p.area) >= 0.02])
    if cap_all.is_empty:
        return {}

    # 3. Partition solid cap polygon cleanly into CutCap_Ext_W/E/S/N and CutCap_Interior
    # Note: In Unity GLB (+Z), Z is mirrored vs Three.js (-Z), so map by exact Wall_Ext_<side>_* face footprints!
    side_polys: dict[str, list[Polygon]] = {s: [] for s in ("W", "E", "S", "N")}
    for k, fi in enumerate(wc_arr.tolist()):
        g = face_groups[fi]
        if g.startswith("Wall_Ext_"):
            parts_g = g.split("_")
            if len(parts_g) >= 3 and parts_g[2] in side_polys:
                x0f, x1f = float(wc_pts[k, :, 0].min()), float(wc_pts[k, :, 0].max())
                z0f, z1f = float(wc_pts[k, :, 2].min()), float(wc_pts[k, :, 2].max())
                side_polys[parts_g[2]].append(shapely_box(x0f - 0.12, z0f - 0.12, x1f + 0.12, z1f + 0.12))

    out_caps: dict[str, trimesh.Trimesh] = {}
    remaining = cap_all
    for side in ("W", "E", "S", "N"):
        if not side_polys[side] or remaining.is_empty:
            continue
        side_fp = unary_union(side_polys[side]).buffer(0)
        piece = remaining.intersection(side_fp).buffer(0)
        if not piece.is_empty and float(piece.area) >= 0.02:
            tm = _triangulate_cap_geom_to_trimesh(piece, y_floor_top, f"mat_cutcap_ext_{side.lower()}")
            if tm is not None:
                out_caps[f"CutCap_Ext_{side}"] = tm
            remaining = remaining.difference(piece).buffer(0)

    if not remaining.is_empty and float(remaining.area) >= 0.02:
        tm = _triangulate_cap_geom_to_trimesh(remaining, y_floor_top, "mat_cutcap_interior")
        if tm is not None:
            out_caps["CutCap_Interior"] = tm

    return out_caps


def export_grouped_glb(
    mesh_unity: MeshData,
    face_groups: Sequence[str],
    mtl_path: Path,
    out_glb_path: Path,
) -> Path:
    """Export a multi-node textured `.glb` via `trimesh.Scene` with one named node per semantic group."""
    mtl_dict = parse_mtl(mtl_path) if mtl_path and mtl_path.is_file() else {}
    tex_cache: dict[str, Image.Image] = {}
    scene = trimesh.Scene()

    by_group: dict[str, list[int]] = defaultdict(list)
    for fi, gname in enumerate(face_groups):
        by_group[str(gname)].append(fi)

    has_uvs = mesh_unity.uvs is not None and len(mesh_unity.uvs) > 0 and mesh_unity.face_vt is not None

    for gname in sorted(by_group):
        fids = by_group[gname]
        # Group within each semantic node by material if multiple materials exist; if 1 material keep exact node name
        by_mat: dict[int, list[int]] = defaultdict(list)
        for fi in fids:
            by_mat[int(mesh_unity.face_material[fi])].append(fi)

        single_mat = len(by_mat) == 1
        for m_idx, mfids in sorted(by_mat.items()):
            f_arr = np.asarray(mfids, dtype=np.int64)
            # Unroll per-corner vertices so UV seams stay exact in GLB
            fv = mesh_unity.face_v[f_arr]
            verts = mesh_unity.positions[fv].reshape(-1, 3)
            faces = np.arange(len(verts), dtype=np.int64).reshape(-1, 3)

            mname = mesh_unity.materials[m_idx] if 0 <= m_idx < len(mesh_unity.materials) else "default"
            mtl_entry = mtl_dict.get(mname)
            tex_img = None
            if mtl_entry and mtl_entry.map_kd:
                tex_rel = mtl_entry.map_kd.split()[-1]
                tex_p = (mtl_path.parent / tex_rel).resolve()
                if tex_p.is_file():
                    key = str(tex_p)
                    if key not in tex_cache:
                        tex_cache[key] = Image.open(tex_p).convert("RGBA")
                    tex_img = tex_cache[key]

            rgba = [220, 218, 210, 255]
            if mtl_entry and mtl_entry.lines:
                kd_vals: list[float] | None = None
                alpha_val = 1.0
                for ml in mtl_entry.lines:
                    parts = ml.split()
                    if len(parts) >= 4 and parts[0] == "Kd":
                        try:
                            kd_vals = [float(parts[1]), float(parts[2]), float(parts[3])]
                        except ValueError:
                            pass
                    elif len(parts) >= 2 and parts[0] == "d":
                        try:
                            alpha_val = float(parts[1])
                        except ValueError:
                            pass
                if kd_vals is not None:
                    rgba = [
                        int(round(max(0.0, min(1.0, kd_vals[0])) * 255)),
                        int(round(max(0.0, min(1.0, kd_vals[1])) * 255)),
                        int(round(max(0.0, min(1.0, kd_vals[2])) * 255)),
                        int(round(max(0.0, min(1.0, alpha_val)) * 255)),
                    ]
                else:
                    rgba[3] = int(round(max(0.0, min(1.0, alpha_val)) * 255))

            if has_uvs:
                fvt = mesh_unity.face_vt[f_arr].reshape(-1)
                uv = np.zeros((len(verts), 2), dtype=np.float64)
                valid_vt = (fvt >= 0) & (fvt < len(mesh_unity.uvs))
                uv[valid_vt] = mesh_unity.uvs[fvt[valid_vt]]
            else:
                uv = np.zeros((len(verts), 2), dtype=np.float64)

            pbr = trimesh.visual.material.PBRMaterial(
                name=mname,
                baseColorFactor=rgba,
                baseColorTexture=tex_img,
                metallicFactor=0.05,
                roughnessFactor=0.85,
                alphaMode="BLEND" if rgba[3] < 250 else "OPAQUE",
                doubleSided=False,
            )
            visual = trimesh.visual.TextureVisuals(uv=uv, material=pbr)
            tm = trimesh.Trimesh(vertices=verts, faces=faces, visual=visual, process=False)

            geom_name = gname if single_mat else f"{gname}__{mname}"
            if single_mat:
                scene.add_geometry(tm, node_name=gname, geom_name=geom_name)
            else:
                if gname not in scene.graph.nodes:
                    scene.graph.update(frame_to=gname, frame_from=scene.graph.base_frame)
                scene.add_geometry(tm, node_name=geom_name, geom_name=geom_name, parent_node_name=gname)

    # Embed solid flat cutaway section caps (`CutCap_Ext_W/E/S/N`, `CutCap_Interior`) for zero-hollow cutaway & Floor trace
    for cap_name, cap_tm in _build_solid_cut_cap_meshes(mesh_unity, face_groups).items():
        scene.add_geometry(cap_tm, node_name=cap_name, geom_name=cap_name)

    out_glb_path.parent.mkdir(parents=True, exist_ok=True)
    out_glb_path.write_bytes(scene.export(file_type="glb"))
    return out_glb_path


def _raycast_iso_panel(
    positions: np.ndarray,
    face_v: np.ndarray,
    face_colors: np.ndarray,
    *,
    width: int = 720,
    height: int = 520,
    view_dir: tuple[float, float, float] = (-0.65, -0.65, -0.58),
    title: str = "",
) -> Image.Image:
    """Fast Embree isometric shaded render for visual before/after cutaway QA."""
    img = Image.new("RGB", (width, height), (10, 24, 18))
    if len(face_v) == 0:
        draw = ImageDraw.Draw(img)
        draw.text((14, 12), f"{title} (empty)", fill=(235, 245, 240))
        return img

    pts_all = positions[face_v].reshape(-1, 3)
    lo, hi = pts_all.min(axis=0), pts_all.max(axis=0)
    center = 0.5 * (lo + hi)
    pos_c = positions - center

    vdir = np.asarray(view_dir, dtype=np.float64)
    vdir /= np.linalg.norm(vdir)
    up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    right = np.cross(vdir, up)
    right /= np.linalg.norm(right)
    cam_up = np.cross(right, vdir)
    cam_up /= np.linalg.norm(cam_up)

    # Project all 8 bbox corners onto (right, cam_up) to fit cleanly
    corners = np.array(
        [[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])],
        dtype=np.float64,
    ) - center
    cu = corners @ right
    cv = corners @ cam_up
    span_u = max(float(cu.max() - cu.min()), 1.0) * 1.12
    span_v = max(float(cv.max() - cv.min()), 1.0) * 1.12
    scale = max(span_u / width, span_v / height)

    xs = (np.arange(width) - 0.5 * width) * scale + 0.5 * (cu.min() + cu.max())
    ys = (0.5 * height - np.arange(height)) * scale + 0.5 * (cv.min() + cv.max())
    uu, vv = np.meshgrid(xs, ys)
    dist_back = float(np.linalg.norm(hi - lo)) * 1.5
    origins = (
        uu.reshape(-1, 1) * right[None, :]
        + vv.reshape(-1, 1) * cam_up[None, :]
        - dist_back * vdir[None, :]
    )
    dirs = np.broadcast_to(vdir[None, :], origins.shape).copy()

    caster = EmbreeCaster(pos_c, face_v)
    hits, _ = caster.first_hit(origins, dirs)

    fn = face_normals(pos_c, face_v, np.ones(len(face_v), dtype=bool))
    light_dir = np.array([0.45, 0.35, 0.82], dtype=np.float64)
    light_dir /= np.linalg.norm(light_dir)

    buf = np.full((height * width, 3), [10, 24, 18], dtype=np.uint8)
    valid = hits >= 0
    if valid.any():
        hf = hits[valid]
        ndotl = np.abs(fn[hf] @ light_dir)
        shade = 0.38 + 0.62 * np.clip(ndotl, 0.0, 1.0)
        cols = np.clip(face_colors[hf] * shade[:, None], 0.0, 255.0).astype(np.uint8)
        buf[valid] = cols

    img = Image.fromarray(buf.reshape(height, width, 3), mode="RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, 30], fill=(6, 16, 12))
    draw.text((12, 8), title, fill=(230, 248, 238))
    return img


def render_cutaway_qa_sheet(
    before_mesh: MeshData,
    after_mesh: MeshData,
    face_groups: Sequence[str],
    out_png: Path,
    *,
    cut_height_m: float = 1.10,
) -> Path:
    """Render a 2x2 visual QA sheet: BEFORE Raw | AFTER Full Grouped | AFTER 1.1m Cutaway | AFTER Walls Hidden."""
    def _group_color(gname: str) -> tuple[int, int, int]:
        if gname == "Floor_Slab":
            return (214, 206, 186)
        if gname.startswith("Column_"):
            return (235, 178, 52)   # UC Gold for G02 structural columns
        if gname.startswith("Wall_Ext_"):
            return (92, 184, 134)   # UC Emerald for exterior walls
        if gname.startswith("Wall_Int_"):
            return (130, 214, 198)  # Mint teal for interior partitions
        if gname == "OverheadBeams_And_Lintels":
            return (196, 98, 92)    # Terracotta red for overhead beams/lintels
        if gname == "Stairs":
            return (124, 152, 214)  # Slate blue for stairs
        if gname == "Glass_Openings":
            return (155, 224, 245)  # Ice cyan for glass
        return (180, 180, 180)

    b_cols = np.full((before_mesh.n_faces, 3), [185, 185, 180], dtype=np.float64)
    a_cols = np.array([_group_color(g) for g in face_groups], dtype=np.float64)

    p1 = _raycast_iso_panel(
        before_mesh.positions,
        before_mesh.face_v,
        b_cols,
        title=f"1. BEFORE Raw ({before_mesh.n_faces:,} tris)",
    )
    p2 = _raycast_iso_panel(
        after_mesh.positions,
        after_mesh.face_v,
        a_cols,
        title=f"2. AFTER Solid Grouped ({after_mesh.n_faces:,} tris · Gold=Cols · Red=Beams)",
    )

    # Panel 3: Simulated 1.10m Half-Wall Cutaway (OverheadBeams hidden, wall faces above cut plane hidden)
    dom_fz, z_grid, grid_meta = _compute_local_floor_z_map(after_mesh)
    pts_a = after_mesh.positions[after_mesh.face_v]
    local_fz = _lookup_local_floor_z(pts_a[:, :, :2].mean(axis=1), z_grid, grid_meta)
    z_cut = local_fz + cut_height_m * METRE_TO_INCH
    keep_cut = np.array(
        [
            (face_groups[f] != "OverheadBeams_And_Lintels")
            and (
                (not face_groups[f].startswith("Wall_"))
                or (float(pts_a[f, :, 2].max()) <= float(z_cut[f]) + 0.35)
            )
            for f in range(after_mesh.n_faces)
        ],
        dtype=bool,
    )
    p3 = _raycast_iso_panel(
        after_mesh.positions,
        after_mesh.face_v[keep_cut],
        a_cols[keep_cut],
        title=f"3. Cutaway {cut_height_m:.2f}m (Beams Hidden · Zero Diagonal Tearing)",
    )

    # Panel 4: Walls Hidden (Floor_Slab + Columns + Stairs only)
    keep_nowall = np.array(
        [
            face_groups[f] in ("Floor_Slab", "Stairs") or face_groups[f].startswith("Column_")
            for f in range(after_mesh.n_faces)
        ],
        dtype=bool,
    )
    p4 = _raycast_iso_panel(
        after_mesh.positions,
        after_mesh.face_v[keep_nowall],
        a_cols[keep_nowall],
        title="4. Walls Hidden (Floor_Slab + Solid G02 Columns + Stairs)",
    )

    sheet = Image.new("RGB", (p1.width * 2, p1.height * 2), (6, 16, 12))
    sheet.paste(p1, (0, 0))
    sheet.paste(p2, (p1.width, 0))
    sheet.paste(p3, (0, p1.height))
    sheet.paste(p4, (p1.width, p1.height))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_png)
    return out_png


def build_solid_wall_column_groups(
    mesh: MeshData,
    mtl_path: Path,
    *,
    cut_height_m: float = 1.10,
    per_segment: bool = True,
    run_core_repair: bool = True,
    enabled_stages: Iterable[str] | None = None,
) -> SolidWallGroupResult:
    """Run the full hardened solid wall & column grouping pipeline on a floor mesh."""
    mesh_ckpt_in = _to_ckpt17_mesh(mesh)
    audit_before = audit_wall_column_health(mesh_ckpt_in)

    stage_stats: dict = {}
    if run_core_repair:
        repaired, _rings, core_stats = repair_building_floor_mesh(
            mesh_ckpt_in,
            mtl_path,
            enabled_stages=enabled_stages,
        )
        stage_stats["core_repair"] = {
            k: v for k, v in core_stats.items() if k not in ("diff_overlay",)
        }
        repaired, cap_stats = cap_visible_planar_holes(mesh_ckpt_in, repaired, visible_only=True)
        stage_stats["cap_visible_holes"] = cap_stats
    else:
        repaired = copy.deepcopy(mesh_ckpt_in)

    # Purge trapped internal cavity ribs (D11/D15 -> G01), iterative up to 3 passes
    repaired, n_cavity_purged = _purge_trapped_cavity_faces(repaired, max_passes=3)
    stage_stats["trapped_cavity_purged"] = n_cavity_purged

    # Resolve near-coplanar Z-fighting pairs (0.01-0.25 in) — strictly post-merge (No-Merge-Last Law)
    repaired, zfight_stats = resolve_near_coplanar_zfight(repaired, min_dist_in=0.01, max_dist_in=0.25)
    stage_stats["near_coplanar_zfight"] = zfight_stats

    # Cross-plane T-junction stitching (zero vertex drift)
    repaired, stitch_stats = stitch_cross_plane_tjunctions(repaired, search_tol_in=0.05)
    stage_stats["tjunction_stitch"] = stitch_stats

    # Pre-grouping exact dedup & coplanar overlap cleanup (No-Merge-Last Law)
    repaired, _, n_pre_dedup = _dedup_exact_triangles(repaired)
    repaired, n_final_ovl = remove_coplanar_overlaps(repaired, overlap_ratio=0.05, drop_only=True)
    stage_stats["pre_group_dedup"] = n_pre_dedup
    stage_stats["final_coplanar_dropped"] = n_final_ovl

    # Slice exterior/perimeter vertical walls cleanly along local floor top plane (z = local_fz)
    # so the 0..1m floor slab skirt stays intact in Floor_Slab when walls are hidden!
    _, pre_z_grid, pre_grid_meta = _compute_local_floor_z_map(repaired)
    pre_pts = repaired.positions[repaired.face_v]
    pre_local_fz = _lookup_local_floor_z(pre_pts[:, :, :2].mean(axis=1), pre_z_grid, pre_grid_meta)
    repaired, _, n_floor_sliced = _slice_mesh_by_z_plane(
        repaired,
        None,
        pre_local_fz,
        target_prefixes=None,
        tol=0.50,
    )
    stage_stats["floor_plane_sliced_tris"] = n_floor_sliced

    # Semantic classification & grouping
    face_groups, local_fz, cls_meta = _classify_and_group_faces(repaired, per_segment=per_segment)
    stage_stats["classification"] = cls_meta

    # Optional clean horizontal cutaway edge loop at cut_height_m above local floor
    if cut_height_m > 0.0:
        z_cut_arr = local_fz + cut_height_m * METRE_TO_INCH
        repaired, face_groups, n_sliced = _slice_mesh_by_z_plane(repaired, face_groups, z_cut_arr)
        stage_stats["cut_plane_sliced_tris"] = n_sliced
    else:
        stage_stats["cut_plane_sliced_tris"] = 0

    # Seal genuine global open planar loops on standalone solid wall/column groups & enforce positive signed volume
    repaired, face_groups, seal_stats = _seal_group_planar_caps_and_orient(repaired, face_groups)
    stage_stats["solid_sealing"] = seal_stats

    # Post-slice/post-seal strict hygiene: exact dedup -> exact flicker drop -> 128-dir outward orientation
    repaired, face_groups_opt, n_post_dedup = _dedup_exact_triangles(repaired, face_groups)
    assert face_groups_opt is not None
    face_groups = face_groups_opt
    repaired, face_groups, n_post_flk = _resolve_flicker_pairs_with_groups(repaired, face_groups, max_passes=3)
    repaired, n_oriented = _orient_strictly_outward(repaired, n_dirs=128, max_passes=3)
    stage_stats["post_seal_dedup"] = n_post_dedup
    stage_stats["post_seal_flicker_dropped"] = n_post_flk
    stage_stats["oriented_flipped"] = n_oriented

    repaired, _ = compact_mesh(repaired, {})
    repaired.units = "inches"
    mesh_unity = _to_unity_mesh(repaired)

    # Sync any remaining reversed normals using the exact same welded topology & FixProfile ray set
    # as `run_unity_preflight_gate` / `find_errors` so BOTH Unity Y-up and CKPT-17 achieve reversed == 0!
    from engine.fixes.pipeline import FixProfile
    from engine.pipeline import analyse_topology

    prof = FixProfile(guard_size=(256, 256), n_dirs=64)
    unity_synced_total = 0
    for _ in range(3):
        topo_u = analyse_topology(mesh_unity, frozenset(), coplanar_angle=prof.coplanar_angle, soft_angle=prof.soft_angle)
        if not topo_u.ok.any():
            break
        cen_u = 0.5 * (topo_u.positions_w.min(axis=0) + topo_u.positions_w.max(axis=0))
        ef_u, eb_u = compute_side_exposure(topo_u.positions_w - cen_u, topo_u.face_w, topo_u.ok, n_dirs=prof.n_dirs)
        flip_u = (classify_orientation(ef_u, eb_u, topo_u.ok) == ORIENT_FLIP) & topo_u.ok
        n_fu = int(flip_u.sum())
        if n_fu == 0:
            break
        mesh_unity = flip_faces(mesh_unity, flip_u)
        repaired = flip_faces(repaired, flip_u)
        unity_synced_total += n_fu
    if unity_synced_total:
        stage_stats["unity_oriented_synced"] = unity_synced_total

    audit_after = audit_wall_column_health(repaired, face_groups=face_groups)
    preflight_unity = run_unity_preflight_gate(mesh_unity, expected_units="metres", min_alt_mm=2.0)

    # Assemble rich manifest for Three.js / Unity / Blender consumers
    lo_u, hi_u = mesh_unity.bbox()
    origin_world = {
        "x": round(0.5 * float(lo_u[0] + hi_u[0]), 4),
        "y": round(float(lo_u[1]), 4),
        "z": round(0.5 * float(lo_u[2] + hi_u[2]), 4),
    }
    groups_manifest: dict[str, dict] = {}
    by_g: dict[str, list[int]] = defaultdict(list)
    for fi, g in enumerate(face_groups):
        by_g[g].append(fi)
    for gname in sorted(by_g):
        f_arr = np.asarray(by_g[gname], dtype=np.int64)
        u_pts = mesh_unity.positions[mesh_unity.face_v[f_arr]].reshape(-1, 3)
        u_lo, u_hi = u_pts.min(axis=0), u_pts.max(axis=0)
        solid_info = audit_after["per_group_solids"].get(gname, {})
        cat = (
            "column" if gname.startswith("Column_")
            else "wall_exterior" if gname.startswith("Wall_Ext_")
            else "wall_interior" if gname.startswith("Wall_Int_")
            else "overhead" if gname == "OverheadBeams_And_Lintels"
            else "floor" if gname == "Floor_Slab"
            else "stairs" if gname == "Stairs"
            else "glass" if gname == "Glass_Openings"
            else "other"
        )
        groups_manifest[gname] = {
            "category": cat,
            "tris": int(len(f_arr)),
            "open_edges": int(solid_info.get("open_edges", 0)),
            "nonmanifold_edges": int(solid_info.get("nonmanifold_edges", 0)),
            "signed_volume": float(solid_info.get("signed_volume", 0.0)),
            "watertight": bool(solid_info.get("watertight", False)),
            "bbox_unity_min": [round(float(v), 4) for v in u_lo],
            "bbox_unity_max": [round(float(v), 4) for v in u_hi],
            "centroid_unity": [round(float(v), 4) for v in (0.5 * (u_lo + u_hi))],
        }

    manifest = {
        "name": repaired.name,
        "cut_height_m": cut_height_m,
        "per_segment": per_segment,
        "origin_world_unity": origin_world,
        "bbox_unity_min": [round(float(v), 4) for v in lo_u],
        "bbox_unity_max": [round(float(v), 4) for v in hi_u],
        "group_count": len(groups_manifest),
        "groups": groups_manifest,
    }

    return SolidWallGroupResult(
        mesh_ckpt17=repaired,
        mesh_unity=mesh_unity,
        face_groups=face_groups,
        manifest=manifest,
        audit_before=audit_before,
        audit_after=audit_after,
        preflight_unity=preflight_unity,
        stage_stats=stage_stats,
    )
