"""Per-pixel comparison between a BEFORE and AFTER orthographic render, and the guard-feedback
loop that uses it to decide which candidate faces can safely be removed.

Ported from the depth-only `damage()` check in `spike/10_ds_visibility.py` and the restore loop in
`spike/11_guard_feedback.py`, generalised with a material dimension: a face whose visible position
merely shifted onto a background of the SAME (and, for a flat material, colour-indistinguishable)
surface is tracked separately from a real hole or a material swap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from engine.guard.views import VIEWS_26, HitBuffers, ortho_first_hit
from engine.rays.caster import EmbreeCaster, ReusableCaster

# Per-pixel verdict codes, in priority order -- see `classify_pixels`.
PX_OK = 0
PX_HOLE = 1
PX_MATERIAL_CHANGED = 2
PX_MOVED_SAME_FLAT = 3
PX_MOVED_OTHER = 4
PX_EDGE_FLICKER = 5
PX_ZFIGHT_TIE = 6
PX_CRACK_CLOSED = 7
PX_FRAGMENT_REMOVED = 8
PX_BORDER_SHIFT = 9
PX_GROWN = 10

#: `(view, HitBuffers)` for one `ortho_first_hit` render.
RenderedView = tuple[Sequence[float], HitBuffers]

#: Block size of the border-shift distance search, in point x triangle pairs, so the bounding-box
#: prefilter's mask stays bounded whatever the size of the mesh.
_DISTANCE_BLOCK = 4_000_000

#: Angles per ring in the `PX_EDGE_FLICKER` test; two rings (at `depth_tol` and `depth_tol / 2`)
#: make 16 rays per candidate pixel.
_RING_ANGLES = 8

#: How many of those 16 BEFORE ring rays must already reproduce AFTER's centre verdict for the
#: pixel to be `PX_CRACK_CLOSED`. 12 of 16 is a clear majority of the neighbourhood while still
#: allowing the crack itself to swallow a few rays -- on file A's own pixel 14 of 16 reproduced.
_CRACK_RING_MIN = 12


def face_planes(positions: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """`(F, 4)` float64 supporting plane of every triangle: `[nx, ny, nz, d]` with `n` a unit
    normal and `n . x + d == 0` on the plane, so `|n . p + d|` is the distance from any point `p`.

    A zero-area triangle has no plane and gets an ALL-ZERO row; `classify_pixels` detects that
    (`n` is not a unit vector) and falls back to depth along the ray for those pixels."""
    positions = np.asarray(positions, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    out = np.zeros((len(faces), 4), dtype=np.float64)
    if not len(faces):
        return out
    tri = positions[faces]
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normal, axis=1)
    good = length > 0.0
    out[good, :3] = normal[good] / length[good, None]
    out[good, 3] = -np.einsum("ij,ij->i", out[good, :3], tri[good, 0])
    return out


def _displacement(before_depth: np.ndarray, before_tri: np.ndarray, after_depth: np.ndarray,
                   after_tri: np.ndarray, both: np.ndarray, origins, direction,
                   plane_before, plane_after) -> np.ndarray:
    """How far the visible SURFACE moved at each both-hit pixel:
    `max(dist(P_before, plane(face_after)), dist(P_after, plane(face_before)))`, where
    `P = origins[px] + depth[px] * direction` is the hit point.

    Falls back to `|t_before - t_after|` (depth along the ray) wherever the metric cannot be
    evaluated: no geometry supplied, or either face's plane undefined (zero area)."""
    with np.errstate(invalid="ignore"):
        out = np.abs(after_depth - before_depth)
    if origins is None or plane_before is None or plane_after is None or not both.any():
        return out

    origins = np.asarray(origins, dtype=np.float64)[both]
    direction = np.asarray(direction, dtype=np.float64)
    point_before = origins + before_depth[both][:, None] * direction
    point_after = origins + after_depth[both][:, None] * direction
    n_before = np.asarray(plane_before, dtype=np.float64)[before_tri[both]]
    n_after = np.asarray(plane_after, dtype=np.float64)[after_tri[both]]

    to_after = np.abs(np.einsum("ij,ij->i", point_before, n_after[:, :3]) + n_after[:, 3])
    to_before = np.abs(np.einsum("ij,ij->i", point_after, n_before[:, :3]) + n_before[:, 3])
    defined = (np.linalg.norm(n_before[:, :3], axis=1) > 0.0) & (np.linalg.norm(n_after[:, :3], axis=1) > 0.0)

    out[both] = np.where(defined, np.maximum(to_after, to_before), out[both])
    return out


def _frame_mismatch(b: HitBuffers, a: HitBuffers) -> str | None:
    """The name of the first camera-frame field a BEFORE/AFTER pair of renders disagrees on, or
    `None` when they share the whole frame.

    The whole frame, not just the view direction: `classify_pixels` takes the ray origins of BOTH
    hit points from the BEFORE buffer, so a pair framed on different bounding boxes (or rendered
    at different image sizes) does not even compare the same pixels, and every displacement it
    reports is measured from the wrong point. `direction`, `right`, `up`, `xs`, `ys` and
    `standoff` together ARE the origins grid (`origins[i, j] == xs[j]*right + ys[i]*up +
    standoff`), so comparing them compares the grid without materialising 13 MB of it."""
    if b.tri.shape != a.tri.shape:
        return "image size"
    for name in ("direction", "right", "up", "xs", "ys", "standoff"):
        mine, theirs = np.asarray(getattr(b, name)), np.asarray(getattr(a, name))
        if mine.shape != theirs.shape or not np.allclose(mine, theirs):
            return name
    return None


def _ring_probe(buffers: HitBuffers, caster_before, caster_after, depth_tol: float):
    """A `mask -> (tri_before, point_before, tri_after, point_after)` callable for
    `classify_pixels`: for each masked pixel, `2 * _RING_ANGLES` rays cast parallel to that
    pixel's own ray from a ring of image-plane offsets around it -- `_RING_ANGLES` at radius
    `depth_tol` and `_RING_ANGLES` at `depth_tol / 2` -- against BOTH geometries.

    `tri_*` are `(P, R)` int64 face indices into the corresponding geometry's `faces` array (`-1`
    for a miss) and `point_*` are `(P, R, 3)` float64 hit points (meaningless wherever `tri < 0`),
    ordered like `np.nonzero(mask)`. Both sides share the SAME camera frame and the SAME origins,
    which is what makes their verdicts comparable -- `compare_views` has already rejected a
    before/after pair whose frames differ. `mask` must be 2-D, like an `ortho_first_hit` buffer.

    The radii are in world units, deliberately: the question a ring answers is whether a boundary
    that moved by at most `depth_tol` could explain this pixel, which has nothing to do with how
    many pixels wide the image happens to be."""
    direction = np.asarray(buffers.direction, dtype=np.float64)

    def probe(mask: np.ndarray):
        rows, cols = np.nonzero(mask)
        origins = buffers.ring_origins(rows, cols, (depth_tol, depth_tol / 2.0), _RING_ANGLES)
        directions = np.tile(direction, (len(origins), 1))
        shape = (len(rows), 2 * _RING_ANGLES)
        out = []
        for caster in (caster_before, caster_after):
            tri, t = caster.first_hit(origins, directions)
            point = origins + np.where(tri >= 0, t, 0.0)[:, None] * direction
            out += [tri.reshape(shape), point.reshape(shape + (3,))]
        return tuple(out)

    return probe


def _tie_probe(buffers: HitBuffers, caster_before, caster_after):
    """A `mask -> ((ray, tri, t) before, (ray, tri, t) after)` callable for `classify_pixels`: for
    each masked pixel, its OWN centre ray is cast with `RayCaster.all_hits` against BOTH
    geometries, so every surface along it is listed, not just the nearest. `ray` indexes the
    masked pixels in `np.nonzero(mask)` order; `tri` indexes the corresponding geometry's `faces`.

    Building the origins from the camera frame (like `HitBuffers.ring_origins`) rather than
    slicing `buffers.origins` keeps this off the 13 MB full-image grid."""
    direction = np.asarray(buffers.direction, dtype=np.float64)

    def probe(mask: np.ndarray):
        rows, cols = np.nonzero(mask)
        origins = (buffers.xs[cols][:, None] * buffers.right
                   + buffers.ys[rows][:, None] * buffers.up + buffers.standoff)
        directions = np.tile(direction, (len(origins), 1))
        return (caster_before.all_hits(origins, directions),
                caster_after.all_hits(origins, directions))

    return probe


def _matches_tie_set(hit_ray: np.ndarray, hit_tri: np.ndarray, hit_t: np.ndarray,
                      t_first: np.ndarray, member_material: np.ndarray, member_plane: np.ndarray,
                      other_point: np.ndarray, other_material: np.ndarray, other_hit: np.ndarray,
                      depth_tol: float, n_pixels: int) -> np.ndarray:
    """Per candidate pixel `(P,)`: does the OTHER render's centre hit match some member of THIS
    render's tie set -- the surfaces this ray meets within `depth_tol` of its own first hit?

    "Matches" is the same test the ring uses: the same material, and a hit point within
    `depth_tol` of that member's supporting plane. A member with no plane (zero area) never
    matches, and a pixel whose other side MISSED matches nothing (a hole is not a tie)."""
    out = np.zeros(n_pixels, dtype=bool)
    if not len(hit_ray):
        return out
    in_set = np.abs(hit_t - t_first[hit_ray]) <= depth_tol
    ray, tri = hit_ray[in_set], hit_tri[in_set]
    if not len(ray):
        return out

    plane = member_plane[tri]
    normal, offset = plane[:, :3], plane[:, 3]
    distance = np.abs(np.einsum("ij,ij->i", other_point[ray], normal) + offset)
    match = (other_hit[ray] & (member_material[tri] == other_material[ray])
             & (distance <= depth_tol) & (np.linalg.norm(normal, axis=1) > 0.0))
    out[ray[match]] = True
    return out


