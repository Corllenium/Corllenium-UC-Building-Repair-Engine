import itertools

import numpy as np

from engine.guard.compare import (PX_HOLE, PX_MATERIAL_CHANGED, PX_MOVED_OTHER, PX_MOVED_SAME_FLAT, PX_OK,
                                   classify_pixels, compare_views, face_planes, guard_feedback)
from engine.guard.render import save_triptych
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import box_with_partition, cube, open_box_with_cells

_SIZE = (120, 80)  # small render: only correctness is under test, not image fidelity


def _centered_topo(mesh):
    """analyse_topology + recentre positions_w to the bbox centre, as ortho_first_hit requires."""
    topo = analyse_topology(mesh)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2
    return topo, topo.positions_w - centre


def _render_views(positions_c, faces, face_ids, views=VIEWS_26, size=_SIZE):
    return [(v, ortho_first_hit(positions_c, faces, face_ids, v, positions_c, size)) for v in views]


def _depth_tol(topo):
    return 1.5 * float(topo.quanta.max())


# ---------------------------------------------------------------------------
# views.py
# ---------------------------------------------------------------------------

def test_views_26_are_the_26_nudged_axis_and_diagonal_directions():
    assert len(VIEWS_26) == 26
    nudge = np.array([0.013, 0.007, 0.011])
    bases = set()
    for v in VIEWS_26:
        arr = np.array(v, dtype=float)
        base = np.round(arr - nudge)
        assert np.allclose(arr - base, nudge)
        bases.add(tuple(int(x) for x in base))
    expected = {v for v in itertools.product((-1, 0, 1), repeat=3) if any(v)}
    assert bases == expected


def test_ortho_first_hit_matches_cube_silhouette_and_miss_background():
    m = cube(10.0)
    positions_c = m.positions - 5.0
    faces = m.face_v
    ids = np.arange(len(faces))
    # frame_points wider than the cube itself so the render has visible background at the edges
    # (frame_points fits the frame tightly to whatever points it is given -- see ortho_first_hit).
    frame_points = positions_c * 2.0
    depth, tri = ortho_first_hit(positions_c, faces, ids, (0.0, 0.0, -1.0), frame_points, size=(20, 20))
    assert depth.shape == (20, 20)
    assert tri.shape == (20, 20)
    hit = tri >= 0
    assert hit.any() and (~hit).any()
    assert np.isfinite(depth[hit]).all()
    assert np.isinf(depth[~hit]).all()
    assert (tri[~hit] == -1).all()
    assert set(np.unique(tri[hit]).tolist()) <= set(ids.tolist())


def test_ortho_first_hit_empty_faces_is_all_miss():
    m = cube(10.0)
    positions_c = m.positions - 5.0
    depth, tri = ortho_first_hit(positions_c, np.zeros((0, 3), np.int64), np.zeros(0, np.int64),
                                  (0.0, 0.0, -1.0), positions_c, size=(8, 6))
    assert depth.shape == (6, 8) and tri.shape == (6, 8)
    assert np.isinf(depth).all()
    assert (tri == -1).all()


# ---------------------------------------------------------------------------
# compare.py: classify_pixels (direct, no rendering)
# ---------------------------------------------------------------------------

def test_classify_pixels_priority_order():
    before_tri = np.array([0, 1, 2, 3, 4, -1])
    after_tri = np.array([-1, 1, 2, 3, 4, -1])
    before_depth = np.array([1.0, 2.0, 3.0, 4.0, 5.0, np.inf])
    after_depth = np.array([np.inf, 2.0, 3.5, 4.6, 5.02, np.inf])
    material_before = np.array([9, 0, 0, 2, 0])
    material_after = np.array([9, 1, 0, 2, 0])
    flat_materials = frozenset({0})

    codes = classify_pixels(before_depth, before_tri, after_depth, after_tri,
                             material_before, material_after, flat_materials, depth_tol=0.1)

    assert codes.tolist() == [PX_HOLE, PX_MATERIAL_CHANGED, PX_MOVED_SAME_FLAT, PX_MOVED_OTHER, PX_OK, PX_OK]


