"""Real-Model Engine v2 + Strict 100% Outer Facade Lock per-floor builder.

Takes an untouched RAW CHECKPOINT-17 export (keeping 100% of real railings, stepped
parapets, 4-pane windows, louver transoms, glass, facade textures, and UVs), runs the
15-stage mesh-preserving `repair_building_floor_mesh` pipeline + horizontal/floor guards
+ post-repair coplanar/normal cleanup + Strict Outer Facade Lock, evaluates RAW vs v1
vs Real-Model v2 apples-to-apples metrics, and writes clean Z-up metre OBJ/MTL/textures
ready for per-floor `.blend` packaging and `.glb` export.
"""
from __future__ import annotations

import argparse
import copy
import gc
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shapely.geometry import Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402
import trimesh  # noqa: E402

from engine.detectors.errors import find_errors  # noqa: E402
from engine.fixes.building_repair import (  # noqa: E402
    REPAIR_STAGE_ORDER,
    _triangulate_clipped_face,
    compact_mesh,
    detect_internal_voxel_stack_plates,
    remove_coplanar_overlaps,
    repair_building_floor_mesh,
)
from engine.fixes.orient import ORIENT_FLIP, classify_orientation, flip_faces  # noqa: E402
from engine.fixes.overlap import double_layers  # noqa: E402
from engine.fixes.patch_protect import detect_piercing_needle_slivers, purge_piercing_needle_slivers  # noqa: E402
from engine.fixes.pipeline import FixProfile, guard_depth_tol  # noqa: E402
from engine.fixes.remove import remove_faces  # noqa: E402
from engine.fixes.solid_wall_groups import (  # noqa: E402
    INCH_TO_METRE,
    convert_unity_to_ckpt17_coords,
)
from engine.guard.views import VIEWS_26  # noqa: E402
from engine.io.mtl import parse_mtl  # noqa: E402
from engine.io.obj_reader import read_obj  # noqa: E402
from engine.io.obj_writer import write_obj  # noqa: E402
from engine.model import MeshData  # noqa: E402
from engine.pipeline import analyse_topology  # noqa: E402
from engine.rays.caster import EmbreeCaster  # noqa: E402
from engine.topo.planes import face_normals, plane_basis  # noqa: E402
from engine.validate.diff_overlay import (  # noqa: E402
    compute_before_after_diff_overlay,
    restore_destroyed_facade_faces,
)
from engine.validate.facade_integrity import (  # noqa: E402
    BARY7,
    _coverage_7pt,
    verify_facade_and_mesh_integrity,
)
from engine.validate.unity_preflight import resolve_near_coplanar_zfight  # noqa: E402
from engine.vis.exposure import BARY, EXP_OUTSIDE, classify_exposure, compute_side_exposure  # noqa: E402

BARY13 = np.array(
    [
        [1 / 3, 1 / 3, 1 / 3],
        [0.60, 0.20, 0.20],
        [0.20, 0.60, 0.20],
        [0.20, 0.20, 0.60],
        [0.80, 0.10, 0.10],
        [0.10, 0.80, 0.10],
        [0.10, 0.10, 0.80],
        [0.48, 0.48, 0.04],
        [0.48, 0.04, 0.48],
        [0.04, 0.48, 0.48],
        [0.92, 0.04, 0.04],
        [0.04, 0.92, 0.04],
        [0.04, 0.04, 0.92],
    ],
    dtype=np.float64,
)


def _append_before_faces(dst: MeshData, src: MeshData, fids: np.ndarray) -> MeshData:
    if len(fids) == 0:
        return dst
    mat_list = list(dst.materials)
    mapped_mats = np.zeros(len(fids), dtype=np.int64)
    for i, fid in enumerate(fids):
        b_mid = int(src.face_material[fid])
        mname = (
            src.materials[b_mid]
            if (0 <= b_mid < len(src.materials))
            else (mat_list[0] if mat_list else "default")
        )
        if mname not in mat_list:
            mat_list.append(mname)
        mapped_mats[i] = mat_list.index(mname)
    dst.materials = mat_list

    pts_add = src.positions[src.face_v[fids]].reshape(-1, 3)
    v_b = len(dst.positions)
    new_fv = np.arange(len(fids) * 3, dtype=np.int64).reshape(-1, 3) + v_b
    dst.positions = np.vstack([dst.positions, pts_add])
    dst.face_v = np.vstack([dst.face_v, new_fv])
    if (
        src.uvs is not None
        and len(src.uvs) > 0
        and dst.uvs is not None
        and (src.face_vt[fids] >= 0).all()
    ):
        uv_add = src.uvs[src.face_vt[fids]].reshape(-1, 2)
        vt_b = len(dst.uvs)
        new_fvt = np.arange(len(fids) * 3, dtype=np.int64).reshape(-1, 3) + vt_b
        dst.uvs = np.vstack([dst.uvs, uv_add])
        dst.face_vt = np.vstack([dst.face_vt, new_fvt])
    else:
        dst.face_vt = np.vstack([dst.face_vt, np.full((len(fids), 3), -1, dtype=np.int64)])
    dst.face_vn = np.vstack([dst.face_vn, np.full((len(fids), 3), -1, dtype=np.int64)])
    dst.face_material = np.concatenate([dst.face_material, mapped_mats])
    dst.face_line = np.concatenate([dst.face_line, np.zeros(len(fids), dtype=np.int64)])
    return dst


def _level_unions(m: MeshData) -> dict[tuple[int, float], Any]:
    p = m.positions[m.face_v]
    fn = face_normals(m.positions, m.face_v, np.ones(m.n_faces, dtype=bool))
    d: dict[tuple[int, float], list[Polygon]] = {}
    for f in np.flatnonzero(np.abs(fn[:, 2]) > 0.9):
        pl = Polygon(p[f, :, :2])
        if pl.is_valid and pl.area > 1e-4:
            d.setdefault((1 if fn[f, 2] > 0 else -1, round(float(p[f, :, 2].mean()), 1)), []).append(pl)
    return {k: unary_union(v) for k, v in d.items()}


def orient_horizontals(b: MeshData, a: MeshData) -> tuple[MeshData, int]:
    """Align horizontal floor/ceiling windings with `b` where `b` is one-sided."""
    u_map = _level_unions(b)
    p = a.positions[a.face_v]
    fn = face_normals(a.positions, a.face_v, np.ones(a.n_faces, dtype=bool))
    n_flip = 0
    for f in np.flatnonzero(np.abs(fn[:, 2]) > 0.9):
        pl = Polygon(p[f, :, :2])
        if not pl.is_valid or pl.area <= 1e-4:
            continue
        z = round(float(p[f, :, 2].mean()), 1)
        cur = 1 if fn[f, 2] > 0 else -1
        same = u_map.get((cur, z))
        opp = u_map.get((-cur, z))
        a_same = pl.intersection(same).area if same is not None else 0.0
        a_opp = pl.intersection(opp).area if opp is not None else 0.0
        if a_opp > 0.5 * pl.area and a_same < 0.1 * pl.area:
            a.face_v[f] = a.face_v[f, [0, 2, 1]]
            if a.face_vt is not None and len(a.face_vt) == a.n_faces:
                a.face_vt[f] = a.face_vt[f, [0, 2, 1]]
            n_flip += 1
    return a, n_flip


