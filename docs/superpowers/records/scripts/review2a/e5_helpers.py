import numpy as np, shapely
import engine.detectors.fragments as fr

rng = np.random.default_rng(7)
bad_pairs = 0
for trial in range(40):
    n = int(rng.integers(2, 300))
    lo = rng.uniform(0, 100, (n, 3)); hi = lo + rng.uniform(0, 15, (n, 3))
    if trial % 3 == 0:
        lo[:, 0] = np.round(lo[:, 0]); hi[:, 0] = lo[:, 0] + np.round(rng.uniform(0, 5, n))  # ties along x
    for block in (2_000_000, 7, 1):
        fr._PAIR_BLOCK = block
        got = {tuple(sorted(p)) for p in fr._box_pairs(lo, hi).tolist()}
        n_got = len(fr._box_pairs(lo, hi))
        want = {(i, j) for i in range(n) for j in range(i + 1, n)
                if np.all(lo[j] <= hi[i]) and np.all(lo[i] <= hi[j])}
        if got != want or n_got != len(want):
            bad_pairs += 1
print("box_pairs mismatches:", bad_pairs)
fr._PAIR_BLOCK = 2_000_000

A = rng.uniform(0, 10, (4000, 3, 2)); B = A + rng.uniform(-6, 6, (4000, 1, 2)) + rng.uniform(-2, 2, (4000, 3, 2))
gap = fr._triangle_gap(A, B)
ref = np.array([shapely.Polygon(a).distance(shapely.Polygon(b)) for a, b in zip(A, B)])
err = np.abs(gap - ref)
print("triangle_gap max abs error vs shapely:", float(err.max()), " n with error > 1e-9:", int((err > 1e-9).sum()),
      " zero-gap agreement:", int(((gap == 0) == (ref < 1e-12)).sum()), "/", len(A))
