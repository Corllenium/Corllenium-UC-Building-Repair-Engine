import numpy as np

from engine.fixes.orient import (ORIENT_FLIP, ORIENT_OK, ORIENT_THIN_SHEET, classify_orientation,
                                  flip_faces, one_sided_holes)
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import cube
from engine.vis.exposure import compute_side_exposure

_SIZE = (120, 80)  # small render: only correctness is under test, not image fidelity


def _centered(mesh):
    topo = analyse_topology(mesh)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2
    return topo, topo.positions_w - centre


# ---------------------------------------------------------------------------
# classify_orientation
# ---------------------------------------------------------------------------

def test_orientation_constants():
    assert ORIENT_OK == 0 and ORIENT_FLIP == 1 and ORIENT_THIN_SHEET == 2


def test_classify_orientation_flip_when_back_exceeds_front():
    front = np.array([0.5, 0.1, 0.0, 0.3])
    back = np.array([0.1, 0.5, 0.0, 0.3])
    ok = np.array([True, True, True, True])
    cls = classify_orientation(front, back, ok)
    assert cls.tolist() == [ORIENT_OK, ORIENT_FLIP, ORIENT_OK, ORIENT_THIN_SHEET]


def test_classify_orientation_hidden_faces_are_ok():
    # front == back == 0: totally hidden (or not-ok) -- never FLIP, never THIN_SHEET.
    front = np.array([0.0, 0.0])
    back = np.array([0.0, 0.0])
    ok = np.array([True, False])
    cls = classify_orientation(front, back, ok)
    assert cls.tolist() == [ORIENT_OK, ORIENT_OK]


def test_classify_orientation_not_ok_faces_are_ok_even_if_back_exceeds_front():
    front = np.array([0.1])
    back = np.array([0.9])
    ok = np.array([False])
    cls = classify_orientation(front, back, ok)
    assert cls.tolist() == [ORIENT_OK]


def test_a_thin_sheet_is_never_flipped_even_when_its_back_sees_more():
    """R1a: THIN_SHEET takes precedence over FLIP. A free-standing sheet with anything at all on
    one side sees a little less sky there, so `back > front` alone reads a perfectly correct sheet
    as reversed -- and flipping one opens a hole in a one-sided renderer on whichever side is now
    the back. It is only a FLIP when the two sides are lopsided enough NOT to be a sheet.

    First pair: a sheet's own measured numbers (a 10x10 quad under a 6x6 awning, below). Second:
    a genuinely reversed face, whose front is nearly blind."""
    front = np.array([0.3906, 0.3887, 0.10, 0.0])
    back = np.array([0.5, 0.5, 0.90, 0.5])
    ok = np.array([True, True, True, True])
    cls = classify_orientation(front, back, ok, sheet_ratio=0.5)
    assert cls.tolist() == [ORIENT_THIN_SHEET, ORIENT_THIN_SHEET, ORIENT_FLIP, ORIENT_FLIP]


def test_classify_orientation_thin_sheet_ratio_threshold():
    # min/max exactly at the default 0.5 threshold -> THIN_SHEET; just below -> OK.
    front = np.array([0.4, 0.41])
    back = np.array([0.2, 0.2])
    ok = np.array([True, True])
    cls = classify_orientation(front, back, ok, sheet_ratio=0.5)
    assert cls.tolist() == [ORIENT_THIN_SHEET, ORIENT_OK]


def test_classify_orientation_cube_with_three_reversed_faces():
    """A closed cube: reverse 3 of its 12 triangles' winding. Each reversed triangle shares its
    quad with an untouched sibling triangle, so double-sided exposure per triangle still measures
    the SAME physical quad; the reversed one classes FLIP, its sibling stays OK."""
    m = cube(10.0)
    reversed_tris = [0, 4, 9]
    for i in reversed_tris:
        m.face_v[i] = m.face_v[i][::-1]
    topo, Pc = _centered(m)
    front, back = compute_side_exposure(Pc, topo.face_w, topo.ok, n_dirs=48)
    cls = classify_orientation(front, back, topo.ok)
    assert set(np.nonzero(cls == ORIENT_FLIP)[0].tolist()) == set(reversed_tris)
    assert (cls[[i for i in range(12) if i not in reversed_tris]] == ORIENT_OK).all()


# ---------------------------------------------------------------------------
# flip_faces
# ---------------------------------------------------------------------------