def test_classify_pixels_empty_flat_materials_treats_everything_as_patterned():
    before_tri = np.array([0])
    after_tri = np.array([0])
    before_depth = np.array([1.0])
    after_depth = np.array([2.0])
    material = np.array([0])
    codes = classify_pixels(before_depth, before_tri, after_depth, after_tri, material, material,
                             frozenset(), depth_tol=0.1)
    assert codes.tolist() == [PX_MOVED_OTHER]


# ---------------------------------------------------------------------------
# compare.py: compare_views mutation tests on box_with_partition / open_box_with_cells
# ---------------------------------------------------------------------------

def test_identity_all_counts_zero_and_passed():
    m = box_with_partition()
    topo, Pc = _centered_topo(m)
    assert topo.ok.all()
    faces, ids = topo.face_w, np.arange(len(topo.face_w))
    rendered = _render_views(Pc, faces, ids)
    mat = m.face_material

    planes = face_planes(Pc, faces)
    report = compare_views(rendered, rendered, mat, mat, frozenset(), _depth_tol(topo), strict=True,
                            plane_before=planes, plane_after=planes)

    assert report.passed
    assert report.totals == {"model_px": report.totals["model_px"], "holes": 0, "material_changed": 0,
                              "moved_same_flat": 0, "moved_other": 0}
    assert report.totals["model_px"] > 0
    assert len(report.views) == 26


def test_delete_one_outer_face_fails():
    m = box_with_partition()
    topo, Pc = _centered_topo(m)
    faces, ids = topo.face_w, np.arange(len(topo.face_w))
    before = _render_views(Pc, faces, ids)
    keep = np.ones(len(faces), bool)
    keep[0] = False  # one triangle of an outer cube face
    after = _render_views(Pc, faces[keep], ids[keep])
    mat = m.face_material

    planes = face_planes(Pc, faces)
    report = compare_views(before, after, mat, mat, frozenset(), _depth_tol(topo),
                            plane_before=planes, plane_after=planes)

    assert not report.passed
    assert report.totals["holes"] > 0 or report.totals["moved_same_flat"] > 0 or report.totals["moved_other"] > 0


def test_delete_hidden_inner_tris_all_zero_and_passed():
    m = box_with_partition()
    topo, Pc = _centered_topo(m)
    faces, ids = topo.face_w, np.arange(len(topo.face_w))
    before = _render_views(Pc, faces, ids)
    keep = np.ones(len(faces), bool)
    keep[[12, 13]] = False  # the two sealed-inside partition tris
    after = _render_views(Pc, faces[keep], ids[keep])
    mat = m.face_material

    planes = face_planes(Pc, faces)
    report = compare_views(before, after, mat, mat, frozenset(), _depth_tol(topo), strict=True,
                            plane_before=planes, plane_after=planes)

    assert report.passed
    assert report.totals["holes"] == 0
    assert report.totals["material_changed"] == 0
    assert report.totals["moved_same_flat"] == 0
    assert report.totals["moved_other"] == 0


def test_material_change_on_visible_face_detected():
    m = box_with_partition()
    topo, Pc = _centered_topo(m)
    faces, ids = topo.face_w, np.arange(len(topo.face_w))
    rendered = _render_views(Pc, faces, ids)
    mat_before = m.face_material.copy()
    mat_after = m.face_material.copy()
    mat_after[0] = 1  # second material on one visible outer face; geometry unchanged

    planes = face_planes(Pc, faces)
    report = compare_views(rendered, rendered, mat_before, mat_after, frozenset({0, 1}), _depth_tol(topo),
                            plane_before=planes, plane_after=planes)

    assert not report.passed
    assert report.totals["material_changed"] > 0
    assert report.totals["holes"] == 0
    assert report.totals["moved_same_flat"] == 0
    assert report.totals["moved_other"] == 0