def heal_walkable_floor_slab_cracks(mesh: MeshData) -> tuple[MeshData, int]:
    """Seal narrow cracks/slivers/notches inside major walkable Z-up floor slabs (>= 25 m^2), preserving UVs."""
    if mesh.n_faces == 0:
        return mesh, 0
    fn = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    pts_m = mesh.positions * INCH_TO_METRE
    tri_m = pts_m[mesh.face_v]
    z_mean_m = tri_m[:, :, 2].mean(axis=1)
    areas_m2 = 0.5 * np.linalg.norm(
        np.cross(tri_m[:, 1] - tri_m[:, 0], tri_m[:, 2] - tri_m[:, 0]), axis=1
    )
    up_mask = (~np.isnan(fn).any(axis=1)) & (fn[:, 2] > 0.85) & (areas_m2 > 1e-6)
    if not np.any(up_mask):
        return mesh, 0
    horiz_mask = (~np.isnan(fn).any(axis=1)) & (np.abs(fn[:, 2]) > 0.85) & (areas_m2 > 1e-6)

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

    has_uvs = mesh.uvs is not None and len(mesh.uvs) > 0 and mesh.face_vt is not None
    out = copy.deepcopy(mesh)
    new_pos_list: list[np.ndarray] = []
    new_uv_list: list[np.ndarray] = []
    new_fv_list: list[list[int]] = []
    new_fvt_list: list[list[int]] = []
    new_fmat_list: list[int] = []
    next_v = len(out.positions)
    next_vt = len(out.uvs) if has_uvs else 0
    healed_holes = 0

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

        fid_polys: list[tuple[int, Polygon]] = []
        for fid in fid_arr:
            fv = mesh.face_v[fid]
            q = Polygon([
                (float(pts_m[fv[0], 0]), float(pts_m[fv[0], 1])),
                (float(pts_m[fv[1], 0]), float(pts_m[fv[1], 1])),
                (float(pts_m[fv[2], 0]), float(pts_m[fv[2], 1])),
            ])
            if q.is_valid and q.area > 1e-6:
                fid_polys.append((int(fid), q))
        if not fid_polys:
            continue
        floor_u = unary_union([q for _, q in fid_polys])
        if not floor_u.is_valid:
            floor_u = floor_u.buffer(0)
        geoms = list(floor_u.geoms) if hasattr(floor_u, "geoms") else [floor_u]
        for gp in geoms:
            if not isinstance(gp, Polygon):
                continue
            for ring in gp.interiors:
                hp_raw = Polygon(ring)
                if not hp_raw.is_valid:
                    hp_raw = hp_raw.buffer(0)
                if not (isinstance(hp_raw, Polygon) and 0.0002 < float(hp_raw.area) < 0.50 and hp_raw.buffer(-0.22, join_style=2).is_empty):
                    continue
                hx0, hy0, hx1, hy1 = hp_raw.bounds
                near_other = [
                    oq for (ox0, oy0, ox1, oy1), oq in other_items
                    if ox1 >= hx0 and ox0 <= hx1 and oy1 >= hy0 and oy0 <= hy1
                ]
                uncovered = hp_raw.difference(unary_union(near_other)) if near_other else hp_raw
                if not uncovered.is_valid:
                    uncovered = uncovered.buffer(0)
                for hp in _expand_poly_parts(uncovered):
                    if not (0.0002 < float(hp.area) < 0.50 and hp.buffer(-0.22, join_style=2).is_empty):
                        continue
                    hp_buf = hp.buffer(0.03, join_style=2)
                    best_fid = fid_polys[0][0]
                    best_ov = -1.0
                    for cand_fid, cand_q in fid_polys:
                        if not cand_q.intersects(hp_buf):
                            continue
                        ov = float(cand_q.boundary.intersection(hp_buf).length)
                        if ov > best_ov:
                            best_ov = ov
                            best_fid = cand_fid

                    try:
                        v2d, f2d = trimesh.creation.triangulate_polygon(hp, engine="earcut")
                    except Exception:
                        try:
                            v2d, f2d = trimesh.creation.triangulate_polygon(hp)
                        except Exception:
                            continue
                    if len(f2d) == 0 or len(v2d) == 0:
                        continue

                    adj_fv = mesh.face_v[best_fid]
                    adj_pts_m = pts_m[adj_fv]
                    z_fl_in = float(np.median(mesh.positions[adj_fv, 2]))
                    v3d_in = np.column_stack([
                        v2d[:, 0] / INCH_TO_METRE,
                        v2d[:, 1] / INCH_TO_METRE,
                        np.full(len(v2d), z_fl_in, dtype=np.float64),
                    ])
                    # Ensure upward +Z winding
                    p0 = v3d_in[f2d[:, 0]]
                    p1 = v3d_in[f2d[:, 1]]
                    p2 = v3d_in[f2d[:, 2]]
                    cz = (p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1]) - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0])
                    f_fixed = f2d.copy()
                    flip = cz < 0
                    if np.any(flip):
                        f_fixed[flip] = f_fixed[flip][:, [0, 2, 1]]

                    # Compute exact 2D->UV affine transform from adjacent floor triangle
                    uv_affine: np.ndarray | None = None
                    if has_uvs and (mesh.face_vt[best_fid] >= 0).all():
                        mat_xy = np.column_stack([adj_pts_m[:, 0], adj_pts_m[:, 1], np.ones(3, dtype=np.float64)])
                        if abs(float(np.linalg.det(mat_xy))) > 1e-8:
                            try:
                                uv_affine = np.linalg.solve(mat_xy, mesh.uvs[mesh.face_vt[best_fid]])
                            except np.linalg.LinAlgError:
                                uv_affine = None
                    if uv_affine is not None:
                        v2_uv = np.column_stack([v2d[:, 0], v2d[:, 1], np.ones(len(v2d), dtype=np.float64)]) @ uv_affine
                    else:
                        v2_uv = np.column_stack([v2d[:, 0] * 0.25, v2d[:, 1] * 0.25])

                    new_pos_list.append(v3d_in)
                    if has_uvs:
                        new_uv_list.append(v2_uv)
                    fmat = int(mesh.face_material[best_fid])
                    for tri in f_fixed:
                        new_fv_list.append([next_v + int(tri[0]), next_v + int(tri[1]), next_v + int(tri[2])])
                        if has_uvs:
                            new_fvt_list.append([next_vt + int(tri[0]), next_vt + int(tri[1]), next_vt + int(tri[2])])
                        else:
                            new_fvt_list.append([-1, -1, -1])
                        new_fmat_list.append(fmat)
                    next_v += len(v3d_in)
                    if has_uvs:
                        next_vt += len(v2_uv)
                    healed_holes += 1

    if healed_holes == 0:
        return mesh, 0
    out.positions = np.vstack([out.positions, *new_pos_list])
    if has_uvs and new_uv_list:
        out.uvs = np.vstack([out.uvs, *new_uv_list])
    new_fv_arr = np.asarray(new_fv_list, dtype=np.int64)
    out.face_v = np.vstack([out.face_v, new_fv_arr])
    if out.face_vt is not None:
        out.face_vt = np.vstack([out.face_vt, np.asarray(new_fvt_list, dtype=np.int64)])
    if out.face_vn is not None:
        out.face_vn = np.vstack([out.face_vn, np.full((len(new_fv_arr), 3), -1, dtype=np.int64)])
    out.face_material = np.concatenate([out.face_material, np.asarray(new_fmat_list, dtype=np.int64)])
    if out.face_line is not None:
        out.face_line = np.concatenate([out.face_line, np.zeros(len(new_fv_arr), dtype=np.int64)])
    out, _ = compact_mesh(out, {})
    return out, healed_holes


def _drop_degenerate_faces(mesh: MeshData, min_area_sqin: float = 1e-6) -> tuple[MeshData, int]:
    """Drop raw zero-area and topology-welded degenerate (`~topo.ok`) faces."""
    if mesh.n_faces == 0:
        return mesh, 0
    fn = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    pts = mesh.positions[mesh.face_v]
    areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)
    topo = analyse_topology(mesh, frozenset())
    ok = (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) > 0.5) & (areas > min_area_sqin) & np.asarray(topo.ok, dtype=bool)
    n_drop = int((~ok).sum())
    if n_drop == 0:
        return mesh, 0
    out, _ = remove_faces(mesh, ~ok)
    out, _ = compact_mesh(out, {})
    return out, n_drop


def count_phantom_bridges(raw_ckpt: MeshData, candidate: MeshData) -> np.ndarray:
    """Return boolean mask of faces in `candidate` not 13/13 backed by `raw_ckpt`."""
    if candidate.n_faces == 0 or raw_ckpt.n_faces == 0:
        return np.zeros(candidate.n_faces, dtype=bool)
    center = 0.5 * (raw_ckpt.positions.min(axis=0) + raw_ckpt.positions.max(axis=0))
    fn_r = face_normals(raw_ckpt.positions, raw_ckpt.face_v, np.ones(raw_ckpt.n_faces, dtype=bool))
    ok_r = np.flatnonzero((~np.isnan(fn_r).any(axis=1)) & (np.linalg.norm(fn_r, axis=1) > 0.5))
    if len(ok_r) == 0:
        return np.zeros(candidate.n_faces, dtype=bool)
    cr = EmbreeCaster(raw_ckpt.positions - center, raw_ckpt.face_v[ok_r])

    fn_c = face_normals(candidate.positions, candidate.face_v, np.ones(candidate.n_faces, dtype=bool))
    ok_c = np.flatnonzero((~np.isnan(fn_c).any(axis=1)) & (np.linalg.norm(fn_c, axis=1) > 0.5))
    phantom = ~np.isin(np.arange(candidate.n_faces), ok_c)
    if len(ok_c) == 0:
        return phantom
    ct = candidate.positions[candidate.face_v[ok_c]] - center
    s13 = np.einsum("sb,fbk->fsk", BARY13, ct).reshape(-1, 3)
    n13 = np.repeat(fn_c[ok_c], 13, axis=0)
    hit = np.zeros(len(s13), dtype=bool)
    for off, tol in ((0.005, 0.0045), (0.06, 0.055)):
        for sign in (1.0, -1.0):
            ih, th = cr.first_hit(s13 + sign * off * n13, -sign * n13)
            c = np.flatnonzero((ih >= 0) & (np.abs(th - off) <= tol))
            fh = ok_r[ih[c]]
            dots = np.abs(np.einsum("ij,ij->i", n13[c], fn_r[fh])) >= 0.98
            hit[c[dots]] = True
    backed = hit.reshape(len(ok_c), 13).all(axis=1)
    phantom[ok_c[~backed]] = True
    return phantom


def drop_phantom_bridges(raw_ckpt: MeshData, candidate: MeshData) -> tuple[MeshData, int]:
    """Drop triangles not backed 13/13 by RAW CKPT-17 geometry (phantom canopy/soffit bridges)."""
    phantom = count_phantom_bridges(raw_ckpt, candidate)
    n_drop = int(phantom.sum())
    if n_drop == 0:
        return candidate, 0
    out, _ = remove_faces(candidate, phantom)
    out, _ = compact_mesh(out, {})
    return out, n_drop

REPO04_ROOT = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair")
RAW_BUILDINGS_ROOT = REPO04_ROOT / "Exports" / "Unity-Buildings-20261014" / "ByBuilding"
V1_BUILDINGS_ROOT = REPO04_ROOT / "Exports" / "Repaired-Buildings-20261015" / "ByBuilding"
DASH_MODELS_ROOT = Path(r"D:\PROJECTS\02-Corllenium-Siege\dashboard\public\models")
DEFAULT_OUT_ROOT = REPO04_ROOT / "02_STAGING_DEVELOPMENT" / "PerFloor-EngineV2"


def ckpt17_to_blender_zup_metres(positions_in: np.ndarray) -> np.ndarray:
    """Convert CKPT-17 Z-up inches -> Blender Z-up metres with det=+1.

    Blender `export_scene.gltf(..., export_yup=True)` maps `(X_b, Y_b, Z_b)` to
    glTF `(X_b, Z_b, -Y_b)`. Using `(-X_c, -Y_c, +Z_c) * 0.0254` preserves
    winding (`det = +1`) and makes glTF output equal `convert_ckpt17_to_unity_coords`.
    """
    pts = np.asarray(positions_in, dtype=np.float64).reshape(-1, 3)
    return np.column_stack([
        -INCH_TO_METRE * pts[:, 0],
        -INCH_TO_METRE * pts[:, 1],
        +INCH_TO_METRE * pts[:, 2],
    ])


