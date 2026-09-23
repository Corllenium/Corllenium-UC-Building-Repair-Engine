"""Close each slab: hang a skirt on every open outline edge of a top surface, and put a bottom
under it, so the interior stops being visible and the hidden-face removal can do its job.

WHY. Measured on file A (spikes 14-16): the sidewalk is a top sheet with partial skirts and
almost no bottom -- 657 open edges, and only 21 of its 182 open TOP edges have any bottom outline
below them. The interior rib walls are therefore visible through the side openings and from
underneath, so the strict hidden-face removal keeps every one of them. Closing the sides alone
hides 105 more faces; sides plus bottom hide 182.

THICKNESS IS MEASURED PER EDGE, not per region. A real skirt on file A varies from 1.3 to 49 in,
so one height for a whole region hangs the shallow side of it far below the slab, and the cap
guard then refuses those faces -- 157 of 418 on file A, which is most of the gap between the 96
faces this step hid and the 182 the spikes predicted. Each open outline edge is therefore
extruded to ITS OWN resolved height (the side faces sharing an endpoint, else any within
`skirt_search_radius`); the region's median is the fallback for an edge that resolves to nothing,
and those are counted as `skirt_edges_fallback`. Two adjacent skirts of different heights leave a
vertical STEP between them at the corner they share. That is correct: the slab really is that
thickness on one side and that thickness on the other, and a step is what a person would draw.

THIS IS THE ONLY STEP IN THE ENGINE THAT INVENTS A VERTEX, and even here it invents as few as it
can: a shifted vertex that rounds onto an existing position reuses that row. Nothing is ever
MOVED. Every face invented here is then put through the cap guard
(`engine.guard.compare.solidify_feedback`), which allows a new face to cover only background, a
back side, or a face whose exposure has gone to zero -- and removes the rest.

WHAT COUNTS AS A TOP SURFACE, and a deliberate deviation. The brief says `n_z > top_min_nz`. That
reads the winding, and the winding is exactly what these exports get wrong: 809 of file A's faces
are wound backwards, and the test fixture `open_box_with_cells` is wound inward throughout, so
its z = 10 LID has `n_z = -1` while its z = 0 FLOOR has `n_z = +1`. A signed test takes the floor
for the top surface and hangs a skirt underneath the box. So a region here is a top surface when
`|n_z| > top_min_nz` AND it SEES SKY: a ray straight up from just above at least
`top_sky_fraction` of its faces escapes. That is a fact about the model rather than about the
exporter's bookkeeping, and it rejects the underside of a slab (which has the slab above it) as
cleanly as it accepts a lid wound the wrong way.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace

import numpy as np
import shapely

from engine.fixes.merge import region_outline
from engine.guard.compare import solidify_feedback
from engine.model import MeshData
from engine.pipeline import Topology
from engine.rays.caster import EmbreeCaster
from engine.topo.planes import cluster_uv, plane_basis
from engine.vis.exposure import EPS_IN, compute_exposure, compute_side_exposure

#: Fraction of a candidate region's faces that must see sky straight up for it to be a top
#: surface. Half, so a slab partly under something else still counts.
TOP_SKY_FRACTION = 0.5

#: Every way one part of a region's bottom can fail to be triangulated. All of them are counted
#: and all of them refuse the whole bottom -- see `_add_bottom`.
_BOTTOM_SKIPS = ("empty_outline", "polygon_failed", "invalid_polygon", "cdt_failed",
                 "non_polygon_part", "corners_unmapped")

#: `1.5 * max(axis quanta)`, clamped -- the same tolerance every guard works to. Kept as a local
#: default so this module does not import `engine.fixes.pipeline`, which imports it.
_DEPTH_TOL_QUANTA = 1.5


@dataclass
class SolidifyResult:
    mesh: MeshData
    #: Bool over `mesh` faces: invented here and kept by the cap guard.
    new_faces: np.ndarray
    report: dict


def _depth_tol(topo: Topology, profile) -> float:
    return min(_DEPTH_TOL_QUANTA * float(topo.quanta.max()),
               getattr(profile, "depth_tol_max", 0.5))


def _face_normals(positions_w: np.ndarray, face_w: np.ndarray) -> np.ndarray:
    tri = positions_w[face_w]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    return n / np.maximum(np.linalg.norm(n, axis=1), 1e-300)[:, None]


def _sees_sky(positions_w: np.ndarray, face_w: np.ndarray, faces: np.ndarray, caster) -> np.ndarray:
    """Per face of `faces`: does a ray straight up from just above its centroid escape?"""
    if not len(faces):
        return np.zeros(0, bool)
    centroid = positions_w[face_w[faces]].mean(axis=1)
    origins = centroid + np.array([0.0, 0.0, EPS_IN])
    return ~caster.any_hit(origins, np.tile(np.array([0.0, 0.0, 1.0]), (len(origins), 1)))


def top_regions(topo: Topology, profile, caster) -> list[int]:
    """Region ids of every top surface, ascending. See the module docstring for why this is
    `|n_z|` plus a sky test rather than the signed `n_z` the brief names."""
    normals = _face_normals(topo.positions_w, topo.face_w)
    top_min_nz = getattr(profile, "top_min_nz", 0.7)
    sky_fraction = getattr(profile, "top_sky_fraction", TOP_SKY_FRACTION)
    out = []
    for region in np.unique(topo.face_region[topo.face_region >= 0]):
        members = np.nonzero(topo.face_region == region)[0]
        if not (np.abs(normals[members][:, 2]) > top_min_nz).all():
            continue
        if _sees_sky(topo.positions_w, topo.face_w, members, caster).mean() >= sky_fraction:
            out.append(int(region))
    return out


def _edge_index(topo: Topology) -> dict[tuple[int, int], int]:
    return {(int(a), int(b)): i for i, (a, b) in enumerate(topo.table.edges)}


def _ring_edges(ring: np.ndarray) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in zip(ring, np.roll(ring, -1))]


def _open_edges(topo: Topology, rings: list[np.ndarray], index: dict) -> list[tuple[int, int]]:
    """Outline edges whose edge-table count is 1. A count of 2 or more already meets a skirt or a
    neighbouring region, and gets nothing. An outline edge the table does not know (which a
    union ring can produce where a T-junction was simplified away) is left alone too: there is no
    count to trust."""
    out = []
    for ring in rings:
        for a, b in _ring_edges(ring):
            edge = index.get((min(a, b), max(a, b)))
            if edge is not None and topo.table.counts[edge] == 1:
                out.append((a, b))
    return out


def _side_faces(topo: Topology, profile) -> np.ndarray:
    normals = _face_normals(topo.positions_w, topo.face_w)
    return np.nonzero(topo.ok & (np.abs(normals[:, 2]) <= getattr(profile, "top_min_nz", 0.7)))[0]


def _edge_thickness(topo: Topology, edges, sides: np.ndarray, side_low: np.ndarray,
                     side_centroid: np.ndarray, vertex_sides: dict, radius: float
                     ) -> list[float | None]:
    """Per open edge, IN `edges` ORDER, `top z - lowest z of the side faces that reach it`, or
    `None` when no side face does. Endpoint-sharing first, because a skirt that is already there
    is attached to the very vertex the new one hangs from; the radius search is the fallback for
    an edge whose own corner has nothing on it.

    One entry per edge, `None` included: the caller extrudes each edge to ITS OWN height and
    needs to know which ones it could not measure. It used to return only the resolved numbers,
    which is why they could only ever be used as a single per-region statistic."""
    out: list[float | None] = []
    for a, b in edges:
        top_z = float(max(topo.positions_w[a][2], topo.positions_w[b][2]))
        rows = sorted(vertex_sides.get(a, set()) | vertex_sides.get(b, set()))
        if not rows:
            midpoint = (topo.positions_w[a] + topo.positions_w[b]) / 2.0
            near = np.linalg.norm(side_centroid - midpoint, axis=1) <= radius
            rows = np.nonzero(near)[0].tolist()
        if not rows:
            out.append(None)
            continue
        thickness = top_z - float(side_low[rows].min())
        out.append(thickness if thickness > 0.0 else None)
    return out


def _uv_scale(mesh: MeshData, topo: Topology, members: np.ndarray, origin, basis) -> float:
    """The region's own inches-to-UV scale, `sqrt(|det J|)` of its least-squares UV fit --
    `engine.fixes.merge._region_uvs` fits the same J. 0.0 when the region carries no UVs, which
    makes every new face's `vt` -1."""
    if not len(mesh.uvs) or not (mesh.face_vt[members] >= 0).all():
        return 0.0
    tri_xy = (topo.positions_w[topo.face_w[members]] - origin) @ basis
    uv = mesh.uvs[mesh.face_vt[members]]
    area = 0.5 * np.abs((tri_xy[:, 1, 0] - tri_xy[:, 0, 0]) * (tri_xy[:, 2, 1] - tri_xy[:, 0, 1])
                        - (tri_xy[:, 1, 1] - tri_xy[:, 0, 1]) * (tri_xy[:, 2, 0] - tri_xy[:, 0, 0]))
    jacobian, _offset = cluster_uv(tri_xy, uv, area)[1][0]
    return float(np.sqrt(abs(float(np.linalg.det(jacobian)))))


