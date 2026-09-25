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
   volume still may never be covered -- except, since brief 10 item 1, what was seen THROUGH a
   slab whose new shell is kept on both sides of the ray (rule 6): a slab's walls and bottom are
   judged together, not each against a mesh that lacks the others.

THICKNESS IS MEASURED PER EDGE, not per region. A real skirt on file A varies from 1.3 to 49 in, so
one height for a whole region hangs the shallow side of it far below the slab. Each wall is
extruded to ITS edge's resolved height: the SHALLOWEST of the slab's OWN sides -- side faces
hanging from its outline -- at the edge's ends or along it (review I1; the deepest side face at
either end, own or not, boxed a 2 in slab touching a 30 in wall to 30 in). The region's median is
the fallback for an edge that resolves to nothing, counted as `skirt_edges_fallback`. Whether a
side is whole is judged at its UNCLAMPED measured height: a 1.3 in skirt is a whole 1.3 in side,
not a broken 2 in one.

A THIN LIP NEVER SETS A SLAB'S BOTTOM (SR6 item 2). An own side is measured by how far it reaches
BELOW the edge it lies along -- a riser standing up from the outline reaches nothing -- and the
slab's REPRESENTATIVE depth is the depth down to which at least half of its own side length goes
(`_representative_depth`). The bottom goes no deeper than that; an own side shallower than it (a
lip, trim or fascia band) measures no edge's height, and is not a whole side either: the side
below it is missing and is completed. SR5 capped the bottom at the shallowest own face instead,
which put file B's ramp bottom 5.62 in down, its landing's 0.26 in, and file A's lower landing's
9.85 in -- every one a lip or a riser, inside a slab 29.52 to 39.37 in deep.

A SLOPED TOP'S WALLS FOLLOW THE GROUND (SR6 item 1). When a slab has a LOWER SURFACE -- rays
straight down from its top meet one, within reach of its representative depth, and no deeper than
its own sides go (`_lower_surface`) -- every wall under its outline goes down to that surface at
EACH end: a trapezoid under a sloped edge over a flat underside, a parallelogram over a parallel
one. File B's ramp is 39.37 in thick everywhere, its underside parallel to its top; its walls had
stopped at one clamped 36 in, and the pieces of its broken side, 28 to 39.4 in down, were not
taken because they did not reach the top edge. A piece is now any face in the band mostly inside
the wall, and such a slab has its bottom: none is invented.

