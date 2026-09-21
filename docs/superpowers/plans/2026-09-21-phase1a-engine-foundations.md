# Phase 1A Engine Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tested Python package that snapshots a live OBJ export, reads it with stable face ids, derives
topology (weld, degenerates, edges, T-junctions, planar regions, edge classes) and packs it for the web canvas.

**Architecture:** Pure library `engine\`, no HTTP, no SQL. Every module is a set of functions over `MeshData`
and numpy arrays. Algorithms that ran on the real sidewalk files in `spike\` are ported, not reinvented.
Phase 1B (API, PostgreSQL, Vue canvas) consumes `analyse_topology` and `pack_meshbuf`.

**Tech Stack:** Python 3.12, numpy, shapely >= 2.1, pillow, pytest. (trimesh + embreex enter in Phase 2.)

**Spec:** `docs\superpowers\specs\2026-09-21-uc-model-fixer-design.md`. Evidence: `docs\spike\2026-09-21-phase0-results.md`.

## Global Constraints

- `engine\` imports nothing from `api\`, no `fastapi`, no `sqlalchemy`.
- Face `i` is the `i`-th `f` line of the source OBJ. Nothing may reorder, merge or drop faces on read.
- Non-triangle faces raise `ObjFormatError`. Measured exports are fully triangulated.
- Vertices are never moved. Weld is **exact** on printed decimals. No tolerance weld, ever (blocked: weld above 0.1 mm).
- Coordinate quantum is **per axis**: `q_i = 10 ** (ceil(log10(max|coord_i|)) - significant_digits)`.
  Plane tolerance = `1.5 * sum(|n_i| * q_i)`.
- Source export folder is live and read-only. Only `engine\io\snapshot.py` reads it, and only via stability check + copy + sha256.
- All commands run from repo root with `.venv\Scripts\python.exe`. Tests: `.venv\Scripts\python.exe -m pytest -q`.
- TDD: failing test first, watch it fail, minimal code, watch it pass, commit. Commit trailer:
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | package + pytest config |
| `engine\model.py` | `MeshData` container |
| `engine\io\obj_reader.py` | strict OBJ parse, face-id stable |
| `engine\io\obj_writer.py` | deterministic OBJ write |
| `engine\io\mtl.py` | MTL parse, subset write, texture flatness |
| `engine\io\snapshot.py` | manifest, stability check, copy + hash, asset copy |
| `engine\topo\weld.py` | exact weld, per-axis quantum |
| `engine\topo\adjacency.py` | degenerate mask, edge table, T-vertices |
| `engine\topo\planes.py` | plane clusters, UV classes, regions |
| `engine\topo\edges.py` | edge classes for the overlay |
| `engine\pipeline.py` | `analyse_topology` tying the above together |
| `engine\transport\meshbuf.py` | binary buffer for the canvas |
| `engine\tests\fixtures\build.py` | synthetic meshes with known answers |

---

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

### Task 4: MTL + texture flatness

**Files:** Create `engine\io\mtl.py`, `engine\tests\test_mtl.py`

**Interfaces — Produces:** `MtlMaterial(name, lines, map_kd)`, `parse_mtl(path) -> dict[str, MtlMaterial]`,
`write_mtl_subset(materials, used, dst, texture_dir="tex") -> dict[str, str]` (material -> source `map_Kd` relpath),
`texture_flatness(path) -> float` (max per-channel colour std, 0-255 scale).

- [ ] **Step 1: failing test**

```python
import numpy as np
from PIL import Image

from engine.io.mtl import parse_mtl, texture_flatness, write_mtl_subset

MTL = """newmtl stone
Kd 0.87 0.87 0.87
map_Kd SRC-TEX/stone.png

newmtl paint
Kd 1 0 0

newmtl unused
map_Kd SRC-TEX/unused.png
"""


def test_parse_and_subset(tmp_path):
    src = tmp_path / "lib.mtl"
    src.write_text(MTL)
    mats = parse_mtl(src)
    assert list(mats) == ["stone", "paint", "unused"] and mats["stone"].map_kd == "SRC-TEX/stone.png"
    assert mats["paint"].map_kd is None
    dst = tmp_path / "out.mtl"
    assert write_mtl_subset(mats, ["paint", "stone"], dst) == {"stone": "SRC-TEX/stone.png"}
    text = dst.read_text()
    assert "map_Kd tex/stone.png" in text and "unused" not in text and "newmtl paint" in text