class _Builder:
    """Collects invented vertices and faces. A shifted vertex that ROUNDS onto a position the
    mesh already has reuses that row, so a slab whose skirts already reach the right depth
    invents nothing at all."""

    def __init__(self, mesh: MeshData):
        self.mesh = mesh
        self.positions = [row for row in mesh.positions]
        self.uvs = [row for row in mesh.uvs]
        self.decimals = mesh.coord_decimals
        self.lookup = {self._key(p): i for i, p in enumerate(mesh.positions)}
        self.invented = 0
        self.faces: list[tuple] = []

    def _key(self, p) -> tuple:
        return tuple(np.round(np.asarray(p, dtype=np.float64), self.decimals) + 0.0)

    def vertex(self, p) -> int:
        key = self._key(p)
        if key in self.lookup:
            return self.lookup[key]
        self.lookup[key] = len(self.positions)
        self.positions.append(np.asarray(p, dtype=np.float64))
        self.invented += 1
        return len(self.positions) - 1

    def face(self, ids, material: int, uv_scale: float) -> None:
        points = np.array([self.positions[i] for i in ids], dtype=np.float64)
        vt = [-1, -1, -1]
        if uv_scale > 0.0:
            normal = np.cross(points[1] - points[0], points[2] - points[0])
            length = float(np.linalg.norm(normal))
            if length > 0.0:
                e1, e2 = plane_basis(normal / length)
                xy = (points - points[0]) @ np.stack([e1, e2], axis=1) * uv_scale
                vt = [len(self.uvs) + k for k in range(3)]
                self.uvs.extend(xy)
        self.faces.append((list(ids), vt, material))

    def build(self) -> tuple[MeshData, np.ndarray]:
        n = self.mesh.n_faces
        if not self.faces:
            return self.mesh, np.zeros(n, bool)
        out = replace(
            self.mesh,
            positions=np.array(self.positions, dtype=np.float64),
            uvs=np.array(self.uvs, dtype=np.float64).reshape(-1, 2) if self.uvs else self.mesh.uvs,
            face_v=np.vstack([self.mesh.face_v, [f[0] for f in self.faces]]).astype(np.int64),
            face_vt=np.vstack([self.mesh.face_vt, [f[1] for f in self.faces]]).astype(np.int64),
            face_vn=np.vstack([self.mesh.face_vn,
                                np.full((len(self.faces), 3), -1, np.int64)]).astype(np.int64),
            face_material=np.append(self.mesh.face_material,
                                     [f[2] for f in self.faces]).astype(np.int64),
            face_line=np.append(self.mesh.face_line,
                                 np.arange(n + 1, n + 1 + len(self.faces))).astype(np.int64),
        )
        new = np.zeros(out.n_faces, bool)
        new[n:] = True
        return out, new


