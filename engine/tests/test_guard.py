import itertools

import numpy as np
import pytest

from engine.guard.compare import (PX_CRACK_CLOSED, PX_EDGE_FLICKER, PX_HOLE, PX_MATERIAL_CHANGED,
                                   PX_MOVED_OTHER, PX_MOVED_SAME_FLAT, PX_OK, PX_ZFIGHT_TIE,
                                   classify_pixels, compare_views, face_planes, guard_feedback)
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
                              "crack_closed": 0, "edge_flicker": 0, "fragment_removed": 0,
                              "edge_flicker_hole": 0,
                              "edge_flicker_moved": 0, "edge_flicker_material": 0,
                              "border_shift": 0, "grown": 0, "edge_flicker_grown": 0,
                              "grown_base": 0, "border_shift_grown": 0, "crack_closed_grown": 0,
                              "zfight_tie_grown": 0}
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


#: The REAL geometry the `_block()` picture comes from: `_buffers` puts every hit one unit along
#: +z from an origin at `(col, row, 0)`, so its hit points all lie on the plane `z = 1`, and the
#: quad below is that plane over the block's own extent (its corner pixels are 25 and 174, so its
#: boundary runs half a pixel outside them). Passing it gives the ring something true to cast
#: against, instead of a placeholder whose verdict would measure the placeholder.
#:
#: What it deliberately does NOT contain is `drop`: an individually deleted pixel is a synthetic
#: edit no real surface can express, which is exactly why no ring ray ever reproduces it and a
#: dropped pixel is never rescued here.
_BLOCK_GEOMETRY = (np.array([[24.5, 24.5, 1.0], [174.5, 24.5, 1.0],
                              [174.5, 174.5, 1.0], [24.5, 174.5, 1.0]]),
                    np.array([[0, 1, 2], [0, 2, 3]], np.int64))


def _flicker_report(drop, cap, strict=True, geometry=None):
    """`geometry` given, `compare_views` derives the planes from it and the ring, tie and crack
    tests all really run; `geometry=None` is the deliberate no-evidence case, which then needs
    `allow_depth_fallback` because there are no planes to measure displacement against."""
    before, after = _buffers(_block()), _buffers(_block(drop))
    mat = np.zeros(2, np.int64)
    kw = ({"allow_depth_fallback": True} if geometry is None
          else {"geometry_before": geometry, "geometry_after": geometry})
    return compare_views([(_FLICKER_VIEW, before)], [(_FLICKER_VIEW, after)], mat, mat,
                          frozenset({0}), 0.15, strict=strict, edge_flicker_cap=cap, **kw)