THE SLAB VOLUME, which rule 5 of the cap guard reads, is the region's footprint from its top down
to its bottom depth: its lower surface when it has one (following that surface's plane), else
`bottom_h` (the SHALLOWEST measured wall, where the bottom goes) when a bottom is built, and the
MEASURED depth of the underside it already has otherwise. A wall hanging deeper than that is a fin
below the slab, and what it covers there is outside.

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
#: file B, and beyond 3 in there are only 7 (A) and 15 (B) pixels of noise. A band wider than
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


def _own_side_rows(topo: Topology, rings: list[np.ndarray], sides: np.ndarray,
                   tol: float) -> tuple[set[int], dict[tuple[int, int], list[int]]]:
    """`(own, along)`: the rows of `sides` that HANG FROM THIS REGION'S OUTLINE -- one of their
    edges lies along an outline edge (every end within `tol` of its line, overlapping the edge by
    more than `tol`), which is how a side shares an edge with the region or starts at its top
    through a T-junction -- and, per outline edge `(a, b)`, the rows lying along that edge itself.

    Review I1: a side face that merely TOUCHES a corner of the outline -- a retaining wall
    running away from a thin slab, a fin -- is not this slab's side and measures nothing."""
    own: set[int] = set()
    along: dict[tuple[int, int], list[int]] = {}
    if not len(sides):
        return own, along
    P = topo.positions_w
    tri = P[topo.face_w[sides]]
    lo, hi = tri.min(axis=1), tri.max(axis=1)
    for ring in rings:
        for a, b in _ring_edges(ring):
            pa, pb = P[a], P[b]
            seg = pb - pa
            length = float(np.linalg.norm(seg))
            if length <= 1e-9:
                continue
            d = seg / length
            near = ((hi >= np.minimum(pa, pb) - tol) & (lo <= np.maximum(pa, pb) + tol)).all(axis=1)
            rows = []
            for row in np.nonzero(near)[0]:
                v = tri[row]
                for i, j in ((0, 1), (1, 2), (2, 0)):
                    u, w = v[i] - pa, v[j] - pa
                    if (np.linalg.norm(np.cross(u, d)) > tol
                            or np.linalg.norm(np.cross(w, d)) > tol):
                        continue
                    tu, tw = float(u @ d), float(w @ d)
                    if min(max(tu, tw), length) - max(min(tu, tw), 0.0) > tol:
                        rows.append(int(row))
                        break
            along[(int(a), int(b))] = rows
            own.update(rows)
    return own, along


def _own_side_depths(topo: Topology, along: dict, sides: np.ndarray, tol: float
                     ) -> tuple[dict[int, float], list[tuple[float, float]]]:
    """`(row_depth, runs)` of a region's own sides (`_own_side_rows`' `along`). `row_depth` is,
    per own row, how far BELOW the outline edge it lies along it reaches -- under the edge's own
    height at each corner, so a sloped edge is measured where each corner lies along it. `runs`
    holds `(depth, run)` per row and edge it lies along, `run` being the length it covers of that
    edge, for every row reaching deeper than `tol`.

    SR6 item 2. SR5 measured an own side by its vertical EXTENT, so a face standing UP from the
    outline -- the riser of the step to the next landing -- counted as a side as tall as itself:
    every one of the shallow "sides" that capped file A's lower landing (region 11) at 9.85 in is
    such a riser, 0.0 in below its edge. A side of this slab is what hangs BELOW its top."""
    P = topo.positions_w
    row_depth: dict[int, float] = {}
    runs: list[tuple[float, float]] = []
    for (a, b), rows in along.items():
        pa, pb = P[a], P[b]
        t = pb - pa
        t[2] = 0.0
        length = float(np.linalg.norm(t))
        if length <= 1e-9:
            continue
        th = t / length
        for row in rows:
            tri = P[topo.face_w[sides[row]]]
            u = np.clip((tri - pa) @ th, 0.0, length)
            depth = float((pa[2] + (pb[2] - pa[2]) * (u / length) - tri[:, 2]).max())
            row_depth[row] = max(row_depth.get(row, -np.inf), depth)
            run = float(u.max() - u.min())
            if depth > tol and run > 0.0:
                runs.append((depth, run))
    return row_depth, runs


def _is_underside(topo: Topology, members: np.ndarray, edges: list[tuple[int, int]],
                  continued: np.ndarray, along: dict, sides: np.ndarray, sky: set, caster,
                  ok_ids: np.ndarray, min_body: float, reach: float) -> bool:
    """Review part 2, C2 (brief 10 item 3): is a region a top runs into, which sees no sky itself,
    the UNDERSIDE of a slab above it -- decided by looking below it AND above it:

    1. BELOW: no slab body hangs from it -- no own side reaches at least `min_body` (the thinnest
       slab the engine builds) below one of its edges it does NOT continue across. A side along
       an edge the top continues across is the neighbour's: file A's region 33 and the review's
       overhang each had one (29.6 in, 8 in), and SR6's test, which counted every own side, took
       them for tops. Measured on file A, the real tops under the upper landing (regions 9 and
       784) hang 29.52 in from such edges, and the slivers beside undersides 1.1 to 1.21 in.
    2. ABOVE: the slab it belongs to is there -- at least `TOP_SKY_FRACTION` of the rays straight
       up from it (four per face, as `_lower_surface` samples) meet a sky-seeing surface within
       `reach` (`max_thickness` plus the side band: no slab is thicker). A floor under a landing
       meets the landing's own underside instead (review M2, which SR6's test -- every own side
       standing up -- took for an underside).

    Why not SR6's test alone: a slab's underside with a neighbour's side hanging along it passed
    for a top, got a bottom invented under it, and the hidden pass deleted it (file A's region
    33: all 16 faces, 19,777 sq in, visible on the input)."""
    P = topo.positions_w
    for i, (a, b) in enumerate(edges):
        rows = along.get((int(a), int(b)), [])
        if continued[i] or not rows:
            continue
        pa, pb = P[a], P[b]
        t = pb - pa
        t[2] = 0.0
        length = float(np.linalg.norm(t))
        if length <= 1e-9:
            continue
        th = t / length
        for row in rows:
            tri = P[topo.face_w[sides[row]]]
            u = np.clip((tri - pa) @ th, 0.0, length)
            if float((pa[2] + (pb[2] - pa[2]) * (u / length) - tri[:, 2]).max()) >= min_body:
                return False
    tri = P[topo.face_w[members]]
    centroid = tri.mean(axis=1)
    samples = np.concatenate([centroid] + [(centroid + tri[:, k]) / 2.0 for k in range(3)])
    hit, t = caster.first_hit(samples + np.array([0.0, 0.0, EPS_IN]),
                              np.tile(np.array([0.0, 0.0, 1.0]), (len(samples), 1)))
    near = (hit >= 0) & (t <= reach)
    above = topo.face_region[ok_ids[hit[near]]]
    return bool(np.isin(above, sorted(sky)).sum() >= TOP_SKY_FRACTION * len(samples))


def _representative_depth(runs: list[tuple[float, float]]) -> float | None:
    """SR6 item 2. The depth a slab's own sides REPRESENTATIVELY reach: the length-weighted
    (lower) median of `_own_side_depths`' runs -- the shallowest depth down to which at least
    half of the slab's own side length goes. `None` without any own side.

    Why the median of the LENGTH: a lip, trim or fascia band is short. Measured: file B's ramp
    (region 309) has 804.1 in of own side reaching below its edges, 5.62 to 39.37 in deep, the
    5.62 in lip running 13.1 in of it (representative 33.74 in); its landing (region 92) 1,452.3
    in, the 0.26 in lip running 29.5 in (representative 39.37 in); file A's lower landing (region
    11) 1,152.9 in, all of it 29.52 in -- the 15 of its 44 own faces that capped it at 9.85 in are
    risers. SR5's shallowest side set all three bottoms at the lip or the riser; it lay below the
    representative depth in 38 regions of file B and 56 of file A. A tie goes to the shallower
    depth: `slab_with_two_depths`, half 1.3 in and half 9.8 in, keeps S-I5's bottom at 1.3 in."""
    if not runs:
        return None
    depth = np.array([r[0] for r in runs], dtype=np.float64)
    run = np.array([r[1] for r in runs], dtype=np.float64)
    order = np.argsort(depth, kind="stable")
    cumulative = np.cumsum(run[order])
    k = int(np.searchsorted(cumulative, 0.5 * cumulative[-1], side="left"))
    return float(depth[order][min(k, len(order) - 1)])


def _edge_thickness(topo: Topology, edges, own: set[int], along: dict, side_low: np.ndarray,
                    vertex_sides: dict, row_depth: dict | None = None,
                    lip_below: float | None = None) -> list[float | None]:
    """Per edge, IN `edges` ORDER, `top z - lowest z` of the SHALLOWEST of this region's own
    sides (`_own_side_rows`) that reach it -- at either endpoint, or lying along the edge -- or
    `None` when none does.

    Review I1: this used to take the DEEPEST side face at either endpoint, own or not, with a
    radius search as a fallback, so a 2 in slab whose corner touched a 30 in retaining wall was
    boxed to 30 in with every guard passing. An edge nothing of the slab's own reaches falls
    back to its region's median, as before; nothing outside the slab is consulted.

    SR6 item 2: an own side reaching less than `lip_below` below its edge (`row_depth`) -- a lip,
    trim or fascia band shallower than the slab's representative depth -- measures nothing. On
    file B's ramp the 7.87 in lip along one broken edge made its wall 7.87 in, and the bottom,
    which goes at the shallowest wall, followed it.

    One entry per edge, `None` included: the caller extrudes each edge to ITS OWN height and
    needs to know which ones it could not measure."""
    out: list[float | None] = []
    for a, b in edges:
        top_z = float(max(topo.positions_w[a][2], topo.positions_w[b][2]))
        rows = ((vertex_sides.get(a, set()) | vertex_sides.get(b, set())) & own)
        rows |= set(along.get((int(a), int(b)), []))
        if lip_below is not None and row_depth is not None:
            rows = {r for r in rows if row_depth.get(r, np.inf) >= lip_below}
        depths = [top_z - float(side_low[r]) for r in sorted(rows)]
        depths = [d for d in depths if d > 0.0]
        out.append(min(depths) if depths else None)
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
        """Append one invented triangle. Its UVs project its corners onto its own plane's basis,
        measured from ONE origin for every face (the model's own origin), scaled by the region's
        inches-to-UV scale: every invented face in one plane then follows one texture map, so a
        textured material's plane keeps them in one UV class (`engine.topo.planes.cluster_uv`)
        and the merge can rebuild them as one polygon. Projected from each triangle's own first
        corner, as it used to be, no two of them shared a map and every edge of a new bottom was
        drawn."""
        points = np.array([self.positions[i] for i in ids], dtype=np.float64)
        vt = [-1, -1, -1]
        if uv_scale > 0.0:
            normal = np.cross(points[1] - points[0], points[2] - points[0])
            length = float(np.linalg.norm(normal))
            if length > 0.0:
                e1, e2 = plane_basis(normal / length)
                xy = points @ np.stack([e1, e2], axis=1) * uv_scale
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
               tol: float) -> tuple[np.ndarray, list[set]]:
    """Per edge `(pa, pb, outward)`: does the top surface CONTINUE across it -- another top-like
    face just outside whose plane passes through the edge? Probed at `_PROBE_FRACTIONS` along
    the edge, `_PROBE_OUT` outside it, straight down from an inch above; a majority decides.
    Such an edge is where two top regions of one slab meet, and has no side at all. Returns the
    verdicts and, per edge, the faces the agreeing probes met -- the surface the top continues
    into, which `solidify` then treats as part of the same top."""
    if not edges:
        return np.zeros(0, bool), []
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
    k = len(_PROBE_FRACTIONS)
    verdict = ok.reshape(len(edges), k).sum(axis=1) * 2 > k
    met = [set(face[i * k:(i + 1) * k][ok[i * k:(i + 1) * k]].tolist()) if verdict[i] else set()
           for i in range(len(edges))]
    return verdict, met


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
                 claimed: set, built: list | None = None, max_depth: float = 0.0,
                 min_side: float = 0.0, h_ends: tuple[float, float] | None = None
                 ) -> tuple[list[int], float, float | None]:
    """`(pieces, coverage, depth)` of the side under edge `pa -> pb` (outward `q`). `depth` is
    the side's measured depth, from ORIGINAL faces only, or `None` when no original face hangs
    from the edge -- a side that is whole only because this run already walled a coincident edge
    measures nothing, and must not set a bottom's depth.

    In the side's own frame -- `u` along the edge, `v` the height below the top edge, so a
    sloped edge's side is still a rectangle `[0, L] x [-h, 0]` -- a face IN THE BAND is an
    eligible face with every corner within `band` of the side's plane and within
    `PIECE_MAX_ANGLE_DEG` of parallel to it.

    The SIDE is judged at its own depth: what HANGS FROM THE TOP EDGE -- the connected part of
    the band's faces over `0 <= u <= L` that reaches up to the edge -- searched down to the
    deepest of `h_measured`, `h_wall` and `max_depth` (the profile's `max_thickness`), or
    `h_measured` when nothing hangs there. Not `h_measured` alone, which comes from ANY side face
    touching an endpoint: `two_level_slab`'s fin, perpendicular to its `y = 0` side at a shared
    corner, makes that whole 8 in side measure 200 in, and on file A (region 11) an edge measured
    11.72 in from its endpoints while the side face in its plane goes 29.52 in deep. Nor a search
    window cut off at `h_measured`: that reported the cut-off (15.22 in) as the side's depth, and
    the bottom went 14.3 in above the slab's real partial bottom. A separate wall further down
    the same plane, below a gap, is not part of the side. `coverage` is the fraction of the
    side's rectangle the faces in the band cover, whichever edge they belong to: one side quad
    spanning two outline edges (a T-junction on its top edge) covers both.

    `built` holds the `(corners)` of every wall this run has already decided to build: one in
    the band covers this side like an original face does (never as a piece), so an outline two
    top regions share -- a duplicate layer of another material, split into many regions -- is
    walled once.

    A PIECE, which the wall replaces, is a face in the band with at least
    `_PIECE_INSIDE_FRACTION` of its own area inside the rectangle down to the deeper of the side
    and the wall; a face mostly outside it belongs to another edge, or is not part of this side
    at all (a railing standing in the band but reaching far above the top).

    SR6 item 2: a side is whole only down to at least `min_side` -- the slab's representative
    depth, less the depth tolerance. A band shallower than that is a lip, trim or fascia over a
    side that is missing below it, and is completed like any broken side.

    SR6 item 1: when the slab has a lower surface, `h_ends` are its depths below `pa` and `pb`,
    and the side is judged -- and its pieces taken -- over the TRAPEZOID from the top edge down to
    that surface, not over a rectangle. And a piece no longer has to hang from the top edge: on
    file B's ramp the broken side along an 85 in edge is only its lower part, 28 to 39.4 in down,
    and taken as nothing it lay under the new wall, which the coincidence test then refused."""
    t = pb - pa
    t[2] = 0.0
    length = float(np.linalg.norm(t))
    if length <= 1e-9:
        return [], 1.0, None
    th = t / length
    reach = max(h_measured, h_wall, max_depth, *(h_ends or ())) + band + 1.0
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
        return [], 0.0, None
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
        return [], 0.0, None
    top = shapely.box(0.0, -band, length, band)

    def hanging_depth(mask):
        if not mask.any():
            return None
        union = shapely.union_all(strip[mask])
        hanging = [g for g in getattr(union, "geoms", [union]) if g.intersects(top)]
        return float(max(-g.bounds[1] for g in hanging)) if hanging else None

    h_side = hanging_depth(own)
    measured = hanging_depth(own & is_face)
    if h_ends is not None:
        # down to the lower surface at each end, or to what hangs from the edge if deeper
        hang = h_side or 0.0
        window = shapely.Polygon([(0.0, 0.0), (length, 0.0), (length, -max(h_ends[1], hang)),
                                  (0.0, -max(h_ends[0], hang))])
        side = shapely.Polygon([(0.0, 0.0), (length, 0.0), (length, -h_ends[1]),
                                (0.0, -h_ends[0])])
    else:
        window = shapely.box(0.0, -max(h_side or 0.0, h_wall), length, 0.0)
        side = (None if h_side is None
                else shapely.box(0.0, -max(h_side, min_side), length, 0.0))
    inside = shapely.area(shapely.intersection(polys, window))
    mine = (own & is_face & (inside >= _PIECE_INSIDE_FRACTION * area))[:len(cand)]
    pieces = [int(f) for f in cand[mine] if int(f) not in claimed]
    if side is None:
        return pieces, 0.0, None
    covered = shapely.area(shapely.intersection(shapely.union_all(polys[own]), side))
    return pieces, float(covered / max(side.area, 1e-12)), measured


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
    min_h = getattr(profile, "min_thickness", 2.0)
    max_h = getattr(profile, "max_thickness", 50.0)
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
    side_top = (topo.positions_w[topo.face_w[sides]][:, :, 2].max(axis=1) if len(sides)
                else np.zeros(0))
    vertex_sides: dict[int, set] = {}
    for row, face in enumerate(sides):
        for v in topo.face_w[face]:
            vertex_sides.setdefault(int(v), set()).add(row)

    index = _edge_index(topo)
    claimed: set[int] = set()
    built_walls: list[np.ndarray] = []
    plans = []
    unmappable = 0
    edges_continued = 0
    sides_intact = 0
    open_edge_count = 0
    # A surface a top CONTINUES into is part of that top, whether or not it sees sky: on file A
    # the lower landing's top runs on under the upper landing (regions 784 and 9), and a slab
    # volume that stopped at the sky's edge counted the inside of that slab as OUTSIDE. The
    # continued regions are processed as tops too, breadth first after the sky-seeing ones --
    # a region must be flat enough (`|n_z| > top_min_nz` on every face) to be one.
    top_like = {int(r) for r in np.unique(topo.face_region[topo.face_region >= 0])
                if (np.abs(normals[topo.face_region == r][:, 2]) > top_min_nz).all()}
    queue = list(regions)
    queued = set(regions)
    sky = set(regions)
    not_tops: set[int] = set()
    continued_tops = 0
    while queue:
        region = queue.pop(0)
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
        own, along = _own_side_rows(topo, rings, sides, 2.0 * tol)
        # SR6 item 2: own sides are measured BELOW their edge (a riser standing up measures 0),
        # and the slab's representative depth is what most of their length reaches; a lip
        # shallower than that measures no edge's height and caps no bottom
        row_depth, runs = _own_side_depths(topo, along, sides, tol)
        continued = np.zeros(len(edges), bool)
        verdict, met = _continues(topo, ok_ids, caster, normals, [frames[i] for i in real],
                                  top_min_nz, 2.0 * tol)
        continued[real] = verdict
        met_regions = {i: {int(topo.face_region[f]) for f in faces_met}
                       for i, faces_met in zip(real, met) if faces_met}
        into = sorted({int(topo.face_region[f]) for faces_met in met for f in faces_met}
                      & top_like - queued)
        for other in into:
            queued.add(other)
            queue.append(other)
            continued_tops += 1
        # SR6 item 3, review part 2 C2: a region a top runs into, which sees no sky itself, may
        # be a slab's UNDERSIDE, met in its plane by a top's edge. Taken for a top, it gets a
        # bottom invented under it, which the cap guard lets through (it reads the space under
        # the "top" as the slab's inside) and which hides the real underside for the hidden pass
        # to delete. Whether it is one is decided by looking below and above it (`_is_underside`),
        # not by which way its own sides run. It is not planned -- but the search goes on through
        # it, as it did, so the tops beyond it are still found.
        if region not in sky and _is_underside(topo, members, edges, continued, along, sides,
                                               sky, caster, ok_ids, min_h, max_h + band):
            not_tops.add(region)
            continue
        rep = _representative_depth(runs)
        measured = _edge_thickness(topo, edges, own, along, side_low, vertex_sides, row_depth,
                                   None if rep is None else rep - tol)
        own_depths = sorted(d for d in row_depth.values() if d > tol)
        plans.append({"region": region, "members": members, "pieces": pieces, "normal": normal,
                      "origin": origin, "basis": basis, "foot": foot, "edges": edges,
                      "frames": frames, "continued": continued, "measured": measured,
                      "own_depths": own_depths, "rep": rep, "met_regions": met_regions})

    # ...and an edge whose top ran on only into undersides does not continue at all: it is a
    # side, walled like any other (the plate beside the box in `slab_beside_a_lower_top`)
    for plan in plans:
        for i, into_regions in plan["met_regions"].items():
            if plan["continued"][i] and into_regions <= not_tops:
                plan["continued"][i] = False

    top_faces = np.nonzero(np.isin(topo.face_region, sorted(queued - not_tops)))[0]
    faces = _Faces(topo, top_faces)

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
    report_rep: dict[str, float | None] = {}
    walls = 0
    wall_length = 0.0
    wall_fallback = 0
    bottoms = 0
    bottoms_refused = 0
    bottom_skips = {reason: 0 for reason in _BOTTOM_SKIPS}
    bottom_exists = 0
    unresolved_thickness = 0
    deeper: list[dict] = []
    lower_regions = 0
    lower_walls = 0
    trapezoids = 0

    for plan in plans:
        members = plan["members"]
        region = plan["region"]
        side_edges = [i for i, c in enumerate(plan["continued"]) if not c
                      and plan["frames"][i][2] is not None]
        edges_continued += int(plan["continued"].sum())
        whole_heights = []
        whole_depths: list[float] = []
        # every side's depth as `_wall_pieces` measured it -- what hangs from its top edge, whole
        # or broken -- which bounds how deep this slab's existing bottom may lie (`_underside`)
        side_depths: list[float] = []
        to_build = []
        rep = plan["rep"]
        report_rep[str(region)] = None if rep is None else round(float(rep), 4)
        # SR6 item 1: the slab's LOWER SURFACE, searched as far as a bottom is (from the
        # representative depth, `bottom_search_extra` further), and only if its own sides reach it
        lower = None
        reach = (rep if rep is not None else 0.0) + bottom_extra + tol
        if rep is not None and plan["own_depths"]:
            lower = _lower_surface(topo, members, caster, ok_ids, normals, reach,
                                   bottom_fraction, max(plan["own_depths"]), band, top_min_nz,
                                   plan["normal"], plan["origin"])

        def ends_of(pa: np.ndarray, pb: np.ndarray) -> tuple[float, float] | None:
            """The wall's depth below each end, down to the lower surface there."""
            if lower is None:
                return None
            coef = lower[0]
            return tuple(float(min(max(p[2] - (coef[0] * p[0] + coef[1] * p[1] + coef[2]),
                                       min_h), reach)) for p in (pa, pb))

        for i in side_edges:
            a, b = plan["edges"][i]
            pa, pb, q = plan["frames"][i]
            meas = plan["measured"][i]
            fallback_guess = clamp(meas) if meas is not None else file_median
            h_side = meas if meas is not None else fallback_guess
            ends = ends_of(pa, pb)
            found, coverage, depth = _wall_pieces(faces, pa.copy(), pb.copy(), q, h_side,
                                                  fallback_guess, band, claimed, built_walls,
                                                  max_depth=max_h,
                                                  min_side=0.0 if rep is None else rep - tol,
                                                  h_ends=ends)
            if depth is not None:
                side_depths.append(float(depth))
            if coverage >= SIDE_WHOLE_FRACTION:
                sides_intact += 1
                if depth is not None:
                    whole_heights.append(clamp(depth))
                    whole_depths.append(float(depth))
                continue
            to_build.append((i, found, ends))
        own = [clamp(plan["measured"][i]) for i, _f, _e in to_build
               if plan["measured"][i] is not None]
        heights = own or whole_heights
        resolved = bool(heights) or bool(file_wide)
        # The region's FALLBACK height, for walls that could not be measured at all.
        h = clamp(float(np.median(heights)) if heights else file_median)
        # ...and the BOTTOM goes at the shallowest height any of its walls actually reached, so
        # it meets one of them instead of crossing the others -- and never deeper than the
        # slab's representative side depth (SR6 item 2; review I1 capped it at the shallowest
        # own side, which a lip or a riser set).
        bottom_h = min(heights) if heights else h
        if rep is not None:
            bottom_h = min(bottom_h, rep)
        existing = plan["own_depths"] + [d for d in whole_depths]
        wall_heights: list[float] = []
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

        for i, found, ends in to_build:
            a, b = plan["edges"][i]
            pa, pb, q = plan["frames"][i]
            measured = plan["measured"][i]
            edge_h = clamp(measured) if measured is not None else h
            if ends is not None:
                # SR6 item 1: down to the lower surface at EACH end -- a trapezoid under a
                # sloped edge over a flat underside, a parallelogram over a parallel one
                h_a, h_b = ends
                lower_walls += 1
                trapezoids += int(abs(h_a - h_b) > tol)
            else:
                if measured is None:
                    wall_fallback += 1
                h_a = h_b = edge_h
            wall_heights.append(max(h_a, h_b))
            group = len(group_region)
            group_region.append(region)
            group_kind.append("wall")
            length = float(np.linalg.norm(pb - pa))
            group_length.append(length)
            quad = [int(welded_to_original[a]), int(welded_to_original[b]),
                    down(b, h_b), down(a, h_a)]
            for triangle in _wound_outward(quad, builder.positions, q):
                builder.face(triangle, material, uv_scale, group)
            for f in found:
                if f not in claimed:            # a corner piece goes to the first wall
                    replaced_group[f] = group
                    claimed.add(f)
            built_walls.append(np.array([pa, pb, pb - [0.0, 0.0, h_b],
                                         pa - [0.0, 0.0, h_a]], dtype=np.float64))
            walls += 1
            wall_length += length

        if existing and ((wall_heights and max(wall_heights) > min(existing) + tol)
                         or bottom_h > min(existing) + tol):
            deeper.append({"region": int(region), "shallowest_side": round(min(existing), 4),
                           "representative_side": None if rep is None else round(float(rep), 4),
                           "deepest_side": round(max(existing), 4),
                           "deepest_wall": round(max(wall_heights), 4) if wall_heights else None,
                           "bottom": round(float(bottom_h), 4)})

        # SR6 item 1: a slab with a lower surface HAS its bottom, and its volume follows it
        if lower is not None:
            lower_regions += 1
            bottom_exists += 1
            report_bottom_depth[str(region)] = round(float(lower[1]), 4)
            volumes[region] = (plan["foot"], plan["normal"], plan["origin"], lower[1], lower[0])
            continue
        # A bottom is only invented at a thickness that was MEASURED -- this region's own sides,
        # or the file-wide median of everyone else's. When nothing in the file resolved, `h` is
        # just `min_thickness`, and a floor at a made-up depth is pure invention.
        if not resolved:
            unresolved_thickness += 1
            continue
        sides_reach = plan["own_depths"] + side_depths
        exists, depth = _underside(topo, members, caster, bottom_h, tol, bottom_fraction,
                                   bottom_extra, max(sides_reach) if sides_reach else None, band)
        if exists:
            bottom_exists += 1
            volumes[region] = (plan["foot"], plan["normal"], plan["origin"], depth, None)
            continue
        volumes[region] = (plan["foot"], plan["normal"], plan["origin"], bottom_h, None)
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
        # SR4: a BOTTOM's faces may not take a parallel face as "interior"; the tops of every
        # slab processed here are the shell being closed; and a new face lying on an existing
        # face is refused before any pixel is judged
        kinds = np.array(group_kind + [""], dtype=object)
        parallel_ok = ~(new_faces & (kinds[np.where(new_faces, new_group, -1)] == "bottom"))
        shell_faces = np.zeros(mesh.n_faces, bool)
        shell_faces[top_faces] = True
        coincident = _coincident_new_faces(solid, new_faces, new_group, replaced_group,
                                           topo.ok, tol)
        out, out_new, cap_history, cap_removed, detail, keep = _cap_guard(
            mesh, solid, new_faces, guard_size, getattr(profile, "n_dirs", 128),
            getattr(profile, "cover_max_exposure", 0.10),
            getattr(profile, "cap_guard_max_rounds", 8),
            replaced_group=replaced_group, new_group=new_group, side_band=band,
            volumes=volumes, group_region=np.asarray(group_region, np.int64),
            parallel_interior_ok=parallel_ok, shell_faces=shell_faces,
            refused_before=coincident,
            piece_cover=_bottom_piece_cover(solid, new_group, replaced_group, group_kind),
            on_pieces=_new_faces_on_pieces(solid, new_faces, replaced_group, tol))
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
        #: SR2. Regions processed as tops because a top continues into them, though they see
        #: no sky (a floor running on under an upper landing): part of the same slab. Counted
        #: when queued; `undersides_not_tops` of them were then found to be undersides.
        "top_regions_continued": continued_tops,
        #: SR6 item 3, review part 2 C2. Regions a top ran into that are a slab's UNDERSIDE
        #: (`_is_underside`: no sky, no body hanging below them, the slab they belong to above
        #: them): not processed, nothing built under them.
        "undersides_not_tops": len(not_tops),
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
        #: Review part 2, M3. Pieces given back because a face of their wall (or of the bottom
        #: over them) was refused -- counted nowhere before; they are where the double layers of
        #: review C1 came from, and the new faces lying on them are refused now.
        "side_pieces_given_back": int(sum(1 for f in np.nonzero(replaced_group >= 0)[0]
                                          if not replaced[f] and not kept_groups[replaced_group[f]])),
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
        #: SR5 (review I1). Every region with a planned wall deeper than, or a bottom below, the
        #: shallowest side it already has: `{region, shallowest_side, representative_side,
        #: deepest_side, deepest_wall, bottom}`, each side measured below its own edge (SR6).
        #: Since SR6 item 2 a bottom below a lip is by design; a wall deeper than the bottom
        #: still hangs below the slab as a fin.
        "regions_deeper_than_own_sides": deeper,
        #: SR6 item 2. Per region, the depth most of its own side length reaches
        #: (`_representative_depth`): the bottom goes no deeper, and an own side shallower than
        #: it is a lip that measures nothing. `None` for a region without own sides.
        "representative_side_per_region": report_rep,
        #: SR6 item 1. Regions with a lower surface (`_lower_surface`) -- they have their bottom,
        #: and their volume follows it -- and the walls built down to it at each end, of which
        #: `trapezoids` differ in depth between their two ends by more than the depth tolerance.
        "walls_to_lower_surface": {"regions": lower_regions, "walls": lower_walls,
                                   "trapezoids": trapezoids},
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
               fraction: float, search_extra: float = 24.0,
               deepest_own: float | None = None, band: float = 0.0) -> tuple[bool, float]:
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
    100 in above a floor does not have that floor for an underside. And, given `deepest_own` (the
    deepest the slab's sides reach: its own sides below their edges, and what `_wall_pieces`
    measured hanging from each outline edge -- a side gridded into rows is as deep as all of
    them), no deeper than they go plus `band` -- the limit `_lower_surface` keeps (review I1;
    brief 10 item 1): a floor 20 in below a 2 in slab whose sides end 2 in down is the ground
    under it, not its bottom. Taken for its bottom, the slab got none, its volume ran down to the
    floor, and its open underside kept the wall on its missing side from ever being kept."""
    centroid = topo.positions_w[topo.face_w[members]].mean(axis=1)
    origins = centroid - np.array([0.0, 0.0, EPS_IN])
    directions = np.tile(np.array([0.0, 0.0, -1.0]), (len(origins), 1))
    tri, t = caster.first_hit(origins, directions)
    found = (tri >= 0) & (t <= h + search_extra + tol)
    depth = float(np.median(t[found]) + EPS_IN) if found.any() else h
    exists = bool(found.mean() >= fraction)
    if exists and deepest_own is not None and depth > deepest_own + band:
        return False, h
    return exists, depth


def _lower_surface(topo: Topology, members: np.ndarray, caster, ok_ids: np.ndarray,
                   normals: np.ndarray, reach: float, fraction: float, deepest_own: float,
                   band: float, top_min_nz: float, top_normal: np.ndarray,
                   top_origin: np.ndarray) -> tuple[np.ndarray, float] | None:
    """SR6 item 1. The slab's LOWER SURFACE, as the plane `z = a x + b y + c` (`(a, b, c)`) with
    the median depth below the top at which it was met -- or `None`.

    Rays go straight down from just below four points of every face of the region (its centroid,
    and halfway from it to each corner). The region has a lower surface when at least `fraction`
    of them meet something within `reach`, and it is the ONE face region most of them meet, on a
    floor-like face (`|n_z| > top_min_nz`) -- if that region takes at least half of them. Its
    plane is fitted to the points met on it alone (a region is planar), or, without three points
    that span a plane, taken parallel to the top at their median depth.

    Why one region, not every point met: 41 of the 196 rays of file B's ramp meet a block face
    inside it first, some only 0.4 to 0.6 in above the underside. A plane fitted to all of them,
    dropping the far ones and fitting again, came out tilted -- the ramp's walls were planned
    34.8 to 37.2 in deep against its 39.37 in. Its underside, region 314, takes 154 of the 196.

    It must be THIS slab's: no deeper than the slab's deepest own side reaches, plus `band`. A
    floor 20 in below a 2 in slab is the ground under it, not its underside, and walls that
    followed it would box the slab down to the floor (review I1)."""
    tri = topo.positions_w[topo.face_w[members]]
    centroid = tri.mean(axis=1)
    samples = np.concatenate([centroid] + [(centroid + tri[:, k]) / 2.0 for k in range(3)])
    origins = samples - np.array([0.0, 0.0, EPS_IN])
    hit_tri, t = caster.first_hit(origins, np.tile(np.array([0.0, 0.0, -1.0]), (len(origins), 1)))
    hit = (hit_tri >= 0) & (t <= reach)
    if not len(hit) or hit.mean() < fraction:
        return None
    face = ok_ids[hit_tri[hit]]
    floorlike = np.abs(normals[face][:, 2]) > top_min_nz
    region = topo.face_region[face]
    candidates = region[floorlike & (region >= 0)]
    if not len(candidates):
        return None
    ids, counts = np.unique(candidates, return_counts=True)
    dominant = int(ids[int(np.argmax(counts))])            # ties: the lowest id, deterministic
    on = floorlike & (region == dominant)
    if on.sum() < 0.5 * int(hit.sum()):
        return None
    points = origins[hit][on].copy()
    points[:, 2] -= t[hit][on]
    depth = float(np.median(t[hit][on]) + EPS_IN)
    if depth > deepest_own + band:
        return None
    A = np.column_stack([points[:, 0], points[:, 1], np.ones(len(points))])
    if len(points) >= 3 and np.linalg.matrix_rank(A) == 3:
        coef = np.linalg.lstsq(A, points[:, 2], rcond=None)[0]
    else:
        # the top plane, z = z0 - (nx (x - x0) + ny (y - y0)) / nz, lowered by the depth
        n, o = top_normal, top_origin
        coef = np.array([-n[0] / n[2], -n[1] / n[2],
                         o[2] + (n[0] * o[0] + n[1] * o[1]) / n[2] - depth])
    return np.asarray(coef, dtype=np.float64), depth


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
    footprint, below its bottom, above its top, or that slab's depth was never measured.

    `volumes` maps a region to `(foot, normal, origin, depth, under)`. With `under`, the plane
    `z = a x + b y + c` of the slab's lower surface (SR6 item 1), the bottom is that surface
    rather than the top lowered by `depth`: a wedge's volume deepens with its slope.

    A point within `EPS_IN` of the top or the bottom plane lies ON it, and is inside (SR6). The
    point judged for a face lying on the new bottom's own plane -- a real partial bottom the
    bottom replaces -- is the hit point itself, and measured it came out 3.05e-6 in below file
    A's lower-landing bottom (all 4,395 of them) and 3.4e-4 to 7.9e-4 in outside file B's ramp
    and its neighbours: the precision of a ray hit on quantised coordinates. Judged "below the
    bottom" they refused half of that bottom, round after round."""
    order = sorted(volumes)

    def interior(face_ids: np.ndarray, points_c: np.ndarray) -> np.ndarray:
        points = np.asarray(points_c, dtype=np.float64) + centre
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        inside = np.zeros(len(points), bool)
        own_code = np.full(len(points), INTERIOR_UNMEASURED, np.int64)
        own_region = group_region[new_group[np.asarray(face_ids, dtype=np.int64)]]
        for region in order:
            foot, normal, origin, depth, under = volumes[region]
            over = shapely.contains_xy(foot, x, y)
            top = _z_top(normal, origin, x, y)
            below_top = top - z
            if under is not None:
                depth = top - (under[0] * x + under[1] * y + under[2])
            inside |= over & (below_top >= -EPS_IN) & (below_top <= depth + EPS_IN)
            mine = own_region == region
            if mine.any():
                code = np.where(~over, INTERIOR_OUTSIDE_FOOTPRINT,
                                np.where(below_top < -EPS_IN, INTERIOR_AT_OR_ABOVE_TOP,
                                         INTERIOR_BELOW_BOTTOM))
                own_code[mine] = code[mine]
        return np.where(inside, INTERIOR_INSIDE, own_code)

    return interior


