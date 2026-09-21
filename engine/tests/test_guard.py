import itertools

import numpy as np
import pytest

from engine.guard.compare import (PX_EDGE_FLICKER, PX_HOLE, PX_MATERIAL_CHANGED, PX_MOVED_OTHER,
                                   PX_MOVED_SAME_FLAT, PX_OK, classify_pixels, compare_views, face_planes,
                                   guard_feedback)
from engine.guard.render import save_triptych
from engine.guard.views import VIEWS_26, HitBuffers, ortho_first_hit
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
                             material_before, material_after, flat_materials, depth_tol=0.1,
                             allow_depth_fallback=True)  # a pure classification test: no geometry

    assert codes.tolist() == [PX_HOLE, PX_MATERIAL_CHANGED, PX_MOVED_SAME_FLAT, PX_MOVED_OTHER, PX_OK, PX_OK]


def test_classify_pixels_empty_flat_materials_treats_everything_as_patterned():
    before_tri = np.array([0])
    after_tri = np.array([0])
    before_depth = np.array([1.0])
    after_depth = np.array([2.0])
    material = np.array([0])
    codes = classify_pixels(before_depth, before_tri, after_depth, after_tri, material, material,
                             frozenset(), depth_tol=0.1, allow_depth_fallback=True)
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
                              "moved_same_flat": 0, "moved_other": 0, "edge_flicker": 0}
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


def test_depth_along_the_ray_fallback_must_be_asked_for_explicitly():
    """Forgetting the geometry used to hand the caller the metric that reported 676 false `moved`
    pixels on file A. It is now an error unless the caller asks for it by name."""
    args = (np.array([1.0]), np.array([0]), np.array([2.0]), np.array([0]),
            np.zeros(1, np.int64), np.zeros(1, np.int64), frozenset({0}))

    with pytest.raises(ValueError) as excinfo:
        classify_pixels(*args, depth_tol=0.15)
    assert "allow_depth_fallback" in str(excinfo.value)

    # half the geometry is not geometry: planes alone cannot place the hit points
    with pytest.raises(ValueError):
        classify_pixels(*args, depth_tol=0.15, plane_before=np.zeros((1, 4)),
                         plane_after=np.zeros((1, 4)))

    codes = classify_pixels(*args, depth_tol=0.15, allow_depth_fallback=True)
    assert codes.tolist() == [PX_MOVED_SAME_FLAT]


def test_compare_views_without_planes_needs_the_same_flag():
    m = cube(10.0)
    Pc = m.positions - 5.0
    faces, ids = m.face_v, np.arange(len(m.face_v))
    view = VIEWS_26[0]
    rendered = [(view, ortho_first_hit(Pc, faces, ids, view, Pc, _SIZE))]
    mat = m.face_material

    with pytest.raises(ValueError) as excinfo:
        compare_views(rendered, rendered, mat, mat, frozenset(), 0.15)
    assert "allow_depth_fallback" in str(excinfo.value)

    assert compare_views(rendered, rendered, mat, mat, frozenset(), 0.15,
                          allow_depth_fallback=True).passed


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
# compare.py: silhouette flicker is its own class
# ---------------------------------------------------------------------------

_FLICKER_VIEW = (0.0, 0.0, 1.0)


def _buffers(tri):
    """A synthetic `HitBuffers` over a `tri` image: every hit one unit away, every miss `inf`.
    Only `tri`/`depth` matter here -- the camera frame is a placeholder, and the single face is
    given no plane, so the moved test falls back to depth along the ray."""
    tri = np.asarray(tri, np.int64)
    h, w = tri.shape
    return HitBuffers(depth=np.where(tri >= 0, 1.0, np.inf), tri=tri,
                       direction=np.array([0.0, 0.0, 1.0]), right=np.array([1.0, 0.0, 0.0]),
                       up=np.array([0.0, 1.0, 0.0]), xs=np.arange(w, dtype=float),
                       ys=np.arange(h, dtype=float), standoff=np.zeros(3))


