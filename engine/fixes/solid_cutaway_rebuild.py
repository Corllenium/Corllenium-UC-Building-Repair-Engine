"""Engine v2 — Deterministic Manifold Solid Architectural Rebuilder (`solid-rebuild`).

Reads a raw architectural floor OBJ (Unity Y-up metres or CKPT-17 Z-up inches)
as exact 3D structural truth and reconstructs 100% watertight, zero-glitch,
stackable solid cutaway geometry via ``manifold3d`` + ``mapbox-earcut``:

- ``Floor_Slab``: continuous solid floor slab (+ genuine raised floor steps), 0 wall stubs.
- ``Stairs``: watertight solid stepped stair treads/risers (0 diagonal spiderwebs).
- ``Column_XX__Plinth / __Lower / __Upper``: isolated compact structural columns.
- ``Wall_Ext_{W,E,N,S}_XX__Plinth / __Lower / __Upper``: exterior perimeter walls
  cleanly split by outward side so Auto cutaway lowers camera-facing walls cleanly.
- ``Wall_Int_XX__Plinth / __Lower / __Upper``: interior partition walls with exact doorways & windows.
- ``Glass_Openings``: solid thin glazed panes inside real window openings.
- ``OverheadBeams_And_Lintels``: door/window header lintels (hidden in interior cutaway).

Designed generically across all UC buildings and floors (auto-detects units,
floor/slab/ceiling/sill/lintel elevations, columns, walls, stairs, and trim).
Never modifies raw ``building_repair.py`` or ``CHECKPOINT-17`` facade guards.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
from typing import Any, Sequence

import manifold3d as m3d
import numpy as np
from PIL import Image
from shapely.affinity import scale as shapely_scale
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiPolygon,
    Polygon,
    box as shapely_box,
)
from shapely.geometry.polygon import orient as shapely_orient
from shapely.ops import polygonize, unary_union
import trimesh


_DEFAULT_ORTHO_SNAP_M = 0.005
_MIN_POLY_AREA = 0.035


@dataclass
class MtlInfo:
    name: str
    map_kd: str | None = None
    kd: tuple[float, float, float] = (0.85, 0.85, 0.82)
    alpha: float = 1.0
    category: str = "structural"


@dataclass
class RawFloorMesh:
    positions: np.ndarray          # (V, 3) float64 in Unity Y-up metres
    faces: np.ndarray              # (F, 3) int64
    face_mats: list[str]
    materials: dict[str, MtlInfo]
    source_frame: str
    floor_y: float
    slab_bottom_y: float
    ceil_y: float
    baseboard_h: float
    sill_y: float
    lintel_y: float
    raised_levels: list[tuple[float, Any]]


@dataclass
class RebuildReport:
    out_dir: Path
    glb_path: Path | None
    obj_path: Path
    manifest: dict[str, Any]
    audit: dict[str, Any]
    passed: bool


# --------------------------------------------------------------------------- OBJ + MTL I/O


def _classify_material_category(name: str, tex_rel: str | None) -> str:
    joined = f"{name} {tex_rel or ''}".lower()
    if "glass" in joined:
        return "glass"
    if "littletiles" in joined:
        return "littletiles_trim"
    if "prismarine_dark" in joined:
        return "baseboard"
    if "concrete_green" in joined:
        return "exterior_accent"
    if "quartz_block_top" in joined:
        return "floor_tile"
    if "quartz_block" in joined or "iron_block" in joined or "metal_block" in joined:
        return "stair_mat"
    return "structural"


def _extract_map_kd_path(raw_val: str) -> str:
    """Strip OBJ MTL options like ``-s 1 1 1 -o 0 0 0 path/to/tex.png``."""
    tokens = raw_val.strip().split()
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("-o", "-s", "-t") and i + 3 < len(tokens):
            i += 4
        elif t in ("-mm",) and i + 2 < len(tokens):
            i += 3
        elif t in ("-clamp", "-imfchan", "-type", "-bm", "-texres") and i + 1 < len(tokens):
            i += 2
        else:
            return " ".join(tokens[i:]).strip()
    return tokens[-1] if tokens else raw_val.strip()


def parse_mtl_file(mtl_path: Path | None) -> dict[str, MtlInfo]:
    mats: dict[str, MtlInfo] = {}
    if mtl_path is None or not mtl_path.is_file():
        return mats
    cur: MtlInfo | None = None
    for line in mtl_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("newmtl "):
            mname = s.split(None, 1)[1].strip()
            cur = MtlInfo(name=mname)
            mats[mname] = cur
        elif cur is not None:
            if s.startswith("map_Kd "):
                cur.map_kd = _extract_map_kd_path(s.split(None, 1)[1])
            elif s.startswith("Kd "):
                parts = s.split()
                if len(parts) >= 4:
                    try:
                        cur.kd = (float(parts[1]), float(parts[2]), float(parts[3]))
                    except ValueError:
                        pass
            elif s.startswith("d "):
                parts = s.split()
                if len(parts) >= 2:
                    try:
                        cur.alpha = float(parts[1])
                    except ValueError:
                        pass
    for m in mats.values():
        m.category = _classify_material_category(m.name, m.map_kd)
    return mats


def load_raw_floor_obj(
    obj_path: Path,
    mtl_path: Path | None = None,
) -> RawFloorMesh:
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    fmats: list[str] = []
    cur_mat = "default"
    discovered_mtl: str | None = None

    with obj_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                p = line.split()
                if len(p) >= 4:
                    verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("mtllib ") and discovered_mtl is None:
                discovered_mtl = line.split(None, 1)[1].strip()
            elif line.startswith("usemtl "):
                cur_mat = line.split(None, 1)[1].strip()
            elif line.startswith("f "):
                idx = [int(tok.split("/")[0]) - 1 for tok in line.split()[1:]]
                for k in range(1, len(idx) - 1):
                    if idx[0] != idx[k] and idx[k] != idx[k + 1] and idx[0] != idx[k + 1]:
                        faces.append((idx[0], idx[k], idx[k + 1]))
                        fmats.append(cur_mat)

    pos = np.asarray(verts, dtype=np.float64)
    fa = np.asarray(faces, dtype=np.int64)
    if mtl_path is None and discovered_mtl:
        cand = obj_path.parent / discovered_mtl
        if cand.is_file():
            mtl_path = cand
    materials = parse_mtl_file(mtl_path)
    for m in set(fmats):
        if m not in materials:
            materials[m] = MtlInfo(name=m, category=_classify_material_category(m, None))

    # Detect inches Z-up (CKPT-17) vs metres Y-up (Unity export)
    span = pos.max(axis=0) - pos.min(axis=0)
    if span[2] < span[1] * 0.45 and np.abs(pos).max() > 800.0:
        # CKPT-17 inches Z-up -> Unity metres Y-up: (-X*0.0254, Z*0.0254, Y*0.0254)
        INCH_TO_M = 0.0254
        pos_m = np.column_stack([-pos[:, 0] * INCH_TO_M, pos[:, 2] * INCH_TO_M, pos[:, 1] * INCH_TO_M])
        fa = fa[:, [0, 2, 1]]  # maintain outward winding across single axis negation
        source_frame = "ckpt17_inches_zup"
    else:
        pos_m = pos
        source_frame = "unity_metres_yup"

    # Compute normals and areas to auto-detect architectural elevation planes
    p0, p1, p2 = pos_m[fa[:, 0]], pos_m[fa[:, 1]], pos_m[fa[:, 2]]
    cr = np.cross(p1 - p0, p2 - p0)
    norms_len = np.linalg.norm(cr, axis=1)
    areas = 0.5 * norms_len
    unit_n = cr / np.maximum(norms_len[:, None], 1e-12)
    yc = pos_m[fa].mean(axis=1)[:, 1]
    y_lo, y_hi = float(pos_m[:, 1].min()), float(pos_m[:, 1].max())
    y_span = max(y_hi - y_lo, 1.0)

    up_mask = unit_n[:, 1] > 0.85
    dn_mask = unit_n[:, 1] < -0.85

    up_hist: dict[float, float] = defaultdict(float)
    for yv, a in zip(np.round(yc[up_mask] / 0.005) * 0.005, areas[up_mask]):
        up_hist[round(float(yv), 3)] += float(a)
    dn_hist: dict[float, float] = defaultdict(float)
    for yv, a in zip(np.round(yc[dn_mask] / 0.005) * 0.005, areas[dn_mask]):
        dn_hist[round(float(yv), 3)] += float(a)

    floor_cands = [(y, a) for y, a in up_hist.items() if y <= y_lo + 0.45 * y_span]
    floor_y = max(floor_cands, key=lambda kv: kv[1])[0] if floor_cands else y_lo + 0.5

    bot_cands = [(y, a) for y, a in dn_hist.items() if y <= floor_y - 0.15]
    slab_bottom_y = max(bot_cands, key=lambda kv: kv[1])[0] if bot_cands else floor_y - 0.50

    ceil_cands = [(y, a) for y, a in up_hist.items() if y >= floor_y + 2.40]
    ceil_y = max(ceil_cands, key=lambda kv: kv[1])[0] if ceil_cands else max(y_hi, floor_y + 3.75)

    # Detect genuine raised floor platforms (area >= 2.0 m^2 in [floor_y + 0.05, floor_y + 0.45])
    raised_levels: list[tuple[float, Any]] = []
    for y_plat, a_plat in sorted(up_hist.items()):
        if floor_y + 0.05 <= y_plat <= floor_y + 0.45 and a_plat >= 2.0:
            pmask = up_mask & (np.abs(yc - y_plat) < 0.025)
            polys = []
            for f in fa[pmask]:
                mat_cat = materials[fmats[0]].category if False else None  # noqa: SIM222
                poly = Polygon(pos_m[f][:, [0, 2]]).buffer(0)
                if poly.area > 1e-4:
                    polys.append(poly)
            if polys:
                u = _clean_shapely(unary_union(polys), 0.01)
                big_comps = [
                    p for p in _iter_polygons(u)
                    if p.area >= 2.2 and min(p.bounds[2] - p.bounds[0], p.bounds[3] - p.bounds[1]) >= 1.2
                ]
                if big_comps:
                    raised_levels.append((y_plat, unary_union(big_comps)))

    # Baseboard height (prismarine_dark top, else 0.50m)
    bb_mask = np.array([materials[m].category == "baseboard" for m in fmats]) & (np.abs(unit_n[:, 1]) < 0.3)
    if bb_mask.any():
        bb_ymax = float(pos_m[fa[bb_mask], 1].max())
        baseboard_h = max(0.25, min(0.75, bb_ymax - floor_y))
    else:
        baseboard_h = 0.50

    # Window sill height from glass
    gl_mask = np.array([materials[m].category == "glass" for m in fmats])
    if gl_mask.any():
        gl_ymin = float(pos_m[fa[gl_mask], 1].min())
        sill_y = max(floor_y + 0.75, min(floor_y + 1.45, gl_ymin))
    else:
        sill_y = floor_y + 1.125

    # Door/window header lintel soffit
    lintel_cands = [(y, a) for y, a in dn_hist.items() if floor_y + 1.85 <= y <= floor_y + 2.55]
    lintel_y = max(lintel_cands, key=lambda kv: kv[1])[0] if lintel_cands else floor_y + 2.125

    return RawFloorMesh(
        positions=pos_m,
        faces=fa,
        face_mats=fmats,
        materials=materials,
        source_frame=source_frame,
        floor_y=floor_y,
        slab_bottom_y=slab_bottom_y,
        ceil_y=ceil_y,
        baseboard_h=baseboard_h,
        sill_y=sill_y,
        lintel_y=lintel_y,
        raised_levels=raised_levels,
    )


# --------------------------------------------------------------------------- Shapely & Manifold helpers


def _iter_polygons(geom: Any) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom] if geom.area >= 1e-6 else []
    if isinstance(geom, (MultiPolygon, GeometryCollection)):
        out: list[Polygon] = []
        for g in geom.geoms:
            out.extend(_iter_polygons(g))
        return out
    return []


def _fill_small_holes(geom: Any, max_hole_area: float = 0.35) -> Any:
    """Close tiny interior chase/void pinholes inside solid wall or landing polygons."""
    polys: list[Polygon] = []
    for p in _iter_polygons(geom):
        kept_holes = [h for h in p.interiors if Polygon(h).area >= max_hole_area]
        polys.append(Polygon(p.exterior, kept_holes).buffer(0))
    if not polys:
        return Polygon()
    return unary_union(polys).buffer(0)


def _clean_shapely(geom: Any, eps: float = 0.008) -> Any:
    if geom is None or geom.is_empty:
        return Polygon()
    g = geom.buffer(0)
    if eps > 0:
        g = g.buffer(eps, join_style=2).buffer(-eps, join_style=2).buffer(0)
    polys = [p for p in _iter_polygons(g) if p.area >= _MIN_POLY_AREA * 0.5]
    if not polys:
        return Polygon()
    return unary_union(polys).buffer(0)


def _regularize_polygon(poly: Polygon, snap_m: float = 0.005) -> Polygon:
    """Snap near-orthogonal coordinates cleanly without losing genuine angled walls."""
    def _ring(coords: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for x, z in coords[:-1]:
            sx = round(float(x) / snap_m) * snap_m
            sz = round(float(z) / snap_m) * snap_m
            if not out or (abs(sx - out[-1][0]) > 1e-5 or abs(sz - out[-1][1]) > 1e-5):
                out.append((sx, sz))
        if len(out) >= 3:
            out.append(out[0])
        return out

    ext = _ring(list(poly.exterior.coords))
    if len(ext) < 4:
        return Polygon()
    holes = []
    for h in poly.interiors:
        hr = _ring(list(h.coords))
        if len(hr) >= 4:
            holes.append(hr)
    p = Polygon(ext, holes).buffer(0)
    if isinstance(p, MultiPolygon):
        p = max(p.geoms, key=lambda g: g.area)
    if not isinstance(p, Polygon) or p.area < _MIN_POLY_AREA:
        return Polygon()
    return p.simplify(0.004, preserve_topology=True)


def _dedup_ring(coords: Sequence[tuple[float, float]], min_dist: float = 2e-3) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for x, z in coords[:-1]:
        fx, fz = float(x), float(z)
        if not pts or math.hypot(fx - pts[-1][0], fz - pts[-1][1]) >= min_dist:
            pts.append((fx, fz))
    if len(pts) >= 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < min_dist:
        pts.pop()
    # Prune collinear ring vertices so cap triangulation never emits zero-area triangles
    changed = True
    while changed and len(pts) >= 4:
        changed = False
        keep_pts: list[tuple[float, float]] = []
        n = len(pts)
        for i in range(n):
            a = pts[(i - 1) % n]
            b = pts[i]
            c = pts[(i + 1) % n]
            ab_len = math.hypot(b[0] - a[0], b[1] - a[1])
            bc_len = math.hypot(c[0] - b[0], c[1] - b[1])
            cross = abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
            if cross <= 1e-6 * max(ab_len * bc_len, 1e-9):
                changed = True
                continue
            keep_pts.append(b)
        if len(keep_pts) >= 3:
            pts = keep_pts
        else:
            break
    return pts


def _extrude_polygon_earcut_yup(poly: Polygon, y_min: float, y_max: float) -> trimesh.Trimesh | None:
    if y_max - y_min <= 1e-4 or poly.is_empty or poly.area < 1e-4:
        return None
    poly = poly.simplify(0.004, preserve_topology=True)
    if poly.is_empty or poly.area < 1e-4:
        return None
    op = shapely_orient(poly, 1.0)
    ext = _dedup_ring(list(op.exterior.coords))
    if len(ext) < 3:
        return None
    holes = []
    for h in op.interiors:
        if Polygon(h).area >= 1e-4:
            hr = _dedup_ring(list(h.coords))
            if len(hr) >= 3:
                holes.append(hr)
    clean_p = Polygon(ext, holes).buffer(0)
    if isinstance(clean_p, MultiPolygon):
        parts = [_extrude_polygon_earcut_yup(g, y_min, y_max) for g in clean_p.geoms]
        valid = [p for p in parts if p is not None]
        return trimesh.util.concatenate(valid) if valid else None
    if not isinstance(clean_p, Polygon) or clean_p.is_empty:
        return None
    tm_z = trimesh.creation.extrude_polygon(clean_p, float(y_max - y_min), engine="earcut")
    vp = tm_z.vertices
    verts_yup = np.column_stack([vp[:, 0], vp[:, 2] + float(y_min), vp[:, 1]])
    faces_yup = tm_z.faces[:, [0, 2, 1]]
    tm = trimesh.Trimesh(vertices=verts_yup, faces=faces_yup, process=False)
    if tm.volume < 0:
        tm.faces = tm.faces[:, [0, 2, 1]]
    return tm


def _polygon_to_manifold(poly: Polygon, y_min: float, y_max: float) -> m3d.Manifold | None:
    if y_max - y_min <= 1e-4 or poly.is_empty or poly.area < 1e-4:
        return None
    poly = poly.simplify(0.004, preserve_topology=True)
    if poly.is_empty or poly.area < 1e-4:
        return None
    op = shapely_orient(poly, 1.0)
    ext_pts = _dedup_ring(list(op.exterior.coords))
    if len(ext_pts) < 3:
        return None
    rings = [np.asarray(ext_pts, dtype=np.float64)]
    for hole in op.interiors:
        if Polygon(hole).area >= 1e-4:
            h_pts = _dedup_ring(list(hole.coords))
            if len(h_pts) >= 3:
                rings.append(np.asarray(h_pts, dtype=np.float64))
    cs = m3d.CrossSection(rings).simplify(0.005)
    if cs.is_empty():
        return None
    man = m3d.Manifold.extrude(cs, float(y_max - y_min))
    if man.is_empty() or man.num_tri() == 0:
        return None
    # Rotate from Manifold Z-up (x, z_2d, y_ext) to Unity Y-up (x, y_ext + y_min, z_2d).
    # Note: 3D axis swap (x, y, z) -> (x, z, y) reverses handedness; manifold_to_trimesh handles orientation cleanly.
    return man.translate((0.0, 0.0, float(y_min)))


def geom_to_manifold(geom: Any, y_min: float, y_max: float) -> m3d.Manifold | None:
    parts: list[m3d.Manifold] = []
    for p in _iter_polygons(geom):
        m = _polygon_to_manifold(p, y_min, y_max)
        if m is not None:
            parts.append(m)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return m3d.Manifold.batch_boolean(parts, m3d.OpType.Add)


def manifold_to_trimesh(man: m3d.Manifold) -> trimesh.Trimesh:
    """Convert Z-up Manifold (where Z = height, Y = Z_world) to Unity Y-up Trimesh with positive volume."""
    mesh = man.to_mesh()
    vp = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    fa = np.asarray(mesh.tri_verts, dtype=np.int64)
    # Map (x, z_2d, y_height) -> (x, y_height, z_2d) and flip winding to restore +volume
    verts_yup = np.column_stack([vp[:, 0], vp[:, 2], vp[:, 1]])
    faces_yup = fa[:, [0, 2, 1]]
    tm = trimesh.Trimesh(vertices=verts_yup, faces=faces_yup, process=False)
    if tm.volume < 0:
        tm.faces = tm.faces[:, [0, 2, 1]]
    return tm


def _slice_trimesh_at_y(tm: trimesh.Trimesh, y_cut: float) -> trimesh.Trimesh:
    """Split every straddling triangle horizontally at ``y_cut`` while keeping 100% watertightness."""
    verts = tm.vertices
    y_vals = verts[:, 1]
    if float(y_vals.min()) >= y_cut - 1e-5 or float(y_vals.max()) <= y_cut + 1e-5:
        return tm

    new_verts = list(verts)
    edge_cache: dict[tuple[int, int], int] = {}

    def _interp(ia: int, ib: int) -> int:
        key = (ia, ib) if ia < ib else (ib, ia)
        cached = edge_cache.get(key)
        if cached is not None:
            return cached
        pa, pb = verts[ia], verts[ib]
        t = (y_cut - pa[1]) / (pb[1] - pa[1])
        pt = pa + t * (pb - pa)
        pt[1] = y_cut
        vid = len(new_verts)
        new_verts.append(pt)
        edge_cache[key] = vid
        return vid

    new_faces: list[tuple[int, int, int]] = []
    eps = 1e-6
    for a, b, c in tm.faces:
        ya, yb, yc_v = float(y_vals[a] - y_cut), float(y_vals[b] - y_cut), float(y_vals[c] - y_cut)
        above = [abs(ya) > eps and ya > 0, abs(yb) > eps and yb > 0, abs(yc_v) > eps and yc_v > 0]
        below = [abs(ya) > eps and ya < 0, abs(yb) > eps and yb < 0, abs(yc_v) > eps and yc_v < 0]
        if not (any(above) and any(below)):
            new_faces.append((int(a), int(b), int(c)))
            continue
        # Rotate cyclic order so vertices[0] is on the lone side (or on y_cut)
        idx = [int(a), int(b), int(c)]
        dy = [ya, yb, yc_v]
        # Find lone non-zero vertex (either 1 above and 1/2 below, or 1 below and 2 above)
        n_ab = sum(above)
        n_bl = sum(below)
        if n_ab == 1 and n_bl == 1:
            # One vertex is ON y_cut! Rotate so that on-plane vertex is first
            k0 = next(k for k in range(3) if not above[k] and not below[k])
            v0, v1, v2 = idx[k0], idx[(k0 + 1) % 3], idx[(k0 + 2) % 3]
            pm = _interp(v1, v2)
            new_faces.append((v0, v1, pm))
            new_faces.append((v0, pm, v2))
        else:
            # 1 vertex on one side, 2 on the other -> split into 1 tri + 1 quad (2 tris)
            lone_flag = (n_ab == 1)
            k0 = next(k for k in range(3) if above[k] == lone_flag)
            v0, v1, v2 = idx[k0], idx[(k0 + 1) % 3], idx[(k0 + 2) % 3]
            p01 = _interp(v0, v1)
            p02 = _interp(v0, v2)
            new_faces.append((v0, p01, p02))
            new_faces.append((p01, v1, v2))
            new_faces.append((p01, v2, p02))

    return trimesh.Trimesh(
        vertices=np.asarray(new_verts, dtype=np.float64),
        faces=np.asarray(new_faces, dtype=np.int64),
        process=False,
    )


# --------------------------------------------------------------------------- 2D Slice Extraction


def _extract_solid_slice(
    struct_tm: trimesh.Trimesh,
    y_plane: float,
    any_cap: Any,
    max_room_area: float = 24.0,
) -> Any:
    """Slice ``struct_tm`` at ``y_plane``, polygonize, and filter empty air vs solid structure."""
    segs = trimesh.intersections.mesh_plane(struct_tm, [0.0, 1.0, 0.0], [0.0, y_plane, 0.0])
    if len(segs) == 0:
        return Polygon()
    lines: list[LineString] = []
    for s in segs:
        p0 = (round(float(s[0, 0]), 3), round(float(s[0, 2]), 3))
        p1 = (round(float(s[1, 0]), 3), round(float(s[1, 2]), 3))
        if p0 != p1:
            lines.append(LineString([p0, p1]))
    if not lines:
        return Polygon()

    noded = unary_union(lines)
    polys = [p for p in polygonize(noded) if p.area >= _MIN_POLY_AREA]
    solids: list[Polygon] = []
    for p in polys:
        if p.area > max_room_area:
            continue
        rov = p.intersection(any_cap).area / max(p.area, 1e-9)
        if rov > 0.45:
            rp = _regularize_polygon(p)
            if not rp.is_empty:
                solids.append(rp)
    if not solids:
        return Polygon()
    return _clean_shapely(unary_union(solids), 0.005)


def _extract_floor_and_stairs(
    raw: RawFloorMesh,
    standing_walls_low: Any,
    standing_walls_mid: Any | None = None,
) -> tuple[Any, list[tuple[float, float, Any]]]:
    """Build solid Floor_Slab footprint and quantized watertight Stair steps."""
    pos, fa, mats, fmats = raw.positions, raw.faces, raw.materials, raw.face_mats
    p0, p1, p2 = pos[fa[:, 0]], pos[fa[:, 1]], pos[fa[:, 2]]
    cr = np.cross(p1 - p0, p2 - p0)
    lens = np.linalg.norm(cr, axis=1)
    unit_n = cr / np.maximum(lens[:, None], 1e-12)
    yc = pos[fa].mean(axis=1)[:, 1]
    keep = np.array([mats[m].category not in ("littletiles_trim", "glass") for m in fmats])

    # Floor slab bottom covers the whole structural underside; floor top covers walkable interior
    bot_mask = keep & (unit_n[:, 1] < -0.85) & (np.abs(yc - raw.slab_bottom_y) < 0.05)
    top_mask = keep & (unit_n[:, 1] > 0.85) & (np.abs(yc - raw.floor_y) < 0.04)
    slab_polys = []
    for f in fa[bot_mask | top_mask]:
        poly = Polygon(pos[f][:, [0, 2]]).buffer(0)
        if poly.area > 1e-4:
            slab_polys.append(poly)
    floor_fp = _clean_shapely(unary_union(slab_polys), 0.015)
    reg_floors = [_regularize_polygon(p, 0.01) for p in _iter_polygons(floor_fp)]
    floor_fp = _clean_shapely(unary_union([p for p in reg_floors if not p.is_empty]), 0.005)

    # Height-aware wall exclusion (low walls exclude < floor_y+1.15m; mid walls allow upper landings above storage walls)
    raised_union = unary_union([rp for _, rp in raw.raised_levels]) if raw.raised_levels else Polygon()
    excl_low = unary_union([standing_walls_low.buffer(0.015, join_style=2), raised_union.buffer(0.015, join_style=2)])
    if standing_walls_mid is not None and not standing_walls_mid.is_empty:
        excl_high = standing_walls_mid.buffer(0.015, join_style=2)
    else:
        excl_high = standing_walls_low.buffer(0.015, join_style=2)

    # Isolate real quartz/stair tread surfaces across descending & ascending flights (strip concrete/green walls)
    keep_stair = np.array([mats[m].category in ("floor_tile", "stair_mat") for m in fmats])
    step_mask = (
        keep_stair
        & (unit_n[:, 1] > 0.85)
        & (
            ((yc >= raw.floor_y + 0.08) & (yc <= raw.ceil_y - 0.12))
            | ((yc >= raw.slab_bottom_y + 0.10) & (yc <= raw.floor_y - 0.05))
        )
    )
    treads_by_y: dict[float, list[Polygon]] = defaultdict(list)
    for f, yy in zip(fa[step_mask], yc[step_mask]):
        yr = round(round(float(yy) / 0.05) * 0.05, 3)
        p = Polygon(pos[f][:, [0, 2]]).buffer(0)
        if p.area < 1e-4:
            continue
        excl = excl_high if yr >= raw.floor_y + 1.15 else excl_low
        diff = p.difference(excl)
        for dp in _iter_polygons(diff):
            # Stair treads sit over or adjacent to the slab (avoid distant exterior awnings)
            if dp.area >= 0.04 and (floor_fp.is_empty or floor_fp.buffer(1.8).intersects(dp)):
                treads_by_y[yr].append(dp)

    # Strip < 28 cm handrail/baluster curbs cleanly while keeping >= 35 cm stair treads & landings up to 24m2 intact
    tread_levels: list[tuple[float, Any]] = []
    for yr, plist in sorted(treads_by_y.items()):
        u = _clean_shapely(unary_union(plist), 0.01)
        for p in _iter_polygons(u):
            p_open = _clean_shapely(p.buffer(-0.14, join_style=2).buffer(0.14, join_style=2), 0.005)
            for op in _iter_polygons(p_open):
                rp = _regularize_polygon(op, 0.01)
                if not rp.is_empty and 0.35 <= rp.area <= 24.0:
                    tread_levels.append((yr, rp))

    if not tread_levels:
        return floor_fp, []

    # Physical headroom deduplication: strip impossible +0.30..+1.35m duplicate inner voxel layers, keep >=1.8m switchbacks
    accepted: list[tuple[float, Polygon]] = []
    for yr, rp in sorted(tread_levels, key=lambda item: item[0]):
        lowers = [p_prev.buffer(0.02, join_style=2) for y_prev, p_prev in accepted if 0.30 <= (yr - y_prev) <= 1.35]
        rp_eff = _clean_shapely(rp.difference(unary_union(lowers)), 0.005) if lowers else rp
        for kp in _iter_polygons(rp_eff):
            if kp.area >= 0.35 and not kp.buffer(-0.12, join_style=2).is_empty:
                accepted.append((yr, kp))

    if not accepted:
        return floor_fp, []

    all_tread_union = _clean_shapely(unary_union([p for _, p in accepted]), 0.35)
    valid_stair_steps: list[tuple[float, float, Any]] = []
    for comp in _iter_polygons(all_tread_union):
        comp_steps = [(yr, p) for yr, p in accepted if comp.intersects(p)]
        distinct_y = sorted({round(yr, 2) for yr, _ in comp_steps})
        if len(distinct_y) >= 2:
            # Close stairwell base underneath descending steps so black background never shows through
            below_steps = [p for yr, p in comp_steps if yr < raw.floor_y - 0.04]
            if below_steps:
                floor_fp = _clean_shapely(unary_union([floor_fp] + below_steps), 0.01)
            for yr, p in comp_steps:
                y0 = raw.slab_bottom_y if yr < raw.floor_y - 0.04 else raw.floor_y
                valid_stair_steps.append((y0, yr, p))

    return floor_fp, valid_stair_steps


def _align_mid_to_base(p_base: Any, raw_mid: Any) -> Any:
    """Keep only genuine window openings (>= 6 cm deep) in p_mid; align wall edges cleanly to p_base."""
    if raw_mid is None or raw_mid.is_empty:
        return Polygon()
    inside = _clean_shapely(raw_mid.intersection(p_base), 0.002)
    if inside.is_empty:
        return Polygon()
    # Any tiny edge jitter between S_base and S_mid (< 8 cm thick) is NOT a real window opening
    real_gaps = _clean_shapely(p_base.difference(inside).buffer(-0.04, join_style=2).buffer(0.04, join_style=2), 0.002)
    if real_gaps.is_empty:
        return p_base
    return _clean_shapely(p_base.difference(real_gaps), 0.002)


def _separate_columns_and_split_walls(
    S_base: Any,
    S_mid: Any,
    floor_fp: Any,
    column_min_width_m: float = 0.56,
) -> tuple[list[tuple[str, Polygon]], list[tuple[str, str, Polygon, Polygon]]]:
    """Isolate compact columns vs thick/thin walls; tag Ext_W/E/N/S vs Int cleanly."""
    r = max(0.20, column_min_width_m * 0.5)
    opened = S_base.buffer(-r, join_style=2).buffer(r, join_style=2).intersection(S_base)
    columns: list[tuple[str, Polygon]] = []
    col_geoms: list[Polygon] = []

    for cand in _iter_polygons(_clean_shapely(opened, 0.005)):
        bx0, bz0, bx1, bz1 = cand.bounds
        w, d = bx1 - bx0, bz1 - bz0
        fill = cand.area / max(w * d, 1e-6)
        if w <= 3.25 and d <= 3.25 and cand.area <= 9.0 and fill >= 0.65:
            col_geoms.append(cand)

    col_geoms.sort(key=lambda p: (round(p.centroid.x, 2), round(p.centroid.y, 2)))
    for i, cg in enumerate(col_geoms, start=1):
        columns.append((f"Column_{i:02d}", cg))

    col_union = unary_union(col_geoms) if col_geoms else Polygon()
    walls_base = _clean_shapely(S_base.difference(col_union), 0.0)
    walls_mid = _clean_shapely(S_mid.difference(col_union), 0.0)

    # True perimeter band (from actual building footprint exterior, not convex hull, so recessed walls stay exact)
    outer_src = floor_fp if not floor_fp.is_empty else S_base
    if isinstance(outer_src, MultiPolygon):
        outer_src = max(outer_src.geoms, key=lambda g: g.area)
    outer_ring = outer_src.exterior
    outer_band = outer_ring.buffer(1.65, join_style=2)
    bx0, bz0, bx1, bz1 = S_base.bounds
    cx, cz = 0.5 * (bx0 + bx1), 0.5 * (bz0 + bz1)
    span_x = max(bx1 - bx0, 1.0)
    span_z = max(bz1 - bz0, 1.0)

    # Partition exterior bounding frame into 4 angular Voronoi wedges (W, E, N, S)
    # so long connected perimeter walls get split cleanly by outward camera side!
    M = max(span_x, span_z) * 2.0 + 10.0
    side_wedges = {
        "W": Polygon([(bx0 - M, bz0 - M), (bx0 - M, bz1 + M), (cx, cz)]),
        "E": Polygon([(bx1 + M, bz0 - M), (cx, cz), (bx1 + M, bz1 + M)]),
        "N": Polygon([(bx0 - M, bz1 + M), (bx1 + M, bz1 + M), (cx, cz)]),
        "S": Polygon([(bx0 - M, bz0 - M), (cx, cz), (bx1 + M, bz0 - M)]),
    }

    wall_groups: list[tuple[str, str, Polygon, Polygon]] = []
    ext_idx = {"W": 0, "E": 0, "N": 0, "S": 0}
    int_idx = 0

    for wp in sorted(_iter_polygons(walls_base), key=lambda p: (round(p.centroid.x, 2), round(p.centroid.y, 2))):
        ext_part = _clean_shapely(wp.intersection(outer_band), 0.0)
        int_part = _clean_shapely(wp.difference(outer_band), 0.0)

        for sp_ext in _iter_polygons(ext_part):
            if sp_ext.area < 0.04:
                continue
            for side, wedge in side_wedges.items():
                sub_b = _clean_shapely(sp_ext.intersection(wedge), 0.0)
                for sp in _iter_polygons(sub_b):
                    if sp.area < 0.04 or sp.buffer(-0.02, join_style=2).is_empty:
                        continue
                    ext_idx[side] += 1
                    gname = f"Wall_Ext_{side}_{ext_idx[side]:02d}"
                    sm = _align_mid_to_base(sp, walls_mid)
                    wall_groups.append((gname, f"ext_{side}", sp, sm))

        for sp_int in _iter_polygons(int_part):
            if sp_int.area < 0.04 or sp_int.buffer(-0.02, join_style=2).is_empty:
                continue
            int_idx += 1
            gname = f"Wall_Int_{int_idx:02d}"
            sm = _align_mid_to_base(sp_int, walls_mid)
            wall_groups.append((gname, "interior", sp_int, sm))

    return columns, wall_groups


# --------------------------------------------------------------------------- Texturing & GLB Export


def _load_texture_image(tex_dir: Path | None, filename_substr: str) -> Image.Image | None:
    if tex_dir is None or not tex_dir.is_dir():
        return None
    exact = tex_dir / filename_substr
    if exact.is_file():
        try:
            return Image.open(exact).convert("RGBA")
        except Exception:
            return None
    low = filename_substr.lower()
    for p in sorted(tex_dir.iterdir()):
        if low in p.name.lower() and p.suffix.lower() in (".png", ".jpg", ".jpeg"):
            try:
                return Image.open(p).convert("RGBA")
            except Exception:
                return None
    return None


def _build_raw_pbr_palette(
    raw: RawFloorMesh,
    textures_dir: Path | None,
) -> tuple[dict[str, trimesh.visual.material.PBRMaterial], dict[str, str], dict[str, str]]:
    """Build real PBR materials matching EVERY original raw MTL texture + alias/category maps."""
    mat_defs: dict[str, trimesh.visual.material.PBRMaterial] = {
        "cut_cap": trimesh.visual.material.PBRMaterial(
            name="UC_Solid_CutCap",
            baseColorFactor=[64, 76, 70, 255],
            metallicFactor=0.04,
            roughnessFactor=0.92,
            doubleSided=False,
        ),
    }
    raw_to_key: dict[str, str] = {}
    key_to_cat: dict[str, str] = {"cut_cap": "cut_cap"}
    tex_cache: dict[str, Image.Image | None] = {}

    for rname, minfo in raw.materials.items():
        if minfo.category == "littletiles_trim":
            continue
        tex_base = Path(minfo.map_kd).name if minfo.map_kd else ""
        if minfo.category == "glass":
            mkey = "glass"
            if mkey not in mat_defs:
                timg = _load_texture_image(textures_dir, tex_base or "glass_white")
                mat_defs[mkey] = trimesh.visual.material.PBRMaterial(
                    name="UC_Glass",
                    baseColorFactor=[180, 225, 240, 105],
                    baseColorTexture=timg,
                    metallicFactor=0.10,
                    roughnessFactor=0.18,
                    alphaMode="BLEND",
                    doubleSided=False,
                )
            raw_to_key[rname] = mkey
            key_to_cat[mkey] = "glass"
            continue

        if tex_base:
            mkey = "tex_" + re.sub(r"[^a-zA-Z0-9_]+", "_", Path(tex_base).stem).strip("_")
            if mkey not in mat_defs:
                if tex_base not in tex_cache:
                    tex_cache[tex_base] = _load_texture_image(textures_dir, tex_base)
                timg = tex_cache[tex_base]
                mat_defs[mkey] = trimesh.visual.material.PBRMaterial(
                    name=mkey,
                    baseColorFactor=[242, 242, 240, 255] if timg is not None else [
                        int(round(max(0.0, min(1.0, minfo.kd[0])) * 255)),
                        int(round(max(0.0, min(1.0, minfo.kd[1])) * 255)),
                        int(round(max(0.0, min(1.0, minfo.kd[2])) * 255)),
                        255,
                    ],
                    baseColorTexture=timg,
                    metallicFactor=0.04,
                    roughnessFactor=0.86,
                    doubleSided=False,
                )
        else:
            mkey = f"mat_{len(mat_defs)}"
            mat_defs[mkey] = trimesh.visual.material.PBRMaterial(
                name=rname,
                baseColorFactor=[
                    int(round(max(0.0, min(1.0, minfo.kd[0])) * 255)),
                    int(round(max(0.0, min(1.0, minfo.kd[1])) * 255)),
                    int(round(max(0.0, min(1.0, minfo.kd[2])) * 255)),
                    255,
                ],
                metallicFactor=0.04,
                roughnessFactor=0.86,
                doubleSided=False,
            )
        raw_to_key[rname] = mkey
        if mkey not in key_to_cat or minfo.category != "structural":
            key_to_cat[mkey] = minfo.category

    if "fallback_wall" not in mat_defs:
        tex_w = _load_texture_image(textures_dir, "concrete_white_-1.") or _load_texture_image(textures_dir, "concrete_white")
        mat_defs["fallback_wall"] = trimesh.visual.material.PBRMaterial(
            name="UC_Fallback_Wall",
            baseColorFactor=[238, 240, 236, 255],
            baseColorTexture=tex_w,
            metallicFactor=0.04,
            roughnessFactor=0.86,
            doubleSided=False,
        )
    key_to_cat.setdefault("fallback_wall", "structural")
    if "fallback_floor" not in mat_defs:
        tex_f = _load_texture_image(textures_dir, "quartz_block_top")
        mat_defs["fallback_floor"] = trimesh.visual.material.PBRMaterial(
            name="UC_Fallback_Floor",
            baseColorFactor=[225, 218, 204, 255],
            baseColorTexture=tex_f,
            metallicFactor=0.04,
            roughnessFactor=0.86,
            doubleSided=False,
        )
    key_to_cat.setdefault("fallback_floor", "floor_tile")
    return mat_defs, raw_to_key, key_to_cat


def _area_vote_key(keys: Sequence[str], areas: np.ndarray, mask: np.ndarray, default: str) -> str:
    idxs = np.where(mask)[0]
    if len(idxs) == 0:
        return default
    totals: dict[str, float] = defaultdict(float)
    for idx in idxs:
        totals[keys[int(idx)]] += float(areas[int(idx)])
    return max(totals.items(), key=lambda kv: kv[1])[0]


def _assign_clean_raw_materials(
    t_verts: np.ndarray,
    t_faces: np.ndarray,
    fc: np.ndarray,
    fn: np.ndarray,
    raw_up_pts: np.ndarray,
    raw_up_keys: list[str],
    raw_up_cats: np.ndarray,
    raw_up_areas: np.ndarray,
    raw_vert_pts: np.ndarray,
    raw_vert_n_xz: np.ndarray,
    raw_vert_keys: list[str],
    raw_vert_cats: np.ndarray,
    raw_vert_areas: np.ndarray,
    key_to_cat: dict[str, str],
    dom_floor_top_key: str,
    dom_floor_side_key: str,
    dom_baseboard_key: str | None,
    dom_wall_key: str,
    floor_y: float,
    y_bb_cut: float,
    kind: str,
    is_plinth: bool,
    is_lower: bool,
    tier_top: float,
) -> list[str]:
    """Semantic + normal-aligned + planar-face texture assignment (0 bleed across floor/wall bands)."""
    n = len(fc)
    if kind == "glass":
        return ["glass"] * n
    out = [""] * n
    up_mask = fn[:, 1] > 0.70
    dn_mask = fn[:, 1] < -0.70
    horiz_mask = up_mask | dn_mask

    # 1. Floor_Slab: uniform category-filtered upward flooring + clean slab edge
    if kind == "floor":
        for gi in np.where(dn_mask | (~horiz_mask))[0]:
            out[int(gi)] = dom_floor_side_key
        up_by_y: dict[float, list[int]] = defaultdict(list)
        for gi in np.where(up_mask)[0]:
            up_by_y[round(float(fc[int(gi), 1]), 2)].append(int(gi))
        for y_lvl, idxs in up_by_y.items():
            if abs(y_lvl - floor_y) <= 0.06 or len(raw_up_pts) == 0:
                mkey = dom_floor_top_key
            else:
                cmask = np.isin(raw_up_cats, ("floor_tile", "stair_mat")) & (np.abs(raw_up_pts[:, 1] - y_lvl) <= 0.15)
                mkey = _area_vote_key(raw_up_keys, raw_up_areas, cmask, dom_floor_top_key)
            for gi in idxs:
                out[gi] = mkey
        return out

    # 2. Stairs / Stairs_Upper: uniform architectural quartz top/side materials (zero diagonal side splits)
    if kind in ("stairs", "stairs_upper"):
        for gi in range(n):
            out[gi] = dom_floor_top_key if up_mask[gi] else dom_floor_side_key
        return out

    # 3. Walls, Columns, Overhead: cutaway top caps + single material per planar wall face + uniform baseboard band
    if is_plinth or is_lower:
        cap_mask = (fn[:, 1] > 0.85) & (fc[:, 1] >= tier_top - 0.015)
        for gi in np.where(cap_mask)[0]:
            out[int(gi)] = "cut_cap"
    else:
        cap_mask = np.zeros(n, dtype=bool)

    for gi in np.where(horiz_mask & (~cap_mask))[0]:
        out[int(gi)] = dom_wall_key

    need_vert = np.where(~horiz_mask)[0]
    if len(need_vert) == 0:
        return out

    body_raw_mask = (
        ~np.isin(raw_vert_cats, ("baseboard", "floor_tile", "glass", "littletiles_trim"))
        & (raw_vert_pts[:, 1] > y_bb_cut + 0.05)
    ) if len(raw_vert_pts) > 0 else np.zeros(0, dtype=bool)

    plane_buckets: dict[tuple[float, float, float], list[int]] = defaultdict(list)
    for gi in need_vert:
        nx, nz = float(fn[gi, 0]), float(fn[gi, 2])
        nlen = math.hypot(nx, nz)
        if nlen > 1e-8:
            nx, nz = nx / nlen, nz / nlen
        plane_d = float(fc[gi, 0]) * nx + float(fc[gi, 2]) * nz
        pkey = (round(nx, 1), round(nz, 1), round(plane_d, 1))
        plane_buckets[pkey].append(int(gi))

    for idxs in plane_buckets.values():
        mean_n = fn[idxs][:, [0, 2]].mean(axis=0)
        nlen = float(np.linalg.norm(mean_n))
        face_n = (mean_n / nlen) if nlen > 1e-8 else np.array([1.0, 0.0], dtype=np.float64)
        face_t = np.array([-face_n[1], face_n[0]], dtype=np.float64)

        tri_pts = t_verts[t_faces[idxs]].reshape(-1, 3)
        tri_xz = tri_pts[:, [0, 2]]
        d_vals = tri_xz @ face_n
        t_vals = tri_xz @ face_t
        d_mid = float(d_vals.mean())
        t_min, t_max = float(t_vals.min()), float(t_vals.max())

        body_key = dom_wall_key
        if len(raw_vert_pts) > 0 and body_raw_mask.any():
            raw_xz = raw_vert_pts[:, [0, 2]]
            aligned = body_raw_mask & ((raw_vert_n_xz @ face_n) > 0.70)
            if aligned.any():
                raw_d = raw_xz @ face_n
                raw_t = raw_xz @ face_t
                for tol in (0.35, 0.75):
                    hit = aligned & (np.abs(raw_d - d_mid) <= tol) & (raw_t >= t_min - 0.25) & (raw_t <= t_max + 0.25)
                    if hit.any():
                        body_key = _area_vote_key(raw_vert_keys, raw_vert_areas, hit, dom_wall_key)
                        break

        keep_accent = key_to_cat.get(body_key) == "exterior_accent"
        for gi in idxs:
            if float(fc[gi, 1]) <= y_bb_cut + 0.002 and not keep_accent and dom_baseboard_key is not None:
                out[gi] = dom_baseboard_key
            else:
                out[gi] = body_key

    return out


def _box_projected_uvs(verts: np.ndarray, face_normal: np.ndarray, tile_m: float = 1.0) -> np.ndarray:
    nx, ny, nz = abs(float(face_normal[0])), abs(float(face_normal[1])), abs(float(face_normal[2]))
    if ny >= nx and ny >= nz:
        return np.column_stack([verts[:, 0] / tile_m, verts[:, 2] / tile_m])
    if nx >= ny and nx >= nz:
        return np.column_stack([verts[:, 2] / tile_m, verts[:, 1] / tile_m])
    return np.column_stack([verts[:, 0] / tile_m, verts[:, 1] / tile_m])


def _split_mesh_by_material_and_flat_uvs(
    tm: trimesh.Trimesh,
    face_keys: Sequence[str],
    mat_defs: dict[str, trimesh.visual.material.PBRMaterial],
) -> list[tuple[str, trimesh.Trimesh]]:
    """Split a guaranteed-watertight Trimesh into crisp flat-normal, box-UV primitives per material."""
    verts = tm.vertices
    faces = tm.faces
    p0, p1, p2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    cr = np.cross(p1 - p0, p2 - p0)
    fn = cr / np.maximum(np.linalg.norm(cr, axis=1, keepdims=True), 1e-12)

    buckets: dict[str, list[int]] = defaultdict(list)
    for fi in range(len(faces)):
        buckets[face_keys[fi]].append(fi)

    out: list[tuple[str, trimesh.Trimesh]] = []
    for mkey, fidx in buckets.items():
        new_verts: list[np.ndarray] = []
        new_uvs: list[np.ndarray] = []
        new_faces: list[tuple[int, int, int]] = []
        vert_map: dict[tuple[Any, ...], int] = {}

        for fi in fidx:
            nvec = fn[fi]
            nkey = (round(float(nvec[0]), 2), round(float(nvec[1]), 2), round(float(nvec[2]), 2))
            tri = faces[fi]
            tri_pts = verts[tri]
            tri_uvs = _box_projected_uvs(tri_pts, nvec, tile_m=1.0)
            out_tri = []
            for k in range(3):
                pt = tri_pts[k]
                uv = tri_uvs[k]
                key = (round(float(pt[0]), 5), round(float(pt[1]), 5), round(float(pt[2]), 5), nkey)
                vid = vert_map.get(key)
                if vid is None:
                    vid = len(new_verts)
                    new_verts.append(pt)
                    new_uvs.append(uv)
                    vert_map[key] = vid
                out_tri.append(vid)
            new_faces.append((out_tri[0], out_tri[1], out_tri[2]))

        pbr = mat_defs[mkey]
        vis = trimesh.visual.TextureVisuals(uv=np.asarray(new_uvs, dtype=np.float64), material=pbr)
        sub_tm = trimesh.Trimesh(
            vertices=np.asarray(new_verts, dtype=np.float64),
            faces=np.asarray(new_faces, dtype=np.int64),
            visual=vis,
            process=False,
        )
        out.append((mkey, sub_tm))
    return out


# --------------------------------------------------------------------------- Main Rebuild Orchestrator


def _apply_overrides_2d(
    S_base: Any,
    S_mid: Any,
    overrides_path: Path | None,
) -> tuple[Any, Any]:
    if overrides_path is None or not overrides_path.is_file():
        return S_base, S_mid
    data = json.loads(overrides_path.read_text(encoding="utf-8"))
    for box in data.get("remove_boxes", []):
        b = shapely_box(box["min_x"], box["min_z"], box["max_x"], box["max_z"])
        S_base = S_base.difference(b)
        S_mid = S_mid.difference(b)
    for w in data.get("add_walls", []):
        b = shapely_box(w["min_x"], w["min_z"], w["max_x"], w["max_z"])
        S_base = unary_union([S_base, b])
        if not w.get("low_only", False):
            S_mid = unary_union([S_mid, b])
    return _clean_shapely(S_base, 0.004), _clean_shapely(S_mid, 0.004)


def run_solid_rebuild(
    obj_path: Path,
    out_dir: Path,
    *,
    mtl_path: Path | None = None,
    textures_dir: Path | None = None,
    overrides_path: Path | None = None,
    low_cut_m: float = 1.25,
    plinth_m: float = 0.04,
    column_min_width_m: float = 0.56,
    export_glb: bool = True,
) -> RebuildReport:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = load_raw_floor_obj(obj_path, mtl_path=mtl_path)

    # Locate texture folder automatically if omitted
    if textures_dir is None:
        for cand in [
            obj_path.parent / "tex",
            obj_path.parent / "textures",
            obj_path.parent.parent / "textures",
            obj_path.parent.parent.parent / "textures",
            obj_path.parent.parent.parent.parent / "textures",
        ]:
            if cand.is_dir():
                textures_dir = cand
                break

    pos, fa, mats, fmats = raw.positions, raw.faces, raw.materials, raw.face_mats
    p0, p1, p2 = pos[fa[:, 0]], pos[fa[:, 1]], pos[fa[:, 2]]
    cr = np.cross(p1 - p0, p2 - p0)
    lens = np.linalg.norm(cr, axis=1)
    unit_n = cr / np.maximum(lens[:, None], 1e-12)
    yc = pos[fa].mean(axis=1)[:, 1]
    keep_struct = np.array([mats[m].category not in ("littletiles_trim", "glass") for m in fmats])
    # Wall/column cross-sections ONLY slice real wall materials (never swallow stairs/floors into phantom walls!)
    keep_wall = np.array([mats[m].category in ("structural", "baseboard", "exterior_accent") for m in fmats])
    wall_tm = trimesh.Trimesh(vertices=pos, faces=fa[keep_wall], process=False)

    # Cap footprint >= floor_y + 0.45m captures real 0.5-1.0m sill/parapet walls while excluding floor/stairs
    up_caps = [
        Polygon(pos[f][:, [0, 2]]).buffer(0)
        for f, ok in zip(fa, keep_wall & (unit_n[:, 1] > 0.85) & (yc >= raw.floor_y + 0.45))
        if ok
    ]
    any_cap = _clean_shapely(unary_union([p for p in up_caps if p.area > 1e-5]), 0.005)

    # 3 architectural elevation cross-sections
    S_40 = _extract_solid_slice(wall_tm, raw.floor_y + 0.40, any_cap)
    S_85 = _extract_solid_slice(wall_tm, raw.floor_y + 0.85, any_cap)
    S_base = _clean_shapely(S_40.intersection(S_85), 0.004)
    if S_base.is_empty:
        S_base = S_85

    h_mid = min(raw.ceil_y - raw.floor_y - 0.35, max(1.50, (raw.sill_y - raw.floor_y) + 0.25))
    S_mid = _extract_solid_slice(wall_tm, raw.floor_y + h_mid, any_cap)
    # Clip S_mid inside S_base envelope so zero upper overhangs leak into walls
    S_mid = _clean_shapely(S_mid.intersection(S_base.buffer(0.02, join_style=2)), 0.004)

    # Weld sub-9cm raw wall micro-slits & fill tiny <0.35m2 pinholes while keeping doorways (>=0.70m) intact
    S_base = _fill_small_holes(_clean_shapely(S_base, 0.045), 0.35)
    S_mid = _fill_small_holes(_clean_shapely(S_mid, 0.045).intersection(S_base), 0.35)
    S_base, S_mid = _apply_overrides_2d(S_base, S_mid, overrides_path)

    floor_fp, stair_steps = _extract_floor_and_stairs(raw, S_base, S_mid)
    stair_zone = (
        _clean_shapely(unary_union([p for _, _, p in stair_steps]), 0.05)
        if stair_steps
        else Polygon()
    )

    # High band clipped closely to S_base + doorway/window lintel bridges (exclude walls AND stair zones)
    S_high_raw = _extract_solid_slice(wall_tm, min(raw.ceil_y - 0.30, raw.lintel_y + 0.35), any_cap)
    # Keep header bridges inside narrow wall corridor envelope (exclude roofs > 1.8m from walls)
    S_high = _clean_shapely(S_high_raw.intersection(S_base.buffer(1.45, join_style=2)), 0.005)
    # Subtract standing walls AND stairwells so upper stair treads never turn into floating ceiling beams
    lintel_excl = S_base.buffer(0.02, join_style=2)
    if not stair_zone.is_empty:
        lintel_excl = unary_union([lintel_excl, stair_zone.buffer(0.95, join_style=2)])
    lintel_only = _clean_shapely(S_high.difference(lintel_excl), 0.005)
    lintel_kept = unary_union(
        [p for p in _iter_polygons(lintel_only) if p.area <= 8.0 and min(p.bounds[2] - p.bounds[0], p.bounds[3] - p.bounds[1]) <= 2.2]
    )
    S_high_wall = _clean_shapely(unary_union([S_base.intersection(S_high_raw), lintel_kept]), 0.004)
    columns, wall_groups = _separate_columns_and_split_walls(
        S_base, S_mid, floor_fp, column_min_width_m=column_min_width_m
    )

    # ------------------------------------------------- Watertight Manifold Assembly
    solid_nodes: list[tuple[str, str, trimesh.Trimesh]] = []  # (node_name, semantic_kind, watertight_trimesh)

    # 1. Floor_Slab (+ raised steps extruded via mapbox_earcut cleanly with 0 zero-area tris)
    floor_fp_s = _clean_shapely(
        unary_union([p.simplify(0.015, preserve_topology=True) for p in _iter_polygons(floor_fp) if not p.is_empty]),
        0.005,
    )
    floor_fp_s = _clean_shapely(
        floor_fp_s.buffer(0.015, join_style=2).buffer(-0.012, join_style=2),
        0.0,
    )
    slab_tms: list[trimesh.Trimesh] = []
    for fp_poly in _iter_polygons(floor_fp_s):
        st = _extrude_polygon_earcut_yup(fp_poly, raw.slab_bottom_y, raw.floor_y)
        if st is not None:
            slab_tms.append(st)
        # Seal stairwell shaft bottom pits so zero empty canvas void shows beneath descending stairs
        for h in fp_poly.interiors:
            hole_poly = Polygon(h).buffer(-0.002, join_style=2)
            for hp in _iter_polygons(hole_poly):
                if hp.area >= 0.15:
                    pit = _extrude_polygon_earcut_yup(hp, raw.slab_bottom_y - 0.12, raw.slab_bottom_y - 0.002)
                    if pit is not None:
                        slab_tms.append(pit)
    for ry, rp in raw.raised_levels:
        rp_clean = _clean_shapely(
            unary_union([_regularize_polygon(p, 0.01).simplify(0.015, preserve_topology=True) for p in _iter_polygons(rp) if not p.is_empty]).intersection(
                floor_fp_s.buffer(-0.005, join_style=2)
            ),
            0.005,
        )
        for rp_poly in _iter_polygons(rp_clean):
            rt = _extrude_polygon_earcut_yup(rp_poly, raw.floor_y, ry)
            if rt is not None:
                slab_tms.append(rt)
    if slab_tms:
        comb_slab = trimesh.util.concatenate(slab_tms) if len(slab_tms) > 1 else slab_tms[0]
        solid_nodes.append(("Floor_Slab", "floor", comb_slab))

    # Align cutaway cleanly to sill_y (above baseboard) so __Lower stays flat without sill pockets
    y_cut = min(raw.floor_y + low_cut_m, max(raw.floor_y + 0.95, raw.sill_y))

    # 2. Stairs: 100% watertight true-3D manifold stepped slabs (switchback-safe, 0 open edges, 0 spikes)
    if stair_steps:
        y_stair_split = y_cut + 0.25
        desc_union = unary_union([sp for _, yr, sp in stair_steps if yr < raw.floor_y - 0.04])
        lo_by_span: dict[tuple[float, float], list[Any]] = defaultdict(list)
        hi_by_span: dict[tuple[float, float], list[Any]] = defaultdict(list)

        for _, yr, sp in stair_steps:
            sp_r = _clean_shapely(_regularize_polygon(sp, 0.01), 0.008)
            if sp_r.is_empty:
                continue
            y_top = round(float(yr), 3)
            if y_top < raw.floor_y - 0.04:
                y_bot = round(float(raw.slab_bottom_y), 3)
                lo_by_span[(y_bot, y_top)].append(sp_r)
            else:
                if y_top <= raw.floor_y + 1.05 and (desc_union.is_empty or not desc_union.intersects(sp_r)):
                    y_bot = round(float(raw.floor_y), 3)
                else:
                    y_bot = round(max(float(raw.floor_y) if y_top > raw.floor_y + 0.08 else float(raw.slab_bottom_y), y_top - 0.28), 3)
                if y_top <= y_stair_split:
                    lo_by_span[(y_bot, y_top)].append(sp_r)
                else:
                    hi_by_span[(y_bot, y_top)].append(sp_r)

        def _fuse_stair_tier(span_map: dict[tuple[float, float], list[Any]]) -> trimesh.Trimesh | None:
            parts: list[m3d.Manifold] = []
            for (yb, yt), plist in sorted(span_map.items()):
                if yt - yb < 0.02:
                    continue
                u = _clean_shapely(unary_union(plist), 0.008)
                for p_s in _iter_polygons(u):
                    m_st = geom_to_manifold(p_s, yb, yt)
                    if m_st is not None:
                        parts.append(m_st)
            if not parts:
                return None
            fused = m3d.Manifold.batch_boolean(parts, m3d.OpType.Add) if len(parts) > 1 else parts[0]
            return manifold_to_trimesh(fused)

        if (tm_lo_st := _fuse_stair_tier(lo_by_span)) is not None:
            solid_nodes.append(("Stairs", "stairs", tm_lo_st))
        if (tm_hi_st := _fuse_stair_tier(hi_by_span)) is not None:
            solid_nodes.append(("Stairs_Upper", "stairs_upper", tm_hi_st))

    # 3. Tiered Solid Prisms (__Plinth, __Lower, __Upper) for every Column & Wall
    y_plinth_top = raw.floor_y + plinth_m

    y_bb_cut = raw.floor_y + raw.baseboard_h

    def _add_tiered_solid(gname: str, kind: str, p_base: Any, p_mid: Any) -> None:
        # __Plinth: flush 4 cm solid footprint trace
        if (m_plinth := geom_to_manifold(p_base, raw.floor_y, y_plinth_top)) is not None:
            solid_nodes.append((f"{gname}__Plinth", kind, manifold_to_trimesh(m_plinth)))

        # __Lower: [y_plinth_top .. y_cut] uniform solid wall base (zero recessed railing/sill pockets)
        if (m_lo := geom_to_manifold(p_base, y_plinth_top, y_cut)) is not None:
            solid_nodes.append((f"{gname}__Lower", kind, _slice_trimesh_at_y(manifold_to_trimesh(m_lo), y_bb_cut)))

        # __Upper: [y_cut .. ceil_y] respecting window openings & wall headers
        m_hi1 = geom_to_manifold(p_mid, y_cut, min(raw.lintel_y, raw.ceil_y))
        up_top = _clean_shapely(unary_union([p_base, p_mid]).intersection(S_high_wall.buffer(0.02, join_style=2)), 0.002)
        up_top_eff = up_top if not up_top.is_empty else p_base
        if p_mid.is_empty is False and p_mid.symmetric_difference(up_top_eff).area < 1e-3:
            if (m_hi := geom_to_manifold(p_mid, y_cut, raw.ceil_y)) is not None:
                solid_nodes.append((f"{gname}__Upper", kind, manifold_to_trimesh(m_hi)))
        else:
            m_hi2 = geom_to_manifold(up_top_eff, raw.lintel_y, raw.ceil_y)
            parts_hi = [m for m in (m_hi1, m_hi2) if m is not None]
            if parts_hi:
                m_hi = m3d.Manifold.batch_boolean(parts_hi, m3d.OpType.Add) if len(parts_hi) > 1 else parts_hi[0]
                solid_nodes.append((f"{gname}__Upper", kind, manifold_to_trimesh(m_hi)))

    for cname, cpoly in columns:
        _add_tiered_solid(cname, "column", cpoly, _align_mid_to_base(cpoly, S_mid))

    for wname, wkind, w_base, w_mid in wall_groups:
        _add_tiered_solid(wname, wkind, w_base, w_mid)

    # 4. Glass_Openings: thin solid panes inside real window openings verified by raw glass triangles
    gl_mask = np.array([mats[m].category == "glass" for m in fmats])
    if gl_mask.any():
        gl_pts_xz = pos[fa[gl_mask]].mean(axis=1)[:, [0, 2]]
        win_gaps = _clean_shapely(S_base.difference(S_mid), 0.002)
        glass_parts: list[m3d.Manifold] = []
        for gp in _iter_polygons(win_gaps):
            if gp.area < 0.05:
                continue
            dists = np.linalg.norm(gl_pts_xz - np.array([gp.centroid.x, gp.centroid.y]), axis=1)
            if float(dists.min()) <= 0.85:
                # Slim down to 0.05m center pane along thin axis
                thin_pane = gp.buffer(-min(0.10, max(0.02, gp.area / max(gp.length, 0.5) * 0.45)), join_style=2)
                pane_2d = thin_pane if not thin_pane.is_empty else gp
                gm = geom_to_manifold(pane_2d, max(raw.sill_y, y_cut), min(raw.lintel_y, raw.ceil_y - 0.1))
                if gm is not None:
                    glass_parts.append(gm)
        if glass_parts:
            g_man = m3d.Manifold.batch_boolean(glass_parts, m3d.OpType.Add) if len(glass_parts) > 1 else glass_parts[0]
            solid_nodes.append(("Glass_Openings", "glass", manifold_to_trimesh(g_man)))

    # 5. OverheadBeams_And_Lintels: solid header lintels above doors/windows
    if not lintel_kept.is_empty:
        ov_man = geom_to_manifold(lintel_kept, raw.lintel_y, raw.ceil_y)
        if ov_man is not None:
            solid_nodes.append(("OverheadBeams_And_Lintels", "overhead", manifold_to_trimesh(ov_man)))

    # ------------------------------------------------- Hard Watertight Audit BEFORE Export
    audit_nodes: list[dict[str, Any]] = []
    passed = True
    for nname, nkind, tm in solid_nodes:
        edges = tm.edges_sorted
        unique_e, counts_e = np.unique(edges, axis=0, return_counts=True)
        open_e = int((counts_e == 1).sum())
        nonman_e = int((counts_e > 2).sum())
        vol = float(tm.volume)
        p_t = tm.vertices[tm.faces]
        elens = np.stack([
            np.linalg.norm(p_t[:, 1] - p_t[:, 0], axis=1),
            np.linalg.norm(p_t[:, 2] - p_t[:, 1], axis=1),
            np.linalg.norm(p_t[:, 0] - p_t[:, 2], axis=1),
        ], axis=1)
        areas_t = 0.5 * np.linalg.norm(np.cross(p_t[:, 1] - p_t[:, 0], p_t[:, 2] - p_t[:, 0]), axis=1)
        zero_tris = int((areas_t <= 1e-10).sum())
        max_e = np.maximum(elens.max(axis=1), 1e-9)
        min_alt_mm = float((2.0 * areas_t / max_e).min() * 1000.0) if len(areas_t) else 0.0
        ok = (open_e == 0) and (nonman_e == 0) and (vol > 0.0) and (zero_tris == 0) and (min_alt_mm >= 1.0)
        if not ok:
            passed = False
        audit_nodes.append({
            "node": nname,
            "kind": nkind,
            "tris": int(len(tm.faces)),
            "open_edges": open_e,
            "nonmanifold_edges": nonman_e,
            "signed_volume": round(vol, 5),
            "zero_area": zero_tris,
            "min_altitude_mm": round(min_alt_mm, 2),
            "watertight": bool(tm.is_watertight),
            "passed": ok,
        })

    # Check zero unintended narrow gaps (0.5mm .. 12cm) between wall/column pieces
    piece_list: list[tuple[str, Polygon]] = [(cname, cpoly) for cname, cpoly in columns] + [
        (wname, w_base) for wname, _, w_base, _ in wall_groups
    ]
    narrow_gap_pairs: list[dict[str, Any]] = []
    for i in range(len(piece_list)):
        na, pa = piece_list[i]
        for j in range(i + 1, len(piece_list)):
            nb, pb = piece_list[j]
            d = float(pa.distance(pb))
            if 0.0005 < d < 0.12:
                narrow_gap_pairs.append({"a": na, "b": nb, "gap_m": round(d, 4)})
    if narrow_gap_pairs:
        passed = False
    # ------------------------------------------------- Material Setup & GLB/OBJ Export
    mat_defs, raw_to_key, key_to_cat = _build_raw_pbr_palette(raw, textures_dir)
    raw_fc = pos[fa].mean(axis=1)
    raw_areas = 0.5 * lens
    valid_raw_idx = np.where(keep_struct & np.array([m in raw_to_key for m in fmats]))[0]
    raw_up_idx = valid_raw_idx[unit_n[valid_raw_idx, 1] > 0.70]
    raw_vert_idx = valid_raw_idx[np.abs(unit_n[valid_raw_idx, 1]) <= 0.70]

    raw_up_pts = raw_fc[raw_up_idx]
    raw_up_keys = [raw_to_key[fmats[i]] for i in raw_up_idx]
    raw_up_cats = np.asarray([key_to_cat[k] for k in raw_up_keys], dtype=object)
    raw_up_areas = raw_areas[raw_up_idx]

    raw_vert_pts = raw_fc[raw_vert_idx]
    rn_xz = unit_n[raw_vert_idx][:, [0, 2]] if len(raw_vert_idx) > 0 else np.zeros((0, 2), dtype=np.float64)
    rn_len = np.maximum(np.linalg.norm(rn_xz, axis=1, keepdims=True), 1e-12) if len(raw_vert_idx) > 0 else np.zeros((0, 1), dtype=np.float64)
    raw_vert_n_xz = rn_xz / rn_len
    raw_vert_keys = [raw_to_key[fmats[i]] for i in raw_vert_idx]
    raw_vert_cats = np.asarray([key_to_cat[k] for k in raw_vert_keys], dtype=object)
    raw_vert_areas = raw_areas[raw_vert_idx]

    # Compute area-weighted per-floor dominant category keys
    up_floor_band = np.abs(raw_up_pts[:, 1] - raw.floor_y) <= 0.15 if len(raw_up_pts) > 0 else np.zeros(0, dtype=bool)
    dom_floor_top_key = _area_vote_key(
        raw_up_keys,
        raw_up_areas,
        up_floor_band & (raw_up_cats == "floor_tile"),
        _area_vote_key(
            raw_up_keys,
            raw_up_areas,
            up_floor_band & ~np.isin(raw_up_cats, ("baseboard", "glass")),
            "fallback_floor",
        ),
    )

    slab_edge_band = (
        (raw_vert_pts[:, 1] >= raw.slab_bottom_y - 0.10) & (raw_vert_pts[:, 1] <= raw.floor_y + 0.10)
    ) if len(raw_vert_pts) > 0 else np.zeros(0, dtype=bool)
    slab_side_pref = np.array([("quartz_block_side" in k.lower()) or (key_to_cat[k] == "stair_mat") for k in raw_vert_keys], dtype=bool)
    dom_floor_side_key = _area_vote_key(
        raw_vert_keys,
        raw_vert_areas,
        slab_edge_band & slab_side_pref,
        dom_floor_top_key,
    )

    dom_baseboard_key: str | None = None
    if len(raw_vert_pts) > 0 and (raw_vert_cats == "baseboard").any():
        dom_baseboard_key = _area_vote_key(raw_vert_keys, raw_vert_areas, raw_vert_cats == "baseboard", "fallback_wall")

    wall_body_band = (raw_vert_pts[:, 1] > y_bb_cut + 0.05) if len(raw_vert_pts) > 0 else np.zeros(0, dtype=bool)
    dom_wall_key = _area_vote_key(
        raw_vert_keys,
        raw_vert_areas,
        wall_body_band & (raw_vert_cats == "structural"),
        "fallback_wall",
    )

    scene = trimesh.Scene()
    obj_lines = [f"# Solid Architectural Rebuild ({raw.source_frame})", f"mtllib materials.mtl"]
    v_offset = 1
    group_list: list[dict[str, Any]] = []

    for nname, kind, tm in solid_nodes:
        is_plinth = nname.endswith("__Plinth")
        is_lower = nname.endswith("__Lower")
        tier_top = float(tm.vertices[:, 1].max())
        t_verts, t_faces = tm.vertices, tm.faces
        tp0, tp1, tp2 = t_verts[t_faces[:, 0]], t_verts[t_faces[:, 1]], t_verts[t_faces[:, 2]]
        t_cr = np.cross(tp1 - tp0, tp2 - tp0)
        t_fn = t_cr / np.maximum(np.linalg.norm(t_cr, axis=1, keepdims=True), 1e-12)
        t_fc = (tp0 + tp1 + tp2) / 3.0
        face_keys = _assign_clean_raw_materials(
            t_verts,
            t_faces,
            t_fc,
            t_fn,
            raw_up_pts,
            raw_up_keys,
            raw_up_cats,
            raw_up_areas,
            raw_vert_pts,
            raw_vert_n_xz,
            raw_vert_keys,
            raw_vert_cats,
            raw_vert_areas,
            key_to_cat,
            dom_floor_top_key,
            dom_floor_side_key,
            dom_baseboard_key,
            dom_wall_key,
            raw.floor_y,
            y_bb_cut,
            kind,
            is_plinth,
            is_lower,
            tier_top,
        )

        prims = _split_mesh_by_material_and_flat_uvs(tm, face_keys, mat_defs)
        single = len(prims) == 1
        for mkey, sub_tm in prims:
            geom_name = nname if single else f"{nname}__{mkey}"
            if single:
                scene.add_geometry(sub_tm, node_name=nname, geom_name=geom_name)
            else:
                if nname not in scene.graph.nodes:
                    scene.graph.update(frame_to=nname, frame_from=scene.graph.base_frame)
                scene.add_geometry(sub_tm, node_name=geom_name, geom_name=geom_name, parent_node_name=nname)

        # Append watertight mesh to combined grouped Unity OBJ
        obj_lines.append(f"g {nname}")
        for vx, vy, vz in tm.vertices:
            obj_lines.append(f"v {vx:.6f} {vy:.6f} {vz:.6f}")
        for i0, i1, i2 in tm.faces:
            obj_lines.append(f"f {v_offset + i0} {v_offset + i1} {v_offset + i2}")
        v_offset += len(tm.vertices)
        group_list.append({"node": nname, "kind": kind, "tris": int(len(tm.faces))})

    stem = obj_path.stem
    out_obj = out_dir / f"{stem}.solid_rebuild.unity.obj"
    out_obj.write_text("\n".join(obj_lines) + "\n", encoding="utf-8")

    out_glb: Path | None = None
    if export_glb:
        out_glb = out_dir / f"{stem}.solid_rebuild.glb"
        out_glb.write_bytes(scene.export(file_type="glb"))

    manifest = {
        "schema": "uc_solid_rebuild_v2",
        "source_obj": str(obj_path),
        "source_frame": raw.source_frame,
        "elevations_m": {
            "slab_bottom_y": raw.slab_bottom_y,
            "floor_y": raw.floor_y,
            "baseboard_h": round(raw.baseboard_h, 3),
            "sill_y": round(raw.sill_y, 3),
            "lintel_y": round(raw.lintel_y, 3),
            "ceil_y": raw.ceil_y,
            "low_cut_m": low_cut_m,
            "plinth_m": plinth_m,
        },
        "counts": {
            "columns": len(columns),
            "wall_groups": len(wall_groups),
            "stair_steps": len(stair_steps),
            "total_nodes": len(solid_nodes),
            "total_tris": sum(len(t.faces) for _, _, t in solid_nodes),
        },
        "groups": group_list,
    }
    audit = {
        "passed": passed,
        "all_watertight": all(n["watertight"] for n in audit_nodes),
        "total_open_edges": sum(n["open_edges"] for n in audit_nodes),
        "total_nonmanifold_edges": sum(n["nonmanifold_edges"] for n in audit_nodes),
        "narrow_wall_gaps": len(narrow_gap_pairs),
        "narrow_wall_gap_pairs": narrow_gap_pairs,
        "negative_volume_nodes": [n["node"] for n in audit_nodes if n["signed_volume"] <= 0.0],
        "nodes": audit_nodes,
    }
    (out_dir / "rebuild_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out_dir / "watertight_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return RebuildReport(out_dir=out_dir, glb_path=out_glb, obj_path=out_obj, manifest=manifest, audit=audit, passed=passed)