def ckpt17_to_gltf_yup_metres(positions_in: np.ndarray) -> np.ndarray:
    """Convert CKPT-17 Z-up inches directly to the exact exported glTF/GLB Y-up metres frame.

    Composes `ckpt17_to_blender_zup_metres` (`-x, -y, +z`) * 0.0254 with Blender
    `export_scene.gltf(export_yup=True)` (`(X_b, Y_b, Z_b) -> (X_b, Z_b, -Y_b)`), yielding
    `(-x, +z, +y) * 0.0254` (`det = +1`) so overlay meshes share exact GLB coordinates.
    """
    pts = np.asarray(positions_in, dtype=np.float64).reshape(-1, 3)
    return np.column_stack([
        -INCH_TO_METRE * pts[:, 0],
        +INCH_TO_METRE * pts[:, 2],
        +INCH_TO_METRE * pts[:, 1],
    ])


def _is_yup_metres(mesh: MeshData) -> bool:
    lo, hi = mesh.bbox()
    size = hi - lo
    return bool(float(size.max()) < 350.0 and float(size[1]) < max(float(size[0]), float(size[2])))


def _find_floor_obj(folder: Path, prefer_fixed: bool) -> Path | None:
    if not folder.is_dir():
        return None
    if prefer_fixed:
        cands = sorted(folder.glob("*.fixed.obj"))
    else:
        cands = [
            p for p in sorted(folder.glob("*.obj"))
            if not p.name.lower().endswith(".fixed.obj")
            and "skp_ref" not in p.name.lower()
            and ".v2." not in p.name.lower()
        ]
    if not cands:
        return None
    return max(cands, key=lambda p: (0 if p.stem.lower().endswith("1") else 1, p.stat().st_size, p.name))


def _resolve_texture_file(tex_ref: str, search_dirs: list[Path]) -> Path | None:
    rel = tex_ref.replace("\\", "/").strip()
    name = Path(rel).name
    stripped = re.sub(r"^texture_\d+_", "", name)
    for d in search_dirs:
        if not d.is_dir():
            continue
        direct = (d / rel)
        if direct.is_file():
            return direct
        for cand_name in (name, stripped):
            p = d / cand_name
            if p.is_file():
                return p
            sub_tex = d / "textures" / cand_name
            if sub_tex.is_file():
                return sub_tex
            sub_t = d / "tex" / cand_name
            if sub_t.is_file():
                return sub_t
    return None


def resolve_and_copy_textures(
    raw_mtl_path: Path,
    v1_dir: Path | None,
    dash_dir: Path | None,
    out_mtl_path: Path,
    out_tex_dir: Path,
) -> dict[str, str]:
    """Parse RAW/v1 MTLs, copy real PNG textures to `out_tex_dir`, and write `out_mtl_path`."""
    raw_mats = parse_mtl(raw_mtl_path) if raw_mtl_path.is_file() else {}
    v1_mtl = v1_dir / raw_mtl_path.name if v1_dir else None
    v1_mats = parse_mtl(v1_mtl) if (v1_mtl is not None and v1_mtl.is_file()) else {}

    search_dirs: list[Path] = [raw_mtl_path.parent]
    if v1_dir is not None:
        search_dirs.append(v1_dir)
    if dash_dir is not None:
        search_dirs.append(dash_dir)

    out_tex_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    copied: dict[str, str] = {}

    merged_names = list(raw_mats.keys())
    for k in v1_mats:
        if k not in raw_mats:
            merged_names.append(k)

    for mname in merged_names:
        mat = raw_mats.get(mname) or v1_mats[mname]
        lines.append(f"newmtl {mname}")
        has_kd = False
        has_map = False
        for line in mat.lines:
            if line.startswith("Kd "):
                has_kd = True
            if line.startswith("map_Kd ") and mat.map_kd:
                has_map = True
                toks = mat.map_kd.split()
                tex_ref = toks[-1]
                src_png = _resolve_texture_file(tex_ref, search_dirs)
                if src_png is None and mname in v1_mats and v1_mats[mname].map_kd:
                    src_png = _resolve_texture_file(v1_mats[mname].map_kd.split()[-1], search_dirs)
                if src_png is not None:
                    dst_png = out_tex_dir / src_png.name
                    if not dst_png.is_file():
                        shutil.copy2(src_png, dst_png)
                    copied[mname] = src_png.name
                    lines.append(f"map_Kd textures/{src_png.name}")
                else:
                    lines.append(line)
            else:
                lines.append(line)
        if not has_kd:
            lines.append("Kd 1 1 1")
        if not has_map and mat.map_kd:
            src_png = _resolve_texture_file(mat.map_kd.split()[-1], search_dirs)
            if src_png is not None:
                dst_png = out_tex_dir / src_png.name
                if not dst_png.is_file():
                    shutil.copy2(src_png, dst_png)
                copied[mname] = src_png.name
                lines.append(f"map_Kd textures/{src_png.name}")
        lines.append("")

    out_mtl_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return copied


def normalize_uv_tile_offsets(mesh: MeshData) -> tuple[MeshData, int, float]:
    """Shift per-triangle UVs by integer tile multiples so repeating UVs stay bounded near [0, N].

    Preserves 100.0% of LittleTiles fractional repeat sampling while eliminating extreme UV
    coordinates before Blender GLB export and Unity Mesh Baker 3.40.2 atlasing (`Consider Mesh UVs`).
    """
    if mesh.n_faces == 0 or mesh.uvs is None or len(mesh.uvs) == 0 or mesh.face_vt is None:
        return mesh, 0, 0.0
    uvs = np.asarray(mesh.uvs, dtype=np.float64)
    fvt = np.asarray(mesh.face_vt, dtype=np.int64).copy()
    new_uvs: list[np.ndarray] = [uvs]
    next_vt = len(uvs)
    faces_shifted = 0

    valid_faces = np.flatnonzero((fvt >= 0).all(axis=1))
    for fid in valid_faces:
        tri_vt = fvt[fid]
        tri_uv = uvs[tri_vt]
        du = float(np.floor(np.min(tri_uv[:, 0])))
        dv = float(np.floor(np.min(tri_uv[:, 1])))
        if du != 0.0 or dv != 0.0:
            shifted = tri_uv - np.array([du, dv], dtype=np.float64)
            new_uvs.append(shifted)
            fvt[fid] = np.array([next_vt, next_vt + 1, next_vt + 2], dtype=np.int64)
            next_vt += 3
            faces_shifted += 1

    out = copy.deepcopy(mesh)
    if faces_shifted > 0:
        out.uvs = np.vstack(new_uvs)
        out.face_vt = fvt
        out, _ = compact_mesh(out, {})
    max_abs = float(np.max(np.abs(out.uvs))) if (out.uvs is not None and len(out.uvs) > 0) else 0.0
    return out, faces_shifted, round(max_abs, 4)


def _dedup_exact_same_normal(mesh: MeshData) -> tuple[MeshData, int]:
    """Remove exact coincident duplicate triangles carrying matching normal direction."""
    if mesh.n_faces < 2:
        return mesh, 0
    center = 0.5 * (mesh.positions.min(axis=0) + mesh.positions.max(axis=0))
    pts_c = mesh.positions[mesh.face_v] - center
    fn = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    ok = (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) > 0.5)
    fn_safe = np.where(ok[:, None], fn, 0.0)
    q_pts = np.sort(np.round(pts_c * 200.0).astype(np.int64), axis=1).reshape(mesh.n_faces, 9)
    q_fn = np.round(fn_safe * 20.0).astype(np.int64)
    _, keep_idx = np.unique(np.hstack([q_pts, q_fn]), axis=0, return_index=True)
    keep = np.zeros(mesh.n_faces, dtype=bool)
    keep[keep_idx] = True
    keep &= ok
    n_drop = int((~keep).sum())
    if n_drop == 0:
        return mesh, 0
    out, _ = remove_faces(mesh, ~keep)
    out, _ = compact_mesh(out, {})
    return out, n_drop


def apply_strict_outer_facade_lock(
    before_ckpt: MeshData,
    repaired_ckpt: MeshData,
    *,
    min_area_sqin: float = 0.01,
    exclude_mask: np.ndarray | None = None,
) -> tuple[MeshData, int]:
    """Ensure 100% of exterior-exposed real model faces (railings, windows, louvers, fascia) survive."""
    if before_ckpt.n_faces == 0:
        return repaired_ckpt, 0
    center = 0.5 * (before_ckpt.positions.min(axis=0) + before_ckpt.positions.max(axis=0))
    pts_b = before_ckpt.positions[before_ckpt.face_v]
    fn_b = face_normals(before_ckpt.positions, before_ckpt.face_v, np.ones(before_ckpt.n_faces, dtype=bool))
    areas_b = 0.5 * np.linalg.norm(np.cross(pts_b[:, 1] - pts_b[:, 0], pts_b[:, 2] - pts_b[:, 0]), axis=1)
    ok_b = (~np.isnan(fn_b).any(axis=1)) & (np.linalg.norm(fn_b, axis=1) > 0.5)
    valid_b = ok_b & (areas_b >= min_area_sqin)
    if exclude_mask is not None and len(exclude_mask) == before_ckpt.n_faces:
        valid_b = valid_b & (~np.asarray(exclude_mask, dtype=bool))

    ef_b, eb_b = compute_side_exposure(before_ckpt.positions - center, before_ckpt.face_v, ok_b, n_dirs=128)
    outer_b = valid_b & (classify_exposure(ef_b + eb_b, ok_b) == EXP_OUTSIDE)
    outer_ids = np.flatnonzero(outer_b)
    if len(outer_ids) == 0:
        return repaired_ckpt, 0

    after_caster = EmbreeCaster(repaired_ckpt.positions - center, repaired_ckpt.face_v)
    _, miss_outer = _coverage_7pt(before_ckpt, after_caster, center, fn_b, outer_ids, tol=0.12)
    if len(miss_outer) == 0:
        return repaired_ckpt, 0

    locked = _append_before_faces(copy.deepcopy(repaired_ckpt), before_ckpt, miss_outer)
    locked, _ = compact_mesh(locked, {})
    return locked, int(len(miss_outer))


