### Task 2: OBJ reader

**Files:** Create `engine\io\obj_reader.py`, `engine\tests\test_obj_reader.py`

**Interfaces — Produces:** `read_obj(path: Path) -> MeshData`, `class ObjFormatError(ValueError)`.

- [ ] **Step 1: failing test**

```python
import numpy as np
import pytest

from engine.io.obj_reader import ObjFormatError, read_obj

OBJ = """# demo
mtllib ../lib.mtl
o Demo_Object
v 1442.94 22669.4 1622.05
v 1442.94 22630.1 1612.2
v 1442.94 22630.1 1622.05
v 10 0 -0.5
vt 0 0
vt 1 0
vt 1 1
vn 1 0 0
usemtl stone
f 1/1/1 2/2/1 3/3/1
usemtl paint
f 2//1 1//1 4//1
f -4 -3 -2
"""


def test_reads_arrays_and_keeps_face_order(tmp_path):
    p = tmp_path / "a.obj"
    p.write_text(OBJ)
    m = read_obj(p)
    assert m.name == "Demo_Object" and m.mtllib == "../lib.mtl"
    assert m.positions.shape == (4, 3) and m.uvs.shape == (3, 2) and m.normals.shape == (1, 3)
    assert m.face_v.tolist() == [[0, 1, 2], [1, 0, 3], [0, 1, 2]]
    assert m.face_vt.tolist() == [[0, 1, 2], [-1, -1, -1], [-1, -1, -1]]
    assert m.face_vn.tolist() == [[0, 0, 0], [0, 0, 0], [-1, -1, -1]]
    assert m.materials == ["stone", "paint"] and m.face_material.tolist() == [0, 1, 1]
    assert m.face_line.tolist() == [13, 15, 16]
    assert m.coord_decimals == 2 and m.sig_digits == 6


def test_rejects_quads(tmp_path):
    p = tmp_path / "q.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n")
    with pytest.raises(ObjFormatError, match="line 5"):
        read_obj(p)


def test_name_falls_back_to_stem(tmp_path):
    p = tmp_path / "thing.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    assert read_obj(p).name == "thing"
```

Run: `.venv\Scripts\python.exe -m pytest engine/tests/test_obj_reader.py -q`. Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 2: implementation `engine\io\obj_reader.py`**

```python
from __future__ import annotations

from pathlib import Path

import numpy as np

from engine.model import MeshData


class ObjFormatError(ValueError):
    pass


def _index(tok: str, count: int, line_no: int) -> int:
    i = int(tok)
    if i > 0:
        return i - 1
    if i < 0:
        return count + i
    raise ObjFormatError(f"line {line_no}: index 0 is invalid")


def read_obj(path: Path) -> MeshData:
    path = Path(path)
    v, vt, vn = [], [], []
    fv, fvt, fvn, fmat, fline = [], [], [], [], []
    materials: list[str] = []
    current, mtllib, name, decimals, sig = -1, None, None, 0, 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line or line[0] == "#":
                continue
            head, _, rest = line.partition(" ")
            rest = rest.strip()
            if head == "v":
                toks = rest.split()[:3]
                v.append([float(t) for t in toks])
                for t in toks:
                    if "." in t:
                        decimals = max(decimals, len(t.split(".")[1]))
                    sig = max(sig, len(t.lstrip("-").replace(".", "").lstrip("0")))
            elif head == "vt":
                vt.append([float(t) for t in rest.split()[:2]])
            elif head == "vn":
                vn.append([float(t) for t in rest.split()[:3]])
            elif head == "usemtl":
                if rest not in materials:
                    materials.append(rest)
                current = materials.index(rest)
            elif head == "mtllib":
                mtllib = rest
            elif head in ("o", "g") and name is None and rest:
                name = rest
            elif head == "f":
                toks = rest.split()
                if len(toks) != 3:
                    raise ObjFormatError(f"line {line_no}: face has {len(toks)} vertices, only triangles supported")
                parts = [t.split("/") for t in toks]
                fv.append([_index(p[0], len(v), line_no) for p in parts])
                fvt.append([_index(p[1], len(vt), line_no) if len(p) > 1 and p[1] else -1 for p in parts])
                fvn.append([_index(p[2], len(vn), line_no) if len(p) > 2 and p[2] else -1 for p in parts])
                fmat.append(current)
                fline.append(line_no)
    return MeshData(
        name=name or path.stem,
        positions=np.array(v, float).reshape(-1, 3), uvs=np.array(vt, float).reshape(-1, 2),
        normals=np.array(vn, float).reshape(-1, 3),
        face_v=np.array(fv, np.int64).reshape(-1, 3), face_vt=np.array(fvt, np.int64).reshape(-1, 3),
        face_vn=np.array(fvn, np.int64).reshape(-1, 3), face_material=np.array(fmat, np.int64),
        face_line=np.array(fline, np.int64), materials=materials, mtllib=mtllib,
        coord_decimals=decimals, sig_digits=sig)
```

- [ ] **Step 3:** Run tests. Expected: `3 passed`.
- [ ] **Step 4:** Commit `feat(engine): strict OBJ reader with stable face ids`.

---

