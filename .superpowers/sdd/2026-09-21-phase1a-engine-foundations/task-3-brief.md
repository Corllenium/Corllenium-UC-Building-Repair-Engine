### Task 3: OBJ writer

**Files:** Create `engine\io\obj_writer.py`, `engine\tests\test_obj_writer.py`

**Interfaces — Consumes:** `read_obj`, fixtures. **Produces:** `write_obj(mesh: MeshData, path: Path) -> None`.

- [ ] **Step 1: failing test**

```python
import numpy as np

from engine.io.obj_reader import read_obj
from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import cube


def test_round_trip_preserves_everything(tmp_path):
    a = cube(10.0)
    a.materials, a.face_material = ["stone", "paint"], np.array([0] * 6 + [1] * 6)
    p = tmp_path / "c.obj"
    write_obj(a, p)
    b = read_obj(p)
    assert np.array_equal(a.positions, b.positions) and np.allclose(a.uvs, b.uvs, atol=1e-6)
    assert np.array_equal(a.face_v, b.face_v) and np.array_equal(a.face_vt, b.face_vt)
    assert b.materials == ["stone", "paint"] and np.array_equal(a.face_material, b.face_material)


def test_write_is_deterministic(tmp_path):
    write_obj(cube(), tmp_path / "1.obj")
    write_obj(cube(), tmp_path / "2.obj")
    assert (tmp_path / "1.obj").read_bytes() == (tmp_path / "2.obj").read_bytes()
```

Run. Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 2: implementation**

```python
from pathlib import Path

from engine.model import MeshData


def _num(x: float, decimals: int) -> str:
    s = f"{x:.{decimals}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def write_obj(mesh: MeshData, path: Path) -> None:
    d = max(mesh.coord_decimals, 1)
    out = [f"# {mesh.name}"]
    if mesh.mtllib:
        out.append(f"mtllib {mesh.mtllib}")
    out.append(f"o {mesh.name}")
    out += ["v " + " ".join(_num(c, d) for c in p) for p in mesh.positions]
    out += ["vt " + " ".join(_num(c, 6) for c in t) for t in mesh.uvs]
    out += ["vn " + " ".join(_num(c, 6) for c in n) for n in mesh.normals]
    current = None
    for f in range(mesh.n_faces):
        mat = int(mesh.face_material[f])
        if mat != current and mat >= 0:
            out.append(f"usemtl {mesh.materials[mat]}")
        current = mat
        toks = []
        for v, t, n in zip(mesh.face_v[f], mesh.face_vt[f], mesh.face_vn[f]):
            if t >= 0 and n >= 0:
                toks.append(f"{v + 1}/{t + 1}/{n + 1}")
            elif t >= 0:
                toks.append(f"{v + 1}/{t + 1}")
            elif n >= 0:
                toks.append(f"{v + 1}//{n + 1}")
            else:
                toks.append(str(v + 1))
        out.append("f " + " ".join(toks))
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
```

- [ ] **Step 3:** Run tests. Expected: `2 passed`.
- [ ] **Step 4:** Commit `feat(engine): deterministic OBJ writer`.

---