def _ring_matches(centre_tri: np.ndarray, centre_material: np.ndarray, centre_plane: np.ndarray,
                   ring_tri: np.ndarray, ring_point: np.ndarray, ring_material: np.ndarray,
                   depth_tol: float) -> np.ndarray:
    """Per candidate pixel and ring ray `(P, R)`: does that ONE ring ray, cast against the other
    geometry, reproduce this geometry's CENTRE verdict?

    A centre MISS is reproduced by a ring ray that also misses. A centre HIT is reproduced by a
    ring ray that hits the same material at a point within `depth_tol` of the centre face's own
    supporting plane -- i.e. the other geometry still has that same surface, just beside the
    pixel rather than under it, which is exactly what a boundary that moved by less than the
    tolerance looks like. A centre face with no plane (zero area) is never reproduced.

    The flicker test asks whether ANY ray reproduces (`_ring_reproduces`); the crack test asks
    HOW MANY do, which is why this returns the whole matrix."""
    hit = ring_tri >= 0
    normal, offset = centre_plane[:, :3], centre_plane[:, 3]
    distance = np.abs(np.einsum("prk,pk->pr", ring_point, normal) + offset[:, None])
    defined = np.linalg.norm(normal, axis=1) > 0.0
    hit_matches = (hit & (ring_material == centre_material[:, None]) & (distance <= depth_tol)
                   & defined[:, None])
    return np.where((centre_tri >= 0)[:, None], hit_matches, ~hit)


def _ring_reproduces(centre_tri: np.ndarray, centre_material: np.ndarray, centre_plane: np.ndarray,
                      ring_tri: np.ndarray, ring_point: np.ndarray, ring_material: np.ndarray,
                      depth_tol: float) -> np.ndarray:
    """Per candidate pixel `(P,)`: does ANY of its ring rays reproduce the centre verdict?"""
    return _ring_matches(centre_tri, centre_material, centre_plane, ring_tri, ring_point,
                          ring_material, depth_tol).any(axis=1)