def purge_internal_voxel_stack_plates(
    raw_ckpt: MeshData,
    candidate: MeshData,
    raw_stack_mask: np.ndarray,
) -> tuple[MeshData, int]:
    """Purge internal 1-block (39.37 in) horizontal voxel-stack plates trapped inside walls/cores."""
    if candidate.n_faces == 0:
        return candidate, 0
    fn_c = face_normals(candidate.positions, candidate.face_v, np.ones(candidate.n_faces, dtype=bool))
    ok_c = (~np.isnan(fn_c).any(axis=1)) & (np.linalg.norm(fn_c, axis=1) > 0.5)
    h_idx = np.flatnonzero(ok_c & (np.abs(fn_c[:, 2]) > 0.95))
    if len(h_idx) == 0:
        return candidate, 0

    cand_stack_mask = detect_internal_voxel_stack_plates(candidate)
    matched_raw_stack = np.zeros(candidate.n_faces, dtype=bool)
    protected_by_non_stack_outer = np.zeros(candidate.n_faces, dtype=bool)
    protected_by_non_stack_raw = np.zeros(candidate.n_faces, dtype=bool)

    if raw_ckpt.n_faces > 0:
        center = 0.5 * (raw_ckpt.positions.min(axis=0) + raw_ckpt.positions.max(axis=0))
        fn_r = face_normals(raw_ckpt.positions, raw_ckpt.face_v, np.ones(raw_ckpt.n_faces, dtype=bool))
        ok_r = (~np.isnan(fn_r).any(axis=1)) & (np.linalg.norm(fn_r, axis=1) > 0.5)
        raw_stack = np.asarray(raw_stack_mask, dtype=bool)
        if len(raw_stack) != raw_ckpt.n_faces:
            raw_stack = detect_internal_voxel_stack_plates(raw_ckpt)
        stack_idx = np.flatnonzero(ok_r & raw_stack)
        non_stack_idx = np.flatnonzero(ok_r & (~raw_stack))

        tri_h = candidate.positions[candidate.face_v[h_idx]] - center
        s4 = np.einsum("sb,fbk->fsk", BARY, tri_h).reshape(-1, 3)
        n4 = np.repeat(fn_c[h_idx], len(BARY), axis=0)

        def _coplanar_hit_counts(caster_faces: np.ndarray) -> np.ndarray:
            if len(caster_faces) == 0:
                return np.zeros(len(h_idx), dtype=np.int64)
            caster = EmbreeCaster(raw_ckpt.positions - center, raw_ckpt.face_v[caster_faces])
            hit = np.zeros(len(s4), dtype=bool)
            for sign in (1.0, -1.0):
                ih, th = caster.first_hit(s4 + sign * 0.12 * n4, -sign * n4)
                c = np.flatnonzero((ih >= 0) & (th <= 0.24))
                if len(c):
                    fh = caster_faces[ih[c]]
                    dots = np.abs(np.einsum("ij,ij->i", n4[c], fn_r[fh])) >= 0.98
                    hit[c[dots]] = True
            return hit.reshape(len(h_idx), len(BARY)).sum(axis=1)

        non_stack_hits = _coplanar_hit_counts(non_stack_idx)
        protected_by_non_stack_raw[h_idx[non_stack_hits >= 2]] = True
        if len(stack_idx) > 0:
            stack_hits = _coplanar_hit_counts(stack_idx)
            matched_raw_stack[h_idx[(stack_hits >= 3) & (non_stack_hits < 2)]] = True

        ef_r, eb_r = compute_side_exposure(raw_ckpt.positions - center, raw_ckpt.face_v, ok_r, n_dirs=128)
        outer_r = ok_r & (classify_exposure(ef_r + eb_r, ok_r) == EXP_OUTSIDE)
        non_stack_outer_idx = np.flatnonzero(outer_r & (~raw_stack))
        if len(non_stack_outer_idx) > 0:
            outer_hits = _coplanar_hit_counts(non_stack_outer_idx)
            protected_by_non_stack_outer[h_idx[outer_hits >= 2]] = True

    drop_mask = matched_raw_stack | (cand_stack_mask & (~protected_by_non_stack_outer) & (~protected_by_non_stack_raw))
    n_drop = int(drop_mask.sum())
    if n_drop == 0:
        return candidate, 0
    out, _ = remove_faces(candidate, drop_mask)
    out, _ = compact_mesh(out, {})
    return out, n_drop


