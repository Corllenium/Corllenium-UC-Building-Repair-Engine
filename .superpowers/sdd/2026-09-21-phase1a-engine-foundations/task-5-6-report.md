# Task 5 & 6 Implementation Report

## Summary
Both Task 5 (Snapshot importer) and Task 6 (Topology basics) have been completed and committed successfully. All tests pass, and the real-data check for Task 5 succeeds against the live export folder.

---

## Task 5: Snapshot Importer with Stability and Manifest Checks

### What Was Implemented
Created two new files:
- `engine/io/snapshot.py`: Complete snapshot importer with SHA256 hashing, stability checks, and asset subsetting
- `engine/tests/test_snapshot.py`: Full test suite with 5 tests

### Key Features Implemented
1. **SourceUnstable** exception for source file stability issues
2. **ManifestMismatch** exception for triangle count validation
3. **ManifestRow** dataclass for parsed manifest entries
4. **SnapshotResult** dataclass for snapshot output with full metadata
5. **read_manifest()**: Parses CSV-style manifest files with thousands separators
6. **sha256_file()**: Computes SHA256 hash of files in 1MB chunks
7. **wait_stable()**: Verifies file stability via size/mtime checks
8. **snapshot_object()**: Main importer function with full pipeline
9. Helper functions for asset copying and loading

### TDD Evidence

**RED (Failing Test):**
```bash
$ .venv/Scripts/python.exe -m pytest engine/tests/test_snapshot.py -q
ModuleNotFoundError: No module named 'engine.io.snapshot'
```

**GREEN (Passing Tests):**
```bash
$ .venv/Scripts/python.exe -m pytest engine/tests/test_snapshot.py -q
.....                                                                    [100%]
5 passed in 0.40s
```

### Real-Data Check (Step 4)
Command executed against live data at `D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17\split`:

```bash
$ .venv/Scripts/python.exe task5_real_data_check.py
ce26e0392ab0907c5c65ab429abeb9ba4911d6252b69134e27c933941bac16fa 4692 {'mumi_littletiles_ltstone_-7': 3.0438862544900456} []
```

**Output Breakdown:**
- SHA256: `ce26e0392ab0907c5c65ab429abeb9ba4911d6252b69134e27c933941bac16fa` (64 hex chars, as expected)
- Faces: `4692` (matches manifest entry exactly)
- Flatness: `{'mumi_littletiles_ltstone_-7': 3.0438862544900456}` (approximately 3.04, within expected ~3.04)
- Missing textures: `[]` (all textures found)

**Status:** PASS - No SourceUnstable errors, all outputs within expected range.

### Files Changed
- Created: `engine/io/snapshot.py` (120 lines)
- Created: `engine/tests/test_snapshot.py` (59 lines)

### Commit
```
666ded9 feat(engine): snapshot importer with stability and manifest checks
```

---

## Task 6: Exact Weld, Per-Axis Quantum, Edge Table, T-Vertices

### What Was Implemented
Created three new files:
- `engine/topo/weld.py`: Welding and quantization functions
- `engine/topo/adjacency.py`: Edge table and adjacency queries
- `engine/tests/test_topo_basics.py`: Full test suite with 5 tests

### Key Features Implemented
1. **weld_exact()**: Merges duplicate vertices based on printed decimals, handles -0.0 → 0.0 folding
2. **axis_quanta()**: Computes per-axis quantum (grid step) from coordinate magnitude
3. **EdgeTable** dataclass: Stores edge list, edge counts, and face→edge index mapping
4. **degenerate_mask()**: Identifies degenerate triangles using area/longest-edge ratio
5. **build_edge_table()**: Constructs edge topology from welded face indices
6. **edge_face_lists()**: Groups face indices by edge for topology queries
7. **find_t_vertices()**: Identifies T-junction vertices on open edges via projection

### TDD Evidence

**RED (Failing Test):**
```bash
$ .venv/Scripts/python.exe -m pytest engine/tests/test_topo_basics.py -q
ModuleNotFoundError: No module named 'engine.topo.adjacency'
```

**GREEN (Passing Tests):**
```bash
$ .venv/Scripts/python.exe -m pytest engine/tests/test_topo_basics.py -q
.....                                                                    [100%]
5 passed in 0.17s
```

### Test Coverage
All five tests validate critical topology operations:
- Weld merges printed duplicates and -0.0
- Axis quanta follow coordinate magnitude
- Cube (closed mesh) produces exactly 18 edges with count=2 everywhere
- Grid slab (open mesh) produces 320 edges with 40 open edges
- T-junction detection finds exactly one T-vertex with correct position and edge

