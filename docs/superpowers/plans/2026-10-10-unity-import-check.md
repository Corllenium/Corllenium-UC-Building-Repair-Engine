# Unity import check (Part 1 of the Unity floor pipeline) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** prove, per floor, whether the engine's fixed OBJ survives Unity's import unchanged. When it does not, name
the cause (missing, extra or flipped faces, materials, textures, UVs, normals) and the import setting that caused
it.

**Architecture:**
- A **mirror Unity project** in this repo (`unity/ImportMirror/`) uses the same Unity version and a sha256-checked
  copy of the owner's `CampusModelImporter.cs`.
- Run headless, it imports an engine build exactly as the owner's project would and **dumps what Unity made of it**
  (an OBJ+MTL plus a JSON sidecar).
- Python (`engine/unity/`) aligns Unity's frame to the build's. It matches faces as oriented multisets, names every
  difference by cause, and runs `find_errors` on both. `engine.cli unity-check` gives the verdict.
- An override postprocessor, present only in the mirror, varies one import setting at a time to isolate the cause.

**Tech Stack:** Python 3.12 (numpy only; there is no scipy in the venv), pytest, Unity 6000.4.7f1 Editor in batch
mode, C# editor scripts.

**Spec:** `docs/superpowers/specs/2026-10-10-unity-floor-pipeline-design.md` (Part 1, plus the measurement step of
Part 2). Parts 2-6 get their own plans after this one's measurements.

## Global Constraints

- **AGENTS.md binds everything.** In particular:
  - nothing is written to the owner's Unity project `D:/PROJECTS/UC/01-UNITY/UC-Campus` (owner decision
    2026-10-10). Its `Assets/Editor/CampusModelImporter.cs` is **read** and copied;
  - never write to `D:/PROJECTS/UC ENVIRONMENT BUILDING/...`, never touch the master `.skp`, never touch the
    containers or the live DB;
  - stage files by name; test first; commit after each item;
  - stop only processes you started, **by PID** (`taskkill /PID <pid> /T /F`), never by image name.
- **Python:** `"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"`, run from the worktree root in a subshell with
  `PYTHONPATH="$PWD"`. Never use a bare `cd`.
- **Unity:** `D:/SOFTWARE/UNITY/Unity Hub/Editor/6000.4.7f1/Editor/Unity.exe`, overridable with the env var
  `UC_UNITY_EXE`. It always runs with `-batchmode -nographics -quit`, on the mirror project only.
- **Branch:** `claude/U1-<task>` worktrees from `feat/repair-p1p2` (the engine with E8a, E8b, E8c and E3). Unity
  tests that launch Unity are marked `@pytest.mark.unity` and skip when the Unity exe is missing.
- **No change** to `engine/guard/**`, `engine/validate/**`, `engine/repair/**` or `FixProfile`.
- **No new Python dependency.**

## Review Focus

1. **A floor over 65,535 vertices.** Unity's default 16-bit index buffer can split or garble it, which shows as
   spikes. The check must report `index_format` and flag the cause, never pass silently. Owned by Task 3, with a
   test.
2. **Coincident opposite faces** (both windings, same place, common in this model). Matching must count them as two
   faces each side and must not merge them, or a dropped side passes. Owned by Task 3, with a test.
3. **Faces with no material** (index -1, the look `material:<none>`). Unity gives them a default material, and the
   compare must name that `material_remapped` instead of crashing. Owned by Task 4, with a test.
4. **The owner changed `CampusModelImporter.cs` since the last sync.** The runner must refuse with a message naming
   both sha256 values, never check against a stale copy. Owned by Task 6, with a test.
5. **Unity missing, failing its licence, or timing out.** The runner must:
   - exit non-zero with the log's last lines;
   - kill only its own PID tree;
   - never leave a half-written dump that reads as valid. The sidecar is written last, and the reader requires
     `complete: true`.

   Owned by Tasks 1 and 7, with tests.

---

## File structure

| File | Responsibility |
|---|---|
| `engine/unity/__init__.py` | package marker |
| `engine/unity/dump.py` | read a Unity dump (OBJ+MTL+sidecar) into `UnityDump`; validate the sidecar |
| `engine/unity/align.py` | find Unity-frame → build-frame mapping (signed axis permutation, scale, offset) |
| `engine/unity/check.py` | `unity_check(build, dump)`: face matching, causes, `find_errors` on both, the verdict |
| `engine/cli.py` | add `unity-check` and `unity-mirror-import` |
| `engine/unity/mirror.py` | stage a build into the mirror, run Unity headless, return the dump path |
| `tools/unity_mirror.py` | `sync` / `check` the importer copy (sha256) |
| `unity/ImportMirror/Assets/Editor/UcFloorExport.cs` | C#: import an OBJ under the owner's rules and dump what Unity made |
| `unity/ImportMirror/Assets/Editor/UcImportOverrides.cs` | C#: mirror-only postprocessor that applies `overrides.json` after the owner's importer |
| `unity/ImportMirror/.gitignore` | ignore Library/Temp/Logs/UserSettings, the importer copy, staged inputs |
| `engine/tests/test_unity_dump.py`, `test_unity_align.py`, `test_unity_check.py`, `test_cli_unity_check.py`, `test_unity_mirror.py` | tests |
| `tools/tests/test_unity_mirror_sync.py` | sync/check tests |

## The dump format (every task uses it)

For a floor named `<name>`, the dump is three files in one folder.

