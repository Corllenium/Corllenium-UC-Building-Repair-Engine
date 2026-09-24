# Implementation Report: Tasks 2-4 (OBJ Reader, OBJ Writer, MTL/Texture)

## Summary

All three tasks completed successfully. Following strict TDD workflow: failing tests written first, red phase verified, implementations applied, green phase confirmed, committed. All 10 tests pass (3 for Task 2, 2 for Task 3, 2 for Task 4, plus 3 earlier fixture tests).

---

## Task 2: OBJ Reader

### What Was Implemented

Created `engine/io/obj_reader.py` with:
- `ObjFormatError` exception class for format violations
- `_index()` helper to parse 1-based OBJ indices (positive and negative)
- `read_obj(path: Path) -> MeshData` reader

The reader:
- Parses vertices (v), texture coords (vt), normals (vn)
- Tracks material (usemtl) assignments and maintains order
- Rejects non-triangle faces with clear error message
- Preserves face order (face i = i-th f line in file)
- Falls back to filename stem if no object name given
- Tracks coordinate precision (decimals, significant digits)

### TDD Evidence

**RED phase:**
```bash
cd /d/PROJECTS/UC MODEL FIXER && .venv/Scripts/python.exe -m pytest engine/tests/test_obj_reader.py -q
```
Exit code 2, `ModuleNotFoundError: No module named 'engine.io.obj_reader'` ✓

**GREEN phase (after implementation):**
```bash
cd /d/PROJECTS/UC MODEL FIXER && .venv/Scripts/python.exe -m pytest engine/tests/test_obj_reader.py -q
```
Output: `3 passed in 0.21s` ✓

### Files Changed

- Created: `engine/io/obj_reader.py` (70 lines)
- Created: `engine/tests/test_obj_reader.py` (56 lines)

### Self-Review

Tests are comprehensive:
- `test_reads_arrays_and_keeps_face_order`: validates all arrays match expected shape, values, and ordering
- `test_rejects_quads`: confirms error on non-triangle face with line number
- `test_name_falls_back_to_stem`: verifies fallback behavior

Implementation follows spec exactly. No overbuilding.

---

## Task 3: OBJ Writer

### What Was Implemented

Created `engine/io/obj_writer.py` with:
- `_num(x: float, decimals: int) -> str` helper for deterministic float formatting
- `write_obj(mesh: MeshData, path: Path) -> None` writer

The writer:
- Outputs deterministic OBJ from MeshData (same input → same bytes)
- Writes comment with mesh name
- Includes mtllib reference if present
- Emits vertices with coordinate precision from mesh.coord_decimals
- Emits UVs and normals with 6-decimal precision
- Tracks material switches and emits usemtl before faces using that material
- Handles all face index combinations (v, v/vt, v//vn, v/vt/vn)
- Uses `newline="\n"` to ensure LF line endings (determinism across platforms)

### TDD Evidence

**RED phase:**
```bash
cd /d/PROJECTS/UC MODEL FIXER && .venv/Scripts/python.exe -m pytest engine/tests/test_obj_writer.py -q
```
Exit code 2, `ModuleNotFoundError: No module named 'engine.io.obj_writer'` ✓

**GREEN phase (after implementation):**
```bash
cd /d/PROJECTS/UC MODEL FIXER && .venv/Scripts/python.exe -m pytest engine/tests/test_obj_writer.py -q
```
Output: `2 passed in 0.20s` ✓

### Files Changed

- Created: `engine/io/obj_writer.py` (37 lines)
- Created: `engine/tests/test_obj_writer.py` (22 lines)

### Self-Review

Tests validate:
- `test_round_trip_preserves_everything`: reads back what was written, arrays and materials match
- `test_write_is_deterministic`: byte-identical output on repeated writes of same input

Implementation is minimal and correct. The `_num()` helper ensures trailing zeros and signs are handled consistently. Material switching logic emits usemtl only on transitions.

---

## Task 4: MTL Subset and Texture Flatness

### What Was Implemented

Created `engine/io/mtl.py` with:
- `MtlMaterial` dataclass: name, lines list, optional map_kd texture path
- `parse_mtl(path: Path) -> dict[str, MtlMaterial]`: parses MTL files, preserves all lines, extracts map_Kd
- `write_mtl_subset(materials, used, dst, texture_dir="tex") -> dict[str, str]`: writes subset of materials to new MTL, remaps texture paths to texture_dir, returns {material -> source_path} for used materials with textures
- `texture_flatness(path: Path) -> float`: converts image to RGB, computes per-channel std dev, returns max (0-255 scale)

### TDD Evidence

**RED phase:**
```bash
cd /d/PROJECTS/UC MODEL FIXER && .venv/Scripts/python.exe -m pytest engine/tests/test_mtl.py -q
```
Exit code 2, `ModuleNotFoundError: No module named 'engine.io.mtl'` ✓

**GREEN phase (after implementation):**
```bash
cd /d/PROJECTS/UC MODEL FIXER && .venv/Scripts/python.exe -m pytest engine/tests/test_mtl.py -q
```
Output: `2 passed in 0.27s` ✓

### Files Changed

- Created: `engine/io/mtl.py` (54 lines)
- Created: `engine/tests/test_mtl.py` (40 lines)

### Self-Review

Tests validate:
- `test_parse_and_subset`: parses MTL, extracts map_Kd, subsets to used materials, remaps texture paths, omits unused materials
- `test_texture_flatness`: distinguishes flat images (std < 5.0) from patterned (std > 100.0) using real PIL images

Implementation is correct. `write_mtl_subset` returns the subset of materials that have textures (as required), remaps paths to `texture_dir/filename`, uses PurePosixPath to normalize backslashes.

---

## Full Test Suite Verification

After all three tasks committed:

```bash
cd /d/PROJECTS/UC MODEL FIXER && .venv/Scripts/python.exe -m pytest -q
```

**Output:** `10 passed in 0.34s` ✓

All 10 tests pass:
- 3 from task-2-brief (test_obj_reader.py)
- 2 from task-3-brief (test_obj_writer.py)
- 2 from task-4-brief (test_mtl.py)
- 3 earlier fixture tests (test_fixtures.py)

No earlier tests broken.

---

## Commits Created

1. **Commit ed1f712**: `feat(engine): strict OBJ reader with stable face ids`
   - Files: engine/io/obj_reader.py, engine/tests/test_obj_reader.py

2. **Commit 65db33f**: `feat(engine): deterministic OBJ writer`
   - Files: engine/io/obj_writer.py, engine/tests/test_obj_writer.py

3. **Commit f34af60**: `feat(engine): MTL subset and texture flatness`
   - Files: engine/io/mtl.py, engine/tests/test_mtl.py

---

## Concerns

None. All three tasks completed to spec, tests pass, no edge cases or ambiguities encountered.

Implementation exactly matches briefs: test code verbatim, implementation code verbatim from briefs, no deviations.

All code follows existing project patterns and imports nothing prohibited (no api, fastapi, sqlalchemy).

Face ordering preserved (face i = i-th f line), no reordering or merging. All tests confirm exact array equality.

---

## Notes for Review

- Implementations are deterministic and verifiable
- Round-trip I/O tested (write then read, verify byte-for-byte or array equality)
- Error handling for format violations (quads rejected with line number)
- Material subset logic correctly filters materials and remaps texture paths
- Texture flatness captures per-channel variance, distinguishing flat from patterned images
