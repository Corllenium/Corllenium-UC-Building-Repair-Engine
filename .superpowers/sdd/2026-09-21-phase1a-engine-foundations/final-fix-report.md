# Final-review fix wave — report

Repo `D:\PROJECTS\UC MODEL FIXER`, branch `phase1a-engine`. Baseline before any change:
`git log --oneline 0dc2d1f..HEAD` was empty (no items from an earlier run were committed) and
`.venv/Scripts/python.exe -m pytest -q` reported **35 passed**.

Baseline real-model script (`analyse_topology` on
`data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj`, `flat_materials=frozenset({0})`):

```
read_obj: 0.019 s
analyse_topology: 0.135 s
topology_stats: 0.0002 s
total: 0.155 s
stats: {'faces': 4692, 'zero_area_faces': 217, 'welded_vertices': 1589, 'axis_quanta': [0.01, 0.1, 0.01],
        'regions': 986, 'edges': 6001, 'real_edges': 1097, 'removable_edges': 2524, 'open_edges': 326,
        'nonmanifold_edges': 1738, 't_junction_edges': 316, 'edges_with_t_vertices': 164}
```

Matches the brief's known baseline exactly.

---

## F1 `fix(engine): meshbuf header accepts Path texture values`

**Test added** (`engine/tests/test_meshbuf.py`): `test_header_serializes_path_texture_value`,
`test_header_serializes_backslash_string_texture_value`, `test_header_keeps_missing_texture_as_null`.

**RED** — `.venv/Scripts/python.exe -m pytest engine/tests/test_meshbuf.py -q`:
```
TypeError: Object of type WindowsPath is not JSON serializable
...
AssertionError: assert [{'name': 'm0', 'texture': 'tex\\stone.png'}] == [{'name': 'm0', 'texture': 'tex/stone.png'}]
2 failed, 2 passed in 0.20s
```
(the pre-existing round-trip test and the new null-texture test already passed; the Path and
backslash-string cases failed as expected.)

**Implementation**: `engine/transport/meshbuf.py` — added `_texture_value(v)` helper
(`None` -> `None`, else `Path(v).as_posix()`), used it in the header's `materials` list instead of
the raw `textures.get(n)`.

**GREEN** — `.venv/Scripts/python.exe -m pytest engine/tests/test_meshbuf.py -q`:
```
....
4 passed in 0.09s
```

**Full suite after item**: `.venv/Scripts/python.exe -m pytest -q` -> `38 passed in 0.35s`.

**Files changed**: `engine/transport/meshbuf.py`, `engine/tests/test_meshbuf.py`.

**Commit**: `44661dc fix(engine): meshbuf header accepts Path texture values`

**Concerns**: none.

---

## F2 `fix(engine): flat-material adapter from flatness-by-name to indices`

**Test added** (new file `engine/tests/test_pipeline.py`):
`test_flat_material_indices_maps_names_to_indices`,
`test_untextured_material_with_no_flatness_entry_is_flat`,
`test_patterned_material_above_threshold_is_not_flat`,
`test_analyse_topology_raises_type_error_on_material_name_in_flat_materials`.

**RED** — `.venv/Scripts/python.exe -m pytest engine/tests/test_pipeline.py -q`:
```
ImportError: cannot import name 'FLAT_TEXTURE_STD' from 'engine.pipeline'
1 error in 0.19s
```

**Implementation**: `engine/pipeline.py` — added `FLAT_TEXTURE_STD = 8.0` and
`flat_material_indices(mesh, flatness, threshold=FLAT_TEXTURE_STD) -> frozenset[int]`
(a material absent from `flatness` counts as flat regardless of threshold). Added a guard at
the top of `analyse_topology` that raises `TypeError` naming the bad element and its type if
any member of `flat_materials` is not an `int`/`np.integer` (bools excluded), pointing callers
at `flat_material_indices()`.

**GREEN** — `.venv/Scripts/python.exe -m pytest engine/tests/test_pipeline.py -q`:
```
....
4 passed in 0.08s
```

**Full suite after item**: `.venv/Scripts/python.exe -m pytest -q` -> `42 passed in 0.38s`.

**Files changed**: `engine/pipeline.py`, `engine/tests/test_pipeline.py`.

**Commit**: `b655d20 fix(engine): flat-material adapter from flatness-by-name to indices`

**Concerns**: none.

---

## F3+F4 `fix(engine): T-junctions from zero-area hints and on every edge`