- **`<name>.obj`:**
  - one `o` per Unity mesh;
  - `v x y z` are positions **as Unity holds them** (the mesh's local coordinates times its transform relative to the
    imported model root, in Unity units);
  - then `vt u v`, `vn x y z`;
  - one `usemtl <material name>` per submesh;
  - faces `f a/a/a b/b/b c/c/c` (1-based, Unity's triangle order).
- **`<name>.mtl`:** `newmtl <material name>`, plus `map_Kd <texture file name>` when the material has a main texture.
- **`<name>.unity.json`** (written last):

```json
{"schema": 1, "complete": true, "unity_version": "6000.4.7f1", "asset_path": "Assets/Models/Campus/_check/<name>/<name>.obj",
 "importer": {"globalScale": 0.0254, "useFileUnits": false, "weldVertices": true, "importNormals": "Calculate",
              "normalSmoothingAngle": 60.0, "meshCompression": "Off", "indexFormat": "Auto",
              "generateSecondaryUV": false, "isReadable": true},
 "importer_sha256": "<sha256 of the CampusModelImporter.cs used>",
 "overrides": {},
 "meshes": [{"name": "<mesh>", "vertex_count": 1234, "index_format": "UInt16",
             "submeshes": [{"material": "<name>", "texture": "<file or null>", "triangle_count": 99}]}]}
```

---

### Task 1: read a Unity dump

**Files:**
- Create: `engine/unity/__init__.py` (empty), `engine/unity/dump.py`
- Test: `engine/tests/test_unity_dump.py`

**Interfaces:**
- Consumes: `engine.io.obj_reader.read_obj(path) -> MeshData` (the faces' `face_vn` index into `normals`).
- Produces:
  - `UnityDump(mesh: MeshData, corner_normals: np.ndarray (F,3,3), sidecar: dict)`;
  - `read_unity_dump(obj_path: Path) -> UnityDump`;
  - `DumpError(ValueError)`.

- [ ] **Step 1: Write the failing tests**

```python
# engine/tests/test_unity_dump.py
import json
from pathlib import Path

import numpy as np
import pytest

from engine.unity.dump import DumpError, read_unity_dump

OBJ = """o m
v 0 0 0
v 1 0 0
v 0 1 0
vt 0 0
vt 1 0
vt 0 1
vn 0 0 1
usemtl wall
f 1/1/1 2/2/1 3/3/1
"""


def _sidecar(**over):
    d = {"schema": 1, "complete": True, "unity_version": "6000.4.7f1", "asset_path": "Assets/x.obj",
         "importer": {"globalScale": 0.0254}, "importer_sha256": "ab", "overrides": {},
         "meshes": [{"name": "m", "vertex_count": 3, "index_format": "UInt16",
                     "submeshes": [{"material": "wall", "texture": None, "triangle_count": 1}]}]}
    d.update(over)
    return d


def _write(tmp_path, sidecar):
    (tmp_path / "f.obj").write_text("mtllib f.mtl\n" + OBJ)
    (tmp_path / "f.mtl").write_text("newmtl wall\n")
    if sidecar is not None:
        (tmp_path / "f.unity.json").write_text(json.dumps(sidecar))
    return tmp_path / "f.obj"


def test_a_complete_dump_reads_mesh_corner_normals_and_sidecar(tmp_path):
    d = read_unity_dump(_write(tmp_path, _sidecar()))
    assert d.mesh.n_faces == 1 and d.mesh.materials == ["wall"]
    assert d.corner_normals.shape == (1, 3, 3)
    np.testing.assert_allclose(d.corner_normals[0], [[0, 0, 1]] * 3)
    assert d.sidecar["meshes"][0]["index_format"] == "UInt16"


def test_a_dump_without_its_sidecar_is_refused(tmp_path):
    with pytest.raises(DumpError, match="sidecar"):
        read_unity_dump(_write(tmp_path, None))


def test_a_half_written_dump_is_refused(tmp_path):
    with pytest.raises(DumpError, match="complete"):
        read_unity_dump(_write(tmp_path, _sidecar(complete=False)))


def test_an_unknown_schema_is_refused(tmp_path):
    with pytest.raises(DumpError, match="schema"):
        read_unity_dump(_write(tmp_path, _sidecar(schema=2)))


def test_a_face_without_normals_is_refused(tmp_path):
    p = _write(tmp_path, _sidecar())
    p.write_text(p.read_text().replace("f 1/1/1 2/2/1 3/3/1", "f 1/1 2/2 3/3"))
    with pytest.raises(DumpError, match="normal"):
        read_unity_dump(p)
```

- [ ] **Step 2: Run them and see them fail**

Run: `( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_unity_dump.py -q -p no:cacheprovider )`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.unity'`.

- [ ] **Step 3: Implement**

```python
# engine/unity/dump.py
"""Read what Unity made of a floor: the dump written by the mirror project (route A) or a live-scene read (route B).

The dump is `<name>.obj` + `<name>.mtl` + `<name>.unity.json`. The sidecar is written LAST and must say
`"complete": true`, so a run that died half way never reads as a valid dump.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from engine.io.obj_reader import read_obj
from engine.model import MeshData

SCHEMA = 1


class DumpError(ValueError):
    """A Unity dump that cannot be trusted."""


@dataclass(frozen=True)
class UnityDump:
    mesh: MeshData                # Unity's geometry, in Unity's own frame and units
    corner_normals: np.ndarray    # (F, 3, 3): each corner's normal as Unity shades it
    sidecar: dict


def read_unity_dump(obj_path: Path) -> UnityDump:
    obj_path = Path(obj_path)
    side = obj_path.with_name(obj_path.stem + ".unity.json")
    if not side.is_file():
        raise DumpError(f"no sidecar {side.name} next to {obj_path.name}")
    sidecar = json.loads(side.read_text(encoding="utf-8"))
    if sidecar.get("schema") != SCHEMA:
        raise DumpError(f"unknown schema {sidecar.get('schema')!r} (expected {SCHEMA})")
    if sidecar.get("complete") is not True:
        raise DumpError("dump not complete: the Unity run did not finish")
    mesh = read_obj(obj_path)
    if mesh.face_vn.size and (mesh.face_vn < 0).any() or len(mesh.normals) == 0:
        raise DumpError("every face corner must carry a normal (vn); Unity always has one")
    return UnityDump(mesh=mesh, corner_normals=mesh.normals[mesh.face_vn], sidecar=sidecar)
```

- [ ] **Step 4: Run them and see them pass**

Run the same command. Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add engine/unity/__init__.py engine/unity/dump.py engine/tests/test_unity_dump.py
git commit -m "feat(unity): read a Unity dump (obj+mtl+sidecar), refusing incomplete or normal-less dumps"
```

---

### Task 2: align Unity's frame to the build's

Unity's OBJ importer scales by `globalScale` and mirrors one axis, and the owner's project rotates nothing. The
mapping is still **found, not assumed**: try all 48 signed axis permutations, and keep the one under which the most
Unity vertices land on build vertices.

**Files:**
- Create: `engine/unity/align.py`
- Test: `engine/tests/test_unity_align.py`

**Interfaces:**
- Consumes: `MeshData` (build and Unity), and the scale from `sidecar["importer"]["globalScale"]`.
- Produces:
  - `Alignment(matrix: np.ndarray (3,3), scale: float, offset: np.ndarray (3,), match: float)`;
  - `align(build: MeshData, unity: MeshData, scale: float, tol: float) -> Alignment`;
  - `to_build_frame(points: np.ndarray, a: Alignment) -> np.ndarray`;
  - `AlignError(ValueError)` when the best match is below 0.99.

- [ ] **Step 1: Write the failing tests**

```python
# engine/tests/test_unity_align.py
import numpy as np
import pytest

from engine.tests.fixtures.build import cube
from engine.unity.align import AlignError, align, to_build_frame


def _as_unity(mesh, matrix, scale):
    from dataclasses import replace
    return replace(mesh, positions=(mesh.positions @ np.asarray(matrix, float).T) * scale)


def test_a_mirrored_scaled_copy_aligns_exactly():
    b = cube(100.0)
    m = np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]])       # x mirrored, y and z swapped
    u = _as_unity(b, m, 0.0254)
    a = align(b, u, 0.0254, tol=1e-3)
    assert a.match == 1.0
    np.testing.assert_allclose(to_build_frame(u.positions, a), b.positions, atol=1e-6)


def test_an_unrelated_mesh_is_refused():
    b = cube(100.0)
    u = _as_unity(cube(37.0), np.eye(3), 1.0)
    with pytest.raises(AlignError, match="match"):
        align(b, u, 1.0, tol=1e-3)
```

- [ ] **Step 2: Run them and see them fail**

Run: `( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_unity_align.py -q -p no:cacheprovider )`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.unity.align'`.

- [ ] **Step 3: Implement**

```python
# engine/unity/align.py
"""Map Unity's frame onto the build's: a signed axis permutation, Unity's import scale and an offset.

Found by trying all 48 signed permutations, not assumed. Unity's OBJ importer mirrors an axis, and a project could
rotate. The winner is the one under which the most Unity vertices land on a build vertex (snapped at `tol`).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np

from engine.model import MeshData

MIN_MATCH = 0.99


class AlignError(ValueError):
    """Unity's mesh does not land on the build under any signed axis permutation."""


@dataclass(frozen=True)
class Alignment:
    matrix: np.ndarray   # build = (matrix @ (unity / scale)) + offset
    scale: float
    offset: np.ndarray
    match: float


def to_build_frame(points: np.ndarray, a: Alignment) -> np.ndarray:
    return (np.asarray(points, float) / a.scale) @ a.matrix.T + a.offset


def _keys(points: np.ndarray, tol: float) -> set:
    return set(map(tuple, np.round(points / tol).astype(np.int64)))


def align(build: MeshData, unity: MeshData, scale: float, tol: float) -> Alignment:
    target = _keys(build.positions, tol)
    bmin = build.positions.min(axis=0)
    best = None
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1.0, -1.0), repeat=3):
            m = np.zeros((3, 3))
            for row, (col, s) in enumerate(zip(perm, signs)):
                m[row, col] = s
            p = (unity.positions / scale) @ m.T
            offset = bmin - p.min(axis=0)
            got = _keys(p + offset, tol)
            match = len(got & target) / max(len(got), 1)
            if best is None or match > best.match:
                best = Alignment(matrix=m, scale=scale, offset=offset, match=match)
    if best.match < MIN_MATCH:
        raise AlignError(f"best match {best.match:.3f} < {MIN_MATCH}: Unity's mesh is not this build")
    return best
```

- [ ] **Step 4: Run them and see them pass**

