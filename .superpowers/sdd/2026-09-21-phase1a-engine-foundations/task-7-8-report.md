# Task 7 & 8 Implementation Report

Branch: `phase1a-engine`. Baseline before starting: 26 tests passing.

## Task 7: planar regions, edge classes, `analyse_topology`

### What I did

1. Read `spike/_region.py` in full to get the exact logic for `plane_basis`,
   `cluster_planes`, `fit_uv`, `cluster_uv`. Confirmed `axis_quanta` and `pieces`
   in that file are excluded from the port (per instructions), and that the
   spike's `shapely` import is not needed by the ported functions.
2. Wrote `engine/tests/test_regions.py` verbatim from the brief's Step 1 code
   block.
3. Ran it — RED, as expected.
4. Created `engine/topo/planes.py`:
   - `plane_basis(n)` — ported unchanged.
   - `cluster_planes(tri, normals, area, material, ok, quanta, facing_dot=0.9, tol_quanta=1.5)`
     — ported unchanged except module constants `FACING_DOT`/`DIST_TOL_QUANTA`
     became keyword args `facing_dot`/`tol_quanta` with the same default values
     (0.9, 1.5), and the parameter `mat` was renamed `material` to match the
     brief's literal "Produces" interface line.
   - `fit_uv(xy, uv)` — ported unchanged.
   - `cluster_uv(xy, uv, area, uv_tol=0.02, max_refit=6)` — ported unchanged
     except `UV_TOL`/`MAX_REFIT` became keyword args with the same default
     values, and per the brief's only-permitted-change, it now returns
     `fits` as `list[(J, o)]` (dropped the third `resid` element and the
     `resid = np.abs(...)` line that computed it, since nothing in the new
     interface consumes it).
   - `build_regions(...)` — added verbatim from the brief's Step 2 code block
     (including its function-local `from engine.topo.adjacency import
     edge_face_lists` import, kept as given).
5. Created `engine/topo/edges.py` with `EDGE_REAL=0, EDGE_REMOVABLE=1,
   EDGE_OPEN=2, EDGE_NONMANIFOLD=3, EDGE_TJUNCTION=4` and `classify_edges`,
   verbatim from the brief's Step 3 code block.
6. Created `engine/pipeline.py` with `Topology` and `analyse_topology` /
   `topology_stats`, verbatim from the brief's Step 4 code block.
7. Ran `engine/tests/test_regions.py` — GREEN on the first attempt, no
   debugging needed; the ported logic matched the brief's expected counts
   exactly (6 regions on the cube, 6 removable diagonals, 12 real edges;
   1 region / 280 removable / 40 open on the 10x10 grid slab; UV-shift and
   material-change/seam-split behaviour all as specified; T-junction fixture
   gives 1 region, `face_region[6] == -1`, 0 T-junction edges after full
   resolution, 7 removable edges).
8. Ran the full suite: 32 passed (26 + 6).
9. Real-data check (Step 6), script at
   `C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-MODEL-FIXER\5472478e-978d-426b-bab2-e7cf21699a70\scratchpad\task7_real_data_check.py`:
   loads `data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj` with
   `read_obj`, computes `texture_flatness` for each material's `map_Kd` texture
   found via `parse_mtl` on `data/snapshots/ce26e0392ab0/materials.mtl`, builds
   `flat_materials` from indices with flatness < 8.0, then times and runs
   `analyse_topology` and prints `topology_stats`.

### Real-data check — command and REAL output

```
$ .venv/Scripts/python.exe "C:/Users/Future26/AppData/Local/Temp/claude/D--PROJECTS-UC-MODEL-FIXER/5472478e-978d-426b-bab2-e7cf21699a70/scratchpad/task7_real_data_check.py"
material 0 'mumi_littletiles_ltstone_-7': texture=tex/mumi_littletiles_ltstone_-7.png flatness=3.044
flat_materials: {0}
topology_stats: {'faces': 4692, 'zero_area_faces': 217, 'welded_vertices': 1589, 'axis_quanta': [0.01, 0.1, 0.01], 'regions': 986, 'edges': 6001, 'real_edges': 1097, 'removable_edges': 2524, 'open_edges': 326, 'nonmanifold_edges': 1738, 't_junction_edges': 316, 'edges_with_t_vertices': 164}
elapsed seconds: 0.2666
```

All anchors from the brief matched exactly:
- `faces` 4692 — match
- `zero_area_faces` 217 — match
- `welded_vertices` 1589 — match
- `axis_quanta` `[0.01, 0.1, 0.01]` — match
- `nonmanifold_edges` 1738, above 1000 — match

Runtime: 0.2666 s.

### Files changed (Task 7)