#: Two faces are parallel enough to COINCIDE within this many degrees (SR4).
_COINCIDENT_ANGLE_DEG = 1.0


class _Planes:
    """Every face of `solid` as a triangle, its unit normal, area and bounding box, for the
    geometric coincidence tests below."""

    def __init__(self, solid: MeshData):
        self.tri = solid.positions[solid.face_v]
        cross = np.cross(self.tri[:, 1] - self.tri[:, 0], self.tri[:, 2] - self.tri[:, 0])
        self.area = 0.5 * np.linalg.norm(cross, axis=1)
        self.unit = cross / np.maximum(2.0 * self.area, 1e-300)[:, None]
        self.lo, self.hi = self.tri.min(axis=1), self.tri.max(axis=1)

    def lying_on(self, f: int, cand: np.ndarray, tol: float) -> np.ndarray:
        """The faces of `cand` lying ON face `f`: parallel to it within `_COINCIDENT_ANGLE_DEG`,
        every corner within `tol` of its plane, and overlapping it in that plane by more than a
        thousandth of the smaller one's area."""
        if self.area[f] <= 0.0 or not len(cand):
            return np.zeros(0, np.int64)
        cand = np.asarray(cand, np.int64)
        near = ((self.hi[cand] >= self.lo[f] - tol) & (self.lo[cand] <= self.hi[f] + tol)).all(axis=1)
        cand = cand[near]
        cos_parallel = float(np.cos(np.radians(_COINCIDENT_ANGLE_DEG)))
        cand = cand[np.abs(self.unit[cand] @ self.unit[f]) >= cos_parallel]
        cand = cand[np.abs((self.tri[cand] - self.tri[f][0]) @ self.unit[f]).max(axis=1) <= tol]
        if not len(cand):
            return cand
        e1, e2 = plane_basis(self.unit[f])
        basis = np.stack([e1, e2], axis=1)
        mine = shapely.Polygon((self.tri[f] - self.tri[f][0]) @ basis)
        keep = []
        for o in cand:
            shared = mine.intersection(shapely.Polygon((self.tri[o] - self.tri[f][0]) @ basis)).area
            if shared > max(1e-4, 1e-3 * min(float(self.area[f]), float(self.area[o]))):
                keep.append(int(o))
        return np.asarray(keep, np.int64)