Run the same command. Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add engine/unity/align.py engine/tests/test_unity_align.py
git commit -m "feat(unity): align Unity's frame to the build by the best of 48 signed axis permutations"
```

---

### Task 3: match faces and name the geometry causes

**Files:**
- Create: `engine/unity/check.py`
- Test: `engine/tests/test_unity_check.py`

**Interfaces:**
- Consumes:
  - `UnityDump` (Task 1);
  - `align`, `to_build_frame` (Task 2);
  - `engine.repair.types.print_step(mesh) -> float`.
- Produces: `geometry_diff(build: MeshData, dump: UnityDump) -> dict`, with keys:
  - `alignment` (`{"match", "det"}`);
  - `faces_build`, `faces_unity`, `matched`, `missing`, `extra`, `flipped`;
  - `index_overflow` (bool), `vertex_counts`;
  - `examples` (up to 20 face indices per cause).

  The tolerance is `print_step(build)`.

- [ ] **Step 1: Write the failing tests**

```python
# engine/tests/test_unity_check.py
from dataclasses import replace

import numpy as np

from engine.tests.fixtures.build import cube
from engine.unity.check import geometry_diff
from engine.unity.dump import UnityDump

M = np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]], float)   # Unity mirrors x; y-up


def _dump(mesh, *, faces=None, index_format="UInt32", vertex_count=None):
    """`mesh` as Unity would hold it: mirrored (so winding reverses) and scaled."""
    f = mesh.face_v[:, ::-1] if faces is None else faces
    u = replace(mesh, positions=(mesh.positions @ M.T) * 0.0254, face_v=f,
                face_vt=mesh.face_vt[:, ::-1], face_material=mesh.face_material[: len(f)])
    n = np.zeros((len(f), 3, 3))
    side = {"importer": {"globalScale": 0.0254},
            "meshes": [{"name": "m", "vertex_count": vertex_count or len(mesh.positions),
                        "index_format": index_format, "submeshes": []}]}
    return UnityDump(mesh=u, corner_normals=n, sidecar=side)


def test_an_unchanged_import_matches_every_face():
    b = cube(100.0)
    g = geometry_diff(b, _dump(b))
    assert (g["matched"], g["missing"], g["extra"], g["flipped"]) == (12, 0, 0, 0)


def test_a_dropped_face_is_missing():
    b = cube(100.0)
    g = geometry_diff(b, _dump(b, faces=b.face_v[1:, ::-1]))
    assert g["missing"] == 1 and g["matched"] == 11


def test_a_face_unity_turned_round_is_flipped_not_missing():
    b = cube(100.0)
    f = b.face_v[:, ::-1].copy()
    f[0] = f[0, ::-1]
    g = geometry_diff(b, _dump(b, faces=f))
    assert g["flipped"] == 1 and g["missing"] == 0 and g["extra"] == 0


def test_coincident_opposite_faces_count_as_two_each_side():
    b = cube(100.0)
    both = replace(b, face_v=np.vstack([b.face_v, b.face_v[:1, ::-1]]),
                   face_vt=np.vstack([b.face_vt, b.face_vt[:1, ::-1]]),
                   face_vn=np.vstack([b.face_vn, b.face_vn[:1]]),
                   face_material=np.append(b.face_material, 0), face_line=np.arange(1, 14))
    g = geometry_diff(both, _dump(both, faces=both.face_v[:12, ::-1]))   # Unity dropped the back copy
    assert g["missing"] == 1 and g["matched"] == 12


def test_a_16_bit_mesh_over_65535_vertices_is_flagged():
    b = cube(100.0)
    g = geometry_diff(b, _dump(b, index_format="UInt16", vertex_count=70000))
    assert g["index_overflow"] is True
```

- [ ] **Step 2: Run them and see them fail**

Run: `( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_unity_check.py -q -p no:cacheprovider )`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.unity.check'`.

- [ ] **Step 3: Implement**

```python
# engine/unity/check.py
"""Did the engine's build survive Unity's import? Face-by-face, by cause.

Faces are compared as ORIENTED multisets of snapped corner positions in the build's frame, so two coincident faces
of opposite winding stay two faces. A face is `matched` (same corners, same orientation), `flipped` (same corners,
opposite orientation), `missing` (in the build only) or `extra` (in Unity only).
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from engine.model import MeshData
from engine.repair.types import print_step
from engine.unity.align import align, to_build_frame
from engine.unity.dump import UnityDump

UINT16_MAX_VERTICES = 65535
_EXAMPLES = 20


def _oriented_keys(points: np.ndarray, faces: np.ndarray, tol: float, flip: bool) -> list[tuple]:
    q = np.round(points / tol).astype(np.int64)
    out = []
    for f in faces:
        c = [tuple(q[i]) for i in (f[::-1] if flip else f)]
        k = min(range(3), key=lambda i: c[i])            # rotate so the smallest corner is first
        out.append(tuple(c[k:] + c[:k]))
    return out


def _reverse(key: tuple) -> tuple:
    a, b, c = key
    return (a, c, b)


def geometry_diff(build: MeshData, dump: UnityDump) -> dict:
    tol = print_step(build)
    scale = float(dump.sidecar["importer"]["globalScale"])
    a = align(build, dump.mesh, scale, tol)
    det = float(np.linalg.det(a.matrix))
    upts = to_build_frame(dump.mesh.positions, a)
    bkeys = _oriented_keys(build.positions, build.face_v, tol, flip=False)
    ukeys = _oriented_keys(upts, dump.mesh.face_v, tol, flip=det < 0)   # a mirror reverses winding
    bc, uc = Counter(bkeys), Counter(ukeys)
    matched = sum((bc & uc).values())
    b_left, u_left = bc - uc, uc - bc
    flipped = 0
    for k, n in list(b_left.items()):
        r = _reverse(k)
        take = min(n, u_left.get(r, 0))
        if take:
            flipped += take
            b_left[k] -= take
            u_left[r] -= take
    missing = sum(v for v in b_left.values() if v > 0)
    extra = sum(v for v in u_left.values() if v > 0)
    miss_keys = {k for k, v in b_left.items() if v > 0}
    meshes = dump.sidecar.get("meshes", [])
    overflow = any(m.get("index_format") == "UInt16" and m.get("vertex_count", 0) > UINT16_MAX_VERTICES
                   for m in meshes)
    return {
        "alignment": {"match": a.match, "det": det},
        "faces_build": int(build.n_faces), "faces_unity": int(dump.mesh.n_faces),
        "matched": matched, "missing": missing, "extra": extra, "flipped": flipped,
        "index_overflow": overflow,
        "vertex_counts": {m.get("name"): m.get("vertex_count") for m in meshes},
        "examples": {"missing": [i for i, k in enumerate(bkeys) if k in miss_keys][:_EXAMPLES]},
    }
```

- [ ] **Step 4: Run them and see them pass**

Run the same command. Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add engine/unity/check.py engine/tests/test_unity_check.py
git commit -m "feat(unity): oriented face matching between the build and Unity's import (matched/missing/extra/flipped, 16-bit overflow)"
```

---

### Task 4: look, UV and normal causes

**Files:**
- Modify: `engine/unity/check.py` (add `surface_diff`)
- Test: `engine/tests/test_unity_check.py` (append)

**Interfaces:**
- Consumes: `geometry_diff`'s matching, `engine.io.mtl.parse_mtl(path) -> dict[str, MtlMaterial]` (`.map_kd`).
- Produces:
  - `surface_diff(build: MeshData, dump: UnityDump, build_mtl: dict, unity_mtl: dict) -> dict`, with keys
    `material_remapped`, `texture_lost`, `uv_changed`, `normal_against_face`, `normal_smoothed`;
  - for each of these, a count and up to 20 example build face indices.
  - Thresholds, named in code: `UV_TOL = 1e-4`, `SMOOTH_DEG = 1.0`.
  - A build face with material index `-1` has the material name `"<none>"`.

- [ ] **Step 1: Write the failing tests (append)**

```python
def _with(dump, **kw):
    return UnityDump(mesh=replace(dump.mesh, **{k: v for k, v in kw.items() if k != "normals"}),
                     corner_normals=kw.get("normals", dump.corner_normals), sidecar=dump.sidecar)


def _face_normals_unity(dump):
    p = dump.mesh.positions[dump.mesh.face_v]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    return n / np.linalg.norm(n, axis=1)[:, None]


def test_matching_looks_uvs_and_normals_report_nothing():
    from engine.unity.check import surface_diff
    b = cube(100.0)
    d = _dump(b)
    good = np.repeat(_face_normals_unity(d)[:, None, :], 3, axis=1)
    s = surface_diff(b, _with(d, normals=good), {"m0": None}, {"m0": None})
    assert all(s[k]["count"] == 0 for k in
               ("material_remapped", "texture_lost", "uv_changed", "normal_against_face", "normal_smoothed"))