### Files Changed
- Created: `engine/topo/weld.py` (15 lines)
- Created: `engine/topo/adjacency.py` (45 lines)
- Created: `engine/tests/test_topo_basics.py` (54 lines)

### Commit
```
b30c6b9 feat(engine): exact weld, per-axis quantum, edge table, T-vertices
```

---

## Full Test Suite Results

After both tasks completed:
```bash
$ .venv/Scripts/python.exe -m pytest -q
....................                                                     [100%]
20 passed in 0.42s
```

**Breakdown:**
- 10 existing tests (from prior tasks): ✓ All passing
- 5 new snapshot tests: ✓ All passing
- 5 new topology tests: ✓ All passing

### Self-Review Findings
- **Completeness**: All interfaces from briefs implemented exactly as specified
- **Quality**: Code follows existing patterns in codebase (dataclasses, type hints, numpy operations)
- **Discipline**: No over-building; each module has single, clear responsibility
- **Testing**: TDD followed; tests verify behavior not implementation; test output pristine
- **Stability**: Real-data check validates against live folder without modification

### Concerns
None. Implementation matches briefs exactly, all tests pass, real-data validation succeeds.

---

## Commit Metadata
Both commits include the trailer:
```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

As specified in task constraints.

---

## Task 5 fix round 1

### Open finding being fixed
Review flagged (Important): `snapshot.py` called `parse_mtl(mtl_src)` directly on the
live source `.mtl` path — the actual file read happened inside `engine.io.mtl`, a
different module, breaking the rule "only `engine/io/snapshot.py` reads [the source
folder], and only via stability check + copy + sha256." `read_manifest` did a raw
`read_text` with no stability check at all, and Step 4 invoked it directly against the
live `_MANIFEST.txt`. Textures were also copied from the live folder with no
post-copy verification.

### Controller's ruling implemented
1. Added a single private choke point, `_copy_verified(src, dst, interval_s, sleep) ->
   tuple[int, int]`: `wait_stable(src)` → `shutil.copyfile(src, dst)` → re-stat `src`,
   raise `SourceUnstable` if missing or changed → return the key. It is now the *only*
   code path that opens a file under the source folder — used for the OBJ, the MTL,
   and every texture.
2. The MTL is copied into the snapshot dir as `source.mtl` via `_copy_verified`, and
   `parse_mtl` now runs only on that copy. `source.mtl` is kept in the final snapshot
   dir for provenance. `materials.mtl` (the used-materials subset) is still written by
   `write_mtl_subset` exactly as before.
3. A texture that does not exist (per a plain `.exists()` check) still lands in
   `missing_textures` — not an error. A texture that exists but changes size/mtime
   during `_copy_verified`'s copy raises `SourceUnstable`.
4. Added `read_manifest_stable(path, interval_s=1.0, sleep=time.sleep) ->
   dict[str, ManifestRow]`: stat key → sleep → read the bytes once → stat again →
   raise `SourceUnstable` if missing/changed/empty → parse those bytes. Refactored so
   both `read_manifest(path)` (unchanged pure-parser signature, still a plain
   `read_text` for snapshot-copy callers) and `read_manifest_stable` share one private
   `_parse_manifest(text)`.
5. Public signatures of `wait_stable`, `snapshot_object`, `SnapshotResult`,
   `read_manifest`, and both exceptions are unchanged. Added
   `source_mtl_path: Path | None = None` to `SnapshotResult` as a new field with a
   default, so existing construction call sites keep working.

### TDD evidence

**RED** — added the new tests (including the `read_manifest_stable` import) before
touching the implementation:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_snapshot.py -q
ImportError: cannot import name 'read_manifest_stable' from 'engine.io.snapshot'
1 error in 0.44s
```
This failure was expected: `read_manifest_stable` did not exist yet.

