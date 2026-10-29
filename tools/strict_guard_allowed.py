"""The strict 26-view guard WITH the owner-approved allowed-change class `coincident_backface_removed`, for the
independent guards (`tools/e5_independent_guard.py`, `tools/e4_independent_guard.py`, `--allow`).

The clean worktree's `strict_guard` (`tools/main_infra_candidate.py` of the 4F-7F worktree, loaded by path and never
edited) forwards nothing to `compare_views` beyond its fixed arguments, so `strict_guard_allowed` here replicates its
render loop EXACTLY -- the same recentring, `VIEWS_26`, 900 x 600, `ReusableCaster`, `guard_depth_tol` over the
transformed source quanta, `strict=True`, planes and geometry, `crack_closed_cap=0.0`, `fragment_removed_cap=0.0` --
and adds the one keyword `allowed_pairs=` (`engine.guard.compare.compare_views`, the one owner-approved touch under
`engine/guard/**`). Without `--allow` the guards still call the helper's own `strict_guard`.

THE EXEMPTION SET is computed here, OUTSIDE the guard, by `backface_twin_pairs`: the Validator's class, face by face
(`engine.validate.checks.CBR`, owner decision 2026-10-24). A BEFORE face is a removed back-face iff it is not kept in
AFTER and its FRONT exposure in BEFORE is 0 (`engine.vis.exposure.compute_side_exposure`, the error census's and E5's
own measure); its coincident twins are the KEPT BEFORE faces whose front exposure is above 0, whose normal is OPPOSITE
(dot < -0.7, `checks._OPPOSITE_DOT`) and whose plane lies within the depth tolerance of sample points of the removed
face, the projected sample inside the twin. Every such `(removed BEFORE face, twin's AFTER face id)` pair is listed,
so a pixel of the removed face that falls on either triangle of a twin quad is covered. The guard then excuses a
`material_changed` / `moved_other` / `moved_same_flat` pixel ONLY where BEFORE's first hit is the removed face, AFTER's
is a listed twin and the two depths agree within the tolerance (`engine.guard.compare.PX_ALLOWED_BACKFACE_TWIN`,
counted as `allowed_backface_twin`); holes, growth and every other class fail as before.
"""
from __future__ import annotations

import numpy as np

from engine.fixes.pipeline import FixProfile, guard_depth_tol
from engine.guard.compare import compare_views, face_planes
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.rays.caster import EmbreeCaster, ReusableCaster
from engine.topo.weld import axis_quanta
from engine.validate.checks import _INSIDE, _OPPOSITE_DOT, ALLOWED_CHANGE_CLASSES, CBR, _barycentric, _FaceGrid
from engine.vis.exposure import compute_side_exposure

#: `--allow` names, the Validator's (`engine.validate.checks.ALLOWED_CHANGE_CLASSES`) -> the guard's counted class.
GUARD_CLASS = {CBR: "allowed_backface_twin"}
assert set(GUARD_CLASS) == set(ALLOWED_CHANGE_CLASSES)
RESOLUTION = (900, 600)
#: Where a removed face is asked for its twin: its centroid, three points near its corners, three near its edges.
_SAMPLE_BARY = np.array([[1 / 3, 1 / 3, 1 / 3],
                         [0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8],
                         [0.45, 0.45, 0.1], [0.1, 0.45, 0.45], [0.45, 0.1, 0.45]], dtype=np.float64)


def guard_frame(before, source, provenance):
    """What `strict_guard` renders in: `(recentred BEFORE positions, depth tolerance, transformed quanta)` -- the
    bbox-centre recentring and `guard_depth_tol(|source_to_engine| @ axis_quanta(source), FixProfile())`."""
    center = (before.positions.min(axis=0) + before.positions.max(axis=0)) / 2
    positions = before.positions - center
    quanta = np.abs(np.asarray(provenance['source_to_engine'])[:3, :3]) @ axis_quanta(source.positions, source.sig_digits)
    depth_tol = guard_depth_tol(quanta, FixProfile())
    return positions, depth_tol, quanta


def after_index_of_kept(before_face_v, after_face_v, kept_faces) -> np.ndarray:
    """`(n_before,)` int64: the AFTER face id of each kept BEFORE face (`kept_faces`, BEFORE ids), -1 for a removed
    one. Matched by exact vertex rows, so the kept faces may sit anywhere in AFTER (E5: first and in order; E4: before
    the new triangles); a kept face AFTER does not hold raises."""
    before_face_v, after_face_v = np.asarray(before_face_v, np.int64), np.asarray(after_face_v, np.int64)
    kept_faces = np.asarray(kept_faces, np.int64)
    index = np.full(len(before_face_v), -1, dtype=np.int64)
    if not len(kept_faces):
        return index
    if len(after_face_v) >= len(kept_faces) and np.array_equal(after_face_v[:len(kept_faces)], before_face_v[kept_faces]):
        index[kept_faces] = np.arange(len(kept_faces))          # the E5 layout: kept faces first, in order
        return index
    rows = {tuple(row): j for j, row in enumerate(after_face_v.tolist())}
    for f in kept_faces.tolist():
        j = rows.get(tuple(before_face_v[f].tolist()))
        if j is None:
            raise ValueError(f'kept BEFORE face {f} is not in AFTER')
        index[f] = j
    return index