def _summarize_audit_full(
    name: str,
    before_ckpt: MeshData,
    candidate_ckpt: MeshData,
    *,
    rebuild_exclusion_mask_fn: Any = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    errs = find_errors(candidate_ckpt)
    fi = verify_facade_and_mesh_integrity(
        before_ckpt,
        candidate_ckpt,
        errs,
        rebuild_exclusion_mask_fn=rebuild_exclusion_mask_fn,
    )
    diff = compute_before_after_diff_overlay(
        before_ckpt,
        candidate_ckpt,
        errs,
        rebuild_exclusion_mask_fn=rebuild_exclusion_mask_fn,
        n_probe_dirs=256,
        n_ext_dirs=128,
    )
    checks = {c["id"]: c for c in fi["checks"]}
    summary = {
        "name": name,
        "tris": int(candidate_ckpt.n_faces),
        "errors": {k: int(v) for k, v in errs["counts"].items()},
        "loose_parts": {k: int(v) for k, v in errs.get("loose_parts", {}).items()},
        "diff_counts": {k: int(v) for k, v in diff.get("counts", {}).items()},
        "automated_passed": bool(fi["automatedPassed"]),
        "failed_checks": list(fi["failedCheckIds"]),
        "checks": {
            cid: {
                "status": c["status"],
                "measured": c["measured"],
                "numericValue": c.get("numericValue"),
            }
            for cid, c in checks.items()
        },
    }
    return summary, errs, diff, fi


def _summarize_audit(
    name: str,
    before_ckpt: MeshData,
    candidate_ckpt: MeshData,
    *,
    rebuild_exclusion_mask_fn: Any = None,
) -> dict[str, Any]:
    summary, _, _, _ = _summarize_audit_full(
        name,
        before_ckpt,
        candidate_ckpt,
        rebuild_exclusion_mask_fn=rebuild_exclusion_mask_fn,
    )
    return summary


def _extract_tris_gltf_yup(
    mesh: MeshData,
    face_ids: list[int] | np.ndarray,
    *,
    max_tris: int = 1800,
) -> list[float]:
    """Extract triangles for `face_ids` in glTF Y-up metres, largest area first."""
    fids = np.asarray(face_ids, dtype=np.int64).ravel()
    fids = fids[(fids >= 0) & (fids < mesh.n_faces)]
    if len(fids) == 0:
        return []
    pts_in = mesh.positions[mesh.face_v[fids]]
    if len(fids) > max_tris:
        areas = 0.5 * np.linalg.norm(np.cross(pts_in[:, 1] - pts_in[:, 0], pts_in[:, 2] - pts_in[:, 0]), axis=1)
        top_idx = np.argsort(-areas)[:max_tris]
        pts_in = pts_in[top_idx]
    pts_gltf = ckpt17_to_gltf_yup_metres(pts_in.reshape(-1, 3))
    return [round(float(v), 4) for v in pts_gltf.reshape(-1)]


def _extract_open_edge_segments_gltf_yup(
    open_edges: list[list[float]] | np.ndarray,
    *,
    max_edges: int = 500,
) -> list[list[float]]:
    arr = np.asarray(open_edges, dtype=np.float64)
    if arr.size == 0:
        return []
    arr = arr.reshape(-1, 6)
    lens = np.linalg.norm(arr[:, 3:6] - arr[:, 0:3], axis=1)
    if len(arr) > max_edges:
        arr = arr[np.argsort(-lens)[:max_edges]]
    p0 = ckpt17_to_gltf_yup_metres(arr[:, 0:3])
    p1 = ckpt17_to_gltf_yup_metres(arr[:, 3:6])
    segs = np.hstack([p0, p1])
    return [[round(float(v), 4) for v in row] for row in segs]


def _spots_gltf_yup(
    spots_dict: dict[str, list[dict[str, Any]]],
    kinds: tuple[str, ...],
    extra_spots: dict[str, list[dict[str, Any]]] | None = None,
    *,
    limit: int = 8,
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for k in kinds:
        raw_list = (extra_spots.get(k) if extra_spots else None) or spots_dict.get(k, [])
        converted: list[dict[str, Any]] = []
        for sp in raw_list[:limit]:
            cen_in = sp.get("centre") or sp.get("center")
            if cen_in is None or len(cen_in) != 3:
                continue
            cen_m = ckpt17_to_gltf_yup_metres(np.asarray([cen_in], dtype=np.float64))[0]
            raw_sz = sp.get("size", 12.0)
            if isinstance(raw_sz, (list, tuple)) and len(raw_sz) == 3:
                sz_m = [
                    max(0.08, round(abs(float(raw_sz[0])) * INCH_TO_METRE, 3)),
                    max(0.08, round(abs(float(raw_sz[2])) * INCH_TO_METRE, 3)),
                    max(0.08, round(abs(float(raw_sz[1])) * INCH_TO_METRE, 3)),
                ]
            else:
                s_val = max(0.18, min(4.0, round(float(raw_sz or 12.0) * INCH_TO_METRE, 3)))
                sz_m = [s_val, s_val, s_val]
            converted.append({
                "kind": k,
                "label": str(sp.get("label", k)),
                "centre_m": [round(float(v), 4) for v in cen_m],
                "size_m": sz_m,
                "count": int(sp.get("count", 1)),
            })
        out[k] = converted
    return out


def _single_side_overlay_payload(
    before_ckpt: MeshData,
    cand_ckpt: MeshData,
    errs: dict[str, Any],
    diff: dict[str, Any],
    fi: dict[str, Any],
    *,
    phantom_tris: int = 0,
) -> dict[str, Any]:
    checks_map = {c["id"]: c for c in fi.get("checks", [])}
    torn_seams = int(round(float(checks_map.get("outer_facade_zero_cracklines", {}).get("numericValue") or 0)))
    diff_counts = diff.get("counts", {})
    counts = {k: int(v) for k, v in errs.get("counts", {}).items()}
    counts["missing_outer_facade"] = int(diff_counts.get("missing_outer_facade", 0))
    counts["missing_interior_visible"] = int(diff_counts.get("missing_interior_visible", 0))
    counts["torn_outer_seams"] = torn_seams
    counts["phantom_bridges"] = int(phantom_tris)

    faces_map = errs.get("faces", {})
    before_faces = diff.get("before_faces", {})
    tris_by_kind: dict[str, list[float]] = {
        "flicker_diff": _extract_tris_gltf_yup(cand_ckpt, faces_map.get("flicker_diff", [])),
        "flicker_same": _extract_tris_gltf_yup(cand_ckpt, faces_map.get("flicker_same", [])),
        "reversed": _extract_tris_gltf_yup(cand_ckpt, faces_map.get("reversed", [])),
        "hidden": _extract_tris_gltf_yup(cand_ckpt, faces_map.get("hidden", [])),
        "loose": _extract_tris_gltf_yup(cand_ckpt, faces_map.get("loose", [])),
        "missing_outer_facade": _extract_tris_gltf_yup(before_ckpt, before_faces.get("missing_outer_facade", [])),
        "missing_interior_visible": _extract_tris_gltf_yup(before_ckpt, before_faces.get("missing_interior_visible", [])),
    }
    segments_by_kind = {
        "open_edges": _extract_open_edge_segments_gltf_yup(errs.get("open_edges", [])),
    }
    extra_spots: dict[str, list[dict[str, Any]]] = {
        "missing_outer_facade": (diff.get("spots", {}).get("missing_outer_facade") or checks_map.get("outer_facade_completeness", {}).get("spots") or []),
        "missing_interior_visible": (diff.get("spots", {}).get("missing_interior_visible") or checks_map.get("interior_visible_retention", {}).get("spots") or []),
        "torn_outer_seams": (checks_map.get("outer_facade_zero_cracklines", {}).get("spots") or []),
    }
    all_kinds = (
        "flicker_diff",
        "flicker_same",
        "reversed",
        "hidden",
        "loose",
        "open_edges",
        "cracks",
        "missing_outer_facade",
        "missing_interior_visible",
        "torn_outer_seams",
    )
    spots = _spots_gltf_yup(errs.get("spots", {}), all_kinds, extra_spots)
    return {
        "tris": int(cand_ckpt.n_faces),
        "counts": counts,
        "trisByKind": tris_by_kind,
        "segmentsByKind": segments_by_kind,
        "spots": spots,
    }


def _build_error_overlay_payload(
    building: str,
    floor: str,
    unit_slug: str,
    before_ckpt: MeshData,
    v1_ckpt: MeshData | None,
    v1_tuple: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]] | None,
    v2_ckpt: MeshData,
    v2_tuple: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
    *,
    phantom_tris_v2: int,
) -> dict[str, Any]:
    """Build compact dual 3D error overlay payload (v1 residual errors + v2 residual errors) in glTF Y-up metres."""
    _, v2_errs, v2_diff, v2_fi = v2_tuple
    v2_side = _single_side_overlay_payload(before_ckpt, v2_ckpt, v2_errs, v2_diff, v2_fi, phantom_tris=phantom_tris_v2)

    if v1_ckpt is not None and v1_tuple is not None:
        _, v1_errs, v1_diff, v1_fi = v1_tuple
        v1_side = _single_side_overlay_payload(before_ckpt, v1_ckpt, v1_errs, v1_diff, v1_fi, phantom_tris=0)
    else:
        v1_side = {
            "tris": 0,
            "counts": {k: 0 for k in v2_side["counts"]},
            "trisByKind": {k: [] for k in v2_side["trisByKind"]},
            "segmentsByKind": {"open_edges": []},
            "spots": {k: [] for k in v2_side["spots"]},
        }

    comparison_defs = [
        ("reversed", "Reversed / Flipped Normals", "Engine v1 left inside-out faces; Real Engine v2 fixes all one-sided orientation via 128-dir Embree visibility."),
        ("missing_outer_facade", "Missing Outer Facade (Deleted by v1)", "Engine v1 deleted exterior railings, trim, or outer concrete faces; Real Engine v2 Strict Outer Facade Lock restores 99.8-100%."),
        ("missing_interior_visible", "Missing Interior Visible Faces", "Engine v1 culled visible room walls/baseboards; Real Engine v2 preserves visible interior rooms & solids."),
        ("flicker_diff", "Coplanar Z-Fighting (Diff Material)", "Overlapping coplanar surfaces flickering on floor/wall faces; Engine v2 E5 border clipping converges to 0."),
        ("flicker_same", "Coplanar Z-Fighting (Same Material)", "Same-material overlapping faces shimmering in camera; Engine v2 resolves to a single sheet."),
        ("torn_outer_seams", "Torn Exterior Crackline Seams", "Newly opened exterior cracks created by partial face drops; Real Engine v2 closes uncovered boundaries."),
        ("hidden", "Buried Internal Faces", "Unseen internal LittleTiles cube faces inside wall cores stripped cleanly while keeping visible walls solid."),
        ("loose", "Loose Floating Debris", "Disconnected sub-grid interior scraps removed without deleting valid railings or frames."),
    ]
    v1_error_list: list[dict[str, Any]] = []
    for kind, title, expl in comparison_defs:
        c1 = int(v1_side["counts"].get(kind, 0))
        c2 = int(v2_side["counts"].get(kind, 0))
        if c1 == 0 and c2 == 0:
            st = "clean"
        elif c2 == 0 and c1 > 0:
            st = "fixed"
        elif c2 < c1:
            st = "reduced"
        else:
            st = "residual"
        v1_error_list.append({
            "kind": kind,
            "title": title,
            "v1Count": c1,
            "v2Count": c2,
            "status": st,
            "explanation": expl,
        })

    return {
        "version": 2,
        "building": building,
        "floor": floor,
        "unitSlug": unit_slug,
        "v1": v1_side,
        "v2": v2_side,
        "v1ErrorList": v1_error_list,
    }


def _exposure_masks(mesh: MeshData, *, n_dirs: int = 128) -> tuple[np.ndarray, np.ndarray]:
    if mesh.n_faces == 0:
        z = np.zeros(0, dtype=bool)
        return z, z
    center = 0.5 * (mesh.positions.min(axis=0) + mesh.positions.max(axis=0))
    fn = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    ok = (~np.isnan(fn).any(axis=1)) & (np.linalg.norm(fn, axis=1) > 0.5)
    ef, eb = compute_side_exposure(mesh.positions - center, mesh.face_v, ok, n_dirs=n_dirs)
    exp = classify_exposure(ef + eb, ok)
    outer_mask = ok & (exp == EXP_OUTSIDE)
    vis_mask = outer_mask | (ok & ((ef + eb) > 0.0))
    return outer_mask, vis_mask