def _coincident_new_faces(solid: MeshData, new_faces: np.ndarray, new_group: np.ndarray,
                          replaced_group: np.ndarray, ok_input: np.ndarray,
                          tol: float) -> np.ndarray:
    """Bool over `solid`'s faces: new faces lying ON an existing face (`_Planes.lying_on`) that
    is not one of the new face's own group's pieces -- or ON a new face another group built
    before it that is not itself refused here (review part 2, C1: one bottom per footprint).

    Decided geometrically, not by pixels (review C1): a coincident pair renders as a tie, so no
    pixel rule can see a skirt laid exactly over an existing side, and one did ship as a
    z-fighting double layer when that side was wound inward. Walls were deduplicated across
    regions (`built_walls`) but bottoms were not: a top that is a duplicate layer of two
    materials got a bottom under each of its regions, 1,600 sq in of m0 exactly over m1."""
    out = np.zeros(solid.n_faces, bool)
    planes = _Planes(solid)
    orig = np.nonzero(np.asarray(ok_input, bool))[0]
    new_ids = np.nonzero(new_faces)[0]
    for f in new_ids:
        cand = orig[replaced_group[orig] != new_group[f]]
        if len(planes.lying_on(f, cand, tol)):
            out[f] = True
            continue
        earlier = new_ids[(new_ids < f) & (new_group[new_ids] != new_group[f])]
        if len(planes.lying_on(f, earlier[~out[earlier]], tol)):
            out[f] = True
    return out


