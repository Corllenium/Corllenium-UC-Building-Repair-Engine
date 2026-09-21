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
from engine.rays.caster import EmbreeCaster

# Per-pixel verdict codes, in priority order -- see `classify_pixels`.
PX_OK = 0
PX_HOLE = 1
PX_MATERIAL_CHANGED = 2
PX_MOVED_SAME_FLAT = 3
PX_MOVED_OTHER = 4
PX_EDGE_FLICKER = 5

#: `(view, HitBuffers)` for one `ortho_first_hit` render.
RenderedView = tuple[Sequence[float], HitBuffers]

#: Side of the sub-ray lattice a would-be hole is supersampled with (25 rays per pixel).
_FLICKER_GRID = 5
#: A would-be hole stays `PX_EDGE_FLICKER` only while its sub-pixel coverage changed by at most
#: this much. A boundary that moved a thousandth of an inch cannot shift more than a sub-ray or
#: two of a 2 in pixel; a removed face takes every sub-ray with it.
_FLICKER_COVERAGE_TOL = 2 / 25


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


def _neighbour_miss(hit_before: np.ndarray) -> np.ndarray:
    """True where a pixel's 3x3 neighbourhood in BEFORE contains a miss, i.e. the pixel sits on
    the model's silhouette. Separable dilation of the miss mask over the last two axes (a 1-D
    buffer dilates over its one axis).

    A neighbour OUTSIDE the image does not count as a miss: a hole is only downgraded to flicker
    on evidence of real background, and `ortho_first_hit` frames the model with a margin anyway,
    so the silhouette never reaches the image border."""
    mask = ~np.asarray(hit_before, dtype=bool)
    for axis in range(max(0, mask.ndim - 2), mask.ndim):
        n = mask.shape[axis]
        pad = [(0, 0)] * mask.ndim
        pad[axis] = (1, 1)
        padded = np.pad(mask, pad, constant_values=False)
        head = (slice(None),) * axis
        mask = (padded[head + (slice(0, n),)] | padded[head + (slice(1, n + 1),)]
                | padded[head + (slice(2, n + 2),)])
    return mask