def _wound_outward(quad, positions, outward) -> list[tuple[int, int, int]]:
    """The quad as two triangles, reversed together when its normal disagrees with `outward`."""
    a, b, c, d = quad
    points = np.array([positions[a], positions[b], positions[c]], dtype=np.float64)
    normal = np.cross(points[1] - points[0], points[2] - points[0])
    if float(normal @ outward) < 0.0:
        a, b, c, d = d, c, b, a
    return [(a, b, c), (a, c, d)]


def solidify(mesh: MeshData, topo: Topology, profile) -> SolidifyResult:
    """Skirt and bottom every top-surface region of `mesh`, then let the cap guard delete
    whichever new faces cover something a person can still see.

    `profile` is an `engine.fixes.pipeline.FixProfile` (duck-typed, so this module does not
    import the module that imports it). Deterministic: regions are visited in ascending id,
    outline edges in ring order, and every tolerance comes from the mesh's own print precision.
    """
    started = time.perf_counter()
    tol = _depth_tol(topo, profile)
    radius = getattr(profile, "skirt_search_radius", 60.0)
    min_h = getattr(profile, "min_thickness", 2.0)
    max_h = getattr(profile, "max_thickness", 36.0)
    bottom_fraction = getattr(profile, "bottom_exists_fraction", 0.9)
    bottom_extra = getattr(profile, "bottom_search_extra", 24.0)
    guard_size = getattr(profile, "guard_size", (900, 600))

    ok_faces = topo.face_w[topo.ok]
    caster = EmbreeCaster(topo.positions_w, ok_faces)
    regions = top_regions(topo, profile, caster)

    sides = _side_faces(topo, profile)
    side_low = (topo.positions_w[topo.face_w[sides]][:, :, 2].min(axis=1) if len(sides)
                else np.zeros(0))
    side_centroid = (topo.positions_w[topo.face_w[sides]].mean(axis=1) if len(sides)
                     else np.zeros((0, 3)))
    vertex_sides: dict[int, set] = {}
    for row, face in enumerate(sides):
        for v in topo.face_w[face]:
            vertex_sides.setdefault(int(v), set()).add(row)

    index = _edge_index(topo)
    plans = []
    unmappable = 0
    for region in regions:
        members = np.nonzero(topo.face_region == region)[0]
        outline = region_outline(topo, members)
        if outline is None:
            unmappable += 1
            continue
        pieces, normal, origin, basis = outline
        rings = [ring for piece in pieces for ring in piece.rings]
        edges = _open_edges(topo, rings, index)
        thicknesses = _edge_thickness(topo, edges, sides, side_low, side_centroid, vertex_sides,
                                      radius)
        plans.append({"region": region, "members": members, "pieces": pieces, "normal": normal,
                      "origin": origin, "basis": basis, "edges": edges,
                      "thicknesses": thicknesses})

    file_wide = [t for plan in plans for t in plan["thicknesses"] if t is not None]
    file_median = float(np.median(file_wide)) if file_wide else min_h

    builder = _Builder(mesh)
    welded_to_original = _welded_to_original(mesh, topo)
    report_thickness: dict[str, float] = {}
    report_bottom_depth: dict[str, float] = {}
    skirts = 0
    skirt_length = 0.0
    skirt_fallback = 0
    bottoms = 0
    bottoms_refused = 0
    bottom_skips = {reason: 0 for reason in _BOTTOM_SKIPS}
    bottom_exists = 0
    unresolved_thickness = 0

    def clamp(height: float) -> float:
        return float(min(max(height, min_h), max_h))

    for plan in plans:
        members = plan["members"]
        own = [clamp(t) for t in plan["thicknesses"] if t is not None]
        resolved = bool(own) or bool(file_wide)
        # The region's FALLBACK height, for the edges that could not be measured at all. Every
        # edge that could be uses its own; see the module docstring.
        h = clamp(float(np.median(own)) if own else file_median)
        # ...and the BOTTOM goes at the shallowest height any of its skirts actually reached, so
        # it meets one of them instead of crossing the others. At the median it hangs below the
        # shallow skirts -- leaving the steps between them open from underneath, which is the
        # one direction a bottom exists to close -- and cuts the deep ones in half.
        bottom_h = min(own) if own else h
        report_thickness[str(plan["region"])] = h
        report_bottom_depth[str(plan["region"])] = bottom_h
        material = int(mesh.face_material[members[0]])
        uv_scale = _uv_scale(mesh, topo, members, plan["origin"], plan["basis"])
        centroid = topo.positions_w[topo.face_w[members]].reshape(-1, 3).mean(axis=0)

        # keyed by (welded id, height): two edges of one region that measured different depths
        # need two different shifted vertices at the corner they share, and the vertical step
        # between their skirts is the honest picture of a slab whose thickness really varies.
        shifted: dict[tuple[int, float], int] = {}

        def down(welded: int, height: float) -> int:
            key = (int(welded), float(height))
            if key not in shifted:
                p = topo.positions_w[welded] - np.array([0.0, 0.0, height])
                shifted[key] = builder.vertex(p)
            return shifted[key]

        for (a, b), measured in zip(plan["edges"], plan["thicknesses"]):
            edge_h = clamp(measured) if measured is not None else h
            if measured is None:
                skirt_fallback += 1
            quad = [int(welded_to_original[a]), int(welded_to_original[b]),
                    down(b, edge_h), down(a, edge_h)]
            midpoint = (topo.positions_w[a] + topo.positions_w[b]) / 2.0
            outward = midpoint - centroid
            outward[2] = 0.0
            if float(outward @ outward) == 0.0:
                outward = np.array([0.0, 0.0, 1.0])
            for triangle in _wound_outward(quad, builder.positions, outward):
                builder.face(triangle, material, uv_scale)
            skirts += 1
            skirt_length += float(np.linalg.norm(topo.positions_w[a] - topo.positions_w[b]))

        # A bottom is only invented at a thickness that was MEASURED -- this region's own open
        # edges, or the file-wide median of everyone else's. When nothing in the file resolved,
        # `h` is just `min_thickness`, and a floor at a made-up depth is pure invention: measured
        # on `box_with_partition`, whose closed cube has no open outline edge anywhere, that put
        # a lid 2 in under the top INSIDE a solid box. A skirt on that fallback is different --
        # it closes a hole a person can see, and the cap guard judges it -- so it still runs.
        if not resolved:
            unresolved_thickness += 1
            continue
        if _has_bottom(topo, members, caster, bottom_h, tol, bottom_fraction, bottom_extra):
            bottom_exists += 1
            continue
        added, part_skipped = _add_bottom(builder, topo, plan, lambda c: down(c, bottom_h),
                                           material, uv_scale, welded_to_original, bottom_skips)
        if added:
            bottoms += 1
        elif part_skipped:
            bottoms_refused += 1

    solid, new_faces = builder.build()
    cap_history: list = []
    cap_removed = 0
    if new_faces.any():
        solid, new_faces, cap_history, cap_removed = _cap_guard(
            mesh, solid, new_faces, guard_size, getattr(profile, "n_dirs", 128),
            getattr(profile, "cover_max_exposure", 0.10),
            getattr(profile, "cap_guard_max_rounds", 8))

    hidden_before, hidden_after = _newly_hidden(mesh, solid, topo, profile)
    report = {
        "regions_processed": len(plans),
        "skirts_added": skirts,
        "skirt_length_total": round(skirt_length, 4),
        #: Open edges whose own height could not be measured, and which therefore fell back to
        #: their region's median (or, with nothing in the file resolved, `min_thickness`).
        "skirt_edges_fallback": skirt_fallback,
        "bottoms_added": bottoms,
        #: Regions whose bottom WAS built and then thrown away whole, because at least one of
        #: its parts could not be triangulated. Never reported as added.
        "bottoms_partial_refused": bottoms_refused,
        #: Why, per reason -- see `_BOTTOM_SKIPS` and `_add_bottom`.
        "bottom_skips": bottom_skips,
        "bottom_exists": bottom_exists,
        "bottom_thickness_unresolved": unresolved_thickness,
        "outline_unmappable": unmappable,
        "thickness_per_region": report_thickness,
        #: Per region, the depth its bottom was placed (or would have been): the SHALLOWEST
        #: height any of its skirts reached, not the median `thickness_per_region` holds.
        "bottom_depth_per_region": report_bottom_depth,
        "invented_vertices": int(len(solid.positions) - len(mesh.positions)),
        "cap_guard_rounds": len(cap_history),
        "cap_guard_removed": cap_removed,
        #: THE CAP GUARD AS AN INVARIANT, not as a count of what it happened to delete. True
        #: only when the LAST entry of `cap_guard` -- which `solidify_feedback` guarantees is a
        #: verification of the mesh being handed back, even when the round limit cut the loop
        #: off -- shows 0 failing pixels. Vacuously True when nothing was invented at all.
        "cap_guard_passed": bool(not cap_history or cap_history[-1]["failing_pixels"] == 0),
        #: `engine.guard.compare.solidify_feedback`'s own per-round history, which is what
        #: `FixResult.guard_solidify` carries: the cap guard's verdict against the PRISTINE
        #: input, the only comparison in the run that still uses it as the reference.
        "cap_guard": cap_history,
        "faces_hidden_before": hidden_before,
        "faces_hidden_after": hidden_after,
        "faces_newly_hidden": hidden_after - hidden_before,
        "runtime_s": round(time.perf_counter() - started, 3),
    }
    return SolidifyResult(mesh=solid, new_faces=new_faces, report=report)