def test_a_corner_normal_pointing_into_the_face_is_named_black_face_cause():
    from engine.unity.check import surface_diff
    b = cube(100.0)
    d = _dump(b)
    n = np.repeat(_face_normals_unity(d)[:, None, :], 3, axis=1)
    n[0] = -n[0]
    s = surface_diff(b, _with(d, normals=n), {"m0": None}, {"m0": None})
    assert s["normal_against_face"]["count"] == 1


def test_a_shifted_uv_is_uv_changed():
    from engine.unity.check import surface_diff
    b = cube(100.0)
    d = _dump(b)
    good = np.repeat(_face_normals_unity(d)[:, None, :], 3, axis=1)
    s = surface_diff(b, _with(d, uvs=d.mesh.uvs + 0.01, normals=good), {"m0": None}, {"m0": None})
    assert s["uv_changed"]["count"] == 12


def test_a_face_without_material_that_unity_gave_a_default_is_remapped_not_a_crash():
    from engine.unity.check import surface_diff
    b = cube(100.0)
    b = replace(b, face_material=np.full(12, -1))
    d = _dump(b)
    d = _with(d, face_material=np.zeros(12, np.int64), materials=["Default-Material"],
              normals=np.repeat(_face_normals_unity(d)[:, None, :], 3, axis=1))
    s = surface_diff(b, d, {}, {"Default-Material": None})
    assert s["material_remapped"]["count"] == 12
```

- [ ] **Step 2: Run them and see them fail**

Run: `( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_unity_check.py -q -p no:cacheprovider )`
Expected: the 4 new tests FAIL with `ImportError: cannot import name 'surface_diff'`.

- [ ] **Step 3: Implement (append to `engine/unity/check.py`)**

```python
UV_TOL = 1e-4
SMOOTH_DEG = 1.0
NO_MATERIAL = "<none>"


def _name(mesh: MeshData, f: int) -> str:
    m = int(mesh.face_material[f])
    return NO_MATERIAL if m < 0 else mesh.materials[m]


def _tex(mtl: dict, name: str):
    e = mtl.get(name)
    return getattr(e, "map_kd", None) if e is not None else None


def _match_pairs(build: MeshData, dump: UnityDump) -> tuple[list[tuple[int, int, list[int]]], np.ndarray]:
    """(build face, unity face, corner order) for every matched face, and Unity's positions in the build frame."""
    tol = print_step(build)
    a = align(build, dump.mesh, float(dump.sidecar["importer"]["globalScale"]), tol)
    flip = np.linalg.det(a.matrix) < 0
    upts = to_build_frame(dump.mesh.positions, a)
    qb = np.round(build.positions / tol).astype(np.int64)
    qu = np.round(upts / tol).astype(np.int64)
    bkeys = _oriented_keys(build.positions, build.face_v, tol, False)
    by_key: dict = {}
    for j, k in enumerate(_oriented_keys(upts, dump.mesh.face_v, tol, flip)):
        by_key.setdefault(k, []).append(j)
    pairs = []
    for i, k in enumerate(bkeys):
        if by_key.get(k):
            j = by_key[k].pop()
            ucorner = {tuple(qu[v]): c for c, v in enumerate(dump.mesh.face_v[j])}
            order = [ucorner[tuple(qb[v])] for v in build.face_v[i]]
            pairs.append((i, j, order))
    return pairs, upts


def surface_diff(build: MeshData, dump: UnityDump, build_mtl: dict, unity_mtl: dict) -> dict:
    pairs, upts = _match_pairs(build, dump)
    found = {k: [] for k in ("material_remapped", "texture_lost", "uv_changed",
                             "normal_against_face", "normal_smoothed")}
    cos_smooth = np.cos(np.radians(SMOOTH_DEG))
    for i, j, order in pairs:
        bn, un = _name(build, i), _name(dump.mesh, j)
        if bn != un:
            found["material_remapped"].append(i)
        if _tex(build_mtl, bn) and not _tex(unity_mtl, un):
            found["texture_lost"].append(i)
        if build.face_vt.size and dump.mesh.face_vt.size:
            buv = build.uvs[build.face_vt[i]]
            uuv = dump.mesh.uvs[dump.mesh.face_vt[j]][order]
            if np.abs(buv - uuv).max() > UV_TOL:
                found["uv_changed"].append(i)
        fn_u = np.cross(*(dump.mesh.positions[dump.mesh.face_v[j]][1:] - dump.mesh.positions[dump.mesh.face_v[j]][0]))
        fn_u = fn_u / max(np.linalg.norm(fn_u), 1e-300)
        dots = dump.corner_normals[j] @ fn_u
        if (dots < 0).any():
            found["normal_against_face"].append(i)
        elif (dots < cos_smooth).any():
            found["normal_smoothed"].append(i)
    return {k: {"count": len(v), "examples": v[:_EXAMPLES]} for k, v in found.items()}
```

- [ ] **Step 4: Run them and see them pass**

Run the same command. Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add engine/unity/check.py engine/tests/test_unity_check.py
git commit -m "feat(unity): name look, texture, UV and normal causes on matched faces (black faces = normal against the face)"
```

---

### Task 5: the verdict and `engine.cli unity-check`

**Files:**
- Modify: `engine/unity/check.py` (add `unity_check`), `engine/cli.py` (add the sub-command)
- Test: `engine/tests/test_cli_unity_check.py`

**Interfaces:**
- Consumes:
  - `geometry_diff` and `surface_diff`;
  - `engine.detectors.errors.find_errors(mesh) -> dict`. Each kind's count is read with `_count(errors, kind)`, as
    `engine/campus/census` reads it; reuse that helper if it exists, otherwise count the kind's list length.
- Produces:
  - `unity_check(build, dump, build_mtl, unity_mtl) -> dict`, with keys `geometry`, `surface`,
    `errors_build`, `errors_unity`, `worse_kinds`, `verdict` (`"UNITY-SAFE"` or `"BROKEN BY IMPORT"`) and
    `causes` (the non-zero cause names);
  - CLI `engine.cli unity-check --build <obj> --unity <dump obj> --out <dir>`. It writes `unity_check.json`. Exit
    0 = UNITY-SAFE, 3 = BROKEN BY IMPORT, 2 = refused (unreadable dump, alignment failure, protected `--out`).

- [ ] **Step 1: Write the failing tests**

```python
# engine/tests/test_cli_unity_check.py
import json

import numpy as np

from engine import cli
from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import cube

M = np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]], float)


def _write_dump(tmp_path, mesh, faces):
    p = (mesh.positions @ M.T) * 0.0254
    lines = ["mtllib d.mtl", "o m"] + [f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in p]
    lines += [f"vt {u} {v}" for u, v in mesh.uvs]
    q = p[faces]
    n = np.cross(q[:, 1] - q[:, 0], q[:, 2] - q[:, 0])
    n /= np.linalg.norm(n, axis=1)[:, None]
    lines += [f"vn {x} {y} {z}" for x, y, z in n]
    lines.append("usemtl m0")
    for k, (f, t) in enumerate(zip(faces, mesh.face_vt[:, ::-1])):
        lines.append("f " + " ".join(f"{a + 1}/{b + 1}/{k + 1}" for a, b in zip(f, t)))
    (tmp_path / "d.obj").write_text("\n".join(lines) + "\n")
    (tmp_path / "d.mtl").write_text("newmtl m0\n")
    side = {"schema": 1, "complete": True, "unity_version": "6000.4.7f1", "asset_path": "x",
            "importer": {"globalScale": 0.0254}, "importer_sha256": "ab", "overrides": {},
            "meshes": [{"name": "m", "vertex_count": len(p), "index_format": "UInt32", "submeshes": []}]}
    (tmp_path / "d.unity.json").write_text(json.dumps(side))
    return tmp_path / "d.obj"


def _build(tmp_path):
    b = cube(100.0)
    write_obj(b, tmp_path / "b.obj")
    return b, tmp_path / "b.obj"


def test_an_unchanged_import_is_unity_safe(tmp_path):
    b, bp = _build(tmp_path)
    dp = _write_dump(tmp_path, b, b.face_v[:, ::-1])
    assert cli.main(["unity-check", "--build", str(bp), "--unity", str(dp), "--out", str(tmp_path / "o")]) == 0
    r = json.loads((tmp_path / "o" / "unity_check.json").read_text())
    assert r["verdict"] == "UNITY-SAFE" and r["causes"] == []


def test_a_dropped_face_is_broken_by_import_with_its_cause(tmp_path):
    b, bp = _build(tmp_path)
    dp = _write_dump(tmp_path, b, b.face_v[1:, ::-1])
    assert cli.main(["unity-check", "--build", str(bp), "--unity", str(dp), "--out", str(tmp_path / "o")]) == 3
    r = json.loads((tmp_path / "o" / "unity_check.json").read_text())
    assert r["verdict"] == "BROKEN BY IMPORT" and "missing" in r["causes"]


def test_an_incomplete_dump_is_refused(tmp_path):
    b, bp = _build(tmp_path)
    dp = _write_dump(tmp_path, b, b.face_v[:, ::-1])
    (tmp_path / "d.unity.json").write_text(json.dumps({"schema": 1, "complete": False}))
    assert cli.main(["unity-check", "--build", str(bp), "--unity", str(dp), "--out", str(tmp_path / "o")]) == 2
```

