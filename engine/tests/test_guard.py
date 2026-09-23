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
                              "moved_same_flat": 0, "moved_other": 0, "zfight_tie": 0,
                              "crack_closed": 0, "edge_flicker": 0, "edge_flicker_hole": 0,
                              "edge_flicker_moved": 0, "edge_flicker_material": 0}
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


def test_a_would_be_hole_is_never_flicker_without_the_geometry_to_ring_test_it():
    """Flicker is decided by casting a RING of rays around the pixel in both geometries, so with
    no geometry to cast against there is no evidence and a would-be hole stays a hole -- even on
    the silhouette, where the old 3x3-neighbourhood precondition alone used to call it flicker.

    `guard_feedback` depends on this: it casts no ring (a removal is not a change a person
    accepted), and every failing pixel there must keep failing."""
    before, after = _buffers(_block()), _buffers(_block(drop=[(25, 25)]))
    mat = np.zeros(1, np.int64)

    codes = classify_pixels(before.depth, before.tri, after.depth, after.tri, mat, mat,
                             frozenset({0}), 0.15, allow_depth_fallback=True)
    assert int((codes == PX_HOLE).sum()) == 1
    assert int((codes == PX_EDGE_FLICKER).sum()) == 0

    report = _flicker_report([(25, 25)], cap=0.0)  # cap 0.0 needs no geometry
    assert report.totals["holes"] == 1 and report.totals["edge_flicker"] == 0
    assert report.views[0].holes == 1
    assert not report.passed


def test_edge_flicker_cap_above_zero_without_geometry_is_an_error():
    """Without both geometries there is no ring to cast, so nothing is ever classed flicker and
    a nonzero cap would silently tolerate nothing while looking as though it tolerated something.
    A caller asking for tolerance without supplying the geometry the ring test needs gets an
    error, not a silent guess."""
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
# compare.py: flicker is a RING test at the merge's own bound
#
# Every would-be failure pixel (hole, moved_same_flat, moved_other, material_changed) is
# re-checked by casting 16 rays around it in the image plane -- 8 at `depth_tol`, 8 at
# `depth_tol / 2` -- in BOTH geometries. It is flicker only when an AFTER ring ray reproduces
# BEFORE's centre verdict AND a BEFORE ring ray reproduces AFTER's. That is exactly the bound
# the merge works to (dropping a nearly-collinear ring vertex moves a boundary by at most the
# collinearity tolerance), and unlike the old 3x3 + 5x5-coverage rule it works at an INTERNAL
# silhouette, where a boundary shift swaps one real surface for another rather than for sky.
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
    """An EXTERNAL silhouette: the plate's right boundary moves 0.001 in (far under the 0.15
    `depth_tol`) and flips the one pixel whose centre it passes through. An AFTER ring ray just
    inside the boundary still hits the plate (BEFORE's centre verdict) and a BEFORE ring ray just
    outside it still misses (AFTER's centre verdict), so it is flicker -- an `edge_flicker_hole`,
    since the base class it was rescued from was a hole."""
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
    assert report.totals["edge_flicker_hole"] == 1          # rescued from PX_HOLE, not from a move
    assert report.totals["edge_flicker_moved"] == 0 and report.totals["edge_flicker_material"] == 0
    assert report.views[0].edge_flicker == 1 and report.views[0].edge_flicker_hole == 1
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


# --- an INTERNAL silhouette: one real surface in front of another, no sky anywhere ----------

_BIG_SIZE = (128, 128)   #: ~13,700 model px, so `edge_flicker_cap = 1e-4` tolerates one of them
_SLAB = 95.0             #: the slabs nearly fill `_FRAME`: the cap is a FRACTION of model_px
_STACK_GAP = 10.0        #: how far the upper slab floats over the lower one (>> any depth_tol here)


def _big_camera():
    """The camera `_FRAME` gives at `_BIG_SIZE`, with no geometry: `xs`/`ys` are the x and y of
    every pixel centre, so a test can straddle a chosen pixel with a moving boundary."""
    return ortho_first_hit(_FRAME, np.zeros((0, 3), np.int64), np.zeros(0, np.int64),
                            _FLAT_VIEW, _FRAME, _BIG_SIZE)


