"""Close each slab: build every side of a top surface that is missing OR BROKEN, and a bottom under
it, so the interior stops being visible and the hidden-face removal can do its job.

WHY. Measured on file A (spikes 14-16): the sidewalk is a top sheet with partial skirts and
almost no bottom -- 657 open edges, and only 21 of its 182 open TOP edges have any bottom outline
below them. The interior rib walls are therefore visible through the side openings and from
underneath, so the strict hidden-face removal keeps every one of them.

SR2: A BROKEN SIDE IS REBUILT, NOT PRESERVED. The first version walled only OPEN outline edges
(edge count 1) and let its cap guard refuse any wall that covered something visible. A side that
exists but is broken -- the owner's photograph is file B's ramp side, a row of triangular teeth
with gaps, some showing their purple back -- is visible by definition, so it was kept, and the
inside seen through its gaps with it: the teeth share some of the top's edges (count 2, never
walled) and the walls on the gaps covered the visible teeth and the visible inside (refused). The
same happened to a BOTTOM that exists in part (file A's region 11, 78 % of that file's remaining
back-face pixels: a sawtooth strip of bottom at exactly the measured depth, and the new bottom
refused because it met the strip in the same plane). So now, per top region:

1. EVERY outline edge is considered, whatever its edge count, except one where the top simply
   CONTINUES into another top surface (a probe just outside the edge finds a top-like face whose
   plane passes through the edge -- two regions of one slab, which the old solidify walled from
   both sides, inside the slab).
2. The edge's side band is the vertical plane through it, from the top edge down to the edge's
   measured height, `FixProfile.side_band` either side. Original faces lying in that band (every
   corner within it, within `PIECE_MAX_ANGLE_DEG` of parallel, mostly inside the side's
   rectangle) are its PIECES. When they cover the side (`SIDE_WHOLE_FRACTION`), the side is
   whole and nothing happens -- an existing side is never an open edge, even when a T-junction
   leaves its top edge unshared (file B, merge region 38). Otherwise a wall is built and the
   pieces are REPLACED: removed together with the wall's acceptance.
3. A bottom is built, as before, when fewer than `bottom_exists_fraction` of the region's faces
   find an underside below them; original faces lying in the bottom's band are its pieces.
4. The cap guard (`engine.guard.compare.solidify_feedback`) allows two more named changes: a
   replaced piece's pixel showing the face that replaced it, and a pixel whose BEFORE hit point
   lies INSIDE a slab's volume (under its top, above its measured bottom). Anything outside the
   volume still may never be covered.

THICKNESS IS MEASURED PER EDGE, not per region. A real skirt on file A varies from 1.3 to 49 in, so
one height for a whole region hangs the shallow side of it far below the slab. Each wall is
extruded to ITS edge's resolved height (the side faces sharing an endpoint, else any within
`skirt_search_radius`); the region's median is the fallback for an edge that resolves to nothing,
counted as `skirt_edges_fallback`. Whether a side is whole is judged at its UNCLAMPED measured
height: a 1.3 in skirt is a whole 1.3 in side, not a broken 2 in one.

THE SLAB VOLUME, which rule 5 of the cap guard reads, is the region's footprint from its top down
to its bottom depth: `bottom_h` (the SHALLOWEST measured wall, where the bottom goes) when a bottom
is built, and the MEASURED depth of the underside it already has otherwise. A wall hanging deeper
than that is a fin below the slab, and what it covers there is outside.

THIS IS THE ONLY STEP IN THE ENGINE THAT INVENTS A VERTEX, and even here it invents as few as it
can: a shifted vertex that rounds onto an existing position reuses that row. Nothing is ever
MOVED. The mesh handed back is the input's faces, minus the pieces replaced, in order, followed by
every invented face the cap guard kept.

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
from engine.guard.compare import (INTERIOR_AT_OR_ABOVE_TOP, INTERIOR_BELOW_BOTTOM,
                                   INTERIOR_INSIDE, INTERIOR_OUTSIDE_FOOTPRINT,
                                   INTERIOR_UNMEASURED, solidify_feedback)
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

#: SR2. A side is WHOLE -- nothing to build -- when the pieces in its band cover this fraction of
#: its rectangle. Short of 1 only by numerical slack.
SIDE_WHOLE_FRACTION = 0.99

#: SR2. A piece of a side (or bottom) lies within this many degrees of that side's own plane.
PIECE_MAX_ANGLE_DEG = 30.0

#: SR2. The ceiling on `FixProfile.side_band`, in inches. Measured in SR1 over every original face
#: the old cap guard refused to cover because it lay near a new wall or bottom and parallel to it:
#: 99 % of those pixels lie within 1.98 in of the new face's plane on file A and within 2.35 in on
#: file B, and beyond 3 in there are only 10 (A) and 15 (B) pixels of noise. A band wider than
#: that stops describing the slab's own broken side and starts reaching things that stand next to
#: it -- a railing or a wall a few inches outside the edge.
SIDE_BAND_MAX = 3.0

#: SR2. The continuation probe: how far outside an outline edge it looks, in inches, and where
#: along the edge. An edge continues into another top surface when most samples find one whose
#: plane passes through the edge.
_PROBE_OUT = 0.5
_PROBE_FRACTIONS = (0.25, 0.5, 0.75)

#: A piece belongs to a side when at least this fraction of its own area lies inside the side's
#: rectangle: a railing standing in the band but reaching far above the top is not a piece.
_PIECE_INSIDE_FRACTION = 0.5


@dataclass
class SolidifyResult:
    mesh: MeshData
    #: Bool over `mesh` faces: invented here and kept by the cap guard.
    new_faces: np.ndarray
    report: dict
    #: SR2. Bool over the INPUT mesh's faces: pieces of a broken side or bottom that a kept closing
    #: face replaced. They are NOT in `mesh`: its first rows are the input's faces with these left
    #: out, in their original order, and the invented faces follow.
    replaced: np.ndarray


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
    """Outline edges whose edge-table count is 1 -- the edges the first solidify walled. SR2
    walls whatever is missing or broken instead (see the module docstring); this stays as the
    measure of how many outline edges the export left open."""
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
    """Per edge, IN `edges` ORDER, `top z - lowest z of the side faces that reach it`, or
    `None` when no side face does. Endpoint-sharing first, because a side that is already there
    is attached to the very vertex the new one hangs from; the radius search is the fallback for
    an edge whose own corner has nothing on it.

    One entry per edge, `None` included: the caller extrudes each edge to ITS OWN height and
    needs to know which ones it could not measure."""
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
    invents nothing at all. Every face carries its closing GROUP: one per wall, one per bottom."""

    def __init__(self, mesh: MeshData):
        self.mesh = mesh
        self.positions = [row for row in mesh.positions]
        self.uvs = [row for row in mesh.uvs]
        self.decimals = mesh.coord_decimals
        self.lookup = {self._key(p): i for i, p in enumerate(mesh.positions)}
        self.invented = 0
        self.faces: list[tuple] = []
        self.groups: list[int] = []

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

    def face(self, ids, material: int, uv_scale: float, group: int) -> None:
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
        self.groups.append(int(group))

    def build(self) -> tuple[MeshData, np.ndarray, np.ndarray]:
        """`(mesh, new_faces, new_group)`: the input with every invented face appended, the
        bool mask of the appended faces, and each face's closing group (-1 for the input's)."""
        n = self.mesh.n_faces
        if not self.faces:
            return self.mesh, np.zeros(n, bool), np.full(n, -1, np.int64)
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
            # -1, not a line number. `face_line` is the row of the OBJ a face was read from,
            # and a face invented here was never in any file: `n + 1, n + 2, ...` are real rows
            # that belong to OTHER faces, and would send anyone chasing a defect to the wrong
            # one. `engine.fixes.merge` takes the MINIMUM line of a region it rebuilds, so a
            # region mixing invented and read faces reports -1 -- which is true of it.
            face_line=np.append(self.mesh.face_line,
                                 np.full(len(self.faces), -1, np.int64)).astype(np.int64),
        )
        new = np.zeros(out.n_faces, bool)
        new[n:] = True
        group = np.full(out.n_faces, -1, np.int64)
        group[n:] = self.groups
        return out, new, group