def backface_twin_pairs(positions_c, face_v, kept_faces, after_face_v, depth_tol, *, caster_factory=EmbreeCaster,
                        n_dirs: int = 128, opposite_dot: float = _OPPOSITE_DOT, front=None):
    """The exemption set of `coincident_backface_removed` for the strict guard: `(pairs, report)`. `pairs` is an
    `(K, 2)` int64 array of `(removed BEFORE face, AFTER face id of its kept coincident twin)`; `report` counts what
    was asked and found. `positions_c` is the guard's recentred BEFORE geometry (`guard_frame`), `face_v` BEFORE's
    faces, `kept_faces` the kept BEFORE ids (the contract's `baseline_kept_source_faces`), `after_face_v` AFTER's
    faces. `front` lets a caller pass the BEFORE front exposure already measured; by default it is measured here
    with `compute_side_exposure(positions_c, face_v, ok, caster_factory, n_dirs)` over the WHOLE mesh (the caster is
    built from `ok`, so a subset would remove occluders)."""
    positions_c = np.asarray(positions_c, dtype=np.float64)
    face_v = np.asarray(face_v, dtype=np.int64)
    n = len(face_v)
    kept_faces = np.asarray(kept_faces, dtype=np.int64)
    kept = np.zeros(n, dtype=bool)
    kept[kept_faces] = True
    planes = face_planes(positions_c, face_v)
    normals = planes[:, :3]
    ok = np.linalg.norm(normals, axis=1) > 0.0
    if front is None:
        front, _back = compute_side_exposure(positions_c, face_v, ok, caster_factory=caster_factory, n_dirs=n_dirs)
    front = np.asarray(front, dtype=np.float64)
    removed = ~kept
    cand = np.flatnonzero(removed & ok & (front <= 0.0))
    twins = np.flatnonzero(kept & ok & (front > 0.0))
    report = dict(rule=CBR, guard_class=GUARD_CLASS[CBR], opposite_dot=float(opposite_dot), depth_tol_inches=float(depth_tol),
                  exposure_n_dirs=int(n_dirs), exposure_caster=getattr(caster_factory, '__name__', str(caster_factory)),
                  before_faces=int(n), kept_faces=int(kept.sum()), removed_faces=int(removed.sum()),
                  removed_hidden_front=int(len(cand)), kept_front_exposed=int(len(twins)),
                  samples_per_face=int(len(_SAMPLE_BARY)), excused_faces=0, twin_faces=0, pairs=0)
    pairs = np.zeros((0, 2), dtype=np.int64)
    if not len(cand) or not len(twins):
        return pairs, report
    after_index = after_index_of_kept(face_v, after_face_v, kept_faces)
    grid = _FaceGrid(positions_c, face_v, twins, float(depth_tol))
    tri = positions_c[face_v[cand]]                                            # (C, 3, 3)
    points = np.einsum('sb,cbk->csk', _SAMPLE_BARY, tri).reshape(-1, 3)        # (C * S, 3)
    owner = np.repeat(cand, len(_SAMPLE_BARY))                                # the removed face of each sample
    rows, faces = grid.lookup(points)
    found = set()
    if len(rows):
        nf, ns = normals[faces], normals[owner[rows]]
        opposite = np.einsum('ij,ij->i', nf, ns) < opposite_dot
        a0 = positions_c[face_v[faces, 0]]
        p = points[rows]
        dist = np.einsum('ij,ij->i', p - a0, nf)
        q = p - dist[:, None] * nf
        inside = (_barycentric(positions_c, face_v[faces], q) >= -_INSIDE).all(axis=1)
        hit = opposite & (np.abs(dist) <= float(depth_tol)) & inside
        found = {(int(owner[r]), int(f)) for r, f in zip(rows[hit], faces[hit])}
    if found:
        before_pairs = np.array(sorted(found), dtype=np.int64)
        pairs = np.stack([before_pairs[:, 0], after_index[before_pairs[:, 1]]], axis=1)
        assert (pairs[:, 1] >= 0).all(), 'a twin is a kept face, so it has an AFTER id'
        report.update(excused_faces=int(len(np.unique(pairs[:, 0]))), twin_faces=int(len(np.unique(before_pairs[:, 1]))),
                      pairs=int(len(pairs)))
    return pairs, report