- `engine/topo/planes.py` (new)
- `engine/topo/edges.py` (new)
- `engine/pipeline.py` (new)
- `engine/tests/test_regions.py` (new)

Commit: `70887ce` — `feat(engine): planar regions, edge classes, analyse_topology`
(topology_stats dict and real-data numbers pasted into the commit body).

### Self-review (Task 7)

- Completeness: all four ported functions, `build_regions`, `edges.py`,
  `pipeline.py` present with the exact interfaces the brief specifies. All 6
  brief tests plus the real-data check pass.
- Quality: no logic was altered beyond the explicitly permitted changes
  (constants → kwargs, `cluster_uv` return shape). Verified by diffing the
  ported code mentally against `spike/_region.py` line by line — the only
  behavioral difference is that `resid` is no longer computed inside
  `cluster_uv`; since it was unused by any of the new callers this is a pure
  deletion, not a behavior change to the clustering itself.
- Discipline: did not import from `spike/` anywhere; did not touch
  `spike/`, `preview/`, `docs/`, or `data/` (only read `data/snapshots/...`
  for the real-data check, via the scratch script, per instructions).
  `git grep -n "fastapi\|sqlalchemy" engine` returns nothing (checked after
  Task 8, covers Task 7 files too).
- Testing: `engine/tests/test_regions.py` written verbatim before any
  implementation code existed; RED confirmed (`ModuleNotFoundError:
  engine.pipeline`) before GREEN. No flaky or skipped tests. Test output is
  pristine (no warnings).

### Concerns (Task 7)

- None regarding correctness — every test in the brief passed on the first
  implementation attempt with no expected-value adjustments needed, so the
  "investigate and prove by hand" branch of the TDD instructions was never
  triggered.
- Minor observation, not a defect: `build_regions`'s local
  `from engine.topo.adjacency import edge_face_lists` import (inside the
  function body rather than at module top) is unusual style but was kept
  verbatim as given in the brief's Step 2 code block, per the "exact values
  to use VERBATIM" instruction.

## Task 8: meshbuf transport

### What I did

1. Wrote `engine/tests/test_meshbuf.py` verbatim from the brief's Step 1 code
   block.
2. Ran it — RED, as expected (`ModuleNotFoundError: No module named
   'engine.transport.meshbuf'`).
3. Created `engine/transport/meshbuf.py` with `pack_meshbuf` / `unpack_meshbuf`,
   verbatim from the brief's Step 2 code block.
4. Ran the test — GREEN on the first attempt: round trip, block 4-byte
   alignment, bbox recentring (`origin_offset == [5.0, 5.0, 5.0]` for a
   size-10 cube), material passthrough, `tri_face_id` identity mapping, and
   per-vertex normal unit length all verified.
5. Ran the full suite: 33 passed (26 pre-existing + 6 Task 7 + 1 Task 8).
6. Verified `git grep -n "fastapi\|sqlalchemy" -- engine` and
   `git grep -n "from spike\|import spike" -- engine` both return nothing
   (exit code 1, no matches).

### Test run — command and REAL output

```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_meshbuf.py -q
.                                                                        [100%]
1 passed in 0.20s

$ .venv/Scripts/python.exe -m pytest -q
.................................                                        [100%]
33 passed in 0.65s
```

### Files changed (Task 8)

- `engine/transport/meshbuf.py` (new)
- `engine/tests/test_meshbuf.py` (new)

Commit: `2c5c105` — `feat(engine): meshbuf transport for the canvas`

### Self-review (Task 8)

- Completeness: layout matches the brief exactly — `UCMB` magic, `u32`
  version, `u32` header length, space-padded UTF-8 JSON header, then
  null-padded 4-byte-aligned blocks in the specified order and dtypes.
  Block offsets are relative to the first byte after the padded header, as
  required, and the test explicitly checks `offset % 4 == 0` for every block.
- Quality: code is a direct, unmodified transcription of the brief's Step 2
  block; no additional abstractions or scope added.
- Discipline: nothing beyond the two specified files was created; no changes
  to `spike/`, `preview/`, `docs/`, `data/`.
- Testing: RED confirmed before GREEN, per TDD. Test output pristine (no
  warnings, no skips).

### Concerns (Task 8)

- None. Implementation and test are a literal port of the brief text and the
  test passed unmodified.

## Discrepancy noted (not a defect, flagged per instructions)