- [ ] **Step 2: Run them and see them fail**

Run: `( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_cli_unity_check.py -q -p no:cacheprovider )`
Expected: FAIL. argparse exits with `invalid choice: 'unity-check'`, or `SystemExit: 2` from the parser.

- [ ] **Step 3: Implement**

Append to `engine/unity/check.py`:

```python
GEOMETRY_CAUSES = ("missing", "extra", "flipped")
SURFACE_CAUSES = ("material_remapped", "texture_lost", "uv_changed", "normal_against_face")


def _kind_counts(errors: dict) -> dict[str, int]:
    # CORRECTED 2026-10-10 (U1-A review): find_errors keeps the per-kind counts under errors["counts"]
    # (flicker_diff, flicker_same, reversed, hidden, loose, open_edges, cracks). The first version of this plan
    # guessed top-level keys, which compared only 2 of the 7 kinds.
    return {k: int(v) for k, v in errors["counts"].items()}


def unity_check(build: MeshData, dump: UnityDump, build_mtl: dict, unity_mtl: dict) -> dict:
    from engine.detectors.errors import find_errors
    from engine.unity.align import align as _align
    g = geometry_diff(build, dump)
    s = surface_diff(build, dump, build_mtl, unity_mtl)
    a = _align(build, dump.mesh, float(dump.sidecar["importer"]["globalScale"]), print_step(build))
    from dataclasses import replace
    unity_in_build_frame = replace(dump.mesh, positions=to_build_frame(dump.mesh.positions, a),
                                   coord_decimals=build.coord_decimals)
    eb = _kind_counts(find_errors(build))
    eu = _kind_counts(find_errors(unity_in_build_frame))
    worse = sorted(k for k in eb if eu.get(k, 0) > eb[k])
    causes = [c for c in GEOMETRY_CAUSES if g[c]] + [c for c in SURFACE_CAUSES if s[c]["count"]]
    if g["index_overflow"]:
        causes.append("index_overflow")
    causes += [f"worse:{k}" for k in worse]
    return {"geometry": g, "surface": s, "errors_build": eb, "errors_unity": eu, "worse_kinds": worse,
            "causes": causes, "verdict": "UNITY-SAFE" if not causes else "BROKEN BY IMPORT",
            "normal_smoothed": s["normal_smoothed"]["count"]}
```

In `engine/cli.py`, add a sub-parser next to the other sub-commands, following their pattern (add the `--out`
argument name to `_OUTPUT_ARGS`, so the existing protected-path check covers it):

```python
p = sub.add_parser("unity-check", help="did this build survive Unity's import? (exit 0 safe, 3 broken, 2 refused)")
p.add_argument("--build", type=Path, required=True)
p.add_argument("--unity", type=Path, required=True, help="the Unity dump's .obj (sidecar next to it)")
p.add_argument("--out", type=Path, required=True)
```

and its handler:

```python
def cmd_unity_check(build_path: Path, unity_path: Path, out_dir: Path) -> int:
    from engine.io.mtl import parse_mtl
    from engine.io.obj_reader import read_obj
    from engine.unity.align import AlignError
    from engine.unity.check import unity_check
    from engine.unity.dump import DumpError, read_unity_dump
    try:
        dump = read_unity_dump(unity_path)
        build = read_obj(build_path)
        bm = build_path.with_suffix(".mtl")
        um = unity_path.with_suffix(".mtl")
        report = unity_check(build, dump, parse_mtl(bm) if bm.is_file() else {},
                             parse_mtl(um) if um.is_file() else {})
    except (DumpError, AlignError) as e:
        print(f"unity-check refused: {e}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "unity_check.json").write_text(json.dumps(report, indent=2, default=int), encoding="utf-8")
    print(f"{build_path.name}: {report['verdict']} {report['causes']}")
    return 0 if report["verdict"] == "UNITY-SAFE" else 3
```

Dispatch: in `main()`, `if args.cmd == "unity-check": return cmd_unity_check(args.build, args.unity, args.out)`.

- [ ] **Step 4: Run them and see them pass**

Run the same command. Expected: `3 passed`. Then run the whole new set:
`( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_unity_dump.py engine/tests/test_unity_align.py engine/tests/test_unity_check.py engine/tests/test_cli_unity_check.py -q -p no:cacheprovider )`
Expected: `19 passed`.

- [ ] **Step 5: Commit**

```bash
git add engine/unity/check.py engine/cli.py engine/tests/test_cli_unity_check.py
git commit -m "feat(unity): unity-check verdict (UNITY-SAFE / BROKEN BY IMPORT, by cause, find_errors on both) and its CLI"
```

---

### Task 6: the mirror project and the importer sync

**Files:**
- Create:
  - `unity/ImportMirror/` (by Unity: `-createProject`);
  - `unity/ImportMirror/.gitignore`;
  - `tools/unity_mirror.py`;
  - `tools/tests/test_unity_mirror_sync.py`.

**Interfaces:**
- Produces:
  - `tools/unity_mirror.py sync` copies the owner's importer to `unity/ImportMirror/Assets/Editor/CampusModelImporter.cs`
    and writes `importer.sha256`;
  - `check` exits 0 when the copy matches, 1 with both sha256 values when not;
  - functions `owner_importer() -> Path`, `sync(mirror: Path, owner: Path) -> str` (returns the sha256),
    `check(mirror: Path, owner: Path) -> tuple[bool, str, str]`.

- [ ] **Step 1: Write the failing tests**

```python
# tools/tests/test_unity_mirror_sync.py
from pathlib import Path

from tools.unity_mirror import check, sync


def _setup(tmp_path):
    owner = tmp_path / "owner" / "CampusModelImporter.cs"
    owner.parent.mkdir()
    owner.write_text("public class CampusModelImporter {}\n")
    mirror = tmp_path / "mirror"
    (mirror / "Assets" / "Editor").mkdir(parents=True)
    return mirror, owner


def test_sync_copies_the_importer_and_check_passes(tmp_path):
    mirror, owner = _setup(tmp_path)
    sha = sync(mirror, owner)
    assert (mirror / "Assets" / "Editor" / "CampusModelImporter.cs").read_text() == owner.read_text()
    assert check(mirror, owner) == (True, sha, sha)


def test_check_fails_after_the_owner_changes_the_importer_naming_both_hashes(tmp_path):
    mirror, owner = _setup(tmp_path)
    old = sync(mirror, owner)
    owner.write_text("public class CampusModelImporter { int x; }\n")
    ok, have, want = check(mirror, owner)
    assert not ok and have == old and want != old


def test_sync_never_writes_to_the_owner_file(tmp_path):
    mirror, owner = _setup(tmp_path)
    before = owner.stat().st_mtime_ns
    sync(mirror, owner)
    assert owner.stat().st_mtime_ns == before
```

- [ ] **Step 2: Run them and see them fail**

Run: `( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest tools/tests/test_unity_mirror_sync.py -q -p no:cacheprovider )`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.unity_mirror'`.

- [ ] **Step 3: Implement**

