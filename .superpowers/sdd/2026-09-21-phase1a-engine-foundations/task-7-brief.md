### Task 7: Regions, edge classes, `analyse_topology`

**Files:** Create `engine\topo\planes.py`, `engine\topo\edges.py`, `engine\pipeline.py`, `engine\tests\test_regions.py`

**Interfaces — Consumes:** Task 6 functions.
**Produces:**
`plane_basis(n) -> (e1, e2)`, `cluster_planes(tri, normals, area, material, ok, quanta, facing_dot=0.9, tol_quanta=1.5) -> (label (F,), planes list[(n, p0, tol)])`,
`fit_uv(xy, uv) -> (J (2,2), o (2,))`, `cluster_uv(xy, uv, area, uv_tol=0.02, max_refit=6) -> (label, fits)`,
`build_regions(mesh, positions_w, face_w, ok, table, t_vertices, quanta, flat_materials: set[int], uv_tol=0.02) -> np.ndarray` (`face_region (F,)`, -1 for excluded),
`EDGE_REAL=0, EDGE_REMOVABLE=1, EDGE_OPEN=2, EDGE_NONMANIFOLD=3, EDGE_TJUNCTION=4`,
`classify_edges(table, face_region, t_vertices) -> np.ndarray[uint8]`,
`Topology(positions_w, face_w, ok, quanta, table, t_vertices, face_region, edge_class)`,
`analyse_topology(mesh, flat_materials=frozenset()) -> Topology`, `topology_stats(topo) -> dict`.

`plane_basis`, `cluster_planes`, `fit_uv`, `cluster_uv` are **ported verbatim from `spike\_region.py`**, which
already ran on both real files. Only change: module constants `UV_TOL`, `FACING_DOT`, `DIST_TOL_QUANTA`,
`MAX_REFIT` become the keyword arguments listed above, and `cluster_uv` returns `fits` as `list[(J, o)]`.

- [ ] **Step 1: failing test**

```python
import numpy as np

from engine.pipeline import analyse_topology, topology_stats
from engine.tests.fixtures.build import cube, grid_slab, t_junction_strip
from engine.topo.edges import EDGE_OPEN, EDGE_REAL, EDGE_REMOVABLE


def regions(topo):
    return len(set(topo.face_region[topo.face_region >= 0].tolist()))


def test_cube_has_six_regions_and_six_removable_diagonals():
    t = analyse_topology(cube())
    assert regions(t) == 6
    assert int((t.edge_class == EDGE_REMOVABLE).sum()) == 6 and int((t.edge_class == EDGE_REAL).sum()) == 12


def test_grid_slab_is_one_region():
    t = analyse_topology(grid_slab(10, 10))
    assert regions(t) == 1
    assert int((t.edge_class == EDGE_REMOVABLE).sum()) == 280 and int((t.edge_class == EDGE_OPEN).sum()) == 40


def test_whole_tile_uv_shift_does_not_split():
    assert regions(analyse_topology(grid_slab(10, 10, shift_cols=(3, 4)))) == 1


def test_real_uv_seam_splits_patterned_texture_only():
    m = grid_slab(10, 10, break_col=5)
    assert regions(analyse_topology(m)) == 2
    assert regions(analyse_topology(m, flat_materials=frozenset({0}))) == 1


def test_material_change_splits():
    m = grid_slab(10, 10)
    m.materials, m.face_material = ["a", "b"], np.array([0] * 100 + [1] * 100)
    assert regions(analyse_topology(m)) == 2


def test_t_junction_joins_one_region_and_edges_are_removable():
    t = analyse_topology(t_junction_strip())
    assert regions(t) == 1 and t.face_region[6] == -1
    assert topology_stats(t)["t_junction_edges"] == 0
    # 3 quad diagonals + edge shared by the two upper quads + long edge + its 2 sub-edges
    assert int((t.edge_class == EDGE_REMOVABLE).sum()) == 7
```

Run. Expected: FAIL, `ModuleNotFoundError: engine.pipeline`.

- [ ] **Step 2: `engine\topo\planes.py`** — port the four functions from `spike\_region.py` as described, then add:

```python
def build_regions(mesh, positions_w, face_w, ok, table, t_vertices, quanta, flat_materials, uv_tol=0.02):
    tri = positions_w[face_w]
    cr = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    norm = np.linalg.norm(cr, axis=1)
    area = 0.5 * norm
    normals = np.zeros_like(cr)
    normals[ok] = cr[ok] / norm[ok, None]
    uv_all = np.zeros((mesh.n_faces, 3, 2))
    has_uv = (mesh.face_vt >= 0).all(axis=1)
    if len(mesh.uvs):
        uv_all[has_uv] = mesh.uvs[mesh.face_vt[has_uv]]

    plabel, planes = cluster_planes(tri, normals, area, mesh.face_material, ok, quanta)
    group = np.full(mesh.n_faces, -1, np.int64)
    next_group = 0
    for pi, (n, p0, _tol) in enumerate(planes):
        members = np.nonzero(plabel == pi)[0]
        if int(mesh.face_material[members[0]]) in flat_materials:
            group[members] = next_group
            next_group += 1
            continue
        e1, e2 = plane_basis(n)
        xy = np.stack([(tri[members] - p0) @ e1, (tri[members] - p0) @ e2], axis=2)
        ulabel, fits = cluster_uv(xy, uv_all[members], area[members], uv_tol)
        group[members] = next_group + ulabel
        next_group += len(fits)

    # connected components inside a group: faces sharing an edge, or meeting across a T-junction chain
    parent = np.arange(mesh.n_faces)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    from engine.topo.adjacency import edge_face_lists
    ef = edge_face_lists(table)
    lookup = {(int(a), int(b)): i for i, (a, b) in enumerate(table.edges)}

    def join(faces):
        faces = [f for f in faces if group[f] >= 0]
        for f in faces[1:]:
            if group[f] == group[faces[0]]:
                parent[find(f)] = find(faces[0])

    for faces in ef:
        join(list(faces))
    for e, verts in t_vertices.items():
        a, b = table.edges[e]
        chain = [int(a), *[int(v) for v in verts], int(b)]
        faces = list(ef[e])
        for p, q in zip(chain, chain[1:]):
            s = lookup.get((min(p, q), max(p, q)))
            if s is not None:
                faces += list(ef[s])
        join(faces)

    face_region = np.full(mesh.n_faces, -1, np.int64)
    roots = {}
    for f in np.nonzero(group >= 0)[0]:
        face_region[f] = roots.setdefault(find(f), len(roots))
    return face_region
```