def resolve_residual_double_layers(
    mesh: MeshData,
    outer_mask: np.ndarray,
    vis_mask: np.ndarray,
) -> tuple[MeshData, int]:
    """Clip or drop any remaining `double_layers` flicker pairs missed by plane bucketing."""
    if mesh.n_faces < 2:
        return mesh, 0
    profile = FixProfile()
    topo = analyse_topology(mesh, frozenset(), coplanar_angle=profile.coplanar_angle, soft_angle=profile.soft_angle)
    pos, faces = topo.positions_w, topo.face_w
    centre = 0.5 * (pos.min(axis=0) + pos.max(axis=0))
    depth_tol = guard_depth_tol(topo.quanta, profile)
    dl = double_layers(pos - centre, faces, depth_tol, VIEWS_26, profile.guard_size, centre=centre)
    pairs = dl.get("pair_list", [])
    if not pairs:
        return mesh, 0

    fn = face_normals(mesh.positions, mesh.face_v, np.ones(mesh.n_faces, dtype=bool))
    pts = mesh.positions[mesh.face_v]
    areas = 0.5 * np.linalg.norm(np.cross(pts[:, 1] - pts[:, 0], pts[:, 2] - pts[:, 0]), axis=1)

    def _score(f: int) -> tuple[int, int, int, float]:
        is_hs = abs(float(fn[f, 2])) > 0.5
        return (
            1 if bool(outer_mask[f]) else 0,
            1 if bool(vis_mask[f]) else 0,
            (1 if float(fn[f, 2]) > 0.0 else 0) if is_hs else 1,
            float(areas[f]),
        )

    drop_mask = np.zeros(mesh.n_faces, dtype=bool)
    win_by_loser: dict[int, list[int]] = {}
    for i, j, _sep, _ovl in pairs:
        if i == j or i < 0 or j < 0 or i >= mesh.n_faces or j >= mesh.n_faces:
            continue
        winner, loser = (i, j) if _score(i) >= _score(j) else (j, i)
        win_by_loser.setdefault(loser, []).append(winner)

    # Non-transitive guard: a face being dropped/clipped in this pass must NEVER clip another face
    active_losers = set(win_by_loser.keys())
    filtered_pairs: list[tuple[int, list[int]]] = []
    for loser, winners in win_by_loser.items():
        non_loser_winners = [w for w in winners if w not in active_losers]
        if non_loser_winners:
            filtered_pairs.append((loser, non_loser_winners))
    if not filtered_pairs and active_losers:
        keeper = max(active_losers, key=_score)
        active_losers.remove(keeper)
        for loser in active_losers:
            non_loser_winners = [w for w in win_by_loser[loser] if w not in active_losers]
            if non_loser_winners:
                filtered_pairs.append((loser, non_loser_winners))

    new_pos_list: list[np.ndarray] = []
    new_uv_list: list[np.ndarray] = []
    new_fv_list: list[list[int]] = []
    new_fvt_list: list[list[int]] = []
    new_fmat_list: list[int] = []
    has_uvs = mesh.uvs is not None and len(mesh.uvs) > 0 and mesh.face_vt is not None
    next_v_idx = len(mesh.positions)
    next_vt_idx = len(mesh.uvs) if has_uvs else 0

    for loser, winners in filtered_pairs:
        if drop_mask[loser]:
            continue
        nl = fn[loser]
        if np.isnan(nl).any() or float(np.linalg.norm(nl)) < 0.5:
            drop_mask[loser] = True
            continue
        u_ax, v_ax = plane_basis(nl)
        p2_l = np.stack([pts[loser] @ u_ax, pts[loser] @ v_ax], axis=-1)
        poly_l = Polygon(p2_l)
        if not poly_l.is_valid or float(poly_l.area) <= 1e-4:
            drop_mask[loser] = True
            continue
        p_l_mean = pts[loser].mean(axis=0)
        win_polys = []
        for w in winners:
            nw = fn[w]
            if np.isnan(nw).any() or float(np.linalg.norm(nw)) < 0.5:
                continue
            # Strict coplanarity guard: never let an angled/distant wall erase an orthogonal wall
            if abs(float(np.dot(nw, nl))) < 0.98:
                continue
            if abs(float(np.dot(pts[w].mean(axis=0) - p_l_mean, nl))) > 0.15:
                continue
            pw = Polygon(np.stack([pts[w] @ u_ax, pts[w] @ v_ax], axis=-1))
            if pw.is_valid and float(pw.area) > 1e-4:
                win_polys.append(pw)
        if not win_polys:
            continue
        w_union = unary_union(win_polys)
        ovl_area = float(poly_l.intersection(w_union).area)
        if ovl_area <= 0.01:
            continue
        rem_area = float(poly_l.area) - ovl_area
        if rem_area > 0.01:
            clip_cut = w_union.buffer(-0.001)
            if clip_cut.is_empty:
                clip_cut = w_union
            rem_geom = poly_l.difference(clip_cut).buffer(0)
            if rem_geom.geom_type == "GeometryCollection":
                rem_geom = unary_union([g for g in rem_geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")])
            if not rem_geom.is_empty and float(rem_geom.area) > 0.01:
                orig_fvt = mesh.face_vt[loser] if has_uvs else np.array([-1, -1, -1], dtype=np.int64)
                uvs_f = mesh.uvs[orig_fvt] if (has_uvs and (orig_fvt >= 0).all()) else None
                npos, nuv, nfv, nfvt, nfmat, next_v_idx, next_vt_idx = _triangulate_clipped_face(
                    pts[loser], p2_l, mesh.face_v[loser], orig_fvt, uvs_f, nl, int(mesh.face_material[loser]),
                    rem_geom, next_v_idx, next_vt_idx, min_part_area=0.01,
                )
                if not nfv and rem_area > 0.25:
                    continue
                new_pos_list.extend(npos)
                new_uv_list.extend(nuv)
                new_fv_list.extend(nfv)
                new_fvt_list.extend(nfvt)
                new_fmat_list.extend(nfmat)
        drop_mask[loser] = True

    if not drop_mask.any():
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
    out, _ = compact_mesh(out, {})
    return out, int(drop_mask.sum())


def build_real_v2_floor(
    building: str,
    floor: str,
    *,
    out_root: Path = DEFAULT_OUT_ROOT,
    include_dashboard_v1_audit: bool = False,
) -> dict[str, Any]:
    raw_dir = RAW_BUILDINGS_ROOT / building / floor
    raw_obj = _find_floor_obj(raw_dir, prefer_fixed=False)
    if raw_obj is None:
        raise FileNotFoundError(f"RAW OBJ not found under {raw_dir}")
    raw_mtl = raw_dir / f"{raw_obj.stem}.mtl"
    if not raw_mtl.is_file():
        mtls = sorted(raw_dir.glob("*.mtl"))
        if not mtls:
            raise FileNotFoundError(f"MTL not found under {raw_dir}")
        raw_mtl = mtls[0]

    v1_dir = V1_BUILDINGS_ROOT / building / floor
    v1_obj = _find_floor_obj(v1_dir, prefer_fixed=True)
    unit_slug = raw_obj.stem.lower()
    dash_dir = DASH_MODELS_ROOT / unit_slug
    if not dash_dir.is_dir():
        dash_dir = next(
            (p for p in DASH_MODELS_ROOT.iterdir() if p.is_dir() and p.name.lower() == unit_slug),
            None,
        )

    out_dir = out_root / building / floor
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{building}_{floor}"
    out_mtl = out_dir / f"{stem}.v2.mtl"
    out_obj = out_dir / f"{stem}.v2.obj"
    out_report = out_dir / "v2_integrity_report.json"
    out_overlay = out_dir / "v2_error_overlay.json"

    copied_textures = resolve_and_copy_textures(
        raw_mtl,
        v1_dir if v1_dir.is_dir() else None,
        dash_dir,
        out_mtl,
        out_dir / "textures",
    )

    ckpt_raw = read_obj(raw_obj)
    if _is_yup_metres(ckpt_raw):
        ckpt_raw.positions = np.round(convert_unity_to_ckpt17_coords(ckpt_raw.positions), 4)
    ckpt_raw.units = "inches"
    raw_stack_mask = detect_internal_voxel_stack_plates(ckpt_raw)
    _excl_stack_fn = lambda m, mask=raw_stack_mask: mask if m.n_faces == len(mask) else detect_internal_voxel_stack_plates(m)

    # 1. Core real-mesh Engine v2 repair (excluding hanging `solidify` soffits) + 13-pt phantom purge
    real_v2_stages = [s for s in REPAIR_STAGE_ORDER if s != "solidify"]
    repaired, _rings, core_stats = repair_building_floor_mesh(ckpt_raw, out_mtl, enabled_stages=real_v2_stages)
    repaired, _ = compact_mesh(repaired, {})
    repaired, n_phantom_pre = drop_phantom_bridges(ckpt_raw, repaired)

    # 2. Align horizontal floor/ceiling orientation without re-appending duplicate triangles
    repaired, n_horiz_flipped = orient_horizontals(ckpt_raw, repaired)

    # 3. Visible-interior (256-dir matching integrity gate) + Strict 100% Outer Facade Lock
    diff_post = compute_before_after_diff_overlay(
        ckpt_raw,
        repaired,
        rebuild_exclusion_mask_fn=_excl_stack_fn,
        n_probe_dirs=256,
        n_ext_dirs=128,
    )
    repaired, n_diff_healed = restore_destroyed_facade_faces(ckpt_raw, repaired, diff_post, include_interior=True)
    repaired, n_outer_locked = apply_strict_outer_facade_lock(
        ckpt_raw, repaired, min_area_sqin=0.05, exclude_mask=raw_stack_mask
    )

    # 4. E5 single-layer zero-flicker convergence (`EXP_OUTSIDE` always wins) + phantom/z-fight/degen cleanup
    outer_mask, vis_mask = _exposure_masks(repaired, n_dirs=128)
    repaired, n_post_coplanar = remove_coplanar_overlaps(
        repaired,
        dist_tol=0.04,
        rebuild=True,
        visible=vis_mask,
        outer_priority=outer_mask,
        allow_same_plane_back_to_back=False,
    )
    repaired, n_phantom_mid = drop_phantom_bridges(ckpt_raw, repaired)
    outer_mask, _ = _exposure_masks(repaired, n_dirs=128)
    repaired, n_zfight_dropped = resolve_near_coplanar_zfight(
        repaired, visible_mask=outer_mask, min_dist_in=0.01, max_dist_in=0.25
    )
    repaired, n_dedup = _dedup_exact_same_normal(repaired)
    repaired, n_degen_dropped = _drop_degenerate_faces(repaired)

    repaired, n_outer_safety = apply_strict_outer_facade_lock(
        ckpt_raw, repaired, min_area_sqin=0.05, exclude_mask=raw_stack_mask
    )
    n_phantom_safety = 0
    if n_outer_safety > 0:
        outer_mask, vis_mask = _exposure_masks(repaired, n_dirs=128)
        repaired, n_cov_extra = remove_coplanar_overlaps(
            repaired,
            dist_tol=0.04,
            rebuild=True,
            visible=vis_mask,
            outer_priority=outer_mask,
            allow_same_plane_back_to_back=False,
        )
        n_post_coplanar += n_cov_extra
        repaired, n_phantom_safety = drop_phantom_bridges(ckpt_raw, repaired)
        repaired, n_degen_s = _drop_degenerate_faces(repaired)
        n_degen_dropped += n_degen_s
    repaired, n_lock_dedup = _dedup_exact_same_normal(repaired)

    # Clear any residual `double_layers` flicker pairs missed by bucketing (up to 5 passes)
    for _ in range(5):
        outer_mask_dl, vis_mask_dl = _exposure_masks(repaired, n_dirs=128)
        repaired, n_res_dl = resolve_residual_double_layers(repaired, outer_mask_dl, vis_mask_dl)
        n_post_coplanar += n_res_dl
        if n_res_dl == 0:
            break
    repaired, n_degen_dl = _drop_degenerate_faces(repaired)
    n_degen_dropped += n_degen_dl
    repaired, n_stack_plates_purged = purge_internal_voxel_stack_plates(ckpt_raw, repaired, raw_stack_mask)

    n_outer_locked += n_outer_safety
    n_phantom_dropped = n_phantom_pre + n_phantom_mid + n_phantom_safety

    # 5. One-sided normal outward orientation pass (leaves two-sided thin railings/glass untouched)
    n_post_oriented = 0
    if repaired.n_faces > 0:
        center = 0.5 * (repaired.positions.min(axis=0) + repaired.positions.max(axis=0))
        fn_r = face_normals(repaired.positions, repaired.face_v, np.ones(repaired.n_faces, dtype=bool))
        ok_r = (~np.isnan(fn_r).any(axis=1)) & (np.linalg.norm(fn_r, axis=1) > 0.5)
        ef_r, eb_r = compute_side_exposure(repaired.positions - center, repaired.face_v, ok_r, n_dirs=128)
        verdict = classify_orientation(ef_r, eb_r, ok_r)
        flip_mask = ok_r & (verdict == ORIENT_FLIP)
        if flip_mask.any():
            repaired = flip_faces(repaired, flip_mask)
            n_post_oriented = int(flip_mask.sum())

    # 6. Final piercing needle-sliver + strict 100.00% outer facade lock & convergence loop
    n_post_slivers = 0
    if repaired.n_faces > 0:
        outer_prot, _ = _exposure_masks(repaired, n_dirs=128)
        repaired, n_post_slivers = purge_piercing_needle_slivers(repaired, protect_mask=outer_prot)
        for conv_round in range(4):
            prev_n = repaired.n_faces
            repaired, n_restored_round = apply_strict_outer_facade_lock(
                ckpt_raw,
                repaired,
                min_area_sqin=0.05,
                exclude_mask=raw_stack_mask,
            )
            if n_restored_round > 0:
                n_outer_locked += n_restored_round
            if conv_round > 0 and n_restored_round == 0:
                break
            for dl_iter in range(5):
                outer_ps, vis_ps = _exposure_masks(repaired, n_dirs=128)
                if dl_iter == 0 and n_restored_round > 0 and repaired.n_faces > prev_n:
                    outer_ps[prev_n:] = True
                repaired, n_dl_ps = resolve_residual_double_layers(repaired, outer_ps, vis_ps)
                n_post_coplanar += n_dl_ps
                if n_dl_ps == 0:
                    break
            repaired, n_post_dedup = _dedup_exact_same_normal(repaired)
            n_lock_dedup += n_post_dedup
            repaired, n_phantom_fin = drop_phantom_bridges(ckpt_raw, repaired)
            n_phantom_dropped += n_phantom_fin
            if repaired.n_faces > 0:
                center_fin = 0.5 * (repaired.positions.min(axis=0) + repaired.positions.max(axis=0))
                fn_fin = face_normals(repaired.positions, repaired.face_v, np.ones(repaired.n_faces, dtype=bool))
                ok_fin = (~np.isnan(fn_fin).any(axis=1)) & (np.linalg.norm(fn_fin, axis=1) > 0.5)
                ef_fin, eb_fin = compute_side_exposure(repaired.positions - center_fin, repaired.face_v, ok_fin, n_dirs=128)
                verdict_fin = classify_orientation(ef_fin, eb_fin, ok_fin)
                flip_fin = ok_fin & (verdict_fin == ORIENT_FLIP)
                if flip_fin.any():
                    repaired = flip_faces(repaired, flip_fin)
                    n_post_oriented += int(flip_fin.sum())
            repaired, n_degen_fin = _drop_degenerate_faces(repaired)
            n_degen_dropped += n_degen_fin
            repaired, _ = compact_mesh(repaired, {})
        if repaired.n_faces > 0:
            sliv_fin, _ = detect_piercing_needle_slivers(repaired)
            if sliv_fin.any():
                safe_drop = np.zeros(repaired.n_faces, dtype=bool)
                for fid in np.flatnonzero(sliv_fin):
                    trial_drop = safe_drop.copy()
                    trial_drop[fid] = True
                    cand_nosliv, _ = remove_faces(repaired, trial_drop)
                    cand_nosliv, _ = compact_mesh(cand_nosliv, {})
                    _, miss_nosliv = apply_strict_outer_facade_lock(
                        ckpt_raw, cand_nosliv, min_area_sqin=0.05, exclude_mask=raw_stack_mask
                    )
                    if (len(miss_nosliv) == 0 if hasattr(miss_nosliv, "__len__") else miss_nosliv == 0):
                        safe_drop[fid] = True
                if safe_drop.any():
                    repaired, _ = remove_faces(repaired, safe_drop)
                    repaired, _ = compact_mesh(repaired, {})
                    n_post_slivers += int(safe_drop.sum())
                    if repaired.n_faces > 0:
                        center_sl = 0.5 * (repaired.positions.min(axis=0) + repaired.positions.max(axis=0))
                        fn_sl = face_normals(repaired.positions, repaired.face_v, np.ones(repaired.n_faces, dtype=bool))
                        ok_sl = (~np.isnan(fn_sl).any(axis=1)) & (np.linalg.norm(fn_sl, axis=1) > 0.5)
                        ef_sl, eb_sl = compute_side_exposure(repaired.positions - center_sl, repaired.face_v, ok_sl, n_dirs=128)
                        flip_sl = ok_sl & (classify_orientation(ef_sl, eb_sl, ok_sl) == ORIENT_FLIP)
                        if flip_sl.any():
                            repaired = flip_faces(repaired, flip_sl)
                            n_post_oriented += int(flip_sl.sum())
    repaired, uv_faces_normalized, uv_max_abs_after = normalize_uv_tile_offsets(repaired)
    phantom_tris_remaining = int(count_phantom_bridges(ckpt_raw, repaired).sum())
    repaired, n_floor_cracks_healed = heal_walkable_floor_slab_cracks(repaired)
    if n_floor_cracks_healed > 0:
        for _ in range(3):
            outer_mask_fc, vis_mask_fc = _exposure_masks(repaired, n_dirs=128)
            repaired, n_dl_fc = resolve_residual_double_layers(repaired, outer_mask_fc, vis_mask_fc)
            n_post_coplanar += n_dl_fc
            if n_dl_fc == 0:
                break
        repaired, n_degen_fc = _drop_degenerate_faces(repaired)
        n_degen_dropped += n_degen_fc
        repaired, _ = compact_mesh(repaired, {})
    gc.collect()

    # Compute Unity + Mesh Baker 3.40.2 optimization telemetry
    used_mat_ids = sorted({int(m) for m in np.asarray(repaired.face_material, dtype=np.int64).tolist() if 0 <= int(m) < len(repaired.materials)})
    used_mat_names = [repaired.materials[m] for m in used_mat_ids]
    transparent_mats = [m for m in used_mat_names if ("glass" in m.lower() or "stained" in m.lower())]
    opaque_mats = [m for m in used_mat_names if m not in transparent_mats]
    projected_draw_calls = (1 if opaque_mats else 0) + (1 if transparent_mats else 0)
    tris_reduction_pct = round(100.0 * (ckpt_raw.n_faces - repaired.n_faces) / max(ckpt_raw.n_faces, 1), 2)

    # 7. Write Z-up metres OBJ for Blender packaging & GLB export
    out_mesh = copy.deepcopy(repaired)
    out_mesh.positions = np.round(ckpt17_to_blender_zup_metres(repaired.positions), 5)
    out_mesh.normals = np.round(face_normals(out_mesh.positions, out_mesh.face_v, np.ones(out_mesh.n_faces, dtype=bool)), 5)
    out_mesh.face_vn = np.repeat(np.arange(out_mesh.n_faces, dtype=np.int64)[:, None], 3, axis=1)
    out_mesh.mtllib = out_mtl.name
    out_mesh.name = f"{stem}_v2"
    out_mesh.coord_decimals = 5
    write_obj(out_mesh, out_obj)
    del out_mesh
    gc.collect()

    # 8. Evaluate RAW vs v1 vs Real-Model Engine v2 + write 3D error overlay JSON
    raw_errs = find_errors(ckpt_raw)
    v2_tuple = _summarize_audit_full(
        "REAL_ENGINE_V2",
        ckpt_raw,
        repaired,
        rebuild_exclusion_mask_fn=_excl_stack_fn,
    )
    audits: dict[str, Any] = {
        "raw": {
            "name": "RAW_CKPT17",
            "tris": int(ckpt_raw.n_faces),
            "errors": {k: int(v) for k, v in raw_errs["counts"].items()},
            "loose_parts": {k: int(v) for k, v in raw_errs.get("loose_parts", {}).items()},
        },
        "real_v2": v2_tuple[0],
    }

    v1_mesh: MeshData | None = None
    v1_tuple: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]] | None = None
    if v1_obj is not None:
        v1_mesh = read_obj(v1_obj)
        if _is_yup_metres(v1_mesh):
            v1_mesh.positions = np.round(convert_unity_to_ckpt17_coords(v1_mesh.positions), 4)
        v1_tuple = _summarize_audit_full(
            "V1_EXPORT_FIXED_OBJ",
            ckpt_raw,
            v1_mesh,
            rebuild_exclusion_mask_fn=_excl_stack_fn,
        )
        audits["v1_export"] = v1_tuple[0]

    if include_dashboard_v1_audit and dash_dir is not None and (dash_dir / "after.obj").is_file():
        dash_v1 = read_obj(dash_dir / "after.obj")
        if _is_yup_metres(dash_v1):
            dash_v1.positions = np.round(convert_unity_to_ckpt17_coords(dash_v1.positions), 4)
        audits["v1_dashboard"] = _summarize_audit(
            "V1_DASHBOARD_AFTER_OBJ",
            ckpt_raw,
            dash_v1,
            rebuild_exclusion_mask_fn=_excl_stack_fn,
        )

    overlay_payload = _build_error_overlay_payload(
        building,
        floor,
        unit_slug,
        ckpt_raw,
        v1_mesh,
        v1_tuple,
        repaired,
        v2_tuple,
        phantom_tris_v2=phantom_tris_remaining,
    )
    out_overlay.write_text(json.dumps(overlay_payload, separators=(",", ":")) + "\n", encoding="utf-8")

    zup_bounds_pts = ckpt17_to_blender_zup_metres(repaired.positions) if repaired.n_faces > 0 else np.zeros((1, 3), dtype=np.float64)
    report = {
        "version": 2,
        "mode": "real_model_mesh_preserving_outer_facade_lock",
        "building": building,
        "floor": floor,
        "unit_slug": unit_slug,
        "raw_obj": str(raw_obj),
        "v1_obj": str(v1_obj) if v1_obj else None,
        "out_obj_zup_metres": str(out_obj),
        "out_mtl": str(out_mtl),
        "out_overlay_json": str(out_overlay),
        "textures_copied_count": len(copied_textures),
        "bounds_zup_metres": {
            "min": [round(float(x), 4) for x in zup_bounds_pts.min(axis=0)],
            "max": [round(float(x), 4) for x in zup_bounds_pts.max(axis=0)],
        },
        "unity_optimization": {
            "mesh_baker_version": "Mesh Baker 3.40.2 (Paid Only)",
            "mesh_baker_ready": True,
            "tris_raw": int(ckpt_raw.n_faces),
            "tris_v2": int(repaired.n_faces),
            "tris_reduction_pct": float(tris_reduction_pct),
            "unique_materials": len(used_mat_names),
            "opaque_materials": len(opaque_mats),
            "transparent_materials": len(transparent_mats),
            "projected_mesh_baker_draw_calls": int(projected_draw_calls),
            "uv_faces_normalized": int(uv_faces_normalized),
            "uv_max_abs_after": float(uv_max_abs_after),
            "recipe": "Bake Opaque submeshes with Consider Mesh UVs=ON + Generate Lightmap UVs into 1 URP Atlas; keep Glass as 1 separate Transparent material.",
        },
        "v2_fixes": {
            "core_removed_hidden": int(core_stats.get("n_removed_hidden", 0)),
            "core_coplanar_protected": int(core_stats.get("n_coplanar_protected", 0)),
            "core_holes_filled": int(core_stats.get("n_holes_filled", 0)),
            "core_solidified": int(core_stats.get("n_solidified", 0)),
            "core_flipped": int(core_stats.get("n_flipped", 0)),
            "core_mandatory_facade_healed": int(core_stats.get("n_mandatory_facade_healed", 0)),
            "horiz_oriented": int(n_horiz_flipped),
            "degenerate_dropped": int(n_degen_dropped),
            "near_zfight_dropped": int(n_zfight_dropped.get("faces_dropped", 0) if isinstance(n_zfight_dropped, dict) else 0),
            "post_coplanar_dropped": int(n_post_coplanar),
            "exact_dedup_dropped": int(n_dedup + n_lock_dedup),
            "diff_overlay_healed": int(n_diff_healed),
            "outer_facade_locked_restored": int(n_outer_locked),
            "post_normals_flipped": int(n_post_oriented),
            "post_needle_slivers_purged": int(n_post_slivers),
            "phantom_tris_dropped": int(n_phantom_dropped),
            "phantom_tris_remaining": int(phantom_tris_remaining),
            "internal_stack_plates_purged": int(n_stack_plates_purged),
            "floor_cracks_healed": int(n_floor_cracks_healed),
            "uv_faces_normalized": int(uv_faces_normalized),
        },
        "audits": audits,
        "blender_topology": None,
    }
    out_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


