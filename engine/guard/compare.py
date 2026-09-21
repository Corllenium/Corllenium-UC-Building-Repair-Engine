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

from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.rays.caster import EmbreeCaster

# Per-pixel verdict codes, in priority order -- see `classify_pixels`.
PX_OK = 0
PX_HOLE = 1
PX_MATERIAL_CHANGED = 2
PX_MOVED_SAME_FLAT = 3
PX_MOVED_OTHER = 4

#: `(view, depth, tri)` for one `ortho_first_hit` render.
RenderedView = tuple[Sequence[float], np.ndarray, np.ndarray]


def classify_pixels(before_depth: np.ndarray, before_tri: np.ndarray,
                     after_depth: np.ndarray, after_tri: np.ndarray,
                     material_before: np.ndarray, material_after: np.ndarray,
                     flat_materials: Iterable[int], depth_tol: float) -> np.ndarray:
    """Per-pixel verdict code, same shape as the inputs (uint8, one of the `PX_*` constants), in
    this priority order: `PX_HOLE` (hit before, miss after); `PX_MATERIAL_CHANGED` (both hit,
    `material_before[before_tri] != material_after[after_tri]`); `PX_MOVED_SAME_FLAT` /
    `PX_MOVED_OTHER` (both hit, same material, `|after_depth - before_depth| > depth_tol` --
    `_SAME_FLAT` when that material index is in `flat_materials`, `_OTHER` otherwise); `PX_OK`
    otherwise (includes both-miss background pixels and pixels that matched within `depth_tol`)."""
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
    mat_before = np.full(before_tri.shape, -1, dtype=np.int64)
    mat_after = np.full(after_tri.shape, -1, dtype=np.int64)
    mat_before[both] = material_before[before_tri[both]]
    mat_after[both] = material_after[after_tri[both]]
    material_changed = both & (mat_before != mat_after)
    codes[material_changed] = PX_MATERIAL_CHANGED

    same_material = both & ~material_changed
    with np.errstate(invalid="ignore"):
        dt = np.abs(after_depth - before_depth)
    moved = same_material & (dt > depth_tol)
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


@dataclass
class GuardReport:
    views: list[ViewVerdict]
    passed: bool
    totals: dict


def _zero_totals() -> dict:
    return {"model_px": 0, "holes": 0, "material_changed": 0, "moved_same_flat": 0, "moved_other": 0}


def _fail_mask(codes: np.ndarray, strict: bool) -> np.ndarray:
    fail = (codes == PX_HOLE) | (codes == PX_MATERIAL_CHANGED) | (codes == PX_MOVED_OTHER)
    if strict:
        fail = fail | (codes == PX_MOVED_SAME_FLAT)
    return fail


def compare_views(before: Sequence[RenderedView], after: Sequence[RenderedView],
                   face_material_before: np.ndarray, face_material_after: np.ndarray,
                   flat_materials: Iterable[int], depth_tol: float,
                   strict: bool = False) -> GuardReport:
    """Compare a BEFORE/AFTER pair of `ortho_first_hit` renders, one `(view, depth, tri)` triple
    per view, paired by position (`before[i]` and `after[i]` must be the same view, and both
    sequences the same length).

    `strict=True` (use for automatic removal of exposure-0 faces -- a depth change there means
    sampling missed real visibility) counts `moved_same_flat` pixels as failures too;
    `strict=False` (use for a change a person already accepted) reports them but tolerates them.
    `passed` is `holes + material_changed + moved_other == 0`, plus `moved_same_flat` when
    `strict`. `moved_same_flat` is always reported in `totals` and every `ViewVerdict`, never
    silently dropped."""
    if len(before) != len(after):
        raise ValueError(f"before/after must have the same number of views, got {len(before)} vs {len(after)}")

    view_verdicts = []
    totals = _zero_totals()
    for (view, before_depth, before_tri), (_, after_depth, after_tri) in zip(before, after):
        codes = classify_pixels(before_depth, before_tri, after_depth, after_tri,
                                 face_material_before, face_material_after, flat_materials, depth_tol)
        counts = {
            "model_px": int((np.asarray(before_tri) >= 0).sum()),
            "holes": int((codes == PX_HOLE).sum()),
            "material_changed": int((codes == PX_MATERIAL_CHANGED).sum()),
            "moved_same_flat": int((codes == PX_MOVED_SAME_FLAT).sum()),
            "moved_other": int((codes == PX_MOVED_OTHER).sum()),
        }
        view_verdicts.append(ViewVerdict(view=tuple(view), **counts))
        for k, v in counts.items():
            totals[k] += v

    fail_total = totals["holes"] + totals["material_changed"] + totals["moved_other"]
    if strict:
        fail_total += totals["moved_same_flat"]
    return GuardReport(views=view_verdicts, passed=fail_total == 0, totals=totals)


def guard_feedback(candidates: np.ndarray, positions_c: np.ndarray, faces: np.ndarray,
                    face_material: np.ndarray, flat_materials: Iterable[int], depth_tol: float,
                    strict: bool, views: Sequence[Sequence[float]] = VIEWS_26,
                    size: tuple[int, int] = (900, 600), caster_factory=EmbreeCaster,
                    max_rounds: int = 8) -> tuple[np.ndarray, list[dict]]:
    """Iteratively confirm which `candidates` (bool mask over ALL of `faces`) can be removed
    without changing the outside, by the same depth/colour-aware pixel test as `compare_views`.

    `positions_c`/`faces` are the ORIGINAL geometry -- every face the guard should consider,
    already whatever subset the caller wants treated as renderable (e.g. non-degenerate only);
    `candidates` and the returned mask are indexed against this same `faces` array. Vertices are
    never moved, so `positions_c` also serves as `frame_points` for every render, before and
    after, keeping pixels aligned across rounds. `face_material` is the single per-face material
    array (materials don't change here, only face presence). `strict` is forwarded to the same
    pixel test `compare_views` uses: `True` for automatic removal of exposure-0 faces, `False`
    for a person-accepted change.

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

    before = [(view,) + ortho_first_hit(positions_c, faces, face_ids, view, positions_c, size, caster_factory)
              for view in views]

    removed = candidates.copy()
    history = []
    for rnd in range(max_rounds):
        keep = ~removed
        keep_faces = faces[keep]
        keep_ids = face_ids[keep]

        restore = set()
        failing_pixels = 0
        for view, before_depth, before_tri in before:
            after_depth, after_tri = ortho_first_hit(positions_c, keep_faces, keep_ids, view, positions_c,
                                                      size, caster_factory)
            codes = classify_pixels(before_depth, before_tri, after_depth, after_tri,
                                     face_material, face_material, flat_materials, depth_tol)
            fail = _fail_mask(codes, strict)
            failing_pixels += int(fail.sum())
            offenders = before_tri[fail]
            restore.update(offenders[removed[offenders]].tolist())

        history.append({"round": rnd, "candidates_remaining": int(removed.sum()),
                         "failing_pixels": failing_pixels, "restored": len(restore)})
        if failing_pixels == 0 or not restore:
            break
        removed[list(restore)] = False

    return removed, history