```python
# tools/unity_mirror.py
"""Keep the mirror Unity project's copy of the owner's CampusModelImporter.cs identical to the real one.

The owner's project is READ only. The mirror refuses to check anything when its copy differs, so a change the owner
makes cannot leave the import check out of date.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

OWNER_PROJECT = Path("D:/PROJECTS/UC/01-UNITY/UC-Campus")
MIRROR = Path(__file__).resolve().parents[1] / "unity" / "ImportMirror"


def owner_importer() -> Path:
    return OWNER_PROJECT / "Assets" / "Editor" / "CampusModelImporter.cs"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _copy_path(mirror: Path) -> Path:
    return mirror / "Assets" / "Editor" / "CampusModelImporter.cs"


def sync(mirror: Path, owner: Path) -> str:
    dst = _copy_path(mirror)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(owner, dst)                     # reads the owner's file, writes only the mirror
    sha = _sha(dst)
    (mirror / "importer.sha256").write_text(sha + "\n", encoding="ascii")
    return sha


def check(mirror: Path, owner: Path) -> tuple[bool, str, str]:
    dst = _copy_path(mirror)
    have = _sha(dst) if dst.is_file() else ""
    want = _sha(owner)
    return have == want, have, want


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["sync", "check"])
    a = ap.parse_args(argv)
    if a.cmd == "sync":
        print(sync(MIRROR, owner_importer()))
        return 0
    ok, have, want = check(MIRROR, owner_importer())
    print(("OK " if ok else "STALE ") + f"mirror={have or '(none)'} owner={want}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run them and see them pass**

Run the same command. Expected: `3 passed`.

- [ ] **Step 5: Create the mirror project with Unity (one-off, real run)**

Run (background; it takes minutes):

```bash
"D:/SOFTWARE/UNITY/Unity Hub/Editor/6000.4.7f1/Editor/Unity.exe" -batchmode -nographics -quit -createProject "<worktree>/unity/ImportMirror" -logFile "C:/Temp/u1/create.log"
```

Expected: exit 0, with `ProjectSettings/` and `Packages/manifest.json` created. Then write the `.gitignore`:

```gitignore
Library/
Temp/
Logs/
UserSettings/
obj/
*.csproj
*.sln
Assets/Editor/CampusModelImporter.cs
Assets/Editor/CampusModelImporter.cs.meta
Assets/Models/
Assets/Models.meta
importer.sha256
overrides.json
```

Then run `( cd "<worktree>" && "$PY" tools/unity_mirror.py sync && "$PY" tools/unity_mirror.py check )`.
Expected: a sha256, then `OK mirror=<sha> owner=<sha>`.

- [ ] **Step 6: Commit**

```bash
git add tools/unity_mirror.py tools/tests/test_unity_mirror_sync.py unity/ImportMirror/.gitignore unity/ImportMirror/Packages/manifest.json unity/ImportMirror/ProjectSettings
git commit -m "feat(unity): the mirror Unity project (6000.4.7f1) and the sha256-checked sync of the owner's importer"
```

---

### Task 7: the C# exporter, the override postprocessor and the headless runner

**Files:**
- Create:
  - `unity/ImportMirror/Assets/Editor/UcFloorExport.cs`;
  - `unity/ImportMirror/Assets/Editor/UcImportOverrides.cs`;
  - `engine/unity/mirror.py`;
  - `engine/tests/test_unity_mirror.py`.
- Modify: `engine/cli.py` (sub-command `unity-mirror-import`).

**Interfaces:**
- Consumes: `tools.unity_mirror.check` (Task 6), `read_unity_dump` (Task 1).
- Produces:
  - `mirror_import(build_obj: Path, out_dir: Path, *, overrides: dict | None = None, unity_exe: Path | None = None,
    timeout_s: int = 1800) -> Path` returns the dump `.obj`. It raises `MirrorError` on a stale importer, a missing
    Unity, a timeout or a non-zero exit (with the log's last 40 lines).
  - CLI `engine.cli unity-mirror-import --build <obj> --out <dir> [--override key=value ...]`.

- [ ] **Step 1: Write the failing tests**

```python
# engine/tests/test_unity_mirror.py
import os
import shutil
from pathlib import Path

import pytest

from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import cube
from engine.unity import mirror
from engine.unity.mirror import MirrorError, mirror_import


def test_a_stale_importer_copy_is_refused_naming_both_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(mirror, "_importer_ok", lambda: (False, "aaa", "bbb"))
    write_obj(cube(100.0), tmp_path / "b.obj")
    with pytest.raises(MirrorError, match="aaa.*bbb"):
        mirror_import(tmp_path / "b.obj", tmp_path / "out")


def test_a_missing_unity_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(mirror, "_importer_ok", lambda: (True, "a", "a"))
    write_obj(cube(100.0), tmp_path / "b.obj")
    with pytest.raises(MirrorError, match="Unity"):
        mirror_import(tmp_path / "b.obj", tmp_path / "out", unity_exe=tmp_path / "nope.exe")


def test_a_timeout_kills_only_its_own_process_and_leaves_no_valid_dump(tmp_path, monkeypatch):
    monkeypatch.setattr(mirror, "_importer_ok", lambda: (True, "a", "a"))
    killed = []
    monkeypatch.setattr(mirror, "_kill_tree", lambda pid: killed.append(pid))
    fake = tmp_path / "sleep.cmd"
    fake.write_text("@ping -n 30 127.0.0.1 >nul\n")
    write_obj(cube(100.0), tmp_path / "b.obj")
    with pytest.raises(MirrorError, match="timed out"):
        mirror_import(tmp_path / "b.obj", tmp_path / "out", unity_exe=fake, timeout_s=2)
    assert len(killed) == 1
    assert not list((tmp_path / "out").glob("*.unity.json"))


UNITY = Path(os.environ.get("UC_UNITY_EXE", mirror.DEFAULT_UNITY))


@pytest.mark.unity
@pytest.mark.skipif(not UNITY.is_file(), reason="Unity 6000.4.7f1 not installed")
def test_a_real_round_trip_under_a_neutral_preset_is_unity_safe(tmp_path):
    from engine import cli
    write_obj(cube(100.0), tmp_path / "b.obj")
    neutral = {"weldVertices": "false", "importNormals": "Import", "meshCompression": "Off",
               "indexFormat": "UInt32"}
    dump = mirror_import(tmp_path / "b.obj", tmp_path / "dump", overrides=neutral)
    assert cli.main(["unity-check", "--build", str(tmp_path / "b.obj"), "--unity", str(dump),
                     "--out", str(tmp_path / "chk")]) == 0
```

Register the marker in `pyproject.toml` `[tool.pytest.ini_options] markers` as `"unity: launches the Unity editor
headless"`, following the existing markers' format.

- [ ] **Step 2: Run them and see them fail**

Run: `( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_unity_mirror.py -q -p no:cacheprovider )`
Expected: FAIL with `ImportError: cannot import name 'mirror' from 'engine.unity'`.

- [ ] **Step 3: Implement the runner**