def _stacked(edge_x, y_lo, y_hi, upper_material):
    """A lower slab at `z = 0` (material 0, faces 0-1) with an upper slab at `z = _STACK_GAP`
    (faces 2-3) laid over it, covering `x <= edge_x` between `y_lo` and `y_hi`.

    Seen from straight above, `x = edge_x` is an INTERNAL silhouette: on one side the ray meets
    the upper slab, on the other the lower one `_STACK_GAP` further away. No pixel anywhere in
    the image is background, which is precisely the case the old rule's 3x3-neighbourhood
    precondition could not recognise. Returns `(positions, faces, face_material, rendered)`."""
    z = _STACK_GAP
    P = np.array([[-_SLAB, -_SLAB, 0.0], [_SLAB, -_SLAB, 0.0], [_SLAB, _SLAB, 0.0], [-_SLAB, _SLAB, 0.0],
                   [-_SLAB, y_lo, z], [edge_x, y_lo, z], [edge_x, y_hi, z], [-_SLAB, y_hi, z]])
    faces = np.vstack([_QUAD, _QUAD + 4])
    mat = np.array([0, 0, upper_material, upper_material], np.int64)
    return P, faces, mat, ortho_first_hit(P, faces, np.arange(4), _FLAT_VIEW, _FRAME, _BIG_SIZE)


def _stacked_pair(shift, upper_material=0, one_row=True):
    """A BEFORE/AFTER pair of `_stacked` scenes whose edge moves by `shift`, straddling the centre
    of one chosen pixel, plus everything `compare_views` needs for them.

    With `one_row` the upper slab is only 0.8 of a pixel tall, so the moving edge can flip exactly
    ONE pixel and no other -- neighbouring rows have no upper slab at all and neighbouring columns
    are a whole pixel pitch away from the band. Without it the slab spans the full height, so a
    band `shift` wide flips a whole column's worth of pixels."""
    cam = _big_camera()
    row, col = 64, 90
    x0, y0 = float(cam.xs[col]), float(cam.ys[row])
    pitch = abs(float(cam.ys[1] - cam.ys[0]))
    y_lo, y_hi = (y0 - 0.4 * pitch, y0 + 0.4 * pitch) if one_row else (-_SLAB, _SLAB)
    Pb, faces, mat, before = _stacked(x0 + shift / 2.0, y_lo, y_hi, upper_material)
    Pa, _, _, after = _stacked(x0 - shift / 2.0, y_lo, y_hi, upper_material)
    kw = dict(strict=True, plane_before=face_planes(Pb, faces), plane_after=face_planes(Pa, faces),
               geometry_before=(Pb, faces), geometry_after=(Pa, faces))
    return (row, col), mat, before, after, kw


