"""Brief 09 item 1: a debris removal is confirmed by rays through the piece itself.

The fragment guard judges pixels, and at the real files' guard size (1.5 to 3.5 in a pixel) no
guard pixel ever meets a strip 0.001 to 0.05 in wide: brief 08 found 10 pieces of real surface
removed that way, each shipping a hairline crack onto the inside, with every guard passing, and
two sub-pixel slots (file A's faces 3540 and 4659) still shipping after the open-border rule.
So every candidate is also judged by LINES THROUGH IT: points area-stratified on the piece, and
from each exposure direction that reaches the piece from outside on the reference, the line that
meets it there; with the piece gone, that line is followed on, and a piece whose lines reach a
face side the reference never exposed -- the inside of a shell -- is refused.
"""
import numpy as np
import pytest

import engine.fixes.pipeline as fix_pipeline
from engine.detectors.fragments import FragmentResult
from engine.fixes.pipeline import FixProfile, fix_object
from engine.guard.piece_rays import piece_ray_check, strata_points
from engine.pipeline import analyse_topology
from engine.rays.caster import EmbreeCaster
from engine.tests.fixtures.build import (printed, slab_with_interior_strip,
                                         slab_with_lip_over_a_slot, slab_with_needle_lying_on_top,
                                         slab_with_standing_needle)
from engine.vis.exposure import compute_side_exposure, fib_dirs

#: The real files' scale with a guard coarser than the real one, so it sees even less: at 2000 in
#: a 240 x 160 guard pixel spans about 8 in, and no guard ray meets any of these pieces.
_REAL_SCALE = FixProfile(guard_size=(240, 160), n_dirs=32, solidify=False)