`task-8-brief.md` Step 3 says "Then the whole suite: ... Expected: `27
passed`." The actual, measured full-suite count after both tasks is **33
passed** (26 pre-existing + 6 from Task 7 + 1 from Task 8), which matches the
controller's own stated expectation ("The suite total after both tasks should
be 33 passed (26 now + 6 regions + 1 meshbuf)"). The brief's "27 passed" text
is stale — it doesn't match either the pre-existing 26-test baseline that
was confirmed present before this work started, or the 6+1 tests this work
adds. No test values were altered to make numbers agree; this is purely a
stale prose count in the brief document, not a test assertion, so nothing
in `test_regions.py` or `test_meshbuf.py` needed correction. Verified by
literal count: `.venv/Scripts/python.exe -m pytest -q` → `33 passed in
0.65s`.

## Phase 1A "done when" checklist

- `.venv/Scripts/python.exe -m pytest -q` → `33 passed in 0.65s` (pasted
  above, and again as the final full-suite run below).
- Real-data checks for Task 5 (already done in an earlier session, per the
  existing `task5_real_data_check.py` scratch script) and Task 7 (this
  session, numbers above) were both run and their printed numbers recorded.
- `git grep -n "fastapi\|sqlalchemy" engine` → no output (clean).

### Final full-suite run (post both commits)

```
$ .venv/Scripts/python.exe -m pytest -q
.................................                                        [100%]
33 passed in 0.65s
```

Working tree is clean (`git status --short` → no output) after both commits.

## Task 7 fix round 1

### Finding being fixed

Open (Important): T-junction chain→sub-edge resolution (build `lookup` dict of
edge-by-vertex-pair, build `chain`, walk `zip(chain, chain[1:])` via `lookup`)
was duplicated near-verbatim between `engine/topo/planes.py` (`build_regions`)
and `engine/topo/edges.py` (`classify_edges`).

Plus a Minor in the same lines: `build_regions`'s function-local
`from engine.topo.adjacency import edge_face_lists` — no circular import
exists, so it belongs at module top.

### What I did

1. **Regression proof, before touching any code.** Wrote
   `C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-MODEL-FIXER\5472478e-978d-426b-bab2-e7cf21699a70\scratchpad\regression_check.py`,
   which loads `data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj` via
   `read_obj`, runs `analyse_topology(mesh, flat_materials=frozenset({0}))`,
   and prints `sha256(face_region.tobytes() + edge_class.tobytes())` and
   `np.bincount(edge_class, minlength=5)`. Ran it — real output:
   ```
   sha256: 427dfacc136004c2082d63d38a4f519cc7404dae93ce1e3350c6ec88f231e458
   bincount: [1097, 2524, 326, 1738, 316]
   ```
   Bincount matched the controller's required
   `[1097, 2524, 326, 1738, 316]` exactly before any change was made.
2. **TDD.** Added two new tests to `engine/tests/test_topo_basics.py` for the
   not-yet-existing `t_junction_sub_edges(table, t_vertices)` helper, using
   the `t_junction_strip()` fixture:
   - `test_t_junction_sub_edges_walks_chain_to_real_sub_edge_indices`: exactly
     one entry, both sub-edges not `None`, and (read through `table.edges`
     and the welded positions `P`) the sub-edge endpoints are the pairs
     x∈{0,10} then x∈{10,20} at y=10, in chain order starting from
     `edges[e][0]`.
   - `test_t_junction_sub_edges_yields_none_for_missing_sub_edge`: hand-built
     `t_vertices = {e: [far_vertex]}` where `far_vertex` is the welded vertex
     at (0,20,0). I first ran the real fixtures through
     `weld_exact`/`build_edge_table`/`find_t_vertices` at the terminal to
     confirm the concrete vertex ids and `table.edges` rows before writing
     the assertion (`a=1 (0,10,0)`, `b=6 (20,10,0)`, real edges include
     `(1,2)` but not `(2,6)`), so the test asserts against measured values,
     not assumption. (0,20,0) is connected to `edges[e][0]`==(0,10,0) by a
     real diagonal edge, so the first leg resolves, but nothing connects it
     to `edges[e][1]`==(20,10,0), so the second leg must be `None` — this is
     explained in a comment above the test.
   - RAN before implementing: `ImportError: cannot import name
     't_junction_sub_edges' from 'engine.topo.adjacency'` — RED confirmed
     (collection error, as expected since the helper didn't exist yet).
3. **Implemented** `t_junction_sub_edges(table: EdgeTable, t_vertices: dict[int,
   np.ndarray]) -> dict[int, list[int | None]]` in `engine/topo/adjacency.py`.
   Builds the vertex-pair `lookup` once per call, then for each `e, verts` in
   `t_vertices` walks `chain = [edges[e][0], *verts, edges[e][1]]` and returns
   `lookup.get((min(p,q), max(p,q)))` for each consecutive pair — identical
   logic to what was previously duplicated in the two call sites.
4. Ran the two new tests — GREEN:
   ```
   $ .venv/Scripts/python.exe -m pytest engine/tests/test_topo_basics.py -q
   .......                                                                  [100%]
   7 passed in 0.14s
   ```
5. **Updated call sites** to remove the duplicated logic:
   - `engine/topo/planes.py`: moved `from engine.topo.adjacency import
     edge_face_lists` to the module-top import (now `from engine.topo.adjacency
     import edge_face_lists, t_junction_sub_edges`), and replaced
     `build_regions`'s local `lookup`/chain-walk loop with
     `sub_edges = t_junction_sub_edges(table, t_vertices)` followed by a loop
     over `sub_edges.items()` that appends `ef[s]` for each non-`None` sub-edge
     — same face set assembled, same `join()` calls, same order.
   - `engine/topo/edges.py`: added `t_junction_sub_edges` to the existing
     top-level import, and replaced `classify_edges`'s local `lookup`/chain
     construction with `sub_edges = t_junction_sub_edges(table, t_vertices)`,
     iterating `sub_edges.items()` in place of the old `t_vertices.items()` +
     inline `subs` computation. The rest of the loop body (`whole`, `kind`,
     `cls[e]`, sub-edge class propagation) is untouched.
6. Confirmed no circular import: `.venv/Scripts/python.exe -c "import
   engine.pipeline; import engine.topo.planes; import engine.topo.edges;
   import engine.topo.adjacency; print('imports OK')"` → `imports OK`.