def _welded_to_original(mesh: MeshData, topo: Topology) -> np.ndarray:
    """Welded id -> the LOWEST original vertex index that welds to it, so a face this module
    emits indexes `mesh.positions` exactly like every other face does."""
    out = np.full(len(topo.positions_w), np.iinfo(np.int64).max, np.int64)
    np.minimum.at(out, topo.face_w.reshape(-1), mesh.face_v.reshape(-1).astype(np.int64))
    return out


def _has_bottom(topo: Topology, members: np.ndarray, caster, h: float, tol: float,
                 fraction: float, search_extra: float = 24.0) -> bool:
    """A ray straight down from just below each of the region's face centroids: the region
    already has a bottom when at least `fraction` of them meet something within
    `h + search_extra + tol`.

    THE SEARCH REACHES PAST `h` DELIBERATELY. `h` is the SHALLOWEST height this region's own
    skirts measured, and an underside deeper than that is still this slab's underside -- it is
    what a slab that is thicker in the middle than at its rim looks like. Stopping at `h + tol`
    declares such a region bottomless and invents a second bottom ABOVE the real one, boxing it
    in; that is the same defect S-C1's cap-guard rule catches after the fact, and this is the
    half of it that never creates the face in the first place.

    Bounded rather than unbounded, because "anything at all below me" is not a bottom: a slab
    100 in above a floor does not have that floor for an underside."""
    centroid = topo.positions_w[topo.face_w[members]].mean(axis=1)
    origins = centroid - np.array([0.0, 0.0, EPS_IN])
    directions = np.tile(np.array([0.0, 0.0, -1.0]), (len(origins), 1))
    tri, t = caster.first_hit(origins, directions)
    return bool(((tri >= 0) & (t <= h + search_extra + tol)).mean() >= fraction)