def _new_faces_on_pieces(solid: MeshData, new_faces: np.ndarray, replaced_group: np.ndarray,
                         tol: float) -> dict[int, np.ndarray]:
    """Review part 2, C1: per new face, the PIECES (original faces some closing face replaces)
    lying on it -- its own group's included, which `_coincident_new_faces` skips because they are
    to be removed. The cap guard refuses a new face whenever one of these is present in the state
    it judges: a piece it gave back must never stay under a new face lying on it."""
    planes = _Planes(solid)
    pieces = np.nonzero(np.asarray(replaced_group) >= 0)[0]
    out: dict[int, np.ndarray] = {}
    if not len(pieces):
        return out
    for f in np.nonzero(new_faces)[0]:
        on = planes.lying_on(int(f), pieces, tol)
        if len(on):
            out[int(f)] = on
    return out


def _bottom_piece_cover(solid: MeshData, new_group: np.ndarray, replaced_group: np.ndarray,
                        group_kind: list[str]) -> dict[int, np.ndarray]:
    """SR6. Per piece of a BOTTOM, the faces of that bottom lying over it (overlapping it seen
    from above by more than a thousandth of the smaller one's area): the cap guard gives the
    piece back only when one of THESE is refused, not when any face of a bottom that may span
    the whole slab is. A wall has two faces and keeps the group rule."""
    out: dict[int, np.ndarray] = {}
    tri = solid.positions[solid.face_v]
    for g, kind in enumerate(group_kind):
        if kind != "bottom":
            continue
        faces = np.nonzero(new_group == g)[0]
        pieces = np.nonzero(replaced_group == g)[0]
        if not len(faces) or not len(pieces):
            continue
        polys = shapely.polygons(tri[faces][:, :, :2])
        areas = shapely.area(polys)
        for p in pieces:
            mine = shapely.Polygon(tri[p][:, :2])
            shared = shapely.area(shapely.intersection(polys, mine))
            over = shared > np.maximum(1e-4, 1e-3 * np.minimum(areas, mine.area))
            out[int(p)] = faces[over]
    return out


