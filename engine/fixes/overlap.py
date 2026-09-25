"""Overlapping coplanar faces: find them, and remove a duplicate layer the rest of its own
region already covers.

A SketchUp export can carry a surface TWICE -- the same walkway drawn over itself. Measured on
file A's removal-stage mesh (2,656 faces): 120 overlapping coplanar pairs, every one of them the
same material, over 133 faces in 25 regions. The merge cannot do anything with those: rule 3
excludes an overlapping triangle from its region's union and a region whose union still overlaps
is skipped outright, so 914 of file A's 1,674 output faces were copied through unmerged and every
gridline around them was drawn.

WHAT AN OVERLAP IS MEASURED IN. Two faces overlap when they lie in ONE PLANE and their outlines
share area. The plane, not the region, is the unit: regions are split by material (and by UV
class, and by connectivity), so the two halves of a different-material z-fight are always in
different regions, and a per-region search could not see the very defect the guard's tie test was
written for. `find_overlaps` therefore groups REGIONS into plane groups first.

WHAT IS SAFE TO REMOVE, and it is a narrower question. A face may be dropped only when the OTHER
faces of its OWN region already cover it (`covered >= 0.99`): same material by construction, same
plane, same outline -- so a ray that met it still meets the same surface, at the same depth, in
the same colour. That is the only claim this module makes, and `guard_feedback` is still asked to
confirm it over all 26 views before anything is deleted.

A DIFFERENT-MATERIAL overlap is never removed here. Which of the two a person wants is not a
question geometry can answer, so those pairs are only reported, with their face ids and
materials.

AN OPPOSITE-WOUND COPY is its own region (`engine.topo.planes.cluster_planes` never puts two
faces facing apart in one), so the rule above never touches it -- and until brief 13 nothing
did: "never treat opposite-normal coincident pairs as duplicates", because such a pair can be a
real two-sided surface. The owner decided on 2026-09-25 that the same surface drawn twice with
opposite windings, which Unity's double-sided shader z-fights, loses one copy "so that it won't
flick in Unity". `plan_coincident_removal` is that exception and nothing wider: an EXACTLY
coincident pair (0.001 in, 0.99 both ways), the same material and the same UV mapping modulo
whole tiles, keeping the face whose front faces the side the ORIGINAL mesh's exposure says the
pair is seen from -- measured against the guard views, since no guard sees a back face. A pair of
two materials, a partial overlap and an offset copy keep both faces, as before.

Vertices are never moved, invented or re-indexed: this module only ever drops whole faces
(`engine.fixes.remove.remove_faces`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely

from engine.fixes.remove import remove_faces
from engine.guard.compare import guard_feedback
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.model import MeshData
from engine.pipeline import Topology
from engine.rays.caster import EmbreeCaster, ReusableCaster
from engine.topo.adjacency import edge_face_lists
from engine.topo.planes import plane_basis

#: A pair counts as overlapping when its shared area exceeds
#: `OVERLAP_REL * min(area_i, area_j) + OVERLAP_ABS`. `min`, so the pair is one fact about two
#: faces rather than two verdicts that can disagree: the same threshold then decides both which
#: pairs are reported and which triangles the merge excludes (rule 3).
OVERLAP_ABS = 1e-9
OVERLAP_REL = 1e-6

#: How much of a face the OTHER faces of its region must already cover for it to be a removal
#: candidate. Not 1.0: a union boundary that a 1e-4 grid snapped can leave a hair of the outline
#: uncovered, and a hair is not a surface.
COVERED_FRACTION = 0.99

#: Two region normals are the same plane's when `|n . m|` exceeds this -- absolute value, because
#: a double face is very often wound the two opposite ways.
PLANE_PARALLEL_DOT = 0.999


@dataclass
class OverlapPlan:
    """What `plan_overlap_removal` decided, before any guard has seen it."""
    #: Bool over `mesh` faces: in a same-material overlap pair AND covered by the rest of its
    #: own region.
    candidates: np.ndarray
    #: Bool over `mesh` faces: the subset of `candidates` actually proposed for removal -- one
    #: member of every mutually covered pair is always protected (see `plan_overlap_removal`).
    remove: np.ndarray
    #: `{face: covered fraction}` for every face in a same-material pair.
    covered: dict
    pairs_same: list = field(default_factory=list)
    pairs_diff: list = field(default_factory=list)


@dataclass
class OverlapResult:
    mesh: MeshData
    #: Int64 over the OUTPUT faces: which face of the input mesh each one is.
    source_faces: np.ndarray
    #: Bool over the INPUT faces. `removed` is what the guard confirmed, `candidates` what was
    #: proposed, `restored` the difference -- candidates the guard put back, which stay.
    removed: np.ndarray
    candidates: np.ndarray
    restored: np.ndarray
    pairs_same: list
    pairs_diff: list
    #: `guard_feedback`'s own per-round history.
    history: list
    report: dict
    #: Bool over the INPUT faces: brief 13's stacked opposite-wound copies proposed
    #: (`CoincidentPlan.remove`), and those of them the guard confirmed -- the latter also in
    #: `removed`, the rest in `restored`.
    coincident_proposed: np.ndarray
    removed_coincident: np.ndarray
    #: `CoincidentPlan.pairs`, each with its final verdict.
    coincident_pairs: list


# ------------------------------------------------------------------------------- plane geometry


def region_frame(positions_w: np.ndarray, face_w: np.ndarray, members: np.ndarray):
    """Area-weighted normal of `members`, a local origin on them, and the `(3, 2)` projection
    basis -- `None` when the faces have no area between them.

    Local, because the real model sits near 24,000 inches and the union downstream runs on a
    1e-4 grid. `engine.fixes.merge` projects every region with this same function, so a region's
    triangles have the same coordinates here and there."""
    tri = positions_w[face_w[members]]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]).sum(axis=0)
    length = float(np.linalg.norm(cross))
    if length == 0.0:
        return None
    normal = cross / length
    e1, e2 = plane_basis(normal)
    return normal, positions_w[face_w[members[0], 0]], np.stack([e1, e2], axis=1)


def _polygons(positions_w: np.ndarray, face_w: np.ndarray, faces: np.ndarray,
              origin: np.ndarray, basis: np.ndarray):
    tri_xy = (positions_w[face_w[faces]] - origin) @ basis
    polys = shapely.polygons(np.concatenate([tri_xy, tri_xy[:, :1]], axis=1))
    return polys, shapely.area(polys)


def overlapping_polygon_pairs(polys: np.ndarray, areas: np.ndarray):
    """`(left, right, shared)` for every `left < right` pair of `polys` whose intersection area
    exceeds `OVERLAP_REL * min(area) + OVERLAP_ABS`, sorted by `(left, right)`.

    The STRtree answers `intersects`, which every pair of neighbouring triangles in a grid
    satisfies along their shared edge; the area threshold is what turns that into an overlap."""
    empty = (np.zeros(0, np.int64),) * 2 + (np.zeros(0, np.float64),)
    if len(polys) < 2:
        return empty
    left, right = shapely.STRtree(polys).query(polys, predicate="intersects")
    upper = left < right
    left, right = left[upper], right[upper]
    if not len(left):
        return empty
    shared = shapely.area(shapely.intersection(polys[left], polys[right]))
    keep = shared > OVERLAP_REL * np.minimum(areas[left], areas[right]) + OVERLAP_ABS
    left, right, shared = left[keep], right[keep], shared[keep]
    order = np.lexsort((right, left))    # STRtree order is unspecified; this one is not
    return left[order].astype(np.int64), right[order].astype(np.int64), shared[order]


def overlap_excluded(polys: np.ndarray, areas: np.ndarray) -> np.ndarray:
    """Rule 3 of `engine.fixes.merge`: every triangle that overlaps another of its own region,
    which the merge excludes from the region's union and copies through instead. Per TRIANGLE,
    never per plane -- flagging a whole plane because of one 0.5 sq-inch overlap froze a
    682-triangle plane in the spike."""
    excluded = np.zeros(len(polys), bool)
    left, right, _shared = overlapping_polygon_pairs(polys, areas)
    excluded[left] = True
    excluded[right] = True
    return excluded


def plane_groups(topo: Topology, plane_tol: float) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """`[(faces, normal, origin), ...]`: the regions of `topo`, gathered into the planes they
    share. A region joins the first existing group (in ascending region id, so the result does
    not depend on dictionary order) whose normal is parallel to within `PLANE_PARALLEL_DOT`,
    ignoring SIGN, and whose plane it lies in to within `plane_tol`.

    Ignoring sign matters: a double face is usually the same outline wound both ways, which is
    exactly the pair that has to end up in one group."""
    groups: list[dict] = []
    for region in np.unique(topo.face_region[topo.face_region >= 0]):
        members = np.nonzero(topo.face_region == region)[0]
        frame = region_frame(topo.positions_w, topo.face_w, members)
        if frame is None:
            continue
        normal, origin, _basis = frame
        for group in groups:
            if (abs(float(normal @ group["normal"])) > PLANE_PARALLEL_DOT
                    and abs(float((origin - group["origin"]) @ group["normal"])) <= plane_tol):
                group["faces"].append(members)
                break
        else:
            groups.append({"normal": normal, "origin": origin, "faces": [members]})
    return [(np.sort(np.concatenate(g["faces"])), g["normal"], g["origin"]) for g in groups]


# ---------------------------------------------------------------------------------- the search


def find_overlaps(mesh: MeshData, topo: Topology, plane_tol: float | None = None) -> list[tuple]:
    """`[(i, j, shared_area, same_material), ...]` for every overlapping coplanar pair of faces,
    `i < j`, sorted. `plane_tol` defaults to the mesh's own `1.5 * max(axis quanta)` -- the same
    bound the guard calls one surface.

    Faces in no region (degenerate) are not considered: they have no area to share."""
    if plane_tol is None:
        plane_tol = 1.5 * float(topo.quanta.max())
    out: list[tuple] = []
    for faces, normal, origin in plane_groups(topo, plane_tol):
        _e1, _e2 = plane_basis(normal)
        polys, areas = _polygons(topo.positions_w, topo.face_w, faces, origin,
                                 np.stack([_e1, _e2], axis=1))
        left, right, shared = overlapping_polygon_pairs(polys, areas)
        for a, b, s in zip(left, right, shared):
            i, j = sorted((int(faces[a]), int(faces[b])))
            out.append((i, j, float(s),
                        bool(mesh.face_material[i] == mesh.face_material[j])))
    return sorted(out)


class _RegionCover:
    """One region, projected into its own plane once, answering "how much of face `f` do the
    faces of this region I am still KEEPING cover?" -- and letting a caller drop a face and ask
    again. Only the region-mates that actually intersect `f` take part in the union, which is
    what keeps this affordable on a 500-triangle region."""

    def __init__(self, topo: Topology, region: int):
        self.members = np.nonzero(topo.face_region == region)[0]
        self.polys = None
        frame = region_frame(topo.positions_w, topo.face_w, self.members)
        if frame is None:
            return
        _normal, origin, basis = frame
        self.polys, self.areas = _polygons(topo.positions_w, topo.face_w, self.members, origin,
                                           basis)
        self.row = {int(f): k for k, f in enumerate(self.members)}
        self.tree = shapely.STRtree(self.polys)
        self.kept = np.ones(len(self.members), bool)

    def covered(self, face: int) -> float:
        if self.polys is None or int(face) not in self.row:
            return 0.0
        k = self.row[int(face)]
        if self.areas[k] <= 0.0:
            return 0.0
        others = np.array(sorted(n for n in self.tree.query(self.polys[k], predicate="intersects")
                                 if n != k and self.kept[n]), dtype=np.int64)
        if not len(others):
            return 0.0
        union = shapely.union_all(self.polys[others])
        return float(shapely.area(shapely.intersection(self.polys[k], union)) / self.areas[k])

    def drop(self, face: int) -> None:
        if self.polys is not None and int(face) in self.row:
            self.kept[self.row[int(face)]] = False


def covered_fractions(topo: Topology, faces) -> dict[int, float]:
    """`{face: area(face & union of the OTHER faces of its region) / area(face)}`, with the whole
    region present.

    Its own REGION, not its plane group: a region is one material and one continuous surface, so
    "the rest of my region already covers me" is the whole argument for dropping a face."""
    by_region: dict[int, list[int]] = {}
    out: dict[int, float] = {}
    for face in faces:
        region = int(topo.face_region[int(face)])
        if region >= 0:
            by_region.setdefault(region, []).append(int(face))
        else:
            out[int(face)] = 0.0
    for region in sorted(by_region):
        cover = _RegionCover(topo, region)
        for face in sorted(by_region[region]):
            out[face] = cover.covered(face)
    return out


# ----------------------------------------------------------------------------------- the plan


def _patch_of(topo: Topology, candidates: np.ndarray) -> np.ndarray:
    """Connected components of the candidate faces under EDGE adjacency: `patch[f]` is a
    component id for a candidate and `-1` otherwise. One stacked copy of a surface is one patch,
    which is what makes "the smaller patch loses" mean "the smaller layer loses"."""
    patch = np.full(len(candidates), -1, np.int64)
    parent = np.arange(len(candidates))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for group in edge_face_lists(topo.table):
        members = [int(f) for f in group if candidates[int(f)]]
        for f in members[1:]:
            parent[find(f)] = find(members[0])
    roots: dict[int, int] = {}
    for f in np.nonzero(candidates)[0]:
        patch[f] = roots.setdefault(find(int(f)), len(roots))
    return patch


def plan_overlap_removal(mesh: MeshData, topo: Topology, pairs: list | None = None,
                         plane_tol: float | None = None,
                         covered_fraction: float = COVERED_FRACTION) -> OverlapPlan:
    """Decide which faces to propose for removal, before any guard runs.

    A CANDIDATE is a face that appears in at least one same-material overlap pair and whose own
    region's other faces already cover at least `covered_fraction` of it.

    WHICH CANDIDATES ACTUALLY GO. Two exactly stacked copies are both candidates, and dropping
    both would leave a hole -- "the rest of my region covers me" stops being true the moment the
    face that covered me is dropped too. So the candidates are walked in a fixed order and each
    one is RE-MEASURED against what is still kept: it is dropped only if it is still covered
    then. The first copy of a stacked pair goes; the second finds its coverer gone and stays; a
    third stacked copy goes as well, which a rule that merely protected one winner per pair could
    not manage. It also frees a covered face whose overlap PARTNER is not covered -- measured on
    file A, 88 faces are covered where only 63 pairs have both members covered.

    THE ORDER, stated as what it actually does. The candidates are sorted by
    `(size of their connected patch, -face id)` ascending, and a face EARLIER in that order is
    the one tried -- and therefore dropped -- first. So the smaller patch loses, and within one
    patch the HIGHER face id loses.

    "Patch" is a connected component of the candidates under EDGE adjacency (`_patch_of`), and
    the first key only decides anything when the candidates really do fall into separate
    components. IT USUALLY DOES NOT. Two EXACTLY coincident layers -- the case this rule exists
    for -- weld to the same vertices, so they share the same welded edges and `_patch_of` unions
    both layers into ONE patch. Measured on `stacked_duplicate_slab`: 144 candidates, one patch
    of 144, and what decides which 72 go is entirely the second key. The patch size matters for
    layers that are merely overlapping rather than coincident, where each is its own component.

    (This docstring used to claim "a whole stacked layer is one patch, so the smaller LAYER
    loses". The first half is true of a layer in isolation; the conclusion is not, because two
    coincident layers are one patch between them.)

    Everything here is decided from face ids, patch sizes and sorted lists, so two runs on the
    same input produce the same plan."""
    if pairs is None:
        pairs = find_overlaps(mesh, topo, plane_tol)
    pairs_same = [p for p in pairs if p[3]]
    pairs_diff = [p for p in pairs if not p[3]]

    in_pairs = sorted({f for i, j, _a, _s in pairs_same for f in (i, j)})
    regions = {int(topo.face_region[f]) for f in in_pairs}
    covers = {r: _RegionCover(topo, r) for r in sorted(regions) if r >= 0}
    covered = {f: covers[int(topo.face_region[f])].covered(f)
               if int(topo.face_region[f]) >= 0 else 0.0 for f in in_pairs}

    candidates = np.zeros(mesh.n_faces, bool)
    for face in in_pairs:
        if covered[face] >= covered_fraction:
            candidates[face] = True

    patch = _patch_of(topo, candidates)
    size = np.bincount(patch[patch >= 0]) if candidates.any() else np.zeros(0, np.int64)

    remove = np.zeros(mesh.n_faces, bool)
    for face in sorted(np.nonzero(candidates)[0].tolist(),
                       key=lambda f: (int(size[patch[f]]), -f)):
        cover = covers[int(topo.face_region[face])]
        if cover.covered(face) >= covered_fraction:
            remove[face] = True
            cover.drop(face)
    return OverlapPlan(candidates=candidates, remove=remove, covered=covered,
                       pairs_same=pairs_same, pairs_diff=pairs_diff)


# ------------------------------------------------------------------ brief 13: stacked copies


#: Brief 13, condition 1. Two faces are ONE surface drawn twice only when every corner of each
#: lies within this many inches of the other's plane: the print precision the brief names, and
#: deliberately not the 0.15 in plane tolerance the engine derives from the real files' 0.1 in
#: print step, which calls a copy 0.01 in off the plane the same surface...
COINCIDENT_PLANE_TOL = 1e-3
#: ...and each covers at least this fraction of the other's area, BOTH ways. A partial overlap is
#: not a copy.
COINCIDENT_COVER = 0.99

#: Brief 13, condition 3: two faces put the texture in the same place when their UVs differ by the
#: same whole number of tiles at every corner of both, to within this many tiles -- the tolerance
#: `engine.topo.planes.build_regions` groups a UV class with (`uv_tol`).
COINCIDENT_UV_TOL = 0.02

#: Rows per block of `find_coincident_pairs`' bounding-box prefilter, so its mask stays bounded
#: whatever the size of the mesh.
_COINCIDENT_BLOCK = 512


def _uv_map(xy: np.ndarray, uv: np.ndarray) -> np.ndarray | None:
    """The affine map `[x, y, 1] -> uv` through a triangle's three corners, `(3, 2)`; `None` when
    the corners give no unique map."""
    try:
        return np.linalg.solve(np.column_stack([xy, np.ones(3)]), uv)
    except np.linalg.LinAlgError:
        return None


def uv_mapping_residual(mesh: MeshData, tri: np.ndarray, i: int, j: int) -> float:
    """How far, in tiles, faces `i` and `j` of `mesh` (corners `tri[i]`, `tri[j]`, one plane) are
    from putting the texture in the same place MODULO WHOLE TILES: their UV maps are compared at
    all six corners, against the one whole-tile shift the first corner shows -- so a mirrored or
    rotated map, which can land on whole tiles at a corner or two, still reads as different. 0.0
    when neither face has UVs, infinity when only one has."""
    has_i, has_j = bool((mesh.face_vt[i] >= 0).all()), bool((mesh.face_vt[j] >= 0).all())
    if not (has_i or has_j):
        return 0.0
    if has_i != has_j:
        return float("inf")
    normal = np.cross(tri[i][1] - tri[i][0], tri[i][2] - tri[i][0])
    e1, e2 = plane_basis(normal / np.linalg.norm(normal))
    basis = np.stack([e1, e2], axis=1)
    xy_i, xy_j = (tri[i] - tri[i][0]) @ basis, (tri[j] - tri[i][0]) @ basis
    map_i = _uv_map(xy_i, np.asarray(mesh.uvs, dtype=np.float64)[mesh.face_vt[i]])
    map_j = _uv_map(xy_j, np.asarray(mesh.uvs, dtype=np.float64)[mesh.face_vt[j]])
    if map_i is None or map_j is None:
        return float("inf")
    points = np.column_stack([np.vstack([xy_i, xy_j]), np.ones(6)])
    diff = points @ map_i - points @ map_j
    return float(np.abs(diff - np.round(diff[0])).max())


def find_coincident_pairs(positions_c: np.ndarray, face_w: np.ndarray, ok: np.ndarray, *,
                          plane_tol: float = COINCIDENT_PLANE_TOL,
                          cover: float = COINCIDENT_COVER) -> list[tuple[int, int, float]]:
    """`[(i, j, shared_area), ...]`, sorted, for every pair `i < j` of `ok` faces wound OPPOSITE
    ways that is EXACTLY coincident: parallel (`n_i . n_j < -PLANE_PARALLEL_DOT`), every corner
    of each within `plane_tol` of the other's plane, and each covering at least `cover` of the
    other's area, measured in `i`'s plane.

    Face by face, never through regions or plane groups: a region's plane is a fit over many
    faces, within the 0.15 in the export's print step allows, and "the same plane" here is a
    thousandth of an inch."""
    positions_c = np.asarray(positions_c, dtype=np.float64)
    face_w = np.asarray(face_w, dtype=np.int64)
    tri = positions_c[face_w]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(cross, axis=1)
    ids = np.nonzero(np.asarray(ok, dtype=bool) & (length > 0.0))[0]
    out: list[tuple[int, int, float]] = []
    if len(ids) < 2:
        return out
    normal = np.zeros_like(cross)
    normal[ids] = cross[ids] / length[ids, None]
    lo, hi = tri.min(axis=1) - plane_tol, tri.max(axis=1) + plane_tol
    for start in range(0, len(ids), _COINCIDENT_BLOCK):
        rows = ids[start:start + _COINCIDENT_BLOCK]
        near = ((lo[rows, None, :] <= hi[None, ids, :])
                & (hi[rows, None, :] >= lo[None, ids, :])).all(axis=2)
        near &= (normal[rows] @ normal[ids].T) < -PLANE_PARALLEL_DOT
        near &= ids[None, :] > rows[:, None]
        for a, b in zip(*np.nonzero(near)):
            i, j = int(rows[a]), int(ids[b])
            if (np.abs((tri[j] - tri[i][0]) @ normal[i]).max() > plane_tol
                    or np.abs((tri[i] - tri[j][0]) @ normal[j]).max() > plane_tol):
                continue
            e1, e2 = plane_basis(normal[i])
            basis = np.stack([e1, e2], axis=1)
            mine = shapely.Polygon((tri[i] - tri[i][0]) @ basis)
            theirs = shapely.Polygon((tri[j] - tri[i][0]) @ basis)
            shared = float(mine.intersection(theirs).area)
            if shared >= cover * mine.area and shared >= cover * theirs.area:
                out.append((i, j, shared))
    return sorted(out)


@dataclass
class CoincidentPlan:
    """What `plan_coincident_removal` decided, before any guard has seen it."""
    #: Bool over `mesh` faces: the copy proposed for removal from each pair.
    remove: np.ndarray
    #: One entry per pair -- see `plan_coincident_removal`.
    pairs: list


def side_pixels(positions_c: np.ndarray, face_w: np.ndarray, *, views=VIEWS_26,
                size: tuple[int, int] = (900, 600),
                caster_factory=EmbreeCaster) -> tuple[np.ndarray, np.ndarray]:
    """`(front_px, back_px)`, int64 per face of `face_w`: over `views` at `size`, framed on
    `positions_c`, how many pixels' FIRST hit is that face met on its front / on its back (the
    ray runs against its winding normal / along it). One double-sided render per view -- as
    `engine.fixes.orient.orient_sheets` counts a sheet's."""
    positions_c = np.asarray(positions_c, dtype=np.float64)
    face_w = np.asarray(face_w, dtype=np.int64)
    tri = positions_c[face_w]
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    front_px = np.zeros(len(face_w), dtype=np.int64)
    back_px = np.zeros(len(face_w), dtype=np.int64)
    ids = np.arange(len(face_w), dtype=np.int64)
    reused = ReusableCaster(caster_factory)
    for view in views:
        buf = ortho_first_hit(positions_c, face_w, ids, view, positions_c, size, reused)
        hit = buf.tri >= 0
        if not hit.any():
            continue
        f = buf.tri[hit]
        seen_back = (normal[f] @ np.asarray(buf.direction, dtype=np.float64)) > 0.0
        np.add.at(back_px, f[seen_back], 1)
        np.add.at(front_px, f[~seen_back], 1)
    return front_px, back_px