def test_texture_flatness(tmp_path):
    rng = np.random.default_rng(0)
    Image.fromarray(rng.integers(217, 228, (16, 16, 3)).astype(np.uint8)).save(tmp_path / "flat.png")
    checker = np.indices((16, 16)).sum(axis=0) % 2 * 255
    Image.fromarray(np.stack([checker] * 3, axis=2).astype(np.uint8)).save(tmp_path / "pattern.png")
    assert texture_flatness(tmp_path / "flat.png") < 5.0
    assert texture_flatness(tmp_path / "pattern.png") > 100.0
```

Run. Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 2: implementation**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import numpy as np
from PIL import Image


@dataclass
class MtlMaterial:
    name: str
    lines: list[str] = field(default_factory=list)
    map_kd: str | None = None


def parse_mtl(path: Path) -> dict[str, MtlMaterial]:
    out: dict[str, MtlMaterial] = {}
    cur = None
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("newmtl "):
            cur = MtlMaterial(line[7:].strip())
            out[cur.name] = cur
        elif cur is not None and line and not line.startswith("#"):
            if line.startswith("map_Kd "):
                cur.map_kd = line[7:].strip()
            cur.lines.append(line)
    return out


def write_mtl_subset(materials, used, dst, texture_dir="tex") -> dict[str, str]:
    textures, out = {}, []
    for name in used:
        mat = materials.get(name)
        if mat is None:
            continue
        out.append(f"newmtl {name}")
        for line in mat.lines:
            if line.startswith("map_Kd ") and mat.map_kd:
                textures[name] = mat.map_kd
                line = f"map_Kd {texture_dir}/{PurePosixPath(mat.map_kd.replace(chr(92), '/')).name}"
            out.append(line)
        out.append("")
    Path(dst).write_text("\n".join(out), encoding="utf-8", newline="\n")
    return textures


def texture_flatness(path: Path) -> float:
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=float).reshape(-1, 3)
    return float(rgb.std(axis=0).max())
```

- [ ] **Step 3:** Run tests. Expected: `2 passed`. Real check: sidewalk textures measured 3.04 in the spike.
- [ ] **Step 4:** Commit `feat(engine): MTL subset and texture flatness`.

---

### Task 5: Snapshot importer

**Files:** Create `engine\io\snapshot.py`, `engine\tests\test_snapshot.py`

**Interfaces — Consumes:** `read_obj`, `parse_mtl`, `write_mtl_subset`, `texture_flatness`.
**Produces:** `ManifestRow(file, tris, group)`, `read_manifest(path) -> dict[str, ManifestRow]`,
`SourceUnstable(Exception)`, `ManifestMismatch(Exception)`, `sha256_file(path) -> str`,
`wait_stable(path, interval_s=1.0, sleep=time.sleep) -> tuple[int, int]`,
`snapshot_object(src_obj, dst_root, expected_tris=None, interval_s=1.0, sleep=time.sleep) -> SnapshotResult`,
`SnapshotResult(dir, obj_path, sha256, size_bytes, mesh, mtl_path, textures: dict[str, Path], flatness: dict[str, float], missing_textures: list[str])`.

- [ ] **Step 1: failing test**

