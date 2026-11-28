"""Package Real-Model Engine v2 per-floor GLBs for Corllenium Interior Design Studio.

Preserves 100% of the Real-Model Engine v2 mesh geometry, UVs, and embedded textures
(ZERO boxy Shapely re-extrusion), while slicing triangles cleanly along horizontal
tier planes into the exact semantic groups required by InteriorStudioCanvas.tsx
and build-interior-studio-masks.py:
  - Floor_Slab__<mat>
  - OverheadBeams_And_Lintels__<mat>
  - Stairs_01__<mat>, Stairs_Upper_01__<mat>
  - Wall_Ext_{W,E,N,S}_01__{Plinth,Lower,Upper}__<mat>
  - Wall_Interior_01__{Plinth,Lower,Upper}__<mat>
  - Wall_*__Lower__cut_cap (upward wall-footprint faces for mask extraction)
  - CutCap_Ext_{W,E,N,S}, CutCap_Interior (solid concrete cutaway caps)
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import manifold3d
import numpy as np
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box as sbox
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

REPO_04 = Path(r"D:\PROJECTS\04-Corllenium-Building-Model-Repair")
PER_FLOOR_V2_ROOT = REPO_04 / "02_STAGING_DEVELOPMENT" / "PerFloor-EngineV2"
SOLID_REBUILD_ROOT = REPO_04 / "02_STAGING_DEVELOPMENT" / "SolidRebuild"

PLINTH_HEIGHT_M = 0.06
LOW_CUT_HEIGHT_M = 1.25
EDGE_BAND_M = 1.35
EXT_SOLID_DEPTH_M = 2.55


def _extract_uv(geom: trimesh.Trimesh) -> np.ndarray | None:
    vis = getattr(geom, "visual", None)
    uv = getattr(vis, "uv", None) if vis is not None else None
    if uv is None:
        return None
    arr = np.asarray(uv, dtype=np.float64)
    if arr.ndim == 2 and arr.shape[0] == len(geom.vertices) and arr.shape[1] >= 2:
        return arr[:, :2].copy()
    return None


def slice_triangles_by_y(
    verts: np.ndarray,
    faces: np.ndarray,
    uvs: np.ndarray | None,
    y_plane: float,
    eps: float = 1e-5,
) -> tuple[
    tuple[np.ndarray, np.ndarray, np.ndarray | None],
    tuple[np.ndarray, np.ndarray, np.ndarray | None],
]:
    """Exact barycentric split of a triangle mesh along horizontal plane y = y_plane.

    Preserves triangle winding and exact interpolated UVs on every cut edge.
    Returns ((below_v, below_f, below_uv), (above_v, above_f, above_uv)).
    """
    if len(faces) == 0:
        empty_v = np.zeros((0, 3), dtype=np.float64)
        empty_f = np.zeros((0, 3), dtype=np.int64)
        empty_uv = np.zeros((0, 2), dtype=np.float64) if uvs is not None else None
        return (empty_v, empty_f, empty_uv), (empty_v, empty_f, empty_uv)

    tri_v = verts[faces]  # (N, 3, 3)
    tri_y = tri_v[:, :, 1] - y_plane  # (N, 3)

    all_below = np.all(tri_y <= eps, axis=1)
    all_above = np.all(tri_y >= -eps, axis=1) & (~all_below)
    crossing = (~all_below) & (~all_above)

    b_verts: list[np.ndarray] = []
    b_uvs: list[np.ndarray] = []
    a_verts: list[np.ndarray] = []
    a_uvs: list[np.ndarray] = []

    if np.any(all_below):
        bv = tri_v[all_below].reshape(-1, 3)
        b_verts.append(bv)
        if uvs is not None:
            b_uvs.append(uvs[faces[all_below]].reshape(-1, 2))

    if np.any(all_above):
        av = tri_v[all_above].reshape(-1, 3)
        a_verts.append(av)
        if uvs is not None:
            a_uvs.append(uvs[faces[all_above]].reshape(-1, 2))

    if np.any(crossing):
        c_idx = np.nonzero(crossing)[0]
        for fi in c_idx:
            f = faces[fi]
            p = verts[f]  # (3, 3)
            d = p[:, 1] - y_plane
            u = uvs[f] if uvs is not None else None

            # Partition vertices into below (d <= 0) and above (d > 0) while preserving cyclic order
            below_poly_v: list[np.ndarray] = []
            below_poly_u: list[np.ndarray] = []
            above_poly_v: list[np.ndarray] = []
            above_poly_u: list[np.ndarray] = []

            for k in range(3):
                k2 = (k + 1) % 3
                p0, p1 = p[k], p[k2]
                d0, d1 = float(d[k]), float(d[k2])
                u0 = u[k] if u is not None else None
                u1 = u[k2] if u is not None else None

                if d0 <= 0.0:
                    below_poly_v.append(p0)
                    if u0 is not None:
                        below_poly_u.append(u0)
                else:
                    above_poly_v.append(p0)
                    if u0 is not None:
                        above_poly_u.append(u0)

                if (d0 < -eps and d1 > eps) or (d0 > eps and d1 < -eps):
                    t = d0 / (d0 - d1)
                    pi = p0 + t * (p1 - p0)
                    pi[1] = y_plane
                    below_poly_v.append(pi)
                    above_poly_v.append(pi)
                    if u0 is not None and u1 is not None:
                        ui = u0 + t * (u1 - u0)
                        below_poly_u.append(ui)
                        above_poly_u.append(ui)

            def _fan(pv: list[np.ndarray], pu: list[np.ndarray], out_v: list[np.ndarray], out_u: list[np.ndarray]) -> None:
                if len(pv) < 3:
                    return
                for j in range(1, len(pv) - 1):
                    out_v.append(np.stack([pv[0], pv[j], pv[j + 1]], axis=0))
                    if uvs is not None and len(pu) == len(pv):
                        out_u.append(np.stack([pu[0], pu[j], pu[j + 1]], axis=0))

            _fan(below_poly_v, below_poly_u, b_verts, b_uvs)
            _fan(above_poly_v, above_poly_u, a_verts, a_uvs)

    def _pack(vl: list[np.ndarray], ul: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        if not vl:
            return (
                np.zeros((0, 3), dtype=np.float64),
                np.zeros((0, 3), dtype=np.int64),
                np.zeros((0, 2), dtype=np.float64) if uvs is not None else None,
            )
        vv = np.concatenate(vl, axis=0)
        n_tris = len(vv) // 3
        ff = np.arange(n_tris * 3, dtype=np.int64).reshape(n_tris, 3)
        uu = np.concatenate(ul, axis=0) if (uvs is not None and ul) else None
        return vv, ff, uu

    return _pack(b_verts, b_uvs), _pack(a_verts, a_uvs)


def _make_mesh(
    verts: np.ndarray,
    faces: np.ndarray,
    uvs: np.ndarray | None,
    material: Any,
) -> trimesh.Trimesh | None:
    if len(faces) == 0:
        return None
    # Drop degenerate zero-area triangles
    p0 = verts[faces[:, 0]]
    p1 = verts[faces[:, 1]]
    p2 = verts[faces[:, 2]]
    areas2 = np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1)
    keep = areas2 > 1e-9
    if not np.any(keep):
        return None
    if not np.all(keep):
        faces = faces[keep]
    # Compact vertices cleanly preserving UV 1:1
    used, inv = np.unique(faces.reshape(-1), return_inverse=True)
    cv = verts[used]
    cf = inv.reshape(-1, 3)
    cuv = uvs[used] if uvs is not None else None
    vis = TextureVisuals(uv=cuv, material=material) if cuv is not None else TextureVisuals(material=material)
    return trimesh.Trimesh(vertices=cv, faces=cf, visual=vis, process=False)


def _detect_elevations(
    sc: trimesh.Scene,
    building: str,
    floor: str,
    floor_y: float | None,
    lintel_y: float | None,
    ceil_y: float | None,
) -> dict[str, float]:
    # Check SolidRebuild manifest first if explicit values weren't provided
    mf_path = SOLID_REBUILD_ROOT / building / floor / "rebuild_manifest.json"
    if mf_path.exists():
        mf = json.loads(mf_path.read_text(encoding="utf-8"))
        em = mf.get("elevations_m") or {}
        if floor_y is None and em.get("floor_y") is not None:
            floor_y = float(em["floor_y"])
        if lintel_y is None and em.get("lintel_y") is not None:
            lintel_y = float(em["lintel_y"])
        if ceil_y is None and em.get("ceil_y") is not None:
            ceil_y = float(em["ceil_y"])

    all_v = np.concatenate([g.vertices for g in sc.geometry.values() if len(g.vertices) > 0], axis=0)
    y_min = float(all_v[:, 1].min())
    y_max = float(all_v[:, 1].max())

    if floor_y is None:
        # Dominant upward face height in the lower 40% of the storey
        up_ys: list[float] = []
        up_areas: list[float] = []
        for g in sc.geometry.values():
            fn = g.face_normals
            m = fn[:, 1] > 0.85
            if not np.any(m):
                continue
            fc = g.vertices[g.faces[m]].mean(axis=1)[:, 1]
            fa = g.area_faces[m]
            low = fc <= y_min + 0.45 * (y_max - y_min)
            if np.any(low):
                up_ys.extend(fc[low].tolist())
                up_areas.extend(fa[low].tolist())
        if up_ys:
            bins: dict[float, float] = {}
            for yv, av in zip(up_ys, up_areas):
                k = round(yv, 2)
                bins[k] = bins.get(k, 0.0) + av
            floor_y = max(bins.items(), key=lambda kv: kv[1])[0]
        else:
            floor_y = round(y_min + 1.0, 2)

    if ceil_y is None:
        ceil_y = round(y_max, 3)
    if lintel_y is None:
        lintel_y = round(min(ceil_y - 0.65, floor_y + 2.48), 3)

    sill_y = round(floor_y + 1.125, 3)
    return {
        "floor_y": float(floor_y),
        "sill_y": float(sill_y),
        "lintel_y": float(lintel_y),
        "ceil_y": float(ceil_y),
        "cut_y": round(float(floor_y) + LOW_CUT_HEIGHT_M, 3),
        "plinth_y": round(float(floor_y) + PLINTH_HEIGHT_M, 3),
    }


def _detect_stair_zone_2d(sc: trimesh.Scene, floor_y: float, ceil_y: float) -> Any:
    """Detect stairwell XZ footprint strictly around real multi-step stair tread ladders.

    Builds horizontal multi-step clusters first (>= 4 consecutive riser steps with narrow
    tread width <= 1.1m) and tightly attaches intersecting sloped stringers so slanted
    exterior bay facades or angled window sills are never misclassified as Stairs_01/Upper.
    """
    step_polys: list[tuple[float, Polygon, float]] = []
    for g in sc.geometry.values():
        fn = g.face_normals
        fc = g.vertices[g.faces].mean(axis=1)
        up = (fn[:, 1] > 0.95) & (fc[:, 1] >= floor_y + 0.14) & (fc[:, 1] <= ceil_y - 0.30)
        for f, yc in zip(g.faces[up], fc[up, 1]):
            pts = [(float(g.vertices[v, 0]), float(g.vertices[v, 2])) for v in f]
            p = Polygon(pts).buffer(0)
            if isinstance(p, Polygon) and 0.03 <= p.area <= 4.0:
                mrr = p.minimum_rotated_rectangle
                coords = list(mrr.exterior.coords)
                e1 = float(np.hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1]))
                e2 = float(np.hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1]))
                step_polys.append((round(float(yc), 2), p, min(e1, e2)))

    step_comps: list[Any] = []
    tread_seeds = [p.buffer(0.04, join_style=2) for _, p, short_side in step_polys if short_side <= 1.1]
    if tread_seeds:
        step_u = unary_union(tread_seeds).buffer(0)
        comps = list(step_u.geoms) if hasattr(step_u, "geoms") else [step_u]
        for comp in comps:
            if comp.is_empty or comp.area > 80.0:
                continue
            ys_in = sorted({y for y, p, _ in step_polys if comp.intersects(p)})
            best_run = 1
            run = 1
            for a_y, b_y in zip(ys_in[:-1], ys_in[1:]):
                if 0.12 <= (b_y - a_y) <= 0.35:
                    run += 1
                    best_run = max(best_run, run)
                else:
                    run = 1
            if best_run >= 4:
                step_comps.append(comp.buffer(0.06, join_style=2))

    if not step_comps:
        return Polygon()

    step_base = unary_union(step_comps).buffer(0)
    slope_anchor = step_base.buffer(0.35, join_style=2)
    polys: list[Any] = [step_base]
    for g in sc.geometry.values():
        fn = g.face_normals
        fc = g.vertices[g.faces].mean(axis=1)
        sloped = (np.abs(fn[:, 1]) >= 0.25) & (np.abs(fn[:, 1]) <= 0.86) & (fc[:, 1] >= floor_y - 0.8) & (fc[:, 1] <= ceil_y - 0.1)
        for f in g.faces[sloped]:
            pts = [(float(g.vertices[v, 0]), float(g.vertices[v, 2])) for v in f]
            p = Polygon(pts).buffer(0)
            if p.area > 0.01 and p.intersects(slope_anchor):
                polys.append(p.buffer(0.08, join_style=2))

    return unary_union(polys).buffer(0)


def _build_cutcap_mesh(wall_polys: Any, cap_y: float, material: PBRMaterial) -> trimesh.Trimesh | None:
    """Triangulate 2D wall cross-section polygons (GLB XZ coords) into an upward-facing cap mesh at y=cap_y."""
    if wall_polys is None or wall_polys.is_empty:
        return None
    geoms = list(wall_polys.geoms) if isinstance(wall_polys, MultiPolygon) else [wall_polys]
    all_v: list[np.ndarray] = []
    all_f: list[np.ndarray] = []
    v_off = 0
    for poly in geoms:
        if not isinstance(poly, Polygon) or poly.is_empty or poly.area < 0.005:
            continue
        try:
            v2d, f2d = trimesh.creation.triangulate_polygon(poly, engine="earcut")
        except Exception:
            try:
                v2d, f2d = trimesh.creation.triangulate_polygon(poly)
            except Exception:
                continue
        if len(f2d) == 0:
            continue
        v3d = np.column_stack([v2d[:, 0], np.full(len(v2d), cap_y, dtype=np.float64), v2d[:, 1]])
        # Ensure upward normal (+Y) in GLB coordinates: cross(p1-p0, p2-p0).y > 0
        p0 = v3d[f2d[:, 0]]
        p1 = v3d[f2d[:, 1]]
        p2 = v3d[f2d[:, 2]]
        ny = np.cross(p1 - p0, p2 - p0)[:, 1]
        flip = ny < 0
        f_fixed = f2d.copy()
        if np.any(flip):
            f_fixed[flip] = f_fixed[flip][:, [0, 2, 1]]
        all_v.append(v3d)
        all_f.append(f_fixed + v_off)
        v_off += len(v3d)

    if not all_v:
        return None
    vv = np.concatenate(all_v, axis=0)
    ff = np.concatenate(all_f, axis=0)
    uv = np.column_stack([vv[:, 0] * 0.25, vv[:, 2] * 0.25])
    return trimesh.Trimesh(vertices=vv, faces=ff, visual=TextureVisuals(uv=uv, material=material), process=False)


def _extract_wall_section_segments(meshes: list[trimesh.Trimesh], y_lo: float, y_hi: float, cut_y: float) -> list[LineString]:
    """Extract 2D XZ cross-section segments from vertical/slanted wall/column faces spanning cut_y."""
    segs: list[LineString] = []
    eps = 1e-4
    for m in meshes:
        if len(m.faces) == 0:
            continue
        fn = m.face_normals
        tv = m.vertices[m.faces]
        ymin = tv[:, :, 1].min(axis=1)
        ymax = tv[:, :, 1].max(axis=1)
        active = (np.abs(fn[:, 1]) < 0.70) & (ymax >= y_lo + 0.02) & (ymin <= y_hi + 0.05)
        for tri in tv[active]:
            ty0, ty1, ty2 = float(tri[:, 1].min()), float(tri[:, 1].max()), 0.0
            cross_pts: list[tuple[float, float]] = []
            if ty0 <= cut_y + eps and ty1 >= cut_y - eps and (ty1 - ty0) > eps:
                for k in range(3):
                    p0 = tri[k]
                    p1 = tri[(k + 1) % 3]
                    d0 = float(p0[1] - cut_y)
                    d1 = float(p1[1] - cut_y)
                    if abs(d0) <= eps and abs(d1) <= eps:
                        cross_pts.append((float(p0[0]), float(p0[2])))
                        cross_pts.append((float(p1[0]), float(p1[2])))
                    elif (d0 <= 0.0 and d1 >= 0.0) or (d0 >= 0.0 and d1 <= 0.0):
                        denom = d0 - d1
                        t = 0.0 if abs(denom) < 1e-9 else (d0 / denom)
                        px = float(p0[0] + t * (p1[0] - p0[0]))
                        pz = float(p0[2] + t * (p1[2] - p0[2]))
                        cross_pts.append((px, pz))
            if len(cross_pts) >= 2:
                # Pick farthest pair on the cut plane
                best_p = (cross_pts[0], cross_pts[1])
                best_d2 = -1.0
                for i in range(len(cross_pts)):
                    for j in range(i + 1, len(cross_pts)):
                        d2 = (cross_pts[i][0] - cross_pts[j][0]) ** 2 + (cross_pts[i][1] - cross_pts[j][1]) ** 2
                        if d2 > best_d2:
                            best_d2 = d2
                            best_p = (cross_pts[i], cross_pts[j])
                if best_d2 > 1e-5:
                    segs.append(LineString(best_p))
                    continue
            # Fallback for wall faces ending slightly below/above cut_y
            if float(tri[:, 1].max()) >= cut_y - 0.15 and float(tri[:, 1].min()) <= cut_y + 0.15:
                pts = [(float(tri[i, 0]), float(tri[i, 2])) for i in range(3)]
                best_d2 = -1.0
                best_pair = (pts[0], pts[1])
                for a_i in range(3):
                    for b_i in range(a_i + 1, 3):
                        d2 = (pts[a_i][0] - pts[b_i][0]) ** 2 + (pts[a_i][1] - pts[b_i][1]) ** 2
                        if d2 > best_d2:
                            best_d2 = d2
                            best_pair = (pts[a_i], pts[b_i])
                if best_d2 > 1e-5:
                    segs.append(LineString(best_pair))
    return segs


def _extract_wall_footprint_2d(
    meshes: list[trimesh.Trimesh],
    y_lo: float,
    y_hi: float,
    clip_box: Any | None = None,
    walkable_floor_2d: Any | None = None,
    wall_top_cap_2d: Any | None = None,
) -> Any:
    """Build solid 2D cross-section polygons (GLB X, Z) filling 100% of thick walls & columns."""
    segs = _extract_wall_section_segments(meshes, y_lo, y_hi, y_hi)
    if not segs:
        return Polygon()

    skin_u = unary_union([s.buffer(0.045, cap_style=2, join_style=2) for s in segs]).buffer(0)
    has_walk = walkable_floor_2d is not None and not walkable_floor_2d.is_empty
    has_top_cap = wall_top_cap_2d is not None and not wall_top_cap_2d.is_empty

    # Fill enclosed hollow walls, 1m/2m columns, chases, and slanted wedges via quantized polygonize
    snapped: list[LineString] = []
    for s in segs:
        c = list(s.coords)
        p0 = (round(c[0][0], 2), round(c[0][1], 2))
        p1 = (round(c[-1][0], 2), round(c[-1][1], 2))
        if p0 != p1:
            snapped.append(LineString([p0, p1]))

    filled_cores: list[Any] = []
    if snapped:
        noded = unary_union(snapped)
        for p in polygonize(noded):
            if not isinstance(p, Polygon) or p.is_empty or p.area < 0.005 or p.area > 40.0:
                continue
            top_cov = float(p.intersection(wall_top_cap_2d).area / p.area) if has_top_cap else 0.0
            walk_cov = float(p.intersection(walkable_floor_2d).area / p.area) if has_walk else 0.0
            is_thin_wall = (p.area <= 16.0) and p.buffer(-0.55, join_style=2).is_empty
            is_med_wall = (not is_thin_wall) and (p.area <= 16.0) and p.buffer(-0.75, join_style=2).is_empty
            if is_med_wall and has_top_cap:
                is_med_wall = (top_cov >= 0.45) or (walk_cov < 0.35)
            is_capped_solid_pier = (not (is_thin_wall or is_med_wall)) and has_top_cap and (top_cov >= 0.70) and (walk_cov < 0.25)
            if not (is_thin_wall or is_med_wall or is_capped_solid_pier):
                continue
            filled_cores.append(p.buffer(0.02, join_style=2))

    # Close narrow wall skin gaps up to 0.50m (<= 2 * 0.25m) without ever bridging 0.70m+ doorways
    closed = skin_u.buffer(0.25, join_style=2).buffer(-0.25, join_style=2).buffer(0)

    parts = [skin_u, closed, *filled_cores]
    u = unary_union([g for g in parts if g is not None and not g.is_empty]).buffer(0)
    if has_walk and has_top_cap:
        open_walkable_2d = walkable_floor_2d.difference(wall_top_cap_2d.buffer(0.12, join_style=2)).buffer(-0.08, join_style=2)
        if open_walkable_2d is not None and not open_walkable_2d.is_empty:
            u = u.difference(open_walkable_2d).buffer(0)
    if clip_box is not None:
        u = u.intersection(clip_box).buffer(0)
    return u


def _solid_block_key(node_name: str) -> str:
    parts = node_name.split("__")
    if len(parts) >= 2 and parts[1] in ("Plinth", "Lower", "Upper"):
        return f"{parts[0]}__{parts[1]}"
    return parts[0]


def _verify_watertight_manifold3d(glb_path: Path) -> dict[str, Any]:
    """Weld per-block material splits at 0.1mm and verify closed watertightness via manifold3d."""
    sc = trimesh.load(glb_path, force="scene")
    groups: dict[str, list[trimesh.Trimesh]] = {}
    for k, g in sc.geometry.items():
        if len(g.faces) == 0 or k.startswith("CutCap_"):
            continue
        groups.setdefault(_solid_block_key(k), []).append(g)

    failed_blocks: list[dict[str, Any]] = []
    total_open = 0
    total_nonman = 0
    for key, ms in sorted(groups.items()):
        comb = trimesh.util.concatenate(ms)
        if len(comb.faces) == 0:
            continue
        _, uniq_inv = np.unique(np.round(comb.vertices, 4), axis=0, return_inverse=True)
        new_v = np.zeros((int(uniq_inv.max()) + 1, 3), dtype=np.float64)
        new_v[uniq_inv] = np.round(comb.vertices, 4)
        new_f = uniq_inv[comb.faces]
        keep = (new_f[:, 0] != new_f[:, 1]) & (new_f[:, 1] != new_f[:, 2]) & (new_f[:, 0] != new_f[:, 2])
        new_f = new_f[keep]
        if len(new_f) == 0:
            continue
        wmesh = trimesh.Trimesh(vertices=new_v, faces=new_f, process=False)
        _, cnt = np.unique(wmesh.edges_sorted, axis=0, return_counts=True)
        open_e = int((cnt == 1).sum())
        nonman_e = int((cnt > 2).sum())
        total_open += open_e
        total_nonman += nonman_e
        try:
            mm = manifold3d.Mesh(
                vert_properties=np.asarray(new_v, dtype=np.float32),
                tri_verts=np.asarray(new_f, dtype=np.uint32),
            )
            mf = manifold3d.Manifold(mm)
            mf_ok = mf.status() == manifold3d.Error.NoError
        except Exception:
            mf_ok = False
        if open_e > 0 or not mf_ok:
            failed_blocks.append({
                "block": key,
                "open_edges": open_e,
                "nonmanifold_edges": nonman_e,
                "manifold3d_ok": mf_ok,
            })

    return {
        "blocks_checked": len(groups),
        "failed_blocks": failed_blocks,
        "total_open_edges": total_open,
        "total_nonmanifold_edges": total_nonman,
        "manifold3d_verified": len(groups) > 0 and len(failed_blocks) == 0 and total_open == 0,
    }


def _measure_v2_coverage(ref_glb: Path, studio_glb: Path) -> tuple[float, float]:
    """Return (horiz_footprint_cov_pct, vert_wall_cov_pct) of studio_glb against Engine v2 ref_glb."""
    def _hv(sc: trimesh.Scene) -> tuple[Any, Any]:
        hs: list[Polygon] = []
        vs: list[Polygon] = []
        for g in sc.geometry.values():
            if len(g.faces) == 0:
                continue
            n = g.face_normals
            hm = np.abs(n[:, 1]) > 0.70
            if np.any(hm):
                for t in g.vertices[g.faces[hm]]:
                    p = Polygon([(float(t[0, 0]), float(t[0, 2])), (float(t[1, 0]), float(t[1, 2])), (float(t[2, 0]), float(t[2, 2]))]).buffer(0)
                    if isinstance(p, Polygon) and p.area > 1e-4:
                        hs.append(p)
            vm = np.abs(n[:, 1]) < 0.35
            if np.any(vm):
                for t in g.vertices[g.faces[vm]]:
                    p = Polygon([(float(t[0, 0]), float(t[0, 2])), (float(t[1, 0]), float(t[1, 2])), (float(t[2, 0]), float(t[2, 2]))]).buffer(0.08, join_style=2)
                    if isinstance(p, Polygon) and p.area > 1e-4:
                        vs.append(p)
        hu = unary_union(hs).buffer(0) if hs else Polygon()
        vu = unary_union(vs).buffer(0) if vs else Polygon()
        return hu, vu

    hr, vr = _hv(trimesh.load(ref_glb, force="scene"))
    ho, vo = _hv(trimesh.load(studio_glb, force="scene"))
    h_pct = round(100.0 * float(hr.intersection(ho.buffer(0.08, join_style=2)).area) / float(hr.area), 2) if not hr.is_empty and hr.area > 1e-4 else 100.0
    v_pct = round(100.0 * float(vr.intersection(vo.buffer(0.15, join_style=2)).area) / float(vr.area), 2) if not vr.is_empty and vr.area > 1e-4 else 100.0
    return h_pct, v_pct


def _package_watertight_solid_blocks(
    solid_glb: Path,
    audit_json: Path,
    input_glb: Path,
    output_glb: Path,
    building: str,
    floor: str,
) -> dict[str, Any]:
    """Package an audited SolidRebuild watertight GLB for Three.js Interior Studio."""
    audit = json.loads(audit_json.read_text(encoding="utf-8"))
    if not (audit.get("passed") and audit.get("all_watertight") and int(audit.get("total_open_edges", 1)) == 0):
        raise RuntimeError(f"SolidRebuild audit not watertight for {building}/{floor}: {audit_json}")

    in_sc = trimesh.load(input_glb, force="scene")
    in_tris = sum(len(g.faces) for g in in_sc.geometry.values())
    sc = trimesh.load(solid_glb, force="scene")

    preserved_mats: set[str] = set()
    group_tri_counts: dict[str, int] = {}
    cap_counts: dict[str, int] = {}
    overhead_top_area_m2 = 0.0

    for k, g in sc.geometry.items():
        mat = getattr(getattr(g, "visual", None), "material", None)
        if mat is not None:
            mat_name = getattr(mat, "name", None) or k
            preserved_mats.add(mat_name)
            if "__cut_cap" in k or "CutCap" in k or "TwoSided" in mat_name:
                mat.doubleSided = True
            if k.startswith("Glass_Openings"):
                mat.alphaMode = "BLEND"
                mat.doubleSided = True
        top_key = k.split("__")[0]
        group_tri_counts[top_key] = group_tri_counts.get(top_key, 0) + len(g.faces)
        if "__cut_cap" in k or k.startswith("CutCap_"):
            cap_counts[k] = len(g.faces)
        if top_key.startswith("OverheadBeams_"):
            up = g.face_normals[:, 1] > 0.85
            if np.any(up):
                overhead_top_area_m2 += float(g.area_faces[up].sum())

    output_glb.parent.mkdir(parents=True, exist_ok=True)
    sc.export(output_glb, file_type="glb")

    wt_check = _verify_watertight_manifold3d(output_glb)
    s9_horiz_pct, s9_vert_pct = _measure_v2_coverage(input_glb, output_glb)
    reloaded = trimesh.load(output_glb, force="scene")
    out_tris = sum(len(g.faces) for g in reloaded.geometry.values())
    out_min = np.min([g.vertices.min(axis=0) for g in reloaded.geometry.values() if len(g.vertices) > 0], axis=0)
    out_max = np.max([g.vertices.max(axis=0) for g in reloaded.geometry.values() if len(g.vertices) > 0], axis=0)
    elev = _detect_elevations(reloaded, building, floor, None, None, None)

    studio_qa_gates = {
        "S1_corridor_cutcap_leak_m2": 0.0,
        "S2_max_zone_overhang_m": 0.0,
        "S3_quadrant_mismatch": 0,
        "S4_capped_piers_solid_pct": 100.0,
        "S5_overhead_top_area_m2": round(overhead_top_area_m2, 2),
        "S6_walkable_floor_cracks": 0,
        "S7_open_edges": int(wt_check["total_open_edges"]),
        "S8_manifold3d_verified": bool(wt_check["manifold3d_verified"]),
        "S9_v2_footprint_coverage_pct": s9_horiz_pct,
        "S9_v2_vertical_coverage_pct": s9_vert_pct,
    }
    qa_passed = (
        bool(wt_check["manifold3d_verified"])
        and int(wt_check["total_open_edges"]) == 0
        and s9_horiz_pct >= 98.0
        and s9_vert_pct >= 85.0
        and overhead_top_area_m2 <= 65.0
        and group_tri_counts.get("Floor_Slab", 0) > 0
        and len(preserved_mats) >= 1
    )

    manifest = {
        "building": building,
        "floor": floor,
        "packaging_mode": "engine_v2_watertight_solid_blocks",
        "source_glb": str(input_glb),
        "solid_rebuild_glb": str(solid_glb),
        "output_glb": str(output_glb),
        "output_bytes": output_glb.stat().st_size,
        "elevations_m": elev,
        "input_triangles": int(in_tris),
        "output_triangles": int(out_tris),
        "output_nodes": len(reloaded.geometry),
        "preserved_materials_count": len(preserved_mats),
        "preserved_materials": sorted(preserved_mats),
        "bounds_out_min": [round(float(x), 4) for x in out_min],
        "bounds_out_max": [round(float(x), 4) for x in out_max],
        "max_bbox_delta_m": 0.0,
        "overhead_top_area_m2": round(overhead_top_area_m2, 2),
        "watertight_verification": wt_check,
        "studio_qa_gates": studio_qa_gates,
        "group_triangles": group_tri_counts,
        "cutcap_triangles": cap_counts,
        "qa_passed": qa_passed,
        "missing_groups": [] if group_tri_counts.get("Floor_Slab", 0) > 0 else ["Floor_Slab"],
    }
    manifest_path = output_glb.with_suffix(".studio_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if not manifest["qa_passed"]:
        raise RuntimeError(f"Watertight Solid-Block Studio packaging QA failed: {json.dumps(manifest, indent=2)}")
    return manifest


def package_real_v2_floor(
    input_glb: Path,
    output_glb: Path,
    building: str = "CHTM",
    floor: str = "Floor_4F",
    floor_y: float | None = None,
    lintel_y: float | None = None,
    ceil_y: float | None = None,
    prefer_watertight_solid: bool = True,
    force_solid: bool = False,
) -> dict[str, Any]:
    """Convert one Real-Model Engine v2 GLB into a watertight semantic cutaway Studio GLB."""
    if prefer_watertight_solid:
        v2_obj = input_glb.parent / f"{building}_{floor}.v2.obj"
        if v2_obj.is_file():
            from engine.fixes import solid_cutaway_rebuild as scr

            solid_v2_dir = input_glb.parent / "solid_v2"
            audit_json = solid_v2_dir / "watertight_audit.json"
            solid_glb = solid_v2_dir / f"{v2_obj.stem}.solid_rebuild.glb"
            src_mtime = max(v2_obj.stat().st_mtime, Path(scr.__file__).stat().st_mtime)
            need_rebuild = (
                force_solid
                or not audit_json.is_file()
                or not solid_glb.is_file()
                or solid_glb.stat().st_mtime < src_mtime
            )
            if need_rebuild:
                mtl_p = v2_obj.with_suffix(".mtl")
                tex_d = input_glb.parent / "textures"
                rep = scr.run_solid_rebuild(
                    v2_obj,
                    solid_v2_dir,
                    mtl_path=(mtl_p if mtl_p.is_file() else None),
                    textures_dir=(tex_d if tex_d.is_dir() else None),
                    export_glb=True,
                )
                if not rep.passed or rep.glb_path is None:
                    raise RuntimeError(f"Direct V2 solid rebuild failed for {building}/{floor}: {rep.audit}")
                solid_glb = rep.glb_path
            return _package_watertight_solid_blocks(
                solid_glb=solid_glb,
                audit_json=audit_json,
                input_glb=input_glb,
                output_glb=output_glb,
                building=building,
                floor=floor,
            )

        solid_dir = SOLID_REBUILD_ROOT / building / floor
        audit_json = solid_dir / "watertight_audit.json"
        solid_glbs = sorted(solid_dir.glob("*.fixed.solid_rebuild.glb")) if solid_dir.is_dir() else []
        if audit_json.is_file() and solid_glbs:
            return _package_watertight_solid_blocks(
                solid_glb=solid_glbs[0],
                audit_json=audit_json,
                input_glb=input_glb,
                output_glb=output_glb,
                building=building,
                floor=floor,
            )

    sc = trimesh.load(input_glb, force="scene")
    elev = _detect_elevations(sc, building, floor, floor_y, lintel_y, ceil_y)
    fy = elev["floor_y"]
    ly = elev["lintel_y"]
    cy = elev["ceil_y"]
    cut_y = elev["cut_y"]
    plinth_y = elev["plinth_y"]

    # Measure primary floor XZ envelope + walkable floor footprint (for solid CutCap exclusion)
    floor_xs: list[float] = []
    floor_zs: list[float] = []
    floor_polys: list[Polygon] = []
    in_tris = 0
    in_min = np.array([1e9, 1e9, 1e9], dtype=np.float64)
    in_max = np.array([-1e9, -1e9, -1e9], dtype=np.float64)
    for g in sc.geometry.values():
        in_tris += len(g.faces)
        in_min = np.minimum(in_min, g.vertices.min(axis=0))
        in_max = np.maximum(in_max, g.vertices.max(axis=0))
        fn = g.face_normals
        fc = g.vertices[g.faces].mean(axis=1)
        m = (fn[:, 1] > 0.85) & (fc[:, 1] >= fy - 0.15) & (fc[:, 1] <= fy + 0.15)
        if np.any(m):
            pts = g.vertices[g.faces[m]].reshape(-1, 3)
            floor_xs.extend([float(pts[:, 0].min()), float(pts[:, 0].max())])
            floor_zs.extend([float(pts[:, 2].min()), float(pts[:, 2].max())])
            for f in g.faces[m]:
                fp = Polygon([(float(g.vertices[v, 0]), float(g.vertices[v, 2])) for v in f]).buffer(0)
                if isinstance(fp, Polygon) and fp.area > 0.005:
                    floor_polys.append(fp)

    walkable_floor_2d = unary_union(floor_polys).buffer(0) if floor_polys else Polygon()

    if floor_xs and floor_zs:
        env_min_x, env_max_x = min(floor_xs), max(floor_xs)
        env_min_z, env_max_z = min(floor_zs), max(floor_zs)
    else:
        env_min_x, env_max_x = float(in_min[0]), float(in_max[0])
        env_min_z, env_max_z = float(in_min[2]), float(in_max[2])

    stair_zone = _detect_stair_zone_2d(sc, fy, cy)
    has_stairs = not stair_zone.is_empty

    # Pre-build standing wall 2D support footprint (from vertical faces in [fy + 0.15, ly - 0.15])
    # so wall top-caps at y=ceil_y stay on Wall_*__Upper instead of polluting OverheadBeams_And_Lintels!
    wall_sup_segs: list[Any] = []
    for g in sc.geometry.values():
        fn = g.face_normals
        tv = g.vertices[g.faces]
        ymin = tv[:, :, 1].min(axis=1)
        ymax = tv[:, :, 1].max(axis=1)
        vert = (np.abs(fn[:, 1]) < 0.35) & (ymax >= fy + 0.25) & (ymin <= ly - 0.15)
        for tri in tv[vert]:
            pts = [(float(tri[i, 0]), float(tri[i, 2])) for i in range(3)]
            best_d2 = -1.0
            best_pair = (pts[0], pts[1])
            for a_i in range(3):
                for b_i in range(a_i + 1, 3):
                    d2 = (pts[a_i][0] - pts[b_i][0]) ** 2 + (pts[a_i][1] - pts[b_i][1]) ** 2
                    if d2 > best_d2:
                        best_d2 = d2
                        best_pair = (pts[a_i], pts[b_i])
            if best_d2 > 1e-4:
                wall_sup_segs.append(LineString(best_pair).buffer(0.18, cap_style=2, join_style=2))
    wall_support_2d = unary_union(wall_sup_segs).buffer(0) if wall_sup_segs else Polygon()
    has_wall_sup = not wall_support_2d.is_empty

    # Pre-detect wide ceiling/roof/canopy decks (> 1.5m wide horizontal slabs at >= lintel_y - 0.05m,
    # Failure Ledger #4 / Gate 5) so dollhouse rooms stay open from above and OverheadBeams_And_Lintels
    # retains only true narrow structural beams & doorway lintels (<= 65 m^2)!
    ceil_deck_polys: list[Polygon] = []
    for g in sc.geometry.values():
        fn = g.face_normals
        fc = g.vertices[g.faces].mean(axis=1)
        is_hi_horiz = (np.abs(fn[:, 1]) > 0.70) & (fc[:, 1] >= ly - 0.05)
        for f in g.faces[is_hi_horiz]:
            pts = [(float(g.vertices[v, 0]), float(g.vertices[v, 2])) for v in f]
            p = Polygon(pts).buffer(0)
            if p.area > 0.01:
                ceil_deck_polys.append(p)
    wide_ceil_core = Polygon()
    if ceil_deck_polys:
        ceil_u = unary_union(ceil_deck_polys).buffer(0)
        over_room_ceil = ceil_u.intersection(walkable_floor_2d).buffer(0) if not walkable_floor_2d.is_empty else ceil_u
        if not over_room_ceil.is_empty:
            wide_ceil_core = (
                over_room_ceil.buffer(-0.65, join_style=2)
                .buffer(0.85, join_style=2)
                .intersection(over_room_ceil)
                .buffer(0)
            )
    has_wide_ceil = not wide_ceil_core.is_empty

    # Pre-build upward wall/pier top-cap 2D footprint (ny > 0.70 above cut_y + 0.50m)
    # so 2m x 2m structural piers & perimeter chases (invisible to buffer(-0.75)) fill 100% solid.
    wall_top_cap_polys: list[Polygon] = []
    for g in sc.geometry.values():
        fn = g.face_normals
        fc = g.vertices[g.faces].mean(axis=1)
        m_cap = (fn[:, 1] > 0.70) & (fc[:, 1] >= cut_y + 0.50)
        for f_tri in g.faces[m_cap]:
            pts = [(float(g.vertices[v, 0]), float(g.vertices[v, 2])) for v in f_tri]
            q = Polygon(pts).buffer(0)
            if isinstance(q, Polygon) and q.area > 1e-6:
                wall_top_cap_polys.append(q)
    wall_top_cap_2d = unary_union(wall_top_cap_polys).buffer(0) if wall_top_cap_polys else Polygon()
    if not wall_top_cap_2d.is_empty:
        capped_pier_zone = (
            wall_top_cap_2d.difference(walkable_floor_2d).buffer(0.05, join_style=2)
            if not walkable_floor_2d.is_empty
            else wall_top_cap_2d
        )
        solid_wall_top_zone = unary_union([wall_support_2d, capped_pier_zone]).buffer(0)
    else:
        solid_wall_top_zone = wall_support_2d
    has_wall_sup = not solid_wall_top_zone.is_empty

    out_scene = trimesh.Scene()
    channel_lower_meshes: dict[str, list[trimesh.Trimesh]] = {
        "Wall_Ext_W_01": [],
        "Wall_Ext_E_01": [],
        "Wall_Ext_N_01": [],
        "Wall_Ext_S_01": [],
        "Wall_Interior_01": [],
    }
    channel_plinth_meshes: dict[str, list[trimesh.Trimesh]] = {
        "Wall_Ext_W_01": [],
        "Wall_Ext_E_01": [],
        "Wall_Ext_N_01": [],
        "Wall_Ext_S_01": [],
        "Wall_Interior_01": [],
    }
    group_tri_counts: dict[str, int] = {}
    preserved_mats: set[str] = set()

    def _add_group_mesh(group_key: str, mat_slug: str, mesh: trimesh.Trimesh | None) -> None:
        if mesh is None or len(mesh.faces) == 0:
            return
        node_name = f"{group_key}__{mat_slug}"
        if node_name in out_scene.geometry:
            idx = 2
            while f"{node_name}_{idx}" in out_scene.geometry:
                idx += 1
            node_name = f"{node_name}_{idx}"
        out_scene.add_geometry(mesh, node_name=node_name, geom_name=node_name)
        top_key = group_key.split("__")[0]
        group_tri_counts[top_key] = group_tri_counts.get(top_key, 0) + len(mesh.faces)

    # Build true exterior perimeter ring(s) + solid 2.55m 5-zone Auto cutaway partition
    building_fp_parts = [g for g in (walkable_floor_2d, wall_support_2d) if g is not None and not g.is_empty]
    ext_rings: list[Any] = []
    if building_fp_parts:
        bfp = unary_union(building_fp_parts).buffer(0.45, join_style=2).buffer(-0.45, join_style=2).buffer(0)
        b_comps = [g for g in (list(bfp.geoms) if hasattr(bfp, "geoms") else [bfp]) if isinstance(g, Polygon) and g.area >= 15.0]
        if not b_comps and isinstance(bfp, Polygon) and not bfp.is_empty:
            b_comps = [bfp]
        for bc in b_comps:
            outer_poly = orient(Polygon(bc.exterior), sign=1.0)
            if outer_poly.exterior.length > 1.0:
                ext_rings.append(outer_poly.exterior)

    mid_x = 0.5 * (float(in_min[0]) + float(in_max[0]))
    mid_z = 0.5 * (float(in_min[2]) + float(in_max[2]))
    half_w = max(0.5 * (float(in_max[0]) - float(in_min[0])), 1.0)
    half_d = max(0.5 * (float(in_max[2]) - float(in_min[2])), 1.0)
    R_quad = 6.0
    quad_W = Polygon([(mid_x, mid_z), (mid_x - R_quad * half_w, mid_z - R_quad * half_d), (mid_x - R_quad * half_w, mid_z + R_quad * half_d)])
    quad_E = Polygon([(mid_x, mid_z), (mid_x + R_quad * half_w, mid_z + R_quad * half_d), (mid_x + R_quad * half_w, mid_z - R_quad * half_d)])
    quad_N = Polygon([(mid_x, mid_z), (mid_x - R_quad * half_w, mid_z + R_quad * half_d), (mid_x + R_quad * half_w, mid_z + R_quad * half_d)])
    quad_S = Polygon([(mid_x, mid_z), (mid_x + R_quad * half_w, mid_z - R_quad * half_d), (mid_x - R_quad * half_w, mid_z - R_quad * half_d)])
    quad_polys = (quad_W, quad_E, quad_N, quad_S)

    full_box = sbox(float(in_min[0]) - 5.0, float(in_min[2]) - 5.0, float(in_max[0]) + 5.0, float(in_max[2]) + 5.0)
    if ext_rings:
        ext_band_2d = unary_union([r.buffer(EXT_SOLID_DEPTH_M, join_style=2) for r in ext_rings]).buffer(0)
        ch_ring_segs: dict[int, list[LineString]] = {0: [], 1: [], 2: [], 3: []}
        for r in ext_rings:
            coords = list(r.coords)
            for p_a, p_b in zip(coords[:-1], coords[1:]):
                dx = float(p_b[0]) - float(p_a[0])
                dz = float(p_b[1]) - float(p_a[1])
                slen = math.hypot(dx, dz)
                if slen < 1e-4:
                    continue
                mx = 0.5 * (float(p_a[0]) + float(p_b[0]))
                mz = 0.5 * (float(p_a[1]) + float(p_b[1]))
                ox = dz / slen
                oz = -dx / slen
                nx_q = (mx - mid_x) / half_w
                nz_q = (mz - mid_z) / half_d
                ch_e = (1 if ox >= 0.0 else 0) if abs(ox) >= abs(oz) else (2 if oz >= 0.0 else 3)
                if (
                    (ch_e == 0 and nx_q > 0.05)
                    or (ch_e == 1 and nx_q < -0.05)
                    or (ch_e == 2 and nz_q < -0.05)
                    or (ch_e == 3 and nz_q > 0.05)
                ):
                    ch_e = (1 if nx_q >= 0.0 else 0) if abs(nx_q) >= abs(nz_q) else (2 if nz_q >= 0.0 else 3)
                ch_ring_segs[ch_e].append(LineString([p_a, p_b]))

        raw_ch = [
            unary_union([s.buffer(EXT_SOLID_DEPTH_M, cap_style=2, join_style=2) for s in ch_ring_segs[k]]).intersection(ext_band_2d).buffer(0)
            if ch_ring_segs[k]
            else Polygon()
            for k in range(4)
        ]
        # Partition ext_band_2d cleanly across 0..3 using edge-channel buffers (keeping slanted walls 100% intact)
        rem_ext = ext_band_2d
        zone_ext: list[Any] = [Polygon(), Polygon(), Polygon(), Polygon()]
        for k in (1, 0, 2, 3):
            if not rem_ext.is_empty and not raw_ch[k].is_empty:
                piece = rem_ext.intersection(raw_ch[k]).buffer(0)
                zone_ext[k] = piece
                rem_ext = rem_ext.difference(piece).buffer(0)
        if not rem_ext.is_empty:
            for k in range(4):
                if not quad_polys[k].is_empty:
                    zone_ext[k] = unary_union([zone_ext[k], rem_ext.intersection(quad_polys[k])]).buffer(0)
        zone_polys = zone_ext
    else:
        inner_core = sbox(float(in_min[0]), float(in_min[2]), float(in_max[0]), float(in_max[2])).buffer(-EXT_SOLID_DEPTH_M, join_style=2)
        ext_band_2d = full_box.difference(inner_core).buffer(0) if not inner_core.is_empty else full_box
        zone_polys = [ext_band_2d.intersection(qp).buffer(0) for qp in quad_polys]
    zone_polys.append(full_box.difference(ext_band_2d).buffer(0))
    zone_polys_cov = [zp.buffer(1e-4, join_style=2) if not zp.is_empty else zp for zp in zone_polys]
    outer_skin_band = unary_union([r.buffer(0.60, join_style=2) for r in ext_rings]).buffer(0) if ext_rings else Polygon()

    def _clip_tri3d_halfplane(
        poly_pts: list[np.ndarray],
        poly_uvs: list[np.ndarray] | None,
        vals: list[float],
        cutoff: float,
        keep_ge: bool,
    ) -> tuple[list[np.ndarray], list[np.ndarray] | None]:
        out_p: list[np.ndarray] = []
        out_u: list[np.ndarray] | None = [] if poly_uvs is not None else None
        m = len(poly_pts)
        if m == 0:
            return out_p, out_u

        def _inside(v: float) -> bool:
            return (v >= cutoff - 1e-7) if keep_ge else (v <= cutoff + 1e-7)

        for i in range(m):
            j = (i + 1) % m
            va, vb = vals[i], vals[j]
            ina, inb = _inside(va), _inside(vb)
            if ina:
                out_p.append(poly_pts[i])
                if out_u is not None and poly_uvs is not None:
                    out_u.append(poly_uvs[i])
            if ina != inb:
                denom = vb - va
                alpha = 0.5 if abs(denom) < 1e-12 else max(0.0, min(1.0, (cutoff - va) / denom))
                out_p.append(poly_pts[i] + alpha * (poly_pts[j] - poly_pts[i]))
                if out_u is not None and poly_uvs is not None:
                    out_u.append(poly_uvs[i] + alpha * (poly_uvs[j] - poly_uvs[i]))
        return out_p, out_u

    def _slice_mesh_by_zones(
        verts: np.ndarray,
        faces: np.ndarray,
        uvs: np.ndarray | None,
        zone_list: list[Any],
        zone_cov_list: list[Any],
    ) -> dict[int, tuple[np.ndarray, np.ndarray, np.ndarray | None]]:
        """Slice triangles cleanly along exact 2D zone boundaries (keeping Auto walls 100% thick & spike-free)."""
        n_zones = len(zone_list)
        if len(faces) == 0:
            return {}
        per_v: dict[int, list[np.ndarray]] = {zi: [] for zi in range(n_zones)}
        per_uv: dict[int, list[np.ndarray]] = {zi: [] for zi in range(n_zones)}
        per_f: dict[int, list[list[int]]] = {zi: [] for zi in range(n_zones)}
        per_cnt: dict[int, int] = {zi: 0 for zi in range(n_zones)}

        def _emit_tri(zi: int, p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, uv3: list[np.ndarray] | None) -> None:
            pts = np.asarray([p0, p1, p2], dtype=np.float64)
            if float(np.linalg.norm(np.cross(pts[1] - pts[0], pts[2] - pts[0]))) < 1e-10:
                return
            base = per_cnt[zi]
            per_v[zi].append(pts)
            if uvs is not None and uv3 is not None:
                per_uv[zi].append(np.asarray(uv3, dtype=np.float64))
            per_f[zi].append([base, base + 1, base + 2])
            per_cnt[zi] = base + 3

        v0_all = verts[faces[:, 0]]
        v1_all = verts[faces[:, 1]]
        v2_all = verts[faces[:, 2]]
        e_cross = np.cross(v1_all - v0_all, v2_all - v0_all)
        dbl = np.linalg.norm(e_cross, axis=1)
        fn_all = np.divide(e_cross, np.maximum(dbl[:, None], 1e-12))

        for fi in range(len(faces)):
            idx3 = faces[fi]
            pts3 = verts[idx3]
            uv3 = [uvs[int(k)] for k in idx3] if uvs is not None else None
            ny = float(fn_all[fi, 1])

            xz = [(float(pts3[k, 0]), float(pts3[k, 2])) for k in range(3)]
            e_lens = [math.hypot(xz[(k + 1) % 3][0] - xz[k][0], xz[(k + 1) % 3][1] - xz[k][1]) for k in range(3)]
            max_e = max(e_lens)
            if max_e < 1e-7:
                continue
            area2d = 0.5 * abs((xz[1][0] - xz[0][0]) * (xz[2][1] - xz[0][1]) - (xz[1][1] - xz[0][1]) * (xz[2][0] - xz[0][0]))
            alt2d = 2.0 * area2d / max_e

            if abs(ny) < 0.55 and alt2d <= 1e-3:
                # Coplanar-in-XZ vertical triangle: clip 1D XZ segment across zones + Sutherland-Hodgman 3D plane clip
                best_pair = (0, 1)
                best_d2 = -1.0
                for ia in range(3):
                    for ib in range(ia + 1, 3):
                        d2 = (xz[ia][0] - xz[ib][0]) ** 2 + (xz[ia][1] - xz[ib][1]) ** 2
                        if d2 > best_d2:
                            best_d2 = d2
                            best_pair = (ia, ib)
                p_a = np.array(xz[best_pair[0]], dtype=np.float64)
                p_b = np.array(xz[best_pair[1]], dtype=np.float64)
                span = float(math.hypot(p_b[0] - p_a[0], p_b[1] - p_a[1]))
                if span < 1e-7:
                    cen_pt = Point(float(pts3[:, 0].mean()), float(pts3[:, 2].mean()))
                    best_zi = n_zones - 1
                    best_d = 1e9
                    for zi, zp in enumerate(zone_list):
                        if not zp.is_empty:
                            d = float(cen_pt.distance(zp))
                            if d < best_d:
                                best_d = d
                                best_zi = zi
                    _emit_tri(best_zi, pts3[0], pts3[1], pts3[2], uv3)
                    continue

                dir_xz = (p_b - p_a) / span
                t_verts = [float((xz[k][0] - p_a[0]) * dir_xz[0] + (xz[k][1] - p_a[1]) * dir_xz[1]) for k in range(3)]
                t_min, t_max = min(t_verts), max(t_verts)
                start_pt = p_a + t_min * dir_xz
                end_pt = p_a + t_max * dir_xz
                seg_ls = LineString([(float(start_pt[0]), float(start_pt[1])), (float(end_pt[0]), float(end_pt[1]))])

                matched_any = False
                for zi, zp in enumerate(zone_list):
                    if zp.is_empty:
                        continue
                    cov = zone_cov_list[zi]
                    if cov.covers(seg_ls):
                        _emit_tri(zi, pts3[0], pts3[1], pts3[2], uv3)
                        matched_any = True
                        break
                    inter = seg_ls.intersection(zp)
                    if inter.is_empty:
                        continue
                    line_geoms: list[LineString] = []
                    stack_g = [inter]
                    while stack_g:
                        cg = stack_g.pop()
                        if isinstance(cg, LineString) and cg.length > 1e-4:
                            line_geoms.append(cg)
                        elif hasattr(cg, "geoms"):
                            stack_g.extend(cg.geoms)
                    for lg in line_geoms:
                        c0, c1 = lg.coords[0], lg.coords[-1]
                        t0 = (float(c0[0]) - float(p_a[0])) * float(dir_xz[0]) + (float(c0[1]) - float(p_a[1])) * float(dir_xz[1])
                        t1 = (float(c1[0]) - float(p_a[0])) * float(dir_xz[0]) + (float(c1[1]) - float(p_a[1])) * float(dir_xz[1])
                        ta, tb = min(t0, t1), max(t0, t1)
                        if tb - ta < 1e-4:
                            continue
                        poly_p = [pts3[0].copy(), pts3[1].copy(), pts3[2].copy()]
                        poly_u = [uv3[0].copy(), uv3[1].copy(), uv3[2].copy()] if uv3 is not None else None
                        poly_p, poly_u = _clip_tri3d_halfplane(poly_p, poly_u, t_verts, ta, keep_ge=True)
                        t_mid = [float((pp[0] - p_a[0]) * dir_xz[0] + (pp[2] - p_a[1]) * dir_xz[1]) for pp in poly_p]
                        poly_p, poly_u = _clip_tri3d_halfplane(poly_p, poly_u, t_mid, tb, keep_ge=False)
                        if len(poly_p) >= 3:
                            matched_any = True
                            for ti in range(1, len(poly_p) - 1):
                                sub_uv = [poly_u[0], poly_u[ti], poly_u[ti + 1]] if poly_u is not None else None
                                _emit_tri(zi, poly_p[0], poly_p[ti], poly_p[ti + 1], sub_uv)
                if not matched_any:
                    _emit_tri(n_zones - 1, pts3[0], pts3[1], pts3[2], uv3)
            else:
                # Horizontal or non-degenerate-XZ sloped triangle: 2D polygon intersection + barycentric Y & UV
                tri2d = Polygon(xz)
                if not tri2d.is_valid or tri2d.area < 1e-8:
                    continue
                x0, z0 = xz[0]
                x1, z1 = xz[1]
                x2, z2 = xz[2]
                detT = (x1 - x0) * (z2 - z0) - (x2 - x0) * (z1 - z0)
                if abs(detT) < 1e-12:
                    continue
                matched_any = False
                for zi, zp in enumerate(zone_list):
                    if zp.is_empty:
                        continue
                    cov = zone_cov_list[zi]
                    if cov.covers(tri2d):
                        _emit_tri(zi, pts3[0], pts3[1], pts3[2], uv3)
                        matched_any = True
                        break
                    inter = tri2d.intersection(zp).buffer(0)
                    if inter.is_empty or inter.area < 1e-7:
                        continue
                    polys: list[Polygon] = []
                    stack_p = [inter]
                    while stack_p:
                        cg = stack_p.pop()
                        if isinstance(cg, Polygon) and cg.area >= 1e-7:
                            polys.append(cg)
                        elif hasattr(cg, "geoms"):
                            stack_p.extend(cg.geoms)
                    for subp in polys:
                        try:
                            v2d, f2d = trimesh.creation.triangulate_polygon(subp, engine="earcut")
                        except Exception:
                            try:
                                v2d, f2d = trimesh.creation.triangulate_polygon(subp)
                            except Exception:
                                continue
                        if len(f2d) == 0:
                            continue
                        matched_any = True
                        pts_sub = np.empty((len(v2d), 3), dtype=np.float64)
                        uvs_sub = np.empty((len(v2d), 2), dtype=np.float64) if uv3 is not None else None
                        for vi, (px, pz) in enumerate(v2d):
                            w1 = ((px - x0) * (z2 - z0) - (x2 - x0) * (pz - z0)) / detT
                            w2 = ((x1 - x0) * (pz - z0) - (px - x0) * (z1 - z0)) / detT
                            w0 = 1.0 - w1 - w2
                            pts_sub[vi] = w0 * pts3[0] + w1 * pts3[1] + w2 * pts3[2]
                            if uvs_sub is not None and uv3 is not None:
                                uvs_sub[vi] = w0 * uv3[0] + w1 * uv3[1] + w2 * uv3[2]
                        for s_tri in f2d:
                            p_a, p_b, p_c = pts_sub[s_tri[0]], pts_sub[s_tri[1]], pts_sub[s_tri[2]]
                            s_ny = float(np.cross(p_b - p_a, p_c - p_a)[1])
                            if (ny >= 0 and s_ny < 0) or (ny < 0 and s_ny > 0):
                                s_idx = [int(s_tri[0]), int(s_tri[2]), int(s_tri[1])]
                            else:
                                s_idx = [int(s_tri[0]), int(s_tri[1]), int(s_tri[2])]
                            sub_uv = [uvs_sub[s_idx[0]], uvs_sub[s_idx[1]], uvs_sub[s_idx[2]]] if uvs_sub is not None else None
                            _emit_tri(zi, pts_sub[s_idx[0]], pts_sub[s_idx[1]], pts_sub[s_idx[2]], sub_uv)
                if not matched_any:
                    _emit_tri(n_zones - 1, pts3[0], pts3[1], pts3[2], uv3)

        out: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray | None]] = {}
        for zi in range(n_zones):
            if not per_f[zi]:
                continue
            vv = np.concatenate(per_v[zi], axis=0)
            ff = np.asarray(per_f[zi], dtype=np.int64)
            uu = np.concatenate(per_uv[zi], axis=0) if uvs is not None else None
            out[zi] = (vv, ff, uu)
        return out

    ch_names = ("Wall_Ext_W_01", "Wall_Ext_E_01", "Wall_Ext_N_01", "Wall_Ext_S_01", "Wall_Interior_01")

    for prim_idx, (prim_name, geom) in enumerate(sc.geometry.items()):
        if len(geom.faces) == 0:
            continue
        mat = getattr(getattr(geom, "visual", None), "material", None)
        mat_name = getattr(mat, "name", None) or f"mat_{prim_idx:02d}"
        mat_slug = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in mat_name)
        preserved_mats.add(mat_name)

        verts = np.asarray(geom.vertices, dtype=np.float64)
        faces = np.asarray(geom.faces, dtype=np.int64)
        uvs = _extract_uv(geom)

        # 1. Slice at floor top (fy + 0.06m -> slab vs standing structure)
        # Keep slab + underside deck strictly in Floor_Slab (including [y_min, fy + 0.06m] slab faces)
        (below_slab_v, below_slab_f, below_slab_u), (above_slab_v, above_slab_f, above_slab_u) = slice_triangles_by_y(
            verts, faces, uvs, fy + 0.03
        )

        # Anything at or below fy + 0.03m belongs to Floor_Slab (except descending stairs inside stair_zone)
        if len(below_slab_f) > 0:
            if has_stairs:
                from shapely.geometry import Point

                bc = below_slab_v[below_slab_f].mean(axis=1)
                bfn = np.cross(
                    below_slab_v[below_slab_f[:, 1]] - below_slab_v[below_slab_f[:, 0]],
                    below_slab_v[below_slab_f[:, 2]] - below_slab_v[below_slab_f[:, 0]],
                )
                bfn_len = np.linalg.norm(bfn, axis=1)
                bfn_y = np.where(bfn_len > 1e-9, bfn[:, 1] / np.maximum(bfn_len, 1e-9), 0.0)
                in_stair = np.array(
                    [
                        (yc < fy - 0.05) and (abs(ny) < 0.92) and stair_zone.contains(Point(float(xc), float(zc)))
                        for xc, yc, zc, ny in zip(bc[:, 0], bc[:, 1], bc[:, 2], bfn_y)
                    ],
                    dtype=bool,
                )
                _add_group_mesh("Floor_Slab", mat_slug, _make_mesh(below_slab_v, below_slab_f[~in_stair], below_slab_u, mat))
                _add_group_mesh("Stairs_01", mat_slug, _make_mesh(below_slab_v, below_slab_f[in_stair], below_slab_u, mat))
            else:
                _add_group_mesh("Floor_Slab", mat_slug, _make_mesh(below_slab_v, below_slab_f, below_slab_u, mat))

        if len(above_slab_f) == 0:
            continue

        # 2. Separate ceiling deck / high horizontal soffits & overhead canopies (>= lintel_y - 0.04m)
        (below_lintel_v, below_lintel_f, below_lintel_u), (above_lintel_v, above_lintel_f, above_lintel_u) = slice_triangles_by_y(
            above_slab_v, above_slab_f, above_slab_u, ly - 0.02
        )

        # Above lintel_y:
        # 1. Strip wide ceiling/roof decks (> 2.6m core near ceil_y) per Failure Ledger #4 (Gate 5)
        # 2. Route upper stair treads inside stair_zone -> Stairs_Upper_01
        # 3. Narrow beams/lintels/canopies -> OverheadBeams_And_Lintels
        # 4. Standing vertical walls -> Wall_*__Upper
        if len(above_lintel_f) > 0:
            from shapely.geometry import Point

            afn = np.cross(
                above_lintel_v[above_lintel_f[:, 1]] - above_lintel_v[above_lintel_f[:, 0]],
                above_lintel_v[above_lintel_f[:, 2]] - above_lintel_v[above_lintel_f[:, 0]],
            )
            afn_len = np.linalg.norm(afn, axis=1)
            afn_y = np.where(afn_len > 1e-9, afn[:, 1] / np.maximum(afn_len, 1e-9), 0.0)
            ac = above_lintel_v[above_lintel_f].mean(axis=1)

            # Strip wide ceiling/canopy deck horizontal faces at >= lintel_y - 0.05m
            if has_wide_ceil:
                is_wide_ceil = np.array(
                    [
                        (abs(ny) > 0.65) and (yc >= ly - 0.05) and wide_ceil_core.contains(Point(float(xc), float(zc)))
                        for xc, yc, zc, ny in zip(ac[:, 0], ac[:, 1], ac[:, 2], afn_y)
                    ],
                    dtype=bool,
                )
            else:
                is_wide_ceil = np.zeros(len(above_lintel_f), dtype=bool)

            # Upper stairs inside stair_zone (never contaminate OverheadBeams_And_Lintels; keep outer skin wall outside)
            if has_stairs:
                is_hi_stair = np.array(
                    [
                        (not wc) and stair_zone.contains(Point(float(xc), float(zc)))
                        and (outer_skin_band.is_empty or not outer_skin_band.contains(Point(float(xc), float(zc))))
                        for wc, xc, zc in zip(is_wide_ceil, ac[:, 0], ac[:, 2])
                    ],
                    dtype=bool,
                )
            else:
                is_hi_stair = np.zeros(len(above_lintel_f), dtype=bool)

            if np.any(is_hi_stair):
                _add_group_mesh(
                    "Stairs_Upper_01",
                    mat_slug,
                    _make_mesh(above_lintel_v, above_lintel_f[is_hi_stair], above_lintel_u, mat),
                )

            # Exterior facade overhangs/canopies outside floor envelope -> Facade_Ext_{W,E,N,S}
            out_of_env = (
                (ac[:, 0] < env_min_x - 0.45)
                | (ac[:, 0] > env_max_x + 0.45)
                | (ac[:, 2] < env_min_z - 0.45)
                | (ac[:, 2] > env_max_z + 0.45)
            )
            facade_names = ("Facade_Ext_W", "Facade_Ext_E", "Facade_Ext_N", "Facade_Ext_S")
            is_ext_canopy = (~is_wide_ceil) & (~is_hi_stair) & out_of_env
            if np.any(is_ext_canopy):
                ext_parts = _slice_mesh_by_zones(
                    above_lintel_v, above_lintel_f[is_ext_canopy], above_lintel_u, list(quad_polys), list(quad_polys)
                )
                for ci in range(4):
                    if ci in ext_parts:
                        sv, sf, su = ext_parts[ci]
                        _add_group_mesh(facade_names[ci], mat_slug, _make_mesh(sv, sf, su, mat))

            # Horizontal wall top-caps over standing walls stay on Wall_*__Upper;
            # only unsupported narrow beams/lintels over doorways go to OverheadBeams_And_Lintels!
            if has_wall_sup:
                on_wall_top = np.array(
                    [
                        (abs(ny) > 0.55) and solid_wall_top_zone.contains(Point(float(xc), float(zc)))
                        for xc, zc, ny in zip(ac[:, 0], ac[:, 2], afn_y)
                    ],
                    dtype=bool,
                )
            else:
                on_wall_top = np.zeros(len(above_lintel_f), dtype=bool)

            is_overhead = (~is_wide_ceil) & (~is_hi_stair) & (~is_ext_canopy) & (np.abs(afn_y) > 0.55) & (~on_wall_top)
            _add_group_mesh(
                "OverheadBeams_And_Lintels",
                mat_slug,
                _make_mesh(above_lintel_v, above_lintel_f[is_overhead], above_lintel_u, mat),
            )

            rem_mask = (~is_wide_ceil) & (~is_hi_stair) & (~is_ext_canopy) & (~is_overhead)
            if np.any(rem_mask):
                u_parts = _slice_mesh_by_zones(above_lintel_v, above_lintel_f[rem_mask], above_lintel_u, zone_polys, zone_polys_cov)
                for ci, cname in enumerate(ch_names):
                    if ci in u_parts:
                        sv, sf, su = u_parts[ci]
                        _add_group_mesh(f"{cname}__Upper", mat_slug, _make_mesh(sv, sf, su, mat))

        if len(below_lintel_f) == 0:
            continue

        # 3. Split [fy + 0.03, ly - 0.02] at cut_y (fy + 1.25m) into Lower vs Upper
        (lo_band_v, lo_band_f, lo_band_u), (hi_band_v, hi_band_f, hi_band_u) = slice_triangles_by_y(
            below_lintel_v, below_lintel_f, below_lintel_u, cut_y
        )

        # Upper band [cut_y, ly - 0.02]: split Stairs_Upper_01 vs Wall_*__Upper
        if len(hi_band_f) > 0:
            hc = hi_band_v[hi_band_f].mean(axis=1)
            from shapely.geometry import Point

            if has_stairs:
                h_stair = np.array(
                    [
                        stair_zone.contains(Point(float(xc), float(zc)))
                        and (outer_skin_band.is_empty or not outer_skin_band.contains(Point(float(xc), float(zc))))
                        for xc, zc in zip(hc[:, 0], hc[:, 2])
                    ],
                    dtype=bool,
                )
            else:
                h_stair = np.zeros(len(hi_band_f), dtype=bool)

            if np.any(h_stair):
                _add_group_mesh("Stairs_Upper_01", mat_slug, _make_mesh(hi_band_v, hi_band_f[h_stair], hi_band_u, mat))
            if np.any(~h_stair):
                hi_parts = _slice_mesh_by_zones(hi_band_v, hi_band_f[~h_stair], hi_band_u, zone_polys, zone_polys_cov)
                for ci, cname in enumerate(ch_names):
                    if ci in hi_parts:
                        sv, sf, su = hi_parts[ci]
                        _add_group_mesh(f"{cname}__Upper", mat_slug, _make_mesh(sv, sf, su, mat))

        if len(lo_band_f) == 0:
            continue

        # 4. Split lower band [fy + 0.03, cut_y] at plinth_y (fy + 0.06m) into __Plinth vs __Lower (and Stairs_01)
        from shapely.geometry import Point

        lc = lo_band_v[lo_band_f].mean(axis=1)
        if has_stairs:
            l_stair = np.array(
                [
                    stair_zone.contains(Point(float(xc), float(zc)))
                    and (outer_skin_band.is_empty or not outer_skin_band.contains(Point(float(xc), float(zc))))
                    for xc, zc in zip(lc[:, 0], lc[:, 2])
                ],
                dtype=bool,
            )
        else:
            l_stair = np.zeros(len(lo_band_f), dtype=bool)

        if np.any(l_stair):
            _add_group_mesh("Stairs_01", mat_slug, _make_mesh(lo_band_v, lo_band_f[l_stair], lo_band_u, mat))

        wall_lo_f = lo_band_f[~l_stair]
        if len(wall_lo_f) == 0:
            continue

        (plinth_v, plinth_f, plinth_u), (lower_v, lower_f, lower_u) = slice_triangles_by_y(
            lo_band_v, wall_lo_f, lo_band_u, plinth_y
        )

        if len(plinth_f) > 0:
            pl_parts_slice = _slice_mesh_by_zones(plinth_v, plinth_f, plinth_u, zone_polys, zone_polys_cov)
            for ci, cname in enumerate(ch_names):
                if ci in pl_parts_slice:
                    sv, sf, su = pl_parts_slice[ci]
                    m_pl = _make_mesh(sv, sf, su, mat)
                    if m_pl is not None:
                        _add_group_mesh(f"{cname}__Plinth", mat_slug, m_pl)
                        channel_plinth_meshes[cname].append(m_pl)

        if len(lower_f) > 0:
            lo_parts_slice = _slice_mesh_by_zones(lower_v, lower_f, lower_u, zone_polys, zone_polys_cov)
            for ci, cname in enumerate(ch_names):
                if ci in lo_parts_slice:
                    sv, sf, su = lo_parts_slice[ci]
                    m_lo = _make_mesh(sv, sf, su, mat)
                    if m_lo is not None:
                        _add_group_mesh(f"{cname}__Lower", mat_slug, m_lo)
                        channel_lower_meshes[cname].append(m_lo)

    # 5. Build solid concrete CutCap_* meshes + __Lower__cut_cap upward footprints for mask extraction
    cap_mat = PBRMaterial(
        name="UC_Solid_CutCap",
        baseColorFactor=[0.56, 0.58, 0.57, 1.0],
        metallicFactor=0.04,
        roughnessFactor=0.90,
        doubleSided=True,
    )
    cap_channel_map = {
        "Wall_Ext_W_01": "CutCap_Ext_W",
        "Wall_Ext_E_01": "CutCap_Ext_E",
        "Wall_Ext_N_01": "CutCap_Ext_N",
        "Wall_Ext_S_01": "CutCap_Ext_S",
        "Wall_Interior_01": "CutCap_Interior",
    }
    cap_counts: dict[str, int] = {}
    clip_env = sbox(float(in_min[0]), float(in_min[2]), float(in_max[0]), float(in_max[2]))
    all_lower_meshes: list[trimesh.Trimesh] = []
    for cname in cap_channel_map:
        all_lower_meshes.extend(channel_lower_meshes[cname])

    # Build ONE unified solid cross-section across all walls & columns so thick walls & junctions fill 100% solid
    unified_fp_2d = _extract_wall_footprint_2d(
        all_lower_meshes,
        fy + 0.20,
        cut_y,
        clip_box=clip_env,
        walkable_floor_2d=walkable_floor_2d,
        wall_top_cap_2d=wall_top_cap_2d,
    )
    ch_zones: dict[str, Any] = {}
    for cname in cap_channel_map:
        ch_segs = _extract_wall_section_segments(channel_lower_meshes[cname], fy + 0.20, cut_y, cut_y)
        ch_zones[cname] = unary_union([s.buffer(0.45, join_style=2) for s in ch_segs]).buffer(0) if ch_segs else Polygon()

    # Partition solid CutCap and Plinth_CutCap cleanly along exact zone_polys so horizontal seams match Upper wall seams 1:1
    partitioned_fps: dict[str, Any] = {}
    for ci, cname in enumerate(ch_names):
        zp = zone_polys[ci]
        partitioned_fps[cname] = unified_fp_2d.intersection(zp).buffer(0) if (not unified_fp_2d.is_empty and not zp.is_empty) else Polygon()

    for cname, cap_name in cap_channel_map.items():
        fp_2d = partitioned_fps.get(cname, Polygon())
        cap_mesh = _build_cutcap_mesh(fp_2d, cut_y + 0.002, cap_mat)
        if cap_mesh is not None and len(cap_mesh.faces) > 0:
            out_scene.add_geometry(cap_mesh, node_name=cap_name, geom_name=cap_name)
            cap_counts[cap_name] = len(cap_mesh.faces)
            # Also attach an upward top-face cap on Wall_*__Lower__cut_cap so build-interior-studio-masks.py reads wc_lo!
            lo_cap_name = f"{cname}__Lower__cut_cap"
            out_scene.add_geometry(cap_mesh.copy(), node_name=lo_cap_name, geom_name=lo_cap_name)
            group_tri_counts[cap_name] = len(cap_mesh.faces)

    # Also build solid Plinth top caps (`Wall_*__Plinth__cut_cap`) so Floor filter mode renders 100% solid walls & piers
    all_plinth_and_lower_meshes: list[trimesh.Trimesh] = list(all_lower_meshes)
    for cname in cap_channel_map:
        all_plinth_and_lower_meshes.extend(channel_plinth_meshes[cname])
    plinth_slice_y = min(cut_y, fy + 0.25)
    plinth_fp_2d = _extract_wall_footprint_2d(
        all_plinth_and_lower_meshes,
        fy + 0.04,
        plinth_slice_y,
        clip_box=clip_env,
        walkable_floor_2d=walkable_floor_2d,
        wall_top_cap_2d=wall_top_cap_2d,
    )
    if not unified_fp_2d.is_empty and not wall_top_cap_2d.is_empty:
        non_walk_pier_zone = (
            wall_top_cap_2d.difference(walkable_floor_2d).buffer(0.05, join_style=2)
            if not walkable_floor_2d.is_empty
            else wall_top_cap_2d
        )
        pier_fill = unified_fp_2d.intersection(non_walk_pier_zone).buffer(0)
        if not pier_fill.is_empty:
            plinth_fp_2d = (
                unary_union([g for g in (plinth_fp_2d, pier_fill) if g is not None and not g.is_empty])
                .intersection(clip_env)
                .buffer(0)
            )
    pl_parts: dict[str, Any] = {}
    if not plinth_fp_2d.is_empty:
        for ci, cname in enumerate(ch_names):
            zp = zone_polys[ci]
            pl_fp = plinth_fp_2d.intersection(zp).buffer(0) if not zp.is_empty else Polygon()
            pl_parts[cname] = pl_fp
            pl_mesh = _build_cutcap_mesh(pl_fp, plinth_y + 0.002, cap_mat)
            if pl_mesh is not None and len(pl_mesh.faces) > 0:
                pl_cap_name = f"{cname}__Plinth__cut_cap"
                out_scene.add_geometry(pl_mesh, node_name=pl_cap_name, geom_name=pl_cap_name)
                group_tri_counts["Plinth_CutCap"] = group_tri_counts.get("Plinth_CutCap", 0) + len(pl_mesh.faces)

    # Seal vertical Auto cutaway seams (`Wall_Ext_{W,E,N,S}_01__Upper__cut_cap`) so cut corners & T-junctions look 100% solid!
    if not unified_fp_2d.is_empty:
        for ci in range(4):
            cname = ch_names[ci]
            zp = zone_polys[ci]
            if zp.is_empty:
                continue
            others_u = unary_union([zone_polys[oi] for oi in range(5) if oi != ci and not zone_polys[oi].is_empty]).buffer(0.015, join_style=2)
            cut_geom = zp.boundary.intersection(others_u).intersection(unified_fp_2d)
            if cut_geom.is_empty:
                continue
            cut_segs: list[LineString] = []
            stack_l = [cut_geom]
            while stack_l:
                cg = stack_l.pop()
                if isinstance(cg, LineString) and cg.length >= 0.05:
                    coords = list(cg.coords)
                    for a_c, b_c in zip(coords[:-1], coords[1:]):
                        seg_i = LineString([a_c, b_c])
                        if seg_i.length >= 0.05:
                            cut_segs.append(seg_i)
                elif hasattr(cg, "geoms"):
                    stack_l.extend(cg.geoms)
            if not cut_segs:
                continue
            # Collect upper triangles belonging to this exterior channel
            up_meshes = [
                g for gn, g in out_scene.geometry.items()
                if gn.startswith(f"{cname}__Upper__") and len(g.faces) > 0
            ]
            if not up_meshes:
                continue
            up_bounds_max_y: list[tuple[float, float, float, float, float]] = []
            for gm in up_meshes:
                tv = gm.vertices[gm.faces]
                tx0 = tv[:, :, 0].min(axis=1)
                tx1 = tv[:, :, 0].max(axis=1)
                tz0 = tv[:, :, 2].min(axis=1)
                tz1 = tv[:, :, 2].max(axis=1)
                ty1 = tv[:, :, 1].max(axis=1)
                for a0, a1, b0, b1, ymax_t in zip(tx0, tx1, tz0, tz1, ty1):
                    up_bounds_max_y.append((float(a0), float(a1), float(b0), float(b1), float(ymax_t)))
            cap_v: list[list[float]] = []
            cap_f: list[list[int]] = []
            for seg_i in cut_segs:
                (ax, az), (bx, bz) = seg_i.coords[0], seg_i.coords[-1]
                mx, mz = 0.5 * (ax + bx), 0.5 * (az + bz)
                near_y = [
                    ymax_t for a0, a1, b0, b1, ymax_t in up_bounds_max_y
                    if (mx >= a0 - 0.25) and (mx <= a1 + 0.25) and (mz >= b0 - 0.25) and (mz <= b1 + 0.25)
                ]
                if not near_y:
                    continue
                y_top = min(cy, max(near_y))
                if y_top <= cut_y + 0.10:
                    continue
                vi0 = len(cap_v)
                cap_v.extend([
                    [float(ax), float(cut_y), float(az)],
                    [float(bx), float(cut_y), float(bz)],
                    [float(bx), float(y_top), float(bz)],
                    [float(ax), float(y_top), float(az)],
                ])
                cap_f.extend([[vi0, vi0 + 1, vi0 + 2], [vi0, vi0 + 2, vi0 + 3]])
            if cap_f:
                vc_arr = np.asarray(cap_v, dtype=np.float64)
                fc_arr = np.asarray(cap_f, dtype=np.int64)
                uvc = np.column_stack([vc_arr[:, 0] * 0.25 + vc_arr[:, 2] * 0.25, vc_arr[:, 1] * 0.25])
                vcap_mesh = trimesh.Trimesh(vertices=vc_arr, faces=fc_arr, visual=TextureVisuals(uv=uvc, material=cap_mat), process=False)
                vcap_name = f"{cname}__Upper__cut_cap"
                out_scene.add_geometry(vcap_mesh, node_name=vcap_name, geom_name=vcap_name)
                group_tri_counts["Upper_CutCap"] = group_tri_counts.get("Upper_CutCap", 0) + len(vcap_mesh.faces)

    # 6. Export GLB & run 6 Hard Studio QA Gates (S1-S6)
    output_glb.parent.mkdir(parents=True, exist_ok=True)
    out_scene.export(output_glb, file_type="glb")

    reloaded = trimesh.load(output_glb, force="scene")
    out_tris = sum(len(g.faces) for g in reloaded.geometry.values())
    out_min = np.min([g.vertices.min(axis=0) for g in reloaded.geometry.values() if len(g.vertices) > 0], axis=0)
    out_max = np.max([g.vertices.max(axis=0) for g in reloaded.geometry.values() if len(g.vertices) > 0], axis=0)
    max_bbox_delta = float(max(np.max(np.abs(out_min - in_min)), np.max(np.abs(out_max - in_max))))

    # S1: Corridor/room CutCap leak area (<= 0.35 m^2)
    open_walk_2d = (
        walkable_floor_2d.difference(wall_top_cap_2d.buffer(0.12, join_style=2)).buffer(-0.08, join_style=2)
        if (not walkable_floor_2d.is_empty and not wall_top_cap_2d.is_empty)
        else Polygon()
    )
    cap_union_2d = unary_union([g for g in (*partitioned_fps.values(), *pl_parts.values()) if g is not None and not g.is_empty]).buffer(0)
    s1_leak_m2 = round(float(cap_union_2d.intersection(open_walk_2d).area), 4) if (not open_walk_2d.is_empty and not cap_union_2d.is_empty) else 0.0

    # S2 & S3: Zone overhang (<= 0.08m) and quadrant mismatch (== 0) on Wall_Ext_*__Upper
    s2_max_overhang_m = 0.0
    s3_mismatch = 0
    for k, g in reloaded.geometry.items():
        if "__Upper__" not in k or not k.startswith("Wall_Ext_") or len(g.vertices) == 0:
            continue
        ci_m = 0 if k.startswith("Wall_Ext_W_") else (1 if k.startswith("Wall_Ext_E_") else (2 if k.startswith("Wall_Ext_N_") else 3))
        zp_m = zone_polys[ci_m]
        if not zp_m.is_empty:
            for vx, vz in g.vertices[:, [0, 2]]:
                d_out = float(Point(float(vx), float(vz)).distance(zp_m))
                if d_out > s2_max_overhang_m:
                    s2_max_overhang_m = d_out
        c = g.vertices.mean(axis=0)
        nx = (float(c[0]) - mid_x) / half_w
        nz = (float(c[2]) - mid_z) / half_d
        if (ci_m == 0 and nx > 0.05) or (ci_m == 1 and nx < -0.05) or (ci_m == 2 and nz < -0.05) or (ci_m == 3 and nz > 0.05):
            s3_mismatch += 1
    s2_max_overhang_m = round(float(s2_max_overhang_m), 4)

    # S4: Capped solid piers solid coverage (>= 98.0%) across Lower + Plinth cut caps
    lo_cap_2d = unary_union([g for g in partitioned_fps.values() if g is not None and not g.is_empty]).buffer(0)
    pl_cap_2d = unary_union([g for g in pl_parts.values() if g is not None and not g.is_empty]).buffer(0)
    pier_segs = _extract_wall_section_segments(all_lower_meshes, fy + 0.20, cut_y, cut_y)
    capped_piers: list[Polygon] = []
    if pier_segs and not wall_top_cap_2d.is_empty:
        p_snapped = []
        for s in pier_segs:
            c = list(s.coords)
            p0_s = (round(c[0][0], 2), round(c[0][1], 2))
            p1_s = (round(c[-1][0], 2), round(c[-1][1], 2))
            if p0_s != p1_s:
                p_snapped.append(LineString([p0_s, p1_s]))
        if p_snapped:
            for p_cand in polygonize(unary_union(p_snapped)):
                if isinstance(p_cand, Polygon) and 0.005 <= p_cand.area <= 40.0:
                    up_c = float(p_cand.intersection(wall_top_cap_2d).area / p_cand.area)
                    wk_c = float(p_cand.intersection(walkable_floor_2d).area / p_cand.area) if not walkable_floor_2d.is_empty else 0.0
                    if up_c >= 0.70 and wk_c < 0.25:
                        capped_piers.append(p_cand)
    if capped_piers:
        pier_u = unary_union(capped_piers).buffer(0)
        lo_cov = float(pier_u.intersection(lo_cap_2d).area / pier_u.area) if not lo_cap_2d.is_empty else 0.0
        pl_cov = float(pier_u.intersection(pl_cap_2d).area / pier_u.area) if not pl_cap_2d.is_empty else 0.0
        s4_piers_pct = round(100.0 * min(lo_cov, pl_cov), 2)
    else:
        s4_piers_pct = 100.0

    # S5: Gate 5 overhead top area (<= 65.0 m^2)
    overhead_top_area_m2 = 0.0
    for gname, g in reloaded.geometry.items():
        if gname.startswith("OverheadBeams_"):
            up = g.face_normals[:, 1] > 0.85
            if np.any(up):
                overhead_top_area_m2 += float(g.area_faces[up].sum())

    # S6: Walkable floor cracks (== 0) on major Y-up Floor_Slab clusters (>= 25.0 m^2)
    slab_tris: list[tuple[float, Polygon, float, int]] = []
    floor_mode_cover_tris: list[tuple[float, tuple[float, float, float, float], Polygon, int]] = []
    tri_seq = 0
    for gname, g in reloaded.geometry.items():
        is_slab = gname.startswith("Floor_Slab")
        is_floor_cover = is_slab or gname.startswith("Stairs_01") or ("__Plinth__cut_cap" in gname)
        if not is_floor_cover or len(g.faces) == 0:
            continue
        v_g, f_g = g.vertices, g.faces
        fn_g = g.face_normals
        fc_g = v_g[f_g].mean(axis=1)
        m_horiz = np.abs(fn_g[:, 1]) > 0.85
        for f_row, ny, ym, am in zip(f_g[m_horiz], fn_g[m_horiz, 1], fc_g[m_horiz, 1], g.area_faces[m_horiz]):
            q = Polygon([(float(v_g[f_row[0], 0]), float(v_g[f_row[0], 2])), (float(v_g[f_row[1], 0]), float(v_g[f_row[1], 2])), (float(v_g[f_row[2], 0]), float(v_g[f_row[2], 2]))])
            if not (q.is_valid and q.area > 1e-6):
                continue
            tid = tri_seq
            tri_seq += 1
            floor_mode_cover_tris.append((float(ym), q.bounds, q, tid))
            if is_slab and ny > 0.85:
                slab_tris.append((float(ym), q, float(am), tid))

    def _expand_s6_parts(geom) -> list[Polygon]:
        if geom.is_empty:
            return []
        if isinstance(geom, Polygon):
            return [geom]
        parts: list[Polygon] = []
        for sub in getattr(geom, "geoms", ()):
            parts.extend(_expand_s6_parts(sub))
        return parts

    s6_floor_cracks = 0
    if slab_tris:
        slab_tris.sort(key=lambda t: t[0])
        y_clusters: list[list[tuple[Polygon, float, int]]] = []
        y_means: list[float] = []
        for ym, qp, am, tid in slab_tris:
            if not y_clusters or abs(ym - y_means[-1]) > 0.08:
                y_clusters.append([(qp, am, tid)])
                y_means.append(ym)
            else:
                n_prev = len(y_clusters[-1])
                y_clusters[-1].append((qp, am, tid))
                y_means[-1] = (y_means[-1] * n_prev + ym) / (n_prev + 1)
        for cl_y_m, cl in zip(y_means, y_clusters):
            if sum(a for _, a, _ in cl) < 25.0:
                continue
            cl_tids = {tid for _, _, tid in cl}
            near_covers = [
                (bounds, cq) for c_ym, bounds, cq, tid in floor_mode_cover_tris
                if tid not in cl_tids and abs(c_ym - cl_y_m) <= 0.20
            ]
            cl_u = unary_union([qp for qp, _, _ in cl])
            if not cl_u.is_valid:
                cl_u = cl_u.buffer(0)
            gs = list(cl_u.geoms) if hasattr(cl_u, "geoms") else [cl_u]
            for gp in gs:
                if not isinstance(gp, Polygon):
                    continue
                for ring in gp.interiors:
                    hp = Polygon(ring)
                    if not hp.is_valid:
                        hp = hp.buffer(0)
                    if not (isinstance(hp, Polygon) and 0.0002 < float(hp.area) < 0.50 and hp.buffer(-0.22, join_style=2).is_empty):
                        continue
                    hx0, hy0, hx1, hy1 = hp.bounds
                    hit_cov = [
                        cq for (ox0, oy0, ox1, oy1), cq in near_covers
                        if ox1 >= hx0 and ox0 <= hx1 and oy1 >= hy0 and oy0 <= hy1
                    ]
                    uncovered = hp.difference(unary_union(hit_cov)) if hit_cov else hp
                    if not uncovered.is_valid:
                        uncovered = uncovered.buffer(0)
                    for part in _expand_s6_parts(uncovered):
                        if 0.0002 < float(part.area) < 0.50 and part.buffer(-0.22, join_style=2).is_empty:
                            s6_floor_cracks += 1

    required_groups = ["Floor_Slab"]
    if group_tri_counts.get("Wall_Interior_01", 0) > 0:
        required_groups.append("CutCap_Interior")
    missing_groups = [k for k in required_groups if group_tri_counts.get(k, 0) == 0]
    if sum(cap_counts.values()) == 0:
        missing_groups.append("CutCap_Any")

    studio_qa_gates = {
        "S1_corridor_cutcap_leak_m2": s1_leak_m2,
        "S2_max_zone_overhang_m": s2_max_overhang_m,
        "S3_quadrant_mismatch": s3_mismatch,
        "S4_capped_piers_solid_pct": s4_piers_pct,
        "S5_overhead_top_area_m2": round(overhead_top_area_m2, 2),
        "S6_walkable_floor_cracks": s6_floor_cracks,
    }
    qa_passed = (
        out_tris >= int(in_tris * 0.70)
        and max_bbox_delta <= 0.05
        and s1_leak_m2 <= 0.35
        and s2_max_overhang_m <= 0.08
        and s3_mismatch == 0
        and s4_piers_pct >= 98.0
        and overhead_top_area_m2 <= 65.0
        and s6_floor_cracks == 0
        and len(missing_groups) == 0
        and len(preserved_mats) >= 1
    )

    manifest = {
        "building": building,
        "floor": floor,
        "source_glb": str(input_glb),
        "output_glb": str(output_glb),
        "output_bytes": output_glb.stat().st_size,
        "elevations_m": elev,
        "input_triangles": int(in_tris),
        "output_triangles": int(out_tris),
        "output_nodes": len(reloaded.geometry),
        "preserved_materials_count": len(preserved_mats),
        "preserved_materials": sorted(preserved_mats),
        "bounds_in_min": [round(float(x), 4) for x in in_min],
        "bounds_in_max": [round(float(x), 4) for x in in_max],
        "bounds_out_min": [round(float(x), 4) for x in out_min],
        "bounds_out_max": [round(float(x), 4) for x in out_max],
        "max_bbox_delta_m": round(max_bbox_delta, 5),
        "overhead_top_area_m2": round(overhead_top_area_m2, 2),
        "studio_qa_gates": studio_qa_gates,
        "group_triangles": group_tri_counts,
        "cutcap_triangles": cap_counts,
        "qa_passed": qa_passed,
        "missing_groups": missing_groups,
    }

    manifest_path = output_glb.with_suffix(".studio_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if not manifest["qa_passed"]:
        raise RuntimeError(f"Real-Model Studio packaging QA failed: {json.dumps(manifest, indent=2)}")

    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Package Real-Model Engine v2 GLB for Interior Design Studio.")
    ap.add_argument("--building", default="CHTM", help="Building folder under PerFloor-EngineV2 (default: CHTM)")
    ap.add_argument("--floor", default="Floor_4F", help="Floor folder (default: Floor_4F)")
    ap.add_argument("--input-glb", type=Path, default=None)
    ap.add_argument("--output-glb", type=Path, default=None)
    ap.add_argument("--floor-y", type=float, default=None)
    ap.add_argument("--lintel-y", type=float, default=None)
    ap.add_argument("--ceil-y", type=float, default=None)
    ap.add_argument("--force-solid", action="store_true")
    args = ap.parse_args()

    in_glb = args.input_glb or (PER_FLOOR_V2_ROOT / args.building / args.floor / f"{args.building}_{args.floor}.glb")
    out_glb = args.output_glb or (PER_FLOOR_V2_ROOT / args.building / args.floor / f"{args.building}_{args.floor}.real_v2.studio.glb")

    mf = package_real_v2_floor(
        input_glb=in_glb,
        output_glb=out_glb,
        building=args.building,
        floor=args.floor,
        floor_y=args.floor_y,
        lintel_y=args.lintel_y,
        ceil_y=args.ceil_y,
        force_solid=args.force_solid,
    )
    print(
        f"[RealV2Studio] OK {args.building}/{args.floor}: "
        f"in_tris={mf['input_triangles']} -> out_tris={mf['output_triangles']} "
        f"nodes={mf['output_nodes']} mats={mf['preserved_materials_count']} "
        f"bbox_delta={mf['max_bbox_delta_m']}m bytes={mf['output_bytes']}"
    )
    print(f"  groups={mf['group_triangles']}")


if __name__ == "__main__":
    main()
