"""Rebuild every flat region as the fewest triangles over its EXISTING vertices.

A SketchUp export cuts each flat surface into hundreds of small coplanar triangles ("gridlines").
This kernel unions each planar region inside its own plane, drops the border vertices that no
region needs as a corner, and re-triangulates what is left, so only real shape edges survive.

Positions are never moved, never appended to and never re-indexed: every output face indexes a
position that was already in `mesh.positions`. `vt` and `vn` rows are attributes, not geometry, so
new ones may be appended.

A polygon with `n` ring vertices and `h` holes triangulates into exactly `n + 2h - 2` triangles,
so the triangle count is decided by how many ring vertices survive the global corner pass -- plus
two for every vertex another face stands on that lies on one of the polygon's diagonals, and one
for every vertex threaded into a triangle copied through (see "T-junctions" below).

T-JUNCTIONS. A vertex the output uses that lies on the interior of an output edge is a T-junction:
SketchUp keeps the long edge and the neighbour's short ones apart and draws a line inside the
surface, and a renderer leaves a hairline crack along it. The export is full of them (on file A's
sloped underside 54 of 218 vertices lie exactly on a neighbouring triangle's edge). Every one is
threaded into the edge it lies on: into a region's ring before the corner pass
(`_thread_union_rings`), and after the output is decided by splitting every triangle that still
has one on an edge, a region's ring taking the vertex too (`_thread_output`). Both only split
edges at vertices already there, within `thread_tolerance`: no vertex moves, none is invented.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

import numpy as np
import shapely

from engine.fixes.overlap import overlap_excluded as _overlap_excluded, region_frame as _region_frame
from engine.model import MeshData
from engine.pipeline import Topology
from engine.topo.adjacency import build_edge_table, degenerate_mask, find_t_vertices
from engine.topo.edges import EDGE_NONMANIFOLD, EDGE_OPEN, EDGE_TJUNCTION
from engine.topo.planes import cluster_uv, plane_basis

#: Precision grid the 2D union snaps to (inches, in the region's LOCAL frame).
GRID_SIZE = 1e-4
#: Floor of the per-region snap tolerance, in inches (`snap_tolerance`): even an exactly flat
#: region reads a union ring coordinate this close to an existing vertex as that vertex.
SNAP_TOL = 1e-3
#: Ceiling of the per-region snap tolerance, in inches: one X/Z print step of the export, a
#: fifteenth of the 0.15 in a merged border may move (`default_collinear_tol`). No union
#: coordinate farther than this from every vertex is ever read as one of them.
SNAP_TOL_MAX = 1e-2
#: A union ring whose mean width, `4 * area / perimeter`, is at most this many grid cells is a
#: SLIVER of the union rather than a gap in the surface, and is closed whatever its corners snap
#: to (`_is_sliver`, `_pieces`).
SLIVER_CELLS = 2.0
#: How many times a region sets aside the triangles that make a union corner no vertex explains
#: and unions the rest again before it is given up whole as `new_vertex` (`_region_union`).
MAX_SET_ASIDE_ROUNDS = 3
#: The ring-simplification bound, in axis quanta: a ring vertex may only be dropped while the
#: WHOLE original polyline between its surviving neighbours stays this close to the chord that
#: replaces it. `1.5 * max(q)` is one and a half of the mesh's own print steps -- the same bound
#: the guard uses for depth -- so a simplified boundary can never move by more than the export
#: could resolve in the first place.
RING_TOL_QUANTA = 1.5
#: Most times pass 2 reruns after a feedback event (see `merge_regions`).
MAX_ROUNDS = 10
#: A vertex lies ON an edge -- a T-junction, threaded into the edge -- when it is within this
#: fraction of the mesh's coarsest print step of the edge's interior (`thread_tolerance`).
THREAD_TOL_QUANTA = 1e-5
#: Most rounds `_thread_output` splits triangles in. A backstop, not the mechanism: a split only
#: makes a vertex the output already uses a corner of the triangles around it, so the pass runs
#: out of vertices to thread (every measured case needs one round and a second that finds none).
MAX_THREAD_ROUNDS = 8
#: Rule 3, the overlap exclusion, is `engine.fixes.overlap.overlap_excluded` -- one
#: implementation, so "these two faces overlap" means the same thing to the merge and to the
#: duplicate-layer removal that runs before it.
#: Relative slack on the area checks: rule 6 per piece, rule 9 per region and per pass.
_AREA_REL_TOL = 1e-6
#: Nearest-vertex search block size, in coordinate x vertex pairs.
_SEARCH_BLOCK = 4_000_000

_SKIP_REASONS = ("overlap", "new_vertex", "invalid_polygon", "area_grew")


def default_collinear_tol(quanta: np.ndarray) -> float:
    """The ring-simplification bound `merge_regions` uses when it is given none:
    `RING_TOL_QUANTA * max(quanta)`, from the mesh's OWN axis print steps (`Topology.quanta`).
    It is also how far a merged border may move, which is why the guards that judge a merged mesh
    read it from here rather than restating it (`engine.fixes.pipeline`)."""
    return RING_TOL_QUANTA * float(np.asarray(quanta).max())


def snap_tolerance(thickness: float, floor: float = SNAP_TOL) -> float:
    """How far a union ring coordinate may land from an existing vertex and still be read as that
    vertex, for a region whose vertices spread `thickness` inches along its own normal: the
    thickness itself, clamped to `[floor, SNAP_TOL_MAX]`.

    WHERE SUCH A CORNER COMES FROM. The union runs in the region's own plane on a `GRID_SIZE`
    grid. An axis-aligned region projects its vertices ONTO that grid (the export printed them on
    a 0.01 in lattice), so its union lands exactly on them. A sloped or skewed region projects
    them OFF it; the union snaps them, and where two of a vertex's own edges meet at a narrow
    angle the two snapped edges part by a grid cell and meet again up to `cell / sin(angle)` from
    the vertex: the tip of a spike or sliver that belongs to that vertex. Which tip, and how far
    out, changes with the order the union combines the same triangles.

    WHY THE THICKNESS. Those regions are exactly the ones the export could not print flat -- a
    sloped plane's vertices are rounded to 0.01 in -- and rebuilding one already moves its
    surface by up to its thickness out of the plane: the old triangles and the new ones run
    through the same vertices, each inside the region's slab. Reading a corner that close to a
    vertex as the vertex moves the border within the plane by no more than that.

    MEASURED on the merge inputs of both real files (A `ce26e0392ab0`, B `0b290ec0bcb4`: 271
    regions of two or more faces, 3,441 union ring coordinates). The 205 axis-aligned regions are
    0 in thick and every coordinate of theirs lies within 3e-12 in of a vertex. The 66 others are
    0.008 in thick at the median, 0.11 in at most. 3,415 coordinates land within 7.1e-5 in (half
    a grid cell's diagonal) of a vertex, 24 more within 4.0e-4 in, and one at 0.0016 in: the apex
    of file B's ramp, 0.0085 in thick, whose fan edges meet 0.3 to 4.7 degrees apart there. All
    25 lie on non-axis-aligned regions, none beyond 0.19 of that region's thickness; 24 are tips
    at a vertex (every edge within 2e-4 in of them ends at it, the narrowest angle there 0.3 to
    37 degrees) and one, 8.9e-5 in out on file A's lattice, is a T-junction sliver's corner.
    Unions of subsets of the same ramp put its tips up to 0.0053 in out, still inside 0.0085.
    The one coordinate left is 7.87 in from every vertex (file A): the corner of a T-junction
    sliver, which no tolerance should read as a vertex and `_pieces` closes instead."""
    return min(max(float(floor), float(thickness)), SNAP_TOL_MAX)


def thread_tolerance(quanta: np.ndarray) -> float:
    """How close, in inches, a vertex must lie to the interior of an edge to be ON it -- a
    T-junction, threaded into the edge (`_thread_union_rings`, `_thread_output`):
    `THREAD_TOL_QUANTA * max(quanta)`, a hundred-thousandth of the mesh's own coarsest print step
    (`Topology.quanta`; 0.1 in on Y near 24,000 in gives 1e-6 in).

    WHY SO TIGHT. A vertex the export put on an edge is on it to float precision, and one it put
    beside an edge is off it by a printable amount. MEASURED on the merge outputs of both real
    files (A `ce26e0392ab0`, B `0b290ec0bcb4`, before this pass existed): of the vertices the
    output uses within 0.15 in of an output edge's interior, 111 (A) and 65 (B) lie within 1e-9 in
    of it -- coordinates near 24,000 in carry about 4e-12 in of float error -- and the nearest of
    the rest is 6.1e-4 in off (B; 1.2e-3 in on A): a real gap or overlap in the export, which
    threading would close by moving the surface. The tolerance sits a thousand times above the one
    and six hundred times below the other, and since threading moves a border by at most this
    much, nothing it threads can move a surface anyone could see."""
    return THREAD_TOL_QUANTA * float(np.asarray(quanta).max())


@dataclass
class MergeResult:
    """`mesh` with every mergeable region re-triangulated; `source_faces[i]` is the array of
    ORIGINAL face indices new face `i` came from (its whole region when merged, a single face when
    copied through -- several rows when a vertex was threaded into one of that face's edges, which
    cuts it into a fan); `report` is the counts described in `merge_regions`.

    `rings[i]`, when present, is the merged region output row `i` belongs to, as its kept LOOPS:
    `{"outer": ids, "inners": [ids, ...]}`. Every id array is int64 and indexes `mesh.positions`
    exactly like `mesh.face_v` does. `outer` runs CCW as seen from the region's own outward side;
    every loop in `inners` runs CW, the convention a polygon consumer reads as a hole. `inners`
    is `[]` for a hole-free region.

    Every row of the SAME region maps to the IDENTICAL dict object (not just equal content), so a
    writer that wants one polygon face per region can dedup by `id()` -- see
    `engine.io.obj_writer.write_obj_polygons`, which writes the `outer` loop as one `f` line for
    hole-free regions and keeps ordinary triangles for the rest, since an OBJ `f` line cannot
    carry a hole.

    A region made of more than one disjoint piece, or whose outer loop keeps fewer than 3
    vertices, has NO entry (its rows are ordinary triangles); rows copied through unmerged never
    have an entry either.

    `face_region[i]` is the region output row `i` belongs to, or -1 when the row was copied
    through unmerged. Two rows sharing a region id `>= 0` are two triangles of ONE rebuilt
    polygon, so the edge between them exists only because OBJ needs triangles. A region's
    triangles use every vertex of its loops and, where another face stands on a diagonal of the
    polygon, that vertex too, inside the polygon (see `merge_regions`, T-junctions)."""
    mesh: MeshData
    source_faces: list[np.ndarray]
    report: dict
    rings: dict[int, dict] = field(default_factory=dict)
    face_region: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))


@dataclass
class _Piece:
    """One polygon of a region's union: its rings as welded vertex ids plus the union's own
    area/perimeter, which the rebuilt polygon is checked against."""
    rings: list[np.ndarray]
    union_area: float
    union_perimeter: float


@dataclass
class _Plan:
    """Everything pass 2 needs about one mergeable region, decided before the global corner pass.

    `vertex_ids` (sorted) and `vertex_xy` are every vertex the region's rings or triangles use,
    projected into its own frame `(v - origin) @ basis` -- its members' vertices, and whatever a
    T-junction threads into it (`_thread_union_rings`, `_thread_output`)."""
    region: int
    members: np.ndarray
    vertex_ids: np.ndarray
    vertex_xy: np.ndarray
    normal: np.ndarray
    origin: np.ndarray
    basis: np.ndarray
    pieces: list[_Piece]
    original_area: float
    #: The snap tolerance the region's union was mapped back onto its vertices with
    #: (`snap_tolerance` of its own thickness).
    snap_tol: float = SNAP_TOL
    #: ORIGINAL face indices set aside because their edges made a union corner no vertex
    #: explains (`_region_union`); copied through, like rule 3's exclusions. Sorted.
    set_aside: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))
    #: `(a, b, vertices)` for every union ring segment `a`-`b` that `_thread_union_rings` threaded
    #: `vertices` into, in ring order.
    threaded: list = field(default_factory=list)


def merge_regions(mesh: MeshData, topo: Topology, flat_materials: Iterable[int] = frozenset(),
                  grid_size: float = GRID_SIZE, snap_tol: float = SNAP_TOL,
                  collinear_tol: float | None = None) -> MergeResult:
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
    from `overlap` / `new_vertex` / `invalid_polygon` / `area_grew`, each a region given up
    WHOLE), `tris_before`, `tris_after`, `vertices_dropped` (welded vertices used by an input face
    and by no output face), `max_area_rel_error`, `faces_copied`, `merge_rounds`,
    `keep_all_regions` (how many regions took the `keep_all` fallback in any round of the loop),
    `converged`, and `new_vertex_triangles_set_aside`: triangles copied through because their
    edges made a union corner no vertex explains, in regions that merged without them
    (`_region_union`). A region given up whole counts in `regions_skipped` only.

    T-JUNCTIONS. Every vertex of the input lying on a region's union ring segment is threaded into
    that ring before the corner pass (`_thread_union_rings`), which keeps it wherever another face
    needs it; once the output is decided, every triangle with a used vertex on one of its edges is
    split at it, a region's ring taking the vertex too (`_thread_output`). Neither moves or
    invents a vertex (`thread_tolerance` decides "on"). `t_vertices_before` / `t_vertices_after`
    count the distinct vertices lying on the interior of an edge of the merge input / of the
    output (`find_t_vertices` at `thread_tolerance`, over the non-degenerate faces: a zero-area
    face covers nothing, so it opens no crack), and `edges_split` the distinct edges cut at a
    threaded vertex: a union ring segment whose threaded vertex the kept ring keeps, or a
    triangle edge the output pass split.

    `collinear_tol` is the ring-simplification bound (see `_ring_keep`); `None`, the default,
    derives it from the mesh's OWN print precision as `RING_TOL_QUANTA * max(topo.quanta)`
    (`default_collinear_tol`).

    `snap_tol` is the FLOOR of each region's snap tolerance: a region maps its union back onto
    its vertices with `snap_tolerance(thickness, snap_tol)`, its own thickness clamped between
    this floor and `SNAP_TOL_MAX`.
    """
    flat = _validated_materials(flat_materials)
    if collinear_tol is None:
        collinear_tol = default_collinear_tol(topo.quanta)
    thread_tol = thread_tolerance(topo.quanta)
    welded_to_original = _welded_to_original(mesh, topo)

    plans, copied, skipped = _plan_regions(topo, grid_size, snap_tol)
    _thread_union_rings(topo, plans, thread_tol)

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

    # Each region's rings exactly as `_triangulate` built its triangles from them in the round
    # that produced `builds`: whole for a `keep_all` region, simplified by the corner pass for the
    # rest.
    keep_all_set = frozenset(kept_whole | set(keep_all))
    kept = {plan.region: [[ring if plan.region in keep_all_set else ring[needed[ring]]
                           for ring in piece.rings] for piece in plan.pieces]
            for plan, _tris in builds}
    split_edges = _kept_threads(builds, kept)
    builds, copied_split, output_splits = _thread_output(topo, builds, copied, kept, thread_tol)
    split_edges |= output_splits

    region_rings: dict[int, dict] = {}
    for plan, _tris in builds:
        loops = _region_loops(plan, kept[plan.region], welded_to_original)
        if loops is not None:
            region_rings[plan.region] = loops

    out = _assemble(mesh, topo, welded_to_original, builds, copied, flat, region_rings,
                    copied_split)
    used_before = np.zeros(len(topo.positions_w), bool)
    used_before[topo.face_w.reshape(-1)] = True
    used_after = np.zeros(len(topo.positions_w), bool)
    face_w_after = _welded_of(mesh, topo, out.mesh)
    used_after[face_w_after] = True
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
        "new_vertex_triangles_set_aside": int(sum(len(plan.set_aside) for plan, _t in builds)),
        "t_vertices_before": _count_t_vertices(topo.positions_w, topo.face_w, thread_tol),
        "t_vertices_after": _count_t_vertices(topo.positions_w, face_w_after.reshape(-1, 3),
                                              thread_tol),
        "edges_split": len(split_edges),
    })
    return out