def _add_bottom(builder: _Builder, topo: Topology, plan: dict, down, material: int,
                 uv_scale: float, welded_to_original: np.ndarray, skips: dict) -> tuple[bool, bool]:
    """The region's outline (outer plus inners), shifted down by the region's bottom depth and
    triangulated over the SHIFTED vertices with `shapely.constrained_delaunay_triangles`, which
    adds no Steiner points -- so every bottom corner is a vertex this function already made.
    Wound so the bottom faces DOWN.

    ALL OR NOTHING. Every triangle is worked out FIRST, and nothing is emitted unless all of them
    were. A bottom missing one of its parts is a HOLE in the underside, which is worse than no
    bottom at all: the rest of it still hides whatever is above, so the hidden pass deletes the
    real geometry and the hole is what ships. Each of the five ways a part can be skipped is
    counted into `skips` (which the caller reports as `bottom_skips`), because a silent `continue`
    is how a half-built underside would leave no trace at all.

    Returns `(added, skipped)`: `added` is True only for a COMPLETE bottom; `skipped` says at
    least one part was refused, which the caller counts as `bottoms_partial_refused`. Building the
    triangle list before touching the builder is also what keeps a refused bottom from inventing
    vertices -- `down()` is only called for parts that are actually emitted."""
    triangles: list[list[int]] = []
    skipped = False
    for piece in plan["pieces"]:
        rings = [r for r in piece.rings if len(r) >= 3]
        if not rings:
            skips["empty_outline"] += 1
            skipped = True
            continue
        xy = {}
        for ring in rings:
            for welded in ring:
                p = topo.positions_w[int(welded)]
                xy[int(welded)] = (float(p[0]), float(p[1]))
        try:
            polygon = shapely.Polygon([xy[int(v)] for v in rings[0]],
                                       [[xy[int(v)] for v in r] for r in rings[1:]])
        except (ValueError, shapely.errors.GEOSException):
            skips["polygon_failed"] += 1
            skipped = True
            continue
        if not polygon.is_valid:
            skips["invalid_polygon"] += 1
            skipped = True
            continue
        lookup = {xy[int(v)]: int(v) for ring in rings for v in ring}
        try:
            cdt = shapely.constrained_delaunay_triangles(polygon)
        except shapely.errors.GEOSException:
            skips["cdt_failed"] += 1
            skipped = True
            continue
        for part in getattr(cdt, "geoms", []):
            if part.geom_type != "Polygon" or part.is_empty:
                skips["non_polygon_part"] += 1
                skipped = True
                continue
            corners = [lookup.get((float(x), float(y)))
                       for x, y in np.asarray(part.exterior.coords)[:3]]
            if any(c is None for c in corners):
                skips["corners_unmapped"] += 1
                skipped = True
                continue
            triangles.append([int(c) for c in corners])

    if skipped or not triangles:
        return False, skipped
    for corners in triangles:
        ids = [down(c) for c in corners]
        points = np.array([builder.positions[i] for i in ids], dtype=np.float64)
        normal = np.cross(points[1] - points[0], points[2] - points[0])
        if float(normal[2]) > 0.0:
            ids = [ids[0], ids[2], ids[1]]
        builder.face(ids, material, uv_scale)
    return True, False