**Test added**:
- `engine/tests/fixtures/build.py`: new fixture `t_junction_shared_strip(drop_zero_area=False)`.
- `engine/tests/test_topo_basics.py`:
  `test_shared_edge_t_vertex_found_via_hint_when_zero_area_face_present`,
  `test_shared_edge_t_vertex_found_via_geometry_alone_when_zero_area_face_absent`,
  `test_degenerate_face_with_repeated_vertex_id_yields_no_hint_and_no_crash`.
- `engine/tests/test_regions.py`: `test_shared_tjunction_edge_keeps_its_count_class_when_chain_regions_differ`
  (added beyond the brief's explicit list — see Concerns).

**RED 1** (find_t_vertices widening) — `.venv/Scripts/python.exe -m pytest engine/tests/test_topo_basics.py -q`:
```
TypeError: find_t_vertices() got an unexpected keyword argument 'face_w'
assert (7 in {})
TypeError: find_t_vertices() got an unexpected keyword argument 'face_w'
3 failed, 7 passed in 0.21s
```

**Implementation 1**: `engine/topo/adjacency.py` — `find_t_vertices` gained `face_w=None,
degenerate=None`; the geometric loop now runs over every edge index (not just `counts == 1`),
candidates are `np.unique(table.edges)` (every welded vertex referenced by an included face,
not just open-edge endpoints). Added `_t_vertex_hints()`: for each degenerate face with three
distinct vertex ids, tries each vertex as the "middle" one, keeps the one whose parameter lies
strictly between the other two along their line (within `tol`), and looks up the edge the other
two form; a repeated vertex id is skipped (no hint, no crash). Hints are merged into the
geometric hits, deduplicated via a set, then reordered by parameter from `edges[e][0]` to
`edges[e][1]`. `engine/pipeline.py`'s `analyse_topology` now calls
`find_t_vertices(..., face_w=face_w, degenerate=~ok)`.

**GREEN 1** — `.venv/Scripts/python.exe -m pytest engine/tests/test_topo_basics.py -q`: `10 passed in 0.10s`.

Full suite at this point: `45 passed` (no regression from the widened search alone).

**RED 2** (classify_edges count-rule precedence) — `.venv/Scripts/python.exe -m pytest engine/tests/test_regions.py -q`:
```
assert t.edge_class[e] == EDGE_REAL
E       assert np.uint8(4) == 0   # got EDGE_TJUNCTION (4), wanted EDGE_REAL (0)
1 failed, 6 passed in 0.22s
```
This confirms the latent bug the spec calls out: once `find_t_vertices` can return a hit for a
`counts == 2` edge, the old `classify_edges` unconditionally set `cls[e] = EDGE_TJUNCTION` for any
non-"whole" chain, regardless of the edge's own count — wrongly overriding a real, already-connected
edge (the long top edge shared with an unrelated wall triangle) just because a T-vertex happened to
sit on it geometrically.

**Implementation 2**: `engine/topo/edges.py` `classify_edges` — in the non-"whole" branch, only
promote `e` (and its `counts == 1` sub-edges) to `EDGE_TJUNCTION` when `table.counts[e] == 1`;
an edge with `counts >= 2` is left untouched, keeping whatever the earlier count-based rules
assigned (`EDGE_REAL`/`EDGE_NONMANIFOLD`, or `EDGE_REMOVABLE` from the `counts == 2` same-region
check). The "whole" branch is unchanged from before.

**GREEN 2** — `.venv/Scripts/python.exe -m pytest engine/tests/test_regions.py -q`: `7 passed in 0.14s`.

**Full suite after item**: `.venv/Scripts/python.exe -m pytest -q` -> `46 passed in 0.36s`.

**Real-model script** (`analyse_topology` on `CHTM_SIDE_WALK_2nd_floor.obj`, `flat_materials=frozenset({0})`):

BEFORE:
```
read_obj: 0.017 s, analyse_topology: 0.135 s, total: 0.155 s
regions 986, real 1097, removable 2524, open 326, nonmanifold 1738,
t_junction 316, edges_with_t_vertices 164
```
AFTER:
```
read_obj: 0.017 s, analyse_topology: 0.417 s, total: 0.435 s
regions 888, real 1097, removable 2527, open 250, nonmanifold 1738,
t_junction 389, edges_with_t_vertices 406
```
Runtime stayed well under 5 s (0.417 s for `analyse_topology`, up from 0.135 s — about 3x, from
searching every edge instead of only the 326 open ones). `edges_with_t_vertices` jumped from 164
to 406: a great many real T-junctions on already-shared (`counts >= 2`) edges were being missed
entirely before this fix. Bookkeeping is internally consistent: `open` dropped by 76 (326->250),
matched exactly by `t_junction` rising 73 (316->389) and `removable` rising 3 (2524->2527);
`real` and `nonmanifold` are unchanged, as expected since neither is reachable by the new
reclassification path. `regions` fell 986->888 because chains that were previously left
disconnected (T-vertex not found) now correctly join across the T-junction.

**Files changed**: `engine/topo/adjacency.py`, `engine/topo/edges.py`, `engine/pipeline.py`,
`engine/tests/fixtures/build.py`, `engine/tests/test_topo_basics.py`, `engine/tests/test_regions.py`.

**Commit**: `44461e2 fix(engine): T-junctions from zero-area hints and on every edge`

**Concerns**:
- The brief's test list for this item only names find_t_vertices-level tests (a)/(b)/(c). Widening
  `find_t_vertices` alone left the full suite green (45/45) without yet fixing `classify_edges`,
  because no existing test exercised a T-vertex discovered on a `counts >= 2` edge — so TDD for the
  `classify_edges` half of the spec required a test I wrote myself
  (`test_shared_tjunction_edge_keeps_its_count_class_when_chain_regions_differ` in
  `test_regions.py`), which I confirmed RED against the pre-fix code before implementing. This is a
  new test, not a modification of an existing one, so it stays within "existing tests unmodified
  unless an item says otherwise."
- In the `t_junction_shared_strip()` fixture specifically, the shared long edge's T-vertex is in
  fact found by geometry alone even when the zero-area face is present (every other vertex on that
  T-vertex, e.g. vertex 4, is already referenced by several other non-degenerate faces in the base
  `t_junction_strip()` geometry, so it is already a geometric candidate). The "found via the hint"
  test therefore exercises the hint-merge/dedup path correctly but does not prove the hint is the
  *only* way this particular case is found; the "via geometry alone" test (fixture without the
  degenerate face, and `find_t_vertices` called without `face_w`/`degenerate` at all) is the one
  that isolates the widened-search fix in isolation. Test (c) (repeated vertex id) does isolate the
  hint code path directly. I judged this sufficient rather than constructing a more contrived
  fixture where the T-vertex is reachable only through the hint, since the brief's fixture is given
  verbatim.

---

## F6 `fix(engine): per-call incoming dir for concurrent snapshots`

**Test added** (`engine/tests/test_snapshot.py`):
`test_two_sequential_calls_succeed_and_stale_incoming_dir_survives_untouched`.

**RED** — `.venv/Scripts/python.exe -m pytest engine/tests/test_snapshot.py -q -k stale`:
```
AssertionError: assert (False)
 +  where False = exists()
 +    where exists = WindowsPath('...snap/.incoming-walk').exists
1 failed, 11 deselected in 0.23s
```
Confirms the old deterministic `.incoming-{stem}` name collided with (and `shutil.rmtree`'d) a
pre-existing directory of the same name, exactly the concurrency/crash-recovery hazard the item
describes.

**Implementation**: `engine/io/snapshot.py` — `snapshot_object` now gets its temp directory via
`tempfile.mkdtemp(prefix=".incoming-", dir=dst_root)` instead of the deterministic
`dst_root / f".incoming-{src_obj.stem}"`, so concurrent calls (or a stale leftover from a
crashed run) never collide on the same path or get swept by name. If `tmp.rename(final)` raises
`OSError` because another call already created `final` first, and `final` does in fact now
exist, we discard our own copy (cleaned up by the existing `finally: shutil.rmtree(tmp, ...)`)
and load the winner's result; any other `OSError` still propagates.

**GREEN** — `.venv/Scripts/python.exe -m pytest engine/tests/test_snapshot.py -q`: `12 passed in 0.25s`
(the pre-existing "no `.incoming-*` left behind" tests still pass unmodified).

**Full suite after item**: `.venv/Scripts/python.exe -m pytest -q` -> `47 passed in 0.40s`.

**Files changed**: `engine/io/snapshot.py`, `engine/tests/test_snapshot.py`.

**Commit**: `9c775f2 fix(engine): per-call incoming dir for concurrent snapshots`

**Concerns**: none.

---

## F7b `fix(engine): OS errors during verified copy mean the source is unstable`

**Test added** (`engine/tests/test_snapshot.py`):
`test_snapshot_wraps_permission_error_during_copy_as_source_unstable` (monkeypatches
`shutil.copyfile` to raise `PermissionError`, exercised through `snapshot_object`),
`test_read_manifest_stable_wraps_os_error_as_source_unstable` (monkeypatches
`Path.read_bytes` to raise `PermissionError`).

**RED** — `.venv/Scripts/python.exe -m pytest engine/tests/test_snapshot.py -q -k "permission_error or os_error"`:
```
PermissionError: locked by another process   (raw, from shutil.copyfile inside _copy_verified)
PermissionError: locked by another process   (raw, from path.read_bytes inside read_manifest_stable)
2 failed, 12 deselected in 0.22s
```

**Implementation**: `engine/io/snapshot.py` — `_copy_verified` wraps `shutil.copyfile(...)` and
the immediate re-stat in `try/except OSError`, raising `SourceUnstable(f"{src.name}: {exc}")
from exc`. `read_manifest_stable` does the same around `path.read_bytes()` and its re-stat,
replacing the narrower `except FileNotFoundError` with `except OSError`, so a
`PermissionError` from a Windows file lock is now caught the same way a vanished file already
was.

**GREEN** — `.venv/Scripts/python.exe -m pytest engine/tests/test_snapshot.py -q`: `14 passed in 0.27s`.

**Full suite after item**: `.venv/Scripts/python.exe -m pytest -q` -> `49 passed in 0.36s`.

**Files changed**: `engine/io/snapshot.py`, `engine/tests/test_snapshot.py`.

**Commit**: `d4266f5 fix(engine): OS errors during verified copy mean the source is unstable`

**Concerns**: none.

---

## F8 `fix(engine): refuse texture basename collisions instead of overwriting`

**Test added** (`engine/tests/test_snapshot.py`):
`test_texture_basename_collision_between_different_source_paths_is_refused` (two materials,
`a/stone.png` and `b/stone.png`).

**RED** — `.venv/Scripts/python.exe -m pytest engine/tests/test_snapshot.py -q -k collision`:
```
Failed: DID NOT RAISE ValueError
1 failed, 14 deselected in 0.28s
```

**Implementation**: `engine/io/snapshot.py` `_copy_assets` — after computing `wanted`, dedups
the rel-paths (`sorted(set(wanted.values()))`), then walks them once building a
`basename -> rel-path` map; a second distinct rel-path landing on a basename already claimed by
a different rel-path raises `ValueError` naming both source paths and the shared basename. This
check runs before `(tmp / "tex").mkdir()`, i.e. before anything is copied.

**GREEN** — `.venv/Scripts/python.exe -m pytest engine/tests/test_snapshot.py -q`: `15 passed in 0.26s`.

**Full suite after item**: `.venv/Scripts/python.exe -m pytest -q` -> `50 passed in 0.43s`.

**Files changed**: `engine/io/snapshot.py`, `engine/tests/test_snapshot.py`.

**Commit**: `a5b6a37 fix(engine): refuse texture basename collisions instead of overwriting`

**Concerns**: none.

---

## M1 `fix(engine): reject exponent-form coordinates`

**Test added** (`engine/tests/test_obj_reader.py`): `test_rejects_exponent_form_coordinates`
(`1e-05`), `test_rejects_uppercase_exponent_form_coordinates` (`2.5E+02`).

**RED** — `.venv/Scripts/python.exe -m pytest engine/tests/test_obj_reader.py -q -k exponent`:
```
Failed: DID NOT RAISE ObjFormatError
Failed: DID NOT RAISE ObjFormatError
2 failed, 3 deselected in 0.16s
```

**Implementation**: `engine/io/obj_reader.py` — in the `v` branch, before parsing floats,
raise `ObjFormatError` naming the line number and the offending token if any coordinate token
contains `e` or `E`.

**GREEN** — `.venv/Scripts/python.exe -m pytest engine/tests/test_obj_reader.py -q`: `5 passed in 0.11s`.

**Full suite after item**: `.venv/Scripts/python.exe -m pytest -q` -> `52 passed in 0.39s`.

**Files changed**: `engine/io/obj_reader.py`, `engine/tests/test_obj_reader.py`.

**Commit**: `623e99e fix(engine): reject exponent-form coordinates`

**Concerns**: none.

---

## T8 `test(engine): meshbuf sentinels for degenerate faces and missing material`

**Test added** (`engine/tests/test_meshbuf.py`):
`test_degenerate_face_and_missing_material_produce_correct_sentinels`, using `t_junction_strip()`
with face 0's `face_material` set to -1.

**Run** — `.venv/Scripts/python.exe -m pytest engine/tests/test_meshbuf.py -q -k sentinels`:
```
.
1 passed, 4 deselected in 0.09s
```
This item is `test(engine)`, not `fix(engine)`: it passed on its first run with no production
code changes. The existing `pack_meshbuf` already does the right thing for every assertion in
the brief — `np.where(ln > 0, cr/ln, [0,0,1])` gives the degenerate face a finite, exact unit
`(0,0,1)` normal; `np.where(face_material >= 0, face_material, 65535)` gives the sentinel for an
unassigned material; `build_regions` leaves `face_region` at its `-1` default for any face never
admitted to a plane group (which a degenerate face never is, since it fails the `ok` mask); and
`tri_face_id` is `np.arange(mesh.n_faces)` unconditionally. There was no RED phase to show
because there is no bug: TDD's "write a failing test first" only applies when the test expresses
an unmet requirement, and here it pins already-correct behaviour, which is exactly what a
`test(engine)`-prefixed item (as opposed to `fix(engine)`) calls for.

**Full suite after item**: `.venv/Scripts/python.exe -m pytest -q` -> `53 passed in 0.39s`.

**Files changed**: `engine/tests/test_meshbuf.py` (test only, no production code touched).

**Commit**: `1dcd360 test(engine): meshbuf sentinels for degenerate faces and missing material`

**Concerns**: none.

---

## Finish

Full suite: `.venv/Scripts/python.exe -m pytest -q` -> **53 passed in 0.39s**, output pristine (no
warnings). Baseline was 35; per-item full-suite totals recorded above progressed
38 (F1) -> 42 (F2) -> 46 (F3+F4) -> 47 (F6) -> 49 (F7b) -> 50 (F8) -> 52 (M1) -> 53 (T8), i.e. 18
new tests added across the wave. Final REAL count: **53 passed**.

Real-model script (`analyse_topology` + `topology_stats` on
`data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj`, `flat_materials=frozenset({0})`), run
once more after all items (actual output):

```
read_obj: 0.0175 s, analyse_topology: 0.4218 s, total: 0.4395 s
{'faces': 4692, 'zero_area_faces': 217, 'welded_vertices': 1589, 'axis_quanta': [0.01, 0.1, 0.01],
 'regions': 888, 'edges': 6001, 'real_edges': 1097, 'removable_edges': 2527, 'open_edges': 250,
 'nonmanifold_edges': 1738, 't_junction_edges': 389, 'edges_with_t_vertices': 406}
```
Identical to the F3+F4 AFTER measurement, confirmed by actually re-running the script (not just
inferred), since no item after F3+F4 touches `engine/pipeline.py`, `engine/topo/`, or
`engine/model.py` in a way that affects topology on this file. Runtime stays well under 5 s.

**All commits, in order**:
1. `44661dc fix(engine): meshbuf header accepts Path texture values`
2. `b655d20 fix(engine): flat-material adapter from flatness-by-name to indices`
3. `44461e2 fix(engine): T-junctions from zero-area hints and on every edge`
4. `9c775f2 fix(engine): per-call incoming dir for concurrent snapshots`
5. `d4266f5 fix(engine): OS errors during verified copy mean the source is unstable`
6. `a5b6a37 fix(engine): refuse texture basename collisions instead of overwriting`
7. `623e99e fix(engine): reject exponent-form coordinates`
8. `1dcd360 test(engine): meshbuf sentinels for degenerate faces and missing material`

**Concerns, collected**:
- F3+F4: the `classify_edges` half of the fix (count >= 2 edges keep their count-rule class)
  had no test in the brief's own list that could go RED against the pre-fix code, since no
  existing test exercised a T-vertex discovered on a shared edge. I wrote one
  (`test_shared_tjunction_edge_keeps_its_count_class_when_chain_regions_differ` in
  `test_regions.py`) and confirmed it RED before implementing, per the "investigate, fix, record
  as a concern" instruction.
- F3+F4: in the `t_junction_shared_strip()` fixture, the shared edge's T-vertex is in fact
  findable by geometry alone even with the zero-area face present (its middle vertex is already
  referenced by several other non-degenerate faces from the base `t_junction_strip()` geometry).
  The "found via the hint" test exercises the hint-merge/dedup path correctly but does not prove
  hint-exclusivity for that specific case; the "geometry alone" variant (fixture without the
  degenerate face, function called without `face_w`/`degenerate`) is the one that isolates the
  widened-search fix, and the repeated-vertex-id test isolates the hint code path directly. See
  the full report above (F3+F4 section) for detail.
- No other concerns. Unrelated concurrent changes appeared under `docs/spike/`,
  `docs/superpowers/plans/`, and `spike/` during this session (not made by this work); per the
  brief's "do not touch spike/, preview/, docs/, data/" rule they were left untouched and never
  staged in any commit above.