def test_open_box_flat_vs_patterned_removal_of_near_partition():
    m = open_box_with_cells()
    topo, Pc = _centered_topo(m)
    faces, ids = topo.face_w, np.arange(len(topo.face_w))
    before = _render_views(Pc, faces, ids)
    keep = np.ones(len(faces), bool)
    keep[[10, 11]] = False  # near partition
    after = _render_views(Pc, faces[keep], ids[keep])
    mat = m.face_material  # single default material shared by every face in this fixture
    depth_tol = _depth_tol(topo)

    planes = face_planes(Pc, faces)
    flat = compare_views(before, after, mat, mat, frozenset({0}), depth_tol, strict=False,
                          plane_before=planes, plane_after=planes)
    assert flat.totals["moved_same_flat"] > 0
    assert flat.totals["holes"] == 0
    assert flat.totals["material_changed"] == 0
    assert flat.totals["moved_other"] == 0
    assert flat.passed

    patterned = compare_views(before, after, mat, mat, frozenset(), depth_tol, strict=False,
                               plane_before=planes, plane_after=planes)
    assert patterned.totals["moved_other"] > 0
    assert not patterned.passed


# ---------------------------------------------------------------------------
# compare.py: the moved test measures SURFACE DISPLACEMENT, not depth along the ray
# ---------------------------------------------------------------------------

def _grazing_view():
    """A view 1 degree above the z = 0 plane, so a ray skims any face lying in it."""
    a = np.radians(1.0)
    return (float(np.cos(a)), 0.0, float(-np.sin(a)))


def _quad(z, x0=-200.0, x1=200.0, base=0):
    """Two triangles of a large axis-aligned quad in the plane `z` (normal +z)."""
    P = np.array([[x0, -200.0, z], [x1, -200.0, z], [x1, 200.0, z], [x0, 200.0, z]], float)
    return P, np.array([[0, 1, 2], [0, 2, 3]], np.int64) + base


def test_grazing_view_does_not_report_a_coplanar_shift_as_moved():
    """A 0.01 in shift along the surface normal, seen 1 degree off the plane, is a 0.57 in change
    measured ALONG the ray -- 4x depth_tol -- but the surface only moved 0.01 in."""
    view, size = _grazing_view(), (200, 200)
    P_before, faces = _quad(0.0)
    P_after = P_before + np.array([0.0, 0.0, 0.01])
    ids = np.arange(len(faces))
    before = ortho_first_hit(P_before, faces, ids, view, P_before, size)
    after = ortho_first_hit(P_after, faces, ids, view, P_before, size)  # SAME frame_points

    both = (before.tri >= 0) & (after.tri >= 0)
    assert int(both.sum()) > 500  # the grazing render really does cover pixels
    assert np.abs(after.depth[both] - before.depth[both]).max() > 0.15  # the OLD metric: moved

    mat = np.zeros(len(faces), np.int64)
    report = compare_views([(view, before)], [(view, after)], mat, mat, frozenset({0}), 0.15,
                            strict=True, plane_before=face_planes(P_before, faces),
                            plane_after=face_planes(P_after, faces))

    assert report.totals["moved_same_flat"] == 0
    assert report.totals["moved_other"] == 0


def test_grazing_view_still_catches_a_face_removed_over_a_surface_behind_it():
    """The same 1-degree view, but the quad is gone and a parallel quad 10 in behind shows
    through. The before hit point is 10 in from the revealed plane, so it still fails."""
    view, size = _grazing_view(), (200, 200)
    P_front, f_front = _quad(0.0)
    # long enough in x that a ray skimming the front quad still lands on it 573 in further along
    P_back, f_back = _quad(-10.0, x0=-200.0, x1=800.0, base=4)
    P = np.vstack([P_front, P_back])
    faces_before = np.vstack([f_front, f_back])
    faces_after = f_back
    before = ortho_first_hit(P, faces_before, np.arange(4), view, P, size)
    after = ortho_first_hit(P, faces_after, np.array([2, 3]), view, P, size)

    mat = np.zeros(4, np.int64)
    planes = face_planes(P, faces_before)
    report = compare_views([(view, before)], [(view, after)], mat, mat, frozenset({0}), 0.15,
                            strict=True, plane_before=planes, plane_after=planes)

    failures = (report.totals["holes"] + report.totals["moved_same_flat"]
                + report.totals["moved_other"])
    assert failures > 0
    assert report.totals["moved_same_flat"] > 0  # the revealed plane is hit, 10 in away
    assert not report.passed


