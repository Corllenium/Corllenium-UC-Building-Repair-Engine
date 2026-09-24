"""Stray fragments and attached slivers: geometry that is not part of anything.

WHAT THIS IS FOR. A SketchUp export carries debris the rest of the pipeline cannot touch. The
hidden-face pass only ever removes what nobody can see, and a stray is usually plainly VISIBLE --
a triangle left where something was deleted, a scrap of a component that was moved away, a needle
too thin to be a surface. The merge cannot dissolve it either, because it is its own region.

So this step is different in kind from every other one here: it deletes geometry a person can
see, on the strength of a size argument, and its guard therefore has to be different too. The
removal runs under a FRAGMENT-mode guard (`engine.guard.compare.fragment_feedback`) whose only
permitted change is a pixel whose BEFORE first hit was one of these very faces AND where AFTER
now shows the sky or a side of a face that was already an outside surface -- never the inside of
a closed shell. Any other failing pixel a candidate was involved in -- one the BEFORE ray met in
front of what AFTER now shows -- puts that candidate back.

THAT GUARD SEES PIXELS, AND DEBRIS IS SMALLER THAN A PIXEL. At the real files' 900 x 600 guard
renders a pixel spans 1.5 to 3.5 in, so a 0.26 in strip or a 1 in triangle is met by a guard ray
only now and then, and most of what this detector names is never judged at all (file A's 19
removed faces covered 24 pixels in 26 views). So the DETECTOR is the defence that has to hold on
its own: it may only name what cannot be a piece of the visible surface, whatever the guard
happens to see.

TWO SHAPES OF DEBRIS, and they are found differently.

A FRAGMENT is a whole connected component -- components are taken over SHARED WELDED EDGES, and
also across the two other ways a real surface is joined in these exports:

  * a T-JUNCTION -- a vertex lying on another face's edge, within `contact_tol`, the tolerance
    `engine.pipeline.analyse_topology` finds T-junctions with (both real files are full of them:
    353 on A and 363 on B at the merge input). Review C2's probe: a 3 x 1 in patch of a slab's
    walking surface met the rest of the top ONLY through T-junctions, was its own 3 sq in
    component, was removed as debris, and a hole shipped with `passed` True. Measured on file A:
    face 3703, a 1.4 x 0.6 in triangle of a side wall joined to it by 2 T-junctions and 5 shared
    vertices, was removed the same way and left a hole onto the unexposed inside;
  * COPLANAR CONTACT -- two faces lying in one plane (each one's corners within `contact_tol` of
    the other's plane) whose triangles touch or overlap there within `contact_tol`: a painted
    mark lying on a surface, a patch whose corners sit inside its neighbour.

Two faces that merely touch at a vertex out of plane, or cross without sharing an edge, are still
separate. A component is a candidate when any one of these holds:

  * its total area is below `FixProfile.fragment_max_area` (4 in^2), or
  * it is a single face, or
  * its longest bounding-box extent is below `FixProfile.fragment_max_extent` (6 in),

and NEVER when it contains a face bigger than `fragment_max_area` on its own. That last rule is
not a refinement, it is what makes the other three safe: a 5 x 4 in panel is under the extent
threshold on every axis, and a rule without it would delete a real panel for being small. A
component that survives all of this is reported with its size, so the thresholds can be argued
with against real numbers rather than asserted.

A SLIVER is a single face inside a component that is NOT a fragment candidate -- so, attached to
something real -- that is THIN and lies on a BORDER. Thin: its polygon quality
`4 * pi * area / perimeter^2` is below `FixProfile.sliver_q` (0.02), its own area is at most
`fragment_max_area`, and its WIDTH -- twice its area over its longest edge, the furthest any point
of it lies from that edge -- is at most `max_width`. That quality is 1 for a circle and about 0.6
for an equilateral triangle; 0.02 is a needle roughly 1:150. On a border: one of its LONG edges
is OPEN (below). It is reported separately from fragments because it is a different claim: a
fragment is debris, a sliver is a real surface's ragged edge.

A SLIVER IS A RAGGED BORDER, NEVER A STRIP OF THE MIDDLE. Removing a face through one of its
edges moves the border that edge belonged to onto the face's two other edges, and no point of the
face lies further from those than the opposite corner's height over the removed edge. So a thin
face with an OPEN LONG edge -- one whose opposite corner lies within `max_width` of it, that no
other face uses, and that has no T-junction partner (no other face's vertex lies inside it, and it
lies inside no other face's edge) -- is a ragged border, and removing it moves that border by at
most `max_width`. A thin face whose long edges are all shared or T-joined is a strip of the
surface's MIDDLE, and removing it opens a SLIT onto whatever lies behind. Every lost point still
lies within the strip's width of the surface left on either side, so the final guard's
border-shift measurement (a clearance to the nearest triangle) would excuse the slit, and at the
real files' guard size no guard ray meets it at all. Review 2a C1: a 29.5 in strip 0.05 to 0.14 in
wide, sandwiched in the top of a 2000 in slab, was removed with `passed` True, and 97 of 97 rays
cast down it fell through onto the inside of the bottom. Such a face is counted
(`n_sandwiched_thin_faces`) and kept; inside a flat region the merge's re-triangulation dissolves
it anyway, with no area lost. A needle whose only open edge is its SHORT end is sandwiched too:
removing it would open a crack as long as the needle, which is why only a long edge counts.

A PARTNER BELONGS TO ONE EDGE. A face thinner than `contact_tol` has all three of its edges
within `contact_tol` of each other, so a vertex or edge of another face that lies on one of them
lies "on" all three by the tolerance alone. Each is therefore given to the edge of the thin face
it lies NEAREST, and a face's own corners are never partners of its own edges.

`max_width` IS THE MERGE'S OWN BORDER TOLERANCE, derived per mesh by the caller
(`engine.fixes.pipeline.sliver_width_bound`: `default_collinear_tol`, clamped exactly like the
final guard's border-shift tolerance): the distance the merge itself may move a border, and the
displacement the final guard measures and excuses as a border shift -- 0.15 in on both real
files. It used to be the constant 0.15, right for the real files' 0.1 in print step and 1,000
times too wide for a model printed to 1e-4 in. Before any width bound the rule named real
surface: measured on the solidified references, the slivers it removed were 0.0007 to 0.047 in
wide except six strips of real surface 0.19 to 0.26 in wide and 30 to 40 in long -- file A's faces
3203 and 3401 inside an underside, file B's faces 692, 698, 1804 and 2734 inside walls (692 and
698 are the two faces of one wall, so removing both left a see-through slit). The guard met none
of them: they are a fraction of a pixel wide.

THE AREA BOUND IS NOT AN EXTRA THRESHOLD, it is the same one the component rule already applies
("never a component holding a face bigger than `fragment_max_area` on its own"), and leaving it
off was a defect. The quality ratio is SCALE-FREE: a 630 x 4 in strip of real sidewalk scores
0.006, deeper into "needle" than a 1 in whisker, because it is long rather than because it is
thin. Measured on file A's solidified reference: 285 faces score under 0.02 and the largest of
them are 391 to 793 sq in -- surfaces nobody would call debris. The fragment guard permits a
candidate's own pixel wherever AFTER shows the sky or an already-exposed side, and a long strip
at the model's edge, removed, shows exactly that -- so it would have removed a 793 sq in strip
without a murmur. A detector whose guard cannot second-guess it has to be the conservative one.

Deterministic: components are numbered in ascending face order, every loop is over a sorted list,
and no random number is drawn.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.topo.adjacency import build_edge_table, edge_face_lists, find_t_vertices

#: How many of the components the size rules did NOT catch are listed in the report, smallest
#: first. Bounded so `report.json` stays a fixed size on a model with thousands of components,
#: and smallest-first because those are the ones near the threshold.
_KEPT_REPORTED = 10

#: Candidate pairs `_box_pairs` tests at once in the coplanar-contact search. It bounds each
#: block's own index arrays (the pairs that overlap along x, before the y and z test) however many
#: long faces overlap one another along x -- NOT the result: every pair that overlaps on all three
#: axes is kept and concatenated, and `_coplanar_contacts` then measures all of them at once.
#: Measured with tracemalloc on the detector's own input (brief 08): file A, 2,644 faces after the
#: hidden pass, 32,089 overlapping box pairs, 10,653 in contact, a peak of 6.3 MB for the whole
#: `_coplanar_contacts` call in 0.07 s; file B, 4,773 faces, 46,942 pairs, 12.2 MB.
_PAIR_BLOCK = 2_000_000


@dataclass
class FragmentResult:
    #: Bool over the faces handed in: this face's whole component is a fragment candidate.
    fragments: np.ndarray
    #: Bool over the faces handed in: an attached sliver candidate. Disjoint from `fragments` --
    #: a face in a fragment component is never also reported as a sliver.
    slivers: np.ndarray
    #: Per face, its connected-component id (always >= 0; every face is in some component).
    component: np.ndarray
    report: dict


class _UnionFind:
    def __init__(self, n: int):
        self.parent = np.arange(n)

    def find(self, a: int) -> int:
        parent = self.parent
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return int(a)

    def union(self, a: int, b: int) -> bool:
        """Join the sets of `a` and `b`; True when they were two sets."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[max(ra, rb)] = min(ra, rb)
        return True

    def labels(self) -> np.ndarray:
        """Set ids numbered from 0 in ascending order of each set's lowest member -- a property
        of the sets, not of the order the unions happened in."""
        out = np.full(len(self.parent), -1, np.int64)
        seen: dict[int, int] = {}
        for f in range(len(self.parent)):
            out[f] = seen.setdefault(self.find(f), len(seen))
        return out