def _kept_threads(builds: list, kept: dict[int, list]) -> set[tuple[int, int]]:
    """Every union ring segment, as a sorted vertex pair, that `_thread_union_rings` threaded a
    vertex into which the region's kept rings still hold -- an edge of the region's outline cut
    at that vertex."""
    out: set[tuple[int, int]] = set()
    for plan, _tris in builds:
        ring_vertices = {int(v) for piece in kept[plan.region] for ring in piece for v in ring}
        for a, b, on in plan.threaded:
            if ring_vertices.intersection(on):
                out.add((min(a, b), max(a, b)))
    return out


def _count_t_vertices(positions: np.ndarray, face_w: np.ndarray, tol: float) -> int:
    """How many distinct vertices of the non-degenerate faces `face_w` lie within `tol` of the
    interior of one of their edges (`find_t_vertices`, without zero-area hints)."""
    ok = ~degenerate_mask(positions, face_w)
    hits = find_t_vertices(positions, build_edge_table(face_w, ok), tol)
    return len({int(v) for verts in hits.values() for v in verts})


def region_outline(topo: Topology, members: np.ndarray, grid_size: float = GRID_SIZE,
                   snap_tol: float = SNAP_TOL):
    """`(pieces, normal, origin, basis)` for one region -- exactly the union `_plan_regions`
    computes for the merge, exposed so `engine.fixes.solidify` hangs its skirt on the SAME
    outline the merge will later rebuild the region from.

    `pieces` are `_Piece`s: each polygon of the union with its rings as WELDED vertex ids, every
    ring a simple cycle of at least 3 and every sliver closed (see `_pieces`). They outline the
    triangles the merge will rebuild: rule 3's exclusions and the triangles `_region_union` sets
    aside are left out of the union here exactly as they are there. `None` when the region has no
    frame (no area), when every one of its triangles is excluded by the overlap rule, when a union
    corner no vertex explains outlasts `MAX_SET_ASIDE_ROUNDS` (or no triangle is left to set
    aside), when the union is empty, or when an outer ring pinches into lobes no single polygon
    over existing vertices describes -- all of which a caller reports as one thing, "the outline
    could not be mapped back onto vertices this mesh has"."""
    outline = _region_union(topo, members, grid_size, snap_tol)
    if outline is None or not outline.pieces:
        return None
    return outline.pieces, outline.normal, outline.origin, outline.basis