def _block(drop=()):
    """A 150x150 block of model (22,500 pixels) inside a 200x200 frame, minus `drop` pixels."""
    tri = np.full((200, 200), -1, np.int64)
    tri[25:175, 25:175] = 0
    for r, c in drop:
        tri[r, c] = -1
    return tri


#: A trivial, always-constructible (positions, faces) pair for tests that must supply SOME
#: geometry to satisfy `edge_flicker_cap > 0`'s requirement but never actually exercise the
#: coverage probe (no flicker candidate exists in that scenario, so it is never ray-cast).
_DUMMY_GEOMETRY = (np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), np.array([[0, 1, 2]], np.int64))


def _flicker_report(drop, cap, strict=True, geometry=None):
    before, after = _buffers(_block()), _buffers(_block(drop))
    mat = np.zeros(1, np.int64)
    kw = {} if geometry is None else {"geometry_before": geometry, "geometry_after": geometry}
    return compare_views([(_FLICKER_VIEW, before)], [(_FLICKER_VIEW, after)], mat, mat,
                          frozenset({0}), 0.15, strict=strict, edge_flicker_cap=cap,
                          allow_depth_fallback=True, **kw)  # synthetic buffers: there is no real geometry


def test_silhouette_pixel_is_classed_edge_flicker_and_fails_at_cap_zero():
    before, after = _buffers(_block()), _buffers(_block(drop=[(25, 25)]))
    mat = np.zeros(1, np.int64)

    codes = classify_pixels(before.depth, before.tri, after.depth, after.tri, mat, mat,
                             frozenset({0}), 0.15, allow_depth_fallback=True)
    assert int((codes == PX_EDGE_FLICKER).sum()) == 1
    assert int((codes == PX_HOLE).sum()) == 0

    report = _flicker_report([(25, 25)], cap=0.0)  # cap 0.0 needs no geometry
    assert report.totals["edge_flicker"] == 1 and report.totals["holes"] == 0
    assert report.views[0].edge_flicker == 1
    assert not report.passed  # the default cap fails a flicker pixel exactly like a hole


def test_edge_flicker_cap_above_zero_without_geometry_is_an_error():
    """A would-be hole is only ever classed flicker by the 3x3 neighbourhood test when no
    geometry is given, and that test alone cannot tell a real hole from the silhouette -- safe
    only when every flicker pixel fails anyway, i.e. cap 0.0. A caller asking for tolerance
    without supplying the geometry the coverage check needs gets an error, not a silent guess."""
    with pytest.raises(ValueError) as excinfo:
        _flicker_report([(25, 25)], cap=1e-4)
    assert "geometry" in str(excinfo.value)
    assert "edge_flicker_cap" in str(excinfo.value)

    # cap 0.0 is unaffected -- still no geometry required
    _flicker_report([(25, 25)], cap=0.0)
    # geometry supplied (even a placeholder never actually ray-cast here) lifts the error
    _flicker_report([(25, 25)], cap=1e-4, geometry=_DUMMY_GEOMETRY)


def test_interior_hole_fails_at_any_cap():
    before, after = _buffers(_block()), _buffers(_block(drop=[(100, 100)]))
    mat = np.zeros(1, np.int64)
    codes = classify_pixels(before.depth, before.tri, after.depth, after.tri, mat, mat,
                             frozenset({0}), 0.15, allow_depth_fallback=True)
    assert int((codes == PX_HOLE).sum()) == 1 and int((codes == PX_EDGE_FLICKER).sum()) == 0

    for cap in (0.0, 1e-4, 1.0):
        # not on the 3x3 silhouette, so never a flicker candidate -- the coverage probe geometry
        # (required for cap > 0) is never actually ray-cast in this scenario.
        report = _flicker_report([(100, 100)], cap=cap, geometry=_DUMMY_GEOMETRY if cap > 0 else None)
        assert report.totals["holes"] == 1 and report.totals["edge_flicker"] == 0
        assert not report.passed


# ---------------------------------------------------------------------------
# compare.py: flicker also needs a sub-pixel coverage check
# ---------------------------------------------------------------------------

_FLAT_VIEW = (0.0, 0.0, -1.0)  # head-on at the z = 0 plane, so `right` is +x and `up` is +y
_FRAME = np.array([[-100.0, -100.0, 0.0], [100.0, -100.0, 0.0],
                    [100.0, 100.0, 0.0], [-100.0, 100.0, 0.0]])
