"""Job P1-K3b item 3: the cover step's cost (carried from the K3 reviews).

* `_meets_shadow`, tested directly on its edge cases: an eye inside or on the box, a direction parallel to an axis,
  a face that only touches the shadow.
* The cull before the per-viewpoint test (a grid over BEFORE's faces, and faces already found are not tested again)
  changes nothing: the candidates equal the exhaustive test's, every face against every viewpoint.
* A block of the cover step stays within its memory budget (at most 500 MB on a real floor).
"""
import tracemalloc

import numpy as np
import pytest

import engine.site_judge as sj
from engine.model import MeshData
from engine.site_judge import SiteJudge, _boxes, _meets_shadow
from engine.tests.test_validate_checks import _looks

BOX_LO, BOX_HI = np.zeros(3), np.ones(3)


def _face(lo, hi):
    return np.array([lo], float), np.array([hi], float)


#: (name, face box, eye or None, direction or None, candidate?)
EDGES = [
    ("eye inside the box: every face, even one behind the eye", ([-11, -11, -11], [-10, -10, -10]),
     [0.5, 0.5, 0.5], None, True),
    ("eye inside the box: a face far ahead", ([10, 10, 10], [11, 11, 11]), [0.5, 0.5, 0.5], None, True),
    ("eye ON the box (its x = 1 side): every face", ([-11, -11, -11], [-10, -10, -10]), [1.0, 0.5, 0.5], None, True),
    ("eye ON a corner of the box", ([30, -5, 7], [31, -4, 8]), [0.0, 0.0, 0.0], None, True),
    ("eye outside: a face beyond the box", ([10, 0.4, 0.4], [11, 0.6, 0.6]), [-5, 0.5, 0.5], None, True),
    ("eye outside: a face between the eye and the box", ([-3, 0.4, 0.4], [-2, 0.6, 0.6]), [-5, 0.5, 0.5], None,
     False),
    ("eye outside: a face behind the eye", ([-10, 0.4, 0.4], [-9, 0.6, 0.6]), [-5, 0.5, 0.5], None, False),
    ("eye outside: a face touching the box's far side", ([1, 0, 0], [2, 1, 1]), [-5, 0.5, 0.5], None, True),
    ("eye outside: a face touching the box's near side only", ([-1, 0, 0], [0, 1, 1]), [-5, 0.5, 0.5], None, True),
    ("direction +z (axis-parallel): a face above", ([0.2, 0.2, 5], [0.8, 0.8, 6]), None, [0, 0, 1], True),
    ("direction +z: a face below", ([0.2, 0.2, -6], [0.8, 0.8, -5]), None, [0, 0, 1], False),
    ("direction +z: a face beside", ([2, 0.2, 5], [3, 0.8, 6]), None, [0, 0, 1], False),
    ("direction +z: a face touching the swept side", ([1, 0, 5], [2, 1, 6]), None, [0, 0, 1], True),
    ("direction +z: a face a hair off the swept side", ([1.001, 0, 5], [2, 1, 6]), None, [0, 0, 1], False),
    ("direction +x: a face touching the swept top", ([5, 0, 1], [6, 1, 2]), None, [1, 0, 0], True),
    ("direction +x: a flat face in the box's own top plane, behind", ([5, 0.2, 1], [6, 0.8, 1]), None, [1, 0, 0],
     True),
    ("diagonal direction: a face along it", ([3, 3, 0], [4, 4, 1]), None, [0.7071067811865476, 0.7071067811865476, 0],
     True),
    ("diagonal direction: a face across from it", ([3, -4, 0], [4, -3, 1]), None,
     [0.7071067811865476, 0.7071067811865476, 0], False),
]


@pytest.mark.parametrize("name, face, eye, direction, expected", EDGES, ids=[e[0] for e in EDGES])
def test_meets_shadow_edge_cases(name, face, eye, direction, expected):
    lo, hi = _face(*face)
    kw = {"eyes": np.array([eye], float)} if eye is not None else {"dirs": np.array([direction], float)}
    assert _meets_shadow(lo, hi, BOX_LO, BOX_HI, **kw).tolist() == [expected], name