```python
import numpy as np
import pytest
from PIL import Image

from engine.io.snapshot import ManifestMismatch, SourceUnstable, read_manifest, snapshot_object, wait_stable

MANIFEST = """file                                                              tris   sketchup group
Main_Infrustructure_Building.obj                               142,248   Main_Infrustructure_Building
CHTM_SIDE_WALK_2nd_floor.obj                                     4,692   CHTM_SIDE_WALK_2nd_floor
"""
OBJ = "mtllib ../lib.mtl\no walk\nv 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\nusemtl stone\nf 1/1 2/2 3/3\n"


def make_source(tmp_path):
    (tmp_path / "split").mkdir()
    (tmp_path / "SRC-TEX").mkdir()
    (tmp_path / "split" / "walk.obj").write_text(OBJ)
    (tmp_path / "lib.mtl").write_text("newmtl stone\nmap_Kd SRC-TEX/stone.png\n\nnewmtl other\nmap_Kd SRC-TEX/gone.png\n")
    Image.fromarray(np.full((4, 4, 3), 220, np.uint8)).save(tmp_path / "SRC-TEX" / "stone.png")
    return tmp_path / "split" / "walk.obj"


def test_manifest_parses_thousands_commas(tmp_path):
    p = tmp_path / "_MANIFEST.txt"
    p.write_text(MANIFEST)
    rows = read_manifest(p)
    assert rows["CHTM_SIDE_WALK_2nd_floor.obj"].tris == 4692
    assert rows["Main_Infrustructure_Building.obj"].group == "Main_Infrustructure_Building"


def test_snapshot_copies_hashes_and_subsets(tmp_path):
    src = make_source(tmp_path / "src")
    res = snapshot_object(src, tmp_path / "snap", expected_tris=1, interval_s=0, sleep=lambda s: None)
    assert res.obj_path.read_bytes() == src.read_bytes() and len(res.sha256) == 64
    assert res.dir.name == res.sha256[:12] and res.mesh.n_faces == 1
    assert "other" not in res.mtl_path.read_text() and res.textures["stone"].exists()
    assert res.flatness["stone"] == 0.0 and res.missing_textures == []
    again = snapshot_object(src, tmp_path / "snap", expected_tris=1, interval_s=0, sleep=lambda s: None)
    assert again.dir == res.dir


def test_source_changing_during_read_is_rejected(tmp_path):
    src = make_source(tmp_path / "src")
    with pytest.raises(SourceUnstable):
        wait_stable(src, interval_s=0, sleep=lambda s: src.write_text(OBJ + "v 9 9 9\n"))


def test_missing_source_is_rejected(tmp_path):
    with pytest.raises(SourceUnstable):
        wait_stable(tmp_path / "nope.obj", interval_s=0, sleep=lambda s: None)


def test_manifest_mismatch(tmp_path):
    src = make_source(tmp_path / "src")
    with pytest.raises(ManifestMismatch):
        snapshot_object(src, tmp_path / "snap", expected_tris=99, interval_s=0, sleep=lambda s: None)
```

Run. Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 2: implementation**

```python
from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from engine.io.mtl import parse_mtl, texture_flatness, write_mtl_subset
from engine.io.obj_reader import ObjFormatError, read_obj
from engine.model import MeshData


class SourceUnstable(Exception):
    pass


class ManifestMismatch(Exception):
    pass


@dataclass
class ManifestRow:
    file: str
    tris: int
    group: str


@dataclass
class SnapshotResult:
    dir: Path
    obj_path: Path
    sha256: str
    size_bytes: int
    mesh: MeshData
    mtl_path: Path | None
    textures: dict[str, Path] = field(default_factory=dict)
    flatness: dict[str, float] = field(default_factory=dict)
    missing_textures: list[str] = field(default_factory=list)


def read_manifest(path: Path) -> dict[str, ManifestRow]:
    rows = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 2 and parts[1].replace(",", "").isdigit():
            rows[parts[0]] = ManifestRow(parts[0], int(parts[1].replace(",", "")), parts[2] if len(parts) > 2 else "")
    return rows


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _key(path: Path) -> tuple[int, int]:
    st = os.stat(path)
    return st.st_size, st.st_mtime_ns


def wait_stable(path: Path, interval_s: float = 1.0, sleep=time.sleep) -> tuple[int, int]:
    path = Path(path)
    if not path.exists():
        raise SourceUnstable(f"{path.name}: missing, source rebuilding")
    a = _key(path)
    sleep(interval_s)
    if not path.exists() or _key(path) != a or a[0] == 0:
        raise SourceUnstable(f"{path.name}: changed during read, source rebuilding")
    return a


def snapshot_object(src_obj, dst_root, expected_tris=None, interval_s=1.0, sleep=time.sleep) -> SnapshotResult:
    src_obj, dst_root = Path(src_obj), Path(dst_root)
    key = wait_stable(src_obj, interval_s, sleep)
    dst_root.mkdir(parents=True, exist_ok=True)
    tmp = dst_root / f".incoming-{src_obj.stem}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        obj_copy = tmp / src_obj.name
        shutil.copyfile(src_obj, obj_copy)
        if not src_obj.exists() or _key(src_obj) != key:
            raise SourceUnstable(f"{src_obj.name}: changed during copy")
        digest = sha256_file(obj_copy)
        try:
            mesh = read_obj(obj_copy)
        except (ObjFormatError, ValueError) as exc:
            raise SourceUnstable(f"{src_obj.name}: copy does not parse ({exc})") from exc
        if expected_tris is not None and mesh.n_faces != expected_tris:
            raise ManifestMismatch(f"{src_obj.name}: {mesh.n_faces} tris, manifest says {expected_tris}")
        final = dst_root / digest[:12]
        if not final.exists():
            _copy_assets(src_obj, mesh, tmp, interval_s, sleep)
            tmp.rename(final)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _load(final, src_obj.name, digest)


def _copy_assets(src_obj, mesh, tmp, interval_s, sleep):
    if not mesh.mtllib:
        return
    mtl_src = (src_obj.parent / mesh.mtllib).resolve()
    wait_stable(mtl_src, interval_s, sleep)
    wanted = write_mtl_subset(parse_mtl(mtl_src), mesh.materials, tmp / "materials.mtl")
    (tmp / "tex").mkdir()
    missing = []
    for rel in sorted(set(wanted.values())):
        tex_src = mtl_src.parent / rel
        if tex_src.exists():
            shutil.copyfile(tex_src, tmp / "tex" / PurePosixPath(rel.replace("\\", "/")).name)
        else:
            missing.append(rel)
    (tmp / "missing_textures.txt").write_text("\n".join(missing), encoding="utf-8")


def _load(final: Path, obj_name: str, digest: str) -> SnapshotResult:
    obj_path = final / obj_name
    mtl_path = final / "materials.mtl"
    res = SnapshotResult(final, obj_path, digest, obj_path.stat().st_size, read_obj(obj_path),
                         mtl_path if mtl_path.exists() else None)
    if res.mtl_path:
        for name, mat in parse_mtl(mtl_path).items():
            if mat.map_kd and (final / mat.map_kd).exists():
                res.textures[name] = final / mat.map_kd
                res.flatness[name] = texture_flatness(final / mat.map_kd)
        miss = final / "missing_textures.txt"
        res.missing_textures = [m for m in miss.read_text(encoding="utf-8").splitlines() if m] if miss.exists() else []
    return res
```