**GREEN** — after implementing `_copy_verified`, the `source.mtl` copy step, and
`read_manifest_stable`:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_snapshot.py -v
test_manifest_parses_thousands_commas PASSED
test_snapshot_copies_hashes_and_subsets PASSED
test_source_changing_during_read_is_rejected PASSED
test_missing_source_is_rejected PASSED
test_manifest_mismatch PASSED
test_mtl_changing_during_copy_raises_source_unstable PASSED
test_texture_changing_during_copy_raises_source_unstable PASSED
test_source_mtl_kept_and_materials_subset_correct PASSED
test_read_manifest_stable_matches_read_manifest_when_unchanged PASSED
test_read_manifest_stable_rejects_change_during_read PASSED
test_failed_snapshot_leaves_no_incoming_dir PASSED
11 passed in 0.39s
```
All 5 pre-existing tests pass unmodified (the earlier `mkdir(parents=True)` fix was
already in place and kept); 6 new tests added, all green.

### New tests added (in `engine/tests/test_snapshot.py`)
- `test_mtl_changing_during_copy_raises_source_unstable`: injectable `sleep` counts
  calls (1st verifies the OBJ, 2nd verifies the MTL) and mutates `lib.mtl` only on the
  2nd call; asserts `SourceUnstable` and no leftover `.incoming-*` dir.
- `test_texture_changing_during_copy_raises_source_unstable`: same pattern, mutates
  `stone.png` on the 3rd `sleep` call (OBJ, MTL, then the one used texture); asserts
  `SourceUnstable` and no leftover `.incoming-*` dir.
- `test_source_mtl_kept_and_materials_subset_correct`: after a successful snapshot,
  `source.mtl` exists and is byte-identical to the source `.mtl`, and `materials.mtl`
  still contains `stone` but not the unused `other` material.
- `test_read_manifest_stable_matches_read_manifest_when_unchanged`: same rows as
  `read_manifest` when the file does not change.
- `test_read_manifest_stable_rejects_change_during_read`: mutates the manifest inside
  the `sleep` callback, asserts `SourceUnstable`.
- `test_failed_snapshot_leaves_no_incoming_dir`: `ManifestMismatch` path also leaves no
  `.incoming-*` directory in `dst_root`.

### Real-data check (re-run with `read_manifest_stable`)
Script written to
`C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-MODEL-FIXER\5472478e-978d-426b-bab2-e7cf21699a70\scratchpad\task5_fixcheck.py`,
run against the live, read-only source folder
`D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17\split`, writing
to a fresh `data/snapshots_fixcheck/` (not `data/snapshots/`, to avoid the dedup
short-circuit from the pre-existing `ce26e0392ab0` snapshot) with retry-on-`SourceUnstable`
(3 attempts, 20 s apart):

```
$ .venv/Scripts/python.exe task5_fixcheck.py
ce26e0392ab0907c5c65ab429abeb9ba4911d6252b69134e27c933941bac16fa 4692 {'mumi_littletiles_ltstone_-7': 3.0438862544900456} [] source.mtl exists: True
```

Succeeded on the first attempt (no `SourceUnstable`). Matches expectations: sha256
starts `ce26e039`, 4692 faces, flatness ≈ 3.04, missing textures `[]`, and `source.mtl`
present in the snapshot directory (`data/snapshots_fixcheck/ce26e0392ab0/source.mtl`),
verified via `find` before cleanup. `data/snapshots_fixcheck/` was deleted afterward
(git-ignored, inside `data/`); `data/snapshots/ce26e0392ab0` from the earlier run was
left untouched.

### Full suite
```
$ .venv/Scripts/python.exe -m pytest -q
..........................                                               [100%]
26 passed in 0.49s
```
(20 pre-existing + 6 new snapshot tests.)

### Files changed
- `engine/io/snapshot.py`: added `_copy_verified`, `read_manifest_stable`, private
  `_parse_manifest`; `_copy_assets` now copies the MTL to `source.mtl` via
  `_copy_verified` and parses that copy instead of the live path; textures are copied
  via `_copy_verified`; `SnapshotResult` gained `source_mtl_path`.
- `engine/tests/test_snapshot.py`: added the 6 tests above and the
  `read_manifest_stable` import.

### Self-review
- No other code path opens a file under the source tree — grepped for `Path(` /
  `open(` / `read_text` / `read_bytes` reachable from source-derived paths;
  `parse_mtl`/`read_obj` calls in `_load` all operate on `final`, the snapshot
  destination, never on `src_obj`/`mtl_src`.
- `read_manifest` (non-stable) keeps its original pure-parser signature and behavior
  for snapshot-copy callers, per the ruling.
- Did not touch `spike/`, `preview/`, or `docs/`.
- No subagents dispatched.

### Concerns
None. All required behaviors implemented and verified with real output.

### Commit
```
7d73e84 fix(engine): snapshot reads the live source only through verified copies
```