def _coverage_probe(buffers: HitBuffers, caster_before, caster_after, grid: int = _FLICKER_GRID):
    """A `mask -> (coverage_before, coverage_after)` callable for `classify_pixels`: the fraction
    of a `grid x grid` lattice of sub-rays through each masked pixel that hits BEFORE, and that
    hits AFTER, ordered like `np.nonzero(mask)`.

    Both sides are cast from the SAME camera frame (`buffers`, whose `direction` they share and
    whose pixel footprint they subdivide), which is what makes the two fractions comparable --
    `compare_views` has already rejected a pair of renders whose frames differ. `mask` must be
    2-D, like an `ortho_first_hit` buffer."""

    def probe(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        rows, cols = np.nonzero(mask)
        origins = buffers.subpixel_origins(rows, cols, grid)
        directions = np.tile(np.asarray(buffers.direction, dtype=np.float64), (len(origins), 1))
        shape = (len(rows), grid * grid)
        return (np.asarray(caster_before.any_hit(origins, directions)).reshape(shape).mean(axis=1),
                np.asarray(caster_after.any_hit(origins, directions)).reshape(shape).mean(axis=1))

    return probe


def classify_pixels(before_depth: np.ndarray, before_tri: np.ndarray,
                     after_depth: np.ndarray, after_tri: np.ndarray,
                     material_before: np.ndarray, material_after: np.ndarray,
                     flat_materials: Iterable[int], depth_tol: float, *,
                     origins: np.ndarray | None = None, direction: np.ndarray | None = None,
                     plane_before: np.ndarray | None = None,
                     plane_after: np.ndarray | None = None,
                     coverage=None) -> np.ndarray:
    """Per-pixel verdict code, same shape as the inputs (uint8, one of the `PX_*` constants), in
    this priority order: `PX_HOLE` (hit before, miss after) or `PX_EDGE_FLICKER` (a would-be hole
    that passes BOTH silhouette tests below); `PX_MATERIAL_CHANGED` (both hit,
    `material_before[before_tri] != material_after[after_tri]`); `PX_MOVED_SAME_FLAT` /
    `PX_MOVED_OTHER` (both hit, same material, the visible surface moved further than `depth_tol`
    -- `_SAME_FLAT` when that material index is in `flat_materials`, `_OTHER` otherwise); `PX_OK`
    otherwise (includes both-miss background pixels and pixels that matched within `depth_tol`).

    A would-be hole is `PX_EDGE_FLICKER` only if (1) its 3x3 BEFORE neighbourhood contains a miss,
    AND (2) its sub-pixel COVERAGE barely changed. On its own, (1) cannot tell the outer silhouette
    from a gap inside the model, so a genuine hole beside a pre-existing opening would be tolerated
    at a non-zero `edge_flicker_cap`. `coverage` adds (2): a callable taking the boolean mask of
    candidate pixels and returning `(coverage_before, coverage_after)` -- the fraction of a 5x5
    lattice of sub-rays through each candidate that hits in each geometry, ordered like
    `np.nonzero(mask)` (build one with `_coverage_probe`; `compare_views` does). A candidate stays
    flicker while `abs(after - before) <= 2/25`, and becomes `PX_HOLE` otherwise: a boundary that
    moved a thousandth of an inch cannot take more than a sub-ray or two of a 2 in pixel with it,
    a removed face takes all 25. Passing no `coverage` leaves test (1) deciding alone, which is
    correct only where flicker and hole are treated alike (`guard_feedback`, cap 0.0).

    "Moved" is SURFACE DISPLACEMENT, not depth along the ray: `_displacement` above. Depth along
    the ray divides the real offset by the sine of the grazing angle, so a 0.005 in plane offset
    seen 0.5 degrees off the surface reads as 0.5 in and a correct re-triangulation is reported as
    moved (measured: 676 px on file A). The displacement metric needs the hit points and both
    planes: pass `origins` (`(..., 3)`, from `HitBuffers.origins`), `direction` (the unit view
    direction, shared by before and after), and `plane_before` / `plane_after` (`face_planes` of
    the two geometries, indexed like `material_before` / `material_after`). Omit them and every
    pixel falls back to `|t_before - t_after|`, as does any pixel whose before- or after-face has
    no plane (zero area)."""
    before_tri = np.asarray(before_tri)
    after_tri = np.asarray(after_tri)
    before_depth = np.asarray(before_depth, dtype=np.float64)
    after_depth = np.asarray(after_depth, dtype=np.float64)
    material_before = np.asarray(material_before)
    material_after = np.asarray(material_after)

    hit_before = before_tri >= 0
    hit_after = after_tri >= 0
    codes = np.full(before_tri.shape, PX_OK, dtype=np.uint8)
    would_be_hole = hit_before & ~hit_after
    codes[would_be_hole] = PX_HOLE
    flicker = would_be_hole & _neighbour_miss(hit_before)
    if coverage is not None and flicker.any():
        before_fraction, after_fraction = coverage(flicker)
        steady = (np.abs(np.asarray(after_fraction, dtype=np.float64)
                         - np.asarray(before_fraction, dtype=np.float64)) <= _FLICKER_COVERAGE_TOL)
        candidates = np.nonzero(flicker)
        flicker = np.zeros_like(flicker)
        flicker[tuple(axis[steady] for axis in candidates)] = True
    codes[flicker] = PX_EDGE_FLICKER

    both = hit_before & hit_after
    mat_before = np.full(before_tri.shape, -1, dtype=np.int64)
    mat_after = np.full(after_tri.shape, -1, dtype=np.int64)
    mat_before[both] = material_before[before_tri[both]]
    mat_after[both] = material_after[after_tri[both]]
    material_changed = both & (mat_before != mat_after)
    codes[material_changed] = PX_MATERIAL_CHANGED

    same_material = both & ~material_changed
    moved = same_material & (_displacement(before_depth, before_tri, after_depth, after_tri, both,
                                            origins, direction, plane_before, plane_after) > depth_tol)
    flat_ids = np.array(sorted(flat_materials), dtype=np.int64)
    is_flat = np.isin(mat_before, flat_ids)
    codes[moved & is_flat] = PX_MOVED_SAME_FLAT
    codes[moved & ~is_flat] = PX_MOVED_OTHER
    return codes


@dataclass
class ViewVerdict:
    view: tuple[float, float, float]
    model_px: int
    holes: int
    moved_same_flat: int
    moved_other: int
    material_changed: int
    edge_flicker: int


@dataclass
class GuardReport:
    views: list[ViewVerdict]
    passed: bool
    totals: dict


def _zero_totals() -> dict:
    return {"model_px": 0, "holes": 0, "material_changed": 0, "moved_same_flat": 0, "moved_other": 0,
            "edge_flicker": 0}


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
                   caster_factory=EmbreeCaster) -> GuardReport:
    """Compare a BEFORE/AFTER pair of `ortho_first_hit` renders, one `(view, HitBuffers)` pair per
    view, paired by position (`before[i]` and `after[i]` must be the same view, and both sequences
    the same length). Each pair must share the whole CAMERA FRAME -- direction, image size and the
    origins grid -- or `ValueError` names the view and the field that differs; comparing renders
    framed on different bounding boxes would silently measure displacement from the wrong points.

    `plane_before` / `plane_after` are `face_planes` of the two geometries, indexed like
    `face_material_before` / `face_material_after`; pass them to get the surface-displacement
    moved test (see `classify_pixels`). Omitted, every pixel falls back to depth along the ray.

    `strict=True` (use for automatic removal of exposure-0 faces -- a depth change there means
    sampling missed real visibility) counts `moved_same_flat` pixels as failures too;
    `strict=False` (use for a change a person already accepted) reports them but tolerates them.

    `geometry_before` / `geometry_after` are `(positions, faces)` -- the two geometries the renders
    were cast against, `faces` indexed like the corresponding `face_material`. Given both, every
    would-be hole on the silhouette is additionally checked for a sub-pixel COVERAGE change (see
    `classify_pixels`), which is the only thing that separates the outer silhouette from a gap
    inside the model; a few dozen pixels per view are supersampled with 25 rays each, so the cost
    is two casters and a handful of rays, not a third render. Omit them and the 3x3 neighbourhood
    test decides alone -- safe only at `edge_flicker_cap = 0.0`, where flicker fails like a hole.

    `edge_flicker_cap` is judged PER VIEW: that view's `edge_flicker` pixels are tolerated only
    while `edge_flicker <= edge_flicker_cap * model_px`, otherwise all of them count as failures.
    At the default 0.0 every flicker pixel fails exactly like a hole, so hidden-face removal keeps
    its zero-tolerance behaviour; an INTERIOR hole is never a flicker pixel and always fails.

    `passed` is `holes + material_changed + moved_other == 0`, plus `moved_same_flat` when
    `strict`, plus the flicker pixels of any view over the cap. Every count -- `moved_same_flat`
    and `edge_flicker` included -- is always reported in `totals` and every `ViewVerdict`, never
    silently dropped."""
    if len(before) != len(after):
        raise ValueError(f"before/after must have the same number of views, got {len(before)} vs {len(after)}")

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
        coverage = (_coverage_probe(b, caster_before, caster_after)
                    if caster_before is not None and caster_after is not None else None)
        codes = classify_pixels(b.depth, b.tri, a.depth, a.tri,
                                 face_material_before, face_material_after, flat_materials, depth_tol,
                                 origins=b.origins, direction=b.direction,
                                 plane_before=plane_before, plane_after=plane_after,
                                 coverage=coverage)
        counts = {
            "model_px": int((b.tri >= 0).sum()),
            "holes": int((codes == PX_HOLE).sum()),
            "material_changed": int((codes == PX_MATERIAL_CHANGED).sum()),
            "moved_same_flat": int((codes == PX_MOVED_SAME_FLAT).sum()),
            "moved_other": int((codes == PX_MOVED_OTHER).sum()),
            "edge_flicker": int((codes == PX_EDGE_FLICKER).sum()),
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
    not a change a person accepted, so a silhouette pixel that flips counts as damage.

    Round 0 renders BEFORE once, against every face in `faces`, and tentatively removes every
    candidate. Each round renders AFTER with the current kept faces; every candidate that is the
    BEFORE first-hit face at a failing pixel is put back. Stops at 0 failing pixels (or nothing
    left to restore) or after `max_rounds` rounds.

    Returns `(mask, history)`: `mask` (bool, same shape as `candidates`) is the surviving --
    confirmed removable -- subset of `candidates`. `history` is one dict per round:
    `{"round", "candidates_remaining", "failing_pixels", "restored"}`, where
    `candidates_remaining` is the still-marked-for-removal count going INTO that round (before
    that round's restores are applied)."""
    candidates = np.asarray(candidates, dtype=bool)
    positions_c = np.asarray(positions_c, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    face_ids = np.arange(len(faces), dtype=np.int64)

    before = [(view, ortho_first_hit(positions_c, faces, face_ids, view, positions_c, size, caster_factory))
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
        for view, b in before:
            a = ortho_first_hit(positions_c, keep_faces, keep_ids, view, positions_c,
                                 size, caster_factory)
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