- [ ] **Step 3: `engine\topo\edges.py`**

```python
import numpy as np

from engine.topo.adjacency import EdgeTable, edge_face_lists

EDGE_REAL, EDGE_REMOVABLE, EDGE_OPEN, EDGE_NONMANIFOLD, EDGE_TJUNCTION = 0, 1, 2, 3, 4


def classify_edges(table: EdgeTable, face_region: np.ndarray, t_vertices: dict) -> np.ndarray:
    cls = np.full(len(table.edges), EDGE_REAL, np.uint8)
    cls[table.counts == 1] = EDGE_OPEN
    cls[table.counts >= 3] = EDGE_NONMANIFOLD
    ef = edge_face_lists(table)
    for e in np.nonzero(table.counts == 2)[0]:
        f0, f1 = ef[e]
        if face_region[f0] >= 0 and face_region[f0] == face_region[f1]:
            cls[e] = EDGE_REMOVABLE
    lookup = {(int(a), int(b)): i for i, (a, b) in enumerate(table.edges)}
    for e, verts in t_vertices.items():
        a, b = table.edges[e]
        chain = [int(a), *[int(v) for v in verts], int(b)]
        subs = [lookup.get((min(p, q), max(p, q))) for p, q in zip(chain, chain[1:])]
        faces = list(ef[e]) + [f for s in subs if s is not None for f in ef[s]]
        regions = {int(face_region[f]) for f in faces}
        whole = all(s is not None for s in subs) and len(regions) == 1 and -1 not in regions
        kind = EDGE_REMOVABLE if whole else EDGE_TJUNCTION
        cls[e] = kind
        for s in subs:
            if s is not None and table.counts[s] == 1:
                cls[s] = kind
    return cls
```

- [ ] **Step 4: `engine\pipeline.py`**

```python
from dataclasses import dataclass

import numpy as np

from engine.model import MeshData
from engine.topo.adjacency import EdgeTable, build_edge_table, degenerate_mask, find_t_vertices
from engine.topo.edges import (EDGE_NONMANIFOLD, EDGE_OPEN, EDGE_REAL, EDGE_REMOVABLE, EDGE_TJUNCTION,
                               classify_edges)
from engine.topo.planes import build_regions
from engine.topo.weld import axis_quanta, weld_exact


@dataclass
class Topology:
    positions_w: np.ndarray
    face_w: np.ndarray
    ok: np.ndarray
    quanta: np.ndarray
    table: EdgeTable
    t_vertices: dict
    face_region: np.ndarray
    edge_class: np.ndarray


def analyse_topology(mesh: MeshData, flat_materials=frozenset()) -> Topology:
    positions_w, remap = weld_exact(mesh.positions, mesh.coord_decimals)
    face_w = remap[mesh.face_v]
    ok = ~degenerate_mask(positions_w, face_w)
    quanta = axis_quanta(positions_w, mesh.sig_digits)
    table = build_edge_table(face_w, ok)
    t_vertices = find_t_vertices(positions_w, table, tol=1.5 * float(quanta.max()))
    face_region = build_regions(mesh, positions_w, face_w, ok, table, t_vertices, quanta, set(flat_materials))
    return Topology(positions_w, face_w, ok, quanta, table, t_vertices, face_region,
                    classify_edges(table, face_region, t_vertices))


def topology_stats(t: Topology) -> dict:
    c = t.edge_class
    return {
        "faces": int(len(t.face_w)), "zero_area_faces": int((~t.ok).sum()),
        "welded_vertices": int(len(t.positions_w)), "axis_quanta": t.quanta.tolist(),
        "regions": int(len(set(t.face_region[t.face_region >= 0].tolist()))),
        "edges": int(len(c)), "real_edges": int((c == EDGE_REAL).sum()),
        "removable_edges": int((c == EDGE_REMOVABLE).sum()), "open_edges": int((c == EDGE_OPEN).sum()),
        "nonmanifold_edges": int((c == EDGE_NONMANIFOLD).sum()), "t_junction_edges": int((c == EDGE_TJUNCTION).sum()),
        "edges_with_t_vertices": int(len(t.t_vertices)),
    }
```

- [ ] **Step 5:** Run `.venv\Scripts\python.exe -m pytest engine/tests/test_regions.py -q`. Expected: `6 passed`.
- [ ] **Step 6: real-data check.** Run `analyse_topology` on the Task 5 snapshot with `flat_materials` = materials whose
  flatness < 8.0, print `topology_stats`. Expected: `faces 4692`, `zero_area_faces 217`, `welded_vertices 1589`,
  `axis_quanta [0.01, 0.1, 0.01]`, `nonmanifold_edges` > 1,000. Record the numbers in the commit message.
- [ ] **Step 7:** Commit `feat(engine): planar regions, edge classes, analyse_topology`.

---