```python
# engine/unity/mirror.py
"""Route A: import an engine build in the mirror Unity project, headless, and return Unity's dump.

The owner's project is never touched. The run is refused when the mirror's copy of the owner's importer is stale.
Unity is stopped only by its own PID tree, and the dump's sidecar is written last by the exporter, so a dead run
never leaves a dump that reads as valid.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from tools.unity_mirror import MIRROR, check, owner_importer

DEFAULT_UNITY = Path("D:/SOFTWARE/UNITY/Unity Hub/Editor/6000.4.7f1/Editor/Unity.exe")
STAGE = "Assets/Models/Campus/_check"


class MirrorError(RuntimeError):
    """The mirror import could not produce a trustworthy dump."""


def _importer_ok():
    return check(MIRROR, owner_importer())


def _kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)   # by PID only


def _stage(build_obj: Path, name: str) -> Path:
    dst = MIRROR / STAGE / name
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    shutil.copyfile(build_obj, dst / f"{name}.obj")
    mtl = build_obj.with_suffix(".mtl")
    if mtl.is_file():
        shutil.copyfile(mtl, dst / f"{name}.mtl")
    tex = build_obj.parent / "tex"
    if tex.is_dir():
        shutil.copytree(tex, dst / "tex")
    return dst


def mirror_import(build_obj: Path, out_dir: Path, *, overrides: dict | None = None,
                  unity_exe: Path | None = None, timeout_s: int = 1800) -> Path:
    ok, have, want = _importer_ok()
    if not ok:
        raise MirrorError(f"mirror importer copy is stale: mirror {have or '(none)'} != owner {want}; "
                          f"run tools/unity_mirror.py sync")
    exe = Path(unity_exe or os.environ.get("UC_UNITY_EXE", DEFAULT_UNITY))
    if not exe.is_file():
        raise MirrorError(f"Unity not found at {exe}")
    name = Path(build_obj).stem.replace(" ", "_")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{name}.*"):
        old.unlink()
    _stage(Path(build_obj), name)
    (MIRROR / "overrides.json").write_text(json.dumps(overrides or {}), encoding="utf-8")
    log = out_dir / f"{name}.unity.log"
    cmd = [str(exe), "-batchmode", "-nographics", "-quit", "-projectPath", str(MIRROR),
           "-executeMethod", "UcFloorExport.ExportFromCli", "-ucAsset", f"{STAGE}/{name}/{name}.obj",
           "-ucOut", str(out_dir), "-ucName", name, "-logFile", str(log)]
    proc = subprocess.Popen(cmd)
    try:
        code = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        raise MirrorError(f"Unity timed out after {timeout_s} s (killed PID {proc.pid} only)")
    tail = "\n".join(log.read_text(errors="replace").splitlines()[-40:]) if log.is_file() else "(no log)"
    if code != 0:
        raise MirrorError(f"Unity exited {code}:\n{tail}")
    dump = out_dir / f"{name}.obj"
    if not (out_dir / f"{name}.unity.json").is_file():
        raise MirrorError(f"Unity finished but wrote no sidecar:\n{tail}")
    return dump
```

- [ ] **Step 4: Implement the two C# files**

```csharp
// unity/ImportMirror/Assets/Editor/UcImportOverrides.cs
// MIRROR-ONLY. Runs AFTER the owner's CampusModelImporter (higher postprocess order) and applies
// overrides.json (one setting at a time, for the cause hunt). With {} it changes nothing.
using System.IO;
using UnityEditor;
using UnityEngine;

public class UcImportOverrides : AssetPostprocessor
{
    public override int GetPostprocessOrder() => 1000;

    void OnPreprocessModel()
    {
        var path = Path.Combine(Directory.GetCurrentDirectory(), "overrides.json");
        if (!File.Exists(path)) return;
        var o = JsonUtility.FromJson<Overrides>(File.ReadAllText(path));
        var imp = (ModelImporter)assetImporter;
        if (!string.IsNullOrEmpty(o.weldVertices)) imp.weldVertices = o.weldVertices == "true";
        if (!string.IsNullOrEmpty(o.importNormals))
            imp.importNormals = (ModelImporterNormals)System.Enum.Parse(typeof(ModelImporterNormals), o.importNormals);
        if (!string.IsNullOrEmpty(o.meshCompression))
            imp.meshCompression = (ModelImporterMeshCompression)System.Enum.Parse(typeof(ModelImporterMeshCompression), o.meshCompression);
        if (!string.IsNullOrEmpty(o.indexFormat))
            imp.indexFormat = (ModelImporterIndexFormat)System.Enum.Parse(typeof(ModelImporterIndexFormat), o.indexFormat);
        if (!string.IsNullOrEmpty(o.normalSmoothingAngle)) imp.normalSmoothingAngle = float.Parse(o.normalSmoothingAngle);
        if (!string.IsNullOrEmpty(o.generateSecondaryUV)) imp.generateSecondaryUV = o.generateSecondaryUV == "true";
    }

    [System.Serializable]
    class Overrides
    {
        public string weldVertices, importNormals, meshCompression, indexFormat, normalSmoothingAngle, generateSecondaryUV;
    }
}
```

```csharp
// unity/ImportMirror/Assets/Editor/UcFloorExport.cs
// Imports one staged OBJ under the project's postprocessors (the owner's CampusModelImporter copy, then
// UcImportOverrides) and writes what Unity made of it: <name>.obj, <name>.mtl, then <name>.unity.json LAST.
// Never saves a scene. Exits 0 on success, 1 on any exception.
using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEngine;

public static class UcFloorExport
{
    static string Arg(string key)
    {
        var a = Environment.GetCommandLineArgs();
        int i = Array.IndexOf(a, key);
        return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
    }

    public static void ExportFromCli()
    {
        try
        {
            string asset = Arg("-ucAsset"), outDir = Arg("-ucOut"), name = Arg("-ucName");
            AssetDatabase.ImportAsset(asset, ImportAssetOptions.ForceUpdate | ImportAssetOptions.ForceSynchronousImport);
            var root = AssetDatabase.LoadAssetAtPath<GameObject>(asset);
            if (root == null) throw new Exception("Unity imported nothing at " + asset);
            Directory.CreateDirectory(outDir);
            Write(root, (ModelImporter)AssetImporter.GetAtPath(asset), asset, outDir, name);
            EditorApplication.Exit(0);
        }
        catch (Exception e)
        {
            Debug.LogError("UcFloorExport failed: " + e);
            EditorApplication.Exit(1);
        }
    }

    static string F(float x) => x.ToString("R", CultureInfo.InvariantCulture);

    static void Write(GameObject root, ModelImporter imp, string asset, string outDir, string name)
    {
        var obj = new StringBuilder($"mtllib {name}.mtl\n");
        var mtl = new StringBuilder();
        var seen = new System.Collections.Generic.HashSet<string>();
        var meshes = new StringBuilder();
        int vBase = 1;
        foreach (var mf in root.GetComponentsInChildren<MeshFilter>(true))
        {
            var mesh = mf.sharedMesh;
            var mr = mf.GetComponent<MeshRenderer>();
            var rel = root.transform.worldToLocalMatrix * mf.transform.localToWorldMatrix;
            var nrel = rel.inverse.transpose;
            obj.Append($"o {mesh.name}\n");
            foreach (var v in mesh.vertices) { var p = rel.MultiplyPoint3x4(v); obj.Append($"v {F(p.x)} {F(p.y)} {F(p.z)}\n"); }
            var uv = mesh.uv;
            for (int i = 0; i < mesh.vertexCount; i++) { var t = i < uv.Length ? uv[i] : Vector2.zero; obj.Append($"vt {F(t.x)} {F(t.y)}\n"); }
            foreach (var n in mesh.normals) { var q = nrel.MultiplyVector(n).normalized; obj.Append($"vn {F(q.x)} {F(q.y)} {F(q.z)}\n"); }
            var subs = new StringBuilder();
            for (int s = 0; s < mesh.subMeshCount; s++)
            {
                var mat = mr != null && s < mr.sharedMaterials.Length ? mr.sharedMaterials[s] : null;
                string mname = mat != null ? mat.name : "<none>";
                string tex = mat != null && mat.mainTexture != null ? Path.GetFileName(AssetDatabase.GetAssetPath(mat.mainTexture)) : null;
                if (seen.Add(mname)) { mtl.Append($"newmtl {mname}\n"); if (tex != null) mtl.Append($"map_Kd {tex}\n"); }
                obj.Append($"usemtl {mname}\n");
                var tri = mesh.GetTriangles(s);
                for (int k = 0; k < tri.Length; k += 3)
                {
                    int a = tri[k] + vBase, b = tri[k + 1] + vBase, c = tri[k + 2] + vBase;
                    obj.Append($"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n");
                }
                if (subs.Length > 0) subs.Append(',');
                subs.Append($"{{\"material\":{Json(mname)},\"texture\":{(tex == null ? "null" : Json(tex))},\"triangle_count\":{tri.Length / 3}}}");
            }
            vBase += mesh.vertexCount;
            if (meshes.Length > 0) meshes.Append(',');
            meshes.Append($"{{\"name\":{Json(mesh.name)},\"vertex_count\":{mesh.vertexCount},\"index_format\":\"{mesh.indexFormat}\",\"submeshes\":[{subs}]}}");
        }
        File.WriteAllText(Path.Combine(outDir, name + ".obj"), obj.ToString());
        File.WriteAllText(Path.Combine(outDir, name + ".mtl"), mtl.ToString());
        string owner = File.ReadAllText(Path.Combine(Application.dataPath, "Editor", "CampusModelImporter.cs"));
        string sha;
        using (var h = SHA256.Create()) sha = string.Concat(h.ComputeHash(Encoding.UTF8.GetBytes(owner)).Select(x => x.ToString("x2")));
        string ov = File.Exists("overrides.json") ? File.ReadAllText("overrides.json") : "{}";
        var side = "{\"schema\":1,\"complete\":true,\"unity_version\":" + Json(Application.unityVersion) +
                   ",\"asset_path\":" + Json(asset) +
                   ",\"importer\":{\"globalScale\":" + F(imp.globalScale) + ",\"useFileUnits\":" + (imp.useFileUnits ? "true" : "false") +
                   ",\"weldVertices\":" + (imp.weldVertices ? "true" : "false") + ",\"importNormals\":" + Json(imp.importNormals.ToString()) +
                   ",\"normalSmoothingAngle\":" + F(imp.normalSmoothingAngle) + ",\"meshCompression\":" + Json(imp.meshCompression.ToString()) +
                   ",\"indexFormat\":" + Json(imp.indexFormat.ToString()) + ",\"generateSecondaryUV\":" + (imp.generateSecondaryUV ? "true" : "false") +
                   ",\"isReadable\":" + (imp.isReadable ? "true" : "false") + "}" +
                   ",\"importer_sha256\":" + Json(sha) + ",\"overrides\":" + ov + ",\"meshes\":[" + meshes + "]}";
        File.WriteAllText(Path.Combine(outDir, name + ".unity.json"), side);   // LAST: marks the dump complete
    }

    static string Json(string s) => "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
}
```