_COVER_SIZE = (64, 64)
_QUAD = np.array([[0, 1, 2], [0, 2, 3]], np.int64)


def _camera():
    """The camera `_FRAME` gives at `_COVER_SIZE`, with no geometry at all: `xs` and `ys` are the
    x and y of every pixel centre, so a test can place geometry ON a pixel centre."""
    return ortho_first_hit(_FRAME, np.zeros((0, 3), np.int64), np.zeros(0, np.int64),
                            _FLAT_VIEW, _FRAME, _COVER_SIZE)


def test_a_thousandth_of_an_inch_of_boundary_shift_is_edge_flicker():
    """A real silhouette: the plate's right boundary moves 0.001 in and flips the one pixel whose
    centre it passes through. 1 of 25 sub-rays changes -- 0.04 <= 2/25 -- so it is flicker."""
    cam = _camera()
    c, r = 40, 26
    x0, y0 = float(cam.xs[c]), float(cam.ys[r])
    k = 0.037  # tilt the boundary off the pixel lattice, so it crosses ONE sub-ray, not a column

    def plate(offset):
        return np.array([[-60.0, -60.0, 0.0],
                          [x0 + k * (-60.0 - y0) + offset, -60.0, 0.0],
                          [x0 + k * (60.0 - y0) + offset, 60.0, 0.0],
                          [-60.0, 60.0, 0.0]])

    P_before, P_after = plate(+0.0005), plate(-0.0005)
    ids = np.arange(2)
    before = ortho_first_hit(P_before, _QUAD, ids, _FLAT_VIEW, _FRAME, _COVER_SIZE)
    after = ortho_first_hit(P_after, _QUAD, ids, _FLAT_VIEW, _FRAME, _COVER_SIZE)

    flipped = (before.tri >= 0) & (after.tri < 0)
    assert int(flipped.sum()) == 1 and flipped[r, c]

    mat = np.zeros(2, np.int64)
    kw = dict(strict=True, plane_before=face_planes(P_before, _QUAD), plane_after=face_planes(P_after, _QUAD),
              geometry_before=(P_before, _QUAD), geometry_after=(P_after, _QUAD))
    report = compare_views([(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat, mat, frozenset({0}), 0.15, **kw)

    assert report.totals["edge_flicker"] == 1 and report.totals["holes"] == 0
    assert report.passed is False  # still fails at the default cap of 0.0

    # cap tolerance, with the real geometry `edge_flicker_cap > 0` now requires: 1 flicker pixel
    # of 949 model pixels -- a cap just above 1/949 tolerates it, one just below does not.
    model_px = int((before.tri >= 0).sum())
    assert model_px == 949
    above = compare_views([(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat, mat, frozenset({0}),
                           0.15, edge_flicker_cap=2e-3, **kw)
    assert above.totals["edge_flicker"] == 1 and above.passed is True
    below = compare_views([(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat, mat, frozenset({0}),
                           0.15, edge_flicker_cap=5e-4, **kw)
    assert below.totals["edge_flicker"] == 1 and below.passed is False


def test_compare_views_refuses_renders_from_a_different_camera_frame():
    """Every displacement is measured from the BEFORE buffer's ray origins, for BOTH hit points.
    A caller who framed AFTER on a different bounding box (or at a different image size) gets
    silently wrong numbers, so the whole camera frame has to match, not just the direction."""
    m = cube(10.0)
    Pc = m.positions - 5.0
    faces, ids = m.face_v, np.arange(len(m.face_v))
    view = VIEWS_26[0]
    mat = m.face_material
    planes = face_planes(Pc, faces)
    before = ortho_first_hit(Pc, faces, ids, view, Pc, _SIZE)

    def compare(after):
        return compare_views([(view, before)], [(view, after)], mat, mat, frozenset(), 0.15,
                              plane_before=planes, plane_after=planes)

    for after in (ortho_first_hit(Pc, faces, ids, view, Pc * 2.0, _SIZE),   # other bounding box
                   ortho_first_hit(Pc, faces, ids, view, Pc, (60, 40))):    # other image size
        with pytest.raises(ValueError) as excinfo:
            compare(after)
        assert "camera frame" in str(excinfo.value)
        assert str(tuple(view)) in str(excinfo.value)  # which view, by name

    assert compare(ortho_first_hit(Pc, faces, ids, view, Pc, _SIZE)).passed  # same frame: fine


def _gap_scene():
    """A wall at x in [-60, -10] and a 2-pixel-wide strip at x in [10, 16.5], both z = 0, with a
    20 in PRE-EXISTING gap between them. AFTER drops the strip entirely: every one of its pixels
    has a miss in its 3x3 BEFORE neighbourhood (the gap on one side, background on the other), so
    the 3x3 test alone calls all of them flicker."""
    P = np.array([[-60.0, -60.0, 0.0], [-10.0, -60.0, 0.0], [-10.0, 60.0, 0.0], [-60.0, 60.0, 0.0],
                   [10.0, -60.0, 0.0], [16.5, -60.0, 0.0], [16.5, 60.0, 0.0], [10.0, 60.0, 0.0]])
    faces_before = np.vstack([_QUAD, _QUAD + 4])
    faces_after = faces_before[:2]
    before = ortho_first_hit(P, faces_before, np.arange(4), _FLAT_VIEW, _FRAME, _COVER_SIZE)
    after = ortho_first_hit(P, faces_after, np.arange(2), _FLAT_VIEW, _FRAME, _COVER_SIZE)
    return P, faces_before, faces_after, before, after


def test_a_removed_face_beside_a_pre_existing_gap_is_a_hole_at_any_cap():
    P, faces_before, faces_after, before, after = _gap_scene()
    cam = _camera()
    cols = np.nonzero((cam.xs > 10.0) & (cam.xs < 16.5))[0]
    strip_px = np.zeros(before.tri.shape, bool)
    strip_px[:, cols] = before.tri[:, cols] >= 0
    removed = int(strip_px.sum())
    assert removed > 0 and int(((before.tri >= 0) & (after.tri < 0)).sum()) == removed

    mat = np.zeros(4, np.int64)
    planes = face_planes(P, faces_before)
    kw = dict(strict=True, plane_before=planes, plane_after=face_planes(P, faces_after))

    # the 3x3 test ALONE cannot tell this from a silhouette (every pixel would be tolerated at a
    # cap), which is exactly why a nonzero cap without geometry is now a hard error rather than a
    # silent wrong answer.
    with pytest.raises(ValueError, match="geometry"):
        compare_views([(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat, mat, frozenset({0}),
                       0.15, edge_flicker_cap=1.0, **kw)

    # with the sub-pixel coverage check, 25 of 25 sub-rays are lost: a hole at every cap
    for cap in (0.0, 1e-4, 1.0):
        report = compare_views([(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat, mat,
                                frozenset({0}), 0.15, edge_flicker_cap=cap,
                                geometry_before=(P, faces_before), geometry_after=(P, faces_after),
                                **kw)
        assert report.totals["holes"] == removed and report.totals["edge_flicker"] == 0
        assert report.passed is False


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


def test_guard_feedback_reuses_one_caster_per_geometry_not_per_view():
    """Task 7 perf fix: a caster is built once for the BEFORE render (26 views, one `faces`
    array) and once per round's AFTER render (26 views, one `keep_faces` array each) -- not once
    per view. Results (the mask) must stay exactly what they were before this optimisation."""
    from engine.rays.caster import EmbreeCaster

    m = box_with_partition()
    topo, Pc = _centered_topo(m)
    faces = topo.face_w
    depth_tol = _depth_tol(topo)
    candidates = np.zeros(len(faces), dtype=bool)
    candidates[[12, 13]] = True
    candidates[0] = True  # forces at least 2 rounds (round 0 restores face 0)

    builds = []

    class CountingCaster(EmbreeCaster):
        def __init__(self, positions, faces_):
            builds.append(1)
            super().__init__(positions, faces_)

    mask, history = guard_feedback(candidates, Pc, faces, m.face_material, frozenset(), depth_tol,
                                    strict=True, views=VIEWS_26, size=_SIZE,
                                    caster_factory=CountingCaster)

    assert len(history) >= 2
    assert len(builds) == 1 + len(history)  # 1 for BEFORE, 1 per round's AFTER -- never 26x that
    assert mask.tolist() == [i in (12, 13) for i in range(len(faces))]


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
                             frozenset(), _depth_tol(topo), allow_depth_fallback=True)

    out = tmp_path / "diff.png"
    save_triptych(out, before, after, codes)

    assert out.exists()
    from PIL import Image
    img = np.array(Image.open(out))
    assert img.shape == (30, 40 * 3, 3)


def _face_normals(positions, faces):
    tri = positions[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(n, axis=1)
    out = np.zeros_like(n)
    safe = length > 0
    out[safe] = n[safe] / length[safe, None]
    return out


def test_save_triptych_shades_before_and_after_panels_by_face_normal(tmp_path):
    """Task 7 fix: with normals given, BEFORE/AFTER panels are Lambert-shaded (not flat grey), so
    two differently-oriented but equally-hit faces render as different pixel colours."""
    m = box_with_partition()
    topo, Pc = _centered_topo(m)
    faces, ids = topo.face_w, np.arange(len(topo.face_w))
    view = VIEWS_26[0]
    size = (60, 40)
    before = ortho_first_hit(Pc, faces, ids, view, Pc, size=size)
    after = ortho_first_hit(Pc, faces, ids, view, Pc, size=size)
    codes = classify_pixels(before[0], before[1], after[0], after[1], m.face_material, m.face_material,
                             frozenset(), _depth_tol(topo), allow_depth_fallback=True)
    normals = _face_normals(Pc, faces)

    flat_out = tmp_path / "flat.png"
    shaded_out = tmp_path / "shaded.png"
    save_triptych(flat_out, before, after, codes)
    save_triptych(shaded_out, before, after, codes, normals_before=normals, normals_after=normals)

    from PIL import Image
    flat_img = np.array(Image.open(flat_out))
    shaded_img = np.array(Image.open(shaded_out))
    assert flat_img.shape == shaded_img.shape
    w = size[0]
    # BEFORE panel (first third) differs once shading is applied -- it is no longer flat grey.
    assert not np.array_equal(flat_img[:, :w], shaded_img[:, :w])
    # the AFTER panel (second third) is identical to BEFORE here (before == after geometry), and
    # both got the SAME per-face shading, so panel 1 and panel 2 of the shaded image also match.
    assert np.array_equal(shaded_img[:, :w], shaded_img[:, w:2 * w])
    hit = np.isfinite(before[0])
    if hit.any():
        # a shaded model pixel is not simply the flat grey model colour.
        assert not np.array_equal(shaded_img[:, :w][hit], flat_img[:, :w][hit])


def test_save_triptych_diff_panel_is_unaffected_by_shading():
    """The DIFF panel stays a flat, light-grey model with red/amber overlays regardless of
    whether normals are supplied -- shading only applies to BEFORE/AFTER."""
    m = box_with_partition()
    topo, Pc = _centered_topo(m)
    faces, ids = topo.face_w, np.arange(len(topo.face_w))
    view = VIEWS_26[0]
    size = (60, 40)
    before = ortho_first_hit(Pc, faces, ids, view, Pc, size=size)
    after = ortho_first_hit(Pc, faces, ids, view, Pc, size=size)
    codes = classify_pixels(before[0], before[1], after[0], after[1], m.face_material, m.face_material,
                             frozenset(), _depth_tol(topo), allow_depth_fallback=True)
    normals = _face_normals(Pc, faces)

    import tempfile
    from pathlib import Path
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp:
        p1, p2 = Path(tmp) / "a.png", Path(tmp) / "b.png"
        save_triptych(p1, before, after, codes)
        save_triptych(p2, before, after, codes, normals_before=normals, normals_after=normals)
        img1, img2 = np.array(Image.open(p1)), np.array(Image.open(p2))
        w = size[0]
        assert np.array_equal(img1[:, 2 * w:], img2[:, 2 * w:])