def test_flip_faces_reverses_vertex_and_uv_order_and_drops_the_normal():
    m = cube(10.0)
    m.face_vn = np.zeros_like(m.face_v)
    m.face_vn[:] = np.arange(m.n_faces)[:, None]  # give every face a distinct (fake) vn index
    flip = np.zeros(m.n_faces, dtype=bool)
    flip[[1, 5]] = True

    out = flip_faces(m, flip)

    assert np.array_equal(out.face_v[1], m.face_v[1][::-1])
    assert np.array_equal(out.face_vt[1], m.face_vt[1][::-1])
    assert (out.face_vn[1] == -1).all()
    assert np.array_equal(out.face_v[5], m.face_v[5][::-1])
    assert (out.face_vn[5] == -1).all()

    untouched = [i for i in range(m.n_faces) if i not in (1, 5)]
    assert np.array_equal(out.face_v[untouched], m.face_v[untouched])
    assert np.array_equal(out.face_vt[untouched], m.face_vt[untouched])
    assert np.array_equal(out.face_vn[untouched], m.face_vn[untouched])

    # vertices are never moved or invented
    assert np.array_equal(out.positions, m.positions)
    assert out.positions is m.positions or np.array_equal(out.positions, m.positions)


def test_flip_faces_all_false_is_identity():
    m = cube(10.0)
    out = flip_faces(m, np.zeros(m.n_faces, dtype=bool))
    assert np.array_equal(out.face_v, m.face_v)
    assert np.array_equal(out.face_vt, m.face_vt)
    assert np.array_equal(out.face_vn, m.face_vn)


def test_flip_faces_wrong_shape_raises():
    m = cube(10.0)
    try:
        flip_faces(m, np.zeros(m.n_faces + 1, dtype=bool))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_flip_faces_never_changes_the_render():
    """Flipping never moves geometry and the caster does not cull backfaces, so a double-sided
    render of a mesh with some faces flipped must be pixel-for-pixel identical to the unflipped
    render: the guard verdict cannot depend on whether flip_faces ran."""
    m = cube(10.0)
    flip = np.zeros(m.n_faces, dtype=bool)
    flip[[0, 3, 7]] = True
    flipped = flip_faces(m, flip)

    topo_before, Pc = _centered(m)
    topo_after = analyse_topology(flipped)
    ids = np.arange(len(topo_before.face_w))

    for view in VIEWS_26:
        before = ortho_first_hit(Pc, topo_before.face_w, ids, view, Pc, _SIZE)
        after = ortho_first_hit(Pc, topo_after.face_w, ids, view, Pc, _SIZE)
        assert np.array_equal(before.tri, after.tri)
        assert np.array_equal(np.isfinite(before.depth), np.isfinite(after.depth))
        finite = np.isfinite(before.depth)
        assert np.allclose(before.depth[finite], after.depth[finite])


# ---------------------------------------------------------------------------
# one_sided_holes
# ---------------------------------------------------------------------------

def test_one_sided_holes_zero_for_a_correctly_wound_closed_cube():
    m = cube(10.0)
    topo, Pc = _centered(m)
    ids = np.arange(len(topo.face_w))
    n = one_sided_holes(Pc, topo.face_w, ids, VIEWS_26, _SIZE)
    assert n == 0


def test_one_sided_holes_positive_when_a_face_is_reversed():
    m = cube(10.0)
    m.face_v[0] = m.face_v[0][::-1]
    topo, Pc = _centered(m)
    ids = np.arange(len(topo.face_w))
    n = one_sided_holes(Pc, topo.face_w, ids, VIEWS_26, _SIZE)
    assert n > 0


def test_one_sided_holes_fixed_by_flip_faces():
    m = cube(10.0)
    m.face_v[0] = m.face_v[0][::-1]  # break face 0's winding
    topo_before, Pc = _centered(m)
    ids = np.arange(len(topo_before.face_w))
    before = one_sided_holes(Pc, topo_before.face_w, ids, VIEWS_26, _SIZE)

    flip = np.zeros(m.n_faces, dtype=bool)
    flip[0] = True
    fixed = flip_faces(m, flip)
    topo_after = analyse_topology(fixed)
    after = one_sided_holes(Pc, topo_after.face_w, ids, VIEWS_26, _SIZE)

    assert before > 0
    assert after == 0
    assert after < before