def plan_coincident_removal(mesh: MeshData, topo: Topology, positions_c: np.ndarray,
                            front: np.ndarray, back: np.ndarray, *,
                            exclude: np.ndarray | None = None, views=VIEWS_26,
                            size: tuple[int, int] = (900, 600),
                            caster_factory=EmbreeCaster) -> CoincidentPlan:
    """Brief 13, the owner's decision of 2026-09-25: of the same surface drawn twice with
    opposite windings -- which Unity's double-sided campus shader draws both of, so they flicker
    -- ONE face goes, and only when every condition below is measured to hold. Everything wider
    keeps both faces, as the blocked-operation rule always did.

    1. EXACTLY coincident (`find_coincident_pairs`): every corner of each face within 0.001 in
       of the other's plane, and each covering the other at least 0.99, both ways. A copy offset
       0.01 in, or one covering half, is not a pair at all.
    2. OPPOSITE windings (same). A same-wound copy is `plan_overlap_removal`'s; faces it already
       proposes (`exclude`) take no part here.
    3. The SAME material (else "different materials": a real two-sided surface, a different
       material on each side) and the same UV mapping modulo whole tiles (else "different UV
       mapping", `uv_mapping_residual` over `COINCIDENT_UV_TOL`): otherwise the look from one
       side would change.
    4. WHICH ONE STAYS. The face whose FRONT faces the side the pair is seen from, by the
       ORIGINAL mesh's exposure: `front` / `back` per face of `mesh` as it is wound here (the
       reference mesh's own side exposure, swapped for a face the orientation step flipped).
       Each side is sampled twice -- the front of one face is the back of the other -- and the
       two samples are averaged. Seen from both sides, the more exposed side wins
       (`seen_from_both_sides` says so); an exact tie keeps both ("exposure tie"). Then the
       choice is MEASURED, because a flip or a removal never changes a double-sided render and
       no guard can see a back face: over `views` at `size`, the pixels whose first hit is one
       of the pair are counted by the side the ray met them from (`side_pixels`, whichever of
       the two won the z-fight), and a pair whose kept side the views see less than the other
       is left as it is ("the guard views see the other side more"). SketchUp paints a back
       face purple, and back pixels from outside must not go up.
    5. Pairs never contradict each other: a face one pair keeps is never removed for another,
       nor one removed kept ("conflicts with another pair" keeps both). What is proposed still
       goes through the strict guard in `remove_overlaps`.

    Whole faces only: nothing is moved, invented or re-indexed.

    Returns `CoincidentPlan(remove, pairs)`, `pairs` one entry per exactly coincident
    opposite-wound pair, sorted by face ids: `{"faces": [i, j], "area": sq in shared, "normal":
    face i's unit normal, "centroid": face i's, in `positions_c`'s frame, "materials": [name,
    name], "uv_residual": tiles or None, "exposure": [side i's front faces,
    side j's front faces], "seen_from_both_sides", "px": [pixels from side i's front faces,
    from side j's] or None, "kept", "removed" (face ids, or None when both stay), "side_kept":
    the kept face's unit front normal or None, "verdict": "removed" | "kept", "reason"}`."""
    exclude = (np.zeros(mesh.n_faces, dtype=bool) if exclude is None
               else np.asarray(exclude, dtype=bool))
    tri = positions_c[topo.face_w]
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    remove = np.zeros(mesh.n_faces, dtype=bool)
    pairs: list[dict] = []
    decided: list[tuple[dict, int, int]] = []
    for i, j, shared in find_coincident_pairs(positions_c, topo.face_w, topo.ok & ~exclude):
        side_i = 0.5 * (float(front[i]) + float(back[j]))
        side_j = 0.5 * (float(back[i]) + float(front[j]))
        unit_i = normal[i] / np.linalg.norm(normal[i])
        entry = {"faces": [i, j], "area": round(shared, 4),
                 "normal": [round(float(c), 6) + 0.0 for c in unit_i],
                 "centroid": tri[i].mean(axis=0).tolist(),
                 "materials": [mesh.materials[int(mesh.face_material[f])] for f in (i, j)],
                 "uv_residual": None, "exposure": [round(side_i, 6), round(side_j, 6)],
                 "seen_from_both_sides": min(side_i, side_j) > 0.0, "px": None,
                 "kept": None, "removed": None, "side_kept": None,
                 "verdict": "kept", "reason": None}
        pairs.append(entry)
        if mesh.face_material[i] != mesh.face_material[j]:
            entry["reason"] = "different materials"
            continue
        entry["uv_residual"] = round(uv_mapping_residual(mesh, tri, i, j), 5)
        if not entry["uv_residual"] <= COINCIDENT_UV_TOL:
            entry["reason"] = "different UV mapping"
            continue
        if side_i == side_j:
            entry["reason"] = "exposure tie"
            continue
        decided.append((entry, *((i, j) if side_i > side_j else (j, i))))

    if decided:
        front_px, back_px = side_pixels(positions_c, topo.face_w, views=views, size=size,
                                        caster_factory=caster_factory)
    kept: set[int] = set()
    dropped: set[int] = set()
    for entry, keep, drop in decided:
        i, j = entry["faces"]
        entry["px"] = [int(front_px[i] + back_px[j]), int(back_px[i] + front_px[j])]
        mine, theirs = entry["px"] if keep == i else entry["px"][::-1]
        if mine < theirs:
            entry["reason"] = "the guard views see the other side more"
            continue
        if keep in dropped or drop in kept:
            entry["reason"] = "conflicts with another pair"
            continue
        kept.add(keep)
        dropped.add(drop)
        remove[drop] = True
        unit = normal[keep] / np.linalg.norm(normal[keep])
        entry.update(kept=keep, removed=drop, verdict="removed",
                     side_kept=[round(float(c), 6) + 0.0 for c in unit])
    return CoincidentPlan(remove=remove, pairs=pairs)


