### Task 6: Weld, quantum, degenerates, edges, T-vertices

**Files:** Create `engine\topo\weld.py`, `engine\topo\adjacency.py`, `engine\tests\test_topo_basics.py`

**Interfaces — Produces:**
`weld_exact(positions, decimals) -> tuple[np.ndarray, np.ndarray]` (unique positions, remap `(V,)`),
`axis_quanta(positions, sig_digits) -> np.ndarray (3,)`,
`degenerate_mask(positions_w, face_w) -> np.ndarray[bool]`,
`EdgeTable(edges (E,2) i64 a<b, counts (E,), face_edges (F,3) i64, -1 for excluded faces)`,
`build_edge_table(face_w, include) -> EdgeTable`, `edge_face_lists(table) -> list[np.ndarray]`,
`find_t_vertices(positions_w, table, tol) -> dict[int, np.ndarray]` (open edge index -> welded vertex ids ordered from `edges[e][0]` to `edges[e][1]`).

- [ ] **Step 1: failing test**

```python
import numpy as np

from engine.tests.fixtures.build import cube, grid_slab, t_junction_strip
from engine.topo.adjacency import build_edge_table, degenerate_mask, edge_face_lists, find_t_vertices
from engine.topo.weld import axis_quanta, weld_exact


def test_weld_merges_printed_duplicates_and_negative_zero():
    P = np.array([[0.0, 1.0, 2.0], [-0.0, 1.0, 2.0], [0.004, 1.0, 2.0], [5.0, 5.0, 5.0]])
    uniq, remap = weld_exact(P, decimals=2)
    assert len(uniq) == 2 and remap.tolist()[:3] == [remap[0]] * 3 and remap[3] != remap[0]


def test_axis_quanta_follow_magnitude():
    P = np.array([[3293.33, 24204.9, 2114.17], [980.11, 22651.0, 1779.53]])
    assert np.allclose(axis_quanta(P, sig_digits=6), [0.01, 0.1, 0.01])


def test_cube_edges():
    m = cube()
    P, remap = weld_exact(m.positions, 2)
    fw = remap[m.face_v]
    ok = ~degenerate_mask(P, fw)
    t = build_edge_table(fw, ok)
    assert ok.all() and len(t.edges) == 18 and (t.counts == 2).all()
    assert all(len(f) == 2 for f in edge_face_lists(t))


def test_grid_slab_open_edges():
    m = grid_slab(10, 10)
    P, remap = weld_exact(m.positions, 2)
    t = build_edge_table(remap[m.face_v], np.ones(200, bool))
    assert len(t.edges) == 320 and int((t.counts == 1).sum()) == 40


def test_t_junction_found():
    m = t_junction_strip()
    P, remap = weld_exact(m.positions, 2)
    fw = remap[m.face_v]
    deg = degenerate_mask(P, fw)
    assert deg.tolist() == [False] * 6 + [True]
    t = build_edge_table(fw, ~deg)
    assert (t.face_edges[6] == -1).all()
    tv = find_t_vertices(P, t, tol=0.015)
    assert len(tv) == 1
    (e, verts), = tv.items()
    assert sorted(P[t.edges[e]][:, 0].tolist()) == [0.0, 20.0] and P[verts[0]].tolist() == [10.0, 10.0, 0.0]
```

Run. Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 2: `engine\topo\weld.py`**

```python
import math

import numpy as np


def weld_exact(positions: np.ndarray, decimals: int) -> tuple[np.ndarray, np.ndarray]:
    rounded = np.round(positions, decimals) + 0.0  # + 0.0 folds -0.0 into 0.0
    uniq, inverse = np.unique(rounded, axis=0, return_inverse=True)
    return uniq, inverse.reshape(-1).astype(np.int64)


def axis_quanta(positions: np.ndarray, sig_digits: int) -> np.ndarray:
    max_abs = np.abs(positions).max(axis=0)
    return np.array([10.0 ** (math.ceil(math.log10(max(a, 1e-9))) - sig_digits) for a in max_abs])
```

- [ ] **Step 3: `engine\topo\adjacency.py`**

```python
from dataclasses import dataclass

import numpy as np


@dataclass
class EdgeTable:
    edges: np.ndarray
    counts: np.ndarray
    face_edges: np.ndarray


def degenerate_mask(positions_w: np.ndarray, face_w: np.ndarray) -> np.ndarray:
    p = positions_w[face_w]
    area = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    longest = np.linalg.norm(p - np.roll(p, -1, axis=1), axis=2).max(axis=1)
    return area <= 1e-7 * np.maximum(longest, 1e-300) ** 2


def build_edge_table(face_w: np.ndarray, include: np.ndarray) -> EdgeTable:
    pairs = np.sort(np.stack([face_w[:, [0, 1]], face_w[:, [1, 2]], face_w[:, [2, 0]]], axis=1), axis=2)
    edges, inverse, counts = np.unique(pairs[include].reshape(-1, 2), axis=0, return_inverse=True, return_counts=True)
    face_edges = np.full((face_w.shape[0], 3), -1, np.int64)
    face_edges[include] = inverse.reshape(-1, 3)
    return EdgeTable(edges.astype(np.int64), counts.astype(np.int64), face_edges)


def edge_face_lists(table: EdgeTable) -> list[np.ndarray]:
    fe = table.face_edges.reshape(-1)
    faces = np.repeat(np.arange(table.face_edges.shape[0]), 3)
    keep = fe >= 0
    fe, faces = fe[keep], faces[keep]
    order = np.argsort(fe, kind="stable")
    splits = np.cumsum(np.bincount(fe, minlength=len(table.edges)))[:-1]
    return np.split(faces[order], splits)


def find_t_vertices(positions_w: np.ndarray, table: EdgeTable, tol: float) -> dict[int, np.ndarray]:
    open_idx = np.nonzero(table.counts == 1)[0]
    if len(open_idx) == 0:
        return {}
    cand = np.unique(table.edges[open_idx])
    P = positions_w[cand]
    out = {}
    for e in open_idx:
        a, b = table.edges[e]
        A, ab = positions_w[a], positions_w[b] - positions_w[a]
        t = ((P - A) @ ab) / (ab @ ab)
        d = np.linalg.norm((P - A) - np.outer(t, ab), axis=1)
        hit = (t > 1e-9) & (t < 1 - 1e-9) & (d <= tol) & (cand != a) & (cand != b)
        if hit.any():
            out[int(e)] = cand[hit][np.argsort(t[hit])]
    return out
```

- [ ] **Step 4:** Run tests. Expected: `5 passed`.
- [ ] **Step 5:** Commit `feat(engine): exact weld, per-axis quantum, edge table, T-vertices`.

---