def _cap_guard(original: MeshData, solid: MeshData, new_faces: np.ndarray,
                guard_size: tuple[int, int], n_dirs: int = 128,
                cover_max_exposure: float = 0.10, max_rounds: int = 8):
    """Render the original and the solidified mesh over `VIEWS_26` and drop every new face the
    cap rule refuses (see `engine.guard.compare.solidify_feedback`). Returns
    `(mesh, new_faces, history, removed)`.

    The exposure the cap rule reads is measured on the ORIGINAL geometry -- `faces_before`
    alone, cast against itself -- because a face that some invented face is covering has, by
    construction, exposure 0 in the solidified mesh, and a rule that read that would authorise
    itself. It costs strictly less than the solidified-mesh measurement it replaces (fewer
    faces, one caster) and is taken once, before any round removes anything.

    `ok` is deliberately all-True here, like the array it replaces: a RELATIVELY degenerate
    face (`engine.topo.adjacency.degenerate_mask` allows `area <= 1e-7 * longest**2`) is real,
    hittable surface and is rendered as one, so it needs a real exposure rather than the 0.0
    `compute_side_exposure` gives a `not ok` face -- which would have made every sliver in the
    file free to cover."""
    from engine.guard.views import VIEWS_26
    from engine.topo.weld import weld_exact

    positions_w, remap = weld_exact(solid.positions, solid.coord_decimals)
    centre = (positions_w.min(axis=0) + positions_w.max(axis=0)) / 2.0
    positions_c = positions_w - centre
    faces_after = remap[solid.face_v]
    faces_before = faces_after[: original.n_faces]
    front, _back = compute_side_exposure(positions_c, faces_before,
                                         np.ones(len(faces_before), bool), n_dirs=n_dirs)

    keep, history = solidify_feedback(positions_c, faces_before, faces_after, new_faces, front,
                                       cover_max_exposure=cover_max_exposure,
                                       views=VIEWS_26, size=guard_size, max_rounds=max_rounds)
    removed = int((~keep).sum())
    if not removed:
        return solid, new_faces, history, 0
    out = replace(solid, face_v=solid.face_v[keep], face_vt=solid.face_vt[keep],
                  face_vn=solid.face_vn[keep], face_material=solid.face_material[keep],
                  face_line=solid.face_line[keep])
    return out, new_faces[keep], history, removed


def _newly_hidden(original: MeshData, solid: MeshData, topo: Topology, profile) -> tuple[int, int]:
    """How many of the ORIGINAL faces have exposure 0 before and after -- the number this whole
    step exists to move."""
    from engine.topo.weld import weld_exact

    n_dirs = getattr(profile, "n_dirs", 128)
    positions_w, remap = weld_exact(solid.positions, solid.coord_decimals)
    centre = (positions_w.min(axis=0) + positions_w.max(axis=0)) / 2.0
    positions_c = positions_w - centre
    faces_after = remap[solid.face_v]
    faces_before = faces_after[: original.n_faces]
    ok = topo.ok
    before = compute_exposure(positions_c, faces_before, ok, n_dirs=n_dirs)
    after = compute_exposure(positions_c, faces_after,
                              np.append(ok, np.ones(solid.n_faces - original.n_faces, bool)),
                              n_dirs=n_dirs)[: original.n_faces]
    return int(((before <= 0.0) & ok).sum()), int(((after <= 0.0) & ok).sum())
