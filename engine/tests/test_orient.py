import numpy as np

from engine.fixes.orient import (ORIENT_FLIP, ORIENT_OK, ORIENT_THIN_SHEET, backface_counts,
                                  backface_pixels, classify_orientation, face_unit_normals,
                                  flip_faces, one_sided_holes, orient_sheets)
from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import cube, slab_with_a_pocket_in_its_top
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


# ---------------------------------------------------------------------------
# SR0: back faces seen from outside, per view -- the objective measure of the owner's purple
# ---------------------------------------------------------------------------

def test_backface_pixels_counts_every_view_separately_and_sums_to_one_sided_holes():
    """Face 0 is half of the cube's z = 0 bottom. Reversed, its normal points INTO the cube, so
    a camera below the cube (looking up, `d_z > 0`) meets its back side and a camera above it
    cannot see it at all."""
    m = cube(10.0)
    m.face_v[0] = m.face_v[0][::-1]
    topo, Pc = _centered(m)
    ids = np.arange(len(topo.face_w))

    per_view = backface_pixels(Pc, topo.face_w, ids, VIEWS_26, _SIZE)

    assert len(per_view) == len(VIEWS_26) == 26
    assert all(isinstance(n, int) for n in per_view)
    assert sum(per_view) == one_sided_holes(Pc, topo.face_w, ids, VIEWS_26, _SIZE) > 0
    for view, n in zip(VIEWS_26, per_view):
        if round(view[2]) == 1:            # looking up at the bottom
            assert n > 0
        if round(view[2]) == -1:           # looking down: the bottom is behind the cube
            assert n == 0


def test_backface_pixels_are_zero_in_every_view_of_a_correctly_wound_cube():
    m = cube(10.0)
    topo, Pc = _centered(m)
    ids = np.arange(len(topo.face_w))
    assert backface_pixels(Pc, topo.face_w, ids, VIEWS_26, _SIZE) == [0] * 26


def test_backface_counts_reads_renders_that_were_already_made():
    """The pipeline renders the reference over the 26 guard views anyway; counting its back
    faces from those buffers must give exactly what a fresh render gives."""
    m = cube(10.0)
    m.face_v[0] = m.face_v[0][::-1]
    m.face_v[5] = m.face_v[5][::-1]
    topo, Pc = _centered(m)
    ids = np.arange(len(topo.face_w))
    rendered = [(v, ortho_first_hit(Pc, topo.face_w, ids, v, Pc, _SIZE)) for v in VIEWS_26]

    assert backface_counts(rendered, face_unit_normals(Pc, topo.face_w)) == \
        backface_pixels(Pc, topo.face_w, ids, VIEWS_26, _SIZE)


# ---------------------------------------------------------------------------
# Brief 11 item 1: a connected near-coplanar sheet is wound consistently, measured in back pixels
# ---------------------------------------------------------------------------

def _sheet_inputs(mesh, n_dirs=32):
    """What `orient_sheets` is handed in `fix_object`: centred welded positions, the faces, their
    side exposures as wound, the per-face verdict's flips and thin sheets, and the depth tolerance
    (1.5 print steps)."""
    topo, Pc = _centered(mesh)
    front, back = compute_side_exposure(Pc, topo.face_w, topo.ok, n_dirs=n_dirs)
    cls = classify_orientation(front, back, topo.ok)
    tol = 1.5 * float(topo.quanta.max())
    return Pc, topo.face_w, front, back, cls == ORIENT_FLIP, cls == ORIENT_THIN_SHEET, topo.ok, tol


def test_a_thin_face_takes_the_winding_of_the_sheet_it_belongs_to():
    """Triage A1 in miniature: the slab's underside is one flat sheet of three cell quads, and the
    middle one -- the floor of a pocket in the top, seen from above as well as from below -- is
    a thin sheet wound UP, while the rest of the underside faces down (cell 2's once the per-face
    flip has turned it). Seen from below it shows its back. The sheet is wound consistently: the
    floor takes the side the whole sheet is more exposed on, and the back pixels of the 26 views
    go down -- measured from one render, since a flip never changes a double-sided render."""
    m = slab_with_a_pocket_in_its_top()
    Pc, faces, front, back, flipped, thin, ok, tol = _sheet_inputs(m)
    assert thin[[6, 7]].all() and flipped[[2, 3, 8, 9]].all()        # the fixture's premise

    result = orient_sheets(Pc, faces, front, back, flipped, thin, ok, tol=tol, size=_SIZE)

    assert np.nonzero(result.flip)[0].tolist() == [6, 7]
    assert result.report["sheets_made_consistent"] == 1
    assert result.report["faces_flipped"] == 2
    before, after = result.report["back_px"]["before"], result.report["back_px"]["after"]
    assert after < before
    # ...and the count is what a fresh render of the re-wound faces gives
    wound = faces.copy()
    turned = flipped | result.flip
    wound[turned] = wound[turned][:, ::-1]
    ids = np.arange(len(faces))
    assert sum(backface_pixels(Pc, wound, ids, VIEWS_26, _SIZE)) == after


def test_a_sheet_is_not_re_wound_where_that_measures_more_back_pixels():
    """The measurement decides: seen only from ABOVE, the pocket's floor shows its front now and
    would show its back once wound with the underside, so the sheet is left as it is."""
    m = slab_with_a_pocket_in_its_top()
    Pc, faces, front, back, flipped, thin, ok, tol = _sheet_inputs(m)

    result = orient_sheets(Pc, faces, front, back, flipped, thin, ok, tol=tol, size=_SIZE,
                           views=[(0.0, 0.0, -1.0)])

    assert not result.flip.any()
    assert result.report["sheets_refused"] == 1
    assert result.report["sheets_made_consistent"] == 0


def test_a_lopsided_face_keeps_its_own_verdict_inside_a_sheet():
    """Only THIN faces follow their sheet. Face 4 (half of cell 0's underside) is handed in as
    seen only from above -- lopsided, its per-face verdict turning it up -- so it disagrees with
    the underside, which the sheet as a whole is more exposed on. It keeps its own verdict: its
    one-sided exposure is evidence, the sheet's total is not. The thin pocket floor is re-wound."""
    m = slab_with_a_pocket_in_its_top()
    Pc, faces, front, back, flipped, thin, ok, tol = _sheet_inputs(m)
    front, back, flipped = front.copy(), back.copy(), flipped.copy()
    front[4], back[4], flipped[4] = 0.0, 0.5, True        # seen from above only: turned up

    result = orient_sheets(Pc, faces, front, back, flipped, thin, ok, tol=tol, size=_SIZE)

    assert np.nonzero(result.flip)[0].tolist() == [6, 7]


def test_a_face_lying_on_another_face_is_never_re_wound():
    """A patch lying ON the pocket's floor, wound the other way, is a coincident pair of opposite
    windings. Re-winding the floor would make the pair look like a duplicate layer to the overlap
    pass -- the operation that is blocked -- so neither the floor nor the patch is touched."""
    m = slab_with_a_pocket_in_its_top(patch_on_floor=True)
    Pc, faces, front, back, flipped, thin, ok, tol = _sheet_inputs(m)
    assert thin[[6, 7]].all()

    result = orient_sheets(Pc, faces, front, back, flipped, thin, ok, tol=tol, size=_SIZE)

    assert not result.flip.any()
    assert result.report["faces_lying_on_another"] == 2