The sidecar's sha256 hashes the file's text as UTF-8. `tools/unity_mirror.py` hashes bytes. **Make them agree:**
the Python side decodes the copy and re-encodes it as UTF-8 before hashing (`hashlib.sha256(p.read_text(encoding=
"utf-8-sig").encode("utf-8"))`). Change `_sha` in Task 6's file to that, and add a test that a file with a BOM hashes
the same both ways.

- [ ] **Step 5: Add the CLI sub-command**

```python
p = sub.add_parser("unity-mirror-import", help="route A: import a build in the mirror Unity project and dump it")
p.add_argument("--build", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
p.add_argument("--override", action="append", default=[], metavar="KEY=VALUE")
```

```python
def cmd_unity_mirror_import(build: Path, out_dir: Path, overrides: list[str]) -> int:
    from engine.unity.mirror import MirrorError, mirror_import
    ov = dict(o.split("=", 1) for o in overrides)
    try:
        dump = mirror_import(build, out_dir, overrides=ov)
    except MirrorError as e:
        print(f"unity-mirror-import failed: {e}", file=sys.stderr)
        return 2
    print(dump)
    return 0
```

Add `--out` to `_OUTPUT_ARGS` for `unity-mirror-import`.

- [ ] **Step 6: Run the tests and see them pass**

Run: `( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_unity_mirror.py tools/tests/test_unity_mirror_sync.py -q -p no:cacheprovider )`
Expected: all pass, including `test_a_real_round_trip_under_a_neutral_preset_is_unity_safe`, which launches Unity
(minutes on the first import). If the real round trip is not UNITY-SAFE under the neutral preset, **stop**: report
the `unity_check.json` causes. The exporter or the frame mapping is wrong, and that must be fixed before Task 8.

- [ ] **Step 7: Commit**

```bash
git add engine/unity/mirror.py engine/cli.py engine/tests/test_unity_mirror.py tools/unity_mirror.py tools/tests/test_unity_mirror_sync.py unity/ImportMirror/Assets/Editor/UcFloorExport.cs unity/ImportMirror/Assets/Editor/UcImportOverrides.cs pyproject.toml
git commit -m "feat(unity): route A - headless mirror import + exporter (sidecar last), override postprocessor, unity-mirror-import CLI"
```

---

### Task 8: measure the golden floors and isolate the cause (real runs; no code unless a bug is found)

**Files:**
- Create: `docs/superpowers/records/unity/2026-10-10-import-check.md` (the measured table), with the outputs under
  `C:/Temp/u1/`.

- [ ] **Step 1: Build the inputs.** Use the engine's current output and the raw BEFORE for each golden floor:

```bash
( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m engine.cli repair-unit --unit CHTM-L05 --engines E8a,E3 --out C:/Temp/u1/chtm5 --materials "D:/PROJECTS/UC MODEL FIXER/data/campus/materials.json" )
( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m engine.cli repair-unit --snapshot "D:/PROJECTS/UC MODEL FIXER/data/snapshots/ce26e0392ab0" --engines E8a,E3 --out C:/Temp/u1/swA --materials "D:/PROJECTS/UC MODEL FIXER/data/campus/materials.json" )
( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m engine.cli repair-unit --snapshot "D:/PROJECTS/UC MODEL FIXER/data/snapshots/0b290ec0bcb4" --engines E8a,E3 --out C:/Temp/u1/swB --materials "D:/PROJECTS/UC MODEL FIXER/data/campus/materials.json" )
```

- [ ] **Step 2: Route A under the owner's real importer** (overrides `{}`), then `unity-check`, for each of the
  three `*.fixed.obj` files and the three BEFOREs:

```bash
( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m engine.cli unity-mirror-import --build C:/Temp/u1/chtm5/CHTM-L05.fixed.obj --out C:/Temp/u1/chtm5/unity )
( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m engine.cli unity-check --build C:/Temp/u1/chtm5/CHTM-L05.fixed.obj --unity C:/Temp/u1/chtm5/unity/CHTM-L05.fixed.obj --out C:/Temp/u1/chtm5/check )
```

(The same for swA and swB, and for the BEFORE OBJ files that `repair-unit` writes next to the build.)

- [ ] **Step 3: One setting at a time.** For each floor that is BROKEN BY IMPORT, re-run route A with one override
  each, and record which override makes each cause go away:
  - `weldVertices=false`;
  - `importNormals=Import`;
  - `normalSmoothingAngle=0`;
  - `indexFormat=UInt32`;
  - `generateSecondaryUV=false`.
- [ ] **Step 4: Write the table**, in `docs/superpowers/records/unity/2026-10-10-import-check.md`. Per floor and
  setting, give:
  - the verdict, and causes with counts;
  - `errors_build` against `errors_unity` per kind;
  - vertex counts and `index_format`;
  - the time.

  Add pictures of the 3 worst faces per cause, rendered with the existing renderer from the dump. **Look at them and
  describe them.**
- [ ] **Step 5: Propose, do not apply.** If a setting fixes the breaks, write the proposed change to the owner's
  `CampusModelImporter.cs` as a diff in the record, with its measured effect. **The owner decides**; this plan
  never writes to the owner's project.
- [ ] **Step 6: Commit the record**

```bash
git add docs/superpowers/records/unity/2026-10-10-import-check.md
git commit -m "docs(unity): measured import check on CHTM 5th and sidewalks A and B, cause by cause, with the proposed importer change"
```

---

## Self-review

- **Spec coverage (Part 1, plus Part 2's measurement step):**
  - route A, the mirror project: Tasks 6 and 7;
  - the dump format and the frame: Tasks 1 and 2;
  - the per-cause compare and the verdict with `find_errors` on both: Tasks 3 to 5;
  - the mirror's sha256 refusal: Tasks 6 and 7;
  - the exporter's own round-trip check: Task 7, step 6;
  - one setting at a time on the golden floors, with the change proposed and never applied: Task 8.
  - Route B, Parts 3 to 6, and Part 2's swap, records and check scene: their own plans, as the scope check said.
- **Placeholders:** none. Every code step has code. `<worktree>` and `$PY` are defined in Global Constraints.
- **Names used across tasks:**
  - `read_unity_dump` / `UnityDump` (Task 1), used in 3-5 and 7;
  - `align` / `to_build_frame` / `AlignError` (Task 2), used in 3-5;
  - `geometry_diff`, `surface_diff`, `unity_check` (Tasks 3-5), used by the CLI;
  - `mirror_import` / `MirrorError` (Task 7), used by the CLI and Task 8;
  - `sync` / `check` (Task 6), used in 7.
- **Review Focus coverage:**
  1. 16-bit overflow: Task 3's test.
  2. Coincident opposite faces: Task 3's test.
  3. A face with no material: Task 4's test.
  4. A stale importer: Tasks 6 and 7's tests.
  5. A missing Unity or a timeout, with no half dump: Task 7's tests, and Task 1's `complete` test.
