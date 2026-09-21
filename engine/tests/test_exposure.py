import numpy as np

from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import box_with_partition, cube, open_box_with_cells
from engine.vis.exposure import (BARY, EPS_IN, EXP_DEGENERATE, EXP_HIDDEN, EXP_OUTSIDE, EXP_SLIT,
                                  classify_exposure, compute_exposure, compute_side_exposure, fib_dirs)


def _centered(mesh):
    """analyse_topology + recentre positions_w to the bbox centre, as compute_exposure requires."""
    topo = analyse_topology(mesh)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2
    return topo, topo.positions_w - centre


def test_fib_dirs_returns_n_unit_vectors():
    d = fib_dirs(32)
    assert d.shape == (32, 3)
    assert np.allclose(np.linalg.norm(d, axis=1), 1.0, atol=1e-9)


def test_bary_is_centroid_plus_three_biased_corners():
    assert BARY.shape == (4, 3)
    assert np.allclose(BARY[0], [1 / 3, 1 / 3, 1 / 3])
    rest = sorted(BARY[1:].tolist())
    assert rest == sorted([[0.6, 0.2, 0.2], [0.2, 0.6, 0.2], [0.2, 0.2, 0.6]])
    assert np.allclose(BARY.sum(axis=1), 1.0)


def test_eps_in_value():
    assert EPS_IN == 0.02


def test_compute_exposure_is_deterministic():
    topo, Pc = _centered(box_with_partition())
    first = compute_exposure(Pc, topo.face_w, topo.ok, n_dirs=16)
    second = compute_exposure(Pc, topo.face_w, topo.ok, n_dirs=16)
    assert np.array_equal(first, second)


def test_box_with_partition_inner_faces_hidden_outer_faces_outside():
    m = box_with_partition()
    topo, Pc = _centered(m)
    assert topo.ok.all()  # no degenerate faces in this fixture
    exposure = compute_exposure(Pc, topo.face_w, topo.ok, n_dirs=32)
    cls = classify_exposure(exposure, topo.ok, slit_threshold=0.05)

    # cube()'s 12 outer tris come first; the partition's 2 tris were appended after.
    assert exposure[12] == 0.0 and exposure[13] == 0.0
    assert cls[12] == EXP_HIDDEN and cls[13] == EXP_HIDDEN
    assert (cls[:12] == EXP_OUTSIDE).all()
    assert (exposure[:12] > 0.05).all()


def test_open_box_with_cells_deep_partition_less_exposed_than_near_both_nonzero():
    m = open_box_with_cells()
    topo, Pc = _centered(m)
    assert topo.ok.all()
    exposure = compute_exposure(Pc, topo.face_w, topo.ok, n_dirs=64)
    cls = classify_exposure(exposure, topo.ok, slit_threshold=0.05)

    # Fixture face order: 5 box quads (10 tris, indices 0-9), near partition (10-11), deep (12-13).
    near = exposure[10:12]
    deep = exposure[12:14]
    assert (near > 0).all()
    assert (deep > 0).all()
    assert deep.max() < near.min()
    assert (cls[:10] == EXP_OUTSIDE).all()


def test_classify_exposure_degenerate_faces_use_ok_mask_not_exposure_value():
    exposure = np.array([0.0, 0.0, 0.3])
    ok = np.array([True, False, True])
    cls = classify_exposure(exposure, ok, slit_threshold=0.05)
    assert cls.tolist() == [EXP_HIDDEN, EXP_DEGENERATE, EXP_OUTSIDE]


def test_classify_exposure_slit_band():
    exposure = np.array([0.0, 0.01, 0.05, 0.2])
    ok = np.ones(4, dtype=bool)
    cls = classify_exposure(exposure, ok, slit_threshold=0.05)
    assert cls.tolist() == [EXP_HIDDEN, EXP_SLIT, EXP_OUTSIDE, EXP_OUTSIDE]


# ---------------------------------------------------------------------------------------------
# Task 8: compute_side_exposure -- front/back split; compute_exposure must keep returning EXACTLY
# what it returned before this task (pinned below against both fixtures' own hardcoded numbers,
# which are unchanged from before this task, and against compute_side_exposure's own sum).
# ---------------------------------------------------------------------------------------------

def test_compute_side_exposure_sums_to_exactly_compute_exposure():
    for n_dirs in (16, 32, 64):
        topo, Pc = _centered(box_with_partition())
        front, back = compute_side_exposure(Pc, topo.face_w, topo.ok, n_dirs=n_dirs)
        exposure = compute_exposure(Pc, topo.face_w, topo.ok, n_dirs=n_dirs)
        assert front.shape == exposure.shape and back.shape == exposure.shape
        assert np.array_equal(front + back, exposure)


def test_compute_exposure_pinned_unchanged_on_box_with_partition():
    """compute_exposure's own numbers on this fixture, exactly as pinned by
    test_box_with_partition_inner_faces_hidden_outer_faces_outside above, must still hold after
    compute_exposure became a thin wrapper over compute_side_exposure."""
    topo, Pc = _centered(box_with_partition())
    exposure = compute_exposure(Pc, topo.face_w, topo.ok, n_dirs=32)
    assert exposure[12] == 0.0 and exposure[13] == 0.0
    assert (exposure[:12] > 0.05).all()


def test_compute_side_exposure_zero_for_degenerate_faces():
    topo, Pc = _centered(box_with_partition())
    ok = topo.ok.copy()
    ok[0] = False  # pretend face 0 is degenerate
    front, back = compute_side_exposure(Pc, topo.face_w, ok, n_dirs=16)
    assert front[0] == 0.0 and back[0] == 0.0


def test_compute_side_exposure_outer_cube_faces_are_front_only_hidden_faces_are_neither():
    """A correctly-wound outer cube face's exterior is its FRONT side (open space escapes there);
    its interior (BACK) is always blocked by the opposite wall of the solid box. The fully-sealed
    interior partition escapes on neither side."""
    m = box_with_partition()
    topo, Pc = _centered(m)
    front, back = compute_side_exposure(Pc, topo.face_w, topo.ok, n_dirs=32)
    assert (front[:12] > 0.0).all()
    assert (back[:12] == 0.0).all()
    assert front[12] == 0.0 and back[12] == 0.0
    assert front[13] == 0.0 and back[13] == 0.0


def test_compute_side_exposure_reversed_face_is_back_only():
    """Reversing a face's winding swaps which side is 'front': the geometric normal now points
    into the solid, so the side that used to be BACK (blocked) becomes FRONT (still blocked, since
    it now points inward) and the side that used to be FRONT (open space) becomes BACK."""
    m = cube(10.0)
    m.face_v[0] = m.face_v[0][::-1]  # reverse one outer face's winding
    topo, Pc = _centered(m)
    front, back = compute_side_exposure(Pc, topo.face_w, topo.ok, n_dirs=32)
    assert front[0] == 0.0
    assert back[0] > 0.0
