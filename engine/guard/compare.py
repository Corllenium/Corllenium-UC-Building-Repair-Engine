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

#: `(view, HitBuffers)` for one `ortho_first_hit` render.
RenderedView = tuple[Sequence[float], HitBuffers]

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


def classify_pixels(before_depth: np.ndarray, before_tri: np.ndarray,
                     after_depth: np.ndarray, after_tri: np.ndarray,
                     material_before: np.ndarray, material_after: np.ndarray,
                     flat_materials: Iterable[int], depth_tol: float, *,
                     origins: np.ndarray | None = None, direction: np.ndarray | None = None,
                     plane_before: np.ndarray | None = None,
                     plane_after: np.ndarray | None = None,
                     ring=None, tie=None, allow_depth_fallback: bool = False,
                     strict: bool = False) -> np.ndarray:
    """Per-pixel verdict code, same shape as the inputs (uint8, one of the `PX_*` constants), in
    this priority order: `PX_HOLE` (hit before, miss after); `PX_MATERIAL_CHANGED` (both hit,
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
    front of another) as at the model's outer edge, where the old 3x3-neighbourhood-plus-5x5-
    coverage rule only worked because it looked for background.

    Passing no `ring` means no pixel is ever flicker, which is correct exactly where flicker and
    the real class are treated alike (`guard_feedback`, cap 0.0). `plane_before`/`plane_after` are
    required for the ring test as well, so a `ring` given without them is ignored.

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
                      strict=strict)[0]


def _failing_base(codes: np.ndarray, strict: bool) -> np.ndarray:
    """Which BASE classes fail under the current strictness, and so may be promoted to one of the
    tolerated classes (`PX_ZFIGHT_TIE`, `PX_CRACK_CLOSED`, `PX_EDGE_FLICKER`). Deliberately the
    same rule `_fail_mask` applies to the FINAL codes, minus the promoted classes themselves."""
    fail = (codes == PX_HOLE) | (codes == PX_MATERIAL_CHANGED) | (codes == PX_MOVED_OTHER)
    if strict:
        fail = fail | (codes == PX_MOVED_SAME_FLAT)
    return fail


def _classify(before_depth: np.ndarray, before_tri: np.ndarray,
               after_depth: np.ndarray, after_tri: np.ndarray,
               material_before: np.ndarray, material_after: np.ndarray,
               flat_materials: Iterable[int], depth_tol: float, *,
               origins=None, direction=None, plane_before=None, plane_after=None,
               ring=None, tie=None, allow_depth_fallback: bool = False,
               strict: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """`classify_pixels`, plus the BASE codes -- what every pixel was classed before the ring test
    rescued any of it -- so `compare_views` can report which class each flicker pixel came from
    (`edge_flicker_hole` / `_moved` / `_material`) without measuring displacement twice."""
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

    base = codes.copy()
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
    #: `edge_flicker` split by the class each of those pixels was rescued FROM; the three always
    #: sum to `edge_flicker`, so a report says whether a tolerated pixel was a would-be hole, a
    #: would-be move (`moved_same_flat` or `moved_other`), or a would-be material swap.
    edge_flicker_hole: int
    edge_flicker_moved: int
    edge_flicker_material: int


@dataclass
class GuardReport:
    views: list[ViewVerdict]
    passed: bool
    totals: dict


def _zero_totals() -> dict:
    return {"model_px": 0, "holes": 0, "material_changed": 0, "moved_same_flat": 0, "moved_other": 0,
            "zfight_tie": 0, "crack_closed": 0, "edge_flicker": 0, "edge_flicker_hole": 0, "edge_flicker_moved": 0,
            "edge_flicker_material": 0}


def _fail_mask(codes: np.ndarray, strict: bool, flicker_fails: bool = True) -> np.ndarray:
    """Which pixels count as damage. `flicker_fails` is the per-view outcome of the
    `edge_flicker_cap` test; at the default cap of 0.0 a flicker pixel fails exactly like a hole."""
    fail = (codes == PX_HOLE) | (codes == PX_MATERIAL_CHANGED) | (codes == PX_MOVED_OTHER)
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
                   geometry_before: tuple[np.ndarray, np.ndarray] | None = None,
                   geometry_after: tuple[np.ndarray, np.ndarray] | None = None,
                   caster_factory=EmbreeCaster,
                   allow_depth_fallback: bool = False) -> GuardReport:
    """Compare a BEFORE/AFTER pair of `ortho_first_hit` renders, one `(view, HitBuffers)` pair per
    view, paired by position (`before[i]` and `after[i]` must be the same view, and both sequences
    the same length). Each pair must share the whole CAMERA FRAME -- direction, image size and the
    origins grid -- or `ValueError` names the view and the field that differs; comparing renders
    framed on different bounding boxes would silently measure displacement from the wrong points.

    `plane_before` / `plane_after` are `face_planes` of the two geometries, indexed like
    `face_material_before` / `face_material_after`; they are what the surface-displacement moved
    test needs (see `classify_pixels`), and leaving them out raises unless the caller asks for the
    old depth-along-the-ray metric with `allow_depth_fallback=True`.

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

    `passed` is `holes + material_changed + moved_other == 0`, plus `moved_same_flat` when
    `strict`, plus the flicker pixels of any view over the cap. Every count -- `moved_same_flat`,
    `edge_flicker` and its `edge_flicker_hole` / `_moved` / `_material` breakdown included -- is
    always reported in `totals` and every `ViewVerdict`, never silently dropped."""
    if len(before) != len(after):
        raise ValueError(f"before/after must have the same number of views, got {len(before)} vs {len(after)}")
    if edge_flicker_cap > 0.0 and (geometry_before is None or geometry_after is None):
        raise ValueError(
            f"compare_views was given edge_flicker_cap={edge_flicker_cap} but no geometry_before/"
            "geometry_after: without them there is no ring to cast around a failing pixel, so "
            "nothing is ever classed edge_flicker and the cap would tolerate nothing while looking "
            "as though it tolerated something. Pass geometry_before and geometry_after (positions, "
            "faces) so failing pixels get the ring test, or use edge_flicker_cap=0.0.")

    caster_before = caster_factory(*geometry_before) if geometry_before is not None else None
    caster_after = caster_factory(*geometry_after) if geometry_after is not None else None

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
                                 strict=strict)
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
            "edge_flicker_hole": int((flicker & (base == PX_HOLE)).sum()),
            "edge_flicker_moved": int((flicker & ((base == PX_MOVED_SAME_FLAT)
                                                  | (base == PX_MOVED_OTHER))).sum()),
            "edge_flicker_material": int((flicker & (base == PX_MATERIAL_CHANGED)).sum()),
        }
        view_verdicts.append(ViewVerdict(view=tuple(view), **counts))
        for k, v in counts.items():
            totals[k] += v
        fail_total += counts["holes"] + counts["material_changed"] + counts["moved_other"]
        if strict:
            fail_total += counts["moved_same_flat"]
        if counts["edge_flicker"] > edge_flicker_cap * counts["model_px"]:
            fail_total += counts["edge_flicker"]

    return GuardReport(views=view_verdicts, passed=fail_total == 0, totals=totals)


def guard_feedback(candidates: np.ndarray, positions_c: np.ndarray, faces: np.ndarray,
                    face_material: np.ndarray, flat_materials: Iterable[int], depth_tol: float,
                    strict: bool, views: Sequence[Sequence[float]] = VIEWS_26,
                    size: tuple[int, int] = (900, 600), caster_factory=EmbreeCaster,
                    max_rounds: int = 8) -> tuple[np.ndarray, list[dict]]:
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
    for a person-accepted change. The edge-flicker cap is ALWAYS 0.0 here -- removing a face is
    not a change a person accepted, so a silhouette pixel that flips counts as damage. No ring is
    cast either (nothing is ever classed `PX_EDGE_FLICKER`), which is the same outcome at cap 0.0
    and saves 16 rays per failing pixel per round.

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
        keep_ids = face_ids[keep]

        restore = set()
        failing_pixels = 0
        after_caster = ReusableCaster(caster_factory)
        for view, b in before:
            a = ortho_first_hit(positions_c, keep_faces, keep_ids, view, positions_c,
                                 size, after_caster)
            codes = classify_pixels(b.depth, b.tri, a.depth, a.tri,
                                     face_material, face_material, flat_materials, depth_tol,
                                     origins=b.origins, direction=b.direction,
                                     plane_before=planes, plane_after=planes)
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