# --------------------------------------------------------------------------- pass 1: plan regions


def _plan_regions(topo: Topology, grid_size: float,
                  snap_tol: float) -> tuple[list[_Plan], list[int], dict]:
    """Project, overlap-filter and union every region (`_region_union`); returns the plans for
    the mergeable ones, the original indices of every face copied through, and the skip reason
    counts so far. A region's rule-3 exclusions and set-aside triangles are copied through and
    the rest of it is planned; a region given up whole is copied through whole."""
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

        outline = _region_union(topo, members, grid_size, snap_tol)
        if outline is None:
            copied.extend(int(f) for f in members)
            skipped["invalid_polygon"] += 1
            continue
        copied.extend(int(f) for f in members[outline.excluded])
        if outline.excluded.all():
            skipped["overlap"] += 1
            continue
        if not outline.pieces:
            copied.extend(int(f) for f in members[~outline.excluded])
            skipped["new_vertex" if outline.pieces is None else "invalid_polygon"] += 1
            continue

        keep = outline.keep
        copied.extend(int(f) for f in members[outline.set_aside])
        plans.append(_Plan(region=int(region), members=members[keep],
                           vertex_ids=outline.vertex_ids, vertex_xy=outline.vertex_xy,
                           normal=outline.normal, origin=outline.origin, basis=outline.basis,
                           pieces=outline.pieces,
                           original_area=float(outline.areas[keep].sum()),
                           snap_tol=outline.snap_tol,
                           set_aside=members[outline.set_aside].astype(np.int64)))
    return plans, copied, skipped


@dataclass
class _RegionUnion:
    """One region projected into its own plane, filtered by rule 3 and unioned, with whatever
    `_region_union` had to set aside. Every mask is over the region's members."""
    normal: np.ndarray
    origin: np.ndarray
    basis: np.ndarray
    vertex_ids: np.ndarray
    vertex_xy: np.ndarray
    areas: np.ndarray
    #: Rule 3: overlaps another triangle of the region (`_overlap_excluded`).
    excluded: np.ndarray
    #: Its edges made a union corner no vertex explains. All False when the region was given up.
    set_aside: np.ndarray
    #: `_pieces` of the union of the triangles in `keep`: `None` (a corner no vertex explains
    #: outlasted the set-aside rounds, or every triangle was excluded), `[]` (pinched), or pieces.
    pieces: list | None
    snap_tol: float

    @property
    def keep(self) -> np.ndarray:
        return ~self.excluded & ~self.set_aside


