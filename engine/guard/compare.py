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


def classify_pixels(before_depth: np.ndarray, before_tri: np.ndarray,
                     after_depth: np.ndarray, after_tri: np.ndarray,
                     material_before: np.ndarray, material_after: np.ndarray,
                     flat_materials: Iterable[int], depth_tol: float, *,
                     origins: np.ndarray | None = None, direction: np.ndarray | None = None,
                     plane_before: np.ndarray | None = None,
                     plane_after: np.ndarray | None = None) -> np.ndarray:
    """Per-pixel verdict code, same shape as the inputs (uint8, one of the `PX_*` constants), in
    this priority order: `PX_HOLE` (hit before, miss after) or `PX_EDGE_FLICKER` (a would-be hole
    whose 3x3 BEFORE neighbourhood contains a miss, i.e. one on the silhouette, where a boundary
    moving 1e-3 in against a 2.1 in pixel flips one sample); `PX_MATERIAL_CHANGED` (both hit,
    `material_before[before_tri] != material_after[after_tri]`); `PX_MOVED_SAME_FLAT` /
    `PX_MOVED_OTHER` (both hit, same material, the visible surface moved further than `depth_tol`
    -- `_SAME_FLAT` when that material index is in `flat_materials`, `_OTHER` otherwise); `PX_OK`
    otherwise (includes both-miss background pixels and pixels that matched within `depth_tol`).

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
    codes[would_be_hole & _neighbour_miss(hit_before)] = PX_EDGE_FLICKER

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
                   edge_flicker_cap: float = 0.0) -> GuardReport:
    """Compare a BEFORE/AFTER pair of `ortho_first_hit` renders, one `(view, HitBuffers)` pair per
    view, paired by position (`before[i]` and `after[i]` must be the same view, and both sequences
    the same length).

    `plane_before` / `plane_after` are `face_planes` of the two geometries, indexed like
    `face_material_before` / `face_material_after`; pass them to get the surface-displacement
    moved test (see `classify_pixels`). Omitted, every pixel falls back to depth along the ray.

    `strict=True` (use for automatic removal of exposure-0 faces -- a depth change there means
    sampling missed real visibility) counts `moved_same_flat` pixels as failures too;
    `strict=False` (use for a change a person already accepted) reports them but tolerates them.

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

    view_verdicts = []
    totals = _zero_totals()
    fail_total = 0
    for (view, b), (_, a) in zip(before, after):
        if not np.allclose(b.direction, a.direction):
            raise ValueError(f"before/after renders of view {tuple(view)} used different view "
                             f"directions: {b.direction.tolist()} vs {a.direction.tolist()}")
        codes = classify_pixels(b.depth, b.tri, a.depth, a.tri,
                                 face_material_before, face_material_after, flat_materials, depth_tol,
                                 origins=b.origins, direction=b.direction,
                                 plane_before=plane_before, plane_after=plane_after)
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
