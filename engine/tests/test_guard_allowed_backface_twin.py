"""`compare_views(..., allowed_pairs=)`: the guard-side, OPT-IN allowed-change class `allowed_backface_twin`
(owner-approved extension of the Validator's `coincident_backface_removed` to the strict 26-view guard, 2026-10-29),
with the counts reported raw (`raw_totals`) and after the exclusion (`totals`), and `failed_by`.

Fixture: a kept +z quad (the exposed twin, material 0) at z = 0 and, 0.01 in nearer the camera, its removed -z
back-face (material 1) -- within the depth tolerance, so without the class the pixels are `material_changed`.
"""
import numpy as np

from engine.guard.compare import (PX_ALLOWED_BACKFACE_TWIN, PX_HOLE, PX_MATERIAL_CHANGED, compare_views, face_planes)
from engine.guard.views import ortho_first_hit

VIEW = (0.0, 0.0, -1.0)          # rays travel -z: the camera is on the +z side
SIZE = (120, 80)
TOL = 0.15


def _quad(z, base=0):
    P = np.array([[-200.0, -200.0, z], [200.0, -200.0, z], [200.0, 200.0, z], [-200.0, 200.0, z]], float)
    return P, np.array([[0, 1, 2], [0, 2, 3]], np.int64) + base


def fixture(gap=0.01):
    """BEFORE = twin (faces 0, 1; +z; material 0) + back-face (faces 2, 3; -z; material 1) `gap` nearer the camera;
    AFTER = the twin alone (faces 0, 1). `(positions, faces_before, faces_after, mat_before, mat_after)`."""
    P0, F0 = _quad(0.0)
    P1, F1 = _quad(gap, base=4)
    F1 = F1[:, ::-1]                                       # reversed winding: normal -z, a back-face to this view
    positions = np.vstack([P0, P1])
    faces_before = np.vstack([F0, F1])
    return positions, faces_before, F0, np.array([0, 0, 1, 1], np.int64), np.array([0, 0], np.int64)


def render(positions, faces, frame):
    return [(VIEW, ortho_first_hit(positions, faces, np.arange(len(faces)), VIEW, frame, SIZE))]


def strict(before, after, mat_b, mat_a, positions, fb, fa, **kw):
    return compare_views(before, after, mat_b, mat_a, (), TOL, strict=True,
                         plane_before=face_planes(positions, fb), plane_after=face_planes(positions, fa),
                         geometry_before=(positions, fb), geometry_after=(positions, fa),
                         crack_closed_cap=0.0, fragment_removed_cap=0.0, **kw)


PAIRS = np.array([[2, 0], [2, 1], [3, 0], [3, 1]], np.int64)   # (BEFORE back-face, AFTER twin) for both twin triangles


def test_default_strict_guard_is_unchanged_and_refuses_the_backface_removal():
    positions, fb, fa, mb, ma = fixture()
    before, after = render(positions, fb, positions), render(positions, fa, positions)
    assert set(np.unique(before[0][1].tri[before[0][1].tri >= 0])) == {2, 3}, 'BEFORE must see the back-face first'
    report = strict(before, after, mb, ma, positions, fb, fa)
    assert report.passed is False
    assert report.totals['material_changed'] > 1000
    assert report.totals['allowed_backface_twin'] == 0 and report.views[0].allowed_backface_twin == 0
    assert report.totals['holes'] == 0
    assert report.raw_totals == report.totals, 'without the class the raw counts are the counts'
    assert report.failed_by == {'material_changed': report.totals['material_changed']}


def test_the_class_reclassifies_exactly_the_twin_pixels_and_the_guard_passes():
    positions, fb, fa, mb, ma = fixture()
    before, after = render(positions, fb, positions), render(positions, fa, positions)
    plain = strict(before, after, mb, ma, positions, fb, fa)
    report = strict(before, after, mb, ma, positions, fb, fa, allowed_pairs=PAIRS)
    assert report.passed is True and report.failed_by == {}
    assert report.totals['material_changed'] == 0 and report.totals['moved_other'] == 0
    assert report.totals['allowed_backface_twin'] == plain.totals['material_changed']
    assert report.totals['allowed_backface_twin_material'] == report.totals['allowed_backface_twin']
    assert report.totals['allowed_backface_twin_moved_other'] == 0 == report.totals['allowed_backface_twin_moved_same_flat']
    assert report.views[0].allowed_backface_twin == report.totals['allowed_backface_twin']
    assert report.views[0].allowed_backface_twin_material == report.totals['allowed_backface_twin']
    assert report.totals['model_px'] == plain.totals['model_px']
    assert report.raw_totals == plain.totals, 'the raw counts are what the guard counted without the class'
    assert PX_ALLOWED_BACKFACE_TWIN not in (PX_HOLE, PX_MATERIAL_CHANGED)


def test_holes_still_fail_under_the_class():
    positions, fb, fa, mb, ma = fixture()
    before = render(positions, fb, positions)
    after = render(positions, np.zeros((0, 3), np.int64), positions)
    report = strict(before, after, mb, np.zeros(0, np.int64), positions, fb, np.zeros((0, 3), np.int64),
                    allowed_pairs=PAIRS)
    assert report.passed is False
    assert report.totals['holes'] > 1000 and report.totals['allowed_backface_twin'] == 0
    assert report.failed_by == {'holes': report.totals['holes']}


def test_a_pixel_whose_after_face_is_not_the_listed_twin_still_fails():
    positions, fb, fa, mb, ma = fixture()
    before, after = render(positions, fb, positions), render(positions, fa, positions)
    only_one_twin = np.array([[2, 0], [3, 0]], np.int64)        # AFTER triangle 1 is not anybody's twin
    report = strict(before, after, mb, ma, positions, fb, fa, allowed_pairs=only_one_twin)
    assert report.passed is False
    assert report.totals['material_changed'] > 0 and report.totals['allowed_backface_twin'] > 0
    plain = strict(before, after, mb, ma, positions, fb, fa)
    assert report.totals['material_changed'] + report.totals['allowed_backface_twin'] == plain.totals['material_changed']
    assert report.raw_totals == plain.totals
    assert report.failed_by == {'material_changed': report.totals['material_changed']}


def test_a_listed_pair_beyond_the_depth_tolerance_is_not_excused():
    positions, fb, fa, mb, ma = fixture(gap=1.0)                # 1 in apart: not coincident
    before, after = render(positions, fb, positions), render(positions, fa, positions)
    report = strict(before, after, mb, ma, positions, fb, fa, allowed_pairs=PAIRS)
    assert report.passed is False
    assert report.totals['allowed_backface_twin'] == 0
    assert report.totals['material_changed'] + report.totals['moved_other'] > 1000
    assert set(report.failed_by) <= {'material_changed', 'moved_other'} and sum(report.failed_by.values()) > 1000


def test_an_empty_pair_list_is_the_default():
    positions, fb, fa, mb, ma = fixture()
    before, after = render(positions, fb, positions), render(positions, fa, positions)
    plain = strict(before, after, mb, ma, positions, fb, fa)
    empty = strict(before, after, mb, ma, positions, fb, fa, allowed_pairs=np.zeros((0, 2), np.int64))
    assert empty.totals == plain.totals and empty.passed is plain.passed
    assert empty.raw_totals == plain.raw_totals and empty.failed_by == plain.failed_by