def _stacked_report(mat, before, after, kw, cap, flat=frozenset({0})):
    return compare_views([(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat, mat, flat, 0.15,
                          edge_flicker_cap=cap, **kw)


def _swapped(before, after):
    """Pixels that met the upper slab (faces 2-3) in BEFORE and the lower one in AFTER."""
    return (before.tri >= 2) & (after.tri >= 0) & (after.tri < 2)


def test_boundary_shift_under_tolerance_at_an_internal_silhouette_is_edge_flicker():
    """The upper slab's boundary moves 0.1 in -- under the 0.15 `depth_tol` a merge works to --
    and the one pixel whose centre it straddles swaps a surface for another 10 in behind it. No
    pixel in the image is background, so the OLD rule (a miss in the 3x3 neighbourhood, then a
    5x5 sub-ray coverage vote) could never call this flicker. The ring test can: an AFTER ring ray
    0.075 in to the left still lands on the upper slab, and a BEFORE ring ray 0.075 in to the
    right already lands on the lower one."""
    (row, col), mat, before, after, kw = _stacked_pair(0.1)

    swapped = _swapped(before, after)
    assert int(swapped.sum()) == 1 and swapped[row, col]      # exactly the pixel we aimed at

    report = _stacked_report(mat, before, after, kw, cap=0.0)
    assert report.totals["edge_flicker"] == 1
    assert report.totals["edge_flicker_moved"] == 1
    assert report.totals["edge_flicker_hole"] == 0 and report.totals["edge_flicker_material"] == 0
    assert report.totals["moved_same_flat"] == 0 and report.totals["holes"] == 0
    assert report.passed is False                              # cap 0.0 fails it like a hole

    # the final merge guard's own cap: 1 flicker pixel of ~13,700 model pixels is under 1e-4
    tolerant = _stacked_report(mat, before, after, kw, cap=1e-4)
    assert tolerant.totals["model_px"] * 1e-4 >= 1.0
    assert tolerant.totals["edge_flicker"] == 1 and tolerant.passed is True


def test_a_material_boundary_shift_under_tolerance_is_edge_flicker_material():
    """The same 0.1 in shift with the upper slab in a DIFFERENT material: the pixel's base class
    is `material_changed`, not a move, and the breakdown says which it was rescued from."""
    (row, col), mat, before, after, kw = _stacked_pair(0.1, upper_material=1)

    strict = _stacked_report(mat, before, after, kw, cap=0.0, flat=frozenset({0, 1}))
    assert strict.totals["edge_flicker"] == 1
    assert strict.totals["edge_flicker_material"] == 1
    assert strict.totals["edge_flicker_moved"] == 0 and strict.totals["edge_flicker_hole"] == 0
    assert strict.totals["material_changed"] == 0
    assert strict.passed is False

    tolerant = _stacked_report(mat, before, after, kw, cap=1e-4, flat=frozenset({0, 1}))
    assert tolerant.totals["edge_flicker_material"] == 1 and tolerant.passed is True


def test_a_boundary_shift_far_beyond_tolerance_stays_a_failure_at_any_cap():
    """2 in is more than `2 * depth_tol`, so no ring ray of either geometry reaches across it:
    every swapped pixel keeps its real class and fails at every cap. The ring rule tolerates a
    boundary that barely moved, never a boundary that actually moved."""
    (row, col), mat, before, after, kw = _stacked_pair(2.0, one_row=False)

    swapped = int(_swapped(before, after).sum())
    assert swapped > 100          # a 2 in band down the whole slab, not one pixel

    for cap in (0.0, 1e-4, 1.0):
        report = _stacked_report(mat, before, after, kw, cap=cap)
        assert report.totals["edge_flicker"] == 0
        assert report.totals["moved_same_flat"] == swapped
        assert report.passed is False


# ---------------------------------------------------------------------------
# R2d: only a base class that FAILS under the current strictness is ever promoted.
#
# Measured regression: a `--accept-slit` run is judged with `strict=False`, where
# `moved_same_flat` is reported but tolerated. 991 such pixels were nevertheless fed to the ring
# test, 15 of them came back `edge_flicker`, and `edge_flicker` IS capped -- 15 pixels in a 9,291
# px view against a 1e-4 cap (0.93 px allowed) failed a run that passed before. A tolerated base
# class must keep its class and never be counted against `edge_flicker_cap`.
# ---------------------------------------------------------------------------

def test_a_tolerated_moved_same_flat_pixel_is_never_promoted_to_flicker():
    """The same sub-tolerance boundary shift at an internal silhouette, judged both ways. With
    `strict=True` the pixel's base class (`moved_same_flat`) fails, so it is a flicker candidate
    and the ring rescues it. With `strict=False` that class is already tolerated: it stays
    `moved_same_flat`, is never promoted, and cannot be capped -- so the view passes even at the
    zero cap, where a flicker pixel would fail like a hole."""
    (row, col), mat, before, after, kw = _stacked_pair(0.1)
    assert kw["strict"] is True

    strict = _stacked_report(mat, before, after, kw, cap=0.0)
    assert strict.totals["edge_flicker"] == 1 and strict.totals["moved_same_flat"] == 0
    assert strict.passed is False

    tolerant = _stacked_report(mat, before, after, {**kw, "strict": False}, cap=0.0)
    assert tolerant.totals["edge_flicker"] == 0
    assert tolerant.totals["edge_flicker_moved"] == 0
    assert tolerant.totals["moved_same_flat"] == 1
    assert tolerant.views[0].moved_same_flat == 1 and tolerant.views[0].edge_flicker == 0
    assert tolerant.passed is True


def test_a_failing_base_class_is_still_promoted_when_not_strict():
    """The gate is the base class's own verdict under the current strictness, not strictness
    itself: `material_changed` fails whether or not `strict`, so a material boundary that moved
    under tolerance is still rescued by the ring in a non-strict report."""
    (row, col), mat, before, after, kw = _stacked_pair(0.1, upper_material=1)

    report = _stacked_report(mat, before, after, {**kw, "strict": False}, cap=1e-4,
                              flat=frozenset({0, 1}))
    assert report.totals["edge_flicker"] == 1 and report.totals["edge_flicker_material"] == 1
    assert report.totals["material_changed"] == 0
    assert report.passed is True


# ---------------------------------------------------------------------------
# M4: a z-fight tie is not damage.
#
# Measured on file B, view (1.013, 1.007, 0.011): 12 `material_changed` pixels where BEFORE hits
# face 2654 (material 1) and AFTER hits face 73 (material 0) at the SAME depth, 5867.73 in, and
# NEITHER face was removed. They are overlapping faces in one plane with different materials -- a
# real defect, but not one this run caused; rebuilding the ray structure over a different face set
# just changed which of the two wins the tie.
# ---------------------------------------------------------------------------

#: Two exactly coincident quads at z = 0, faces 0-1 and 2-3, so every ray through them meets both
#: at the same depth and a first-hit cast picks one arbitrarily.
_TWIN = np.vstack([_QUAD, _QUAD])
_TWIN_FRAME = np.array([[-60.0, -60.0, 0.0], [60.0, -60.0, 0.0],
                         [60.0, 60.0, 0.0], [-60.0, 60.0, 0.0]])


def _twin_render(faces, ids):
    return ortho_first_hit(_TWIN_FRAME, faces, ids, _FLAT_VIEW, _FRAME, _COVER_SIZE)


def _twin_report(before, after, mat_before, mat_after, faces_before, faces_after, cap=0.0,
                  strict=True, flat=frozenset({0, 1})):
    return compare_views(
        [(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat_before, mat_after, flat, 0.15,
        strict=strict, edge_flicker_cap=cap,
        plane_before=face_planes(_TWIN_FRAME, faces_before),
        plane_after=face_planes(_TWIN_FRAME, faces_after),
        geometry_before=(_TWIN_FRAME, faces_before), geometry_after=(_TWIN_FRAME, faces_after))


def test_overlapping_coplanar_faces_of_different_materials_are_a_zfight_tie():
    """AFTER is the SAME geometry with the face order reversed, which is enough to flip which of
    the two coincident quads embree returns first. Every model pixel changes material and not one
    of them is damage: both faces are still there, at the same depth, in both meshes."""
    mat_before = np.array([0, 0, 1, 1], np.int64)
    faces_after, mat_after = _TWIN[::-1].copy(), mat_before[::-1].copy()
    before = _twin_render(_TWIN, np.arange(4))
    after = _twin_render(faces_after, np.arange(4))

    model = before.tri >= 0
    assert model.sum() > 100
    # the fixture only means something if the winner really flipped
    assert (mat_before[before.tri[model]] != mat_after[after.tri[model]]).all()

    report = _twin_report(before, after, mat_before, mat_after, _TWIN, faces_after)
    assert report.totals["zfight_tie"] == int(model.sum())
    assert report.totals["material_changed"] == 0 and report.totals["edge_flicker"] == 0
    assert report.views[0].zfight_tie == int(model.sum())
    assert report.passed is True
    for cap in (0.0, 1e-4, 1.0):     # never a failure at any cap
        assert _twin_report(before, after, mat_before, mat_after, _TWIN, faces_after,
                             cap=cap).passed is True


def test_a_zfight_member_that_was_removed_is_still_a_material_change():
    """Drop whichever quad won in BEFORE. AFTER's first hit is still a member of BEFORE's tie
    set, but BEFORE's first hit is NOT a member of AFTER's -- it is gone. The rule is tested in
    both directions precisely so a removed member stays a failure."""
    mat_before = np.array([0, 0, 1, 1], np.int64)
    before = _twin_render(_TWIN, np.arange(4))
    model = before.tri >= 0
    winner = int(np.bincount(before.tri[model]).argmax())
    keep = np.array([f for f in range(4) if mat_before[f] != mat_before[winner]], np.int64)
    faces_after, mat_after = _TWIN[keep], mat_before[keep]
    after = _twin_render(faces_after, np.arange(len(keep)))

    assert (after.tri[model] >= 0).all()
    assert (mat_after[after.tri[model]] != mat_before[before.tri[model]]).all()

    report = _twin_report(before, after, mat_before, mat_after, _TWIN, faces_after)
    assert report.totals["zfight_tie"] == 0
    assert report.totals["material_changed"] == int(model.sum())
    assert report.passed is False


def test_a_coincident_same_material_pair_losing_one_member_is_no_change_at_all():
    """The same overlap in ONE material: losing a member changes nothing a ray can see, so the
    tie machinery is not even needed -- every pixel is plain `PX_OK`."""
    mat_before = np.zeros(4, np.int64)
    faces_after, mat_after = _TWIN[:2], mat_before[:2]
    before = _twin_render(_TWIN, np.arange(4))
    after = _twin_render(faces_after, np.arange(2))

    report = _twin_report(before, after, mat_before, mat_after, _TWIN, faces_after,
                           flat=frozenset({0}))
    assert {k: v for k, v in report.totals.items() if k != "model_px"} \
        == {k: 0 for k in report.totals if k != "model_px"}
    assert report.totals["model_px"] > 100
    assert report.passed is True


# ---------------------------------------------------------------------------
# M5: a closed crack is an improvement, not damage.
#
# Measured on file A, view (-0.987, 0.007, -0.989), pixel (530, 338) -- the ONLY pixel that rolled
# the merge back. BEFORE's centre ray slipped through a T-junction crack about 0.02 in wide (2 of
# 201 rays at 0.02 in steps reached the ramp face 2540 at t = 3318.66) while 14 of its 16 ring rays
# already met the region surface 16.3 in nearer. The merge closed the crack. That is the fix this
# project exists for, so the guard must not call it damage.
# ---------------------------------------------------------------------------

_CRACK_GAP = 0.02        #: crack width, measured along x -- the width measured on file A
_CRACK_SLOPE = 0.4       #: the crack runs along x = x0 + 0.4 * (y - y0), so it is not parallel to
                         #: any of the ring's 8 angles: every ring ray clears a 0.02 in gap.


def _crack_scene(row=64, col=70):
    """A lower surface `_STACK_GAP` behind an upper slab of two big triangles split by a
    `_CRACK_GAP`-wide crack, aimed so the crack passes exactly through pixel `(row, col)`'s own
    ray. `(positions, faces_before, faces_after_closed, faces_after_torn)` -- `faces` are
    `[upper, upper, lower, lower]`, so `tri >= 2` means the ray fell through to the lower surface.

    AFTER-closed re-triangulates the upper slab as ONE quad with no crack at all (what a merge
    does); AFTER-torn drops the whole first upper triangle (real damage, same scene)."""
    cam = _big_camera()
    x0, y0 = float(cam.xs[col]), float(cam.ys[row])
    h = _CRACK_GAP / 2.0

    def edge(y, side):
        return x0 + _CRACK_SLOPE * (y - y0) + side * h

    z = -_STACK_GAP
    P = np.array([
        [edge(-500.0, +1), -500.0, 0.0], [edge(500.0, +1), 500.0, 0.0], [x0 + 3000.0, -500.0, 0.0],
        [edge(-500.0, -1), -500.0, 0.0], [edge(500.0, -1), 500.0, 0.0], [x0 - 3000.0, 500.0, 0.0],
        [-500.0, -500.0, z], [500.0, -500.0, z], [500.0, 500.0, z], [-500.0, 500.0, z],
        [-500.0, -500.0, 0.0], [500.0, -500.0, 0.0], [500.0, 500.0, 0.0], [-500.0, 500.0, 0.0],
    ])
    lower = np.array([[6, 7, 8], [6, 8, 9]], np.int64)
    merged = np.array([[10, 11, 12], [10, 12, 13]], np.int64)
    before = np.vstack([[[0, 1, 2], [3, 4, 5]], lower])
    closed = np.vstack([merged, lower])
    torn = np.vstack([[[3, 4, 5]], lower])   # the first upper triangle is gone: tri >= 1 is lower
    return P, before, closed, torn


def _crack_report(P, faces_before, faces_after, before, after, cap=0.0, strict=True):
    mat_b = np.zeros(len(faces_before), np.int64)
    mat_a = np.zeros(len(faces_after), np.int64)
    return compare_views(
        [(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat_b, mat_a, frozenset(), 0.15,
        strict=strict, edge_flicker_cap=cap,
        plane_before=face_planes(P, faces_before), plane_after=face_planes(P, faces_after),
        geometry_before=(P, faces_before), geometry_after=(P, faces_after))


def test_a_crack_the_merge_closed_is_reported_as_crack_closed_and_passes():
    """BEFORE's centre ray falls through the crack to the surface 10 in behind; AFTER's meets the
    re-triangulated slab. Its base class is a real `moved_other`, and its own 16 BEFORE ring rays
    -- every one of which clears a 0.02 in crack at this slope -- already saw AFTER's surface.
    That is a crack the merge closed, not a surface it lost."""
    P, faces_before, faces_closed, _ = _crack_scene()
    before = ortho_first_hit(P, faces_before, np.arange(4), _FLAT_VIEW, _FRAME, _BIG_SIZE)
    after = ortho_first_hit(P, faces_closed, np.arange(4), _FLAT_VIEW, _FRAME, _BIG_SIZE)

    # the crack runs at 2/5, and the pixel pitch is the same in x and y, so it passes exactly
    # through a pixel centre every 5th row: 25 of the 128 rows fall through it, not just the one
    # the fixture aimed at.
    fell_through = (before.tri >= 2) & (after.tri >= 0) & (after.tri < 2)
    assert int(fell_through.sum()) == 25

    report = _crack_report(P, faces_before, faces_closed, before, after)
    assert report.totals["crack_closed"] == 25
    assert report.views[0].crack_closed == 25
    assert report.totals["moved_other"] == 0 and report.totals["holes"] == 0
    assert report.totals["edge_flicker"] == 0 and report.totals["zfight_tie"] == 0
    assert report.passed is True
    for cap in (0.0, 1e-4, 1.0):               # never a failure at any cap
        assert _crack_report(P, faces_before, faces_closed, before, after, cap=cap).passed is True


def test_a_whole_triangle_lost_from_the_same_scene_is_still_a_failure():
    """The same slab, same crack, same lower surface -- but AFTER loses one upper triangle
    outright. Not one BEFORE ring ray reproduces AFTER's centre verdict there (they all still meet
    the slab 10 in in front of it), so nothing is rescued and every lost pixel fails at any cap."""
    P, faces_before, _, faces_torn = _crack_scene()
    before = ortho_first_hit(P, faces_before, np.arange(4), _FLAT_VIEW, _FRAME, _BIG_SIZE)
    after = ortho_first_hit(P, faces_torn, np.arange(3), _FLAT_VIEW, _FRAME, _BIG_SIZE)

    lost = (before.tri == 0) & (after.tri >= 1)   # AFTER's tri 0 is the surviving upper triangle
    assert int(lost.sum()) > 1000              # half the image, not a boundary pixel

    for cap in (0.0, 1e-4, 1.0):
        report = _crack_report(P, faces_before, faces_torn, before, after, cap=cap)
        assert report.totals["crack_closed"] == 0
        assert report.totals["moved_other"] == int(lost.sum())
        assert report.totals["edge_flicker"] == 0 and report.totals["zfight_tie"] == 0
        assert report.passed is False


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
