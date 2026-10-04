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

Vertices are never moved, invented or re-indexed: this module only ever drops whole faces
(`engine.fixes.remove.remove_faces`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely

from engine.fixes.remove import remove_faces
from engine.guard.compare import guard_feedback
from engine.model import MeshData
from engine.pipeline import Topology
from engine.rays.caster import EmbreeCaster
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


# --------------------------------------------------------------------------------- the removal


def remove_overlaps(mesh: MeshData, topo: Topology, positions_c: np.ndarray, flat_materials,
                    depth_tol: float, *, guard_size: tuple[int, int] = (900, 600),
                    crack_closed_cap: float = float("inf"), plane_tol: float | None = None,
                    covered_fraction: float = COVERED_FRACTION,
                    caster_factory=EmbreeCaster, guard=None) -> OverlapResult:
    """Plan the removal, confirm it with `guard_feedback(strict=True)` over all 26 views, and
    drop what survives.

    The guard is the same one hidden faces go through, at the same strictness and against the
    SAME mesh this function was handed: the claim being checked is "the picture does not change",
    and a candidate that changes any pixel is restored, stays in the mesh, and is counted in
    `n_restored_overlap`. `positions_c` must be `topo.positions_w` recentred by the caller, so
    `topo.face_w` indexes it.

    `guard` is for tests only -- a stand-in for `guard_feedback` with the same call shape."""
    plan = plan_overlap_removal(mesh, topo, plane_tol=plane_tol,
                                covered_fraction=covered_fraction)
    history: list = []
    removed = np.zeros(mesh.n_faces, bool)
    if plan.remove.any():
        call = guard if guard is not None else guard_feedback
        removed, history = call(plan.remove, positions_c, topo.face_w, mesh.face_material,
                                flat_materials, depth_tol, strict=True, size=guard_size,
                                caster_factory=caster_factory,
                                crack_closed_cap=crack_closed_cap)
        removed = np.asarray(removed, dtype=bool)

    restored = plan.remove & ~removed
    out_mesh, source_faces = remove_faces(mesh, removed)
    report = {
        "n_overlap_pairs_same": len(plan.pairs_same),
        "n_overlap_pairs_diff": len(plan.pairs_diff),
        "n_overlap_candidates": int(plan.candidates.sum()),
        "n_removed_overlap": int(removed.sum()),
        "n_restored_overlap": int(restored.sum()),
        "overlap_pairs_diff_material": [
            {"faces": [i, j], "materials": [int(mesh.face_material[i]), int(mesh.face_material[j])],
             "area": round(area, 6)}
            for i, j, area, _same in plan.pairs_diff],
    }
    return OverlapResult(mesh=out_mesh, source_faces=source_faces, removed=removed,
                         candidates=plan.candidates, restored=restored,
                         pairs_same=plan.pairs_same, pairs_diff=plan.pairs_diff,
                         history=history, report=report)


# ------------------------------------------------------------------------------------------------
# Brief 15 item 1: what can still flicker, measured on every run

#: Two faces are a DOUBLE LAYER when they share more than this many square inches within one
#: plane (brief 14's `MIN_AREA`): below it, a sliver along a shared edge, not a surface drawn twice.
DOUBLE_LAYER_MIN_AREA = 1.0


def double_layers_reference(positions_c: np.ndarray, faces: np.ndarray, depth_tol: float,
                            views=None, size: tuple[int, int] = (900, 600), caster_factory=EmbreeCaster,
                            min_area: float = DOUBLE_LAYER_MIN_AREA,
                            centre: np.ndarray | None = None) -> dict:
    """Test oracle: the original double_layers implementation. Kept verbatim and must not change.

    Brief 15 item 1 -- brief 14's measurement of what can still flicker in Unity, cheap enough
    for every run. A DOUBLE LAYER is two of `faces` whose outlines share more than `min_area` sq in
    within ONE plane: parallel (`|n . m| > PLANE_PARALLEL_DOT`), every corner of each within
    `depth_tol` of the other's plane -- the band the guard itself calls one surface. Any winding,
    any material: two layers of one colour still trade places in a depth test whenever their
    lighting or texture mapping differ, and the guard's `zfight_tie` sees none of them, because it
    only counts pixels whose winning face CHANGED between two meshes.

    Its PIXELS are those of the renders over `views` (`VIEWS_26` by default) whose first hit is
    one of the two and whose ray meets the other within `depth_tol` -- where the two can trade
    places. Each pixel is counted once.

    Returns `{"count": pairs, "area": their shared sq in, "px": pixels, "planes": [...], "pair_list": [...]}`,
    the planes largest first, each `{"normal", "offset", "centroid", "faces", "pairs", "opposite",
    "area", "px"}` (`faces` index `faces`; `offset` is `n . p` on the plane, `n` pointing to the
    positive side of its largest component). `pair_list` is every pair `[i, j, shared, opposite]`
    with `i < j` indexing the input `faces`, sorted by descending shared area, then by `i` and `j`.
    `positions_c` is the recentred frame the guard renders in; with `centre`, the planes' centroid
    and offset are given in world coordinates. No double layer: no render at all."""
    from engine.guard.views import VIEWS_26, ortho_first_hit
    from engine.rays.caster import ReusableCaster

    views = VIEWS_26 if views is None else views
    positions_c = np.asarray(positions_c, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    empty = {"count": 0, "area": 0.0, "px": 0, "planes": [], "pair_list": []}
    if not len(faces):
        return empty
    tri = positions_c[faces]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(cross, axis=1)
    ok = length > 1e-12
    normal = np.zeros_like(cross)
    normal[ok] = cross[ok] / length[ok, None]
    lo, hi = tri.min(axis=1) - depth_tol, tri.max(axis=1) + depth_tol
    ids = np.nonzero(ok)[0]
    pairs: list[tuple[int, int, float, bool]] = []
    for s in range(0, len(ids), 400):
        rows = ids[s:s + 400]
        near = ((lo[rows, None] <= hi[None, ids]) & (hi[rows, None] >= lo[None, ids])).all(axis=2)
        near &= np.abs(normal[rows] @ normal[ids].T) > PLANE_PARALLEL_DOT
        near &= ids[None, :] > rows[:, None]
        for a, b in zip(*np.nonzero(near)):
            i, j = int(rows[a]), int(ids[b])
            sep = max(float(np.abs((tri[j] - tri[i][0]) @ normal[i]).max()),
                      float(np.abs((tri[i] - tri[j][0]) @ normal[j]).max()))
            if sep > depth_tol:
                continue
            e1, e2 = plane_basis(normal[i])
            basis = np.stack([e1, e2], axis=1)
            shared = float(shapely.area(shapely.intersection(
                shapely.Polygon((tri[i] - tri[i][0]) @ basis),
                shapely.Polygon((tri[j] - tri[i][0]) @ basis))))
            if shared > min_area:
                pairs.append((i, j, shared, bool(normal[i] @ normal[j] < 0.0)))
    if not pairs:
        return empty

    # the planes: pairs whose faces share a plane (parallel, offsets within the tolerance)
    def plane_of(f):
        n = normal[f].copy()
        if n[int(np.argmax(np.abs(n)))] < 0.0:
            n = -n
        return n, float(tri[f][0] @ n)

    planes: list[dict] = []
    for i, j, shared, opposite in pairs:
        n, d = plane_of(i)
        for p in planes:
            if abs(float(p["_n"] @ n)) > PLANE_PARALLEL_DOT and abs(p["_d"] - d) <= depth_tol:
                break
        else:
            p = {"_n": n, "_d": d, "_faces": set(), "_pairs": [], "_c": []}
            planes.append(p)
        p["_faces"].update((i, j))
        p["_pairs"].append((i, j, shared, opposite))
        p["_c"].append((tri[i].mean(axis=0) + tri[j].mean(axis=0)) / 2.0)

    # the pixels: first hit on a face of a pair, and the ray meets its partner within depth_tol
    partners: dict[int, set] = {}
    plane_index: dict[int, int] = {}
    for k, p in enumerate(planes):
        for i, j, _s, _o in p["_pairs"]:
            partners.setdefault(i, set()).add(j)
            partners.setdefault(j, set()).add(i)
            plane_index[i] = plane_index[j] = k
    ids_all = np.arange(len(faces), dtype=np.int64)
    reusable = ReusableCaster(caster_factory)
    px_plane = np.zeros(len(planes), dtype=np.int64)
    # partners as CSR arrays over face ids, for a vectorized (pixel, partner) expansion
    ptr = np.zeros(len(faces) + 1, dtype=np.int64)
    for f, ps in partners.items():
        ptr[f + 1] = len(ps)
    ptr = np.cumsum(ptr)
    idx = np.zeros(int(ptr[-1]), dtype=np.int64)
    for f, ps in partners.items():
        idx[ptr[f]:ptr[f + 1]] = sorted(ps)
    plane_of_face = np.full(len(faces), -1, dtype=np.int64)
    for f, k in plane_index.items():
        plane_of_face[f] = k
    watched = np.array(sorted(partners), dtype=np.int64)
    for view in views:
        buf = ortho_first_hit(positions_c, faces, ids_all, view, positions_c, size, reusable)
        mask = (buf.tri >= 0) & np.isin(buf.tri, watched)
        if not mask.any():
            continue
        rows, cols = np.nonzero(mask)
        first_f = buf.tri[rows, cols].astype(np.int64)
        first_t = buf.depth[rows, cols]
        origins = buf.xs[cols][:, None] * buf.right + buf.ys[rows][:, None] * buf.up + buf.standoff
        direction = np.asarray(buf.direction, dtype=np.float64)
        # every (pixel, partner of its first face) row
        counts = ptr[first_f + 1] - ptr[first_f]
        pix = np.repeat(np.arange(len(first_f)), counts)
        starts = np.repeat(ptr[first_f] - np.concatenate(([0], np.cumsum(counts)[:-1])), counts)
        partner = idx[starts + np.arange(len(pix))]
        # Moller-Trumbore against that partner: does the ray meet it within depth_tol of the first hit?
        v0 = tri[partner, 0]
        e1 = tri[partner, 1] - v0
        e2 = tri[partner, 2] - v0
        pvec = np.cross(np.broadcast_to(direction, e2.shape), e2)
        det = np.einsum("ij,ij->i", e1, pvec)
        usable = np.abs(det) > 1e-12
        inv = np.where(usable, 1.0 / np.where(usable, det, 1.0), 0.0)
        s = origins[pix] - v0
        u = np.einsum("ij,ij->i", s, pvec) * inv
        qvec = np.cross(s, e1)
        v = (qvec @ direction) * inv
        t = np.einsum("ij,ij->i", e2, qvec) * inv
        eps = 1e-6
        met = usable & (u >= -eps) & (v >= -eps) & (u + v <= 1.0 + eps) & (np.abs(t - first_t[pix]) <= depth_tol)
        counted = np.unique(pix[met])
        np.add.at(px_plane, plane_of_face[first_f[counted]], 1)
    px_plane = px_plane.tolist()

    shift = np.zeros(3) if centre is None else np.asarray(centre, dtype=np.float64)
    out_planes = []
    for k, p in enumerate(planes):
        out_planes.append({
            "normal": [round(float(v), 4) for v in p["_n"]],
            "offset": round(p["_d"] + float(p["_n"] @ shift), 4),
            "centroid": [round(float(v), 2) for v in np.mean(p["_c"], axis=0) + shift],
            "faces": sorted(int(f) for f in p["_faces"]),
            "pairs": len(p["_pairs"]),
            "opposite": sum(1 for _i, _j, _s, o in p["_pairs"] if o),
            "area": round(sum(s for _i, _j, s, _o in p["_pairs"]), 3),
            "px": px_plane[k]})
    out_planes.sort(key=lambda p: (-p["area"], p["faces"]))
    pair_list = sorted(([int(i), int(j), round(float(s), 3), bool(o)] for i, j, s, o in pairs),
                       key=lambda p: (-p[2], p[0], p[1]))
    return {"count": len(pairs), "area": round(sum(s for _i, _j, s, _o in pairs), 3),
            "px": int(sum(px_plane)), "planes": out_planes, "pair_list": pair_list}


def double_layers(positions_c: np.ndarray, faces: np.ndarray, depth_tol: float,
                  views=None, size: tuple[int, int] = (900, 600), caster_factory=EmbreeCaster,
                  min_area: float = DOUBLE_LAYER_MIN_AREA,
                  centre: np.ndarray | None = None, *,
                  stats: dict | None = None,
                  chunk_rows: int = 200_000,
                  block_pairs: int = 2_000_000) -> dict:
    """Brief 15 item 1 / P1-S3 / P1-S3b: double layers detection, made sub-quadratic.
    Returns identical results to double_layers_reference with bounded memory and
    spatial candidate search.

    A DOUBLE LAYER is two of `faces` whose outlines share more than `min_area` sq in
    within ONE plane: parallel (`|n . m| > PLANE_PARALLEL_DOT`), every corner of each within
    `depth_tol` of the other's plane -- the band the guard itself calls one surface. Any winding,
    any material: two layers of one colour still trade places in a depth test whenever their
    lighting or texture mapping differ, and the guard's `zfight_tie` sees none of them, because it
    only counts pixels whose winning face CHANGED between two meshes.

    Its PIXELS are those of the renders over `views` (`VIEWS_26` by default) whose first hit is
    one of the two and whose ray meets the other within `depth_tol` -- where the two can trade
    places. Each pixel is counted once.

    Returns `{"count": pairs, "area": their shared sq in, "px": pixels, "planes": [...], "pair_list": [...]}`,
    the planes largest first, each `{"normal", "offset", "centroid", "faces", "pairs", "opposite",
    "area", "px"}` (`faces` index `faces`; `offset` is `n . p` on the plane, `n` pointing to the
    positive side of its largest component). `pair_list` is every pair `[i, j, shared, opposite]`
    with `i < j` indexing the input `faces`, sorted by descending shared area, then by `i` and `j`.
    `positions_c` is the recentred frame the guard renders in; with `centre`, the planes' centroid
    and offset are given in world coordinates. No double layer: no render at all.
    """
    from engine.guard.views import VIEWS_26, ortho_first_hit
    from engine.rays.caster import ReusableCaster

    if stats is not None:
        stats["bbox_pairs"] = 0
        stats["pairs_tested"] = 0
        stats["pairs_peak"] = 0
        stats["big_faces"] = 0
        stats["big_face_pairs"] = 0
        stats["pixel_rows_max"] = 0

    views = VIEWS_26 if views is None else views
    positions_c = np.asarray(positions_c, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    empty = {"count": 0, "area": 0.0, "px": 0, "planes": [], "pair_list": []}
    if not len(faces):
        return empty

    tri = positions_c[faces]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(cross, axis=1)
    ok = length > 1e-12
    normal = np.zeros_like(cross)
    normal[ok] = cross[ok] / length[ok, None]
    lo, hi = tri.min(axis=1) - depth_tol, tri.max(axis=1) + depth_tol
    ids = np.nonzero(ok)[0]
    if len(ids) < 2:
        return empty

    # Cell size tied to typical face size, never largest face or whole scene
    sz = tri[ids].max(axis=1) - tri[ids].min(axis=1)
    diag = np.linalg.norm(sz, axis=1)
    med = float(np.median(diag))
    cell_size = max(med * 1.0, 2.0 * depth_tol, 1e-6)

    c_lo = np.floor(lo / cell_size).astype(np.int64)
    c_hi = np.floor(hi / cell_size).astype(np.int64)
    span = c_hi[ids] - c_lo[ids] + 1
    n_cells = span[:, 0] * span[:, 1] * span[:, 2]

    # Faces spanning more than 64 cells go to big-faces list
    BIG_FACE_CELLS = 64
    is_big_arr = n_cells > BIG_FACE_CELLS
    ids_big = ids[is_big_arr]
    ids_small = ids[~is_big_arr]
    is_big_map = np.zeros(len(faces), dtype=bool)
    is_big_map[ids_big] = True

    if stats is not None:
        stats["big_faces"] = int(len(ids_big))

    survivors: list[tuple[int, int, float, bool]] = []
    PAIR_CHUNK = 200_000

    def process_block(cand_i: np.ndarray, cand_j: np.ndarray):
        if not len(cand_i):
            return
        if stats is not None:
            stats["pairs_peak"] = max(stats["pairs_peak"], len(cand_i))

        n_pairs = len(cand_i)
        for s in range(0, n_pairs, PAIR_CHUNK):
            e = min(s + PAIR_CHUNK, n_pairs)
            sub_i = cand_i[s:e]
            sub_j = cand_j[s:e]

            if stats is not None:
                stats["bbox_pairs"] += len(sub_i)

            # Box test & parallel test
            box_ok = (lo[sub_i, 0] <= hi[sub_j, 0]) & (hi[sub_i, 0] >= lo[sub_j, 0])
            box_ok &= (lo[sub_i, 1] <= hi[sub_j, 1]) & (hi[sub_i, 1] >= lo[sub_j, 1])
            box_ok &= (lo[sub_i, 2] <= hi[sub_j, 2]) & (hi[sub_i, 2] >= lo[sub_j, 2])

            dot = (normal[sub_i] * normal[sub_j]).sum(axis=1)
            abs_dot = np.abs(dot)
            tie_dot = np.abs(abs_dot - PLANE_PARALLEL_DOT) <= 1e-12
            if tie_dot.any():
                for tidx in np.nonzero(tie_dot)[0]:
                    abs_dot[tidx] = abs(float(normal[sub_i[tidx]] @ normal[sub_j[tidx]]))

            cand = box_ok & (abs_dot > PLANE_PARALLEL_DOT)
            if stats is not None:
                stats["pairs_tested"] += int(cand.sum())
            if not cand.any():
                continue

            i_cand = sub_i[cand]
            j_cand = sub_j[cand]

            # Separation test
            v0_i = tri[i_cand, 0]
            v0_j = tri[j_cand, 0]
            n_i = normal[i_cand]
            n_j = normal[j_cand]

            diff_j = tri[j_cand] - v0_i[:, None, :]
            dist_j = np.abs(diff_j[:, :, 0] * n_i[:, None, 0] + diff_j[:, :, 1] * n_i[:, None, 1] + diff_j[:, :, 2] * n_i[:, None, 2])
            sep_j = dist_j.max(axis=1)

            diff_i = tri[i_cand] - v0_j[:, None, :]
            dist_i = np.abs(diff_i[:, :, 0] * n_j[:, None, 0] + diff_i[:, :, 1] * n_j[:, None, 1] + diff_i[:, :, 2] * n_j[:, None, 2])
            sep_i = dist_i.max(axis=1)

            sep = np.maximum(sep_j, sep_i)
            tie_sep = np.abs(sep - depth_tol) <= 1e-9
            if tie_sep.any():
                for tidx in np.nonzero(tie_sep)[0]:
                    ii, jj = int(i_cand[tidx]), int(j_cand[tidx])
                    s_j = float(np.abs((tri[jj] - tri[ii][0]) @ normal[ii]).max())
                    s_i = float(np.abs((tri[ii] - tri[jj][0]) @ normal[jj]).max())
                    sep[tidx] = max(s_j, s_i)

            sep_ok = sep <= depth_tol
            if not sep_ok.any():
                continue

            i_surv = i_cand[sep_ok]
            j_surv = j_cand[sep_ok]

            # Vectorized plane_basis and shared area
            n_surv = normal[i_surv]
            a = np.zeros_like(n_surv)
            use_x = np.abs(n_surv[:, 0]) < 0.9
            a[use_x, 0] = 1.0
            a[~use_x, 1] = 1.0
            e1 = np.cross(n_surv, a)
            e1 /= np.linalg.norm(e1, axis=1, keepdims=True)
            e2 = np.cross(n_surv, e1)

            v0_surv = tri[i_surv, 0]
            tri_i_rel = tri[i_surv] - v0_surv[:, None, :]
            tri_j_rel = tri[j_surv] - v0_surv[:, None, :]

            pts_i = np.stack([(tri_i_rel * e1[:, None, :]).sum(axis=-1), (tri_i_rel * e2[:, None, :]).sum(axis=-1)], axis=-1)
            pts_j = np.stack([(tri_j_rel * e1[:, None, :]).sum(axis=-1), (tri_j_rel * e2[:, None, :]).sum(axis=-1)], axis=-1)

            inter_min = np.maximum(pts_i.min(axis=1), pts_j.min(axis=1))
            inter_max = np.minimum(pts_i.max(axis=1), pts_j.max(axis=1))
            inter_dim = np.maximum(inter_max - inter_min, 0.0)
            box_area = inter_dim[:, 0] * inter_dim[:, 1]
            box2d_ok = (box_area > min_area) | (np.abs(box_area - min_area) <= 1e-9)
            if not box2d_ok.any():
                continue

            i_box2d = i_surv[box2d_ok]
            j_box2d = j_surv[box2d_ok]
            pts_i_sub = pts_i[box2d_ok]
            pts_j_sub = pts_j[box2d_ok]

            polys_i = shapely.polygons(np.concatenate([pts_i_sub, pts_i_sub[:, :1]], axis=1))
            polys_j = shapely.polygons(np.concatenate([pts_j_sub, pts_j_sub[:, :1]], axis=1))
            shared = np.asarray(shapely.area(shapely.intersection(polys_i, polys_j)))

            tie_shared = np.abs(shared - min_area) <= 1e-9
            if tie_shared.any():
                for tidx in np.nonzero(tie_shared)[0]:
                    ii, jj = int(i_box2d[tidx]), int(j_box2d[tidx])
                    e1_exact, e2_exact = plane_basis(normal[ii])
                    basis_exact = np.stack([e1_exact, e2_exact], axis=1)
                    shared[tidx] = float(shapely.area(shapely.intersection(
                        shapely.Polygon((tri[ii] - tri[ii][0]) @ basis_exact),
                        shapely.Polygon((tri[jj] - tri[ii][0]) @ basis_exact))))

            keep = shared > min_area
            if not keep.any():
                continue

            i_keep = i_box2d[keep]
            j_keep = j_box2d[keep]
            shared_keep = shared[keep]
            opp_keep = (normal[i_keep] * normal[j_keep]).sum(axis=1) < 0.0

            for k in range(len(i_keep)):
                survivors.append((int(i_keep[k]), int(j_keep[k]), float(shared_keep[k]), bool(opp_keep[k])))

    # Helper to accumulate and flush candidate pairs in strict block_pairs limits
    block_i_parts, block_j_parts = [], []
    curr_block_len = 0

    def add_pairs(pa: np.ndarray, pb: np.ndarray):
        nonlocal curr_block_len, block_i_parts, block_j_parts
        if not len(pa):
            return
        idx = 0
        total = len(pa)
        while idx < total:
            room = block_pairs - curr_block_len
            take = min(room, total - idx)
            block_i_parts.append(pa[idx : idx + take])
            block_j_parts.append(pb[idx : idx + take])
            curr_block_len += take
            idx += take
            if curr_block_len >= block_pairs:
                process_block(np.concatenate(block_i_parts), np.concatenate(block_j_parts))
                block_i_parts, block_j_parts = [], []
                curr_block_len = 0

    def flush_pairs():
        nonlocal curr_block_len, block_i_parts, block_j_parts
        if block_i_parts:
            process_block(np.concatenate(block_i_parts), np.concatenate(block_j_parts))
            block_i_parts, block_j_parts = [], []
            curr_block_len = 0

    # 1. Big faces: candidate pairs involving big faces
    if len(ids_big) > 0:
        K = 200
        for s in range(0, len(ids_big), K):
            b_sub = ids_big[s : s + K]
            x_ok = (lo[b_sub, 0, None] <= hi[ids, 0]) & (hi[b_sub, 0, None] >= lo[ids, 0])
            y_ok = x_ok & (lo[b_sub, 1, None] <= hi[ids, 1]) & (hi[b_sub, 1, None] >= lo[ids, 1])
            box_ok = y_ok & (lo[b_sub, 2, None] <= hi[ids, 2]) & (hi[b_sub, 2, None] >= lo[ids, 2])
            rows, cols = np.nonzero(box_ok)
            if not len(rows):
                continue
            b_r = b_sub[rows]
            c_c = ids[cols]
            pair_keep = (c_c > b_r) | ((c_c < b_r) & (~is_big_map[c_c]))
            if not pair_keep.any():
                continue
            b_r_k = b_r[pair_keep]
            c_c_k = c_c[pair_keep]
            fa = np.minimum(b_r_k, c_c_k)
            fb = np.maximum(b_r_k, c_c_k)
            if stats is not None:
                stats["big_face_pairs"] += len(fa)
            add_pairs(fa, fb)

        flush_pairs()

    # 2. Small faces: canonical cell pair indexing
    if len(ids_small) > 1:
        small_span = span[~is_big_arr]
        c_lo_small = c_lo[ids_small]
        shape_code = (small_span[:, 0] << 16) | (small_span[:, 1] << 8) | small_span[:, 2]
        unq_shapes, inv = np.unique(shape_code, return_inverse=True)
        face_parts, cell_parts = [], []
        for u in range(len(unq_shapes)):
            u_idx = np.nonzero(inv == u)[0]
            dx = int((unq_shapes[u] >> 16) & 0xff)
            dy = int((unq_shapes[u] >> 8) & 0xff)
            dz = int(unq_shapes[u] & 0xff)
            offsets = np.indices((dx, dy, dz), dtype=np.int64).reshape(3, -1).T
            V = len(offsets)
            c = c_lo_small[u_idx, None, :] + offsets[None, :, :]
            cell_parts.append(c.reshape(-1, 3))
            face_parts.append(np.repeat(ids_small[u_idx], V))

        all_f = np.concatenate(face_parts)
        all_c = np.concatenate(cell_parts)
        del face_parts, cell_parts

        c_min = all_c.min(axis=0)
        c_shifted = all_c - c_min
        c_span = c_shifted.max(axis=0) + 1
        if float(c_span[0]) * float(c_span[1]) * float(c_span[2]) < 2**62:
            cell_key = (c_shifted[:, 0].astype(np.int64) * c_span[1] + c_shifted[:, 1].astype(np.int64)) * c_span[2] + c_shifted[:, 2].astype(np.int64)
            order = np.argsort(cell_key)
            sorted_k = cell_key[order]
            diff = sorted_k[1:] != sorted_k[:-1]
            del cell_key, sorted_k
        else:
            order = np.lexsort((all_c[:, 2], all_c[:, 1], all_c[:, 0]))
            sorted_c_tmp = all_c[order]
            diff = (sorted_c_tmp[1:] != sorted_c_tmp[:-1]).any(axis=1)
            del sorted_c_tmp

        sorted_f = all_f[order]
        sorted_c = all_c[order]
        del all_f, all_c, order

        split_idx = np.nonzero(diff)[0] + 1
        cell_starts = np.concatenate(([0], split_idx))
        cell_ends = np.concatenate((split_idx, [len(sorted_f)]))
        cell_counts = cell_ends - cell_starts
        del diff, split_idx

        multi_mask = cell_counts > 1
        multi_starts = cell_starts[multi_mask]
        multi_counts = cell_counts[multi_mask]
        del cell_starts, cell_ends, cell_counts, multi_mask

        # Vectorized generation for cells with exactly 2 faces
        m2 = multi_counts == 2
        if m2.any():
            st2 = multi_starts[m2]
            f0 = sorted_f[st2]
            f1 = sorted_f[st2 + 1]
            C2 = sorted_c[st2]
            fa = np.minimum(f0, f1)
            fb = np.maximum(f0, f1)
            canon2 = (np.maximum(c_lo[fa], c_lo[fb]) == C2).all(axis=1)
            if canon2.any():
                add_pairs(fa[canon2], fb[canon2])

        # Cells with > 2 faces
        other_cells = np.nonzero(multi_counts > 2)[0]
        for cidx in other_cells:
            st = multi_starts[cidx]
            cnt = int(multi_counts[cidx])
            f = sorted_f[st : st + cnt]
            C = sorted_c[st]
            ii, jj = np.triu_indices(cnt, k=1)
            fa = np.minimum(f[ii], f[jj])
            fb = np.maximum(f[ii], f[jj])
            canon = (np.maximum(c_lo[fa], c_lo[fb]) == C).all(axis=1)
            if canon.any():
                add_pairs(fa[canon], fb[canon])

        flush_pairs()

    if not survivors:
        return empty

    # Sort survivors by (i, j) before plane clustering
    survivors.sort(key=lambda p: (p[0], p[1]))
    pairs_final = survivors

    # The planes: pairs whose faces share a plane (parallel, offsets within tolerance)
    def plane_of(f):
        n = normal[f].copy()
        if n[int(np.argmax(np.abs(n)))] < 0.0:
            n = -n
        return n, float(tri[f][0] @ n)

    planes: list[dict] = []
    plane_n = np.zeros((max(len(pairs_final) // 4, 32), 3), dtype=np.float64)
    plane_d = np.zeros(len(plane_n), dtype=np.float64)
    num_p = 0

    for i, j, s_val, opposite in pairs_final:
        n, d = plane_of(i)
        matched_idx = -1
        if num_p > 0:
            dots = np.abs(plane_n[:num_p] @ n) > PLANE_PARALLEL_DOT
            d_ok = np.abs(plane_d[:num_p] - d) <= depth_tol
            matches = dots & d_ok
            if matches.any():
                matched_idx = int(np.argmax(matches))

        if matched_idx >= 0:
            p = planes[matched_idx]
        else:
            p = {"_n": n, "_d": d, "_faces": set(), "_pairs": [], "_c": []}
            planes.append(p)
            if num_p == len(plane_n):
                plane_n = np.resize(plane_n, (num_p * 2, 3))
                plane_d = np.resize(plane_d, num_p * 2)
            plane_n[num_p] = n
            plane_d[num_p] = d
            num_p += 1

        p["_faces"].update((i, j))
        p["_pairs"].append((i, j, s_val, opposite))
        p["_c"].append((tri[i].mean(axis=0) + tri[j].mean(axis=0)) / 2.0)

    # The pixels: first hit on a face of a pair, ray meets partner within depth_tol
    partners: dict[int, set] = {}
    plane_index: dict[int, int] = {}
    for k, p in enumerate(planes):
        for i, j, _s, _o in p["_pairs"]:
            partners.setdefault(i, set()).add(j)
            partners.setdefault(j, set()).add(i)
            plane_index[i] = plane_index[j] = k
    ids_all = np.arange(len(faces), dtype=np.int64)
    reusable = ReusableCaster(caster_factory)
    px_plane = np.zeros(len(planes), dtype=np.int64)

    ptr = np.zeros(len(faces) + 1, dtype=np.int64)
    for f, ps in partners.items():
        ptr[f + 1] = len(ps)
    ptr = np.cumsum(ptr)
    idx = np.zeros(int(ptr[-1]), dtype=np.int64)
    for f, ps in partners.items():
        idx[ptr[f]:ptr[f + 1]] = sorted(ps)
    plane_of_face = np.full(len(faces), -1, dtype=np.int64)
    for f, k in plane_index.items():
        plane_of_face[f] = k
    watched = np.array(sorted(partners), dtype=np.int64)
    is_watched = np.zeros(len(faces), dtype=bool)
    is_watched[watched] = True

    max_batch = 0
    for view in views:
        buf = ortho_first_hit(positions_c, faces, ids_all, view, positions_c, size, reusable)
        mask = (buf.tri >= 0) & is_watched[np.maximum(buf.tri, 0)]
        if not mask.any():
            continue
        rows, cols = np.nonzero(mask)
        first_f = buf.tri[rows, cols].astype(np.int64)
        first_t = buf.depth[rows, cols]
        origins = buf.xs[cols][:, None] * buf.right + buf.ys[rows][:, None] * buf.up + buf.standoff
        direction = np.asarray(buf.direction, dtype=np.float64)

        counts = ptr[first_f + 1] - ptr[first_f]
        cum = np.cumsum(counts)
        total_rows = int(cum[-1]) if len(cum) else 0
        if total_rows == 0:
            continue

        pixel_met = np.zeros(len(first_f), dtype=bool)
        for r_start in range(0, total_rows, chunk_rows):
            r_end = min(r_start + chunk_rows, total_rows)
            batch_len = r_end - r_start
            if batch_len > max_batch:
                max_batch = batch_len

            p_start = int(np.searchsorted(cum, r_start, side='right'))
            p_end = min(int(np.searchsorted(cum, r_end, side='left')) + 1, len(first_f))

            sub_f = first_f[p_start:p_end]
            sub_counts = counts[p_start:p_end]
            sub_pix = np.repeat(np.arange(p_start, p_end), sub_counts)
            sub_starts = np.repeat(ptr[sub_f] - np.concatenate(([0], np.cumsum(sub_counts)[:-1])), sub_counts)
            sub_partner = idx[sub_starts + np.arange(len(sub_pix))]

            offset = r_start - (cum[p_start - 1] if p_start > 0 else 0)
            ch_pix = sub_pix[offset : offset + batch_len]
            ch_partner = sub_partner[offset : offset + batch_len]

            v0 = tri[ch_partner, 0]
            e1 = tri[ch_partner, 1] - v0
            e2 = tri[ch_partner, 2] - v0
            pvec = np.cross(np.broadcast_to(direction, e2.shape), e2)
            det = np.einsum("ij,ij->i", e1, pvec)
            usable = np.abs(det) > 1e-12
            inv = np.where(usable, 1.0 / np.where(usable, det, 1.0), 0.0)
            s_vec = origins[ch_pix] - v0
            u = np.einsum("ij,ij->i", s_vec, pvec) * inv
            qvec = np.cross(s_vec, e1)
            v = (qvec @ direction) * inv
            t = np.einsum("ij,ij->i", e2, qvec) * inv
            eps = 1e-6
            met = usable & (u >= -eps) & (v >= -eps) & (u + v <= 1.0 + eps) & (np.abs(t - first_t[ch_pix]) <= depth_tol)
            pixel_met[ch_pix[met]] = True

        counted = np.nonzero(pixel_met)[0]
        np.add.at(px_plane, plane_of_face[first_f[counted]], 1)

    if stats is not None:
        stats["pixel_rows_max"] = max_batch
    px_plane = px_plane.tolist()

    shift = np.zeros(3) if centre is None else np.asarray(centre, dtype=np.float64)
    out_planes = []
    for k, p in enumerate(planes):
        out_planes.append({
            "normal": [round(float(v), 4) for v in p["_n"]],
            "offset": round(p["_d"] + float(p["_n"] @ shift), 4),
            "centroid": [round(float(v), 2) for v in np.mean(p["_c"], axis=0) + shift],
            "faces": sorted(int(f) for f in p["_faces"]),
            "pairs": len(p["_pairs"]),
            "opposite": sum(1 for _i, _j, _s, o in p["_pairs"] if o),
            "area": round(sum(s for _i, _j, s, _o in p["_pairs"]), 3),
            "px": px_plane[k]})
    out_planes.sort(key=lambda p: (-p["area"], p["faces"]))
    pair_list = sorted(([int(i), int(j), round(float(s), 3), bool(o)] for i, j, s, o in pairs_final),
                       key=lambda p: (-p[2], p[0], p[1]))
    return {"count": len(pairs_final), "area": round(sum(s for _i, _j, s, _o in pairs_final), 3),
            "px": int(sum(px_plane)), "planes": out_planes, "pair_list": pair_list}