7. Ran `engine/tests/test_regions.py` + `engine/tests/test_topo_basics.py`
   together — GREEN:
   ```
   $ .venv/Scripts/python.exe -m pytest engine/tests/test_regions.py engine/tests/test_topo_basics.py -q
   .............                                                            [100%]
   13 passed in 0.21s
   ```
8. **Regression proof, after the refactor.** Re-ran the same
   `regression_check.py` script unmodified:
   ```
   sha256: 427dfacc136004c2082d63d38a4f519cc7404dae93ce1e3350c6ec88f231e458
   bincount: [1097, 2524, 326, 1738, 316]
   ```
   Identical to the before-refactor run — byte-for-byte identical behaviour
   confirmed on real data.
9. Ran the whole suite:
   ```
   $ .venv/Scripts/python.exe -m pytest -q
   ...................................                                      [100%]
   35 passed in 0.60s
   ```
   35 = 33 pre-existing + 2 new tests added in this round, all passing
   unmodified.
10. Reviewed the diff before committing: `git diff --stat` touched exactly
    `engine/tests/test_topo_basics.py`, `engine/topo/adjacency.py`,
    `engine/topo/edges.py`, `engine/topo/planes.py` — no changes to `spike/`,
    `preview/`, `docs/`, or `data/`, and no other refactors made.
11. Committed as `0dc2d1f` —
    `refactor(engine): single T-junction chain helper shared by regions and edge classes`.

### TDD Evidence

- RED: `.venv/Scripts/python.exe -m pytest engine/tests/test_topo_basics.py -q`
  → `ImportError: cannot import name 't_junction_sub_edges' from
  'engine.topo.adjacency'` (collection error) — expected, since the helper
  did not exist yet.
- GREEN: same command → `7 passed in 0.14s`.

### Files changed

- `engine/topo/adjacency.py` — added `t_junction_sub_edges`.
- `engine/topo/planes.py` — `build_regions` now calls the helper; import
  moved to module top.
- `engine/topo/edges.py` — `classify_edges` now calls the helper.
- `engine/tests/test_topo_basics.py` — two new tests for the helper.

### Self-review

- Completeness: both the Important duplication finding and the Minor
  function-local-import finding are fixed. Both call sites now share one
  helper; no copy of the lookup/chain logic remains in `planes.py` or
  `edges.py` (verified by reading both files in full after editing).
- Quality: `t_junction_sub_edges`'s docstring states the exact contract from
  the controller's ruling. Naming matches the ruling exactly
  (`t_junction_sub_edges(table, t_vertices) -> dict[int, list[int | None]]`).
- Discipline: no other refactors made; did not touch `spike/`, `preview/`,
  `docs/`, `data/` (only read the snapshot `.obj` via the regression script).
  Did not modify `engine/pipeline.py`, `engine/model.py`, or any other file.
- Testing: RED confirmed before implementing, GREEN after. Full suite run
  once before committing (35 passed, output pristine — no warnings, no
  skips). Real-data hash and bincount identical before/after.

### Concerns

None. The refactor is behavior-preserving by construction (same lookup
dict, same chain construction, same `.get` semantics) and this is confirmed
both by the unit tests and by the byte-for-byte identical hash/bincount on
real data before and after.