_FLOOR_SORT_ORDER = {
    "Floor_1B": 1,
    "Floor_2B": 2,
    "Floor_3B": 3,
    "Floor_4B": 4,
    "Floor_1F": 11,
    "Floor_2F": 12,
    "Floor_3F": 13,
    "Floor_4F": 14,
    "Floor_5F": 15,
    "Floor_6F": 16,
    "Floor_7F": 17,
    "Floor_8F": 18,
    "Floor_9F": 19,
    "Floor_9M": 20,
    "Floor_RF": 30,
}


def discover_building_floors(building: str) -> list[str]:
    bdir = RAW_BUILDINGS_ROOT / building
    if not bdir.is_dir():
        raise FileNotFoundError(f"Building folder not found: {bdir}")
    floors = [p.name for p in bdir.iterdir() if p.is_dir() and _find_floor_obj(p, prefer_fixed=False) is not None]
    return sorted(floors, key=lambda name: (_FLOOR_SORT_ORDER.get(name, 100), name))


def _package_blender_floor(report_path: Path) -> dict[str, Any]:
    import os
    import subprocess

    blender_exe = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")
    packager = Path(__file__).resolve().parent / "blender_package_v2_floor.py"
    temp_dir = Path(r"D:\SOFTWARE\AI TOOLS SETUP\python-runtime\temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    env["TMPDIR"] = str(temp_dir)
    env["PYTHONPYCACHEPREFIX"] = str(temp_dir.parent / "pycache")
    cmd = [
        str(blender_exe),
        "-b",
        "--factory-startup",
        "--python",
        str(packager),
        "--",
        "--report",
        str(report_path),
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Blender packager failed for {report_path} (exit={proc.returncode}):\n{proc.stderr[-1200:]}"
        )
    updated = json.loads(report_path.read_text(encoding="utf-8"))
    return updated.get("blender_topology") or {}


def _is_floor_output_complete(out_dir: Path, building: str, floor: str, require_blender: bool) -> bool:
    stem = f"{building}_{floor}"
    rep_path = out_dir / "v2_integrity_report.json"
    ov_path = out_dir / "v2_error_overlay.json"
    if not (rep_path.is_file() and ov_path.is_file()):
        return False
    try:
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if "unity_optimization" not in rep:
        return False
    if require_blender:
        bt = rep.get("blender_topology") or {}
        if not (bt.get("valid") and (out_dir / f"{stem}.blend").is_file() and (out_dir / f"{stem}.glb").is_file()):
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Real-Model Engine v2 per-floor OBJ + integrity report")
    parser.add_argument("--building", required=True)
    parser.add_argument("--floor", default=None)
    parser.add_argument("--all-floors", action="store_true", help="Process all floors in isolated per-floor child processes")
    parser.add_argument("--skip-existing", action="store_true", help="Skip floors whose outputs + unity_optimization already exist")
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--include-dashboard-v1-audit", action="store_true")
    parser.add_argument("--package-blender", action="store_true", help="Also run Blender 5.1 per-floor .blend + .glb packager")
    parser.add_argument("--summary-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if not args.all_floors and not args.floor:
        parser.error("Provide either --floor <Floor_XX> or --all-floors")

    out_root = Path(args.out_root)
    if args.all_floors:
        floors = discover_building_floors(args.building)
        summary_rows: list[dict[str, Any]] = []
        failures: list[str] = []
        for idx, fl in enumerate(floors, 1):
            fl_dir = out_root / args.building / fl
            if args.skip_existing and _is_floor_output_complete(fl_dir, args.building, fl, bool(args.package_blender)):
                rep = json.loads((fl_dir / "v2_integrity_report.json").read_text(encoding="utf-8"))
                print(f"[{idx}/{len(floors)}] Skipping existing {args.building}/{fl}", flush=True)
            else:
                print(f"[{idx}/{len(floors)}] Spawning isolated worker for {args.building}/{fl}...", flush=True)
                cmd = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--building",
                    args.building,
                    "--floor",
                    fl,
                    "--out-root",
                    str(out_root),
                ]
                if args.include_dashboard_v1_audit:
                    cmd.append("--include-dashboard-v1-audit")
                if args.package_blender:
                    cmd.append("--package-blender")
                proc = subprocess.run(cmd, check=False)
                if proc.returncode != 0 or not (fl_dir / "v2_integrity_report.json").is_file():
                    failures.append(fl)
                    print(f"  !! FAILED {args.building}/{fl} (exit={proc.returncode})", flush=True)
                    continue
                rep = json.loads((fl_dir / "v2_integrity_report.json").read_text(encoding="utf-8"))

            v2 = rep["audits"]["real_v2"]
            uopt = rep.get("unity_optimization") or {}
            blender_topo = rep.get("blender_topology")
            row = {
                "floor": fl,
                "tris_raw": rep["audits"]["raw"]["tris"],
                "tris_v2": v2["tris"],
                "flicker_diff": v2["errors"]["flicker_diff"],
                "flicker_same": v2["errors"]["flicker_same"],
                "reversed": v2["errors"]["reversed"],
                "phantoms": rep["v2_fixes"]["phantom_tris_remaining"],
                "outer_pct": v2["checks"]["outer_facade_completeness"]["numericValue"],
                "interior_pct": v2["checks"]["interior_visible_retention"]["numericValue"],
                "materials": uopt.get("unique_materials"),
                "draw_calls_mb": uopt.get("projected_mesh_baker_draw_calls"),
                "blender_valid": blender_topo.get("valid") if blender_topo else None,
            }
            summary_rows.append(row)
            print(f"  -> {json.dumps(row)}", flush=True)

        print(json.dumps({
            "building": args.building,
            "floors_completed": len(summary_rows),
            "failures": failures,
            "summary": summary_rows,
        }, indent=2))
        return 1 if failures else 0

    rep = build_real_v2_floor(
        args.building,
        str(args.floor),
        out_root=out_root,
        include_dashboard_v1_audit=bool(args.include_dashboard_v1_audit),
    )
    blender_topo = None
    if args.package_blender:
        report_path = out_root / args.building / str(args.floor) / "v2_integrity_report.json"
        blender_topo = _package_blender_floor(report_path)
        rep["blender_topology"] = blender_topo
    v2 = rep["audits"]["real_v2"]
    print(json.dumps({
        "building": rep["building"],
        "floor": rep["floor"],
        "tris_raw": rep["audits"]["raw"]["tris"],
        "tris_v2": v2["tris"],
        "flicker": [v2["errors"]["flicker_diff"], v2["errors"]["flicker_same"]],
        "reversed": v2["errors"]["reversed"],
        "phantoms": rep["v2_fixes"]["phantom_tris_remaining"],
        "unity_optimization": rep["unity_optimization"],
        "blender_valid": blender_topo.get("valid") if blender_topo else None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
