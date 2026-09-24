### Task 1: Scaffold + fixtures

**Files:** Create `pyproject.toml`, `engine\__init__.py`, `engine\io\__init__.py`, `engine\topo\__init__.py`,
`engine\transport\__init__.py`, `engine\tests\__init__.py`, `engine\tests\fixtures\__init__.py`,
`engine\model.py`, `engine\tests\fixtures\build.py`, `engine\tests\test_fixtures.py`

**Interfaces — Produces:**
`MeshData(name, positions(V,3) f64, uvs(T,2) f64, normals(N,3) f64, face_v(F,3) i64, face_vt(F,3) i64 (-1 absent),
face_vn(F,3) i64 (-1 absent), face_material(F,) i64 (-1 none), face_line(F,) i64 (1-based), materials: list[str],
mtllib: str|None, coord_decimals: int, sig_digits: int, units="inches")` with `.n_faces`, `.bbox()`.
Fixtures: `cube(size=10.0)`, `grid_slab(nx=10, ny=10, cell=10.0, uv_per_unit=0.05, shift_cols=(), break_col=None)`,
`t_junction_strip()`.

- [ ] **Step 1: `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "uc-model-fixer"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["numpy>=2.0", "shapely>=2.1", "pillow>=10"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
include = ["engine*", "api*"]

[tool.pytest.ini_options]
testpaths = ["engine/tests"]
```

Run: `.venv\Scripts\python.exe -m pip install -e ".[dev]"`. Expected: `Successfully installed ... uc-model-fixer-0.1.0`.

- [ ] **Step 2: failing test `engine\tests\test_fixtures.py`**

```python
import numpy as np
from engine.tests.fixtures.build import cube, grid_slab, t_junction_strip


def test_cube_is_12_outward_triangles():
    m = cube(10.0)
    assert m.n_faces == 12 and m.positions.shape == (8, 3)
    p = m.positions[m.face_v]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    centre = m.positions.mean(axis=0)
    assert (np.einsum("ij,ij->i", n, p.mean(axis=1) - centre) > 0).all()


def test_grid_slab_counts():
    m = grid_slab(10, 10)
    assert m.n_faces == 200 and m.positions.shape == (121, 3) and m.uvs.shape == (400, 2)


def test_t_junction_strip_has_one_zero_area_face():
    m = t_junction_strip()
    p = m.positions[m.face_v]
    area = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    assert m.n_faces == 7 and int((area == 0).sum()) == 1
```

Run: `.venv\Scripts\python.exe -m pytest engine/tests/test_fixtures.py -q`. Expected: FAIL, `ModuleNotFoundError: engine.tests.fixtures.build`.

- [ ] **Step 3: `engine\model.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MeshData:
    name: str
    positions: np.ndarray
    uvs: np.ndarray
    normals: np.ndarray
    face_v: np.ndarray
    face_vt: np.ndarray
    face_vn: np.ndarray
    face_material: np.ndarray
    face_line: np.ndarray
    materials: list[str]
    mtllib: str | None
    coord_decimals: int
    sig_digits: int
    units: str = "inches"

    @property
    def n_faces(self) -> int:
        return int(self.face_v.shape[0])

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return self.positions.min(axis=0), self.positions.max(axis=0)
```

- [ ] **Step 4: `engine\tests\fixtures\build.py`**

```python
import numpy as np

from engine.model import MeshData


def _mesh(name, positions, uvs, face_v, face_vt, materials=("m0",), face_material=None):
    f = len(face_v)
    return MeshData(
        name=name, positions=np.asarray(positions, float), uvs=np.asarray(uvs, float).reshape(-1, 2),
        normals=np.zeros((0, 3)), face_v=np.asarray(face_v, np.int64), face_vt=np.asarray(face_vt, np.int64),
        face_vn=np.full((f, 3), -1, np.int64),
        face_material=np.zeros(f, np.int64) if face_material is None else np.asarray(face_material, np.int64),
        face_line=np.arange(1, f + 1, dtype=np.int64), materials=list(materials), mtllib=None,
        coord_decimals=2, sig_digits=6)


def cube(size=10.0):
    s = size
    P = np.array([[0, 0, 0], [s, 0, 0], [s, s, 0], [0, s, 0], [0, 0, s], [s, 0, s], [s, s, s], [0, s, s]], float)
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (3, 0, 4, 7)]
    uvs, fv, fvt = [], [], []
    for q in quads:
        pts = P[list(q)]
        keep = [a for a in range(3) if np.ptp(pts[:, a]) > 0]
        base = len(uvs)
        uvs.extend((pts[:, keep] * 0.1).tolist())
        fv += [[q[0], q[1], q[2]], [q[0], q[2], q[3]]]
        fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    return _mesh("cube", P, uvs, fv, fvt)


def grid_slab(nx=10, ny=10, cell=10.0, uv_per_unit=0.05, shift_cols=(), break_col=None):
    """Flat z=0 slab, shared positions, 4 private UVs per cell.
    shift_cols: columns whose UVs are shifted by a whole number of tiles (invisible seam).
    break_col:  columns >= break_col get a +0.37 non-integer UV offset (real seam)."""
    P = [[i * cell, j * cell, 0.0] for j in range(ny + 1) for i in range(nx + 1)]
    vid = lambda i, j: j * (nx + 1) + i
    uvs, fv, fvt = [], [], []
    for j in range(ny):
        for i in range(nx):
            shift = np.array([3.0, -2.0]) if i in shift_cols else np.zeros(2)
            if break_col is not None and i >= break_col:
                shift = shift + 0.37
            corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            base = len(uvs)
            uvs.extend([(np.array([a * cell, b * cell]) * uv_per_unit + shift).tolist() for a, b in corners])
            v = [vid(a, b) for a, b in corners]
            fv += [[v[0], v[1], v[2]], [v[0], v[2], v[3]]]
            fvt += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    return _mesh("grid_slab", P, uvs, fv, fvt)


def t_junction_strip():
    """Big quad 20x10 below, two 10x10 quads above. Vertex (10,10) sits mid-edge of the big quad's top edge.
    One zero-area stitching triangle (0,10)-(10,10)-(20,10), as SketchUp exports them."""
    P = [[0, 0, 0], [20, 0, 0], [20, 10, 0], [0, 10, 0], [10, 10, 0], [0, 20, 0], [10, 20, 0], [20, 20, 0]]
    fv = [[0, 1, 2], [0, 2, 3], [3, 4, 6], [3, 6, 5], [4, 2, 7], [4, 7, 6], [3, 4, 2]]
    uvs = (np.asarray(P, float)[:, :2] * 0.05).tolist()
    return _mesh("t_strip", P, uvs, fv, fv)
```

- [ ] **Step 5:** Run `.venv\Scripts\python.exe -m pytest engine/tests/test_fixtures.py -q`. Expected: `3 passed`.
- [ ] **Step 6:** Commit `feat(engine): MeshData and synthetic fixtures`.

---