def strict_guard_allowed(before, after, source, provenance, *, allowed_pairs, caster_factory=EmbreeCaster, on_view=None,
                         render=ortho_first_hit, compare=compare_views):
    """`strict_guard` of the clean worktree's `tools/main_infra_candidate.py`, line for line, plus
    `compare_views(..., allowed_pairs=allowed_pairs)`. Returns `(GuardReport, depth_tol)` like it. `render` and
    `compare` exist for tests that fake the renderer; the guards never pass them."""
    positions, depth_tol, quanta = guard_frame(before, source, provenance)

    def render_views(mesh, label):
        factory = ReusableCaster(caster_factory)
        rendered = []
        for index, view in enumerate(VIEWS_26, 1):
            rendered.append((view, render(positions, mesh.face_v, np.arange(mesh.n_faces), view, positions, RESOLUTION, factory)))
            print(f'GUARD rendered {mesh.n_faces} triangles view {index}/26', flush=True)
            if on_view:
                on_view(label, index)
        return rendered

    print(f'GUARD original sig_digits={source.sig_digits}, transformed quanta={quanta.tolist()}, existing depth tolerance={depth_tol}in',
          flush=True)
    print(f'GUARD allowed-change class {CBR} -> {GUARD_CLASS[CBR]}: {len(allowed_pairs)} (removed back-face, kept twin) pairs',
          flush=True)
    before_views, after_views = render_views(before, 'Before'), render_views(after, 'After')
    print('GUARD comparing saved 26-view buffers', flush=True)
    report = compare(before_views, after_views, before.face_material, after.face_material, (),
                     depth_tol, strict=True, plane_before=face_planes(positions, before.face_v),
                     plane_after=face_planes(positions, after.face_v),
                     geometry_before=(positions, before.face_v), geometry_after=(positions, after.face_v),
                     caster_factory=caster_factory,
                     crack_closed_cap=0.0, fragment_removed_cap=0.0, allowed_pairs=allowed_pairs)
    return report, depth_tol


def run_strict_guard(helper, before, after_bound, source, provenance, *, kept_faces, allowed_changes, audit=None,
                     caster_factory=None, exposure_caster_factory=EmbreeCaster, on_view=None):
    """What both independent guards do after the readback: WITHOUT `allowed_changes` the helper's own, unchanged
    `strict_guard` (`helper` is the loaded `tools/main_infra_candidate.py` module); WITH `coincident_backface_removed`
    the exemption set from the BEFORE geometry (`backface_twin_pairs`; `n_dirs` from the audit's
    `engine_report.exposure_n_dirs` when present, else 128) and `strict_guard_allowed`. Returns
    `(report, depth_tol, receipt_fields)` -- `receipt_fields` names the caller, the class, the pairs, how many
    pixels the class excused (`excused_px`), the counts BEFORE the exclusion (`raw_totals`) and the failing classes
    after it (`failed_by`), so a receipt always says what judged it and what it refused on."""
    caster_kwargs = {} if caster_factory is None else dict(caster_factory=caster_factory)
    caster_name = getattr(caster_factory, '__name__', None) or 'EmbreeCaster default'
    if not allowed_changes:
        report, tol = helper.strict_guard(before, after_bound, source, provenance, on_view=on_view, **caster_kwargs)
        fields = dict(guard_caller='unchanged helper strict_guard', allowed_changes=[], guard_class=None,
                      allowed_pairs=None, excused_px=0, raw_totals=getattr(report, 'raw_totals', None),
                      failed_by=getattr(report, 'failed_by', None))
        return report, tol, fields
    assert allowed_changes == [CBR], allowed_changes
    positions, depth_tol, _quanta = guard_frame(before, source, provenance)
    n_dirs = int(((audit or {}).get('engine_report') or {}).get('exposure_n_dirs') or 128)
    pairs, pair_report = backface_twin_pairs(positions, before.face_v, kept_faces, after_bound.face_v, depth_tol,
                                             caster_factory=exposure_caster_factory, n_dirs=n_dirs)
    print(f'GUARD {CBR}: {pair_report}', flush=True)
    report, tol = strict_guard_allowed(before, after_bound, source, provenance, allowed_pairs=pairs, on_view=on_view,
                                       **caster_kwargs)
    fields = dict(guard_caller=f'tools/strict_guard_allowed.strict_guard_allowed (replicates the helper strict_guard render '
                               f'loop; caster {caster_name}; compare_views allowed_pairs)',
                  allowed_changes=list(allowed_changes), guard_class=GUARD_CLASS[CBR], allowed_pairs=pair_report,
                  excused_px=int(report.totals.get(GUARD_CLASS[CBR], 0)),
                  raw_totals=getattr(report, 'raw_totals', None), failed_by=getattr(report, 'failed_by', None))
    return report, tol, fields


def parse_allow(values) -> list[str]:
    """The `--allow` names, validated against the Validator's class names, de-duplicated in order."""
    out: list[str] = []
    for name in values or ():
        if name not in GUARD_CLASS:
            raise ValueError(f'unknown allowed-change class {name!r}; the strict guard knows {sorted(GUARD_CLASS)}')
        if name not in out:
            out.append(name)
    return out