def _random_mesh(n, seed, spread=400.0, size=8.0):
    rng = np.random.default_rng(seed)
    centres = rng.uniform(0.0, spread, (n, 3)) * np.array([1.0, 1.0, 0.3])
    tri = centres[:, None, :] + rng.normal(0.0, size, (n, 3, 3))
    return MeshData(name="random", positions=tri.reshape(-1, 3), uvs=np.zeros((0, 2)), normals=np.zeros((0, 3)),
                    face_v=np.arange(3 * n).reshape(n, 3), face_vt=np.full((n, 3), -1), face_vn=np.full((n, 3), -1),
                    face_material=np.zeros(n, np.int64), face_line=np.arange(1, n + 1), materials=["m0"],
                    mtllib=None, coord_decimals=2, sig_digits=6)


def _exhaustive(judge, after, new):
    """The cover step without any cull: every BEFORE face against every box, direction, camera and probe."""
    st = judge.stage
    grow = st.tol + sj.EPS_ORIGIN + sj._SLACK
    found = np.zeros(st.before.n_faces, dtype=bool)
    for lo, hi in _boxes(after.positions[after.face_v[np.unique(new)]], sj._MAX_BOXES):
        for k in range(len(st.dirs)):
            found |= _meets_shadow(st.face_lo, st.face_hi, lo - grow, hi + grow, dirs=st.dirs[k:k + 1])
        for k in range(len(st.viewpoints)):
            found |= _meets_shadow(st.face_lo, st.face_hi, lo - grow, hi + grow, eyes=st.viewpoints[k:k + 1])
    return np.flatnonzero(found)


@pytest.mark.parametrize("seed, n_new, some_left_out", [(1, 1, True), (2, 5, True), (3, 20, True), (5, 3, True),
                                                        (4, 80, False)])
def test_the_culled_cover_candidates_equal_the_exhaustive_shadow_test(seed, n_new, some_left_out):
    """1,500 small random triangles over 2,000 x 2,000 x 600 in (about 90 probes among them); the site is the
    `n_new` faces nearest a random one."""
    mesh = _random_mesh(1500, seed, spread=2000.0, size=4.0)
    judge = SiteJudge(_looks("m0"), settings=sj.Settings(n_directions=24, n_cameras=8))
    judge.begin(mesh)
    centres = mesh.positions[mesh.face_v].mean(axis=1)
    at = centres[np.random.default_rng(seed + 100).integers(mesh.n_faces)]
    new = np.argsort(np.linalg.norm(centres - at, axis=1), kind="stable")[:n_new]
    expected = _exhaustive(judge, mesh, new)
    got = judge.cover_candidates(mesh, new)
    if some_left_out:
        assert 0 < len(expected) < mesh.n_faces, "the fixture must leave some faces out, or the test proves nothing"
    assert got.tolist() == expected.tolist()


def test_a_block_of_the_cover_step_stays_within_its_memory_budget(monkeypatch):
    budget = 4 * 2**20
    monkeypatch.setattr(sj, "_BLOCK_BYTES", budget)
    mesh = _random_mesh(20000, 7, spread=2000.0)
    judge = SiteJudge(_looks("m0"))
    judge.begin(mesh)
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        base, _ = tracemalloc.get_traced_memory()
        judge.cover_candidates(mesh, np.arange(50))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    fixed = 64 * mesh.n_faces                        # per-face bookkeeping of the whole call (ids, masks, cells)
    assert peak - base <= budget + fixed, f"{(peak - base) / 2**20:.1f} MB for a {budget / 2**20:.0f} MB budget"


def test_the_default_block_budget_is_at_most_500_mb():
    assert sj._BLOCK_BYTES <= 500 * 2**20