def _point_triangle_distance(points: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """`(N,)` exact Euclidean distance from `points[i]` `(N, 3)` to the closed triangle
    `triangles[i]` `(N, 3, 3)`: the perpendicular to its plane where the foot of it lands inside
    the triangle, otherwise the distance to the nearest point of its three edges. A zero-area
    (collinear) triangle has no inside, and is exactly its edges."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    triangles = np.asarray(triangles, dtype=np.float64).reshape(-1, 3, 3)
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]

    edge_distance = np.full(len(points), np.inf)
    for p0, p1 in ((a, b), (b, c), (c, a)):
        edge = p1 - p0
        length2 = np.einsum("ij,ij->i", edge, edge)
        along = np.einsum("ij,ij->i", points - p0, edge) / np.where(length2 > 0.0, length2, 1.0)
        nearest = p0 + np.clip(np.where(length2 > 0.0, along, 0.0), 0.0, 1.0)[:, None] * edge
        edge_distance = np.minimum(edge_distance, np.linalg.norm(points - nearest, axis=1))

    normal = np.cross(b - a, c - a)
    normal2 = np.einsum("ij,ij->i", normal, normal)
    inside = normal2 > 0.0
    for p0, p1 in ((a, b), (b, c), (c, a)):
        inside &= np.einsum("ij,ij->i", np.cross(p1 - p0, points - p0), normal) >= 0.0
    plane_distance = (np.abs(np.einsum("ij,ij->i", points - a, normal))
                      / np.sqrt(np.where(inside, normal2, 1.0)))
    return np.where(inside, np.minimum(edge_distance, plane_distance), edge_distance)


def _nearest_triangle_distance(points: np.ndarray, triangles: np.ndarray, reach: float) -> np.ndarray:
    """`(P,)` distance from each of `points` `(P, 3)` to the nearest of `triangles` `(F, 3, 3)` --
    EVERY triangle, whatever plane it lies in. Exact wherever that distance is within `reach`;
    a point with nothing within `reach` gets a number above it (`inf` when no triangle's bounding
    box comes that close).

    Brute force behind an axis-aligned bounding-box prefilter expanded by `reach`: a triangle
    whose expanded box does not contain the point is further than `reach` from it, so it is never
    measured. The `points x triangles` mask is built a block of points at a time
    (`_DISTANCE_BLOCK` pairs), so it stays bounded however big the mesh is."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    triangles = np.asarray(triangles, dtype=np.float64).reshape(-1, 3, 3)
    out = np.full(len(points), np.inf)
    if not len(points) or not len(triangles):
        return out
    lo = triangles.min(axis=1) - reach
    hi = triangles.max(axis=1) + reach
    block = max(1, _DISTANCE_BLOCK // len(triangles))
    for start in range(0, len(points), block):
        chunk = points[start:start + block]
        near = ((chunk[:, None, :] >= lo[None]) & (chunk[:, None, :] <= hi[None])).all(axis=2)
        point, tri = np.nonzero(near)
        if len(point):
            np.minimum.at(out, start + point, _point_triangle_distance(chunk[point], triangles[tri]))
    return out


def _border_probe(geometry_before, geometry_after, tol: float):
    """A `(points, gone) -> within` callable for `classify_pixels`: is each of `points` `(P, 3)`
    within `tol` of the OTHER geometry? `gone[i]` True measures a BEFORE hit point against every
    AFTER triangle -- something disappeared there; False measures an AFTER hit point against every
    BEFORE triangle -- something appeared. `geometry_*` are `(positions, faces)`, exactly as
    `compare_views` takes them, and are turned into triangles once, not once per view."""
    before, after = (np.asarray(positions, dtype=np.float64)[np.asarray(faces, dtype=np.int64).reshape(-1, 3)]
                     for positions, faces in (geometry_before, geometry_after))

    def probe(points: np.ndarray, gone: np.ndarray) -> np.ndarray:
        points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        gone = np.asarray(gone, dtype=bool).reshape(-1)
        distance = np.full(len(points), np.inf)
        for side, triangles in ((gone, after), (~gone, before)):
            if side.any():
                distance[side] = _nearest_triangle_distance(points[side], triangles, tol)
        return distance <= tol

    return probe


def classify_pixels(before_depth: np.ndarray, before_tri: np.ndarray,
                     after_depth: np.ndarray, after_tri: np.ndarray,
                     material_before: np.ndarray, material_after: np.ndarray,
                     flat_materials: Iterable[int], depth_tol: float, *,
                     origins: np.ndarray | None = None, direction: np.ndarray | None = None,
                     plane_before: np.ndarray | None = None,
                     plane_after: np.ndarray | None = None,
                     ring=None, tie=None, allow_depth_fallback: bool = False,
                     strict: bool = False,
                     removed_before: np.ndarray | None = None, border=None,
                     exposed_after: np.ndarray | None = None) -> np.ndarray:
    """Per-pixel verdict code, same shape as the inputs (uint8, one of the `PX_*` constants), in
    this priority order: `PX_FRAGMENT_REMOVED` (BEFORE's first hit is a face `removed_before`
    marks and AFTER shows what it may, see below); `PX_HOLE` (hit before, miss after); `PX_MATERIAL_CHANGED` (both hit,
    `material_before[before_tri] != material_after[after_tri]`); `PX_MOVED_SAME_FLAT` /
    `PX_MOVED_OTHER` (both hit, same material, the visible surface moved further than `depth_tol`
    -- `_SAME_FLAT` when that material index is in `flat_materials`, `_OTHER` otherwise); `PX_OK`
    otherwise (includes both-miss background pixels and pixels that matched within `depth_tol`).

    A pixel whose base class FAILS under the current strictness is then re-checked, in this order,
    by the TIE test, the CRACK test and the RING test, and promoted to `PX_ZFIGHT_TIE`,
    `PX_CRACK_CLOSED` or `PX_EDGE_FLICKER` if one of them passes. "Fails under the current
    strictness" means `PX_HOLE`, `PX_MATERIAL_CHANGED` or
    `PX_MOVED_OTHER` always, and `PX_MOVED_SAME_FLAT` only when `strict` -- see `_failing_base`. A
    base class the caller already TOLERATES keeps its class: promoting it would move a tolerated
    pixel into `edge_flicker`, which IS capped, so a non-strict run could fail on pixels it had
    decided not to mind (measured: 15 of 991 tolerated `moved_same_flat` pixels re-classed as
    flicker, over a 1e-4 cap in a 9,291 px view).

    `removed_before` is a bool mask over `material_before`'s faces. A pixel whose BEFORE first hit
    is one of them is `PX_FRAGMENT_REMOVED` before any other test runs -- never a failure, never
    promotable, and counted on its own -- when what AFTER shows there is something the removal
    MAY uncover: the sky (AFTER missed), or a face met on a side `exposed_after` marks as already
    exposed on the reference (`(F_after, 2)` bool, column 0 the FRONT, column 1 the BACK; the ray
    meets the back where `n . direction > 0`, as in `solidify_feedback`). Anything else -- the
    inside of a closed shell, a side nobody could see before -- is not debris disappearing, it is
    a hole, and the pixel keeps its own class and is judged like every other. Without
    `exposed_after` only the sky qualifies. It exists for `engine.detectors.fragments`, the one
    removal in the engine that deliberately changes the picture: those faces were debris a person
    could see, so the pixels they occupied MUST differ -- into what was already outside -- and
    every other pixel must not. It used to excuse every such pixel by name, whatever AFTER showed,
    and review C2's probe shipped a hole in a slab's top that way with `passed` True.

    Stated as a pixel rule rather than by leaving the faces out of the BEFORE geometry, which is
    not the same thing and is wrong. Measured on file A: a sliver hides a face the hidden pass
    had already deleted -- correctly, because the sliver covered it -- and a BEFORE render
    without that sliver puts the deleted face back on screen and reports 749 moved pixels of
    damage that never existed. The pixel rule excuses exactly the pixels the debris occupied,
    including whatever was behind it.

    THE TIE TEST. Given `tie` (build one with `_tie_probe`; `compare_views` does), a failing pixel
    gets its own centre ray re-cast with `RayCaster.all_hits` in both geometries. Its BEFORE TIE
    SET is every surface that ray meets within `depth_tol` of BEFORE's first hit, and likewise
    AFTER's. The pixel is `PX_ZFIGHT_TIE` iff AFTER's first hit matches a member of BEFORE's tie
    set AND BEFORE's first hit matches a member of AFTER's -- "matches" meaning the same material
    and a hit point within `depth_tol` of that member's supporting plane. BOTH directions are
    required, so a pixel where one member of an overlapping pair was REMOVED still fails; only a
    pixel where both surfaces are still there, at the same depth, and merely swapped places, is a
    tie. Measured on file B: 12 pixels where BEFORE hits face 2654 (material 1) and AFTER hits
    face 73 (material 0) at the same 5867.73 in, neither removed. Ties are never failures at any
    cap -- the overlap is a defect this run neither caused nor can fix here -- and are counted as
    `zfight_tie` so the overlap detector has the evidence.

    THE CRACK TEST, evaluated after the tie test and before the ring test, on the same 16 ring
    rays. A pixel is `PX_CRACK_CLOSED` when at least `_CRACK_RING_MIN` (12 of 16) of its BEFORE
    ring rays already reproduce AFTER's CENTRE verdict -- the same material and a hit point within
    `depth_tol` of AFTER's centre-hit face's plane, or a miss where AFTER's centre missed. Then
    BEFORE's centre ray, and only it, went somewhere its whole neighbourhood did not: it slipped
    through a sub-tolerance crack or caught a sliver, and AFTER closed it. Measured on file A:
    pixel (530, 338) of view (-0.987, 0.007, -0.989), where BEFORE's ray found a 0.02 in T-junction
    gap (2 of 201 rays at 0.02 in steps reached through it) while 14 of its 16 ring rays already
    met the surface the merge then presented. Never a failure at any cap; counted as
    `crack_closed`, which is a POSITIVE metric -- sparkle pixels the fix removed.

    ITS LIMIT, deliberately: damage NARROWER than the ring radius (`depth_tol`) is
    indistinguishable from a closed crack. A genuinely lost sliver thinner than that, with intact
    surface on both sides of it, reads as a crack the fix closed. The ring radius is the merge's
    own working tolerance, so this is the same bound everything else here is judged at.

    THE RING TEST. Given `ring`, each failing-base pixel gets 16 extra rays cast parallel to
    its own, from a ring of image-plane offsets around it: 8 at radius `depth_tol` and 8 at
    `depth_tol / 2`, at 45-degree steps, in BOTH geometries (build one with `_ring_probe`;
    `compare_views` does). The pixel is `PX_EDGE_FLICKER` iff (1) at least one AFTER ring ray
    reproduces BEFORE's centre verdict AND (2) at least one BEFORE ring ray reproduces AFTER's --
    "reproduces" meaning a hit of the same material within `depth_tol` of the centre-hit face's
    plane, or a miss when the centre missed (see `_ring_reproduces`). Otherwise the failure class
    stands.

    That is the bound the merge itself works to: re-triangulating a region over its own vertices
    can drop a nearly-collinear ring vertex, which moves the region's boundary by at most the
    collinearity tolerance, and at a grazing pixel that is enough to change which of two real
    surfaces the ray meets first. Both halves are needed: (1) alone would tolerate a surface that
    really vanished as long as something similar sat nearby, (2) alone would tolerate a surface
    that really appeared. Together they say the two pictures differ only by a boundary that moved
    less than the tolerance -- which is as true at an INTERNAL silhouette (one real surface in
    front of another), where there is no background pixel anywhere in the image, as at the model's
    outer edge.

    Passing no `ring` means no pixel is ever flicker, which is correct exactly where flicker and
    the real class are treated alike (`guard_feedback`, cap 0.0). `plane_before`/`plane_after` are
    required for the ring test as well, so a `ring` given without them is ignored.

    THE BORDER-SHIFT MEASUREMENT, the last step. Given `border` (build one with `_border_probe`;
    `compare_views` does, at its `border_shift_tol`), every `PX_EDGE_FLICKER` pixel whose BASE
    class is a hole or a move is MEASURED, and becomes `PX_BORDER_SHIFT` when the surface under
    it really moved no further than that tolerance. Where something DISAPPEARED -- AFTER's ray
    missed, or met the scene further away than BEFORE's -- the displacement is the distance from
    BEFORE's hit point to the nearest AFTER triangle; where something APPEARED -- AFTER's ray met
    the scene nearer, or BEFORE's missed -- it is the distance from AFTER's hit point to the
    nearest BEFORE triangle. Exact point-to-triangle distances, over EVERY triangle of the other
    mesh whatever plane it lies in: quantised sloped faces are not coplanar within 0.05 in, so a
    same-plane filter finds nothing to measure against. A flicker pixel rescued from a MATERIAL
    change is never measured -- a surface that changed colour did not move -- and one measured
    further than the tolerance stays `PX_EDGE_FLICKER`, capped exactly as before. A border-shift
    pixel is never a failure, never capped, and counted on its own (`border_shift`).

    WHY A MEASUREMENT AND NOT A COUNT. The ring says a boundary within its radius COULD explain a
    pixel -- in the IMAGE plane, so seen at grazing incidence it spans inches of surface -- and
    says nothing about how far anything moved. `compare_views` answered that with a per-view
    pixel count (`edge_flicker_cap`), and a count measures how many pixel centres a moved edge
    happens to cross, not how far it moved: an edge lying almost on a row of pixel centres flips
    the whole run for a 0.013 in shift. Measured on file A: its merge was rolled back on flicker
    alone -- view 0 had 14 flicker pixels against a cap of 11.4, 9 of them one run along pixel
    row 133 where merged region 2 reaches 0.0002 to 0.013 in past its original border -- while
    every failing pixel lay within 0.062 in of the other mesh, far inside the 0.15 in the merge
    may move a border.

    "Moved" is SURFACE DISPLACEMENT, not depth along the ray: `_displacement` above. Depth along
    the ray divides the real offset by the sine of the grazing angle, so a 0.005 in plane offset
    seen 0.5 degrees off the surface reads as 0.5 in and a correct re-triangulation is reported as
    moved (measured: 676 px on file A). The displacement metric needs the hit points and both
    planes: pass `origins` (`(..., 3)`, from `HitBuffers.origins`), `direction` (the unit view
    direction, shared by before and after), and `plane_before` / `plane_after` (`face_planes` of
    the two geometries, indexed like `material_before` / `material_after`).

    Omitting any of those four is an ERROR unless `allow_depth_fallback=True`: the whole-image
    fallback to `|t_before - t_after|` is the metric that produced those 676 false positives, so a
    caller has to ask for it by name rather than get it for forgetting an argument. A pixel whose
    before- or after-face has no plane (zero area) still falls back on its own -- that is per
    pixel, not a caller mistake."""
    return _classify(before_depth, before_tri, after_depth, after_tri, material_before,
                      material_after, flat_materials, depth_tol, origins=origins,
                      direction=direction, plane_before=plane_before, plane_after=plane_after,
                      ring=ring, tie=tie, allow_depth_fallback=allow_depth_fallback,
                      strict=strict, removed_before=removed_before, border=border,
                      exposed_after=exposed_after)[0]


def _failing_base(codes: np.ndarray, strict: bool) -> np.ndarray:
    """Which BASE classes fail under the current strictness, and so may be promoted to one of the
    tolerated classes (`PX_ZFIGHT_TIE`, `PX_CRACK_CLOSED`, `PX_EDGE_FLICKER`). Deliberately the
    same rule `_fail_mask` applies to the FINAL codes, minus the promoted classes themselves."""
    fail = ((codes == PX_HOLE) | (codes == PX_MATERIAL_CHANGED) | (codes == PX_MOVED_OTHER)
            | (codes == PX_GROWN))
    if strict:
        fail = fail | (codes == PX_MOVED_SAME_FLAT)
    return fail


def _classify(before_depth: np.ndarray, before_tri: np.ndarray,
               after_depth: np.ndarray, after_tri: np.ndarray,
               material_before: np.ndarray, material_after: np.ndarray,
               flat_materials: Iterable[int], depth_tol: float, *,
               origins=None, direction=None, plane_before=None, plane_after=None,
               ring=None, tie=None, allow_depth_fallback: bool = False,
               strict: bool = False,
               removed_before: np.ndarray | None = None,
               border=None,
               exposed_after: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """`classify_pixels`, plus the BASE codes -- what every pixel was classed before the ring test
    rescued any of it, or the fragment excuse excused it -- so `compare_views` can report which
    class each flicker pixel came from (`edge_flicker_hole` / `_moved` / `_material`) without
    measuring displacement twice, and put a capped class back to what it was."""
    if not allow_depth_fallback and (origins is None or direction is None
                                      or plane_before is None or plane_after is None):
        raise ValueError(
            "classify_pixels needs the geometry of BOTH renders to measure surface displacement: "
            "origins, direction, plane_before and plane_after (see face_planes). Without all four "
            "the moved test falls back to depth along the ray, which divides the real offset by "
            "the sine of the grazing angle and reported 676 false `moved` pixels on file A. Pass "
            "allow_depth_fallback=True to ask for that metric deliberately.")

    before_tri = np.asarray(before_tri)
    after_tri = np.asarray(after_tri)
    before_depth = np.asarray(before_depth, dtype=np.float64)
    after_depth = np.asarray(after_depth, dtype=np.float64)
    material_before = np.asarray(material_before)
    material_after = np.asarray(material_after)

    hit_before = before_tri >= 0
    hit_after = after_tri >= 0
    codes = np.full(before_tri.shape, PX_OK, dtype=np.uint8)
    codes[hit_before & ~hit_after] = PX_HOLE
    codes[~hit_before & hit_after] = PX_GROWN

    both = hit_before & hit_after
    # materials of EVERY hit pixel, not only both-hit ones: the ring test needs BEFORE's material
    # at a would-be hole too, where AFTER has none.
    mat_before = np.full(before_tri.shape, -1, dtype=np.int64)
    mat_after = np.full(after_tri.shape, -1, dtype=np.int64)
    mat_before[hit_before] = material_before[before_tri[hit_before]]
    mat_after[hit_after] = material_after[after_tri[hit_after]]
    material_changed = both & (mat_before != mat_after)
    codes[material_changed] = PX_MATERIAL_CHANGED

    same_material = both & ~material_changed
    moved = same_material & (_displacement(before_depth, before_tri, after_depth, after_tri, both,
                                            origins, direction, plane_before, plane_after) > depth_tol)
    flat_ids = np.array(sorted(flat_materials), dtype=np.int64)
    is_flat = np.isin(mat_before, flat_ids)
    codes[moved & is_flat] = PX_MOVED_SAME_FLAT
    codes[moved & ~is_flat] = PX_MOVED_OTHER

    # ...and then, over everything: a pixel whose BEFORE first hit was DELIBERATELY deleted
    # debris, where AFTER shows only what that deletion may uncover. Stamped last so it wins over
    # every other class, and AFTER `base` is taken so a capped fragment pixel can fall back to
    # what it really is -- but it is taken out of `promotable`, so it is never promoted either.
    base = codes.copy()
    if removed_before is not None:
        gone = np.asarray(removed_before, dtype=bool)
        own = hit_before & gone[np.where(hit_before, before_tri, 0)]
        may_show = ~hit_after
        if exposed_after is not None and plane_after is not None and direction is not None:
            exposed = np.asarray(exposed_after, dtype=bool).reshape(-1, 2)
            normal = np.asarray(plane_after, dtype=np.float64).reshape(-1, 4)[:, :3]
            ids = np.where(hit_after, after_tri, 0)
            facing = normal[ids] @ np.asarray(direction, dtype=np.float64)
            side = np.where(facing > 0.0, exposed[ids, 1], exposed[ids, 0])
            # a face with no plane has no side a ray could be said to meet
            may_show |= hit_after & side & (np.linalg.norm(normal[ids], axis=-1) > 0.0)
        codes[own & may_show] = PX_FRAGMENT_REMOVED

    promotable = _failing_base(codes, strict)
    have_planes = plane_before is not None and plane_after is not None
    if not have_planes or not promotable.any():
        return codes, base

    # One padded row per lookup table, so a miss (`-1`) reads a material of -1 and an all-zero
    # (undefined) plane instead of wrapping around -- and so an empty geometry is still safe.
    planes_b = np.vstack([np.asarray(plane_before, dtype=np.float64).reshape(-1, 4), np.zeros((1, 4))])
    planes_a = np.vstack([np.asarray(plane_after, dtype=np.float64).reshape(-1, 4), np.zeros((1, 4))])
    mats_b = np.append(material_before.astype(np.int64).reshape(-1), -1)
    mats_a = np.append(material_after.astype(np.int64).reshape(-1), -1)

    def _promote(mask: np.ndarray, chosen: np.ndarray, code: int) -> np.ndarray:
        """Set `code` on the `chosen` subset of `mask`'s pixels and drop them from `mask`."""
        where = np.nonzero(mask)
        codes[tuple(axis[chosen] for axis in where)] = code
        still = mask.copy()
        still[tuple(axis[chosen] for axis in where)] = False
        return still

    # ---- z-fight ties: the same two overlapping surfaces, a different winner ------------------
    if tie is not None and origins is not None and direction is not None:
        (ray_b, hit_tri_b, t_b), (ray_a, hit_tri_a, t_a) = tie(promotable)
        origin_c = np.asarray(origins, dtype=np.float64)[promotable]
        direction = np.asarray(direction, dtype=np.float64)
        t_first_b, t_first_a = before_depth[promotable], after_depth[promotable]
        hit_b_c, hit_a_c = hit_before[promotable], hit_after[promotable]
        point_c_b = origin_c + np.where(hit_b_c, t_first_b, 0.0)[:, None] * direction
        point_c_a = origin_c + np.where(hit_a_c, t_first_a, 0.0)[:, None] * direction
        n_px = len(t_first_b)
        is_tie = (
            _matches_tie_set(ray_b, hit_tri_b, t_b, t_first_b, mats_b, planes_b,
                             point_c_a, mat_after[promotable], hit_a_c, depth_tol, n_px)
            & _matches_tie_set(ray_a, hit_tri_a, t_a, t_first_a, mats_a, planes_a,
                               point_c_b, mat_before[promotable], hit_b_c, depth_tol, n_px))
        promotable = _promote(promotable, is_tie, PX_ZFIGHT_TIE)

    # ---- one ring cast, two questions: was the crack closed, or did a boundary flicker? -------
    if ring is not None and promotable.any():
        tri_b, point_b, tri_a, point_a = ring(promotable)
        centre_b, centre_a = before_tri[promotable], after_tri[promotable]
        # BEFORE's own ring rays against AFTER's centre verdict -- the crack test counts them,
        # the flicker test only asks whether any of them reproduced.
        before_ring = _ring_matches(centre_a, mat_after[promotable], planes_a[centre_a],
                                     tri_b, point_b, mats_b[tri_b], depth_tol)
        after_ring = _ring_matches(centre_b, mat_before[promotable], planes_b[centre_b],
                                    tri_a, point_a, mats_a[tri_a], depth_tol)
        crack = before_ring.sum(axis=1) >= _CRACK_RING_MIN
        steady = ~crack & after_ring.any(axis=1) & before_ring.any(axis=1)
        promotable = _promote(promotable, crack, PX_CRACK_CLOSED)
        _promote(promotable, steady[~crack], PX_EDGE_FLICKER)

    # ---- border shift: how far did the surface under a flicker pixel REALLY move? ------------
    if border is not None and origins is not None and direction is not None:
        shift = (codes == PX_EDGE_FLICKER) & ((base == PX_HOLE) | (base == PX_MOVED_SAME_FLAT)
                                               | (base == PX_MOVED_OTHER) | (base == PX_GROWN))
        if shift.any():
            t_b, t_a = before_depth[shift], after_depth[shift]
            # something DISAPPEARED where AFTER missed or met the scene further away, and BEFORE's
            # hit point is measured against AFTER; anywhere else something APPEARED, and AFTER's
            # hit point is measured against BEFORE
            gone = ~hit_after[shift] | (t_a > t_b)
            t = np.where(gone, t_b, t_a)
            point = (np.asarray(origins, dtype=np.float64)[shift]
                     + np.where(np.isfinite(t), t, 0.0)[:, None] * np.asarray(direction, dtype=np.float64))
            within = border(point, gone) & np.isfinite(t)
            codes[shift] = np.where(within, PX_BORDER_SHIFT, PX_EDGE_FLICKER)
    return codes, base


@dataclass
class ViewVerdict:
    view: tuple[float, float, float]
    model_px: int
    holes: int
    moved_same_flat: int
    moved_other: int
    material_changed: int
    #: Pixels where BEFORE and AFTER met two overlapping surfaces at the same depth and merely
    #: swapped which one won -- both still present in both meshes. Never a failure; evidence of a
    #: pre-existing z-fight overlap, not of damage. See `classify_pixels`.
    zfight_tie: int
    #: Pixels where BEFORE's centre ray alone slipped through a sub-tolerance crack that AFTER
    #: closed -- an improvement, not damage, and never a failure. See `classify_pixels`.
    crack_closed: int
    edge_flicker: int
    #: Pixels whose BEFORE first hit was debris `engine.detectors.fragments` deleted on purpose.
    #: Never a failure -- the whole point of that pass is that these pixels change. See
    #: `classify_pixels`.
    fragment_removed: int
    #: `edge_flicker` split by the class each of those pixels was rescued FROM; the three always
    #: sum to `edge_flicker`, so a report says whether a tolerated pixel was a would-be hole, a
    #: would-be move (`moved_same_flat` or `moved_other`), or a would-be material swap.
    edge_flicker_hole: int
    edge_flicker_moved: int
    edge_flicker_material: int
    #: Flicker pixels MEASURED as a border that moved no further than `compare_views`'
    #: `border_shift_tol` -- never a failure and never capped, and no longer counted in
    #: `edge_flicker` or its breakdown. Always 0 at the default tolerance of 0.0. See
    #: `classify_pixels`.
    border_shift: int
    grown: int = 0
    edge_flicker_grown: int = 0


@dataclass
class GuardReport:
    views: list[ViewVerdict]
    passed: bool
    totals: dict


def _zero_totals() -> dict:
    return {"model_px": 0, "holes": 0, "material_changed": 0, "moved_same_flat": 0, "moved_other": 0,
            "zfight_tie": 0, "crack_closed": 0, "edge_flicker": 0, "fragment_removed": 0,
            "edge_flicker_hole": 0, "edge_flicker_moved": 0,
            "edge_flicker_material": 0, "border_shift": 0,
            "grown": 0, "edge_flicker_grown": 0}


def _fail_mask(codes: np.ndarray, strict: bool, flicker_fails: bool = True) -> np.ndarray:
    """Which pixels count as damage. `flicker_fails` is the per-view outcome of the
    `edge_flicker_cap` test; at the default cap of 0.0 a flicker pixel fails exactly like a hole."""
    fail = (codes == PX_HOLE) | (codes == PX_MATERIAL_CHANGED) | (codes == PX_MOVED_OTHER) | (codes == PX_GROWN)
    if flicker_fails:
        fail = fail | (codes == PX_EDGE_FLICKER)
    if strict:
        fail = fail | (codes == PX_MOVED_SAME_FLAT)
    return fail


def compare_views(before: Sequence[RenderedView], after: Sequence[RenderedView],
                   face_material_before: np.ndarray, face_material_after: np.ndarray,
                   flat_materials: Iterable[int], depth_tol: float,
                   strict: bool = False, plane_before: np.ndarray | None = None,
                   plane_after: np.ndarray | None = None,
                   edge_flicker_cap: float = 0.0,
                   crack_closed_cap: float = float("inf"),
                   geometry_before: tuple[np.ndarray, np.ndarray] | None = None,
                   geometry_after: tuple[np.ndarray, np.ndarray] | None = None,
                   caster_factory=EmbreeCaster,
                   allow_depth_fallback: bool = False,
                   removed_before: np.ndarray | None = None,
                   border_shift_tol: float = 0.0,
                   exposed_after: np.ndarray | None = None,
                   fragment_removed_cap: float = float("inf")) -> GuardReport:
    """Compare a BEFORE/AFTER pair of `ortho_first_hit` renders, one `(view, HitBuffers)` pair per
    view, paired by position (`before[i]` and `after[i]` must be the same view, and both sequences
    the same length). Each pair must share the whole CAMERA FRAME -- direction, image size and the
    origins grid -- or `ValueError` names the view and the field that differs; comparing renders
    framed on different bounding boxes would silently measure displacement from the wrong points.

    `plane_before` / `plane_after` are `face_planes` of the two geometries, indexed like
    `face_material_before` / `face_material_after`; they are what the surface-displacement moved
    test needs (see `classify_pixels`), and leaving them out raises unless the caller asks for the
    old depth-along-the-ray metric with `allow_depth_fallback=True`. Given `geometry_before` /
    `geometry_after`, though, they are DERIVED from it rather than demanded, since they are a pure
    function of it -- so supplying the geometry alone never silently skips the tests that need
    planes.

    `strict=True` (use for automatic removal of exposure-0 faces -- a depth change there means
    sampling missed real visibility) counts `moved_same_flat` pixels as failures too;
    `strict=False` (use for a change a person already accepted) reports them but tolerates them.
    `strict` also decides which base classes are eligible for the ring test at all: a class this
    report TOLERATES is never promoted to `edge_flicker` (which is capped) -- see
    `classify_pixels`.

    `geometry_before` / `geometry_after` are `(positions, faces)` -- the two geometries the renders
    were cast against, `faces` indexed like the corresponding `face_material`. Given both, every
    would-be failure pixel (hole, material change or move alike) is re-checked with a RING of 16
    rays around it in each geometry and reclassified `PX_EDGE_FLICKER` when the two pictures
    differ only by a boundary that moved less than `depth_tol` -- see `classify_pixels` for the
    rule. That costs two casters and 16 rays per failing pixel, not a third render. Omit them and
    nothing is ever flicker -- safe only at `edge_flicker_cap = 0.0`, where flicker would fail
    exactly like the class it came from.

    `edge_flicker_cap` is judged PER VIEW: that view's `edge_flicker` pixels are tolerated only
    while `edge_flicker <= edge_flicker_cap * model_px`, otherwise all of them count as failures.
    At the default 0.0 every flicker pixel fails exactly like a hole, so hidden-face removal keeps
    its zero-tolerance behaviour. `edge_flicker_cap > 0.0` REQUIRES both `geometry_before` and
    `geometry_after`, and raises `ValueError` otherwise: without them there is no ring to cast, so
    a nonzero cap would tolerate nothing while looking as though it tolerated something.

    `crack_closed_cap` is the same per-view test for `PX_CRACK_CLOSED`, and exists because the
    crack test's own documented limit is that damage NARROWER than the ring radius is
    indistinguishable from a crack the fix closed. A handful of such pixels is the improvement it
    claims to be; a FIELD of them is a picture that changed for a reason this test cannot see.
    Over the cap that view's crack pixels FALL BACK to the base class they were promoted from
    (hole / material change / move -- always a class that fails under this report's strictness,
    since only failing base classes are promotable at all), so the counts say what actually
    happened instead of showing a tolerated improvement beside `passed: False`. That is the one
    place this differs from flicker, which keeps its class and is merely counted as failing.
    The default `inf` never caps, which is what this has always done; `engine.fixes.pipeline`
    passes `FixProfile.crack_closed_cap`.

    `zfight_tie` is deliberately NOT capped, at any number: an overlap this run neither caused
    nor can fix here is not evidence about this run, however much of the picture it covers.

    `removed_before` names faces this run deleted ON PURPOSE as debris, under their own guard
    (`fragment_feedback`), and `exposed_after` says which sides of the AFTER faces were already
    outside surfaces on the reference: a pixel of one of those faces is `PX_FRAGMENT_REMOVED`
    only where AFTER shows the sky or such a side (see `classify_pixels`), and is judged like any
    other pixel everywhere else. `fragment_removed_cap` caps it PER VIEW exactly as
    `crack_closed_cap` caps cracks: over `fragment_removed_cap * model_px` that view's fragment
    pixels fall back to the class they would have had without the excuse, and fail as that. A
    handful of debris pixels is the debris; a field of them is a change nobody named. The default
    `inf` never caps; `engine.fixes.pipeline` passes `FixProfile.fragment_removed_cap`. It used
    to be uncapped, and the excuse unconditional (review C2).

    `border_shift_tol` MEASURES what the flicker cap can only count. Above 0.0, every flicker
    pixel rescued from a hole, move or grown silhouette gets the real clearance of the surface
    under it -- the exact Euclidean clearance from the hit point to the nearest triangle of the
    OTHER geometry (taken over any surface within reach, as quantised sloped faces are not coplanar
    within small tolerances; see `classify_pixels`) -- and is `PX_BORDER_SHIFT` when that clearance
    is within the tolerance: counted as `border_shift`, never a failure, never capped, and no longer
    part of `edge_flicker` or its breakdown. Flicker measured further than the tolerance, and every
    pixel, stay `PX_EDGE_FLICKER` and are capped exactly as before. The default 0.0 measures
    nothing, which is what this has always done; `engine.fixes.pipeline` passes the merge's own
    border tolerance to the guards that judge a merged mesh and 0.0 to the removal guard. Above
    0.0 it REQUIRES both `geometry_before` and `geometry_after`, and raises `ValueError`
    otherwise: the measurement is a distance to the other mesh's triangles, and the flicker it
    re-classes needs both meshes for its ring, so without them a tolerance would excuse nothing
    while looking as though it excused something.

    `passed` is `holes + material_changed + moved_other == 0`, plus `moved_same_flat` when
    `strict`, plus the flicker pixels of any view over the cap; `border_shift` never counts.
    Every count -- `moved_same_flat`, `edge_flicker` and its `edge_flicker_hole` / `_moved` /
    `_material` breakdown, `border_shift` included -- is always reported in `totals` and every
    `ViewVerdict`, never silently dropped."""
    if len(before) != len(after):
        raise ValueError(f"before/after must have the same number of views, got {len(before)} vs {len(after)}")
    if edge_flicker_cap > 0.0 and (geometry_before is None or geometry_after is None):
        raise ValueError(
            f"compare_views was given edge_flicker_cap={edge_flicker_cap} but no geometry_before/"
            "geometry_after: without them there is no ring to cast around a failing pixel, so "
            "nothing is ever classed edge_flicker and the cap would tolerate nothing while looking "
            "as though it tolerated something. Pass geometry_before and geometry_after (positions, "
            "faces) so failing pixels get the ring test, or use edge_flicker_cap=0.0. Planes alone "
            "are not enough -- they say what a ring ray hit, not where to cast it.")
    if border_shift_tol > 0.0 and (geometry_before is None or geometry_after is None):
        raise ValueError(
            f"compare_views was given border_shift_tol={border_shift_tol} but not both "
            "geometry_before and geometry_after: the border-shift measurement is a distance to the "
            "OTHER mesh's triangles, and the flicker pixels it re-classes need both meshes for "
            "their ring, so a nonzero tolerance would excuse nothing while looking as though it "
            "excused something. Pass geometry_before and geometry_after (positions, faces), or use "
            "border_shift_tol=0.0.")

    # The ring, tie and crack tests ALSO need the planes, and a caller who supplied the geometry
    # has already said everything needed to build them: deriving them here is what stops a cap
    # above zero from silently skipping every one of those tests (the ValueError above only ever
    # checked the geometry, so `geometry` without `planes` tolerated nothing while looking as
    # though it tolerated something -- R2b). They are a pure function of the geometry, so a caller
    # who passes both gets exactly the same numbers.
    if plane_before is None and geometry_before is not None:
        plane_before = face_planes(*geometry_before)
    if plane_after is None and geometry_after is not None:
        plane_after = face_planes(*geometry_after)

    caster_before = caster_factory(*geometry_before) if geometry_before is not None else None
    caster_after = caster_factory(*geometry_after) if geometry_after is not None else None
    border = (_border_probe(geometry_before, geometry_after, border_shift_tol)
              if border_shift_tol > 0.0 else None)

    view_verdicts = []
    totals = _zero_totals()
    fail_total = 0
    for (view, b), (_, a) in zip(before, after):
        mismatch = _frame_mismatch(b, a)
        if mismatch is not None:
            raise ValueError(
                f"before/after renders of view {tuple(view)} used different camera frames: "
                f"{mismatch} differs. Render both sides with the same `view`, `size` and "
                f"`frame_points` -- vertices are never moved, so one static `frame_points` (the "
                f"recentred original positions) is correct for both.")
        both_casters = caster_before is not None and caster_after is not None
        ring = _ring_probe(b, caster_before, caster_after, depth_tol) if both_casters else None
        tie = _tie_probe(b, caster_before, caster_after) if both_casters else None
        codes, base = _classify(b.depth, b.tri, a.depth, a.tri,
                                 face_material_before, face_material_after, flat_materials, depth_tol,
                                 origins=b.origins, direction=b.direction,
                                 plane_before=plane_before, plane_after=plane_after,
                                 ring=ring, tie=tie, allow_depth_fallback=allow_depth_fallback,
                                 strict=strict, removed_before=removed_before, border=border,
                                 exposed_after=exposed_after)
        # The crack and fragment caps are applied BEFORE the counts are taken, because over one
        # a pixel is not a crack or debris at all -- it goes back to being whatever it was, and is
        # reported as that.
        crack = codes == PX_CRACK_CLOSED
        if crack.any() and int(crack.sum()) > crack_closed_cap * int((b.tri >= 0).sum()):
            codes = np.where(crack, base, codes)
        fragment = codes == PX_FRAGMENT_REMOVED
        if fragment.any() and int(fragment.sum()) > fragment_removed_cap * int((b.tri >= 0).sum()):
            codes = np.where(fragment, base, codes)
        flicker = codes == PX_EDGE_FLICKER
        counts = {
            "model_px": int((b.tri >= 0).sum()),
            "holes": int((codes == PX_HOLE).sum()),
            "material_changed": int((codes == PX_MATERIAL_CHANGED).sum()),
            "moved_same_flat": int((codes == PX_MOVED_SAME_FLAT).sum()),
            "moved_other": int((codes == PX_MOVED_OTHER).sum()),
            "zfight_tie": int((codes == PX_ZFIGHT_TIE).sum()),
            "crack_closed": int((codes == PX_CRACK_CLOSED).sum()),
            "edge_flicker": int(flicker.sum()),
            "fragment_removed": int((codes == PX_FRAGMENT_REMOVED).sum()),
            "edge_flicker_hole": int((flicker & (base == PX_HOLE)).sum()),
            "edge_flicker_moved": int((flicker & ((base == PX_MOVED_SAME_FLAT)
                                                  | (base == PX_MOVED_OTHER))).sum()),
            "edge_flicker_material": int((flicker & (base == PX_MATERIAL_CHANGED)).sum()),
            "border_shift": int((codes == PX_BORDER_SHIFT).sum()),
            "grown": int((codes == PX_GROWN).sum()),
            "edge_flicker_grown": int((flicker & (base == PX_GROWN)).sum()),
        }
        view_verdicts.append(ViewVerdict(view=tuple(view), **counts))
        for k, v in counts.items():
            totals[k] += v
        fail_total += counts["holes"] + counts["material_changed"] + counts["moved_other"] + counts["grown"]
        if strict:
            fail_total += counts["moved_same_flat"]
        if counts["edge_flicker"] > edge_flicker_cap * counts["model_px"]:
            fail_total += counts["edge_flicker"]

    return GuardReport(views=view_verdicts, passed=fail_total == 0, totals=totals)


def guard_feedback(candidates: np.ndarray, positions_c: np.ndarray, faces: np.ndarray,
                    face_material: np.ndarray, flat_materials: Iterable[int], depth_tol: float,
                    strict: bool, views: Sequence[Sequence[float]] = VIEWS_26,
                    size: tuple[int, int] = (900, 600), caster_factory=EmbreeCaster,
                    max_rounds: int = 8,
                    crack_closed_cap: float = float("inf")) -> tuple[np.ndarray, list[dict]]:
    """Iteratively confirm which `candidates` (bool mask over ALL of `faces`) can be removed
    without changing the outside, by the same displacement/colour-aware pixel test as
    `compare_views` (the planes both sides need are built here from `positions_c`/`faces`, which
    is correct for both renders because only face PRESENCE changes between them).

    `positions_c`/`faces` are the ORIGINAL geometry -- every face the guard should consider,
    already whatever subset the caller wants treated as renderable (e.g. non-degenerate only);
    `candidates` and the returned mask are indexed against this same `faces` array. Vertices are
    never moved, so `positions_c` also serves as `frame_points` for every render, before and
    after, keeping pixels aligned across rounds. `face_material` is the single per-face material
    array (materials don't change here, only face presence). `strict` is forwarded to the same
    pixel test `compare_views` uses: `True` for automatic removal of exposure-0 faces, `False`
    for a person-accepted change.

    THE THREE TOLERATED CLASSES, and where this really does agree with `compare_views`. The
    edge-flicker cap is ALWAYS 0.0 here -- removing a face is not a change a person accepted, so a
    silhouette pixel that flips counts as damage, exactly as it would in a `compare_views` call at
    that cap. The other two are NOT a matter of the cap: `PX_ZFIGHT_TIE` and `PX_CRACK_CLOSED` are
    never failures at any cap, because a tie is an overlap this run neither caused nor can fix and
    a closed crack is an improvement. So the ring and tie probes ARE cast here, and this function's
    verdicts now match `compare_views(..., edge_flicker_cap=0.0)` pixel for pixel. It used to cast
    neither and claim, in this docstring, that the two already agreed; they did not, and the
    removal guard counted both classes as damage.

    `crack_closed_cap` is the same per-view cap `compare_views` takes (see there); `inf`, the
    default, never caps, and `engine.fixes.pipeline` passes `FixProfile.crack_closed_cap` so the
    removal guard is never more tolerant of cracks than the final guard is.

    CONSEQUENCE, stated plainly: a removed face whose disappearance is narrower than the ring
    radius (`depth_tol`) on all 16 ring rays now reads as a closed crack rather than a hole, and
    is therefore removed instead of restored. That is the documented limit of the crack test
    (`classify_pixels`), and it now applies to removal as well as to merging.

    Round 0 renders BEFORE once, against every face in `faces`, and tentatively removes every
    candidate. Each round renders AFTER with the current kept faces; every candidate that is the
    BEFORE first-hit face at a failing pixel is put back. Stops at 0 failing pixels (or nothing
    left to restore) or after `max_rounds` rounds.

    Returns `(mask, history)`: `mask` (bool, same shape as `candidates`) is the surviving --
    confirmed removable -- subset of `candidates`. `history` is one dict per round:
    `{"round", "candidates_remaining", "failing_pixels", "restored"}`, where
    `candidates_remaining` is the still-marked-for-removal count going INTO that round (before
    that round's restores are applied).

    `caster_factory` is wrapped in a `ReusableCaster` internally, so the SAME geometry (the
    `faces` array for the BEFORE render, one `keep_faces` array per round for its AFTER render) is
    built into a caster ONCE and reused across all of `views`, instead of once per view -- results
    are bit-identical either way, only construction is skipped."""
    candidates = np.asarray(candidates, dtype=bool)
    positions_c = np.asarray(positions_c, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    face_ids = np.arange(len(faces), dtype=np.int64)

    before_caster = ReusableCaster(caster_factory)
    before = [(view, ortho_first_hit(positions_c, faces, face_ids, view, positions_c, size, before_caster))
              for view in views]
    planes = face_planes(positions_c, faces)  # geometry never changes here, only face presence

    removed = candidates.copy()
    history = []
    for rnd in range(max_rounds):
        keep = ~removed
        keep_faces = faces[keep]
        # The AFTER render is labelled with LOCAL ids into `keep_faces`, not with the original
        # ones, because the ring and tie probes report `tri` as indices into the caster's own
        # `faces` array and `classify_pixels` reads `material_after` / `plane_after` with both.
        # `b.tri` is still original-indexed, which is what the restore below needs.
        keep_local = np.arange(len(keep_faces), dtype=np.int64)
        keep_material = face_material[keep]
        keep_planes = planes[keep]

        restore = set()
        failing_pixels = 0
        after_caster = ReusableCaster(caster_factory)
        caster_b = before_caster(positions_c, faces)
        caster_a = after_caster(positions_c, keep_faces)
        for view, b in before:
            a = ortho_first_hit(positions_c, keep_faces, keep_local, view, positions_c,
                                 size, after_caster)
            codes, base = _classify(b.depth, b.tri, a.depth, a.tri,
                                     face_material, keep_material, flat_materials, depth_tol,
                                     origins=b.origins, direction=b.direction,
                                     plane_before=planes, plane_after=keep_planes,
                                     ring=_ring_probe(b, caster_b, caster_a, depth_tol),
                                     tie=_tie_probe(b, caster_b, caster_a), strict=strict)
            # A crack promotion says "BEFORE's ray alone slipped through something thinner than
            # the ring radius, and AFTER closed it". That reading is only available when AFTER
            # still HAS the surface. Here it may not: if BEFORE's first hit is a face this pass
            # is deleting, the pixel changed because of the deletion, and calling that a closed
            # crack would let the guard delete any surface narrower than `depth_tol` -- measured:
            # `floor_with_sliver`'s 1e-4 in sliver, which every one of the 16 ring rays misses.
            # Those pixels go back to their base class. Ties need no such rule: a tie already
            # requires BEFORE's own first hit to match a member of AFTER's tie set, which a
            # removed face cannot do unless the same material is still there in the same plane.
            crack = codes == PX_CRACK_CLOSED
            if crack.any():
                own = crack & (b.tri >= 0) & removed[np.where(b.tri >= 0, b.tri, 0)]
                over_cap = int(crack.sum()) > crack_closed_cap * int((b.tri >= 0).sum())
                codes = np.where(own | (crack if over_cap else False), base, codes)
            fail = _fail_mask(codes, strict)
            failing_pixels += int(fail.sum())
            offenders = b.tri[fail]
            restore.update(offenders[removed[offenders]].tolist())

        history.append({"round": rnd, "candidates_remaining": int(removed.sum()),
                         "failing_pixels": failing_pixels, "restored": len(restore)})
        if failing_pixels == 0 or not restore:
            break
        removed[list(restore)] = False

    return removed, history


def fragment_feedback(candidates: np.ndarray, positions_c: np.ndarray, faces: np.ndarray,
                       face_material: np.ndarray, flat_materials: Iterable[int], depth_tol: float,
                       already_removed: np.ndarray | None = None,
                       views: Sequence[Sequence[float]] = VIEWS_26,
                       size: tuple[int, int] = (900, 600), caster_factory=EmbreeCaster,
                       max_rounds: int = 8,
                       crack_closed_cap: float = float("inf"),
                       side_exposure: np.ndarray | None = None,
                       fragment_removed_cap: float = float("inf")) -> tuple[np.ndarray, list[dict]]:
    """FRAGMENT MODE: which `candidates` (bool over `faces`) may be deleted, when deleting them
    is MEANT to change the picture.

    Every other removal guard here asks "is the picture unchanged" and restores anything that
    changed a pixel. That is the wrong question for `engine.detectors.fragments`, whose whole
    subject is debris a person CAN see: a stray triangle left by a delete is visible, and a guard
    that refused every visible deletion would refuse all of them. So the question here is
    narrower and sharper: DID ANYTHING ELSE CHANGE?

    A pixel is permitted when its BEFORE first hit is one of the candidates currently marked for
    removal AND what AFTER shows there is something that was already outside: the sky, or a face
    met on a side `side_exposure` (`(F, 2)` bool over `faces`: FRONT, BACK exposed on the
    reference) marks as exposed -- that is the fragment disappearing, which is what was asked
    for. Where AFTER shows a side nobody could see before -- the inside of a closed shell -- the
    candidate was part of that shell's skin, and the pixel is judged like every other one:
    exactly the rule the strict removal guard uses (`_fail_mask(strict=True)`, with the ring, tie
    and crack probes cast, so the three tolerated classes mean the same thing they mean
    everywhere else). Without `side_exposure` only the sky is permitted. It used to permit every
    pixel of a candidate whatever AFTER showed, and let review C2's probe take a patch of a slab's
    top that only T-junctions joined to the rest (`classify_pixels` has the rule; this is its
    `removed_before` / `exposed_after`).

    `fragment_removed_cap` caps the permitted pixels PER VIEW exactly as the final guard caps them
    (`compare_views`): over the cap that view's permitted pixels are judged as what they are,
    and every candidate in front of them goes back -- so this guard never confirms a removal the
    final guard would then refuse.

    BEFORE IS THE WHOLE MESH, including `already_removed` -- the faces earlier passes took out,
    which are dropped from AFTER only. It has to be: this guard's verdict is checked later by the
    final guard, whose BEFORE is that same whole mesh, and two guards rendering different BEFOREs
    disagree about which face a pixel even shows. Measured on file A: three faces coincide at one
    pixel, the hidden pass removed the one the render happened to pick, a 0.1 sq in sliver was
    the only surface still holding that pixel, and a guard rendering the POST-HIDDEN mesh saw the
    pixel as the sliver's own and let it go -- one pixel of damage that then failed the final
    guard and rolled back the whole merge.

    WHICH CANDIDATE IS BLAMED. Every marked candidate the BEFORE ray meets IN FRONT OF AFTER's
    first hit (anywhere along the ray, when AFTER missed). Faces are only ever removed, so the
    surfaces in front of AFTER's first hit are exactly the ones no longer there at that pixel,
    and the candidates among them are this pass's share of the change. Not just BEFORE's first
    hit -- at a coincident pixel the face actually holding it may be second in the list -- and
    not only those within `depth_tol` of it either: at the near-horizontal views
    (`VIEWS_26` carries z components of about 0.01) a 0.01 in gap between two surfaces is an
    inch ALONG THE RAY, and a tie-set rule misses the very candidate that went.

    A failing pixel with NO candidate in front of AFTER's first hit is not this pass's doing:
    restoring every candidate would leave it exactly as it is. It was made by an earlier pass,
    under that pass's own guard -- the colour-tolerant slit pass, say, whose tolerated
    `moved_same_flat` pixels fail the strict rule used here -- and the FINAL guard still judges
    it. It is counted as `not_ours_pixels` and otherwise left alone, so another pass's verdict
    can never make this one throw its work away.

    `positions_c` / `faces` / `face_material` / `depth_tol` / `flat_materials` mean exactly what
    they mean in `guard_feedback`, and `crack_closed_cap` is forwarded the same way. Returns
    `(mask, history)` with `mask` the confirmed-removable subset of `candidates`, and one history
    dict per round: `{"round", "candidates_remaining", "failing_pixels", "not_ours_pixels",
    "restored"}` -- `failing_pixels` counting only the ones a candidate was involved in."""
    candidates = np.asarray(candidates, dtype=bool)
    positions_c = np.asarray(positions_c, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    gone = (np.zeros(len(faces), dtype=bool) if already_removed is None
            else np.asarray(already_removed, dtype=bool))
    exposure = (None if side_exposure is None
                else np.asarray(side_exposure, dtype=bool).reshape(len(faces), 2))
    face_ids = np.arange(len(faces), dtype=np.int64)

    before_caster = ReusableCaster(caster_factory)
    before = [(view, ortho_first_hit(positions_c, faces, face_ids, view, positions_c, size,
                                      before_caster))
              for view in views]
    planes = face_planes(positions_c, faces)   # geometry never changes here, only face presence

    removed = candidates.copy()
    history: list[dict] = []
    for rnd in range(max_rounds):
        keep = ~(removed | gone)
        keep_faces = faces[keep]
        keep_local = np.arange(len(keep_faces), dtype=np.int64)
        keep_material = face_material[keep]
        keep_planes = planes[keep]

        restore: set[int] = set()
        failing_pixels = 0
        not_ours = 0
        after_caster = ReusableCaster(caster_factory)
        caster_b = before_caster(positions_c, faces)
        caster_a = after_caster(positions_c, keep_faces)
        for view, b in before:
            a = ortho_first_hit(positions_c, keep_faces, keep_local, view, positions_c, size,
                                 after_caster)
            # ...and THIS is the whole difference: a pixel showing a fragment on its way out, where
            # AFTER shows only what was already outside, is not damage, it is the point. It is
            # `PX_FRAGMENT_REMOVED`, which never fails; every other pixel of a candidate fails as
            # what it is.
            codes, base = _classify(b.depth, b.tri, a.depth, a.tri,
                                     face_material, keep_material, flat_materials, depth_tol,
                                     origins=b.origins, direction=b.direction,
                                     plane_before=planes, plane_after=keep_planes,
                                     ring=_ring_probe(b, caster_b, caster_a, depth_tol),
                                     tie=_tie_probe(b, caster_b, caster_a), strict=True,
                                     removed_before=removed,
                                     exposed_after=None if exposure is None else exposure[keep])
            # Same rule as `guard_feedback`: a crack promotion is only available when AFTER still
            # HAS the surface, which it does not where this run deleted BEFORE's first hit.
            crack = codes == PX_CRACK_CLOSED
            if crack.any():
                dropped = removed | gone
                own_crack = crack & (b.tri >= 0) & dropped[np.where(b.tri >= 0, b.tri, 0)]
                over_cap = int(crack.sum()) > crack_closed_cap * int((b.tri >= 0).sum())
                codes = np.where(own_crack | (crack if over_cap else False), base, codes)
            # the same per-view cap the final guard applies, so nothing confirmed here fails there
            fragment = codes == PX_FRAGMENT_REMOVED
            if int(fragment.sum()) > fragment_removed_cap * int((b.tri >= 0).sum()):
                codes = np.where(fragment, base, codes)

            fail = _fail_mask(codes, strict=True)
            if not fail.any():
                continue

            rows, cols = np.nonzero(fail)
            origins = (b.xs[cols][:, None] * b.right + b.ys[rows][:, None] * b.up + b.standoff)
            direction = np.asarray(b.direction, dtype=np.float64)
            ray, tri, t = caster_b.all_hits(origins, np.tile(direction, (len(origins), 1)))
            # AFTER's first hit is the first SURVIVING surface on this ray; a candidate in front of
            # it (or anywhere, when AFTER missed) is one this pass took away from this pixel.
            t_after = np.where(a.tri[rows, cols] >= 0, a.depth[rows, cols], np.inf)
            involved = removed[tri] & (t <= t_after[ray])
            restore.update(tri[involved].tolist())
            ours = np.zeros(len(rows), dtype=bool)
            ours[ray[involved]] = True
            failing_pixels += int(ours.sum())
            not_ours += int((~ours).sum())

        history.append({"round": rnd, "candidates_remaining": int(removed.sum()),
                         "failing_pixels": failing_pixels, "not_ours_pixels": not_ours,
                         "restored": len(restore)})
        if failing_pixels == 0 or not restore:
            break
        removed[list(restore)] = False

    return removed, history


def solidify_feedback(positions_c: np.ndarray, faces_before: np.ndarray, faces_after: np.ndarray,
                       is_new: np.ndarray, front_exposure_before: np.ndarray,
                       cover_max_exposure: float = 0.10,
                       views: Sequence[Sequence[float]] = VIEWS_26,
                       size: tuple[int, int] = (900, 600), caster_factory=EmbreeCaster,
                       max_rounds: int = 8) -> tuple[np.ndarray, list[dict]]:
    """The CAP GUARD: which of the faces `engine.fixes.solidify` invented may stay.

    A different question from every other guard here, and it needs its own rule. The other guards
    ask "is the picture unchanged"; this one is asked about a step whose whole purpose is to
    change the picture -- a slab with no bottom gets one, and from underneath that IS a change.
    What must not happen is a new face covering something a person can still see.

    Only faces are ADDED, so an AFTER first hit is either the same original face at the same
    depth or a NEW face in front of it: a changed pixel is exactly one whose AFTER first hit is
    new. Such a pixel is ALLOWED when what it covers is one of three things, and nothing else:

    1. background -- BEFORE's ray missed everything;
    2. a face seen on its BACK side (`n . view_dir > 0`) -- a one-sided renderer was dropping
       that pixel anyway, which is the hole this whole step exists to close;
    3. a face met on its FRONT side whose FRONT exposure ON THE ORIGINAL MESH is below
       `cover_max_exposure` -- a surface that was only ever seen through an opening, which is
       the interior rib wall this step exists to hide behind the skirt that closes its cell.

    RULE 3 READS THE ORIGINAL MESH, NOT THE SOLIDIFIED ONE, and that is the whole point of the
    rule. It used to ask whether the covered face's exposure was 0 in the SOLIDIFIED mesh --
    but any covering face drives that exposure to 0, so the rule authorised itself: a bottom
    invented 9.8 in down under a slab whose real underside is 4 in down boxed that underside in,
    its solidified exposure went to 0, the cap guard allowed the cover, and the hidden pass then
    deleted the real underside with every guard still passing (`slab_with_partial_underside`).
    Measured on the original mesh the underside is plainly visible from below, so the covering
    face is refused instead.

    RULE 3 IS ALSO PER SIDE, a deliberate departure from "a face whose exposure is 0". Exposure
    is double-sided, so a face that is part of the outer shell always has some -- and the face
    you see through an opening is very often exactly that: the INSIDE of the far wall, or the
    underside of a top sheet whose other side sees sky. Measured on `open_box_with_cells`, whose
    lid, walls and floor are all wound inward: with a whole-face test the only skirt that closes
    the box is refused, because it covers the inside of the far wall, and the step can never do
    its job at all. The side a ray met a face on is decided by `n . view_dir`, the same quantity
    rule 2 uses, so the two rules read one number.

    `cover_max_exposure` is a THRESHOLD, not `== 0`, because a face seen only through a small
    opening never measures exactly 0 by ray sampling: the far wall of `compartment_with_deep_wall`
    is seen through a 10 x 10 in hole 45 in away and measures a fraction of a percent. The
    default 0.10 is `engine.fixes.pipeline.FixProfile.cover_max_exposure`.

    Any other change MARKS the new face at that pixel. Marked faces are dropped and the whole
    thing runs again, because removing one new face can expose what another was covering, until
    a round marks nothing or `max_rounds` rounds have run.

    THE LAST STATE IS ALWAYS VERIFIED. A round's `failing_pixels` is measured BEFORE that round's
    own removals, so a loop cut off at `max_rounds` would leave a history describing a mesh that
    is not the one handed back. When the loop ends that way one extra render-only round is
    appended (`"removed": 0`), so `history[-1]["failing_pixels"] == 0` is always a statement about
    the returned `keep`. `engine.fixes.solidify` publishes exactly that as `cap_guard_passed` and
    `engine.fixes.pipeline` makes it an invariant of the whole run.

    `faces_before` / `faces_after` are welded triangles into the SAME `positions_c` (solidify
    only appends positions, so an original face still indexes the same rows) and `positions_c`
    frames both renders, so the two line up pixel for pixel. `is_new` is a bool mask over
    `faces_after`. `front_exposure_before` is the FRONT half of
    `engine.vis.exposure.compute_side_exposure` per face of `faces_BEFORE`, measured on the
    ORIGINAL mesh -- the geometry as it arrived, before a single face was invented.

    Returns `(keep, history)`: `keep` is a bool mask over `faces_after` (always True for a face
    that is not new), and `history` is one dict per round,
    `{"round", "new_remaining", "failing_pixels", "removed"}`."""
    positions_c = np.asarray(positions_c, dtype=np.float64)
    faces_before = np.asarray(faces_before, dtype=np.int64)
    faces_after = np.asarray(faces_after, dtype=np.int64)
    is_new = np.asarray(is_new, dtype=bool)
    # measured on the ORIGINAL mesh, so it is already indexed like `faces_before`
    front_exposure = np.asarray(front_exposure_before, dtype=np.float64)[:len(faces_before)]

    tri = positions_c[faces_before]
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    normal = normal / np.maximum(np.linalg.norm(normal, axis=1), 1e-300)[:, None]

    before_caster = ReusableCaster(caster_factory)
    before = [(view, ortho_first_hit(positions_c, faces_before,
                                      np.arange(len(faces_before), dtype=np.int64), view,
                                      positions_c, size, before_caster))
              for view in views]

    keep = np.ones(len(faces_after), dtype=bool)

    def measure() -> tuple[int, set[int]]:
        """`(failing pixels, the new faces at them)` for the CURRENT `keep`."""
        ids = np.nonzero(keep)[0]
        after_caster = ReusableCaster(caster_factory)
        marked: set[int] = set()
        failing = 0
        for view, b in before:
            a = ortho_first_hit(positions_c, faces_after[keep], ids, view, positions_c, size,
                                 after_caster)
            changed = (a.tri >= 0) & is_new[np.where(a.tri >= 0, a.tri, 0)]
            if not changed.any():
                continue
            hit_before = b.tri[changed]
            direction = np.asarray(b.direction, dtype=np.float64)
            covered = hit_before >= 0
            safe_index = np.where(covered, hit_before, 0)
            back_side = covered & (normal[safe_index] @ direction > 1e-9)
            # the ray met the FRONT side wherever it is not a back-side hit, so this is the
            # exposure of the side it met -- ON THE ORIGINAL MESH, which is the one thing the
            # face being covered cannot have changed.
            only_through_an_opening = covered & (front_exposure[safe_index] < cover_max_exposure)
            bad = covered & ~back_side & ~only_through_an_opening
            failing += int(bad.sum())
            marked.update(a.tri[changed][bad].tolist())
        return failing, marked

    history: list[dict] = []
    for rnd in range(max_rounds):
        failing, marked = measure()
        history.append({"round": rnd, "new_remaining": int((keep & is_new).sum()),
                         "failing_pixels": failing, "removed": len(marked)})
        if not marked:
            return keep, history
        keep[sorted(marked)] = False

    # Cut off at the cap with its last round's removals never checked. A round's `failing_pixels`
    # is measured BEFORE its own removals, so without this the history would describe a mesh that
    # is not the one being handed back, and `history[-1]["failing_pixels"] == 0` -- which the
    # caller publishes as `cap_guard_passed` -- would be a claim about a superseded state.
    failing, _marked = measure()
    history.append({"round": max_rounds, "new_remaining": int((keep & is_new).sum()),
                     "failing_pixels": failing, "removed": 0})
    return keep, history