- [ ] **Step 3:** Run tests. Expected: `5 passed`.
- [ ] **Step 4: real-data check** (not a unit test, source is live):

```
.venv\Scripts\python.exe -c "from pathlib import Path; from engine.io.snapshot import *; s=Path(r'D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17\split'); m=read_manifest(s/'_MANIFEST.txt'); r=snapshot_object(s/'CHTM_SIDE_WALK_2nd_floor.obj', Path('data/snapshots'), m['CHTM_SIDE_WALK_2nd_floor.obj'].tris); print(r.sha256, r.mesh.n_faces, r.flatness, r.missing_textures)"
```

Expected: 64-hex sha, `4692`, flatness about `3.04`, `[]`. `SourceUnstable` means the other pipeline is mid-rebuild: wait and retry, do not work around it.

- [ ] **Step 5:** Commit `feat(engine): snapshot importer with stability and manifest checks`.

---

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

### Task 8: Meshbuf

**Files:** Create `engine\transport\meshbuf.py`, `engine\tests\test_meshbuf.py`

**Interfaces — Consumes:** `MeshData`, `Topology`.
**Produces:** `pack_meshbuf(mesh, topo, textures: dict[str, str | None]) -> bytes`,
`unpack_meshbuf(buf) -> tuple[dict, dict[str, np.ndarray]]`.

Layout: `b"UCMB"`, `u32` version 1, `u32` header length, UTF-8 JSON header padded with spaces to 4 bytes, then blocks.
Block offsets in the header are relative to the first byte after the padded header. Every block is padded to 4 bytes.
Blocks: `positions f32 (F*3,3)` recentred to bbox centre, non-indexed; `uvs f32 (F*3,2)`; `normals f32 (F*3,3)`
(source `vn` when present, else face normal, `(0,0,1)` for degenerates); `tri_material u16 (F,)` (65535 = none);
`tri_face_id u32 (F,)`; `tri_region i32 (F,)`; `edge_positions f32 (E*2,3)`; `edge_class u8 (E,)`.
Non-indexed geometry means three.js `faceIndex` k maps to `tri_face_id[k]`.

- [ ] **Step 1: failing test**

```python
import numpy as np

from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import cube
from engine.transport.meshbuf import pack_meshbuf, unpack_meshbuf


def test_round_trip_and_alignment():
    m = cube(10.0)
    buf = pack_meshbuf(m, analyse_topology(m), {"m0": "tex/stone.png"})
    assert buf[:4] == b"UCMB"
    header, blocks = unpack_meshbuf(buf)
    assert header["version"] == 1 and header["counts"] == {"faces": 12, "edges": 18}
    assert header["origin_offset"] == [5.0, 5.0, 5.0] and header["unit_scale_m"] == 0.0254
    assert header["materials"] == [{"name": "m0", "texture": "tex/stone.png"}]
    assert all(b["offset"] % 4 == 0 for b in header["blocks"])
    assert blocks["positions"].shape == (36, 3) and np.abs(blocks["positions"]).max() == 5.0
    assert blocks["tri_face_id"].tolist() == list(range(12))
    assert blocks["edge_positions"].shape == (36, 3) and blocks["edge_class"].shape == (18,)
    n = blocks["normals"].reshape(12, 3, 3)[:, 0]
    assert np.allclose(np.linalg.norm(n, axis=1), 1.0)
```