def _setup(mesh, n_dirs=32):
    """The recentred frame, faces and per-side exposure exactly as `fix_object` builds them."""
    topo = analyse_topology(mesh)
    pc = topo.positions_w - (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    front, back = compute_side_exposure(pc, topo.face_w, topo.ok, n_dirs=n_dirs)
    return pc, topo.face_w, np.stack([front > 0.0, back > 0.0], axis=1)


def _check(mesh, units, **kw):
    pc, faces, exposed = _setup(mesh)
    return piece_ray_check([np.asarray(u) for u in units], pc, faces, exposed,
                           directions=fib_dirs(32), **kw)


def _verdict(result, faces):
    """The ray verdict `fix_object` reports for the candidate made of exactly `faces`."""
    found = [v for v in result.fragment_ray_check if v["faces"] == list(faces)]
    assert len(found) == 1, result.fragment_ray_check
    return found[0]


def _first_z_down(mesh, xy, top=50.0):
    """z where straight-down rays from above each `(x, y)` first meet `mesh`, NaN for a miss."""
    xy = np.asarray(xy, dtype=np.float64)
    origins = np.column_stack([xy, np.full(len(xy), top)])
    tri, t = EmbreeCaster(mesh.positions, mesh.face_v).first_hit(
        origins, np.tile([0.0, 0.0, -1.0], (len(xy), 1)))
    return np.where(tri >= 0, top - t, np.nan)


# ----------------------------------------------------------------------------- the strata


def test_the_points_are_one_per_equal_area_stratum_and_spread_along_a_needle():
    """Area-stratified: the face is cut into slices along its longest edge and equal-area bands
    from that edge toward the apex, strata as square as the face allows but never fewer than four
    bands -- so a needle is sampled along its whole length AND across its width -- and each point
    is the middle, by area, of its own stratum."""
    needle = np.array([[0.0, 0.0, 0.0], [16.0, 0.0, 0.0], [8.0, 0.1, 0.0]])
    pts = strata_points(needle, 256)
    assert len(pts) == 256
    # each point as (u, h): the point `h` of the way from `u` along the longest edge to the apex
    assert np.allclose(pts[:, 2], 0.0)
    h = pts[:, 1] / 0.1
    u = (pts[:, 0] - 8.0 * h) / (16.0 * (1.0 - h))
    assert ((h > 0.0) & (h < 1.0) & (u > 0.0) & (u < 1.0)).all()      # inside the outline
    # 64 slices along its 16 in -- a point every 0.25 in -- and 4 bands across its 0.1 in
    assert np.allclose(np.unique(np.round(u, 9)), (np.arange(64) + 0.5) / 64)
    assert len(np.unique(np.round(h, 9))) == 4
    # equal areas: the part of the face within 1 - sqrt(3/4) of the way to the apex is a quarter
    # of its area (far less than a quarter of its height), and holds a quarter of the points
    assert int((h < 1.0 - np.sqrt(0.75)).sum()) == 64

    # a fat face gets strata as square as it allows
    fat = np.array([[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [2.0, 3.0, 0.0]])
    fat_pts = strata_points(fat, 256)
    assert 240 <= len(fat_pts) <= 272
    assert len(np.unique(np.round(fat_pts[:, 1], 9))) > 4


# ------------------------------------------------------------------ the check on its own


@pytest.mark.parametrize("width", [0.05, 0.14])
def test_review_experiment_e2b_the_sandwiched_strip_is_refused(width):
    """Review 2a experiment E2b: a 29.5 in strip of walking surface, sandwiched in the top of a
    closed 2000 in slab. Every line through it, with it gone, falls through the slit onto the
    inside of the bottom -- a side nobody could see on the reference."""
    m = printed(slab_with_interior_strip(width=width, size=2000.0))
    result = _check(m, [[0]])
    assert not result.confirmed[0]
    v = result.verdicts[0]
    assert v["refused"] is True
    assert v["lines"] > 0 and v["lines_inside"] > 0.9 * v["lines"]
    assert v["faces"] == [0] and v["points"] == 256
    bottom = [m.n_faces - 2, m.n_faces - 1]
    assert set(v["inside_faces"]) <= set(bottom) and v["inside_faces"]


def test_review_c2s_infill_patch_is_refused_as_one_unit():
    """Review C2's probe: a 3 x 1 in patch of a closed slab's walking surface, two faces joined to
    the rest of the top only through T-junctions. Judged as one unit, as a fragment component is:
    every line through either face, with both gone, falls through the hole onto the inside."""
    from engine.tests.fixtures.build import slab_with_infill_patch
    m = slab_with_infill_patch()
    patch = [m.n_faces - 12, m.n_faces - 11]
    v = _check(m, [patch]).verdicts[0]
    assert v["faces"] == patch and v["points"] > 256            # both faces sampled
    assert v["refused"] is True and v["lines_inside"] > 0.9 * v["lines"]


def test_a_lip_over_a_slot_is_refused_by_the_lines_crossing_the_slot():
    m = printed(slab_with_lip_over_a_slot())
    v = _check(m, [[0]]).verdicts[0]
    assert v["refused"] is True
    # about half the lip lies over the slot, half on the top beside it
    assert 0 < v["lines_inside"] < v["lines"]


def test_a_free_needle_pointing_into_the_sky_is_confirmed():
    v = _check(printed(slab_with_standing_needle()), [[12]]).verdicts[0]
    assert v["refused"] is False
    assert v["lines"] > 0 and v["lines_inside"] == 0


@pytest.mark.parametrize("lift", [0.0, 0.01])
def test_a_double_layer_lying_on_a_coplanar_face_is_confirmed(lift):
    """Exactly in the top's plane, every line through the needle meets the top at the same depth
    -- a tie, which is still a line through the needle -- and, with it gone, the top's own outside
    side. Lifted by the fixture's print step (0.01 in: the weld rounds anything finer back into
    the plane), the same."""
    m = printed(slab_with_needle_lying_on_top(lift=lift))
    pc, faces, _exposed = _setup(m)
    assert pc[faces[12], 2].max() - pc[faces[0], 2].max() == pytest.approx(lift, abs=1e-9)
    v = _check(m, [[12]]).verdicts[0]
    assert v["refused"] is False
    assert v["lines"] > 0 and v["lines_inside"] == 0


def test_the_lines_are_followed_on_with_every_marked_piece_gone():
    """Brief 08's fold pair 5750/5751 at 670ad50: each of two pieces covers the other, so either
    one alone may go -- and the two together open the crack. The check judges each piece with
    EVERYTHING marked for removal gone, never one at a time. Here the lip is doubled by a copy of
    itself wound the other way (face 18)."""
    from dataclasses import replace
    m = printed(slab_with_lip_over_a_slot())
    lip = m.face_v[0]
    twin = replace(m, face_v=np.vstack([m.face_v, lip[::-1]]),
                   face_vt=np.vstack([m.face_vt, m.face_vt[0][::-1]]),
                   face_vn=np.vstack([m.face_vn, m.face_vn[0]]),
                   face_material=np.append(m.face_material, m.face_material[0]),
                   face_line=np.append(m.face_line, m.face_line.max() + 1))
    alone = _check(twin, [[0]])
    assert alone.confirmed.tolist() == [True]           # its twin still covers the slot
    both = _check(twin, [[0], [18]])
    assert both.confirmed.tolist() == [False, False]


def test_the_ray_check_is_deterministic():
    m = printed(slab_with_lip_over_a_slot())
    a, b = _check(m, [[0], [3]]), _check(m, [[0], [3]])
    assert a.confirmed.tolist() == b.confirmed.tolist()
    assert a.verdicts == b.verdicts and a.history == b.history


# ------------------------------------------------------------------- through `fix_object`


def _names_as_sliver(face):
    """The detector exactly as it is, except that it also names `face` a sliver."""
    real = fix_pipeline.detect_fragments

    def detect(positions_w, face_w, profile, **kw):
        d = real(positions_w, face_w, profile, **kw)
        slivers = d.slivers.copy()
        slivers[face] = True
        return FragmentResult(d.fragments, slivers, d.component, d.report)
    return detect


@pytest.mark.parametrize("width", [0.05, 0.14])
def test_fix_object_refuses_the_e2b_strip_even_when_the_detector_names_it(monkeypatch, width):
    """The detector's open-border rule is what keeps the strip now; with that defence switched
    off, the pixel guard would let it go at this scale (review 2a: 97 of 97 rays down the strip
    fell through, `passed` True). The rays through the strip refuse it on their own."""
    size = 2000.0
    m = printed(slab_with_interior_strip(width=width, size=size))
    monkeypatch.setattr(fix_pipeline, "detect_fragments", _names_as_sliver(0))
    r = fix_object(m, {}, FixProfile(guard_size=(240, 160), n_dirs=32))
    assert not r.removed_fragments[0]
    v = _verdict(r, [0])
    assert v["kind"] == "sliver" and v["refused"] is True and v["lines_inside"] > 0
    assert r.n_refused_by_rays == 1 and r.n_removed_slivers == 0
    xs = np.linspace(size / 2 - 12.0, size / 2 + 12.0, 97)
    ys = size / 2 + 0.4 * width * (1.0 - np.abs(xs - size / 2) / 14.75)
    assert np.isclose(_first_z_down(r.mesh, np.column_stack([xs, ys])), 0.0, atol=1e-6).all()
    assert r.passed is True


def test_fix_object_keeps_a_lip_over_a_slot():
    """The detector names the lip (its free long edge is open), and no guard pixel ever meets it
    at this scale -- so without the rays it went, and the slot shipped with `passed` True."""
    m = printed(slab_with_lip_over_a_slot())
    r = fix_object(m, {}, _REAL_SCALE)
    assert r.fragment_report["n_sliver_faces"] == 1               # the premise: it is named
    assert not r.removed_fragments[0]
    v = _verdict(r, [0])
    assert v["kind"] == "sliver" and v["refused"] is True
    assert 0 < v["lines_inside"] < v["lines"]
    # straight down through the slot's middle: the lip, at the top, not the bottom at -8
    c = 1000.0
    ys = np.linspace(c - 6.0, c + 7.5, 28)
    xs = c + 0.25 * 0.05 * (ys - (c - 8.0)) / 16.0
    assert np.isclose(_first_z_down(r.mesh, np.column_stack([xs, ys])), 0.0, atol=1e-6).all()
    assert r.passed is True


def test_fix_object_removes_a_free_needle_pointing_into_the_sky():
    r = fix_object(printed(slab_with_standing_needle()), {}, _REAL_SCALE)
    assert r.removed_fragments[12] and r.n_removed_slivers == 1
    v = _verdict(r, [12])
    assert v["refused"] is False and v["lines"] > 0 and v["lines_inside"] == 0
    [removal] = r.fragment_removals
    assert removal["faces"] == [12]
    assert removal["lines"] == v["lines"] and removal["lines_inside"] == 0
    assert r.passed is True


def test_fix_object_removes_a_double_layer_lying_on_a_coplanar_face():
    r = fix_object(printed(slab_with_needle_lying_on_top()), {}, _REAL_SCALE)
    assert r.removed_fragments[12] and r.n_removed_slivers == 1
    v = _verdict(r, [12])
    assert v["refused"] is False and v["lines"] > 0 and v["lines_inside"] == 0
    assert r.passed is True


def test_fix_object_reports_the_same_ray_verdicts_every_run():
    m = printed(slab_with_lip_over_a_slot())
    a, b = fix_object(m, {}, _REAL_SCALE), fix_object(m, {}, _REAL_SCALE)
    assert a.fragment_ray_check == b.fragment_ray_check
    assert a.removed_fragments.tolist() == b.removed_fragments.tolist()