def _wound_outward(quad, positions, outward) -> list[tuple[int, int, int]]:
    """The quad as two triangles, reversed together when its normal disagrees with `outward`."""
    a, b, c, d = quad
    points = np.array([positions[a], positions[b], positions[c]], dtype=np.float64)
    normal = np.cross(points[1] - points[0], points[2] - points[0])
    if float(normal @ outward) < 0.0:
        a, b, c, d = d, c, b, a
    return [(a, b, c), (a, c, d)]


def _footprint(topo: Topology, members: np.ndarray):
    """The region's xy footprint: the union of its triangles seen from above, prepared."""
    tri = topo.positions_w[topo.face_w[members]][:, :, :2]
    polys = shapely.polygons(np.concatenate([tri, tri[:, :1]], axis=1))
    foot = shapely.union_all(polys[shapely.area(polys) > 0.0])
    shapely.prepare(foot)
    return foot


def _z_top(normal: np.ndarray, origin: np.ndarray, x, y):
    """The region's own plane, as a height over (x, y)."""
    return origin[2] - (normal[0] * (x - origin[0]) + normal[1] * (y - origin[1])) / normal[2]


def _outward(foot, pa: np.ndarray, pb: np.ndarray, centroid: np.ndarray) -> np.ndarray | None:
    """Horizontal unit vector perpendicular to edge `pa -> pb`, pointing OUT of the footprint:
    whichever side a point half an inch off the edge's middle falls outside it. The region
    centroid decides only when both sides agree (a sliver narrower than the probe), which is
    what the first solidify used for every edge -- and got wrong on an L-shaped region."""
    t = pb[:2] - pa[:2]
    length = float(np.hypot(t[0], t[1]))
    if length <= 1e-9:
        return None
    q = np.array([t[1], -t[0]]) / length
    m = (pa[:2] + pb[:2]) / 2.0
    ends = np.array([m + _PROBE_OUT * q, m - _PROBE_OUT * q])
    plus, minus = shapely.contains_xy(foot, ends[:, 0], ends[:, 1])
    if plus and not minus:
        q = -q
    elif plus == minus and float(q @ (m - centroid[:2])) < 0.0:
        q = -q
    return np.array([q[0], q[1], 0.0])