def test_a_would_be_hole_is_never_flicker_without_the_geometry_to_ring_test_it():
    """Flicker is decided by casting a RING of rays around the pixel in both geometries, so with
    no geometry to cast against there is no evidence and a would-be hole stays a hole -- on the
    silhouette as much as anywhere else.

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
    # real geometry lifts the error, and the ring it now casts finds no evidence for the pixel:
    # the block's own surface has no boundary within a ring radius of it, so a synthetically
    # dropped pixel is still a hole.
    with_geometry = _flicker_report([(25, 25)], cap=1e-4, geometry=_BLOCK_GEOMETRY)
    assert with_geometry.totals["holes"] == 1 and with_geometry.totals["edge_flicker"] == 0
    assert with_geometry.totals["crack_closed"] == 0 and with_geometry.passed is False


def test_a_cap_above_zero_builds_the_planes_the_ring_needs_from_the_geometry():
    """R2b: the ring test needs BOTH the geometry (to cast against) and the planes (to judge what
    it hit), and `compare_views` used to require a nonzero cap to come with geometry while
    silently skipping the ring when the planes were left out -- a cap that looked as though it
    tolerated something and tolerated nothing. The planes are a pure function of the geometry, so
    they are derived from it: with or without them the report is identical."""
    cam = _camera()
    c, r = 40, 26
    x0, y0 = float(cam.xs[c]), float(cam.ys[r])
    k = 0.037

    def plate(offset):
        return np.array([[-60.0, -60.0, 0.0],
                          [x0 + k * (-60.0 - y0) + offset, -60.0, 0.0],
                          [x0 + k * (60.0 - y0) + offset, 60.0, 0.0],
                          [-60.0, 60.0, 0.0]])

    P_before, P_after = plate(+0.0005), plate(-0.0005)
    ids = np.arange(2)
    before = ortho_first_hit(P_before, _QUAD, ids, _FLAT_VIEW, _FRAME, _COVER_SIZE)
    after = ortho_first_hit(P_after, _QUAD, ids, _FLAT_VIEW, _FRAME, _COVER_SIZE)
    mat = np.zeros(2, np.int64)
    geometry = dict(geometry_before=(P_before, _QUAD), geometry_after=(P_after, _QUAD))

    derived = compare_views([(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat, mat, frozenset({0}),
                             0.15, strict=True, edge_flicker_cap=2e-3, **geometry)
    supplied = compare_views([(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat, mat, frozenset({0}),
                              0.15, strict=True, edge_flicker_cap=2e-3,
                              plane_before=face_planes(P_before, _QUAD),
                              plane_after=face_planes(P_after, _QUAD), **geometry)

    assert derived.totals["edge_flicker"] == 1      # the ring really was cast
    assert derived.totals == supplied.totals
    assert derived.passed is supplied.passed is True


def test_a_cap_above_zero_with_planes_but_no_geometry_is_still_an_error():
    """Planes alone are not enough: there is nothing to cast the ring AT, so the cap would again
    tolerate nothing while looking as though it tolerated something."""
    before, after = _buffers(_block()), _buffers(_block(drop=[(25, 25)]))
    mat = np.zeros(1, np.int64)
    with pytest.raises(ValueError) as excinfo:
        compare_views([(_FLICKER_VIEW, before)], [(_FLICKER_VIEW, after)], mat, mat, frozenset({0}),
                       0.15, strict=True, edge_flicker_cap=1e-4, allow_depth_fallback=True,
                       plane_before=np.zeros((1, 4)), plane_after=np.zeros((1, 4)))
    assert "geometry" in str(excinfo.value) and "edge_flicker_cap" in str(excinfo.value)


def test_interior_hole_fails_at_any_cap():
    before, after = _buffers(_block()), _buffers(_block(drop=[(100, 100)]))
    mat = np.zeros(1, np.int64)
    codes = classify_pixels(before.depth, before.tri, after.depth, after.tri, mat, mat,
                             frozenset({0}), 0.15, allow_depth_fallback=True)
    assert int((codes == PX_HOLE).sum()) == 1 and int((codes == PX_EDGE_FLICKER).sum()) == 0

    # The same answer at every cap, with the ring really cast against the block's own surface:
    # a pixel in the middle of a slab has no boundary anywhere near it, so nothing reproduces
    # AFTER's missing centre and it is neither flicker nor a crack the fix closed.
    for cap in (0.0, 1e-4, 1.0):
        report = _flicker_report([(100, 100)], cap=cap,
                                  geometry=_BLOCK_GEOMETRY if cap > 0 else None)
        assert report.totals["holes"] == 1 and report.totals["edge_flicker"] == 0
        assert report.totals["crack_closed"] == 0 and report.totals["zfight_tie"] == 0
        assert not report.passed


# ---------------------------------------------------------------------------
# compare.py: flicker is a RING test at the merge's own bound
#
# Every would-be failure pixel (hole, moved_same_flat, moved_other, material_changed) is
# re-checked by casting 16 rays around it in the image plane -- 8 at `depth_tol`, 8 at
# `depth_tol / 2` -- in BOTH geometries. It is flicker only when an AFTER ring ray reproduces
# BEFORE's centre verdict AND a BEFORE ring ray reproduces AFTER's. That is exactly the bound
# the merge works to (dropping a nearly-collinear ring vertex moves a boundary by at most the
# collinearity tolerance), and it works at an INTERNAL silhouette, where a boundary shift swaps
# one real surface for another rather than for sky -- with no background pixel anywhere in the
# image to key off.
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
    k = 0.037  # tilt the boundary off the pixel lattice, so it crosses ONE pixel, not a column

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
    the image is background, so nothing here can be judged by looking for sky.
    Returns `(positions, faces, face_material, rendered)`."""
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
    pixel in the image is background, so there is no sky to key off: the verdict has to come from
    what the two geometries actually hold beside the pixel. An AFTER ring ray 0.075 in to the left
    still lands on the upper slab, and a BEFORE ring ray 0.075 in to the right already lands on
    the lower one -- both halves of the ring rule, so it is flicker."""
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
                  strict=True, flat=frozenset({0, 1}), crack_closed_cap=float("inf")):
    return compare_views(
        [(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat_before, mat_after, flat, 0.15,
        strict=strict, edge_flicker_cap=cap, crack_closed_cap=crack_closed_cap,
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


def _hole_scene(c0=30, c1=36, r0=26, r1=32, rim_inset=0.05):
    """A flat slab at `z = 0` with a real rectangular HOLE punched through it. BEFORE fills the
    hole (faces 0-1); AFTER is the same slab with those two triangles gone and nothing else
    changed, so the hole's whole rim is flanked by coplanar, same-material survivors.

    The hole's left edge is placed `rim_inset` (under the inner ring radius, `depth_tol / 2`) to
    the left of column `c0`'s pixel centre, so that pixel's own AFTER ring rays reach back onto
    the surviving slab: ring condition 1 -- "an AFTER ring ray reproduces BEFORE's centre verdict"
    -- genuinely holds there. Condition 2 must not: BEFORE has no miss anywhere near it.

    Returns `(positions, faces_before, faces_after, before, after, hole_px)`."""
    cam = _camera()
    hx0, hx1 = float(cam.xs[c0]) - rim_inset, float(cam.xs[c1]) + 1.0
    hy1, hy0 = float(cam.ys[r0]) + 1.0, float(cam.ys[r1]) - 1.0
    P = np.array([
        [-95.0, -95.0, 0.0], [95.0, -95.0, 0.0], [95.0, hy0, 0.0], [-95.0, hy0, 0.0],
        [-95.0, hy1, 0.0], [95.0, hy1, 0.0], [95.0, 95.0, 0.0], [-95.0, 95.0, 0.0],
        [hx0, hy0, 0.0], [hx1, hy0, 0.0], [hx1, hy1, 0.0], [hx0, hy1, 0.0],
    ])
    hole = np.array([[8, 9, 10], [8, 10, 11]], np.int64)
    rest = np.array([[0, 1, 2], [0, 2, 3],        # below the hole
                      [4, 5, 6], [4, 6, 7],        # above it
                      [3, 8, 11], [3, 11, 4],      # left of it
                      [9, 2, 5], [9, 5, 10]], np.int64)   # right of it
    faces_before = np.vstack([hole, rest])
    before = ortho_first_hit(P, faces_before, np.arange(10), _FLAT_VIEW, _FRAME, _COVER_SIZE)
    after = ortho_first_hit(P, rest, np.arange(8), _FLAT_VIEW, _FRAME, _COVER_SIZE)
    return P, faces_before, rest, before, after, (before.tri >= 0) & (before.tri < 2)


def test_an_interior_hole_flanked_by_coplanar_survivors_fails_at_any_cap():
    """The ring test needs BOTH of its halves, and this is the scene that proves it. Every rim
    pixel satisfies condition 1 -- the slab beside the hole is the same material in the same plane,
    so an AFTER ring ray reproduces BEFORE's centre verdict exactly. Condition 2 cannot hold:
    BEFORE has no miss within the ring, so nothing reproduces AFTER's. The hole stays a hole at
    every cap, and it is not a crack the fix closed either -- BEFORE's ring rays all HIT, so none
    of them reproduces AFTER's missing centre."""
    P, faces_before, faces_after, before, after, hole_px = _hole_scene()
    cam = _camera()
    assert 0.0 < float(cam.xs[30]) - float(P[8, 0]) < 0.075   # rim within the inner ring radius
    assert int(hole_px.sum()) == 49
    assert (after.tri[hole_px] < 0).all()                      # the hole really is a hole
    rows = np.unique(np.nonzero(hole_px)[0])
    assert (after.tri[rows, 29] >= 0).all()                    # flanked by surviving slab
    assert (after.tri[rows, 37] >= 0).all()

    mat_b, mat_a = np.zeros(10, np.int64), np.zeros(8, np.int64)
    for cap in (0.0, 1e-4, 1.0):
        report = compare_views(
            [(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat_b, mat_a, frozenset({0}), 0.15,
            strict=True, edge_flicker_cap=cap,
            geometry_before=(P, faces_before), geometry_after=(P, faces_after))
        assert report.totals["holes"] == 49
        assert report.totals["edge_flicker"] == 0
        assert report.totals["crack_closed"] == 0 and report.totals["zfight_tie"] == 0
        assert report.passed is False


def _gap_scene():
    """A wall at x in [-60, -10] and a 2-pixel-wide strip at x in [10, 16.5], both z = 0, with a
    20 in PRE-EXISTING gap between them. AFTER drops the strip entirely: every one of its pixels
    has a BEFORE miss right beside it (the gap on one side, background on the other), so every one
    of them satisfies HALF the ring rule -- a BEFORE ring ray does reproduce AFTER's missing
    centre. The other half is what must save it: nothing in AFTER reproduces the strip."""
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

    # planes alone cannot answer this -- there is nothing to cast a ring AT -- which is why a
    # nonzero cap without geometry is a hard error rather than a silent wrong answer.
    with pytest.raises(ValueError, match="geometry"):
        compare_views([(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat, mat, frozenset({0}),
                       0.15, edge_flicker_cap=1.0, **kw)

    # with the ring cast in both geometries, no AFTER ray reproduces the strip: a hole at every cap
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


# ---------------------------------------------------------------------------------------------
# M4b: the tie set is found by GEOMETRY, not by vertex sharing. `_TWIN` puts both quads on the
# same four frame vertices, so the old recovery found the second one by looking at the faces
# sharing a vertex with the first. Two loops drawn separately and never welded share nothing.
# ---------------------------------------------------------------------------------------------

#: The same two coincident quads as `_TWIN`, on DISJOINT vertex ids: faces 0-1 use frame
#: vertices 0-3, faces 2-3 their own identical copies 4-7.
_SPLIT_FRAME = np.vstack([_TWIN_FRAME, _TWIN_FRAME])
_SPLIT_TWIN = np.vstack([_QUAD, _QUAD + len(_TWIN_FRAME)])


def _split_render(faces, ids):
    return ortho_first_hit(_SPLIT_FRAME, faces, ids, _FLAT_VIEW, _FRAME, _COVER_SIZE)


def test_a_zfight_tie_is_found_between_faces_that_share_no_vertex():
    """Identical to `test_overlapping_coplanar_faces_of_different_materials_are_a_zfight_tie`
    except that the two coincident quads have disjoint vertex ids. Embree's multi-hit walk steps
    over the second one, and no vertex-sharing lookup can recover it."""
    assert not (set(_SPLIT_TWIN[:2].reshape(-1).tolist())
                & set(_SPLIT_TWIN[2:].reshape(-1).tolist()))
    mat_before = np.array([0, 0, 1, 1], np.int64)
    faces_after, mat_after = _SPLIT_TWIN[::-1].copy(), mat_before[::-1].copy()
    before = _split_render(_SPLIT_TWIN, np.arange(4))
    after = _split_render(faces_after, np.arange(4))

    model = before.tri >= 0
    assert model.sum() > 100
    assert (mat_before[before.tri[model]] != mat_after[after.tri[model]]).all()

    report = compare_views(
        [(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat_before, mat_after, frozenset({0, 1}),
        0.15, strict=True, edge_flicker_cap=0.0,
        plane_before=face_planes(_SPLIT_FRAME, _SPLIT_TWIN),
        plane_after=face_planes(_SPLIT_FRAME, faces_after),
        geometry_before=(_SPLIT_FRAME, _SPLIT_TWIN), geometry_after=(_SPLIT_FRAME, faces_after))
    assert report.totals["zfight_tie"] == int(model.sum())
    assert report.totals["material_changed"] == 0
    assert report.passed is True


# ---------------------------------------------------------------------------------------------
# M0b: the DIFF panel gives the two tolerated-by-construction classes their own colours, so a
# person reading a triptych can tell "a z-fight swapped winners" and "a crack closed" from the
# amber "reported, tolerated by some caller" and from real red damage.
# ---------------------------------------------------------------------------------------------

def test_save_triptych_gives_ties_and_closed_cracks_their_own_diff_colours(tmp_path):
    from PIL import Image

    from engine.guard import render as render_module

    depth = np.full((1, 6), 5.0)
    tri = np.zeros((1, 6), np.int64)
    codes = np.array([[PX_OK, PX_MOVED_SAME_FLAT, PX_EDGE_FLICKER, PX_ZFIGHT_TIE,
                       PX_CRACK_CLOSED, PX_HOLE]], np.int64)

    out = tmp_path / "legend.png"
    save_triptych(out, (depth, tri), (depth, tri), codes)
    diff = np.array(Image.open(out))[:, 12:, :]      # the third panel

    assert tuple(diff[0, 0]) == render_module._MODEL          # untouched model grey
    assert tuple(diff[0, 1]) == render_module._AMBER
    assert tuple(diff[0, 2]) == render_module._AMBER
    assert tuple(diff[0, 3]) == render_module._TIE
    assert tuple(diff[0, 4]) == render_module._CRACK
    assert tuple(diff[0, 5]) == render_module._FAIL
    assert len({render_module._MODEL, render_module._AMBER, render_module._TIE,
                render_module._CRACK, render_module._FAIL}) == 5


def test_save_triptych_gives_grown_pixels_their_own_diff_colour(tmp_path):
    """Review 2a Minor 1(b): `PX_GROWN` (code 10) -- surface where BEFORE saw the sky -- fails like
    a hole but had no colour at all, so a view failing only on growth drew a DIFF panel with
    nothing on it. It gets its own colour, painted where BEFORE saw background, so what appeared
    reads differently from what went."""
    from PIL import Image

    from engine.guard import render as render_module
    from engine.guard.compare import PX_GROWN

    before = (np.array([[5.0, np.inf, np.inf]]), np.array([[0, -1, -1]], np.int64))
    after = (np.array([[5.0, 5.0, np.inf]]), np.array([[0, 0, -1]], np.int64))
    codes = np.array([[PX_OK, PX_GROWN, PX_OK]], np.int64)

    out = tmp_path / "grown.png"
    save_triptych(out, before, after, codes)
    diff = np.array(Image.open(out))[:, 6:, :]       # the third panel

    assert tuple(diff[0, 0]) == render_module._MODEL
    assert tuple(diff[0, 1]) == render_module._GROWN
    assert tuple(diff[0, 2]) == render_module._BG
    assert len({render_module._MODEL, render_module._AMBER, render_module._TIE,
                render_module._CRACK, render_module._FAIL, render_module._BG,
                render_module._GROWN}) == 7


# ---------------------------------------------------------------------------
# G1: `crack_closed` is capped per view, like flicker. Its own docstring names the limit --
# damage NARROWER than the ring radius is indistinguishable from a crack the fix closed -- so a
# handful of such pixels is the improvement it claims to be and a FIELD of them is a picture that
# changed for a reason this test cannot see. Over the cap they fall back to their base class,
# which is what makes the report say what actually happened.
# ---------------------------------------------------------------------------

def _crack_cap_report(cap, flicker_cap=0.0):
    P, faces_before, faces_closed, _ = _crack_scene()
    before = ortho_first_hit(P, faces_before, np.arange(4), _FLAT_VIEW, _FRAME, _BIG_SIZE)
    after = ortho_first_hit(P, faces_closed, np.arange(4), _FLAT_VIEW, _FRAME, _BIG_SIZE)
    return compare_views(
        [(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], np.zeros(4, np.int64), np.zeros(4, np.int64),
        frozenset(), 0.15, strict=True, edge_flicker_cap=flicker_cap, crack_closed_cap=cap,
        plane_before=face_planes(P, faces_before), plane_after=face_planes(P, faces_closed),
        geometry_before=(P, faces_before), geometry_after=(P, faces_closed))


def test_closed_cracks_under_the_cap_are_still_tolerated_and_reported():
    report = _crack_cap_report(1e-2)              # 1e-2 * ~14,000 model px, far above 25
    assert report.totals["crack_closed"] == 25
    assert report.totals["moved_other"] == 0 and report.passed is True


def test_closed_cracks_over_the_cap_fall_back_to_their_base_class_and_fail():
    """25 crack pixels in a view of about 14,000 model px is 1.8e-3, over the 1e-3 default. The
    report must then show them as what they really were -- `moved_other` -- not as a tolerated
    improvement next to `passed: False` with nothing to explain it."""
    report = _crack_cap_report(1e-3)
    assert report.views[0].model_px < 25 / 1e-3    # the cap really is exceeded here
    assert report.totals["crack_closed"] == 0
    assert report.totals["moved_other"] == 25
    assert report.passed is False


def test_the_crack_cap_defaults_to_uncapped_so_existing_callers_are_unchanged():
    report = _crack_cap_report(float("inf"))
    assert report.totals["crack_closed"] == 25 and report.passed is True


def test_a_zfight_tie_is_never_capped():
    """Ties are a defect this run neither caused nor can fix, so no cap applies to them -- only
    cracks and flicker are capped. Every model pixel of the twin scene is a tie, which is far
    over any cap a fraction of `model_px` could express."""
    mat_before = np.array([0, 0, 1, 1], np.int64)
    faces_after, mat_after = _TWIN[::-1].copy(), mat_before[::-1].copy()
    before = _twin_render(_TWIN, np.arange(4))
    after = _twin_render(faces_after, np.arange(4))
    for crack_cap in (0.0, 1e-3, float("inf")):
        report = _twin_report(before, after, mat_before, mat_after, _TWIN, faces_after,
                              crack_closed_cap=crack_cap)
        assert report.totals["zfight_tie"] == int((before.tri >= 0).sum())
        assert report.passed is True


# ---------------------------------------------------------------------------
# G2: the removal guard classifies ties and closed cracks like the merge guard.
#
# `guard_feedback` cast no ring and no tie at all, while its docstring claimed "the same
# displacement/colour-aware pixel test as `compare_views`". At the flicker cap of 0.0 that is
# true of FLICKER -- a flicker pixel fails there exactly like the class it came from -- and false
# of the other two: `PX_ZFIGHT_TIE` and `PX_CRACK_CLOSED` are never failures at any cap, and the
# removal guard was counting both as damage.
# ---------------------------------------------------------------------------

_STACK_QUAD = np.array([[-50.0, -50.0, 0.0], [50.0, -50.0, 0.0],
                        [50.0, 50.0, 0.0], [-50.0, 50.0, 0.0]])


def _coincident_stack():
    """Three exactly coincident copies of one quad, materials `[0, 0, 1]` per copy (6 faces).
    Embree's first hit over all six is copy 2 (material 1); drop copy 1 and it becomes copy 0
    (material 0) -- both copies present in both meshes, so every model pixel changes material
    while nothing was lost. That is a z-fight tie, reached the way the real one is: by rebuilding
    the ray structure over a different face set."""
    faces = np.vstack([np.array([[0, 1, 2], [0, 2, 3]], np.int64)] * 3)
    material = np.array([0, 0, 0, 0, 1, 1], np.int64)
    candidates = np.zeros(6, bool)
    candidates[2:4] = True                       # copy 1, the one being removed
    return faces, material, candidates


def test_the_removal_guard_tolerates_a_zfight_tie_it_caused():
    faces, material, candidates = _coincident_stack()
    mask, history = guard_feedback(candidates, _STACK_QUAD, faces, material, frozenset({0, 1}),
                                   0.15, strict=True, views=[_FLAT_VIEW], size=_COVER_SIZE)

    # the fixture only means anything if the winner really flipped, on material
    before = ortho_first_hit(_STACK_QUAD, faces, np.arange(6), _FLAT_VIEW, _FRAME, _COVER_SIZE)
    keep = ~candidates
    after = ortho_first_hit(_STACK_QUAD, faces[keep], np.nonzero(keep)[0], _FLAT_VIEW, _FRAME,
                            _COVER_SIZE)
    model = before.tri >= 0
    assert model.sum() > 100
    assert (material[before.tri[model]] != material[after.tri[model]]).all()

    assert history[0]["failing_pixels"] == 0      # a tie is not damage, here as anywhere else
    assert history[0]["restored"] == 0
    assert np.array_equal(mask, candidates)


def test_the_removal_guard_still_fails_when_a_tie_member_was_the_one_removed():
    """The counterpart, so tolerance does not become blindness: remove the copy embree picks
    FIRST and BEFORE's own winner is gone from AFTER's tie set. Not a tie -- a material change --
    and the faces come back."""
    faces, material, _ = _coincident_stack()
    before = ortho_first_hit(_STACK_QUAD, faces, np.arange(6), _FLAT_VIEW, _FRAME, _COVER_SIZE)
    winner = int(np.bincount(before.tri[before.tri >= 0]).argmax())
    candidates = np.zeros(6, bool)
    candidates[[f for f in range(6) if material[f] == material[winner]]] = True

    mask, history = guard_feedback(candidates, _STACK_QUAD, faces, material, frozenset({0, 1}),
                                   0.15, strict=True, views=[_FLAT_VIEW], size=_COVER_SIZE)
    assert history[0]["failing_pixels"] > 100
    assert history[0]["restored"] > 0
    assert not mask[winner]


def test_the_removal_guard_still_fails_a_flicker_pixel():
    """Flicker is the one of the three that stays a failure here: `guard_feedback` runs at a cap
    of 0.0, where a flicker pixel fails exactly like the class it came from."""
    P, faces_before, _faces_closed, faces_torn = _crack_scene()
    # `faces_torn` is `faces_before` minus its first upper triangle: express that as a removal.
    candidates = np.zeros(len(faces_before), bool)
    candidates[0] = True
    mask, history = guard_feedback(candidates, P, faces_before, np.zeros(4, np.int64),
                                   frozenset(), 0.15, strict=True, views=[_FLAT_VIEW],
                                   size=_BIG_SIZE)
    # 656 px here, not the 1,000+ of `_crack_report`: `guard_feedback` frames every render on
    # `positions_c` (all 14 points of the scene) rather than on the 4-point `_FRAME`.
    assert history[0]["failing_pixels"] > 500
    assert mask[0] == False                       # half the image went missing: put it back


def test_a_removed_face_narrower_than_the_ring_is_never_excused_as_a_closed_crack():
    """The crack test's own documented limit, turned into a rule the removal guard cannot trip
    over: damage NARROWER than the ring radius looks exactly like a crack the fix closed. When
    the surface BEFORE hit is one this pass is DELETING, that reading is not available -- AFTER
    did not close anything, it lost it -- so the pixel goes back to its base class.

    The strip here is 0.02 in wide against a 0.15 in ring radius, differently coloured, laid over
    a floor and aimed straight through a column of pixel centres. Every one of its 16 ring rays
    misses it, so without the rule every pixel along it promotes to `PX_CRACK_CLOSED` and the
    guard deletes a real surface it can see."""
    # `guard_feedback` frames every render on `positions_c` itself, so the pixel centres have to
    # be taken from a camera framed the same way -- the strip sits inside the floor's own extent,
    # so adding it does not move them.
    floor = np.array([[-_SLAB, -_SLAB, 0.0], [_SLAB, -_SLAB, 0.0], [_SLAB, _SLAB, 0.0],
                       [-_SLAB, _SLAB, 0.0]])
    cam = ortho_first_hit(floor, np.zeros((0, 3), np.int64), np.zeros(0, np.int64),
                           _FLAT_VIEW, floor, _BIG_SIZE)
    x0 = float(cam.xs[70])
    half = 0.01                     # a 0.02 in strip: under depth_tol, over nothing
    P = np.vstack([floor,
                   [[x0 - half, -_SLAB, _STACK_GAP], [x0 + half, -_SLAB, _STACK_GAP],
                    [x0 + half, _SLAB, _STACK_GAP], [x0 - half, _SLAB, _STACK_GAP]]])
    faces = np.vstack([_QUAD, _QUAD + 4])
    material = np.array([0, 0, 1, 1], np.int64)
    candidates = np.array([False, False, True, True])

    before = ortho_first_hit(P, faces, np.arange(4), _FLAT_VIEW, P, _BIG_SIZE)
    assert int((before.tri >= 2).sum()) >= 100      # the strip really is on a column of pixels

    mask, history = guard_feedback(candidates, P, faces, material, frozenset({0, 1}), 0.15,
                                   strict=True, views=[_FLAT_VIEW], size=_BIG_SIZE)
    assert history[0]["failing_pixels"] >= 100
    assert not mask.any()                            # restored: the strip stays in the mesh


# ---------------------------------------------------------------------------------------------
# B1: a border the merge moved by less than its own tolerance is MEASURED, not counted.
#
# Measured on file A at e57462d: the merge (2,579 -> 1,117 triangles) was rolled back on edge
# flicker alone -- 59 pixels over 18 views, with 0 holes, 0 material changes and 0 moved pixels.
# View 0 failed with 14 flicker pixels against a cap of 11.4, and 9 of them were ONE run along
# pixel row 133, where merged region 2 reaches 0.0002 to 0.013 in past its original border. Every
# failing pixel was at most 0.062 in from the other mesh -- far inside the 0.15 in the merge may
# move a border -- but a per-view pixel COUNT cannot tell that from damage: an edge lying almost
# on a row of pixel centres flips the whole run for a 0.013 in shift. `border_shift_tol` measures
# instead each flicker pixel's clearance to the nearest triangle of the other mesh.
# ---------------------------------------------------------------------------------------------

import engine.guard.compare as guard_compare

#: `border_shift_tol` on file A: `min(collinear_tol, depth_tol_max)` = min(1.5 * 0.1, 0.5) in.
_BORDER_TOL = 0.15


def _row_scene(shift, upper=False, row=64):
    """A BEFORE/AFTER pair whose ONLY difference is one straight border that moved `shift` in,
    laid exactly along pixel row `row` of `_big_camera()`: BEFORE's edge is `shift / 2` above that
    row's pixel centres and AFTER's is `shift / 2` below them, so every centre of the row lies
    between the old edge and the new one and the whole run flips at once.

    `upper=False`: a lone 120 x ~60 in plate at z = 0, its top edge at `y = ys[row] +/- shift/2`.
    A positive `shift` RETREATS the border, so each pixel of the run turns from plate to sky.
    `upper=True`: the same plate floated `_STACK_GAP` above a floor covering the whole frame, so the
    border is an INTERNAL silhouette and a flipped pixel swaps plate for floor (a move, never a
    hole). A positive `shift` retreats the plate (something disappeared), a negative one advances
    it (something appeared). Returns `(mat, before, after, compare_views keywords)`."""
    y_row = float(_big_camera().ys[row])
    z = _STACK_GAP if upper else 0.0

    def scene(y_edge):
        plate = np.array([[-60.0, -60.0, z], [60.0, -60.0, z], [60.0, y_edge, z], [-60.0, y_edge, z]])
        if not upper:
            return plate, _QUAD.copy()
        floor = np.array([[-_SLAB, -_SLAB, 0.0], [_SLAB, -_SLAB, 0.0], [_SLAB, _SLAB, 0.0],
                          [-_SLAB, _SLAB, 0.0]])
        return np.vstack([floor, plate]), np.vstack([_QUAD, _QUAD + 4])

    P_before, faces = scene(y_row + shift / 2.0)
    P_after, _ = scene(y_row - shift / 2.0)
    ids = np.arange(len(faces))
    before = ortho_first_hit(P_before, faces, ids, _FLAT_VIEW, _FRAME, _BIG_SIZE)
    after = ortho_first_hit(P_after, faces, ids, _FLAT_VIEW, _FRAME, _BIG_SIZE)
    kw = dict(strict=True, geometry_before=(P_before, faces), geometry_after=(P_after, faces))
    return np.zeros(len(faces), np.int64), before, after, kw


def _one_view_report(view, mat, before, after, kw, **extra):
    return compare_views([(view, before)], [(view, after)], mat, mat, frozenset({0}), 0.15,
                          **kw, **extra)


def test_a_border_moved_a_hundredth_of_an_inch_along_a_pixel_row_is_a_border_shift():
    """File A's own failure, built on purpose. The plate's top edge runs exactly along pixel row
    64 and the merge moved it 0.01 in, so every centre of that row lies between the old edge and
    the new one: the whole run of 74 pixels turns from plate to sky at once.

    Every one of them really does reach the ring and come out as flicker -- that is checked first,
    so this test cannot pass on pixels the ring never saw -- and no count cap the merge guard uses
    can tolerate a run that long. Measured instead, each BEFORE hit point is 0.005 in from the
    plate AFTER still has: a border shift, never a failure. At `border_shift_tol = 0.0` the same
    pair fails exactly as it did before the measurement existed."""
    mat, before, after, kw = _row_scene(0.01)
    lost = (before.tri >= 0) & (after.tri < 0)
    n = int(lost.sum())
    assert n == 74 and int(lost[64].sum()) == n          # one whole run, all on the aimed row
    assert int(((before.tri >= 0) != (after.tri >= 0)).sum()) == n     # and nothing else changed

    today = _one_view_report(_FLAT_VIEW, mat, before, after, kw, edge_flicker_cap=0.0)
    assert today.totals["edge_flicker"] == n and today.totals["edge_flicker_hole"] == n
    assert today.totals["holes"] == 0 and today.totals["crack_closed"] == 0
    assert today.passed is False
    counted = _one_view_report(_FLAT_VIEW, mat, before, after, kw, edge_flicker_cap=1e-4)
    assert counted.views[0].model_px * 1e-4 < n and counted.passed is False

    measured = _one_view_report(_FLAT_VIEW, mat, before, after, kw, edge_flicker_cap=0.0,
                                border_shift_tol=_BORDER_TOL)
    assert measured.totals["border_shift"] == n and measured.views[0].border_shift == n
    assert measured.totals["edge_flicker"] == 0 and measured.views[0].edge_flicker == 0
    assert measured.totals["edge_flicker_hole"] == 0 and measured.totals["holes"] == 0
    assert measured.passed is True

    off = _one_view_report(_FLAT_VIEW, mat, before, after, kw, edge_flicker_cap=0.0,
                           border_shift_tol=0.0)
    assert off.totals == today.totals and off.totals["border_shift"] == 0
    assert off.passed is False


@pytest.mark.parametrize("shift", [0.01, -0.01], ids=["retreats", "advances"])
def test_an_internal_border_moved_a_hundredth_of_an_inch_along_a_pixel_row_is_a_border_shift(shift):
    """The same 0.01 in along a pixel row, at an INTERNAL silhouette: each pixel of the run swaps
    the plate for the floor 10 in behind it (the border retreated -- something disappeared, and
    BEFORE's hit point is measured against AFTER's triangles) or the floor for the plate (it
    advanced -- something appeared, and AFTER's hit point is measured against BEFORE's). Either
    way the base class is a move, the ring promotes it to flicker, and the measurement finds
    0.005 in."""
    mat, before, after, kw = _row_scene(shift, upper=True)
    swapped = (before.tri >= 2) != (after.tri >= 2)
    n = int(swapped.sum())
    assert n == 74 and int(swapped[64].sum()) == n
    appeared = shift < 0
    assert bool((after.tri[swapped] >= 2).all()) is appeared   # AFTER shows the plate iff it grew

    today = _one_view_report(_FLAT_VIEW, mat, before, after, kw, edge_flicker_cap=0.0)
    assert today.totals["edge_flicker"] == n and today.totals["edge_flicker_moved"] == n
    assert today.totals["moved_same_flat"] == 0 and today.passed is False

    measured = _one_view_report(_FLAT_VIEW, mat, before, after, kw, edge_flicker_cap=0.0,
                                border_shift_tol=_BORDER_TOL)
    assert measured.totals["border_shift"] == n
    assert measured.totals["edge_flicker"] == 0 and measured.totals["edge_flicker_moved"] == 0
    assert measured.totals["moved_same_flat"] == 0 and measured.passed is True


def _grazing_camera():
    """The camera `_grazing_view()` gives with `_FRAME` at `_BIG_SIZE`, with no geometry at all."""
    return ortho_first_hit(_FRAME, np.zeros((0, 3), np.int64), np.zeros(0, np.int64),
                           _grazing_view(), _FRAME, _BIG_SIZE)


def _grazing_hit_x(row, z):
    """Where the centre rays of pixel row `row` of `_grazing_camera()` cross the plane `z`. The view
    looks along +x (1 degree down), so `right` is -y and a column only picks y: every column of
    one row crosses the plane at the same x."""
    cam = _grazing_camera()
    origin = float(cam.ys[row]) * cam.up + cam.standoff
    t = (origin[2] - z) / -float(cam.direction[2])
    return float(origin[0] + t * cam.direction[0])


def test_a_two_inch_strip_lost_at_a_border_still_fails_where_the_ring_calls_it_flicker():
    """The measurement is what stops the tolerance excusing real damage. Seen 1 degree off the
    plate, the ring's 0.15 in radius -- in the IMAGE plane -- spans 8.6 in ALONG the plate, so a
    2 in strip lost at its far border does come out of the ring as flicker. Measured, BEFORE's hit
    point is 1.9 in from anything AFTER still has, so it stays flicker and fails at the zero cap
    whatever `border_shift_tol` is."""
    view, row = _grazing_view(), 64
    x_hit = _grazing_hit_x(row, 0.0)
    x_old = x_hit + 0.1                       # row 64 lands 0.1 in inside BEFORE's border...
    x_new = x_old - 2.0                       # ...and 1.9 in beyond AFTER's

    def plate(x_edge):
        return np.array([[x_hit - 150.0, -60.0, 0.0], [x_edge, -60.0, 0.0],
                         [x_edge, 60.0, 0.0], [x_hit - 150.0, 60.0, 0.0]])

    P_before, P_after = plate(x_old), plate(x_new)
    before = ortho_first_hit(P_before, _QUAD, np.arange(2), view, _FRAME, _BIG_SIZE)
    after = ortho_first_hit(P_after, _QUAD, np.arange(2), view, _FRAME, _BIG_SIZE)
    lost = (before.tri >= 0) & (after.tri < 0)
    n = int(lost.sum())
    assert n == 74 and int(lost[row].sum()) == n

    mat = np.zeros(2, np.int64)
    kw = dict(strict=True, geometry_before=(P_before, _QUAD), geometry_after=(P_after, _QUAD))
    for tol in (0.0, _BORDER_TOL):
        report = _one_view_report(view, mat, before, after, kw, edge_flicker_cap=0.0,
                                  border_shift_tol=tol)
        assert report.totals["edge_flicker"] == n and report.totals["edge_flicker_hole"] == n
        assert report.totals["border_shift"] == 0
        assert report.passed is False


def test_a_two_inch_strip_lost_at_a_border_is_a_hole_even_beside_the_new_edge():
    """Head-on, the same 2 in loss is 2 in wide in the image too -- far wider than the ring -- so
    its pixels are holes, not flicker, and the measurement never sees them. That includes row 64,
    whose centres sit 0.05 in from the new edge: a rule that measured EVERY failing pixel would
    have excused that whole run. Only a pixel the ring already calls flicker is measured -- or,
    since SR6, a hairline crack whose ring rays ALL saw the same, or moved no further than the
    tolerance; row 64's ring rays out over the lost strip lie up to 0.2 in from the new edge."""
    y_row = float(_big_camera().ys[64])
    y_new = y_row - 0.05                      # row 64's centres are 0.05 in outside AFTER's plate
    y_old = y_new + 2.0

    def plate(y_edge):
        return np.array([[-60.0, -60.0, 0.0], [60.0, -60.0, 0.0], [60.0, y_edge, 0.0],
                         [-60.0, y_edge, 0.0]])

    P_before, P_after = plate(y_old), plate(y_new)
    before = ortho_first_hit(P_before, _QUAD, np.arange(2), _FLAT_VIEW, _FRAME, _BIG_SIZE)
    after = ortho_first_hit(P_after, _QUAD, np.arange(2), _FLAT_VIEW, _FRAME, _BIG_SIZE)
    lost = (before.tri >= 0) & (after.tri < 0)
    n = int(lost.sum())
    assert int(lost[64].sum()) == 74 and n == 2 * 74       # rows 63 and 64

    mat = np.zeros(2, np.int64)
    kw = dict(strict=True, geometry_before=(P_before, _QUAD), geometry_after=(P_after, _QUAD))
    for tol in (0.0, _BORDER_TOL):
        report = _one_view_report(_FLAT_VIEW, mat, before, after, kw, edge_flicker_cap=0.0,
                                  border_shift_tol=tol)
        assert report.totals["holes"] == n
        assert report.totals["edge_flicker"] == 0 and report.totals["border_shift"] == 0
        assert report.passed is False


def test_a_surface_appearing_an_inch_beyond_its_border_still_fails_where_the_ring_calls_it_flicker():
    """The other direction. A plate 1 in above a floor grows 1 in past its old border; seen 1
    degree off the plate, the ring calls the run of pixels that now meet it instead of the floor
    flicker. Measured, AFTER's hit point is 0.9 in from anything BEFORE had -- the old border -- so
    it stays flicker and fails at the zero cap whatever `border_shift_tol` is."""
    view, row, height = _grazing_view(), 64, 1.0
    x_top = _grazing_hit_x(row, height)       # where row 64 crosses the plate's plane
    x_old = x_top - 0.9                       # BEFORE's border: row 64 passes 0.9 in beyond it
    x_new = x_old + 1.0                       # AFTER's plate reaches 1 in further, past row 64

    def scene(x_edge):
        floor = np.array([[x_top - 300.0, -60.0, 0.0], [x_top + 300.0, -60.0, 0.0],
                          [x_top + 300.0, 60.0, 0.0], [x_top - 300.0, 60.0, 0.0]])
        plate = np.array([[x_top - 150.0, -60.0, height], [x_edge, -60.0, height],
                          [x_edge, 60.0, height], [x_top - 150.0, 60.0, height]])
        return np.vstack([floor, plate])

    faces = np.vstack([_QUAD, _QUAD + 4])
    P_before, P_after = scene(x_old), scene(x_new)
    before = ortho_first_hit(P_before, faces, np.arange(4), view, _FRAME, _BIG_SIZE)
    after = ortho_first_hit(P_after, faces, np.arange(4), view, _FRAME, _BIG_SIZE)
    appeared = (before.tri >= 0) & (before.tri < 2) & (after.tri >= 2)
    n = int(appeared.sum())
    assert n == 74 and int(appeared[row].sum()) == n
    assert int((before.tri != after.tri).sum()) >= n

    mat = np.zeros(4, np.int64)
    kw = dict(strict=True, geometry_before=(P_before, faces), geometry_after=(P_after, faces))
    for tol in (0.0, _BORDER_TOL):
        report = _one_view_report(view, mat, before, after, kw, edge_flicker_cap=0.0,
                                  border_shift_tol=tol)
        assert report.totals["edge_flicker"] == n and report.totals["edge_flicker_moved"] == n
        assert report.totals["border_shift"] == 0
        assert report.passed is False


def test_a_material_change_is_never_measured_away_as_a_border_shift():
    """The measurement is for a surface that MOVED, never for one that changed colour.
    `_stacked_pair`'s 0.1 in shift with the upper slab in another material is flicker rescued from
    `material_changed`, and it stays exactly that at any tolerance -- while the very same shift in
    one material measures 0.05 in and is a border shift."""
    _, mat, before, after, kw = _stacked_pair(0.1, upper_material=1)
    kw = {**kw, "border_shift_tol": _BORDER_TOL}
    material = _stacked_report(mat, before, after, kw, cap=0.0, flat=frozenset({0, 1}))
    assert material.totals["edge_flicker"] == 1 and material.totals["edge_flicker_material"] == 1
    assert material.totals["border_shift"] == 0 and material.passed is False

    _, mat, before, after, kw = _stacked_pair(0.1)
    same = _stacked_report(mat, before, after, {**kw, "border_shift_tol": _BORDER_TOL}, cap=0.0)
    assert same.totals["border_shift"] == 1 and same.totals["edge_flicker"] == 0
    assert same.passed is True


def test_border_shift_tol_above_zero_without_both_geometries_is_an_error():
    """The measurement needs both meshes, and the flicker it re-classes needs them for its ring.
    Without them a nonzero tolerance would excuse nothing while looking as though it excused
    something -- the same trap the flicker cap refuses."""
    before, after = _buffers(_block()), _buffers(_block(drop=[(25, 25)]))
    mat = np.zeros(2, np.int64)
    args = ([(_FLICKER_VIEW, before)], [(_FLICKER_VIEW, after)], mat, mat, frozenset({0}), 0.15)

    with pytest.raises(ValueError) as excinfo:
        compare_views(*args, border_shift_tol=0.15, allow_depth_fallback=True)
    assert "border_shift_tol" in str(excinfo.value) and "geometry" in str(excinfo.value)
    with pytest.raises(ValueError, match="border_shift_tol"):
        compare_views(*args, border_shift_tol=0.15, allow_depth_fallback=True,
                      geometry_before=_BLOCK_GEOMETRY)

    # 0.0, the default, measures nothing and needs nothing
    report = compare_views(*args, border_shift_tol=0.0, allow_depth_fallback=True)
    assert report.totals["holes"] == 1 and report.totals["border_shift"] == 0


def test_the_border_shift_distance_is_exact_and_blind_to_which_plane_a_triangle_lies_in():
    """`_nearest_triangle_distance` is a true point-to-triangle distance -- the perpendicular over
    the interior, the nearest edge or corner outside it, never the distance to the triangle's
    PLANE alone -- taken over every triangle within reach whatever plane it lies in (quantised
    sloped faces are not coplanar within 0.05 in, so a same-plane filter finds nothing), and `inf`
    where nothing is within reach."""
    floor = [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]]
    points = np.array([[2.0, 2.0, 3.0],       # over the interior: the perpendicular, 3
                       [5.0, -4.0, 0.0],      # beside edge (0,0)-(10,0): 4 (its plane says 0)
                       [-3.0, -4.0, 0.0],     # past corner (0,0,0): 5
                       [6.0, 6.0, 0.0],       # past the hypotenuse x + y = 10: sqrt(2)
                       [13.0, 0.0, 4.0]])     # past corner (10,0,0): 5
    one = guard_compare._nearest_triangle_distance(points, np.array([floor]), 10.0)
    assert one == pytest.approx([3.0, 4.0, 5.0, np.sqrt(2.0), 5.0], abs=1e-12)

    # a zero-area (collinear) triangle is still a segment you can be near
    needle = np.array([[[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [20.0, 0.0, 0.0]]])
    assert guard_compare._nearest_triangle_distance(np.array([[5.0, 3.0, 0.0]]), needle,
                                                    10.0) == pytest.approx([3.0], abs=1e-12)

    # the nearest triangle wins whatever its plane: a WALL standing at x = 11 is 1 in from
    # (12, 5, 0), the floor triangle 7 / sqrt(2) = 4.9 in away
    wall = [[11.0, 0.0, 0.0], [11.0, 10.0, 0.0], [11.0, 0.0, 10.0]]
    both = guard_compare._nearest_triangle_distance(np.array([[12.0, 5.0, 0.0]]),
                                                    np.array([floor, wall]), 2.0)
    assert both == pytest.approx([1.0], abs=1e-12)

    # nothing within reach is `inf`, not a guess
    far = guard_compare._nearest_triangle_distance(np.array([[2.0, 2.0, 3.0]]),
                                                   np.array([floor]), 1.0)
    assert np.isinf(far).all()


def test_growth_over_background_is_failing_base_and_excused_by_border_shift():
    """Review M3: A pixel where BEFORE missed and AFTER hit is classified as PX_GROWN (failing base)
    and excused as border_shift when within border_shift_tol of the BEFORE mesh."""
    def make_slab(xmax):
        pos = np.array([[-5.0, -5.0, 0.0], [xmax, -5.0, 0.0], [xmax, 5.0, 0.0], [-5.0, 5.0, 0.0]])
        faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
        return pos, faces

    Pb, fb = make_slab(0.0)
    Pa, fa = make_slab(0.08)
    view = [0.0, 0.0, 1.0]
    bounds = np.array([[-6.0, -6.0, -1.0], [6.0, 6.0, 1.0]])
    size = (120, 80)
    before_hit = ortho_first_hit(Pb, fb, np.arange(2), view, bounds, size)
    after_hit = ortho_first_hit(Pa, fa, np.arange(2), view, bounds, size)

    mat = np.zeros(2, np.int64)
    kw = dict(plane_before=face_planes(Pb, fb), plane_after=face_planes(Pa, fa),
              geometry_before=(Pb, fb), geometry_after=(Pa, fa), strict=True)

    # With border_shift_tol=0.0 and cap=0.0: the grown pixels fail
    rep_strict = compare_views([(view, before_hit)], [(view, after_hit)], mat, mat, frozenset({0}), 0.15,
                               edge_flicker_cap=0.0, border_shift_tol=0.0, **kw)
    assert rep_strict.passed is False
    assert rep_strict.totals["edge_flicker_grown"] > 0

    # With border_shift_tol measuring clearance to BEFORE mesh: the grown pixels are excused
    rep_tol = compare_views([(view, before_hit)], [(view, after_hit)], mat, mat, frozenset({0}), 0.15,
                            edge_flicker_cap=0.0, border_shift_tol=0.15, **kw)
    assert rep_tol.passed is True
    assert rep_tol.totals["border_shift"] > 0

    # Review 2a Minor 4: every report says what the grown pixels BECAME -- how many pixels had
    # PX_GROWN as their base class, and how many of those the tolerated classes took -- so a run's
    # border shift, flicker and crack counts can be split into losses and growth.
    for rep in (rep_strict, rep_tol):
        for counts in [rep.totals] + [vars(v) for v in rep.views]:
            assert counts["grown_base"] == (counts["grown"] + counts["edge_flicker_grown"]
                                            + counts["border_shift_grown"]
                                            + counts["crack_closed_grown"]
                                            + counts["zfight_tie_grown"])
    assert rep_strict.totals["grown_base"] == rep_tol.totals["grown_base"] > 0
    assert rep_strict.totals["border_shift_grown"] == 0
    # nothing was lost here, so every border shift is growth the tolerance measured and excused
    assert rep_tol.totals["border_shift_grown"] == rep_tol.totals["border_shift"]


# ---------------------------------------------------------------------------------------------
# SR6 item 3: a hairline crack the merge OPENED, measured like any other border shift.
#
# Measured on file A (SR6, items 1 and 2 applied): the merge (3,168 -> 1,428 triangles) was
# rolled back on two pixels. In view 2 AFTER's centre ray missed where BEFORE met face 4880; in
# view 15 it went on to a surface 48.5 in behind. BEFORE's hit points were 0.0001 in and 0.0049 in
# from the merged mesh -- within the 0.15 in the merge may move a border -- and 16 and 10 of the
# AFTER ring rays still met BEFORE's surface. But not one BEFORE ring ray met what AFTER's centre
# saw through the crack, so the flicker test never passed, and the border-shift measurement,
# which only ever looked at flicker pixels, never measured them.
# ---------------------------------------------------------------------------------------------


def _opened_crack_report(faces_before, faces_after, n_after, **extra):
    P = _crack_scene()[0]
    before = ortho_first_hit(P, faces_before, np.arange(len(faces_before)), _FLAT_VIEW, _FRAME,
                             _BIG_SIZE)
    after = ortho_first_hit(P, faces_after, np.arange(n_after), _FLAT_VIEW, _FRAME, _BIG_SIZE)
    mat_b = np.zeros(len(faces_before), np.int64)
    mat_a = np.zeros(len(faces_after), np.int64)
    report = compare_views(
        [(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], mat_b, mat_a, frozenset(), 0.15,
        strict=True, edge_flicker_cap=0.0,
        plane_before=face_planes(P, faces_before), plane_after=face_planes(P, faces_after),
        geometry_before=(P, faces_before), geometry_after=(P, faces_after), **extra)
    return before, after, report


def _lower_exposed(front: bool) -> np.ndarray:
    """`exposed_after` for `_crack_scene`'s AFTER faces `[upper, upper, lower, lower]`: whether
    the lower surface's FRONT (+z, the side the camera meets) was already exposed."""
    exposed = np.ones((4, 2), dtype=bool)
    exposed[2:, 0] = front
    return exposed


def test_a_crack_the_merge_opened_narrower_than_its_border_tolerance_is_a_border_shift():
    """The crack test's mirror image: BEFORE is the closed slab, AFTER the same slab split by a
    0.02 in crack, so in 25 pixels AFTER's centre ray falls through to the surface 10 in behind.
    Every AFTER ring ray still meets the slab -- the surface is still there, beside each pixel --
    and the crack, measured across against the slab AFTER still has in BEFORE's own plane and
    material, is 0.02 in wide: a border the merge moved less than its own tolerance, not a lost
    surface -- where what shows through it is a side the reference already exposed (review part
    2, M1: the rule used to excuse whatever showed through). At `border_shift_tol = 0.0` the same
    pixels fail exactly as they did."""
    P, faces_cracked, faces_closed, _ = _crack_scene()
    before, after, today = _opened_crack_report(faces_closed, faces_cracked, 4)
    opened = (before.tri >= 0) & (before.tri < 2) & (after.tri >= 2)
    assert int(opened.sum()) == 25
    assert today.totals["moved_other"] == 25 and today.totals["border_shift"] == 0
    assert today.passed is False

    _, _, measured = _opened_crack_report(faces_closed, faces_cracked, 4,
                                          border_shift_tol=_BORDER_TOL,
                                          exposed_after=_lower_exposed(True))
    assert measured.totals["border_shift"] == 25
    assert measured.totals["moved_other"] == 0 and measured.totals["edge_flicker"] == 0
    assert measured.passed is True


def test_a_crack_the_merge_opened_onto_a_side_nobody_saw_is_never_a_border_shift():
    """Review part 2, M1: the opened-crack rule never asked what shows through the crack. The same
    0.02 in crack, but the surface behind it was NOT exposed on the reference -- the inside of a
    shell: a hole judged as one, as the fragment rule judges it (review C2). Without any exposure
    given, only the sky qualifies."""
    P, faces_cracked, faces_closed, _ = _crack_scene()
    for extra in ({"exposed_after": _lower_exposed(False)}, {}):
        _, _, report = _opened_crack_report(faces_closed, faces_cracked, 4,
                                            border_shift_tol=_BORDER_TOL, **extra)
        assert report.totals["border_shift"] == 0
        assert report.totals["moved_other"] == 25
        assert report.passed is False


def test_a_crack_wider_than_the_border_tolerance_is_never_a_border_shift(monkeypatch):
    """Review part 2, M1: the rule measured BEFORE's hit point -- in the MIDDLE of the crack --
    against the nearest AFTER surface, which is half the crack's width away: cracks up to twice
    the 0.15 in tolerance passed (0.29 in did, 0.31 in failed). It measures the crack ACROSS now:
    0.2 in fails, whatever shows through it."""
    import engine.tests.test_guard as tg
    monkeypatch.setattr(tg, "_CRACK_GAP", 0.2)
    P, faces_cracked, faces_closed, _ = _crack_scene()
    before, after, report = _opened_crack_report(faces_closed, faces_cracked, 4,
                                                 border_shift_tol=_BORDER_TOL,
                                                 exposed_after=_lower_exposed(True))
    opened = (before.tri >= 0) & (before.tri < 2) & (after.tri >= 2)
    assert int(opened.sum()) == 25            # one pixel per row, as at 0.02 in: finer than a pixel
    assert report.totals["border_shift"] == 0
    assert report.passed is False


def test_a_crack_the_merge_opened_onto_the_sky_is_a_border_shift():
    """The file A pixel the opened-crack rule exists for: AFTER's centre ray MISSED through a
    0.0001 in crack. The sky may always show (as for removed debris): the same 0.02 in crack with
    nothing behind the slab is a border shift with no exposure given at all."""
    P, faces_cracked, faces_closed, _ = _crack_scene()
    upper_closed, upper_cracked = faces_closed[:2], faces_cracked[:2]
    before, after, report = _opened_crack_report(upper_closed, upper_cracked, 2,
                                                 border_shift_tol=_BORDER_TOL)
    opened = (before.tri >= 0) & (after.tri < 0)
    assert int(opened.sum()) == 25
    assert report.totals["border_shift"] == 25 and report.passed is True


def test_a_whole_triangle_lost_after_a_closed_slab_still_fails_with_the_border_tolerance():
    """The measurement is what keeps that from excusing damage: AFTER loses one upper triangle
    outright. Deep inside it no AFTER ring ray meets the slab, and BEFORE's hit points are far
    from anything AFTER still has, so the lost pixels stay failures at the merge's tolerance."""
    P, _, faces_closed, faces_torn = _crack_scene()
    before, after, report = _opened_crack_report(faces_closed, faces_torn, 3,
                                                 border_shift_tol=_BORDER_TOL)
    lost = (before.tri < 2) & (after.tri >= 1)
    assert int(lost.sum()) > 1000
    assert report.totals["moved_other"] > 1000
    assert report.passed is False


def test_a_removed_fragment_that_opens_onto_the_inside_is_never_an_opened_crack():
    """The side rebuild's opened-crack rule (SR6) meets the debris rule (review C2) in one place:
    a pixel whose BEFORE hit is a face the fragment pass REMOVED. The crack here is filled by a
    0.02 in sliver in BEFORE, and the sliver is the debris removed; AFTER's centre ray falls
    through to the surface 10 in behind, in the same 25 pixels as the opened crack above.

    Where that surface's side was already outside on the reference, the removal may show it:
    `fragment_removed`, as on feat-dashboard. Where it was NOT -- the inside of a shell -- the
    removal uncovered a side nobody could see, which is a hole judged as one (review C2), and the
    merge's border tolerance is no excuse for it: the merge did not open that crack, the removal
    did. Neither branch ever let such a pixel through as `border_shift` (on feat/side-rebuild a
    removed fragment's pixel was always `fragment_removed`, and feat-dashboard had no opened-crack
    rule), so the merged guard does not either."""
    P, faces_cracked, faces_closed, _ = _crack_scene()
    upper, lower = faces_cracked[:2], faces_cracked[2:]
    sliver = np.array([[0, 1, 4], [0, 4, 3]], np.int64)        # fills the crack, in the z = 0 plane
    faces_before = np.vstack([upper, sliver, lower])            # 0-1 upper, 2-3 sliver, 4-5 lower
    removed = np.array([False, False, True, True, False, False])
    before = ortho_first_hit(P, faces_before, np.arange(6), _FLAT_VIEW, _FRAME, _BIG_SIZE)
    after = ortho_first_hit(P, faces_cracked, np.arange(4), _FLAT_VIEW, _FRAME, _BIG_SIZE)
    opened = (before.tri >= 2) & (before.tri < 4) & (after.tri >= 2)
    assert int(opened.sum()) == 25

    def report(lower_front_exposed: bool, **extra):
        exposed = np.ones((4, 2), dtype=bool)
        exposed[2:, 0] = lower_front_exposed        # the lower surface's FRONT (+z) faces the camera
        return compare_views(
            [(_FLAT_VIEW, before)], [(_FLAT_VIEW, after)], np.zeros(6, np.int64),
            np.zeros(4, np.int64), frozenset(), 0.15, strict=True, edge_flicker_cap=0.0,
            plane_before=face_planes(P, faces_before), plane_after=face_planes(P, faces_cracked),
            geometry_before=(P, faces_before), geometry_after=(P, faces_cracked),
            border_shift_tol=_BORDER_TOL, removed_before=removed,
            exposed_after=exposed, **extra)

    shows_the_outside = report(True)
    assert shows_the_outside.totals["fragment_removed"] == 25
    assert shows_the_outside.totals["border_shift"] == 0
    assert shows_the_outside.passed is True

    shows_the_inside = report(False)
    assert shows_the_inside.totals["fragment_removed"] == 0
    assert shows_the_inside.totals["border_shift"] == 0
    assert shows_the_inside.totals["moved_other"] == 25
    assert shows_the_inside.passed is False


# ---------------------------------------------------------------------------
# Brief 10 item 1: the cap guard's rule 6 -- seen through a closed slab
# ---------------------------------------------------------------------------

def test_a_view_is_through_the_slab_only_between_two_kept_shell_faces_inside_it():
    """Two new walls of one slab, `y = 0` wound -y and `y = 20` wound +y (outward), both reaching
    `z = -10`, while the slab itself is `z` -2 to 0: below -2 they are fins. A ray along +y enters
    the near wall from outside and leaves through the far one. Seen through the slab -- rule 6 --
    only when every stretch between them lies inside the slab and BEFORE's hit lies beyond the far
    wall; never for a ray that met its new face on the back (it came in through an opening)."""
    from engine.guard.compare import INTERIOR_BELOW_BOTTOM, INTERIOR_INSIDE, _through_closed_shell
    from engine.rays.caster import EmbreeCaster
    P = np.array([[0, 0, 0], [40, 0, 0], [40, 0, -10], [0, 0, -10],
                  [0, 20, 0], [40, 20, 0], [40, 20, -10], [0, 20, -10]], dtype=np.float64)
    faces = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7]], dtype=np.int64)
    planes = face_planes(P, faces)
    assert planes[0, 1] == -1.0 and planes[2, 1] == 1.0
    caster = EmbreeCaster(P, faces)

    def interior(face_ids, points):
        inside = (points[:, 2] <= 0.0) & (points[:, 2] >= -2.0)
        return np.where(inside, INTERIOR_INSIDE, INTERIOR_BELOW_BOTTOM)

    start = np.array([[20.0, 0.0, -1.0], [20.0, 0.0, -5.0], [20.0, 0.0, -1.0]])
    gap = np.array([30.0, 30.0, 10.0])      # BEFORE's hit at y = 30, 30, and 10 (short of the wall)
    out, leave = _through_closed_shell(start, np.array([0.0, 1.0, 0.0]), gap,
                                       np.array([0, 0, 0]), planes, caster, np.arange(4),
                                       interior)
    assert out.tolist() == [True, False, False]
    assert leave[0] in (2, 3) and leave[1:].tolist() == [-1, -1]
    # the far wall's inner side, reached from within: its ray met it on the back
    back, _ = _through_closed_shell(np.array([[20.0, 20.0, -1.0]]), np.array([0.0, 1.0, 0.0]),
                                    np.array([10.0]), np.array([2]), planes, caster,
                                    np.arange(4), interior)
    assert back.tolist() == [False]


def test_a_face_held_up_by_a_refused_face_is_refused_with_it_unless_another_holds_it():
    """Brief 10 item 1, "refused together": a pixel rule 6 allowed because its ray left the slab
    through a new wall at y = 20 (faces 2-3). That wall is refused this round. Re-cast against
    the rest of the shell, the ray next leaves through the wall at y = 30 (faces 4-5):

    - if the slab ends at y = 20, the stretch beyond it is outside, so the pixel's own new face
      (0) is refused in the SAME round;
    - if the slab runs on to y = 30 (a lower slab beyond a step wall), the ray still leaves a
      closed slab, and face 0 stays;
    - if what BEFORE showed there is a replaced piece, the piece is restored instead."""
    from engine.guard.compare import (INTERIOR_BELOW_BOTTOM, INTERIOR_INSIDE,
                                      INTERIOR_OUTSIDE_FOOTPRINT, _refuse_together)
    from engine.rays.caster import EmbreeCaster
    P, faces = [], []
    for y, sign in ((0.0, -1), (20.0, 1), (30.0, 1)):
        b = len(P)
        P += [[0, y, 0], [40, y, 0], [40, y, -10], [0, y, -10]]
        faces += ([[b, b + 2, b + 1], [b, b + 3, b + 2]] if sign < 0
                  else [[b, b + 1, b + 2], [b, b + 2, b + 3]])
    P, faces = np.array(P, dtype=np.float64), np.array(faces, dtype=np.int64)
    planes = face_planes(P, faces)
    assert planes[0, 1] == -1.0 and planes[2, 1] == 1.0 and planes[4, 1] == 1.0

    def slab_to(y_end):
        def interior(face_ids, points):
            inside = (points[:, 2] >= -2.0) & (points[:, 2] <= 0.0) & (points[:, 1] <= y_end)
            return np.where(inside, INTERIOR_INSIDE, INTERIOR_BELOW_BOTTOM)
        return interior

    def run(y_end, piece):
        records = [[np.array([0.0, 1.0, 0.0]), np.array([[20.0, 0.0, -1.0]]), np.array([40.0]),
                    np.array([0]), np.array([7]), np.array([INTERIOR_OUTSIDE_FOOTPRINT]),
                    np.array([2])]]
        refuse, restore = {2: [1], 3: [1]}, set()
        removed = np.zeros(10, dtype=bool)
        removed[7] = piece
        together = _refuse_together(refuse, restore, removed, records, np.arange(6), planes, P,
                                    faces, EmbreeCaster, slab_to(y_end))
        return together, sorted(refuse), sorted(restore), int(records[0][6][0])

    assert run(20.0, False) == (1, [0, 2, 3], [], 2)
    together, refused, restored, leave = run(30.0, False)
    assert (together, refused, restored) == (0, [2, 3], []) and leave in (4, 5)
    assert run(20.0, True) == (0, [2, 3], [7], 2)


def test_a_lost_rule_6_pixel_over_a_replaced_piece_always_restores_the_piece():
    """Review of brief 10, M1 (`probe_refuse_together_piece.py`): who pays when a rule-6 pixel is
    lost and what BEFORE showed there is a REPLACED piece. The docstring and the main loop say:
    the piece is restored, the new face kept. `_refuse_together` did so for the FIRST such pixel
    only -- a second pixel on the same piece, or one on a piece the main loop already restores
    this round, fell through and refused the new face (face 0), whose group then gave its pieces
    back. The scene is `test_a_face_held_up_by_a_refused_face_is_refused_with_it_unless_another_
    holds_it`'s: walls at y = 0, 20 (refused this round) and 30; the slab ends at y = 20."""
    from engine.guard.compare import (INTERIOR_BELOW_BOTTOM, INTERIOR_INSIDE,
                                      INTERIOR_OUTSIDE_FOOTPRINT, _refuse_together)
    from engine.rays.caster import EmbreeCaster
    P, faces = [], []
    for y, sign in ((0.0, -1), (20.0, 1), (30.0, 1)):
        b = len(P)
        P += [[0, y, 0], [40, y, 0], [40, y, -10], [0, y, -10]]
        faces += ([[b, b + 2, b + 1], [b, b + 3, b + 2]] if sign < 0
                  else [[b, b + 1, b + 2], [b, b + 2, b + 3]])
    P, faces = np.array(P, dtype=np.float64), np.array(faces, dtype=np.int64)
    planes = face_planes(P, faces)

    def interior(face_ids, points):
        inside = (points[:, 2] >= -2.0) & (points[:, 2] <= 0.0) & (points[:, 1] <= 20.0)
        return np.where(inside, INTERIOR_INSIDE, INTERIOR_BELOW_BOTTOM)

    def run(n_pixels, already_restoring):
        starts = np.array([[20.0 + k, 0.0, -1.0] for k in range(n_pixels)])
        records = [[np.array([0.0, 1.0, 0.0]), starts, np.full(n_pixels, 40.0),
                    np.zeros(n_pixels, np.int64), np.full(n_pixels, 7),
                    np.full(n_pixels, INTERIOR_OUTSIDE_FOOTPRINT), np.full(n_pixels, 2)]]
        refuse, restore = {2: [1], 3: [1]}, ({7} if already_restoring else set())
        removed = np.zeros(10, dtype=bool)
        removed[7] = True
        together = _refuse_together(refuse, restore, removed, records, np.arange(6), planes, P,
                                    faces, EmbreeCaster, interior)
        return together, sorted(refuse), sorted(restore)

    assert run(1, False) == (0, [2, 3], [7])            # as before
    assert run(2, False) == (0, [2, 3], [7])            # was (1, [0, 2, 3], [7])
    assert run(1, True) == (0, [2, 3], [7])             # was (1, [0, 2, 3], [7])