def _region_union(topo: Topology, members: np.ndarray, grid_size: float,
                  snap_tol: float) -> _RegionUnion | None:
    """Project `members` into their own plane, exclude rule 3's overlaps, union the rest on the
    `grid_size` grid and map the union back onto existing vertices within the region's snap
    tolerance (`snap_tolerance` of its thickness, `snap_tol` the floor). `None` when the region
    has no frame (no area).

    A UNION CORNER NO VERTEX EXPLAINS does not give the whole region up any more. The triangles
    that make it are the ones whose BOUNDARY passes within the snap tolerance of it -- the union's
    ring coordinates all lie on the (grid-snapped) edges of the triangles that bound it, so a
    corner where two edges cross lies on both. They are set aside exactly like rule 3's
    exclusions: copied through unmerged, and since every vertex of a copied face is `needed`,
    the corner pass keeps each of them that lies on the rest's rings, so no T-junction opens.
    The rest is unioned again. Proved on the real 274-triangle region of file A
    (`engine.tests.fixtures.build.t_junction_lattice_region`) with its slivers left open: its one
    corner, 7.87 in from every vertex, lies 4.6e-5 in from the edges of exactly two triangles --
    the one whose 236.2 in edge carries the T-junction and the one whose 39.4 in edge ends on it
    -- and no other triangle comes within its snap tolerance (0.01 in, the ceiling: the region is
    0.0105 in thick) or within half of it. One round sets those two aside and the rest maps onto
    existing vertices. (With slivers closed, `_pieces`, that region needs no round at all.)

    After `MAX_SET_ASIDE_ROUNDS` rounds, or when every remaining triangle would go, the region is
    given up whole as before (`pieces` None, nothing counted as set aside)."""
    frame = _region_frame(topo.positions_w, topo.face_w, members)
    if frame is None:
        return None
    normal, origin, basis = frame
    vertex_ids = np.unique(topo.face_w[members])
    vertex_xy = (topo.positions_w[vertex_ids] - origin) @ basis
    tol = snap_tolerance(_thickness(topo.positions_w[vertex_ids] - origin, normal), snap_tol)
    tri_xy = vertex_xy[np.searchsorted(vertex_ids, topo.face_w[members])]
    polys = shapely.polygons(np.concatenate([tri_xy, tri_xy[:, :1]], axis=1))
    areas = shapely.area(polys)
    excluded = _overlap_excluded(polys, areas)
    set_aside = np.zeros(len(members), bool)
    pieces = None
    keep = ~excluded
    if keep.any():
        boundaries = shapely.boundary(polys)
        for attempt in range(MAX_SET_ASIDE_ROUNDS + 1):
            pieces, corners = _map_union(_union(polys[keep], grid_size), vertex_xy, vertex_ids,
                                         tol, grid_size)
            if pieces is not None or attempt == MAX_SET_ASIDE_ROUNDS:
                break
            makers = keep & _corner_makers(boundaries, corners, tol)
            if not makers.any() or makers.sum() == keep.sum():
                break
            set_aside |= makers
            keep &= ~makers
    if not pieces:
        set_aside[:] = False
    return _RegionUnion(normal=normal, origin=origin, basis=basis, vertex_ids=vertex_ids,
                        vertex_xy=vertex_xy, areas=areas, excluded=excluded, set_aside=set_aside,
                        pieces=pieces, snap_tol=tol)


def _corner_makers(boundaries: np.ndarray, corners: np.ndarray, tol: float) -> np.ndarray:
    """Bool per triangle: its boundary (`shapely.boundary` of its projected polygon) passes within
    `tol` of at least one of `corners`."""
    hit = np.zeros(len(boundaries), bool)
    for point in shapely.points(np.asarray(corners, float).reshape(-1, 2)):
        hit |= shapely.distance(boundaries, point) <= tol
    return hit


def _thickness(offsets_3d: np.ndarray, normal: np.ndarray) -> float:
    """The spread along `normal` of the points `offsets_3d` (each relative to a common origin):
    how far from flat the export printed a region. 0.0 for an exactly flat one."""
    along = offsets_3d @ normal
    return float(along.max() - along.min()) if len(along) else 0.0


def _union(polys: np.ndarray, grid_size: float):
    try:
        return shapely.union_all(polys, grid_size=grid_size)
    except shapely.errors.GEOSException:
        try:
            return shapely.union_all(polys)
        except shapely.errors.GEOSException:
            return None


def _pieces(union, vertex_xy: np.ndarray, vertex_ids: np.ndarray, snap_tol: float,
            grid_size: float = GRID_SIZE):
    """Rings of every polygon of `union`, as welded vertex ids. `None` when a ring coordinate
    fails to land within `snap_tol` of an existing vertex -- a corner no vertex explains (see
    `_region_union`, which sets aside the triangles that make one).

    SLIVERS. The grid-snapped union leaves rings inside a region that has no gap there. A ring
    whose mean width, `4 * area / perimeter` on the union's own coordinates, is at most
    `SLIVER_CELLS` grid cells is one of them and is closed -- a hole dropped, an island's polygon
    dropped -- WHATEVER ITS CORNERS SNAP TO (`_is_sliver`). They run
      - around a vertex a whole fan of triangles shares, or along an edge two triangles share:
        their coordinates snap to one or two vertices (on the real region `union_sliver_region`
        their number changes with the order the union combines the same triangles);
      - at the apex of a fan of long thin triangles: file B's ramp, 0.0016 in off the apex;
      - along a T-JUNCTION line, a vertex lying exactly on the edge of a neighbouring triangle.
        The union snaps the long edge and the short ones independently, they part by a grid cell
        and cross again at a vanishing angle, and the crossing lands anywhere along the line: on
        file A's big sloped underside (`t_junction_lattice_region`) 7.87 in from every vertex,
        where the snapped 236.2 in edge crosses the snapped collinear 39.4 in one, which gave
        all 274 triangles up as `new_vertex`. A T-junction sliver whose corners do snap can snap
        to three or four distinct COLLINEAR vertices -- file B's ramp has one of each -- and a
        rebuilt polygon cannot carry that zero-width hole: the region went `invalid_polygon`.
    Measured over every region of the merge inputs of both real files: 13 of the 33 union holes
    are slivers, 5.0e-5 to 8.9e-5 in wide by this measure; the other 20 are openings at least
    0.25 in wide, and no outer ring is narrower than 0.75 in (the export prints to 0.01 in). The
    bound, 2e-4 in, sits more than twice above the one and a thousand times below the other.

    A ring that is not a sliver is kept as the SIMPLE cycles its snapped ids form
    (`_simple_cycles`); a cycle of fewer than 3 ids is dropped, because no three existing vertices
    can bound it. A hole that splits into several simple cycles becomes that many holes, touching
    at the shared vertex. An outer ring that keeps no cycle is a sliver island and its polygon is
    dropped; one that keeps more than one is two lobes joined by a neck narrower than `snap_tol`,
    which no single polygon over existing vertices describes, so the region is given up (`[]`,
    the `invalid_polygon` skip, at plan time).

    `union_area` / `union_perimeter` are measured on the union's OWN coordinates of the kept
    cycles: the polygon the rebuilt region is checked against (rule 6), every dropped ring
    closed."""
    return _map_union(union, vertex_xy, vertex_ids, snap_tol, grid_size)[0]