Run. Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 2: implementation**

```python
import json
import struct

import numpy as np

MAGIC, VERSION = b"UCMB", 1
_DT = {"f32": np.float32, "u16": np.uint16, "u32": np.uint32, "i32": np.int32, "u8": np.uint8}


def _pad4(b: bytes, fill: bytes = b"\0") -> bytes:
    return b + fill * (-len(b) % 4)


def pack_meshbuf(mesh, topo, textures) -> bytes:
    lo, hi = mesh.bbox()
    origin = (lo + hi) / 2
    tri = mesh.positions[mesh.face_v]
    cr = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(cr, axis=1)
    face_n = np.where(ln[:, None] > 0, cr / np.maximum(ln, 1e-300)[:, None], np.array([0.0, 0.0, 1.0]))
    normals = np.repeat(face_n[:, None, :], 3, axis=1)
    has_vn = (mesh.face_vn >= 0).all(axis=1)
    if has_vn.any():
        normals[has_vn] = mesh.normals[mesh.face_vn[has_vn]]
    uvs = np.zeros((mesh.n_faces, 3, 2))
    has_vt = (mesh.face_vt >= 0).all(axis=1)
    if has_vt.any():
        uvs[has_vt] = mesh.uvs[mesh.face_vt[has_vt]]
    arrays = [
        ("positions", "f32", (tri - origin).reshape(-1, 3)),
        ("uvs", "f32", uvs.reshape(-1, 2)),
        ("normals", "f32", normals.reshape(-1, 3)),
        ("tri_material", "u16", np.where(mesh.face_material >= 0, mesh.face_material, 65535)),
        ("tri_face_id", "u32", np.arange(mesh.n_faces)),
        ("tri_region", "i32", topo.face_region),
        ("edge_positions", "f32", (topo.positions_w[topo.table.edges] - origin).reshape(-1, 3)),
        ("edge_class", "u8", topo.edge_class),
    ]
    body, blocks = b"", []
    for name, dt, arr in arrays:
        raw = np.ascontiguousarray(arr, dtype=_DT[dt]).tobytes()
        blocks.append({"name": name, "dtype": dt, "shape": list(np.shape(arr)), "offset": len(body), "nbytes": len(raw)})
        body += _pad4(raw)
    header = {
        "version": VERSION, "name": mesh.name, "units": mesh.units, "unit_scale_m": 0.0254,
        "origin_offset": origin.tolist(), "bbox": {"min": lo.tolist(), "max": hi.tolist()},
        "materials": [{"name": n, "texture": textures.get(n)} for n in mesh.materials],
        "counts": {"faces": mesh.n_faces, "edges": int(len(topo.table.edges))}, "blocks": blocks,
    }
    hjson = _pad4(json.dumps(header, separators=(",", ":")).encode("utf-8"), b" ")
    return MAGIC + struct.pack("<II", VERSION, len(hjson)) + hjson + body


def unpack_meshbuf(buf: bytes):
    assert buf[:4] == MAGIC, "not a meshbuf"
    _version, hlen = struct.unpack("<II", buf[4:12])
    header = json.loads(buf[12:12 + hlen].decode("utf-8"))
    start = 12 + hlen
    blocks = {b["name"]: np.frombuffer(buf, dtype=_DT[b["dtype"]], count=int(np.prod(b["shape"])),
                                       offset=start + b["offset"]).reshape(b["shape"])
              for b in header["blocks"]}
    return header, blocks
```

- [ ] **Step 3:** Run tests. Expected: `1 passed`. Then the whole suite: `.venv\Scripts\python.exe -m pytest -q`. Expected: `27 passed`.
- [ ] **Step 4:** Commit `feat(engine): meshbuf transport for the canvas`.

---

## Phase 1A done when

- `.venv\Scripts\python.exe -m pytest -q` shows `27 passed`, output pasted in the completion message.
- Real-data checks of Task 5 and Task 7 were run and their printed numbers recorded.
- `git grep -n "fastapi\|sqlalchemy" engine` returns nothing.

Next: Phase 1B plan (PostgreSQL in Docker, FastAPI, Vue canvas). Canvas requirement from the spike:
**double-sided rendering by default**, one-sided as a diagnostic toggle only.