# --------------------------------------------------------------------------------- the removal


def remove_overlaps(mesh: MeshData, topo: Topology, positions_c: np.ndarray, flat_materials,
                    depth_tol: float, *, guard_size: tuple[int, int] = (900, 600),
                    crack_closed_cap: float = float("inf"), plane_tol: float | None = None,
                    covered_fraction: float = COVERED_FRACTION,
                    caster_factory=EmbreeCaster, guard=None,
                    side_exposure: tuple[np.ndarray, np.ndarray] | None = None) -> OverlapResult:
    """Plan the removal, confirm it with `guard_feedback(strict=True)` over all 26 views, and
    drop what survives.

    The guard is the same one hidden faces go through, at the same strictness and against the
    SAME mesh this function was handed: the claim being checked is "the picture does not change",
    and a candidate that changes any pixel is restored, stays in the mesh, and is counted in
    `n_restored_overlap`. `positions_c` must be `topo.positions_w` recentred by the caller, so
    `topo.face_w` indexes it.

    `side_exposure` is `(front, back)` per face of `mesh` as it is wound here; given, brief 13's
    stacked opposite-wound copies are planned too (`plan_coincident_removal`).

    `guard` is for tests only -- a stand-in for `guard_feedback` with the same call shape."""
    plan = plan_overlap_removal(mesh, topo, plane_tol=plane_tol,
                                covered_fraction=covered_fraction)
    coincident = CoincidentPlan(remove=np.zeros(mesh.n_faces, bool), pairs=[])
    if side_exposure is not None:
        coincident = plan_coincident_removal(mesh, topo, positions_c, *side_exposure,
                                             exclude=plan.remove, size=guard_size,
                                             caster_factory=caster_factory)
    proposed = plan.remove | coincident.remove
    history: list = []
    removed = np.zeros(mesh.n_faces, bool)
    if proposed.any():
        call = guard if guard is not None else guard_feedback
        removed, history = call(proposed, positions_c, topo.face_w, mesh.face_material,
                                flat_materials, depth_tol, strict=True, size=guard_size,
                                caster_factory=caster_factory,
                                crack_closed_cap=crack_closed_cap)
        removed = np.asarray(removed, dtype=bool)

    removed_coincident = removed & coincident.remove
    for entry in coincident.pairs:
        if entry["verdict"] == "removed" and not removed[entry["removed"]]:
            entry.update(verdict="kept", reason="put back by the guard", kept=None, removed=None,
                         side_kept=None)
    restored = proposed & ~removed
    out_mesh, source_faces = remove_faces(mesh, removed)
    report = {
        "n_overlap_pairs_same": len(plan.pairs_same),
        "n_overlap_pairs_diff": len(plan.pairs_diff),
        "n_overlap_candidates": int(plan.candidates.sum()),
        "n_removed_overlap": int((removed & plan.remove).sum()),
        "n_restored_overlap": int((restored & plan.remove).sum()),
        "overlap_pairs_diff_material": [
            {"faces": [i, j], "materials": [int(mesh.face_material[i]), int(mesh.face_material[j])],
             "area": round(area, 6)}
            for i, j, area, _same in plan.pairs_diff],
        "n_coincident_pairs": len(coincident.pairs),
        "n_removed_coincident": int(removed_coincident.sum()),
        "n_restored_coincident": int((restored & coincident.remove).sum()),
    }
    return OverlapResult(mesh=out_mesh, source_faces=source_faces, removed=removed,
                         candidates=plan.candidates, restored=restored,
                         pairs_same=plan.pairs_same, pairs_diff=plan.pairs_diff,
                         history=history, report=report, coincident_proposed=coincident.remove,
                         removed_coincident=removed_coincident, coincident_pairs=coincident.pairs)
