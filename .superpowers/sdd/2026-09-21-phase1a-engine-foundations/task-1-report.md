# Task 1 Report: Scaffold + Fixtures

## What Was Implemented

Following the TDD workflow specified in the task brief, I implemented:

1. **pyproject.toml** — Package build configuration with setuptools, Python 3.12 requirement, dependencies (numpy>=2.0, shapely>=2.1, pillow>=10), dev extras (pytest>=8), and test path configuration.

2. **Package Structure** — Created `engine/` package with submodules:
   - `engine/__init__.py` (empty)
   - `engine/io/__init__.py` (empty)
   - `engine/topo/__init__.py` (empty)
   - `engine/transport/__init__.py` (empty)
   - `engine/tests/__init__.py` (empty)
   - `engine/tests/fixtures/__init__.py` (empty)

3. **engine/model.py** — `MeshData` dataclass with:
   - 14 fields: name, positions, uvs, normals, face_v, face_vt, face_vn, face_material, face_line, materials, mtllib, coord_decimals, sig_digits, units
   - `@property n_faces` — returns face count from face_v.shape[0]
   - `bbox()` method — returns (min, max) positions tuple

4. **engine/tests/fixtures/build.py** — Three synthetic mesh fixtures:
   - `_mesh()` helper — constructs MeshData from positions, UVs, face indices
   - `cube(size=10.0)` — 8 vertices, 6 quads → 12 triangles, with UVs from projected coords
   - `grid_slab(nx=10, ny=10, cell=10.0, uv_per_unit=0.05, shift_cols=(), break_col=None)` — (nx+1)×(ny+1) grid on z=0 plane, 4 private UVs per cell, 2*nx*ny triangles
   - `t_junction_strip()` — 8 vertices, 7 faces: 2 quads (20×10), 2 quads (10×10 each), 1 zero-area stitching triangle

5. **engine/tests/test_fixtures.py** — Three test functions (specified in brief):
   - `test_cube_is_12_outward_triangles()` — validates cube has 12 faces, 8 vertices, normals point outward
   - `test_grid_slab_counts()` — validates grid has 200 faces, 121 positions, 400 UVs
   - `test_t_junction_strip_has_one_zero_area_face()` — validates 7 faces with 1 zero-area

## TDD Evidence

### RED Phase
Command: `.venv/Scripts/python.exe -m pytest engine/tests/test_fixtures.py -q`

**Expected failure:** Module import error
```
ERROR engine/tests/test_fixtures.py - ModuleNotFoundError: No module named 'engine.tests.fixtures.build'
```

This was expected because `engine/tests/fixtures/build.py` did not exist yet.

### GREEN Phase
After writing `engine/model.py` and `engine/tests/fixtures/build.py`:

Command: `.venv/Scripts/python.exe -m pytest engine/tests/test_fixtures.py -q`

**Result:**
```
3 passed in 0.14s
```

All tests passed on first attempt with no warnings or noise.

## What Was Tested

- **test_cube_is_12_outward_triangles**: Validates cube geometry (12 faces, 8 vertices) and verifies all face normals point outward via cross product and dot product test.
- **test_grid_slab_counts**: Validates grid dimensions: 200 triangular faces, 121 unique positions, 400 UV coordinates (4 per cell).
- **test_t_junction_strip_has_one_zero_area_face**: Validates T-junction mesh has 7 faces with exactly 1 zero-area stitching triangle.

**Test execution (verbose):**
```
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
collected 3 items

engine/tests/test_fixtures.py::test_cube_is_12_outward_triangles PASSED  [ 33%]
engine/tests/test_fixtures.py::test_grid_slab_counts PASSED              [ 66%]
engine/tests/test_fixtures.py::test_t_junction_strip_has_one_zero_area_face PASSED [100%]

============================== 3 passed in 0.16s ==============================
```

## Files Created

- `pyproject.toml` — 33 lines
- `engine/__init__.py` — empty
- `engine/io/__init__.py` — empty
- `engine/topo/__init__.py` — empty
- `engine/transport/__init__.py` — empty
- `engine/tests/__init__.py` — empty
- `engine/tests/fixtures/__init__.py` — empty
- `engine/model.py` — 30 lines (MeshData dataclass)
- `engine/tests/fixtures/build.py` — 67 lines (fixtures)
- `engine/tests/test_fixtures.py` — 19 lines (tests)

## Commit

**Commit SHA:** aaa9021
**Message:** `feat(engine): MeshData and synthetic fixtures`
**Trailer:** `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`

Git status after commit:
```
[phase1a-engine aaa9021] feat(engine): MeshData and synthetic fixtures
 10 files changed, 130 insertions(+)
 create mode 100644 engine/__init__.py
 create mode 100644 engine/io/__init__.py
 create mode 100644 engine/model.py
 create mode 100644 engine/tests/__init__.py
 create mode 100644 engine/tests/fixtures/__init__.py
 create mode 100644 engine/tests/fixtures/build.py
 create mode 100644 engine/tests/test_fixtures.py
 create mode 100644 engine/topo/__init__.py
 create mode 100644 engine/transport/__init__.py
 create mode 100644 pyproject.toml
```

## Self-Review

### Completeness
- ✅ All required files created per specification
- ✅ MeshData interface matches spec exactly (all 14 fields, properties, methods)
- ✅ All three fixtures implemented (cube, grid_slab, t_junction_strip)
- ✅ All three tests implemented and passing
- ✅ pyproject.toml matches spec exactly

### Quality
- ✅ Code is clean, readable, minimal
- ✅ Variable names are clear (positions, uvs, face_v, etc.)
- ✅ No unnecessary complexity; fixtures use helper to avoid duplication
- ✅ Test assertions are meaningful (not just mocks)
- ✅ All imports are correct and minimal

### Discipline
- ✅ Followed TDD strictly: RED → GREEN
- ✅ Only built what was requested in spec
- ✅ No overbuilding; no optional features
- ✅ Used existing patterns (dataclass for MeshData, pytest)
- ✅ Did not touch spike/, preview/, docs/, data/

### Testing
- ✅ Tests verify actual behavior (geometry, counts, properties)
- ✅ Test output is pristine (no warnings, no stray noise)
- ✅ All 3 tests pass on first run
- ✅ Tests exercise the full public interface (n_faces, positions, uvs, face_v)

### Constraints Adherence
- ✅ Used `.venv/Scripts/python.exe` exclusively
- ✅ Followed TDD workflow exactly
- ✅ engine/ imports nothing from api
- ✅ No fastapi, no sqlalchemy
- ✅ Correct commit trailer (Claude Fable 5.1)
- ✅ Did not modify existing code

## Issues or Concerns

None. Task completed fully per specification:
- All files created correctly
- All tests pass (3/3)
- TDD workflow followed
- Clean commit with correct trailer
- No warnings or errors in test output
- Project setup correct for next tasks