def _unit_normals(tri: np.ndarray) -> np.ndarray:
    """`(F, 3)` unit normals, all-zero for a triangle with no area."""
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normal, axis=1)
    out = np.zeros_like(normal)
    good = length > 0.0
    out[good] = normal[good] / length[good, None]
    return out


def _box_pairs(lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """`(K, 2)` pairs of indices whose axis-aligned boxes `[lo, hi]` overlap on all three axes,
    each pair once: a sweep along x (sorted by `lo[:, 0]`, stable), `_PAIR_BLOCK` pairs at a time."""
    n = len(lo)
    if n < 2:
        return np.zeros((0, 2), np.int64)
    order = np.argsort(lo[:, 0], kind="stable")
    lo_s, hi_s = lo[order], hi[order]
    # every j after i in x order whose box starts before i's ends overlaps it along x
    count = np.maximum(np.searchsorted(lo_s[:, 0], hi_s[:, 0], side="right") - np.arange(n) - 1, 0)
    out = []
    block = max(1, _PAIR_BLOCK // n)
    for start in range(0, n, block):
        i = np.arange(start, min(start + block, n))
        c = count[i]
        ii = np.repeat(i, c)
        jj = ii + 1 + np.arange(int(c.sum())) - np.repeat(np.cumsum(c) - c, c)
        ok = ((lo_s[jj, 1] <= hi_s[ii, 1]) & (lo_s[ii, 1] <= hi_s[jj, 1])
              & (lo_s[jj, 2] <= hi_s[ii, 2]) & (lo_s[ii, 2] <= hi_s[jj, 2]))
        out.append(np.stack([order[ii[ok]], order[jj[ok]]], axis=1))
    return np.concatenate(out).astype(np.int64)


def _cross2(o: np.ndarray, u: np.ndarray, p: np.ndarray) -> np.ndarray:
    """z of `(u - o) x (p - o)` for 2-D points, broadcast over leading axes."""
    return (u[..., 0] - o[..., 0]) * (p[..., 1] - o[..., 1]) - (u[..., 1] - o[..., 1]) * (p[..., 0] - o[..., 0])


def _inside(points: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """`(K, 3)`: is each of `points` `(K, 3, 2)` inside or on the 2-D triangle `tri` `(K, 3, 2)`?"""
    a, b, c = (tri[:, k][:, None] for k in range(3))
    s1, s2, s3 = _cross2(a, b, points), _cross2(b, c, points), _cross2(c, a, points)
    return ((s1 >= 0) & (s2 >= 0) & (s3 >= 0)) | ((s1 <= 0) & (s2 <= 0) & (s3 <= 0))


def _point_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    length2 = np.einsum("ij,ij->i", ab, ab)
    t = np.clip(np.einsum("ij,ij->i", p - a, ab) / np.where(length2 > 0.0, length2, 1.0), 0.0, 1.0)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def _triangle_gap(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """`(K,)` distance between the 2-D triangles `A[k]` and `B[k]` (`(K, 3, 2)` each): 0 where
    they overlap or touch -- a corner of one inside the other, or two sides crossing -- else the
    shortest corner-to-side distance between them."""
    gap = np.where(_inside(B, A).any(axis=1) | _inside(A, B).any(axis=1), 0.0, np.inf)
    for i in range(3):
        p1, p2 = A[:, i], A[:, (i + 1) % 3]
        for j in range(3):
            q1, q2 = B[:, j], B[:, (j + 1) % 3]
            crossing = ((_cross2(q1, q2, p1) * _cross2(q1, q2, p2) < 0.0)
                        & (_cross2(p1, p2, q1) * _cross2(p1, p2, q2) < 0.0))
            ends = np.minimum.reduce([_point_segment(p1, q1, q2), _point_segment(p2, q1, q2),
                                      _point_segment(q1, p1, p2), _point_segment(q2, p1, p2)])
            gap = np.minimum(gap, np.where(crossing, 0.0, ends))
    return gap


def _coplanar_contacts(positions_w: np.ndarray, face_w: np.ndarray, tol: float) -> np.ndarray:
    """`(K, 2)` face pairs in COPLANAR CONTACT: both non-degenerate, each one's three corners
    within `tol` of the other's plane, and their triangles, laid in the first one's plane, no
    further than `tol` apart. Only pairs whose boxes (grown by `tol`) overlap are measured."""
    tri = positions_w[face_w]
    normal = _unit_normals(tri)
    pairs = _box_pairs(tri.min(axis=1) - tol, tri.max(axis=1) + tol)
    if not len(pairs):
        return pairs
    a, b = pairs[:, 0], pairs[:, 1]
    good = (np.linalg.norm(normal[a], axis=1) > 0.0) & (np.linalg.norm(normal[b], axis=1) > 0.0)
    offset = -np.einsum("ij,ij->i", normal, tri[:, 0])
    off_a = np.abs(np.einsum("kij,kj->ki", tri[b], normal[a]) + offset[a][:, None]).max(axis=1)
    off_b = np.abs(np.einsum("kij,kj->ki", tri[a], normal[b]) + offset[b][:, None]).max(axis=1)
    pairs = pairs[good & (off_a <= tol) & (off_b <= tol)]
    if not len(pairs):
        return pairs
    a, b = pairs[:, 0], pairs[:, 1]
    n = normal[a]
    axis = np.eye(3)[np.argmin(np.abs(n), axis=1)]
    e1 = np.cross(n, axis)
    e1 /= np.linalg.norm(e1, axis=1)[:, None]
    e2 = np.cross(n, e1)
    flat_a = np.stack([np.einsum("kij,kj->ki", tri[a], e1), np.einsum("kij,kj->ki", tri[a], e2)], axis=-1)
    flat_b = np.stack([np.einsum("kij,kj->ki", tri[b], e1), np.einsum("kij,kj->ki", tri[b], e2)], axis=-1)
    return pairs[_triangle_gap(flat_a, flat_b) <= tol]


@dataclass
class _EdgeTables:
    """The edge tables both the components and the sliver rule read, built once: `table` over
    every face; `t_table` over the faces with three distinct corners (a repeated corner is an edge
    of no length, which has no inside for a vertex to lie on), or `None` when there is none; and
    `t_vertices`, `engine.topo.adjacency.find_t_vertices` over `t_table` at `contact_tol` -- the
    search `analyse_topology` runs -- `{t_table edge: vertices inside it}`."""
    table: object
    t_table: object
    t_vertices: dict


def _edge_tables(positions_w: np.ndarray, face_w: np.ndarray, contact_tol: float) -> _EdgeTables:
    n = len(face_w)
    table = build_edge_table(face_w, np.ones(n, dtype=bool))
    distinct = ((face_w[:, 0] != face_w[:, 1]) & (face_w[:, 1] != face_w[:, 2])
                & (face_w[:, 0] != face_w[:, 2]))
    t_table = build_edge_table(face_w, distinct) if distinct.any() else None
    t_vertices = find_t_vertices(positions_w, t_table, contact_tol) if t_table is not None else {}
    return _EdgeTables(table, t_table, t_vertices)


def _components(positions_w: np.ndarray, face_w: np.ndarray, contact_tol: float,
                tables: _EdgeTables) -> tuple[np.ndarray, dict]:
    """Connected components of `face_w`, numbered from 0 in ascending order of their lowest face
    id, over SHARED WELDED EDGES, T-JUNCTIONS (a vertex within `contact_tol` of the inside of
    another face's edge -- `engine.topo.adjacency.find_t_vertices`, the search
    `analyse_topology` runs) and COPLANAR CONTACT (`_coplanar_contacts`). Also returns how many
    components shared edges alone made and how many joins each contact rule added."""
    n = len(face_w)
    sets = _UnionFind(n)
    stats = {"n_components_by_shared_edges": 0, "n_joined_by_tjunction": 0,
             "n_joined_by_coplanar_contact": 0}
    if not n:
        return np.zeros(0, np.int64), stats
    faces_of_edge = edge_face_lists(tables.table)
    for group in faces_of_edge:
        for f in group[1:]:
            sets.union(int(group[0]), int(f))
    stats["n_components_by_shared_edges"] = int(len(set(sets.find(f) for f in range(n))))

    corner = face_w.reshape(-1)
    owner = np.repeat(np.arange(n), 3)
    order = np.argsort(corner, kind="stable")
    vertices, first = np.unique(corner[order], return_index=True)
    faces_of_vertex = dict(zip(vertices.tolist(), np.split(owner[order], first[1:])))
    t_table, t_vertices = tables.t_table, tables.t_vertices
    faces_of_t_edge = edge_face_lists(t_table) if t_table is not None else []
    for e, on_edge in sorted(t_vertices.items()):
        edge_face = int(faces_of_t_edge[e][0])
        for v in on_edge.tolist():
            for f in faces_of_vertex[v].tolist():
                stats["n_joined_by_tjunction"] += sets.union(edge_face, f)

    for f, g in _coplanar_contacts(positions_w, face_w, contact_tol).tolist():
        stats["n_joined_by_coplanar_contact"] += sets.union(f, g)
    return sets.labels(), stats


def _face_area(positions_w: np.ndarray, face_w: np.ndarray) -> np.ndarray:
    tri = positions_w[face_w]
    return 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)


def _face_quality(positions_w: np.ndarray, face_w: np.ndarray) -> np.ndarray:
    """`4 * pi * area / perimeter**2` per face: 1 for a circle, ~0.6 for an equilateral triangle,
    towards 0 for a needle. A face with no perimeter at all (every vertex welded together) gets
    0.0, which is the honest answer -- it has no shape."""
    tri = positions_w[face_w]
    area = _face_area(positions_w, face_w)
    perimeter = np.linalg.norm(tri - np.roll(tri, -1, axis=1), axis=2).sum(axis=1)
    out = np.zeros(len(face_w), dtype=np.float64)
    good = perimeter > 0.0
    out[good] = 4.0 * np.pi * area[good] / perimeter[good] ** 2
    return out


def face_width(positions_w: np.ndarray, face_w: np.ndarray) -> np.ndarray:
    """Twice the area over the longest edge per face: the furthest any point of the triangle lies
    from that edge, so the most removing it can move the surface around it. 0.0 for a face with
    no extent at all."""
    tri = positions_w[face_w]
    longest = np.linalg.norm(tri - np.roll(tri, -1, axis=1), axis=2).max(axis=1)
    out = np.zeros(len(face_w), dtype=np.float64)
    good = longest > 0.0
    out[good] = 2.0 * _face_area(positions_w, face_w)[good] / longest[good]
    return out


def _to_segment(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """`(N,)` distance from each of `points` `(N, 3)` to the one segment `a`-`b`."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    return _point_segment(points, np.broadcast_to(a, points.shape), np.broadcast_to(b, points.shape))


def _open_long_edges(positions_w: np.ndarray, face_w: np.ndarray, faces: np.ndarray,
                     area: np.ndarray, max_width: float, tables: _EdgeTables) -> np.ndarray:
    """Per face of `faces`: has it a LONG edge -- one whose opposite corner lies within
    `max_width` of it -- that is an OPEN border: used by no other face, with no other face's
    vertex inside it, and lying inside no other face's edge? See the module docstring: a thin
    face that has one is a ragged border, and one that has none is a strip of the middle.

    A vertex or edge of another face that lies within `contact_tol` of this face's edges is the
    partner of the edge it lies NEAREST (a face thinner than `contact_tol` has all three edges
    within it of each other), and a face's own corners are never partners of its own edges."""
    table, t_table, t_vertices = tables.table, tables.t_table, tables.t_vertices
    users = {(int(a), int(b)): int(c) for (a, b), c in zip(table.edges, table.counts)}
    t_index: dict[tuple[int, int], int] = {}
    lies_on: dict[int, set[int]] = {}           # every t_table edge a vertex ends or lies inside
    if t_table is not None:
        for i, (a, b) in enumerate(t_table.edges.tolist()):
            t_index[(a, b)] = i
            lies_on.setdefault(a, set()).add(i)
            lies_on.setdefault(b, set()).add(i)
        for e, inside in t_vertices.items():
            for v in inside.tolist():
                lies_on.setdefault(v, set()).add(int(e))

    out = np.zeros(len(faces), dtype=bool)
    for n, f in enumerate(np.asarray(faces, dtype=np.int64).tolist()):
        corners = [int(v) for v in face_w[f]]
        tri = positions_w[corners]
        keys = [tuple(sorted((corners[k], corners[(k + 1) % 3]))) for k in range(3)]
        lengths = np.linalg.norm(tri - np.roll(tri, -1, axis=0), axis=1)
        own = {t_index[key] for key in keys if key in t_index}

        def to_sides(points: np.ndarray) -> np.ndarray:
            """`(N, 3)`: distance from each point to each of this face's three edges."""
            return np.stack([_to_segment(points, tri[k], tri[(k + 1) % 3]) for k in range(3)],
                            axis=1)

        for k, key in enumerate(keys):
            if lengths[k] <= 0.0 or 2.0 * float(area[f]) / lengths[k] > max_width:
                continue                                  # not an edge the face is thin along
            if users.get(key, 0) >= 2:
                continue                                  # shared: a neighbour lies across it
            e = t_index.get(key)
            inside = ([v for v in t_vertices[e].tolist() if v not in corners]
                      if e is not None and e in t_vertices else [])
            if inside:
                d = to_sides(positions_w[inside])
                if (d[:, k] <= d.min(axis=1)).any():
                    continue                              # another face's vertex inside it
            covered = False
            for g in sorted((lies_on.get(key[0], set()) & lies_on.get(key[1], set())) - own):
                g0, g1 = t_table.edges[g]
                reach = _to_segment(tri, positions_w[g0], positions_w[g1])    # per corner
                far = np.maximum(reach, np.roll(reach, -1))                     # per edge
                if far[k] <= far.min():
                    covered = True                        # it lies inside another face's edge
                    break
            if not covered:
                out[n] = True
                break
    return out


def detect_fragments(positions_w: np.ndarray, face_w: np.ndarray, profile, *,
                     contact_tol: float, max_width: float,
                     protected: np.ndarray | None = None) -> FragmentResult:
    """Find every stray-fragment and attached-sliver candidate in `face_w` (welded triangles into
    `positions_w`). See the module docstring for both rules.

    `contact_tol` (inches) is how close a vertex must come to another face's edge to be a
    T-junction, and two faces to one plane and to each other to be in coplanar contact;
    `engine.fixes.pipeline` passes the tolerance `analyse_topology` finds T-junctions with,
    `1.5 x` the mesh's coarsest print step. It has no default because it is a property of the
    mesh: 0 would join nothing that floating point does not place exactly.

    `max_width` (inches) is the widest a sliver may be -- how far removing one may move a border.
    `engine.fixes.pipeline` passes `sliver_width_bound`, the merge's own border tolerance; no
    default, for the same reason as `contact_tol`.

    `protected` (bool over the faces handed in; `None` protects nothing) marks faces this detector
    may never name: `engine.fixes.pipeline` passes the faces `engine.fixes.solidify` invented. A
    protected face is never a sliver, and a component holding one is never a fragment -- it is
    part of a shell solidify is closing, and taking only its original faces would leave invented
    ones hanging where nothing is. Measured on file A before this: face 4721, a bottom triangle
    solidify invented under face 174, was named a one-face stray and removed. A protected face
    still joins components and still counts as a neighbour across a sliver's edge.

    `profile` is an `engine.fixes.pipeline.FixProfile`, duck-typed like every other consumer in
    `engine.fixes`, so this package imports nothing from it. Nothing is removed here: the caller
    puts the candidates through `engine.guard.compare.fragment_feedback` first."""
    positions_w = np.asarray(positions_w, dtype=np.float64)
    face_w = np.asarray(face_w, dtype=np.int64)
    max_area = float(getattr(profile, "fragment_max_area", 4.0))
    max_extent = float(getattr(profile, "fragment_max_extent", 6.0))
    min_q = float(getattr(profile, "sliver_q", 0.02))
    max_width = float(max_width)
    bounds = {"contact_tol": float(contact_tol), "sliver_max_width": max_width}

    n = len(face_w)
    protected = (np.zeros(n, dtype=bool) if protected is None
                 else np.asarray(protected, dtype=bool).reshape(n))
    fragments = np.zeros(n, dtype=bool)
    slivers = np.zeros(n, dtype=bool)
    tables = _edge_tables(positions_w, face_w, float(contact_tol)) if n else None
    component, joins = _components(positions_w, face_w, float(contact_tol), tables)
    if not n:
        return FragmentResult(fragments, slivers, component,
                              {"n_components": 0, **joins, **bounds, "n_candidate_components": 0,
                               "n_protected_components": 0, "n_protected_faces": 0,
                               "n_above_threshold_components": 0, "n_fragment_faces": 0,
                               "n_thin_faces": 0, "n_sandwiched_thin_faces": 0,
                               "n_sliver_faces": 0, "smallest_kept_components": []})

    area = _face_area(positions_w, face_w)
    n_components = int(component.max()) + 1

    kept: list[dict] = []
    n_candidates = n_protected = 0
    for c in range(n_components):
        members = np.nonzero(component == c)[0]
        total = float(area[members].sum())
        corners = positions_w[face_w[members]].reshape(-1, 3)
        extent = float((corners.max(axis=0) - corners.min(axis=0)).max())
        biggest = float(area[members].max())

        candidate = (biggest <= max_area
                     and (total < max_area or len(members) == 1 or extent < max_extent))
        if candidate and protected[members].any():
            n_protected += 1                    # small, but a shell solidify is closing
        elif candidate:
            fragments[members] = True
            n_candidates += 1
        else:
            kept.append({"faces": int(len(members)), "area": round(total, 4),
                          "extent": round(extent, 4), "largest_face": round(biggest, 4)})

    # Slivers are looked for only OUTSIDE the fragment components: inside one the whole thing is
    # going anyway, and reporting the same face under two headings would double-count it. The
    # area and width bounds and the open-border rule are the module docstring's subject --
    # without them this catches long real strips, strips of real surface too wide to be a ragged
    # edge, and strips sandwiched in the middle of a surface.
    quality = _face_quality(positions_w, face_w)
    width = face_width(positions_w, face_w)
    thin = np.nonzero(~fragments & ~protected & (quality < min_q) & (area <= max_area)
                      & (width <= max_width))[0]
    on_border = _open_long_edges(positions_w, face_w, thin, area, max_width, tables)
    slivers[thin[on_border]] = True

    kept.sort(key=lambda k: (k["area"], k["faces"], k["extent"]))
    report = {
        "n_components": n_components,
        #: How many components shared welded edges alone made, and how many joins the two
        #: contact rules added -- the evidence for what those rules changed on this model.
        **joins,
        #: The two tolerances this run was given, both derived from the mesh's print step.
        **bounds,
        "n_candidate_components": n_candidates,
        #: Components the size rules caught but that hold a `protected` face (one solidify
        #: invented), so are never debris; and how many protected faces were handed in at all.
        "n_protected_components": n_protected,
        "n_protected_faces": int(protected.sum()),
        "n_above_threshold_components": n_components - n_candidates - n_protected,
        "n_fragment_faces": int(fragments.sum()),
        #: Faces thin enough to be a sliver (quality, area, width), and how many of them were
        #: KEPT because no long edge of theirs is an open border -- strips of a surface's middle,
        #: whose removal would open a slit (review 2a C1).
        "n_thin_faces": int(len(thin)),
        "n_sandwiched_thin_faces": int((~on_border).sum()),
        "n_sliver_faces": int(slivers.sum()),
        #: The smallest components the size rules did NOT catch -- the evidence for where the
        #: thresholds sit relative to this model, and the first place to look if something real
        #: went missing or something stray survived.
        "smallest_kept_components": kept[:_KEPT_REPORTED],
    }
    return FragmentResult(fragments=fragments, slivers=slivers, component=component,
                          report=report)