def _map_union(union, vertex_xy: np.ndarray, vertex_ids: np.ndarray, snap_tol: float,
               grid_size: float = GRID_SIZE):
    """`(pieces, unexplained)`: `_pieces` of `union`, and every ring coordinate of a ring that is
    not a sliver with no vertex within `snap_tol` -- all of them, from every ring, so one round of
    `_region_union` sees every corner at once. `unexplained` is `(0, 2)` unless `pieces` is
    None; a corner no vertex explains decides before a pinched outer ring does."""
    out: list[_Piece] = []
    unexplained: list[np.ndarray] = []
    pinched = False
    for poly in _polygons(union):
        rings = [np.asarray(ring.coords)[:-1] for ring in [poly.exterior, *poly.interiors]]
        if _is_sliver(rings[0], grid_size):
            continue                      # a sliver island: its polygon is dropped
        loops: list[tuple[np.ndarray, np.ndarray]] = []  # (ids, coords), outer ring first
        for k, coords in enumerate(rings):
            if k and _is_sliver(coords, grid_size):
                continue                  # a sliver hole: closed
            rows, distance = _nearest(coords, vertex_xy)
            far = distance > snap_tol
            if far.any():
                unexplained.append(coords[far])
                continue
            ids = vertex_ids[rows]
            cycles = _simple_cycles(ids)
            if k == 0 and not cycles:
                break                     # collapses onto fewer than 3 vertices: dropped
            if k == 0 and len(cycles) > 1:
                pinched = True
            loops.extend((ids[r], coords[r]) for r in cycles)
        if unexplained or pinched or not loops:
            continue
        area = perimeter = 0.0
        for k, (_ids, xy) in enumerate(loops):
            loop = shapely.Polygon(xy)
            area += loop.area if k == 0 else -loop.area
            perimeter += loop.length
        out.append(_Piece(rings=[ids for ids, _xy in loops], union_area=float(area),
                          union_perimeter=float(perimeter)))
    if unexplained:
        return None, np.concatenate(unexplained)
    return ([] if pinched else out), np.zeros((0, 2))


def _is_sliver(coords: np.ndarray, grid_size: float) -> bool:
    """True when the closed ring `coords` is, on average, at most `SLIVER_CELLS` grid cells wide:
    `4 * area <= SLIVER_CELLS * grid_size * perimeter`. For a thin triangle `4 * area / perimeter`
    is its height, for a thin strip twice its width -- either way a ring the grid, not the
    surface, made. Measured with the shoelace formula about the ring's first coordinate."""
    if len(coords) < 3:
        return True
    rel = coords - coords[0]
    x, y = rel[:, 0], rel[:, 1]
    area = 0.5 * abs(float(x @ np.roll(y, -1) - np.roll(x, -1) @ y))
    perimeter = float(np.linalg.norm(np.roll(rel, -1, axis=0) - rel, axis=1).sum())
    return 4.0 * area <= SLIVER_CELLS * grid_size * perimeter


def _polygons(geom) -> list:
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon" and not g.is_empty]


def _nearest_ids(coords: np.ndarray, vertex_xy: np.ndarray, vertex_ids: np.ndarray,
                 snap_tol: float):
    """The vertex id nearest each of `coords`, or `None` when any lies farther than `snap_tol`
    from every vertex (or there are no coordinates)."""
    if not len(coords):
        return None
    rows, distance = _nearest(coords, vertex_xy)
    if distance.max() > snap_tol:
        return None
    return vertex_ids[rows]