def _cap_guard(original: MeshData, solid: MeshData, new_faces: np.ndarray,
                guard_size: tuple[int, int], n_dirs: int = 128,
                cover_max_exposure: float = 0.10, max_rounds: int = 8, *,
                replaced_group: np.ndarray | None = None, new_group: np.ndarray | None = None,
                side_band: float = 0.0, volumes: dict | None = None,
                group_region: np.ndarray | None = None,
                parallel_interior_ok: np.ndarray | None = None,
                shell_faces: np.ndarray | None = None,
                refused_before: np.ndarray | None = None,
                piece_cover: dict | None = None, on_pieces: dict | None = None):
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
    front, back = compute_side_exposure(positions_c, faces_before,
                                        np.ones(len(faces_before), bool), n_dirs=n_dirs)

    interior = None
    if volumes and new_group is not None and group_region is not None and len(group_region):
        interior = _interior_test(volumes, np.asarray(new_group, np.int64),
                                  np.asarray(group_region, np.int64), centre)
    keep, history, detail = solidify_feedback(
        positions_c, faces_before, faces_after, new_faces, front,
        cover_max_exposure=cover_max_exposure, views=VIEWS_26, size=guard_size,
        max_rounds=max_rounds, replaced_group=replaced_group, new_group=new_group,
        side_band=side_band, interior=interior, back_exposure_before=back,
        parallel_interior_ok=parallel_interior_ok, shell_faces=shell_faces,
        refused_before=refused_before, piece_cover=piece_cover, on_pieces=on_pieces)
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