def _continues(topo: Topology, ok_ids: np.ndarray, caster, normals: np.ndarray,
               edges: list[tuple[np.ndarray, np.ndarray, np.ndarray]], top_min_nz: float,
               tol: float) -> np.ndarray:
    """Per edge `(pa, pb, outward)`: does the top surface CONTINUE across it -- another top-like
    face just outside whose plane passes through the edge? Probed at `_PROBE_FRACTIONS` along
    the edge, `_PROBE_OUT` outside it, straight down from an inch above; a majority decides.
    Such an edge is where two top regions of one slab meet, and has no side at all."""
    if not edges:
        return np.zeros(0, bool)
    points, origins = [], []
    for pa, pb, q in edges:
        for f in _PROBE_FRACTIONS:
            p = pa + f * (pb - pa)
            points.append(p)
            origins.append(p + _PROBE_OUT * q + np.array([0.0, 0.0, 1.0]))
    points = np.asarray(points)
    tri, _t = caster.first_hit(np.asarray(origins), np.tile([0.0, 0.0, -1.0], (len(origins), 1)))
    hit = tri >= 0
    face = np.where(hit, ok_ids[np.where(hit, tri, 0)], 0)
    n = normals[face]
    v0 = topo.positions_w[topo.face_w[face][:, 0]]
    through = np.abs(np.einsum("ij,ij->i", points - v0, n)) <= tol
    ok = hit & (np.abs(n[:, 2]) > top_min_nz) & through
    return ok.reshape(len(edges), len(_PROBE_FRACTIONS)).sum(axis=1) * 2 > len(_PROBE_FRACTIONS)