def test_undefined_plane_falls_back_to_depth_along_the_ray():
    """A zero-area face has no plane; those pixels keep the old |t_before - t_after| test."""
    before_tri = np.array([0, 1])
    after_tri = np.array([0, 1])
    before_depth = np.array([1.0, 1.0])
    after_depth = np.array([1.0, 2.0])
    origins = np.zeros((2, 3))
    direction = np.array([0.0, 0.0, 1.0])
    mat = np.zeros(2, np.int64)
    # face 0 has a real plane (z = 1), face 1 is degenerate -> an all-zero row
    planes = np.array([[0.0, 0.0, 1.0, -1.0], [0.0, 0.0, 0.0, 0.0]])

    codes = classify_pixels(before_depth, before_tri, after_depth, after_tri, mat, mat,
                             frozenset({0}), depth_tol=0.15, origins=origins, direction=direction,
                             plane_before=planes, plane_after=planes)

    assert codes.tolist() == [PX_OK, PX_MOVED_SAME_FLAT]


# ---------------------------------------------------------------------------
# compare.py: guard_feedback
# ---------------------------------------------------------------------------

def test_guard_feedback_restores_wrong_face_keeps_only_hidden_tris():
    m = box_with_partition()
    topo, Pc = _centered_topo(m)
    faces = topo.face_w
    depth_tol = _depth_tol(topo)
    candidates = np.zeros(len(faces), dtype=bool)
    candidates[[12, 13]] = True  # truly hidden inner partition tris
    candidates[0] = True  # deliberately wrong: a visible outer face

    mask, history = guard_feedback(candidates, Pc, faces, m.face_material, frozenset(), depth_tol,
                                    strict=True, views=VIEWS_26, size=_SIZE)

    assert mask.tolist() == [i in (12, 13) for i in range(len(faces))]
    assert history[0]["restored"] == 1
    assert history[-1]["failing_pixels"] == 0


def test_guard_feedback_no_candidates_is_a_noop():
    m = box_with_partition()
    topo, Pc = _centered_topo(m)
    faces = topo.face_w
    candidates = np.zeros(len(faces), dtype=bool)

    mask, history = guard_feedback(candidates, Pc, faces, m.face_material, frozenset(), _depth_tol(topo),
                                    strict=True, views=VIEWS_26, size=_SIZE)

    assert not mask.any()
    assert history[0]["failing_pixels"] == 0
    assert len(history) == 1  # stops immediately: 0 failures


# ---------------------------------------------------------------------------
# render.py: save_triptych
# ---------------------------------------------------------------------------

def test_save_triptych_writes_three_panel_png(tmp_path):
    m = box_with_partition()
    topo, Pc = _centered_topo(m)
    faces, ids = topo.face_w, np.arange(len(topo.face_w))
    view = VIEWS_26[0]
    size = (40, 30)
    before = ortho_first_hit(Pc, faces, ids, view, Pc, size=size)
    keep = np.ones(len(faces), bool)
    keep[0] = False
    after = ortho_first_hit(Pc, faces[keep], ids[keep], view, Pc, size=size)
    codes = classify_pixels(before[0], before[1], after[0], after[1], m.face_material, m.face_material,
                             frozenset(), _depth_tol(topo))

    out = tmp_path / "diff.png"
    save_triptych(out, before, after, codes)

    assert out.exists()
    from PIL import Image
    img = np.array(Image.open(out))
    assert img.shape == (30, 40 * 3, 3)
