"""Rebuild every flat region as the fewest triangles over its EXISTING vertices.

A SketchUp export cuts each flat surface into hundreds of small coplanar triangles ("gridlines").
This kernel unions each planar region inside its own plane, drops the border vertices that no
region needs as a corner, and re-triangulates what is left, so only real shape edges survive.

Positions are never moved, never appended to and never re-indexed: every output face indexes a
position that was already in `mesh.positions`. `vt` and `vn` rows are attributes, not geometry, so
new ones may be appended.

A polygon with `n` ring vertices and `h` holes triangulates into exactly `n + 2h - 2` triangles,
so the triangle count is decided by how many ring vertices survive the global corner pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

import numpy as np
import shapely

from engine.model import MeshData
from engine.pipeline import Topology
from engine.topo.edges import EDGE_NONMANIFOLD, EDGE_OPEN, EDGE_TJUNCTION
from engine.topo.planes import cluster_uv, plane_basis

#: Precision grid the 2D union snaps to (inches, in the region's LOCAL frame).
GRID_SIZE = 1e-4
#: A union ring coordinate must land this close to an existing vertex to be accepted (inches).
SNAP_TOL = 1e-3
#: A ring vertex further than this from the chord of its ring neighbours is a corner (inches).
COLLINEAR_TOL = 1e-3
#: Most times pass 2 reruns after a feedback event (see `merge_regions`).
MAX_ROUNDS = 10
#: A triangle overlapping another of its own region by more than `_OVERLAP_ABS + _OVERLAP_REL *
#: its own area` is excluded from the merge and copied through.
_OVERLAP_ABS = 1e-9
_OVERLAP_REL = 1e-6
#: Relative slack on the per-region area checks (rules 6 and 9).
_AREA_REL_TOL = 1e-6
#: Nearest-vertex search block size, in coordinate x vertex pairs.
_SEARCH_BLOCK = 4_000_000

_SKIP_REASONS = ("overlap", "new_vertex", "invalid_polygon", "area_grew")


@dataclass
class MergeResult:
    """`mesh` with every mergeable region re-triangulated; `source_faces[i]` is the array of
    ORIGINAL face indices new face `i` came from (its whole region when merged, a single face when
    copied through); `report` is the counts described in `merge_regions`.

    `rings[i]`, when present, is the ordered outer ring of vertex ids (int64, indexing
    `mesh.positions` exactly like `mesh.face_v` does, CCW as seen from the region's own outward
    side) of the HOLE-FREE merged region output row `i` belongs to. Every row of the SAME region
    maps to the IDENTICAL ring array object (not just equal content), so a writer that wants one
    polygon face per region can dedup by `id()` -- see `engine.io.obj_writer.write_obj_polygons`.
    A region with a hole, more than one disjoint piece, or fewer than 3 kept ring vertices has NO
    entry here (every one of its rows is written as an ordinary triangle instead); rows that were
    copied through unmerged never have an entry either."""
    mesh: MeshData
    source_faces: list[np.ndarray]
    report: dict
    rings: dict[int, np.ndarray] = field(default_factory=dict)


@dataclass
class _Piece:
    """One polygon of a region's union: its rings as welded vertex ids plus the union's own
    area/perimeter, which the rebuilt polygon is checked against."""
    rings: list[np.ndarray]
    union_area: float
    union_perimeter: float


@dataclass
class _Plan:
    """Everything pass 2 needs about one mergeable region, decided before the global corner pass."""
    region: int
    members: np.ndarray
    vertex_ids: np.ndarray
    vertex_xy: np.ndarray
    normal: np.ndarray
    pieces: list[_Piece]
    original_area: float


def merge_regions(mesh: MeshData, topo: Topology, flat_materials: Iterable[int] = frozenset(),
                  grid_size: float = GRID_SIZE, snap_tol: float = SNAP_TOL,
                  collinear_tol: float = COLLINEAR_TOL) -> MergeResult:
    """Re-triangulate every region of `topo.face_region` over its existing vertices.

    Regions are visited in ascending region id and every ordering inside the kernel is by index or
    sorted, so two runs on the same input produce bit-identical arrays.

    A region can only fail rules 6, 7 and 9 AFTER the global corner pass has already run, and it
    is then copied through with ALL of its vertices while its neighbours have already dropped the
    border vertices they shared with it -- exactly the T-junction the corner pass exists to
    prevent. A `keep_all` SUCCESS (rule 6's fallback, `_triangulate`) does the same damage for the
    same reason: the region is accepted holding every one of its ring vertices, which its
    neighbours may already have dropped.

    So pass 2 is a FIXED-POINT loop over both kinds of feedback event: a late-skipped region's
    vertices and a `keep_all` region's RING vertices join the `needed` set, and ring simplification
    + triangulation rerun for EVERY region, until a round turns up no event that earlier rounds had
    not already fed back. `needed` only ever grows, so the loop terminates; a region that fed back
    and then succeeded keeps its vertices needed, which costs triangles but can never open a
    T-junction.

    `report["converged"]` is True only when a round turned up nothing new -- the loop ended by
    agreement. `MAX_ROUNDS` is a backstop, not the mechanism: ending on it leaves the last round's
    feedback unfed, so a neighbour may still be holding a T-junction open, and `converged` is
    False. `report["merge_rounds"]` says how many rounds ran either way.

    `report` keys: `regions_merged`, `regions_skipped` (reason -> count, only non-zero reasons,
    from `overlap` / `new_vertex` / `invalid_polygon` / `area_grew`), `tris_before`, `tris_after`,
    `vertices_dropped` (welded vertices used by an input face and by no output face),
    `max_area_rel_error`, `faces_copied`, `merge_rounds`, `keep_all_regions` (how many regions took
    the `keep_all` fallback in any round of the loop) and `converged`.
    """
    flat = _validated_materials(flat_materials)
    welded_to_original = _welded_to_original(mesh, topo)

    plans, copied, skipped = _plan_regions(topo, grid_size, snap_tol)

    fed_back: dict[int, str] = {}
    kept_whole: set[int] = set()
    rounds = 0
    while True:
        rounds += 1
        needed = _needed_vertices(topo, copied + _late_faces(plans, fed_back), plans, collinear_tol,
                                  kept_whole)
        builds, late, keep_all, max_area_rel_error = _build_regions(plans, needed, collinear_tol)
        converged = set(late) <= set(fed_back) and set(keep_all) <= kept_whole
        if converged or rounds >= MAX_ROUNDS:
            break
        fed_back.update(late)
        kept_whole.update(keep_all)

    for plan in plans:
        if plan.region in late:
            skipped[late[plan.region]] += 1
            copied.extend(int(f) for f in plan.members)

    keep_all_set = frozenset(kept_whole | set(keep_all))
    region_rings: dict[int, np.ndarray] = {}
    for plan, _tris in builds:
        ring = _region_ring(plan, needed, keep_all_set, welded_to_original)
        if ring is not None:
            region_rings[plan.region] = ring

    out = _assemble(mesh, topo, welded_to_original, builds, copied, flat, region_rings)
    used_before = np.zeros(len(topo.positions_w), bool)
    used_before[topo.face_w.reshape(-1)] = True
    used_after = np.zeros(len(topo.positions_w), bool)
    used_after[_welded_of(mesh, topo, out.mesh)] = True
    out.report.update({
        "regions_merged": len(builds),
        "regions_skipped": {r: skipped[r] for r in _SKIP_REASONS if skipped[r]},
        "tris_before": int(mesh.n_faces),
        "tris_after": int(out.mesh.n_faces),
        "vertices_dropped": int((used_before & ~used_after).sum()),
        "max_area_rel_error": float(max_area_rel_error),
        "merge_rounds": int(rounds),
        "keep_all_regions": len(kept_whole | set(keep_all)),
        "converged": bool(converged),
    })
    return out


# --------------------------------------------------------------------------- pass 1: plan regions


def _plan_regions(topo: Topology, grid_size: float,
                  snap_tol: float) -> tuple[list[_Plan], list[int], dict]:
    """Project, overlap-filter and union every region; returns the plans for the mergeable ones,
    the original indices of every face copied through, and the skip reason counts so far."""
    plans: list[_Plan] = []
    copied: list[int] = []
    skipped = {r: 0 for r in _SKIP_REASONS}

    region_ids = np.unique(topo.face_region[topo.face_region >= 0])
    copied.extend(int(f) for f in np.nonzero(topo.face_region < 0)[0])
    for region in region_ids:
        members = np.nonzero(topo.face_region == region)[0]
        if len(members) < 2:
            copied.extend(int(f) for f in members)
            continue

        frame = _region_frame(topo.positions_w, topo.face_w, members)
        if frame is None:
            copied.extend(int(f) for f in members)
            skipped["invalid_polygon"] += 1
            continue
        normal, origin, basis = frame
        vertex_ids = np.unique(topo.face_w[members])
        vertex_xy = (topo.positions_w[vertex_ids] - origin) @ basis
        tri_xy = vertex_xy[np.searchsorted(vertex_ids, topo.face_w[members])]

        polys = shapely.polygons(np.concatenate([tri_xy, tri_xy[:, :1]], axis=1))
        areas = shapely.area(polys)
        excluded = _overlap_excluded(polys, areas)
        copied.extend(int(f) for f in members[excluded])
        keep = ~excluded
        if not keep.any():
            skipped["overlap"] += 1
            continue

        union = _union(polys[keep], grid_size)
        pieces = _pieces(union, vertex_xy, vertex_ids, snap_tol)
        if pieces is None:
            copied.extend(int(f) for f in members[keep])
            skipped["new_vertex"] += 1
            continue
        if not pieces:
            copied.extend(int(f) for f in members[keep])
            skipped["invalid_polygon"] += 1
            continue

        plans.append(_Plan(region=int(region), members=members[keep], vertex_ids=vertex_ids,
                           vertex_xy=vertex_xy, normal=normal, pieces=pieces,
                           original_area=float(areas[keep].sum())))
    return plans, copied, skipped


def _region_frame(positions_w: np.ndarray, face_w: np.ndarray, members: np.ndarray):
    """Area-weighted region normal, a local origin on the region, and the `(3, 2)` projection
    basis. Local, because the real model sits near 24,000 inches and the union runs on a 1e-4 grid."""
    tri = positions_w[face_w[members]]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]).sum(axis=0)
    length = float(np.linalg.norm(cross))
    if length == 0.0:
        return None
    normal = cross / length
    e1, e2 = plane_basis(normal)
    return normal, positions_w[face_w[members[0], 0]], np.stack([e1, e2], axis=1)


def _overlap_excluded(polys: np.ndarray, areas: np.ndarray) -> np.ndarray:
    """Per TRIANGLE, never per plane: a triangle overlapping another of its own region by more than
    `_OVERLAP_ABS + _OVERLAP_REL * its own area` is excluded. Flagging a whole plane because of one
    0.5 sq-inch overlap froze a 682-triangle plane in the spike."""
    excluded = np.zeros(len(polys), bool)
    if len(polys) < 2:
        return excluded
    left, right = shapely.STRtree(polys).query(polys, predicate="intersects")
    pair = left < right
    left, right = left[pair], right[pair]
    if not len(left):
        return excluded
    shared = shapely.area(shapely.intersection(polys[left], polys[right]))
    excluded[left[shared > _OVERLAP_ABS + _OVERLAP_REL * areas[left]]] = True
    excluded[right[shared > _OVERLAP_ABS + _OVERLAP_REL * areas[right]]] = True
    return excluded


def _union(polys: np.ndarray, grid_size: float):
    try:
        return shapely.union_all(polys, grid_size=grid_size)
    except shapely.errors.GEOSException:
        try:
            return shapely.union_all(polys)
        except shapely.errors.GEOSException:
            return None


def _pieces(union, vertex_xy: np.ndarray, vertex_ids: np.ndarray, snap_tol: float):
    """Rings of every polygon of `union`, as welded vertex ids. `None` when any ring coordinate
    fails to land within `snap_tol` of an existing vertex -- the union invented a vertex, which
    in the spike happened up to 94 inches away where slightly overlapping triangles crossed."""
    out: list[_Piece] = []
    for poly in _polygons(union):
        rings = []
        for ring in [poly.exterior, *poly.interiors]:
            ids = _nearest_ids(np.asarray(ring.coords)[:-1], vertex_xy, vertex_ids, snap_tol)
            if ids is None:
                return None
            rings.append(_dedup_cycle(ids))
        out.append(_Piece(rings=rings, union_area=float(poly.area),
                          union_perimeter=float(poly.length)))
    return out


def _polygons(geom) -> list:
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon" and not g.is_empty]


def _nearest_ids(coords: np.ndarray, vertex_xy: np.ndarray, vertex_ids: np.ndarray,
                 snap_tol: float):
    if not len(coords):
        return None
    step = max(1, _SEARCH_BLOCK // max(len(vertex_xy), 1))
    picked = np.empty(len(coords), np.int64)
    for start in range(0, len(coords), step):
        block = coords[start:start + step]
        distance = np.linalg.norm(block[:, None, :] - vertex_xy[None, :, :], axis=2)
        nearest = distance.argmin(axis=1)
        if distance[np.arange(len(nearest)), nearest].max() > snap_tol:
            return None
        picked[start:start + step] = nearest
    return vertex_ids[picked]


def _dedup_cycle(ids: np.ndarray) -> np.ndarray:
    keep = [int(ids[0])]
    for v in ids[1:]:
        if int(v) != keep[-1]:
            keep.append(int(v))
    if len(keep) > 1 and keep[0] == keep[-1]:
        keep.pop()
    return np.array(keep, np.int64)


# ------------------------------------------------------------------- the global corner pass (5)


def _needed_vertices(topo: Topology, copied: list[int], plans: list[_Plan],
                     collinear_tol: float, kept_whole: Iterable[int] = ()) -> np.ndarray:
    """`needed` decides RING membership: a welded vertex is needed when it is a corner in ANY ring,
    or is used by any non-degenerate face copied through, or lies ON (strictly between the
    endpoints of) an edge classed OPEN, NONMANIFOLD or TJUNCTION, or is ANY ring vertex of a
    region in `kept_whole` (one fed back by a `keep_all` success, which keeps its whole ring, so
    every neighbour has to keep the border vertices it shares with it). Deciding it globally is
    what keeps both sides of a shared border identical, so no new T-junction can appear.

    "Lies on" is the interior of the edge, not its endpoints: a 10x10 `grid_slab` has 40 boundary
    vertices that are endpoints of OPEN edges, and pinning those would give 38 triangles instead of
    the 2 the spec requires.

    Nothing is ever pinned in a region's INTERIOR. A wall standing on the interior of a slab needs
    no shared vertex: the slab surface is continuous beneath it, perpendicular contact cannot open
    a crack, and an interior vertex would make the region impossible to export as one polygon
    later. A vertex a merged region needs is a vertex on its border."""
    needed = np.zeros(len(topo.positions_w), bool)
    for face in copied:
        if topo.ok[face]:
            needed[topo.face_w[face]] = True
    pinning = (EDGE_OPEN, EDGE_NONMANIFOLD, EDGE_TJUNCTION)
    for edge, on_edge in topo.t_vertices.items():
        if topo.edge_class[edge] in pinning:
            needed[on_edge] = True
    kept_whole = frozenset(int(r) for r in kept_whole)
    for plan in plans:
        whole = plan.region in kept_whole
        for piece in plan.pieces:
            for ring in piece.rings:
                if whole or len(ring) < 3:
                    needed[ring] = True
                    continue
                xy = plan.vertex_xy[np.searchsorted(plan.vertex_ids, ring)]
                needed[ring[_corner_mask(xy, collinear_tol)]] = True
    return needed


def _corner_mask(xy: np.ndarray, tol: float) -> np.ndarray:
    """True where a ring vertex sits further than `tol` from the chord of its two ring
    neighbours, or where the path doubles back (the vertex projects outside that chord)."""
    before, here, after = np.roll(xy, 1, axis=0), xy, np.roll(xy, -1, axis=0)
    chord = after - before
    leg = here - before
    length = np.linalg.norm(chord, axis=1)
    cross = np.abs(chord[:, 0] * leg[:, 1] - chord[:, 1] * leg[:, 0])
    distance = np.where(length > 1e-12, cross / np.maximum(length, 1e-12), np.linalg.norm(leg, axis=1))
    along = np.einsum("ij,ij->i", leg, chord) / np.maximum(length ** 2, 1e-24)
    return (distance > tol) | (along < 0.0) | (along > 1.0)


# ----------------------------------------------------------- pass 2: rebuild and re-triangulate


def _ring_ccw(plan: _Plan, ring: np.ndarray) -> np.ndarray:
    """`ring` (welded ids), reversed if needed so its signed area in the region's own `(e1, e2)`
    frame is positive -- CCW as seen from the side the region normal points to, matching `_wound`'s
    per-triangle convention (`plane_basis` returns a right-handed frame, `cross(e1, e2) == n`)."""
    rows = np.searchsorted(plan.vertex_ids, ring)
    xy = plan.vertex_xy[rows]
    area = 0.5 * float(np.sum(xy[:, 0] * np.roll(xy[:, 1], -1) - np.roll(xy[:, 0], -1) * xy[:, 1]))
    return ring if area >= 0.0 else ring[::-1]


def _region_ring(plan: _Plan, needed: np.ndarray, keep_all_set: frozenset,
                 welded_to_original: np.ndarray):
    """The single simplified (kept-corners-only) outer ring of `plan`, mapped to ORIGINAL vertex
    ids -- or `None` when the region has a hole, more than one disjoint piece, or fewer than 3
    surviving ring vertices. Mirrors `_triangulate`'s own ring-simplification exactly (without
    changing that function's arity, which callers monkeypatch against): the FULL ring when
    `plan.region` took the `keep_all` fallback in the round that produced `builds`, the
    corner-pass-simplified ring otherwise."""
    if len(plan.pieces) != 1:
        return None
    piece = plan.pieces[0]
    if len(piece.rings) != 1:
        return None
    ring = piece.rings[0]
    if plan.region not in keep_all_set:
        ring = ring[needed[ring]]
    if len(ring) < 3:
        return None
    return welded_to_original[_ring_ccw(plan, ring)]


def _late_faces(plans: list[_Plan], fed_back: dict[int, str]) -> list[int]:
    """The faces of every region fed back into the corner pass, in ascending region id. They are
    handed to `_needed_vertices` as if already copied through, which is exactly what marks all of
    their vertices needed -- a late-skipped region IS copied through with all of its vertices."""
    return [int(f) for plan in plans if plan.region in fed_back for f in plan.members]


def _build_regions(plans: list[_Plan], needed: np.ndarray, collinear_tol: float):
    """One whole pass 2 over every region. Returns `(builds, late, keep_all, max_area_rel_error)`,
    where `late` maps the region id of each region that failed AFTER the corner pass (rule 6
    invalid polygon, rule 7 unmappable vertex at CDT time, rule 9 area grew) to its reason, and
    `keep_all` lists the region ids that succeeded only on the full-ring fallback -- the other
    feedback event `merge_regions` reruns for."""
    builds: list[tuple[_Plan, list]] = []
    late: dict[int, str] = {}
    keep_all: list[int] = []
    max_area_rel_error = 0.0
    for plan in plans:
        tris, note = _triangulate(plan, needed, collinear_tol)
        if tris is not None:
            merged_area = _signed_area_sum(plan.vertex_xy, plan.vertex_ids, tris)
            if merged_area > plan.original_area * (1.0 + _AREA_REL_TOL):
                tris, note = None, "area_grew"
            else:
                max_area_rel_error = max(
                    max_area_rel_error,
                    abs(merged_area - plan.original_area) / max(plan.original_area, 1e-300))
        if tris is None:
            late[plan.region] = note
            continue
        if note == "keep_all":
            keep_all.append(plan.region)
        builds.append((plan, tris))
    return builds, late, keep_all, max_area_rel_error


def _triangulate(plan: _Plan, needed: np.ndarray, collinear_tol: float):
    """Rebuild each piece from its kept ring vertices and triangulate. Falls back to keeping ALL
    ring vertices of the region when a rebuilt polygon is invalid or its area drifts from the
    union's. Returns `(triangles, note)`: `note` is `None` for a clean success, `"keep_all"` when
    only the full-ring fallback worked (a feedback event -- see `merge_regions`), and the skip
    reason when `triangles` is `None`."""
    for keep_all in (False, True):
        triangles: list[tuple[int, int, int]] = []
        usable = True
        for piece in plan.pieces:
            rings = [r if keep_all else r[needed[r]] for r in piece.rings]
            polygon = _polygon(plan, rings)
            if polygon is None or not polygon.is_valid:
                usable = False
                break
            if not keep_all and abs(polygon.area - piece.union_area) > (
                    _AREA_REL_TOL * piece.union_area + collinear_tol * piece.union_perimeter):
                usable = False
                break
            got = _cdt_triangles(polygon, plan, rings)
            if got is None:
                return None, "new_vertex"
            triangles.extend(got)
        if usable:
            return triangles, ("keep_all" if keep_all else None)
    return None, "invalid_polygon"


def _polygon(plan: _Plan, rings: list[np.ndarray]):
    if any(len(r) < 3 for r in rings):
        return None
    coords = [plan.vertex_xy[np.searchsorted(plan.vertex_ids, r)] for r in rings]
    try:
        return shapely.Polygon(coords[0], coords[1:])
    except (ValueError, shapely.errors.GEOSException):
        return None


def _cdt_triangles(polygon, plan: _Plan, rings: list[np.ndarray]):
    """`shapely.constrained_delaunay_triangles` adds no Steiner points, so every output coordinate
    must be one of the ring coordinates we fed it -- matched exactly, never re-snapped."""
    lookup = {}
    for ring in rings:
        for vertex, (x, y) in zip(ring, plan.vertex_xy[np.searchsorted(plan.vertex_ids, ring)]):
            lookup[(float(x), float(y))] = int(vertex)
    try:
        cdt = shapely.constrained_delaunay_triangles(polygon)
    except shapely.errors.GEOSException:
        return None
    out = []
    for part in _polygons(cdt):
        triangle = []
        for x, y in np.asarray(part.exterior.coords)[:3]:
            vertex = lookup.get((float(x), float(y)))
            if vertex is None:
                return None
            triangle.append(vertex)
        out.append(tuple(triangle))
    return out


def _cross(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _signed_area_sum(vertex_xy: np.ndarray, vertex_ids: np.ndarray, triangles: list) -> float:
    if not triangles:
        return 0.0
    rows = np.searchsorted(vertex_ids, np.asarray(triangles, np.int64))
    p = vertex_xy[rows]
    return float(0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
                              - (p[:, 1, 1] - p[:, 0, 1]) * (p[:, 2, 0] - p[:, 0, 0])).sum())


# ------------------------------------------------------------------------------ output assembly


def _assemble(mesh: MeshData, topo: Topology, welded_to_original: np.ndarray,
              builds: list, copied: list[int], flat: frozenset,
              region_rings: dict[int, np.ndarray] | None = None) -> MergeResult:
    """Emit faces ordered by the lowest original face index of their group, so a merged region
    lands where its first member was and untouched faces keep their relative order."""
    region_rings = region_rings or {}
    uvs = [mesh.uvs] if len(mesh.uvs) else []
    normals = [mesh.normals] if len(mesh.normals) else []
    next_uv = len(mesh.uvs)
    next_normal = len(mesh.normals)

    emitted: list[tuple] = []
    for face in sorted(set(copied)):
        emitted.append((int(face), mesh.face_v[face], mesh.face_vt[face], mesh.face_vn[face],
                        int(mesh.face_material[face]), int(mesh.face_line[face]),
                        np.array([face], np.int64), -1))

    for plan, triangles in builds:
        kept = np.unique(np.asarray(triangles, np.int64))
        uv_rows = _region_uvs(mesh, topo, plan, kept, flat)
        if uv_rows is not None:
            uvs.append(uv_rows)
            uv_index = {int(v): next_uv + i for i, v in enumerate(kept)}
            next_uv += len(kept)
        normals.append(plan.normal[None, :])
        normal_index = next_normal
        next_normal += 1

        key = int(plan.members.min())
        material = int(mesh.face_material[plan.members[0]])
        line = int(mesh.face_line[plan.members].min())
        source = plan.members.astype(np.int64)
        for triangle in _wound(plan, triangles):
            face_v = welded_to_original[np.asarray(triangle, np.int64)]
            face_vt = (np.array([uv_index[v] for v in triangle], np.int64)
                       if uv_rows is not None else np.full(3, -1, np.int64))
            emitted.append((key, face_v, face_vt, np.full(3, normal_index, np.int64),
                            material, line, source, plan.region))

    emitted.sort(key=lambda row: row[0])
    rings = {i: region_rings[row[7]] for i, row in enumerate(emitted) if row[7] in region_rings}
    n = len(emitted)
    out = replace(
        mesh,
        uvs=np.vstack(uvs) if uvs else mesh.uvs,
        normals=np.vstack(normals) if normals else mesh.normals,
        face_v=np.array([r[1] for r in emitted], np.int64).reshape(n, 3),
        face_vt=np.array([r[2] for r in emitted], np.int64).reshape(n, 3),
        face_vn=np.array([r[3] for r in emitted], np.int64).reshape(n, 3),
        face_material=np.array([r[4] for r in emitted], np.int64),
        face_line=np.array([r[5] for r in emitted], np.int64),
    )
    return MergeResult(mesh=out, source_faces=[r[6] for r in emitted],
                       report={"faces_copied": len(set(copied))}, rings=rings)


def _wound(plan: _Plan, triangles: list) -> list:
    """Wind every triangle counter-clockwise in the `(e1, e2)` frame, which is the region normal:
    `plane_basis` returns a right-handed frame, so `cross(e1, e2) == n`."""
    out = []
    for triangle in triangles:
        rows = np.searchsorted(plan.vertex_ids, np.asarray(triangle, np.int64))
        a, b, c = plan.vertex_xy[rows]
        area = _cross(a, b, c)
        if area > 0:
            out.append(triangle)
        elif area < 0:
            out.append((triangle[0], triangle[2], triangle[1]))
    return out


def _region_uvs(mesh: MeshData, topo: Topology, plan: _Plan, kept: np.ndarray, flat: frozenset):
    """One new `vt` per kept vertex, from the region's least-squares UV fit: largest member seeds,
    iterative refit (`cluster_uv`), taking the fit of the class the largest member seeded. For a
    flat material the region may span several UV classes and the fit is re-based so the region's
    minimum UV lies in [0, 1); for a patterned material the region is one UV class by construction
    and the fit's own offset already reproduces the original tiling, so it is kept."""
    if not len(mesh.uvs) or not (mesh.face_vt[plan.members] >= 0).all():
        return None
    tri_xy = plan.vertex_xy[np.searchsorted(plan.vertex_ids, topo.face_w[plan.members])]
    uv = mesh.uvs[mesh.face_vt[plan.members]]
    area = 0.5 * np.abs((tri_xy[:, 1, 0] - tri_xy[:, 0, 0]) * (tri_xy[:, 2, 1] - tri_xy[:, 0, 1])
                        - (tri_xy[:, 1, 1] - tri_xy[:, 0, 1]) * (tri_xy[:, 2, 0] - tri_xy[:, 0, 0]))
    _, fits = cluster_uv(tri_xy, uv, area)
    jacobian, offset = fits[0]
    rows = plan.vertex_xy[np.searchsorted(plan.vertex_ids, kept)] @ jacobian.T + offset
    if int(mesh.face_material[plan.members[0]]) in flat:
        rows = rows - np.floor(rows.min(axis=0))
    return rows


def _validated_materials(flat_materials: Iterable[int]) -> frozenset:
    out = set()
    for m in flat_materials:
        if not isinstance(m, (int, np.integer)) or isinstance(m, bool):
            raise TypeError(
                f"flat_materials must contain int indices into mesh.materials, got {m!r} "
                f"({type(m).__name__}); use flat_material_indices() to convert names first")
        out.add(int(m))
    return frozenset(out)


def _welded_to_original(mesh: MeshData, topo: Topology) -> np.ndarray:
    """Welded id -> the LOWEST original vertex index that welds to it. Output faces must index
    `mesh.positions`, which is never appended to, so a welded id has to resolve to one of the
    original rows it came from."""
    out = np.full(len(topo.positions_w), np.iinfo(np.int64).max, np.int64)
    np.minimum.at(out, topo.face_w.reshape(-1), mesh.face_v.reshape(-1).astype(np.int64))
    return out


def _welded_of(mesh: MeshData, topo: Topology, out_mesh: MeshData) -> np.ndarray:
    """Welded ids the merged mesh's faces use, via the original-vertex -> welded-id map implied by
    `mesh.face_v` / `topo.face_w`."""
    original_to_welded = np.full(len(mesh.positions), -1, np.int64)
    original_to_welded[mesh.face_v.reshape(-1)] = topo.face_w.reshape(-1)
    return original_to_welded[out_mesh.face_v.reshape(-1)]