class _Faces:
    """The input's faces as candidate pieces: world triangles, unit normals, bounding boxes, and
    which of them may be a piece at all (non-degenerate, and not part of any top surface -- a top
    face is never removed or covered)."""

    def __init__(self, topo: Topology, top_faces: np.ndarray):
        self.tri = topo.positions_w[topo.face_w]
        self.normal = _face_normals(topo.positions_w, topo.face_w)
        self.lo = self.tri.min(axis=1)
        self.hi = self.tri.max(axis=1)
        self.eligible = topo.ok.copy()
        self.eligible[top_faces] = False

    def near(self, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        return np.nonzero(self.eligible & (self.hi >= lo).all(axis=1)
                          & (self.lo <= hi).all(axis=1))[0]


def _wall_pieces(faces: _Faces, pa, pb, q, h_measured: float, h_wall: float, band: float,
                 claimed: set, built: list | None = None) -> tuple[list[int], float, float]:
    """`(pieces, coverage, depth)` of the side under edge `pa -> pb` (outward `q`).

    In the side's own frame -- `u` along the edge, `v` the height below the top edge, so a
    sloped edge's side is still a rectangle `[0, L] x [-h, 0]` -- a face IN THE BAND is an
    eligible face with every corner within `band` of the side's plane and within
    `PIECE_MAX_ANGLE_DEG` of parallel to it.

    The SIDE is judged at its own depth: the deepest point of the faces in the band that overlap
    `0 <= u <= L`, or `h_measured` when there are none. Not at `h_measured` alone, which comes
    from ANY side face touching an endpoint -- `two_level_slab`'s fin, perpendicular to its
    `y = 0` side at a shared corner, makes that whole 8 in side measure 200 in. `coverage` is the
    fraction of that rectangle the faces in the band cover, whichever edge they belong to: one
    side quad spanning two outline edges (a T-junction on its top edge) covers both.

    `built` holds the `(corners)` of every wall this run has already decided to build: one in
    the band covers this side like an original face does (never as a piece), so an outline two
    top regions share -- a duplicate layer of another material, split into many regions -- is
    walled once.

    A PIECE, which the wall replaces, is a face in the band with at least
    `_PIECE_INSIDE_FRACTION` of its own area inside the rectangle down to the deeper of the side
    and the wall; a face mostly outside it belongs to another edge, or is not part of this side
    at all (a railing standing in the band but reaching far above the top)."""
    t = pb - pa
    t[2] = 0.0
    length = float(np.linalg.norm(t))
    if length <= 1e-9:
        return [], 1.0, h_measured
    th = t / length
    reach = max(h_measured, h_wall) + band + 1.0
    lo = np.minimum(pa, pb) - band
    hi = np.maximum(pa, pb) + band
    lo[2] = min(pa[2], pb[2]) - reach
    hi[2] = max(pa[2], pb[2]) + band
    cand = faces.near(lo, hi)
    v = faces.tri[cand]
    s = (v - pa) @ q
    parallel = np.abs(faces.normal[cand] @ q) >= np.cos(np.radians(PIECE_MAX_ANGLE_DEG))
    cand = cand[(np.abs(s).max(axis=1) <= band) & parallel]
    corners = [faces.tri[f] for f in cand]
    is_face = [True] * len(cand)
    for quad in built or ():
        quad = np.asarray(quad, dtype=np.float64)
        n = np.cross(quad[1] - quad[0], quad[2] - quad[0])
        n = n / max(float(np.linalg.norm(n)), 1e-300)
        if (abs(float(n @ q)) >= np.cos(np.radians(PIECE_MAX_ANGLE_DEG))
                and float(np.abs((quad - pa) @ q).max()) <= band):
            corners.append(quad)
            is_face.append(False)
    if not corners:
        return [], 0.0, h_measured
    polys = []
    for v in corners:
        u = (v - pa) @ th
        z_edge = pa[2] + (pb[2] - pa[2]) * (u / length)
        polys.append(shapely.Polygon(np.stack([u, v[:, 2] - z_edge], axis=1)))
    polys = np.array(polys, dtype=object)
    is_face = np.array(is_face, dtype=bool)
    area = shapely.area(polys)
    strip = shapely.intersection(polys, shapely.box(0.0, -reach, length, band))
    own = (area > 0.0) & (shapely.area(strip) > 0.0)
    if not own.any():
        return [], 0.0, h_measured
    h_side = float(-shapely.bounds(strip[own])[:, 1].min())
    h_box = max(h_side, h_wall)
    inside = shapely.area(shapely.intersection(polys, shapely.box(0.0, -h_box, length, 0.0)))
    mine = (own & is_face & (inside >= _PIECE_INSIDE_FRACTION * area))[:len(cand)]
    pieces = [int(f) for f in cand[mine] if int(f) not in claimed]
    side = shapely.box(0.0, -h_side, length, 0.0)
    covered = shapely.area(shapely.intersection(shapely.union_all(polys[own]), side))
    return pieces, float(covered / max(side.area, 1e-12)), h_side


def _bottom_pieces(faces: _Faces, foot, normal, origin, bottom_h: float, band: float,
                   claimed: set) -> list[int]:
    """Eligible faces lying in the bottom's band: every corner within `band` of the bottom plane
    (the top plane lowered by `bottom_h`), within `PIECE_MAX_ANGLE_DEG` of parallel to it, closer
    to the bottom than to the top, with the centroid over the footprint."""
    x0, y0, x1, y1 = foot.bounds
    z = _z_top(normal, origin, np.array([x0, x1, x0, x1]), np.array([y0, y0, y1, y1]))
    lo = np.array([x0, y0, float(z.min()) - bottom_h - band])
    hi = np.array([x1, y1, float(z.max()) - bottom_h + band])
    cand = faces.near(lo, hi)
    if not len(cand):
        return []
    v = faces.tri[cand]
    top = _z_top(normal, origin, v[:, :, 0], v[:, :, 1])
    below_top = top - v[:, :, 2]                       # vertical depth under the top plane
    off = np.abs(below_top - bottom_h) * abs(float(normal[2]))
    parallel = np.abs(faces.normal[cand] @ normal) >= np.cos(np.radians(PIECE_MAX_ANGLE_DEG))
    nearer = np.abs(below_top - bottom_h).mean(axis=1) < np.abs(below_top).mean(axis=1)
    c = v.mean(axis=1)
    over = shapely.contains_xy(foot, c[:, 0], c[:, 1])
    mine = (off.max(axis=1) <= band) & parallel & nearer & over
    return [int(f) for f in cand[mine] if int(f) not in claimed]


def solidify(mesh: MeshData, topo: Topology, profile) -> SolidifyResult:
    """Build every missing or broken side and every missing bottom of every top-surface region of
    `mesh`, replace the broken pieces, then let the cap guard refuse whatever new face covers
    something a person can see outside the slab.

    `profile` is an `engine.fixes.pipeline.FixProfile` (duck-typed, so this module does not
    import the module that imports it). Deterministic: regions are visited in ascending id,
    outline edges in ring order, pieces in face order, and every tolerance comes from the mesh's
    own print precision or the profile.
    """
    started = time.perf_counter()
    tol = _depth_tol(topo, profile)
    radius = getattr(profile, "skirt_search_radius", 60.0)
    min_h = getattr(profile, "min_thickness", 2.0)
    max_h = getattr(profile, "max_thickness", 36.0)
    bottom_fraction = getattr(profile, "bottom_exists_fraction", 0.9)
    bottom_extra = getattr(profile, "bottom_search_extra", 24.0)
    guard_size = getattr(profile, "guard_size", (900, 600))
    top_min_nz = getattr(profile, "top_min_nz", 0.7)
    band = min(float(getattr(profile, "side_band", 2.5)), SIDE_BAND_MAX)

    ok_ids = np.nonzero(topo.ok)[0]
    caster = EmbreeCaster(topo.positions_w, topo.face_w[ok_ids])
    regions = top_regions(topo, profile, caster)
    normals = _face_normals(topo.positions_w, topo.face_w)

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
    top_faces = np.nonzero(np.isin(topo.face_region, regions))[0] if regions else np.zeros(0, int)
    faces = _Faces(topo, top_faces)
    claimed: set[int] = set()
    built_walls: list[np.ndarray] = []
    plans = []
    unmappable = 0
    edges_continued = 0
    sides_intact = 0
    open_edge_count = 0
    for region in regions:
        members = np.nonzero(topo.face_region == region)[0]
        outline = region_outline(topo, members)
        if outline is None:
            unmappable += 1
            continue
        pieces, normal, origin, basis = outline
        normal = normal if normal[2] > 0 else -normal
        rings = [ring for piece in pieces for ring in piece.rings]
        open_edge_count += len(_open_edges(topo, rings, index))
        foot = _footprint(topo, members)
        centroid = topo.positions_w[topo.face_w[members]].reshape(-1, 3).mean(axis=0)
        edges = [e for ring in rings for e in _ring_edges(ring)]
        frames = [(topo.positions_w[a], topo.positions_w[b],
                   _outward(foot, topo.positions_w[a], topo.positions_w[b], centroid))
                  for a, b in edges]
        real = [i for i, f in enumerate(frames) if f[2] is not None]
        continued = np.zeros(len(edges), bool)
        continued[real] = _continues(topo, ok_ids, caster, normals, [frames[i] for i in real],
                                     top_min_nz, 2.0 * tol)
        measured = _edge_thickness(topo, edges, sides, side_low, side_centroid, vertex_sides,
                                   radius)
        plans.append({"region": region, "members": members, "pieces": pieces, "normal": normal,
                      "origin": origin, "basis": basis, "foot": foot, "edges": edges,
                      "frames": frames, "continued": continued, "measured": measured})

    # the file-wide fallback height, from the edges that are sides at all
    file_wide = [t for plan in plans for t, c in zip(plan["measured"], plan["continued"])
                 if t is not None and not c]
    file_median = float(np.median(file_wide)) if file_wide else min_h

    def clamp(height: float) -> float:
        return float(min(max(height, min_h), max_h))

    builder = _Builder(mesh)
    welded_to_original = _welded_to_original(mesh, topo)
    replaced_group = np.full(mesh.n_faces, -1, np.int64)
    group_region: list[int] = []
    group_kind: list[str] = []
    group_length: list[float] = []
    volumes: dict[int, tuple] = {}
    report_thickness: dict[str, float] = {}
    report_bottom_depth: dict[str, float] = {}
    walls = 0
    wall_length = 0.0
    wall_fallback = 0
    bottoms = 0
    bottoms_refused = 0
    bottom_skips = {reason: 0 for reason in _BOTTOM_SKIPS}
    bottom_exists = 0
    unresolved_thickness = 0

    for plan in plans:
        members = plan["members"]
        region = plan["region"]
        side_edges = [i for i, c in enumerate(plan["continued"]) if not c
                      and plan["frames"][i][2] is not None]
        edges_continued += int(plan["continued"].sum())
        whole_heights = []
        to_build = []
        for i in side_edges:
            a, b = plan["edges"][i]
            pa, pb, q = plan["frames"][i]
            meas = plan["measured"][i]
            fallback_guess = clamp(meas) if meas is not None else file_median
            h_side = meas if meas is not None else fallback_guess
            found, coverage, depth = _wall_pieces(faces, pa.copy(), pb.copy(), q, h_side,
                                                  fallback_guess, band, claimed, built_walls)
            if coverage >= SIDE_WHOLE_FRACTION:
                sides_intact += 1
                whole_heights.append(clamp(depth))
                continue
            to_build.append((i, found))
        own = [clamp(plan["measured"][i]) for i, _f in to_build if plan["measured"][i] is not None]
        heights = own or whole_heights
        resolved = bool(heights) or bool(file_wide)
        # The region's FALLBACK height, for walls that could not be measured at all.
        h = clamp(float(np.median(heights)) if heights else file_median)
        # ...and the BOTTOM goes at the shallowest height any of its walls actually reached, so
        # it meets one of them instead of crossing the others.
        bottom_h = min(heights) if heights else h
        report_thickness[str(region)] = h
        report_bottom_depth[str(region)] = bottom_h
        material = int(mesh.face_material[members[0]])
        uv_scale = _uv_scale(mesh, topo, members, plan["origin"], plan["basis"])

        # keyed by (welded id, height): two edges of one region that measured different depths
        # need two different shifted vertices at the corner they share, and the vertical step
        # between their walls is the honest picture of a slab whose thickness really varies.
        shifted: dict[tuple[int, float], int] = {}

        def down(welded: int, height: float) -> int:
            key = (int(welded), float(height))
            if key not in shifted:
                p = topo.positions_w[welded] - np.array([0.0, 0.0, height])
                shifted[key] = builder.vertex(p)
            return shifted[key]

        for i, found in to_build:
            a, b = plan["edges"][i]
            pa, pb, q = plan["frames"][i]
            measured = plan["measured"][i]
            edge_h = clamp(measured) if measured is not None else h
            if measured is None:
                wall_fallback += 1
            group = len(group_region)
            group_region.append(region)
            group_kind.append("wall")
            length = float(np.linalg.norm(pb - pa))
            group_length.append(length)
            quad = [int(welded_to_original[a]), int(welded_to_original[b]),
                    down(b, edge_h), down(a, edge_h)]
            for triangle in _wound_outward(quad, builder.positions, q):
                builder.face(triangle, material, uv_scale, group)
            for f in found:
                if f not in claimed:            # a corner piece goes to the first wall
                    replaced_group[f] = group
                    claimed.add(f)
            built_walls.append(np.array([pa, pb, pb - [0.0, 0.0, edge_h],
                                         pa - [0.0, 0.0, edge_h]], dtype=np.float64))
            walls += 1
            wall_length += length

        # A bottom is only invented at a thickness that was MEASURED -- this region's own sides,
        # or the file-wide median of everyone else's. When nothing in the file resolved, `h` is
        # just `min_thickness`, and a floor at a made-up depth is pure invention.
        if not resolved:
            unresolved_thickness += 1
            continue
        exists, depth = _underside(topo, members, caster, bottom_h, tol, bottom_fraction,
                                   bottom_extra)
        if exists:
            bottom_exists += 1
            volumes[region] = (plan["foot"], plan["normal"], plan["origin"], depth)
            continue
        volumes[region] = (plan["foot"], plan["normal"], plan["origin"], bottom_h)
        group = len(group_region)
        added, part_skipped = _add_bottom(builder, topo, plan, lambda c: down(c, bottom_h),
                                           material, uv_scale, bottom_skips, group)
        if added:
            bottoms += 1
            group_region.append(region)
            group_kind.append("bottom")
            group_length.append(0.0)
            for f in _bottom_pieces(faces, plan["foot"], plan["normal"], plan["origin"],
                                    bottom_h, band, claimed):
                replaced_group[f] = group
                claimed.add(f)
        elif part_skipped:
            bottoms_refused += 1

    solid, new_faces, new_group = builder.build()
    cap_history: list = []
    cap_removed = 0
    detail = {"replaced": np.zeros(mesh.n_faces, bool), "interior_faces": [],
              "refused_reason": {}}
    out, out_new, keep = solid, new_faces, np.ones(solid.n_faces, bool)
    if new_faces.any():
        out, out_new, cap_history, cap_removed, detail, keep = _cap_guard(
            mesh, solid, new_faces, guard_size, getattr(profile, "n_dirs", 128),
            getattr(profile, "cover_max_exposure", 0.10),
            getattr(profile, "cap_guard_max_rounds", 8),
            replaced_group=replaced_group, new_group=new_group, side_band=band,
            volumes=volumes, group_region=np.asarray(group_region, np.int64))
    replaced = np.asarray(detail["replaced"], bool)

    # a group is kept whole when every one of its new faces survived the cap guard
    kept_groups = np.ones(len(group_region), bool)
    refused = new_faces & ~keep
    np.logical_and.at(kept_groups, new_group[new_faces], ~refused[new_faces])
    rebuilt = [g for g in range(len(group_region)) if group_kind[g] == "wall" and kept_groups[g]]
    wall_reasons: dict[str, int] = {}
    bottom_reasons: dict[str, int] = {}
    walls_refused_faces = bottom_faces_refused = 0
    for f, reason in sorted(detail["refused_reason"].items()):
        kind = group_kind[int(new_group[f])]
        target = wall_reasons if kind == "wall" else bottom_reasons
        target[reason] = target.get(reason, 0) + 1
        if kind == "wall":
            walls_refused_faces += 1
        else:
            bottom_faces_refused += 1

    hidden_before, hidden_after = _newly_hidden(mesh, out, topo, profile, replaced)
    report = {
        "regions_processed": len(plans),
        #: Outline edges of top surfaces the export left OPEN (edge count 1) -- what the first
        #: solidify walled. Informational since SR2, which walls what is missing or broken.
        "open_outline_edges": open_edge_count,
        #: Walls BUILT (one per outline edge whose side is missing or broken), before the cap
        #: guard judged them; `sides_rebuilt` is what it kept.
        "skirts_added": walls,
        "skirt_length_total": round(wall_length, 4),
        #: Walls whose own height could not be measured, and which therefore fell back to their
        #: region's median (or, with nothing in the file resolved, `min_thickness`).
        "skirt_edges_fallback": wall_fallback,
        #: SR2. Outline edges whose side is whole (its pieces cover it): nothing built.
        "sides_intact": sides_intact,
        #: SR2. Outline edges where the top continues into another top surface: not a side.
        "edges_continued": edges_continued,
        #: SR2. Walls the cap guard KEPT whole, and the outline length they close.
        "sides_rebuilt": {"edges": len(rebuilt),
                          "length": round(float(sum(group_length[g] for g in rebuilt)), 4)},
        #: SR2. Original faces REMOVED because a kept wall or bottom replaced them -- pieces of a
        #: broken side lying within `side_band` of its plane.
        "side_pieces_replaced": int(replaced.sum()),
        "side_pieces_replaced_by": {
            "walls": int(sum(1 for f in np.nonzero(replaced)[0]
                             if group_kind[int(replaced_group[f])] == "wall")),
            "bottoms": int(sum(1 for f in np.nonzero(replaced)[0]
                               if group_kind[int(replaced_group[f])] == "bottom"))},
        #: SR2. Pieces the guard gave back because removing them exposed something else.
        "side_pieces_restored": int(sum(1 for f in np.nonzero(replaced_group >= 0)[0]
                                        if not replaced[f] and kept_groups[replaced_group[f]])),
        #: SR2. Distinct original faces a kept closing face covers where they lie INSIDE a slab's
        #: volume (rule 5) -- the inside the hidden-face pass then removes.
        "interior_faces_covered": len(detail["interior_faces"]),
        #: SR2. New faces the cap guard refused, and why: what the failing pixels showed that
        #: lies outside every slab volume.
        "walls_refused": {"faces": walls_refused_faces, "reasons": wall_reasons},
        "bottom_faces_refused": {"faces": bottom_faces_refused, "reasons": bottom_reasons},
        "side_band": band,
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
        #: height any of its walls reached, not the median `thickness_per_region` holds.
        "bottom_depth_per_region": report_bottom_depth,
        "invented_vertices": int(len(out.positions) - len(mesh.positions)),
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
    return SolidifyResult(mesh=out, new_faces=out_new, report=report, replaced=replaced)


def _welded_to_original(mesh: MeshData, topo: Topology) -> np.ndarray:
    """Welded id -> the LOWEST original vertex index that welds to it, so a face this module
    emits indexes `mesh.positions` exactly like every other face does."""
    out = np.full(len(topo.positions_w), np.iinfo(np.int64).max, np.int64)
    np.minimum.at(out, topo.face_w.reshape(-1), mesh.face_v.reshape(-1).astype(np.int64))
    return out


def _underside(topo: Topology, members: np.ndarray, caster, h: float, tol: float,
               fraction: float, search_extra: float = 24.0) -> tuple[bool, float]:
    """`(exists, depth)`: a ray straight down from just below each of the region's face
    centroids; the region already has a bottom when at least `fraction` of them meet something
    within `h + search_extra + tol`, and `depth` is the MEDIAN depth below the top at which they
    met it -- the slab's measured underside, which bounds its volume (rule 5 of the cap guard).

    THE SEARCH REACHES PAST `h` DELIBERATELY. `h` is the SHALLOWEST height this region's own
    sides measured, and an underside deeper than that is still this slab's underside -- it is
    what a slab that is thicker in the middle than at its rim looks like. Stopping at `h + tol`
    declares such a region bottomless and invents a second bottom ABOVE the real one, boxing it
    in.

    Bounded rather than unbounded, because "anything at all below me" is not a bottom: a slab
    100 in above a floor does not have that floor for an underside."""
    centroid = topo.positions_w[topo.face_w[members]].mean(axis=1)
    origins = centroid - np.array([0.0, 0.0, EPS_IN])
    directions = np.tile(np.array([0.0, 0.0, -1.0]), (len(origins), 1))
    tri, t = caster.first_hit(origins, directions)
    found = (tri >= 0) & (t <= h + search_extra + tol)
    depth = float(np.median(t[found]) + EPS_IN) if found.any() else h
    return bool(found.mean() >= fraction), depth


def _has_bottom(topo: Topology, members: np.ndarray, caster, h: float, tol: float,
                 fraction: float, search_extra: float = 24.0) -> bool:
    """`_underside`'s verdict alone."""
    return _underside(topo, members, caster, h, tol, fraction, search_extra)[0]


def _add_bottom(builder: _Builder, topo: Topology, plan: dict, down, material: int,
                 uv_scale: float, skips: dict, group: int) -> tuple[bool, bool]:
    """The region's outline (outer plus inners), shifted down by the region's bottom depth and
    triangulated over the SHIFTED vertices with `shapely.constrained_delaunay_triangles`, which
    adds no Steiner points -- so every bottom corner is a vertex this function already made.
    Wound so the bottom faces DOWN.

    ALL OR NOTHING. Every triangle is worked out FIRST, and nothing is emitted unless all of them
    were. A bottom missing one of its parts is a HOLE in the underside, which is worse than no
    bottom at all: the rest of it still hides whatever is above, so the hidden pass deletes the
    real geometry and the hole is what ships. Each of the ways a part can be skipped is counted
    into `skips` (which the caller reports as `bottom_skips`).

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
        builder.face(ids, material, uv_scale, group)
    return True, False


def _interior_test(volumes: dict, new_group: np.ndarray, group_region: np.ndarray,
                   centre: np.ndarray):
    """The cap guard's rule 5, as `interior(new_face_ids, points_c) -> codes`. The guard hands
    it the point just IN FRONT of each covered hit (see `solidify_feedback`), so INSIDE means the
    covered face was reached through the inside of a slab.

    A point is INSIDE when it lies over the footprint of ANY top region whose slab depth is
    known, no higher than that region's top plane and no lower than its bottom depth -- a slab is
    often several top regions (one material each, or split at a T-junction; on file A region 11
    and region 9 are one slab at z 1612.2), and what lies inside one of them is inside the model.
    Otherwise the code says where the point is relative to the new face's OWN slab: outside its
    footprint, below its bottom, above its top, or that slab's depth was never measured."""
    order = sorted(volumes)

    def interior(face_ids: np.ndarray, points_c: np.ndarray) -> np.ndarray:
        points = np.asarray(points_c, dtype=np.float64) + centre
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        inside = np.zeros(len(points), bool)
        own_code = np.full(len(points), INTERIOR_UNMEASURED, np.int64)
        own_region = group_region[new_group[np.asarray(face_ids, dtype=np.int64)]]
        for region in order:
            foot, normal, origin, depth = volumes[region]
            over = shapely.contains_xy(foot, x, y)
            below_top = _z_top(normal, origin, x, y) - z
            inside |= over & (below_top >= 0.0) & (below_top <= depth)
            mine = own_region == region
            if mine.any():
                code = np.where(~over, INTERIOR_OUTSIDE_FOOTPRINT,
                                np.where(below_top < 0.0, INTERIOR_AT_OR_ABOVE_TOP,
                                         INTERIOR_BELOW_BOTTOM))
                own_code[mine] = code[mine]
        return np.where(inside, INTERIOR_INSIDE, own_code)

    return interior


def _cap_guard(original: MeshData, solid: MeshData, new_faces: np.ndarray,
                guard_size: tuple[int, int], n_dirs: int = 128,
                cover_max_exposure: float = 0.10, max_rounds: int = 8, *,
                replaced_group: np.ndarray | None = None, new_group: np.ndarray | None = None,
                side_band: float = 0.0, volumes: dict | None = None,
                group_region: np.ndarray | None = None):
    """Render the original and the solidified mesh over `VIEWS_26` and drop every new face the
    cap rule refuses, and every original face a kept closing face replaces (see
    `engine.guard.compare.solidify_feedback`). Returns
    `(mesh, new_faces, history, removed, detail, keep)`, `keep` over `solid`'s faces.

    The exposure the cap rule reads is measured on the ORIGINAL geometry -- `faces_before`
    alone, cast against itself -- because a face that some invented face is covering has, by
    construction, exposure 0 in the solidified mesh, and a rule that read that would authorise
    itself.

    `ok` is deliberately all-True here: a RELATIVELY degenerate face
    (`engine.topo.adjacency.degenerate_mask` allows `area <= 1e-7 * longest**2`) is real,
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

    interior = None
    if volumes and new_group is not None and group_region is not None and len(group_region):
        interior = _interior_test(volumes, np.asarray(new_group, np.int64),
                                  np.asarray(group_region, np.int64), centre)
    keep, history, detail = solidify_feedback(
        positions_c, faces_before, faces_after, new_faces, front,
        cover_max_exposure=cover_max_exposure, views=VIEWS_26, size=guard_size,
        max_rounds=max_rounds, replaced_group=replaced_group, new_group=new_group,
        side_band=side_band, interior=interior)
    removed = int((~keep & new_faces).sum())
    if keep.all():
        return solid, new_faces, history, 0, detail, keep
    out = replace(solid, face_v=solid.face_v[keep], face_vt=solid.face_vt[keep],
                  face_vn=solid.face_vn[keep], face_material=solid.face_material[keep],
                  face_line=solid.face_line[keep])
    return out, new_faces[keep], history, removed, detail, keep


def _newly_hidden(original: MeshData, solid: MeshData, topo: Topology, profile,
                  replaced: np.ndarray) -> tuple[int, int]:
    """How many of the ORIGINAL faces that are still in `solid` (every one not `replaced`) have
    exposure 0 before and after -- the number this whole step exists to move.

    Both counts are over those same surviving original faces, and that is the only thing they
    have in common: `before` is measured against the original geometry ALONE and `after` against
    the whole SOLIDIFIED mesh. The difference is exactly what the invented faces (and the pieces
    they replaced) did to visibility, which is the question."""
    from engine.topo.weld import weld_exact

    n_dirs = getattr(profile, "n_dirs", 128)
    positions_w, remap = weld_exact(solid.positions, solid.coord_decimals)
    centre = (positions_w.min(axis=0) + positions_w.max(axis=0)) / 2.0
    positions_c = positions_w - centre
    survivors = ~np.asarray(replaced, bool)
    ok = topo.ok
    faces_original = remap[original.face_v]
    before = compute_exposure(positions_c, faces_original, ok, n_dirs=n_dirs)
    n_kept = int(survivors.sum())
    faces_after = remap[solid.face_v]
    ok_after = np.append(ok[survivors], np.ones(solid.n_faces - n_kept, bool))
    after = compute_exposure(positions_c, faces_after, ok_after, n_dirs=n_dirs)[:n_kept]
    return (int(((before <= 0.0) & ok & survivors).sum()),
            int(((after <= 0.0) & ok[survivors]).sum()))
