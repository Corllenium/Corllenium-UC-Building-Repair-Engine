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

    Builds horizontal multi-step clusters first (>= 4 distinct step heights) and only
    attaches nearby sloped strings/railings intersecting those clusters so slanted exterior
    walls or angled window sills are never misclassified as Stairs_Upper_01.
    """
    step_polys: list[tuple[float, Polygon]] = []
    for g in sc.geometry.values():
        fn = g.face_normals
        fc = g.vertices[g.faces].mean(axis=1)
        up = (fn[:, 1] > 0.90) & (fc[:, 1] >= floor_y + 0.14) & (fc[:, 1] <= ceil_y - 0.30)
        for f, yc in zip(g.faces[up], fc[up, 1]):
            pts = [(float(g.vertices[v, 0]), float(g.vertices[v, 2])) for v in f]
            p = Polygon(pts).buffer(0)
            if 0.04 <= p.area <= 4.0:
                step_polys.append((round(float(yc), 2), p))

    step_comps: list[Any] = []
    if step_polys:
        step_u = unary_union([p.buffer(0.16, join_style=2) for _, p in step_polys]).buffer(0)
        comps = list(step_u.geoms) if hasattr(step_u, "geoms") else [step_u]
        for comp in comps:
            if comp.is_empty or comp.area > 40.0:
                continue
            ys_in = {y for y, p in step_polys if comp.intersects(p)}
            if len(ys_in) >= 4:
                step_comps.append(comp.buffer(0.15, join_style=2))

    if not step_comps:
        return Polygon()

    step_base = unary_union(step_comps).buffer(0)
    slope_anchor = step_base.buffer(1.2, join_style=2)
    polys: list[Any] = [step_base]
    for g in sc.geometry.values():
        fn = g.face_normals
        fc = g.vertices[g.faces].mean(axis=1)
        sloped = (np.abs(fn[:, 1]) >= 0.25) & (np.abs(fn[:, 1]) <= 0.86) & (fc[:, 1] >= floor_y - 0.8) & (fc[:, 1] <= ceil_y - 0.1)
        for f in g.faces[sloped]:
            pts = [(float(g.vertices[v, 0]), float(g.vertices[v, 2])) for v in f]
            p = Polygon(pts).buffer(0)
            if p.area > 0.01 and p.intersects(slope_anchor):
                polys.append(p.buffer(0.20, join_style=2))

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
            is_narrow_wall = (p.area <= 16.0) and p.buffer(-0.75, join_style=2).is_empty
            is_capped_solid_pier = False
            if not is_narrow_wall and has_top_cap:
                top_cov = float(p.intersection(wall_top_cap_2d).area / p.area)
                walk_cov = float(p.intersection(walkable_floor_2d).area / p.area) if has_walk else 0.0
                is_capped_solid_pier = (top_cov >= 0.70) and (walk_cov < 0.25)
            if not (is_narrow_wall or is_capped_solid_pier):
                continue
            filled_cores.append(p.buffer(0.02, join_style=2))

    # Close narrow wall skin gaps up to 0.50m (<= 2 * 0.25m) without ever bridging 0.70m+ doorways
    closed = skin_u.buffer(0.25, join_style=2).buffer(-0.25, join_style=2).buffer(0)

    parts = [skin_u, closed, *filled_cores]
    u = unary_union([g for g in parts if g is not None and not g.is_empty]).buffer(0)
    if clip_box is not None:
        u = u.intersection(clip_box).buffer(0)
    return u


def package_real_v2_floor(
    input_glb: Path,
    output_glb: Path,
    building: str = "CHTM",
    floor: str = "Floor_4F",
    floor_y: float | None = None,
    lintel_y: float | None = None,
    ceil_y: float | None = None,
) -> dict[str, Any]:
    """Convert one Real-Model Engine v2 GLB into a semantic cutaway Studio GLB."""
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

    # Build true exterior perimeter ring(s) from floor + standing walls so slanted exterior walls stay unified
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

    def _classify_mesh_wall_channels(
        verts: np.ndarray,
        faces: np.ndarray,
        edge_band: float = EDGE_BAND_M,
    ) -> np.ndarray:
        """Assign wall channels atomically per coplanar connected wall panel (zero Auto-cutaway spikes).

        Vertical wall triangles that share edges (up to 1mm vertex quantization) and have
        coplanar normals (dot > 0.995) stay in ONE single channel. Exterior channels are
        quadrant-consistent with InteriorStudioCanvas.tsx L560-573 sideDirX/Z signs.
        """
        n_faces = len(faces)
        out = np.full(n_faces, 4, dtype=np.int32)
        if n_faces == 0:
            return out

        v0 = verts[faces[:, 0]]
        v1 = verts[faces[:, 1]]
        v2 = verts[faces[:, 2]]
        e_cross = np.cross(v1 - v0, v2 - v0)
        dbl_area = np.linalg.norm(e_cross, axis=1)
        fn = np.divide(e_cross, np.maximum(dbl_area[:, None], 1e-12))
        face_areas = 0.5 * dbl_area
        fc = (v0 + v1 + v2) / 3.0

        mid_x = 0.5 * (float(in_min[0]) + float(in_max[0]))
        mid_z = 0.5 * (float(in_min[2]) + float(in_max[2]))
        half_w = max(0.5 * (float(in_max[0]) - float(in_min[0])), 1.0)
        half_d = max(0.5 * (float(in_max[2]) - float(in_min[2])), 1.0)

        def _point_quadrant_channel(px: float, pz: float, ox: float, oz: float) -> int:
            nx = (px - mid_x) / half_w
            nz = (pz - mid_z) / half_d
            if abs(ox) >= abs(oz):
                cand = 1 if ox >= 0.0 else 0
            else:
                cand = 2 if oz >= 0.0 else 3
            if (
                (cand == 0 and nx > 0.05)
                or (cand == 1 and nx < -0.05)
                or (cand == 2 and nz < -0.05)
                or (cand == 3 and nz > 0.05)
            ):
                if abs(nx) >= abs(nz):
                    return 1 if nx >= 0.0 else 0
                return 2 if nz >= 0.0 else 3
            return cand

        def _ring_dist_and_outward(px: float, pz: float) -> tuple[float, float, float]:
            if ext_rings:
                pt = Point(px, pz)
                best_ring = None
                best_d = 1e9
                for r in ext_rings:
                    d = float(pt.distance(r))
                    if d < best_d:
                        best_d = d
                        best_ring = r
                if best_ring is None:
                    return 1e9, 0.0, 0.0
                L = float(best_ring.length)
                s = float(best_ring.project(pt))
                pa = best_ring.interpolate((s - 0.45) % L)
                pb = best_ring.interpolate((s + 0.45) % L)
                ox = float(pb.y - pa.y)
                oz = -float(pb.x - pa.x)
                norm = math.hypot(ox, oz)
                if norm > 1e-9:
                    ox /= norm
                    oz /= norm
                return best_d, ox, oz
            dists = (
                (abs(px - env_min_x), -1.0, 0.0),
                (abs(env_max_x - px), 1.0, 0.0),
                (abs(env_max_z - pz), 0.0, 1.0),
                (abs(pz - env_min_z), 0.0, -1.0),
            )
            return min(dists, key=lambda item: item[0])

        # Cache per-XZ-coordinate queries within this mesh (rounded to 1cm)
        xz_cache: dict[tuple[float, float], tuple[float, float, float]] = {}

        def _cached_ring(px: float, pz: float) -> tuple[float, float, float]:
            key = (round(px, 2), round(pz, 2))
            hit = xz_cache.get(key)
            if hit is None:
                hit = _ring_dist_and_outward(px, pz)
                xz_cache[key] = hit
            return hit

        # Quantize 3D vertices to 1mm so duplicated-vertex quads merge cleanly across edges
        qkey_to_id: dict[tuple[int, int, int], int] = {}
        v_canon = np.empty(len(verts), dtype=np.int64)
        for vi, (vx, vy, vz) in enumerate(verts):
            qk = (int(round(float(vx) * 1000.0)), int(round(float(vy) * 1000.0)), int(round(float(vz) * 1000.0)))
            cid = qkey_to_id.get(qk)
            if cid is None:
                cid = len(qkey_to_id)
                qkey_to_id[qk] = cid
            v_canon[vi] = cid

        cf = v_canon[faces]
        edge_to_faces: dict[tuple[int, int], list[int]] = {}
        for fi in range(n_faces):
            a, b, c = int(cf[fi, 0]), int(cf[fi, 1]), int(cf[fi, 2])
            for u_v, w_v in ((a, b), (b, c), (c, a)):
                ek = (u_v, w_v) if u_v < w_v else (w_v, u_v)
                edge_to_faces.setdefault(ek, []).append(fi)

        adj: list[list[int]] = [[] for _ in range(n_faces)]
        for f_list in edge_to_faces.values():
            if len(f_list) < 2:
                continue
            for idx_a in range(len(f_list)):
                fa = f_list[idx_a]
                na = fn[fa]
                for idx_b in range(idx_a + 1, len(f_list)):
                    fb = f_list[idx_b]
                    if float(np.dot(na, fn[fb])) > 0.995:
                        adj[fa].append(fb)
                        adj[fb].append(fa)

        visited = np.zeros(n_faces, dtype=bool)
        for start in range(n_faces):
            if visited[start]:
                continue
            comp: list[int] = [start]
            visited[start] = True
            stack = [start]
            while stack:
                cur = stack.pop()
                for nb in adj[cur]:
                    if not visited[nb]:
                        visited[nb] = True
                        stack.append(nb)
                        comp.append(nb)

            comp_arr = np.asarray(comp, dtype=np.int64)
            weights = np.maximum(face_areas[comp_arr], 1e-6)
            mean_ny = float(np.average(fn[comp_arr, 1], weights=weights))

            if abs(mean_ny) < 0.55:
                sample_pts: set[tuple[float, float]] = set()
                for fi in comp:
                    a, b, c = int(faces[fi, 0]), int(faces[fi, 1]), int(faces[fi, 2])
                    ax, az = float(verts[a, 0]), float(verts[a, 2])
                    bx, bz = float(verts[b, 0]), float(verts[b, 2])
                    cx_, cz_ = float(verts[c, 0]), float(verts[c, 2])
                    for sx, sz in (
                        (ax, az),
                        (bx, bz),
                        (cx_, cz_),
                        (0.5 * (ax + bx), 0.5 * (az + bz)),
                        (0.5 * (bx + cx_), 0.5 * (bz + cz_)),
                        (0.5 * (cx_ + ax), 0.5 * (cz_ + az)),
                    ):
                        sample_pts.add((round(sx, 2), round(sz, 2)))
                ext_hits = sum(1 for sx, sz in sample_pts if _cached_ring(sx, sz)[0] <= edge_band)
                frac_ext = ext_hits / max(len(sample_pts), 1)
                if frac_ext < 0.85:
                    out[comp_arr] = 4
                else:
                    sum_ox = 0.0
                    sum_oz = 0.0
                    for fi, wt in zip(comp, weights):
                        _, ox, oz = _cached_ring(float(fc[fi, 0]), float(fc[fi, 2]))
                        sum_ox += float(wt) * ox
                        sum_oz += float(wt) * oz
                    cx_avg = float(np.average(fc[comp_arr, 0], weights=weights))
                    cz_avg = float(np.average(fc[comp_arr, 2], weights=weights))
                    out[comp_arr] = _point_quadrant_channel(cx_avg, cz_avg, sum_ox, sum_oz)
            else:
                for fi in comp:
                    all_verts_ext = True
                    for vk in faces[fi]:
                        if _cached_ring(float(verts[vk, 0]), float(verts[vk, 2]))[0] > edge_band:
                            all_verts_ext = False
                            break
                    if not all_verts_ext:
                        out[fi] = 4
                    else:
                        fx, fz = float(fc[fi, 0]), float(fc[fi, 2])
                        _, ox, oz = _cached_ring(fx, fz)
                        out[fi] = _point_quadrant_channel(fx, fz, ox, oz)

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

            # Upper stairs inside stair_zone (never contaminate OverheadBeams_And_Lintels)
            a_ch = _classify_mesh_wall_channels(above_lintel_v, above_lintel_f)
            if has_stairs:
                is_hi_stair = np.array(
                    [
                        (not wc) and (ch == 4) and stair_zone.contains(Point(float(xc), float(zc)))
                        for wc, ch, xc, zc in zip(is_wide_ceil, a_ch, ac[:, 0], ac[:, 2])
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
            is_ext_canopy = (~is_wide_ceil) & (~is_hi_stair) & out_of_env & (a_ch < 4)
            if np.any(is_ext_canopy):
                for ci in range(4):
                    sel = is_ext_canopy & (a_ch == ci)
                    if np.any(sel):
                        _add_group_mesh(
                            facade_names[ci],
                            mat_slug,
                            _make_mesh(above_lintel_v, above_lintel_f[sel], above_lintel_u, mat),
                        )

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
                rem_f = above_lintel_f[rem_mask]
                rem_ch = a_ch[rem_mask]
                for ci, cname in enumerate(ch_names):
                    sel = rem_ch == ci
                    if np.any(sel):
                        _add_group_mesh(f"{cname}__Upper", mat_slug, _make_mesh(above_lintel_v, rem_f[sel], above_lintel_u, mat))

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
                h_stair = np.array([stair_zone.contains(Point(float(xc), float(zc))) for xc, zc in zip(hc[:, 0], hc[:, 2])], dtype=bool)
                # Keep exterior perimeter walls in Wall_Ext_* even near stairwells
                h_ch = _classify_mesh_wall_channels(hi_band_v, hi_band_f)
                h_stair &= h_ch == 4
            else:
                h_stair = np.zeros(len(hi_band_f), dtype=bool)
                h_ch = _classify_mesh_wall_channels(hi_band_v, hi_band_f)

            if np.any(h_stair):
                _add_group_mesh("Stairs_Upper_01", mat_slug, _make_mesh(hi_band_v, hi_band_f[h_stair], hi_band_u, mat))
            for ci, cname in enumerate(ch_names):
                sel = (~h_stair) & (h_ch == ci)
                if np.any(sel):
                    _add_group_mesh(f"{cname}__Upper", mat_slug, _make_mesh(hi_band_v, hi_band_f[sel], hi_band_u, mat))

        if len(lo_band_f) == 0:
            continue

        # 4. Split lower band [fy + 0.03, cut_y] at plinth_y (fy + 0.06m) into __Plinth vs __Lower (and Stairs_01)
        from shapely.geometry import Point

        lc = lo_band_v[lo_band_f].mean(axis=1)
        l_ch = _classify_mesh_wall_channels(lo_band_v, lo_band_f)
        if has_stairs:
            l_stair = np.array([stair_zone.contains(Point(float(xc), float(zc))) for xc, zc in zip(lc[:, 0], lc[:, 2])], dtype=bool)
            l_stair &= l_ch == 4
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
            p_ch = _classify_mesh_wall_channels(plinth_v, plinth_f)
            for ci, cname in enumerate(ch_names):
                sel = p_ch == ci
                if np.any(sel):
                    m_pl = _make_mesh(plinth_v, plinth_f[sel], plinth_u, mat)
                    if m_pl is not None:
                        _add_group_mesh(f"{cname}__Plinth", mat_slug, m_pl)
                        channel_plinth_meshes[cname].append(m_pl)

        if len(lower_f) > 0:
            lw_ch = _classify_mesh_wall_channels(lower_v, lower_f)
            for ci, cname in enumerate(ch_names):
                sel = lw_ch == ci
                if np.any(sel):
                    m_lo = _make_mesh(lower_v, lower_f[sel], lower_u, mat)
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

    remaining_fp = unified_fp_2d
    ext_order = ("Wall_Ext_W_01", "Wall_Ext_E_01", "Wall_Ext_N_01", "Wall_Ext_S_01")
    partitioned_fps: dict[str, Any] = {}
    for cname in ext_order:
        if remaining_fp.is_empty or ch_zones[cname].is_empty:
            partitioned_fps[cname] = Polygon()
            continue
        piece = remaining_fp.intersection(ch_zones[cname]).buffer(0)
        partitioned_fps[cname] = piece
        remaining_fp = remaining_fp.difference(piece).buffer(0)
    partitioned_fps["Wall_Interior_01"] = remaining_fp

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
    if not plinth_fp_2d.is_empty:
        plinth_ch_zones: dict[str, Any] = {}
        for cname in cap_channel_map:
            ch_meshes = channel_lower_meshes[cname] + channel_plinth_meshes[cname]
            ch_segs = _extract_wall_section_segments(ch_meshes, fy + 0.04, plinth_slice_y, plinth_slice_y)
            plinth_ch_zones[cname] = (
                unary_union([s.buffer(0.45, join_style=2) for s in ch_segs]).buffer(0) if ch_segs else ch_zones[cname]
            )
        rem_pl = plinth_fp_2d
        pl_parts: dict[str, Any] = {}
        for cname in ext_order:
            if rem_pl.is_empty or plinth_ch_zones[cname].is_empty:
                pl_parts[cname] = Polygon()
                continue
            piece = rem_pl.intersection(plinth_ch_zones[cname]).buffer(0)
            pl_parts[cname] = piece
            rem_pl = rem_pl.difference(piece).buffer(0)
        pl_parts["Wall_Interior_01"] = rem_pl
        for cname in cap_channel_map:
            pl_mesh = _build_cutcap_mesh(pl_parts.get(cname, Polygon()), plinth_y + 0.002, cap_mat)
            if pl_mesh is not None and len(pl_mesh.faces) > 0:
                pl_cap_name = f"{cname}__Plinth__cut_cap"
                out_scene.add_geometry(pl_mesh, node_name=pl_cap_name, geom_name=pl_cap_name)
                group_tri_counts["Plinth_CutCap"] = group_tri_counts.get("Plinth_CutCap", 0) + len(pl_mesh.faces)

    # 6. Export GLB & run mandatory QA assertions
    output_glb.parent.mkdir(parents=True, exist_ok=True)
    out_scene.export(output_glb, file_type="glb")

    # Verify reload parity & Gate 5 (overhead_top_area <= 65 m^2)
    reloaded = trimesh.load(output_glb, force="scene")
    out_tris = sum(len(g.faces) for g in reloaded.geometry.values())
    out_min = np.min([g.vertices.min(axis=0) for g in reloaded.geometry.values() if len(g.vertices) > 0], axis=0)
    out_max = np.max([g.vertices.max(axis=0) for g in reloaded.geometry.values() if len(g.vertices) > 0], axis=0)
    max_bbox_delta = float(max(np.max(np.abs(out_min - in_min)), np.max(np.abs(out_max - in_max))))

    overhead_top_area_m2 = 0.0
    for gname, g in reloaded.geometry.items():
        if gname.startswith("OverheadBeams_"):
            up = g.face_normals[:, 1] > 0.85
            if np.any(up):
                overhead_top_area_m2 += float(g.area_faces[up].sum())

    required_groups = ["Floor_Slab"]
    if group_tri_counts.get("Wall_Interior_01", 0) > 0:
        required_groups.append("CutCap_Interior")
    missing_groups = [k for k in required_groups if group_tri_counts.get(k, 0) == 0]
    if sum(cap_counts.values()) == 0:
        missing_groups.append("CutCap_Any")

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
        "group_triangles": group_tri_counts,
        "cutcap_triangles": cap_counts,
        "qa_passed": (
            out_tris >= int(in_tris * 0.70)
            and max_bbox_delta <= 0.05
            and overhead_top_area_m2 <= 65.0
            and len(missing_groups) == 0
            and len(preserved_mats) >= 1
        ),
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
