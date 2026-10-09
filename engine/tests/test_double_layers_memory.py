"""P1-H1b item 6: the memory of double_layers' big-face pre-filter is bounded, and the answer is unchanged.

The pre-filter compares K big faces with all N faces by bounding box, so it holds K x N booleans (several of them at
once) plus the index arrays of every hit. K used to be a fixed 200, which is 28 M cells per matrix on the largest
unit (142,234 faces). K now shrinks as N grows: K x N never exceeds `BIG_FACE_CELL_BUDGET`.
"""
import tracemalloc

import numpy as np
import pytest

from engine.fixes import overlap
from engine.fixes.overlap import double_layers, double_layers_reference
from engine.guard.views import VIEWS_26

SIZE = (90, 60)


def test_k_shrinks_as_n_grows_and_never_exceeds_the_old_200():
    rows = overlap.big_face_block_rows
    assert rows(1_000) == 200                                           # small units keep the old block
    assert rows(142_234) < 200                                          # the largest unit gets a smaller one
    assert rows(10**9) == 1                                             # never below one row
    for n in (1, 10, 5_000, 20_000, 91_714, 142_234, 1_000_000):
        k = rows(n)
        assert 1 <= k <= 200
        assert k * n <= max(overlap.BIG_FACE_CELL_BUDGET, n)            # K x N is bounded (one row at worst)
    assert rows(142_234, budget=1_000_000) == 7
    with pytest.raises(ValueError):
        rows(100, budget=0)


def _scene(n_small, n_big, seed=0):
    """`n_small` small bounding boxes in a 1000 in square, `n_big` big ones over the whole square (all overlap all)."""
    rng = np.random.default_rng(seed)
    lo = rng.uniform(0, 1000, (n_small, 3)); lo[:, 2] = rng.uniform(0, 5, n_small)
    hi = lo + rng.uniform(0.5, 2.0, (n_small, 3))
    big_lo = np.tile([0.0, 0.0, 0.0], (n_big, 1)); big_hi = np.tile([1000.0, 1000.0, 5.0], (n_big, 1))
    lo, hi = np.vstack([big_lo, lo]), np.vstack([big_hi, hi])
    ids = np.arange(len(lo))
    ids_big = ids[:n_big]
    is_big = np.zeros(len(lo), bool); is_big[ids_big] = True
    return lo, hi, ids, ids_big, is_big


def _pairs(gen):
    out = set()
    for fa, fb in gen:
        assert (fa < fb).all()
        out.update(zip(fa.tolist(), fb.tolist()))
    return out


def test_the_same_pairs_whatever_the_budget():
    lo, hi, ids, ids_big, is_big = _scene(400, 9)
    reference = _pairs(overlap._big_face_pairs(lo, hi, ids, ids_big, is_big, budget=10**9))   # one block, K = 9
    assert len(reference) == 9 * 400 + 9 * 8 // 2                                             # every pair, once
    for budget in (1, 399, 400, 1_000, 5_000):
        assert _pairs(overlap._big_face_pairs(lo, hi, ids, ids_big, is_big, budget=budget)) == reference


def test_the_peak_memory_follows_the_budget_not_n_times_200():
    lo, hi, ids, ids_big, is_big = _scene(60_000, 120)
    peaks = {}
    for budget in (500_000, 6_000_000):
        tracemalloc.start()
        total = sum(len(fa) for fa, _fb in overlap._big_face_pairs(lo, hi, ids, ids_big, is_big, budget=budget))
        peaks[budget] = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        assert total == 120 * 60_000 + 120 * 119 // 2
    assert peaks[500_000] < 0.25 * peaks[6_000_000], peaks             # a smaller budget really holds less
    assert peaks[500_000] < 80 * 500_000, peaks                        # worst case (every box hits): ~70 bytes a cell


def _giant_scene():
    """Giant faces (they span many cells) over a field of small faces, in three layers 0.05 apart."""
    P, F = [], []

    def tri(a, b, c):
        n = len(P)
        P.extend([a, b, c])
        F.append([n, n + 1, n + 2])
    for z in (0.0, 0.05, 0.1):
        tri([-250, -250, z], [250, -250, z], [0, 250, z])
        tri([-250, 250, z], [250, -250, z], [250, 250, z])
    for k in range(40):
        x = -20.0 + (k % 10) * 4.0
        y = -6.0 + (k // 10) * 4.0
        tri([x, y, 0.02], [x + 2.0, y, 0.02], [x, y + 2.0, 0.02])
    return np.array(P, float), np.array(F, np.int64)


@pytest.mark.parametrize("budget", [1, 50, 10_000, None])
def test_the_answer_equals_the_reference_for_any_budget(budget):
    P, F = _giant_scene()
    centre = (P.min(axis=0) + P.max(axis=0)) / 2
    kw = {} if budget is None else {"big_face_budget": budget}
    stats = {}
    new = double_layers(P - centre, F, 0.15, VIEWS_26, SIZE, centre=centre, stats=stats, **kw)
    old = double_layers_reference(P - centre, F, 0.15, VIEWS_26, SIZE, centre=centre)
    assert stats["big_faces"] >= 6 and old["count"] > 6
    assert new == old