def _nearest(coords: np.ndarray, vertex_xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`(rows, distance)`: the row of `vertex_xy` nearest each of `coords` (the lowest row on a
    tie) and how far it is, searched in blocks of `_SEARCH_BLOCK` coordinate x vertex pairs."""
    step = max(1, _SEARCH_BLOCK // max(len(vertex_xy), 1))
    rows = np.empty(len(coords), np.int64)
    distance = np.empty(len(coords), float)
    for start in range(0, len(coords), step):
        block = coords[start:start + step]
        d = np.linalg.norm(block[:, None, :] - vertex_xy[None, :, :], axis=2)
        nearest = d.argmin(axis=1)
        rows[start:start + step] = nearest
        distance[start:start + step] = d[np.arange(len(nearest)), nearest]
    return rows, distance


def _dedup_rows(ids: np.ndarray) -> np.ndarray:
    """The rows of `ids` (one closed ring) that start a run of equal ids, the closing run folded
    into the opening one: `[p, p, a, b, p]` keeps rows `[0, 2, 3]`."""
    keep = [0]
    for row in range(1, len(ids)):
        if ids[row] != ids[keep[-1]]:
            keep.append(row)
    if len(keep) > 1 and ids[keep[-1]] == ids[keep[0]]:
        keep.pop()
    return np.array(keep, np.int64)


def _simple_cycles(ids: np.ndarray) -> list[np.ndarray]:
    """The simple cycles one closed ring of snapped ids is made of, each as the ROWS of `ids` it
    visits in ring order, leaving out every cycle of fewer than 3 ids. Consecutive repeats of an
    id are one visit. The ring is walked with a stack: a second visit to an id closes the cycle
    walked since its first visit, and the walk resumes from that first visit. So `[p, a, p, b]`
    is the two-id cycles `[p, a]` and `[p, b]`, both left out; `[p, a, b, p, c, d]` is
    `[p, a, b]` and `[p, c, d]`; and a ring that visits every id once is itself."""
    rows = _dedup_rows(ids)
    stack: list[int] = []   # indices into `rows`, the walk so far
    at: dict[int, int] = {}  # id -> its index in `stack`
    out: list[np.ndarray] = []
    for i, v in enumerate(ids[rows].tolist()):
        k = at.get(v)
        if k is None:
            at[v] = len(stack)
            stack.append(i)
            continue
        cycle = stack[k:]
        del stack[k + 1:]
        for j in cycle[1:]:
            del at[int(ids[rows[j]])]
        if len(cycle) >= 3:
            out.append(rows[cycle])
    if len(stack) >= 3:
        out.append(rows[stack])
    return out


# ------------------------------------------------------------------------------------ T-junctions


def _thread_union_rings(topo: Topology, plans: list[_Plan], tol: float) -> None:
    """Thread into every ring of every plan each vertex of the merge input that lies within `tol`
    of the INTERIOR of one of the ring's segments, in order along the segment -- the export's
    T-junctions along a region's border -- before the corner pass decides what the region keeps.

    Such a vertex belongs to a neighbour -- a face copied through, another region's ring, a wall
    standing on the border -- and lies on this region's border without being one of its corners,
    so the region's rebuilt edge would run straight past it. Threaded, it is a ring vertex like
    any other and the corner pass treats it as one: kept when another face needs it (a vertex a
    copied face uses, or one lying on an open edge, is `needed`), and a vertex a neighbour's ring
    shares is decided on both sides between the same anchors (`_divergent_vertices`), so the two
    borders stay identical. Nothing moves: the ring passes through the vertex where the segment
    already did, to within `tol` (`thread_tolerance`).

    The candidates are the vertices of every non-degenerate face, taken in each segment's own
    order (by position along it, then by id). A vertex already in the piece is never threaded
    again -- that would pinch its rings. Deterministic: plans, rings and segments are visited in
    order."""
    positions = topo.positions_w
    candidates = np.unique(topo.face_w[topo.ok])
    for plan in plans:
        corners = positions[plan.vertex_ids]
        near = ((positions[candidates] >= corners.min(axis=0) - tol).all(axis=1)
                & (positions[candidates] <= corners.max(axis=0) + tol).all(axis=1))
        local = candidates[near]
        added: list[int] = []
        for piece in plan.pieces:
            present = {int(v) for ring in piece.rings for v in ring}
            rings = []
            for ring in piece.rings:
                ids = [int(v) for v in ring]
                out: list[int] = []
                for k, a in enumerate(ids):
                    b = ids[(k + 1) % len(ids)]
                    out.append(a)
                    on = [int(v) for v in _inside_segment(positions, local, a, b, tol)
                          if int(v) not in present]
                    if on:
                        out.extend(on)
                        present.update(on)
                        added.extend(on)
                        plan.threaded.append((a, b, on))
                rings.append(np.array(out, np.int64))
            piece.rings = rings
        _extend_plan(plan, positions, added)


def _inside_segment(positions: np.ndarray, candidates: np.ndarray, a: int, b: int,
                    tol: float) -> np.ndarray:
    """The ids of `candidates` within `tol` of the interior of segment `a`-`b`, ordered from `a`
    to `b` (ties on the lower id): `engine.topo.adjacency.find_t_vertices`' own test, for one
    segment."""
    start, along = positions[a], positions[b] - positions[a]
    denom = float(along @ along)
    if denom == 0.0 or not len(candidates):
        return np.zeros(0, np.int64)
    rel = positions[candidates] - start
    t = rel @ along / denom
    distance = np.linalg.norm(rel - np.outer(t, along), axis=1)
    hit = ((t > 1e-9) & (t < 1 - 1e-9) & (distance <= tol)
           & (candidates != a) & (candidates != b))
    ids, t = candidates[hit], t[hit]
    return ids[np.lexsort((ids, t))]


def _extend_plan(plan: _Plan, positions: np.ndarray, ids) -> None:
    """Add `ids` to the plan's projected vertices, in its own frame. Rows already there are kept
    bit for bit, so nothing the plan computed from them changes."""
    ids = np.setdiff1d(np.asarray(ids, np.int64), plan.vertex_ids)
    if not len(ids):
        return
    every = np.concatenate([plan.vertex_ids, ids])
    xy = np.vstack([plan.vertex_xy, (positions[ids] - plan.origin) @ plan.basis])
    order = np.argsort(every, kind="stable")
    plan.vertex_ids, plan.vertex_xy = every[order], xy[order]


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
    rings: list[tuple[_Plan, np.ndarray]] = []
    for plan in plans:
        whole = plan.region in kept_whole
        for piece in plan.pieces:
            for ring in piece.rings:
                if whole or len(ring) < 3:
                    needed[ring] = True
                else:
                    rings.append((plan, ring))

    # `forced` is frozen BEFORE any ring is simplified, so no ring's own result can move another
    # ring's anchors: the decision stays global, and independent of the order plans arrive in.
    forced = needed.copy()
    forced[_divergent_vertices(rings)] = True
    for plan, ring in rings:
        xy = plan.vertex_xy[np.searchsorted(plan.vertex_ids, ring)]
        needed[ring[_ring_keep(xy, ring, forced[ring], collinear_tol)]] = True
    return needed


def _divergent_vertices(rings: list[tuple[_Plan, np.ndarray]]) -> np.ndarray:
    """Every vertex whose two ring NEIGHBOURS are not the same in every ring that contains it --
    the points where two regions' borders part company, plus any vertex a single ring visits
    twice (a pinch).

    The per-vertex corner test this replaced was symmetric by accident: a vertex's verdict
    depended only on itself and its two ring neighbours, which are the same pair (reversed) in
    both rings sharing a border, so both sides always agreed. Ramer-Douglas-Peucker is NOT local
    -- what it keeps along a stretch depends on that stretch's endpoints -- so two regions only
    stay in step if they simplify a shared stretch between the SAME endpoints. Anchoring both
    sides on the vertices where their rings diverge restores that guarantee, and no new
    T-junction can appear."""
    seen: dict[int, frozenset] = {}
    out: set[int] = set()
    for _plan, ring in rings:
        for v, a, b in zip(ring, np.roll(ring, 1), np.roll(ring, -1)):
            pair = frozenset((int(a), int(b)))
            if seen.setdefault(int(v), pair) != pair:
                out.add(int(v))
    return np.array(sorted(out), np.int64)


def _ring_keep(xy: np.ndarray, ids: np.ndarray, forced: np.ndarray, tol: float) -> np.ndarray:
    """Which rows of one CLOSED ring survive Ramer-Douglas-Peucker at `tol` (a bool mask).

    A vertex is dropped only if the WHOLE original polyline between the neighbours that SURVIVE
    stays within `tol` of the chord replacing it -- which is what the guard's ring test assumes
    and what testing each vertex against its own two neighbours could not promise: a run of
    nearly-collinear vertices was dropped one at a time, each step legal on its own, and the
    final chord could end up arbitrarily far from the original boundary.

    `forced` vertices always survive and cut the ring into runs that are simplified
    independently. With fewer than two of them the ring is anchored on its own lowest vertex id
    and the vertex farthest from it, so the result never depends on where the union happened to
    start the ring. Every tie -- equal distances at a split -- is broken on the lowest vertex id,
    which is also what makes a shared stretch simplify identically from either direction."""
    n = len(xy)
    keep = np.asarray(forced, bool).copy()
    anchors = np.flatnonzero(keep).tolist()
    if len(anchors) < 2:
        start = anchors[0] if anchors else int(np.argmin(ids))
        anchors = sorted({start, _farthest(xy, ids, start)})
        if len(anchors) < 2:
            keep[start] = True
            return keep
        keep[anchors] = True
    for i, a in enumerate(anchors):
        b = anchors[(i + 1) % len(anchors)]
        run = (a + np.arange(((b - a) % n) + 1)) % n
        _rdp(xy, ids, run, tol, keep)
    return keep


def _farthest(xy: np.ndarray, ids: np.ndarray, start: int) -> int:
    d = np.linalg.norm(xy - xy[start], axis=1)
    cand = np.flatnonzero(d == d.max())
    return int(cand[np.argmin(ids[cand])])


def _rdp(xy: np.ndarray, ids: np.ndarray, run: np.ndarray, tol: float, keep: np.ndarray) -> None:
    """Mark in `keep` the rows of one OPEN run (`run`, row indices into `xy`) that survive
    Ramer-Douglas-Peucker at `tol`. Iterative, so a ring of any length is safe."""
    keep[run[0]] = keep[run[-1]] = True
    stack = [(0, len(run) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        inner = run[lo + 1:hi]
        d = _segment_distance(xy[inner], xy[run[lo]], xy[run[hi]])
        worst = d.max()
        if worst <= tol:
            continue
        cand = np.flatnonzero(d == worst)
        split = lo + 1 + int(cand[np.argmin(ids[inner][cand])])
        keep[run[split]] = True
        stack.append((lo, split))
        stack.append((split, hi))


def _segment_distance(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance from each point to the SEGMENT `a`-`b`, not to its infinite line -- so a vertex
    the boundary doubles back past is far from the chord, exactly as the old corner test's
    `along < 0 or > 1` check treated it."""
    ab = b - a
    denom = float(ab @ ab)
    if denom == 0.0:
        return np.linalg.norm(points - a, axis=1)
    t = np.clip((points - a) @ ab / denom, 0.0, 1.0)
    return np.linalg.norm(points - (a + t[:, None] * ab), axis=1)


# ----------------------------------------------------------- pass 2: rebuild and re-triangulate


def _ring_ccw(plan: _Plan, ring: np.ndarray) -> np.ndarray:
    """`ring` (welded ids), reversed if needed so its signed area in the region's own `(e1, e2)`
    frame is positive -- CCW as seen from the side the region normal points to, matching `_wound`'s
    per-triangle convention (`plane_basis` returns a right-handed frame, `cross(e1, e2) == n`)."""
    rows = np.searchsorted(plan.vertex_ids, ring)
    xy = plan.vertex_xy[rows]
    area = 0.5 * float(np.sum(xy[:, 0] * np.roll(xy[:, 1], -1) - np.roll(xy[:, 0], -1) * xy[:, 1]))
    return ring if area >= 0.0 else ring[::-1]


def _region_loops(plan: _Plan, kept: list, welded_to_original: np.ndarray):
    """The kept loops of `plan` as ORIGINAL vertex ids -- `{"outer": ids, "inners": [ids, ...]}`
    -- or `None` when the region is more than one disjoint piece (there is then no single outer
    loop to name) or its outer loop keeps fewer than 3 vertices.

    `kept` is the region's rings per piece exactly as its triangles were built from them
    (`merge_regions`): the FULL rings when the region took the `keep_all` fallback in the round
    that produced `builds`, the simplified ones otherwise, each with every vertex `_thread_output`
    threaded into it. A region that reaches `builds` always has at least 3 kept vertices in EVERY
    ring -- `_polygon` rejects anything less and the region falls back to `keep_all` or is
    skipped -- so no inner loop can arrive here degenerate.

    `_ring_ccw` orients a loop CCW in the region's own frame; hole loops are then reversed, so
    the result is the outer-CCW / holes-CW convention a polygon consumer expects."""
    if len(kept) != 1:
        return None
    rings = kept[0]
    if len(rings[0]) < 3:
        return None
    return {"outer": welded_to_original[_ring_ccw(plan, rings[0])],
            "inners": [welded_to_original[_ring_ccw(plan, r)[::-1]] for r in rings[1:]]}


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
    feedback event `merge_regions` reruns for.

    Rule 9 has two parts. PER REGION, the rebuilt triangles may exceed the original faces by at
    most the boundary movement rule 6 has already accepted for the same ring, `collinear_tol *
    perimeter` plus the relative slack -- the same bound because it is the same movement, only
    measured against the original faces instead of their union. OVER THE PASS, the regions that
    build may not add up to more than they started with, beyond the relative slack. Simplifying
    a border two regions SHARE moves area from one to the other and nowhere else, so the pair
    nets to zero and both keep the simplification; a region that grows along an OPEN border has
    no neighbour paying for it, the pass as a whole grows, and every region that grew is then
    fed back as `area_grew`, exactly as the old per-region rule did unconditionally. Either way
    the regions that ship never total more than the faces they replace, which is what
    `engine.fixes.pipeline`'s `area_not_grown` invariant relies on: the check that used to be
    per region is now per pass, and it is still made before anything is emitted."""
    builds: list[tuple[_Plan, list]] = []
    growth: list[float] = []
    late: dict[int, str] = {}
    keep_all: list[int] = []
    for plan in plans:
        tris, note = _triangulate(plan, needed, collinear_tol)
        if tris is None:
            late[plan.region] = note
            continue
        grown = _signed_area_sum(plan.vertex_xy, plan.vertex_ids, tris) - plan.original_area
        perimeter = sum(piece.union_perimeter for piece in plan.pieces)
        if grown > _AREA_REL_TOL * plan.original_area + collinear_tol * perimeter:
            late[plan.region] = "area_grew"
            continue
        if note == "keep_all":
            keep_all.append(plan.region)
        builds.append((plan, tris))
        growth.append(grown)

    if sum(growth) > _AREA_REL_TOL * sum(plan.original_area for plan, _tris in builds):
        grew = [g > _AREA_REL_TOL * plan.original_area for (plan, _tris), g in zip(builds, growth)]
        late.update((plan.region, "area_grew") for (plan, _tris), g in zip(builds, grew) if g)
        builds = [build for build, g in zip(builds, grew) if not g]
        growth = [g for g, did in zip(growth, grew) if not did]
        keep_all = [region for region in keep_all if region not in late]
    max_area_rel_error = max((abs(g) / max(plan.original_area, 1e-300)
                              for (plan, _tris), g in zip(builds, growth)), default=0.0)
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


# ------------------------------------------------------------ T-junctions left in the output


def _thread_output(topo: Topology, builds: list, copied: list[int], kept: dict[int, list],
                   tol: float):
    """Thread every vertex the output uses into every output edge it lies on, and repeat until
    no edge has one or `MAX_THREAD_ROUNDS` is reached. Returns `(builds, copied_split,
    split_edges)`.

    The output is the triangles of `builds` and the faces in `copied`. A round finds, with
    `find_t_vertices` at `tol` over its non-degenerate triangles, every edge that has a used
    vertex on its interior, and splits every non-degenerate triangle holding such an edge into a
    fan from the corner opposite it (`_split`): each piece is wound like the triangle it came
    from, the pieces cover exactly that triangle, and no vertex is moved or invented -- the
    surface is unchanged, only its edges are cut. A merged region's ring edge -- two consecutive
    vertices of `kept[region]`, its kept rings per piece -- takes the vertices into the ring as
    well, so the polygon passes through them; a diagonal inside the region does not (the vertex
    stands inside the polygon, where a wall's foot needs no ring vertex, see `_needed_vertices`).
    The new edges run through a triangle's interior, where a vertex another face uses can lie,
    which is what the next round is for.

    `builds` comes back with the split triangles and every vertex they use added to each plan
    (`_extend_plan`); `kept` is updated in place. `copied_split` maps each copied face that was
    split to its pieces as welded triples; a zero-area face is never split (it covers nothing).
    `split_edges` is every split edge, as a sorted vertex pair."""
    positions = topo.positions_w
    tris = [[tuple(int(v) for v in t) for t in triangles] for _plan, triangles in builds]
    faces = sorted(set(int(f) for f in copied))
    pieces = {f: [tuple(int(v) for v in topo.face_w[f])] for f in faces}
    split_edges: set[tuple[int, int]] = set()
    for _round in range(MAX_THREAD_ROUNDS):
        rows = [t for triangles in tris for t in triangles] + [t for f in faces for t in pieces[f]]
        face_w = np.array(rows, np.int64).reshape(-1, 3)
        ok = ~degenerate_mask(positions, face_w)
        table = build_edge_table(face_w, ok)
        hits = find_t_vertices(positions, table, tol)
        if not hits:
            break
        on_edge = {(int(table.edges[e][0]), int(table.edges[e][1])): [int(v) for v in hits[e]]
                   for e in sorted(hits)}
        split_edges.update(on_edge)
        valid = iter(ok.tolist())
        for i, (plan, _triangles) in enumerate(builds):
            kept[plan.region] = [[_thread_ring(ring, on_edge) for ring in piece]
                                 for piece in kept[plan.region]]
            tris[i] = [s for t in tris[i] for s in (_split(t, on_edge) if next(valid) else [t])]
        for f in faces:
            pieces[f] = [s for t in pieces[f] for s in (_split(t, on_edge) if next(valid) else [t])]
    out = []
    for (plan, _triangles), triangles in zip(builds, tris):
        used = [v for t in triangles for v in t]
        used += [int(v) for piece in kept[plan.region] for ring in piece for v in ring]
        _extend_plan(plan, positions, used)
        out.append((plan, triangles))
    return out, {f: pieces[f] for f in faces if len(pieces[f]) > 1}, split_edges


def _between(on_edge: dict, p: int, q: int) -> list[int]:
    """The vertices `on_edge` lists for edge `p`-`q`, in order from `p` to `q` (`[]` if none)."""
    verts = on_edge.get((min(p, q), max(p, q)), [])
    return list(verts) if p < q else list(verts)[::-1]


def _split(tri: tuple, on_edge: dict) -> list[tuple]:
    """`tri` cut at every vertex `on_edge` lists for one of its edges: a fan from the corner
    opposite that edge, each piece split again at the vertices listed for its own edges. It ends:
    each cut makes a listed vertex a corner, and a piece of the cut edge lists nothing, since the
    vertices strictly inside the whole edge are all in its own list. Every piece keeps `tri`'s
    winding -- a vertex strictly inside `p`-`q` makes `(p, w, r)` and `(w, q, r)` turn the way
    `(p, q, r)` does."""
    for k in range(3):
        p, q, r = tri[k], tri[(k + 1) % 3], tri[(k + 2) % 3]
        on = [v for v in _between(on_edge, p, q) if v != r]
        if on:
            chain = [p, *on, q]
            return [s for i in range(len(chain) - 1)
                    for s in _split((chain[i], chain[i + 1], r), on_edge)]
    return [tri]


def _thread_ring(ring: np.ndarray, on_edge: dict) -> np.ndarray:
    """`ring` with the vertices `on_edge` lists for each of its segments inserted in order."""
    ids = [int(v) for v in ring]
    out: list[int] = []
    for k, p in enumerate(ids):
        out.append(p)
        out.extend(_between(on_edge, p, ids[(k + 1) % len(ids)]))
    return np.array(out, np.int64)


def _barycentric(point: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """The weights of `corners` (a `(3, 3)` triangle) that give `point`, which lies on it."""
    a, b, c = corners
    v0, v1, v2 = b - a, c - a, point - a
    d00, d01, d11 = float(v0 @ v0), float(v0 @ v1), float(v1 @ v1)
    d20, d21 = float(v2 @ v0), float(v2 @ v1)
    den = d00 * d11 - d01 * d01
    u = (d11 * d20 - d01 * d21) / den
    v = (d00 * d21 - d01 * d20) / den
    return np.array([1.0 - u - v, u, v])


# ------------------------------------------------------------------------------ output assembly


def _assemble(mesh: MeshData, topo: Topology, welded_to_original: np.ndarray,
              builds: list, copied: list[int], flat: frozenset,
              region_rings: dict[int, np.ndarray] | None = None,
              copied_split: dict[int, list] | None = None) -> MergeResult:
    """Emit faces ordered by the lowest original face index of their group, so a merged region
    lands where its first member was and untouched faces keep their relative order.

    A copied face in `copied_split` (`_thread_output`) is emitted as its pieces, in order, each
    with the face's own material, line and source. A corner that is one of the face's own keeps
    its `v`/`vt`/`vn` exactly; a threaded vertex gets its lowest original row and, when the face
    carries them, a NEW `vt` and `vn` row interpolated at it from the face's three corners, so
    the texture lies on the pieces exactly as it lay on the face."""
    region_rings = region_rings or {}
    copied_split = copied_split or {}
    uvs = [mesh.uvs] if len(mesh.uvs) else []
    normals = [mesh.normals] if len(mesh.normals) else []
    next_uv = len(mesh.uvs)
    next_normal = len(mesh.normals)

    emitted: list[tuple] = []
    for face in sorted(set(copied)):
        material, line = int(mesh.face_material[face]), int(mesh.face_line[face])
        if face not in copied_split:
            emitted.append((int(face), mesh.face_v[face], mesh.face_vt[face], mesh.face_vn[face],
                            material, line, np.array([face], np.int64), -1))
            continue
        corners = [int(w) for w in topo.face_w[face]]
        vt, vn = mesh.face_vt[face], mesh.face_vn[face]
        new_vt: dict[int, int] = {}
        new_vn: dict[int, int] = {}
        for piece in copied_split[face]:
            rows = []
            for w in piece:
                if w in corners:
                    j = corners.index(w)
                    rows.append((int(mesh.face_v[face][j]), int(vt[j]), int(vn[j])))
                    continue
                weights = _barycentric(topo.positions_w[w], topo.positions_w[corners])
                if w not in new_vt and (vt >= 0).all():
                    new_vt[w] = next_uv
                    uvs.append((weights @ mesh.uvs[vt])[None, :])
                    next_uv += 1
                if w not in new_vn and (vn >= 0).all():
                    if len(set(vn.tolist())) == 1:
                        new_vn[w] = int(vn[0])
                    else:
                        n = weights @ mesh.normals[vn]
                        normals.append((n / np.linalg.norm(n))[None, :])
                        new_vn[w] = next_normal
                        next_normal += 1
                rows.append((int(welded_to_original[w]), new_vt.get(w, -1), new_vn.get(w, -1)))
            emitted.append((int(face), np.array([r[0] for r in rows], np.int64),
                            np.array([r[1] for r in rows], np.int64),
                            np.array([r[2] for r in rows], np.int64),
                            material, line, np.array([face], np.int64), -1))

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
                       report={"faces_copied": len(set(copied))}, rings=rings,
                       face_region=np.array([r[7] for r in emitted], np.int64))


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
