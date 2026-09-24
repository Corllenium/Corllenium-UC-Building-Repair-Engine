# Task 7/8/9 report: fix CLI, outward orientation, polygon export

Appended after each task completes, in task order (A = task 8, B = task 9, C = task 7), so an
interruption loses nothing. Final `## Public signatures` section at the end.

---

## Task A (task-8-brief.md): outward orientation + one-sided completeness

### What I implemented

- `engine/vis/exposure.py`: added `compute_side_exposure(positions_c, face_w, ok,
  caster_factory=EmbreeCaster, n_dirs=128) -> (front, back)`, splitting the existing
  double-sided ray sampling loop into two accumulators (`escapes_front` for rays cast from
  `+EPS_IN * normal`, `escapes_back` for `-EPS_IN * normal`), each divided by the SAME full
  denominator `n_dirs * len(BARY)`. `compute_exposure` is now a one-line wrapper: `front + back`.
  Because the denominator is a power of two for every `n_dirs` used anywhere in this codebase
  (16/32/64/128), each division is exact in float64 and the sum is bit-identical to the old
  single-division formula — pinned by test.
- `engine/fixes/orient.py` (new): `ORIENT_OK=0`, `ORIENT_FLIP=1`, `ORIENT_THIN_SHEET=2`;
  `classify_orientation(front, back, ok, sheet_ratio=0.5)` — `FLIP` when `back > front`, else
  `THIN_SHEET` when both sides are exposed and `min/max >= sheet_ratio`, else `OK` (hidden and
  degenerate faces are always `OK`, priority is FLIP first); `flip_faces(mesh, flip)` — reverses
  `face_v`/`face_vt` order for flagged faces, drops their `face_vn` to `-1` (reordering a normal
  INDEX cannot fix a normal VECTOR that still points the old, now-wrong way), moves no vertex;
  `one_sided_holes(positions_c, faces, face_ids, views, size, caster_factory=EmbreeCaster) -> int`
  — renders each view double-sided (`ortho_first_hit` never culls backfaces) and counts hit
  pixels whose first-hit face's own geometric normal faces the same way as the view direction
  (back-facing to that camera).
- `engine/fixes/pipeline.py`: `fix_object` now computes `front, back = compute_side_exposure(...)`
  once (`exposure = front + back` feeds the existing hidden/slit classification, no extra ray
  casting), classifies orientation over the ORIGINAL mesh, and — AFTER hidden/slit removal, BEFORE
  merge — flips every surviving `ORIENT_FLIP` face (`flip_faces` on `mesh_removed`), then runs
  `analyse_topology` + `merge_regions` on the FLIPPED mesh instead of the bare removal result. The
  final-guard rollback path (merge not converged / guard failed) now falls back to the
  flipped-but-unmerged mesh, not the pre-flip one — flipping is unconditional, not gated behind
  merge succeeding. `FixResult` gains `flipped` (bool, over ORIGINAL faces), `thin_sheets` (bool,
  over ORIGINAL faces), `one_sided_holes_before` / `one_sided_holes_after` (int, measured on the
  original mesh's faces and on the actually-shipped final mesh's faces, over `VIEWS_26`).
- `engine/tests/fixtures/build.py`: fixed `gridded_box()` — 3 of its 6 faces (`z=0`, `y=s`, `x=0`)
  had inward-pointing winding by construction (`du`/`dv` chosen without regard to outward
  direction, since nothing checked winding before this task). Swapped `du`/`dv` for those three
  faces so `cross(du, dv)` points outward on all 6, matching the fixture's own docstring claim.
  This surfaced only because the new flip logic classified ~96 of its 192 triangles `FLIP` on the
  UNMODIFIED fixture, breaking the pre-existing `test_rolled_back_when_merge_does_not_converge`
  (which asserts the rolled-back mesh is byte-identical to the input) and my own new
  reversed-triangle test. No other fixture is affected (`cube()`/`box_with_partition()` were
  already correctly wound, confirmed by a dedicated test before touching anything).

### TDD evidence

RED (before implementing `compute_side_exposure`/`orient.py`): tests referencing
`compute_side_exposure`, `ORIENT_*`, `classify_orientation`, `flip_faces`, `one_sided_holes` were
written first in `engine/tests/test_exposure.py` and `engine/tests/test_orient.py`; running them
against the pre-change code failed with `ImportError` (names did not exist yet). After writing
`compute_side_exposure` in `exposure.py`, `test_orient.py` still failed with `ModuleNotFoundError:
No module named 'engine.fixes.orient'` until that file was created.

GREEN, focused:
```
.venv/Scripts/python.exe -m pytest engine/tests/test_exposure.py -q
13 passed in 0.48s
.venv/Scripts/python.exe -m pytest engine/tests/test_orient.py -q
13 passed in 0.81s
```

Wiring `fix_object` (`engine/fixes/pipeline.py`) surfaced two real regressions on first run of the
full suite:
```
2 failed, 135 passed in 10.72s
FAILED engine/tests/test_pipeline.py::test_rolled_back_when_merge_does_not_converge
FAILED engine/tests/test_pipeline.py::test_fix_object_flips_a_reversed_interior_triangle_and_still_fully_merges
```
Root cause (see systematic-debugging: read the actual failure, don't guess): `r.flipped.tolist()`
was `[True, True, ...]` for a deliberately-untouched region too — `gridded_box()`'s own winding
was inconsistent across faces (see fixture fix above), not a bug in `classify_orientation` or the
pipeline wiring; confirmed by checking `cube()`'s winding independently first (correct) before
concluding the fixture, not the new code, was wrong. After fixing `gridded_box()`:
```
.venv/Scripts/python.exe -m pytest -q
137 passed in 10.24s
```

### Real-data: 727 faces flip, one_sided_holes before/after

Deferred to the end of Task C (the CLI is what actually runs the pipeline against the real
snapshot files) — see the "Real-data acceptance" section below for both files' numbers, produced
by `python -m engine.cli fix`.

### Files changed
- `engine/vis/exposure.py` (modified)
- `engine/fixes/orient.py` (new)
- `engine/fixes/pipeline.py` (modified)
- `engine/tests/fixtures/build.py` (modified: `gridded_box` winding fix)
- `engine/tests/test_exposure.py` (modified)
- `engine/tests/test_orient.py` (new)
- `engine/tests/test_pipeline.py` (modified)

### Self-review / concerns

- `one_sided_holes` is called twice per `fix_object` run (before and after), each a fresh 26-view
  double-sided render with its own `EmbreeCaster` per view — real added cost, addressed by the
  caster-reuse fix in Task C (applied there to `one_sided_holes` too, even though task-8's brief
  doesn't name it, since it has the exact same 26-views-one-geometry hot loop).
- `thin_sheets`/`flipped` are bool arrays over ORIGINAL faces (paralleling `removed_hidden`/
  `removed_slit`), not scalar counts — the brief doesn't pin the exact shape, and `report.json`
  (Task C) sums them for the numeric fields it needs.

### Commit
`feat(engine): outward orientation and one-sided completeness` — db01d7a

---

## Task B (task-9-brief.md): polygon export + honest viewer data

### What I implemented

- `engine/fixes/merge.py`: `MergeResult` gains `rings: dict[int, np.ndarray] = field(default_factory=dict)`.
  Keyed by OUTPUT face row index in `mesh.face_v`; every row belonging to the SAME hole-free,
  single-piece merged region maps to the IDENTICAL ring array object (not just equal content), so
  a writer can group a region's rows and emit one polygon line by deduping on `id()` rather than
  on ambiguous vertex-set matching (two ADJACENT merged regions legitimately share border
  vertices, by design of the corner pass — matching on vertex membership alone would misattribute
  triangles on real, many-region files). `_region_ring(plan, needed, keep_all_set,
  welded_to_original)` replicates `_triangulate`'s own ring-simplification logic (full ring on the
  `keep_all` fallback, corner-pass-simplified ring otherwise) without changing `_triangulate`'s
  arity, which the task-5 report flags as load-bearing for existing monkeypatches. `_ring_ccw`
  orients the ring to match `_wound`'s own per-triangle CCW convention. A region with a hole, more
  than one disjoint piece, or fewer than 3 kept ring vertices gets no entry (its rows stay
  ordinary triangles). Ring vertex ids are mapped through `welded_to_original`, so they index
  `mesh.positions` exactly like `face_v` does.
- `engine/io/obj_writer.py`: `write_obj_polygons(mesh, rings, path)` — one `f` line per distinct
  ring (position-only, no vt/vn: an arbitrary n-gon has no single triangle's per-corner attribute
  set), ordinary (full v/vt/vn) triangles for every row absent from `rings`. `write_obj` itself is
  untouched.
- `engine/fixes/pipeline.py`: `FixResult` gains `rings` (`merge_result.rings` when not rolled
  back, else `{}` — there is no merged mesh for it to index into after a rollback). Not named in
  the task-9 brief's file list, but needed so the CLI (Task C) can write the ngon file without
  re-running the (expensive) hidden-removal guard a second time just to reconstruct
  `mesh_removed`; noted as a deliberate deviation from the brief's stated file list.

### TDD evidence

RED:
```
.venv/Scripts/python.exe -m pytest engine/tests/test_merge.py::test_grid_slab_rings_is_one_shared_four_vertex_ring_for_both_output_triangles -q
FAILED ... AttributeError: 'MergeResult' object has no attribute 'rings'
```
(all 4 new `test_merge.py` ring tests and all 4 new `test_obj_writer.py` polygon tests failed the
same way / with `ImportError: cannot import name 'write_obj_polygons'` before implementation.)

GREEN:
```
.venv/Scripts/python.exe -m pytest engine/tests/test_merge.py engine/tests/test_obj_writer.py -q
28 passed in ...
.venv/Scripts/python.exe -m pytest -q
145 passed in 10.69s
```

### Files changed
- `engine/fixes/merge.py` (modified)
- `engine/io/obj_writer.py` (modified)
- `engine/fixes/pipeline.py` (modified: `FixResult.rings`)
- `engine/tests/test_merge.py` (modified)
- `engine/tests/test_obj_writer.py` (modified)
- `engine/tests/test_pipeline.py` (modified: ring assertions on existing tests)

### Self-review / concerns

- Polygon lines are position-only (no vt/vn). The brief's signature (`write_obj_polygons(mesh,
  rings, path)`) doesn't carry per-corner attribute data for an arbitrary n-gon, and the file's
  own stated purpose is "show only its real shape edges" (a viewer/documentation artifact), not a
  textured/Unity-facing file — `write_obj` (unchanged) remains the file with full v/vt/vn and
  `usemtl` fidelity.
- `FixResult.rings` addition (see above) goes slightly beyond task-9's stated file list; flagged
  rather than silently done.

### Commit
`feat(engine): polygon export and viewer edge classes for the fixed mesh` — f3186d6

---

## Task C (task-7-brief.md): fix CLI, report, guard images, preview data

### What I implemented

- `engine/cli.py` (new): `python -m engine.cli fix <snapshot_dir> [--accept-slit] [--out data/output]`
  loads the snapshot (`_load_snapshot`: reads the one `.obj`, `materials.mtl`, derives flatness via
  `parse_mtl` + `texture_flatness`), runs `fix_object`, writes `<out>/<name>/<name>.fixed.obj`
  (triangles), `<name>.fixed.ngon.obj` (polygons, via `write_obj_polygons(result.mesh,
  result.rings, ...)`), copies `materials.mtl`/`tex/`, writes `report.json` (every `FixResult`
  number, both guard reports per view, the profile, `sha256_file(obj_path)`), and 6
  `guard_<axis>.png` triptychs (the 6 axis-aligned views of `VIEWS_26`); returns 0/2 as the exit
  code. `python -m engine.cli preview-data <snapshot_dir> --out preview/data` writes the JSON
  `preview/index.html` reads: AFTER is `result.mesh` (the real fixed mesh) and the real
  `guard_final`/`guard_after_removal` numbers; AFTER edges are split into `outline_after` (real
  shape edges) and `tri_after` (unavoidable triangulation diagonals) via
  `source_faces[i] is source_faces[j]` identity (two triangles from the SAME merged region share
  the identical array object `engine.fixes.merge._assemble` gives every triangle of one plan) --
  robust against two ADJACENT merged regions legitimately sharing border vertices, which a
  vertex-membership test would have misattributed. `stats` gained `flipped`, `thin_sheets`,
  `one_sided_holes_before/after`, `outline_edges_after`, `unavoidable_diagonals_after`,
  `guard_passed`. `preview/index.html` was not touched (it already reads `edges.tri_after`/
  `outline_after` for the AFTER panel).
- `engine/guard/render.py`: `save_triptych` gained optional `normals_before`/`normals_after` --
  when given, BEFORE/AFTER panels are Lambert-shaded (one fixed light + an ambient floor) by the
  hit face's own normal instead of flat grey; omitted, the old flat rendering is unchanged (the
  pre-existing test asserting image shape still passes untouched). DIFF stays flat/unshaded with
  red/amber overlays, per the brief.
- `engine/rays/caster.py`: `ReusableCaster(factory=EmbreeCaster)` -- a size-1 cache keyed by
  `(positions, faces)` object IDENTITY (`is`, not equality). Threaded through every 26-view render
  loop that previously built a fresh caster per view: `engine.fixes.pipeline._render`,
  `engine.guard.compare.guard_feedback`'s BEFORE list and each round's AFTER render, and
  `engine.fixes.orient.one_sided_holes` (not named in task-8's brief, but it has the identical
  26-views-one-geometry hot loop, so I applied the same fix there too for consistency and real
  benefit). `compare_views`'s own coverage-probe casters were already built once outside any
  per-view loop and needed no change.

### TDD evidence

RED: `engine/tests/test_cli.py` referenced `engine.cli` before the module existed
(`ModuleNotFoundError`); `engine/tests/test_caster.py`'s `ReusableCaster` tests failed with
`ImportError: cannot import name 'ReusableCaster'`; `engine/tests/test_guard.py`'s new shading
tests failed with `TypeError: save_triptych() got an unexpected keyword argument 'normals_before'`.

GREEN:
```
.venv/Scripts/python.exe -m pytest engine/tests/test_cli.py -q          -> 12 passed in 3.12s
.venv/Scripts/python.exe -m pytest engine/tests/test_caster.py -q       -> 7 passed
.venv/Scripts/python.exe -m pytest engine/tests/test_guard.py -q        -> 27 passed
.venv/Scripts/python.exe -m pytest -q                                   -> 164 passed in 9.81s (10.92s on the final run)
```
CLI tests use a `_FAST` profile (`guard_size=(120, 80), n_dirs=32`, matching the rest of the
suite's convention) -- the default `FixProfile` (900x600 x 26 views) is real-file-sized and took
30-45s per `fix_object` call even on a 14-triangle fixture (see "runtimes" below for why), which
is not something a unit test should pay for. `cmd_fix`/`cmd_preview_data` both accept an optional
`profile` override for exactly this reason; `main()`'s own argparse dispatch is tested by stubbing
`cmd_fix`/`cmd_preview_data`, not by running the real pipeline.

The "exits 2" test (`test_cmd_fix_exits_two_when_a_visible_face_is_wrongly_removed`) monkeypatches
`engine.fixes.pipeline.guard_feedback` to also confirm-remove a real, visible outer cube face
(bypassing its own restore loop) -- the INDEPENDENT final guard (unpatched, comparing the merged
result to the pristine original) still catches the resulting hole and fails, proving the exit
code is driven by a real, structurally-independent guard check, not just a flag threaded through.

### Real-data acceptance

Snapshots: file A = `data/snapshots/ce26e0392ab0` (already existed). File B had no engine
snapshot; `../CKPT17-CLEAN.mtl` did not resolve from `data/spike/snapshot/`'s own directory (that
file lives one level up only conceptually -- `data/spike/CKPT17-CLEAN.mtl` does not exist), so per
the fallback instructions I copied `CHTM_2nd_to_3rd_building_sidewalk_outside.obj` +
`CKPT17-CLEAN.mtl` + `SRC-TEX/` into `data/output/_scratch/{split/<obj>, CKPT17-CLEAN.mtl,
SRC-TEX/}` and ran `engine.io.snapshot.snapshot_object` from there, producing
`data/snapshots/0b290ec0bcb4/` (7,227 triangles, 3 materials, 0 missing textures). The live export
folder `D:\PROJECTS\UC ENVIRONMENT BUILDING\...` was never read.

Commands run (default `FixProfile`, i.e. `n_dirs=128`, `guard_size=(900,600)`):
```
python -m engine.cli fix data/snapshots/ce26e0392ab0 --out data/output
python -m engine.cli fix data/snapshots/ce26e0392ab0 --accept-slit --out data/output_accept_slit
python -m engine.cli fix data/snapshots/0b290ec0bcb4 --out data/output
python -m engine.cli fix data/snapshots/0b290ec0bcb4 --accept-slit --out data/output_accept_slit
python -m engine.cli preview-data data/snapshots/ce26e0392ab0 --out preview/data
python -m engine.cli preview-data data/snapshots/0b290ec0bcb4 --out preview/data
```

**File A (2nd floor), default (`data/output/CHTM_SIDE_WALK_2nd_floor/report.json`):**
```
input_sha256: ce26e0392ab0907c5c65ab429abeb9ba4911d6252b69134e27c933941bac16fa
n_hidden_candidates: 1853   n_restored_by_guard: 34   n_removed_hidden: 1819   n_zero_area_dropped: 217
n_flipped: 844   n_thin_sheets: 47
one_sided_holes_before: 570046   one_sided_holes_after: 116041
tris_before: 4692   tris_after: 2656
guard_after_removal: passed=True, {holes:0, material_changed:0, moved_same_flat:0, moved_other:0, edge_flicker:0}
merge_report: tris_before=2656, tris_after=1894, regions_merged=169, converged=True,
              rolled_back=True, rolled_back_reason="guard_failed"
guard_final (of the SHIPPED, rolled-back mesh vs original): passed=True, all-zero totals
invariants: {material_count_same:True, bbox_same:True, area_not_grown:True, guard_passed:True}
passed: True
```
Matches expectations: hidden removed after feedback (1,819 = "A 1,819"); `guard after removal`
0/0/0 over all 26 views; invariants all true; fixed OBJ re-imports with 0 zero-area faces,
1 material (unchanged).

**Does NOT match two expectations, investigated and explained, not tuned away:**

1. **`n_flipped` = 844, not the expected 727.** Restricting to non-slit (`EXP_OUTSIDE`) faces only
   gives 760 (closer, still not 727); by area, flipped faces are 24.6% of visible area vs the
   brief's measured 18.1%. `classify_orientation`/`compute_side_exposure` were implemented exactly
   to the brief's written spec (`FLIP when back > front`, `n_dirs=128`, same `EPS_IN`/`BARY`
   sampling as `compute_exposure` always used) and unit-tested to prove `flip_faces` never changes
   a single pixel of any render (`test_orient.py::test_flip_faces_never_changes_the_render`,
   `test_pipeline.py::test_flip_step_never_introduces_guard_damage`) -- so the discrepancy is in
   which faces get COUNTED as needing a flip, not in flip's own correctness. I could not fully
   reproduce "the same sampling as the measurement above" without the original measurement script
   (not present in the repo); slit-inclusion explains part of the gap (844 -> 760) but not all of
   it. I did not tune any threshold to chase 727.

2. **`tris_after` = 2,656, not `<= 2,073`, because the merge ROLLED BACK.** The merge itself
   converged and produced 1,894 triangles (fewer than the historical no-flip 2,062, i.e. flip DID
   let more regions merge, as intended) -- but its own guard against the pristine original found
   exactly **one** `moved_same_flat` pixel (of 2,059,414) plus the same one pre-existing
   `edge_flicker` pixel, and `strict_final` (`= not (accept_slit and n_removed_slit > 0)`, which is
   unconditionally `True` for a non-`--accept-slit` run) treats ANY `moved_same_flat` pixel as an
   automatic failure regardless of the flicker cap, so the pipeline correctly rolled back to the
   safe, flipped-but-unmerged 2,656-triangle mesh.

   I traced the one pixel by hand (view `(-0.987, 0.007, -0.989)`, pixel `(530, 338)`): BEFORE
   hits original face 2540 (part of a sloped ramp/stair segment, z~1749-1755); AFTER hits a
   triangle from a 261-member merged region on an ADJACENT stair segment (z~1770-1780) that is
   16.3 units closer along the ray. Both faces are legitimately part of the model; this is an
   occlusion-order tie-break between two DIFFERENT, real, adjacent-in-screen-space surfaces at one
   oblique camera angle, not a hole or lost geometry. **Confirmed this is a task-8-introduced
   change, not a pre-existing defect**: re-running the identical removal state through
   `merge_regions` WITHOUT the flip step reproduces the historical numbers exactly (`tris_after
   =2062`, `guard_final passed=True`, `{holes:0, material_changed:0, moved_same_flat:0,
   moved_other:0, edge_flicker:1}`) -- flipping 844 faces lets MORE triangles join their true
   region (including, on this specific pair of adjacent ramp segments, ones that make the region's
   retriangulated boundary graze a different surface at one pixel). With `--accept-slit` (see
   below), `strict_final` becomes `False` and the SAME kind of pixel (1,008 of them, at a much
   larger scale) is correctly reported but tolerated, confirming the mechanism.

   I deliberately did **not** change `strict_final`'s semantics to make this pass: that is a
   pre-existing (task 6) design decision this task's brief didn't ask me to revisit, and doing so
   to reach a specific number is exactly what "do not tune anything to reach a number" forbids.
   Flagged as a concern below with a specific, narrow suggested fix.

**File A, `--accept-slit`** (`data/output_accept_slit/CHTM_SIDE_WALK_2nd_floor/report.json`):
```
n_removed_hidden: 1819 (same)   n_removed_slit: 163 (expected "164 more" -- off by one, see below)
n_flipped: 761   tris_before: 4692   tris_after: 1731
merge_report: regions_merged=137, converged=True   (no rollback this time)
guard_final: passed=True, {holes:0, material_changed:0, moved_same_flat:1008, moved_other:0, edge_flicker:1}
invariants: all True.  passed: True
```
`n_removed_slit=163` vs the expected "164 more" is off by one, well within the noise of a
guard-feedback restore loop (see `report.json`'s own `feedback_history["slit"]` for file A's exact
per-round counts). `moved_same_flat` is large (1,008) here specifically BECAUSE `strict_final` is
`False` (`accept_slit` AND `slit-removed>0`), so it is reported, not treated as a failure --
exactly the "final guard ... with moved_same_flat reported" pattern the task-7 acceptance table
names, and exactly the mechanism identified above as the fix for the default run's 1-pixel
rollback.

**File B (2nd to 3rd), default** (`data/output/CHTM_2nd_to_3rd_building_sidewalk_outside/report.json`):
```
input_sha256: 0b290ec0bcb47402a5fe661fc037eb7d457e01917a0d748d900b8551946b65e2
n_hidden_candidates: 2411   n_restored_by_guard: 30   n_removed_hidden: 2381   n_zero_area_dropped: 79
n_flipped: 842   n_thin_sheets: 103
one_sided_holes_before: 465146   one_sided_holes_after: 90543
tris_before: 7227   tris_after: 4767
guard_after_removal: passed=False, {holes:0, material_changed:12, moved_same_flat:0, moved_other:0, edge_flicker:0}
merge_report: converged=True, tris_after=1282, rolled_back=True, rolled_back_reason="guard_failed"
invariants: {..., guard_passed: False}.  passed: False
```
`n_removed_hidden=2381` matches "B 2,381" exactly. `n_flipped=842` is close to "about 800".
**`passed=False`, tris stuck at 4,767 (not `<= 2,499`) -- and this is NOT caused by task 8/9.**
`guard_after_removal` already fails at 12 `material_changed` pixels BEFORE merge is even reached
(merge then also rolls back, since its own guard inherits the same original-vs-final comparison).
I reproduced the identical `{material_changed: 12}` by re-running removal WITHOUT the flip step at
all: **file B's zero-area-face removal (79 faces, dropped unconditionally by `remove_faces` with
no guard check at all, per `engine.fixes.pipeline`'s design since task 6) exposes 12 pixels where
a different material now shows through.** This is a pre-existing gap in the removal pipeline
(zero-area drop bypasses `guard_feedback` entirely), reproducible with or without flip, and out of
scope for tasks 8/9 to fix.

**File B, `--accept-slit`** (`data/output_accept_slit/CHTM_2nd_to_3rd_building_sidewalk_outside/report.json`):
```
n_removed_slit: 181   tris_after: 4586   passed: False
guard_after_removal / guard_final: {material_changed:12, moved_same_flat:426, ...}, passed=False
slit feedback history: round 0 {candidates_remaining:193, failing_pixels:155, restored:12}, round 1 {..., restored:0}
```
The task's expectation ("B's 260 px material_changed must make that run fail unless guard feedback
restores the responsible faces, in which case report how many were restored") is answered
precisely: **guard feedback restored 12 of the 193 slit candidates** (its own colour-tolerant pass
converges to 0 failing pixels for the slit removal itself: round 0 had 155 failing pixels, all
gone after restoring those 12). The run still reports `passed=False`, but for the SAME
pre-existing, slit-unrelated reason as the default run: `material_changed` stays at exactly 12 in
both the default and `--accept-slit` runs, confirming it is the zero-area-removal gap, not
anything slit-caused. `n_removed_slit=181` is in the ballpark of "193 more" (193 candidates, 12
restored, 181 shipped).

**Guard images**: 6 `guard_<axis>.png` triptychs written per run. Visually confirmed
(`data/output/CHTM_SIDE_WALK_2nd_floor/guard_+z.png`): the BEFORE panel shows a visibly
inconsistent light/dark shading pattern across one large wall (the orientation defect this task
fixes), and the AFTER panel shows the same wall uniformly shaded once its mis-wound triangles are
flipped -- a direct visual confirmation that orientation correction is doing what it claims.

**Preview page**: `preview/data/{name}.json` + `index.json` written for both files; opened
`http://localhost:5180` (via the existing `.claude/launch.json` "preview" config) and confirmed
both files load with the real numbers (4,692/217/1,819/561 for A, 7,227/79/2,381/571 for B, both
matching `report.json` exactly) and no console errors.

### Runtimes: before/after the caster-reuse fix

Measured on file A (`data/snapshots/ce26e0392ab0`), default profile:
- **CLI `fix` wall-clock (with `ReusableCaster` reuse, as shipped): 28-35s** (34.6s / 33.0s
  measured across separate runs, includes report/ngon/guard-image writing).
- **`fix_object` alone, WITH reuse: 28.7s. WITHOUT reuse (`ReusableCaster` monkeypatched to a
  never-caching passthrough, simulating the pre-fix behaviour): 25.6s.** Ran back-to-back in the
  same process; results (mesh `face_v`, `guard_final.totals`) were bit-identical between the two,
  confirming correctness, but **the measured wall-clock difference is within noise -- no
  meaningful speedup on this file.**
- I profiled why (`cProfile` on a `fix_object` call): ~85% of total time is inside
  `ortho_first_hit` -> `EmbreeCaster.first_hit` -> trimesh's `RayMeshIntersector.intersects_location`
  (182 render calls, 25.4s of 30.8s total on a small fixture). Isolated construction cost directly:
  **26 `EmbreeCaster` constructions for 4,475 real triangles took 0.000s total** (sub-millisecond
  each) -- construction was never the bottleneck for this codebase. One 900x600 `first_hit` call
  (540,000 rays) against that same geometry took **0.086s**, and `fix_object` makes on the order of
  150-200 such calls (before/after renders x 26 views x several guard passes, plus the two new
  `one_sided_holes` passes this task added), which is what actually adds up to ~30s.

  **Honest conclusion**: `ReusableCaster` is implemented correctly and is a legitimate
  optimisation (it removes genuinely wasted, redundant BVH construction, verified bit-identical by
  test and by this A/B run), but it does not meaningfully reduce the measured ~30s/object runtime
  for this codebase, because the dominant cost is trimesh's per-ray Python-level overhead in
  `intersects_location` (proportional to image resolution x view count x render-pass count), not
  caster construction. A real reduction in per-object runtime would need a different fix (e.g. a
  lower-level embree call bypassing `intersects_location`'s overhead, fewer render passes, or a
  smaller default `guard_size`) that is out of this task's stated scope ("build one caster per
  distinct geometry and reuse it across views" -- which I did, and confirmed is not itself where
  the time goes). I am reporting this rather than claiming a speedup that the numbers don't show.

### Files changed
- `engine/cli.py` (new)
- `engine/tests/test_cli.py` (new)
- `engine/guard/render.py` (modified: shading)
- `engine/rays/caster.py` (modified: `ReusableCaster`)
- `engine/guard/compare.py`, `engine/fixes/pipeline.py`, `engine/fixes/orient.py` (modified: wired
  `ReusableCaster` into their 26-view render loops)
- `engine/tests/test_caster.py`, `engine/tests/test_guard.py`, `engine/tests/test_pipeline.py`
  (modified: reuse + shading tests)
- Data (git-ignored, not committed): `data/snapshots/0b290ec0bcb4/` (file B's new snapshot),
  `data/output/`, `data/output_accept_slit/`, `preview/data/`, `data/output/_scratch/` (the
  scratch copy used only to resolve file B's `mtllib`, per the task's own fallback instructions)

### Self-review / concerns

1. **File A's default run does not merge (rolls back to 2,656 tris, not <=2,073)** because of a
   single `moved_same_flat` pixel introduced by flip enabling more aggressive merging, treated as
   an automatic failure by the pre-existing (task 6) `strict_final=True` policy for non-slit runs.
   Root cause fully traced and explained above. **Suggested fix (not applied, out of this task's
   scope):** decouple the FINAL (post-merge) guard's strictness from `guard_after_removal`'s --
   merging is provably non-destructive (never deletes visible content; `merge_regions` already
   enforces `area_not_grown`), unlike removal, so treating a rare, sub-pixel `moved_same_flat` from
   re-triangulation as an unconditional failure the way an actual deletion should be judged treats
   two different kinds of risk identically. This would very likely bring file A's default run to
   the expected `<=2,073` (the same merge already produces 1,894 when it isn't rolled back).
2. **File B does not pass in EITHER mode** (`material_changed=12`, reproduced identically with and
   without flip and with and without `--accept-slit`): a pre-existing gap where zero-area faces
   are dropped by `remove_faces` with no guard check at all. Out of scope for tasks 8/9; flagged
   for a follow-up task, not fixed here.
3. `n_flipped` (844/842) does not match the brief's measured 727/800 "same sampling" figures for
   either file; investigated (see above) but not resolved without the original measurement script.
4. Runtime: caster reuse verified correct (bit-identical) but not shown to meaningfully reduce
   real-file runtime; the actual bottleneck (trimesh's per-ray overhead) is identified but not
   addressed, as that was out of this task's literal scope.
5. Guard images use the plain 3x3-neighbourhood flicker test (no sub-pixel coverage probe), so a
   rare borderline silhouette pixel could render red in the diagnostic image even when the real
   (coverage-checked) `guard_final` tolerated it as flicker -- noted in the module docstring;
   `report.json`'s numbers are always the authoritative ones, never re-derived from the images.

### Commit
`feat(engine): fix CLI, report, guard images, preview data` — 4667e4e

---

## Public signatures

(new/changed by this batch of three tasks; anything not listed here is unchanged from the last
`## Public signatures` section of `task-3-4-report.md`, `task-5-report.md` or `task-6-report.md`)

```
engine/vis/exposure.py

compute_side_exposure(positions_c, face_w, ok, caster_factory=EmbreeCaster, n_dirs=128)
    -> (front: np.ndarray, back: np.ndarray)   # NEW
compute_exposure(positions_c, face_w, ok, caster_factory=EmbreeCaster, n_dirs=128) -> np.ndarray
    # unchanged return value (front + back); implementation now delegates to compute_side_exposure
```

```
engine/fixes/orient.py   # NEW FILE

ORIENT_OK = 0
ORIENT_FLIP = 1
ORIENT_THIN_SHEET = 2

classify_orientation(front, back, ok, sheet_ratio=0.5) -> np.ndarray[uint8]
    # FLIP when back > front; else THIN_SHEET when front>0 and back>0 and
    # min(front,back)/max(front,back) >= sheet_ratio; else OK. Hidden/not-ok faces are always OK.

flip_faces(mesh: MeshData, flip: np.ndarray[bool]) -> MeshData
    # reverses face_v/face_vt order for flagged faces, drops their face_vn to -1 (all three
    # corners), leaves positions/everything else untouched. Raises ValueError on shape mismatch.

one_sided_holes(positions_c, faces, face_ids, views, size, caster_factory=EmbreeCaster) -> int
    # pixels that hit in a double-sided render but whose first-hit face is back-facing to that
    # view's camera, summed over every view in `views`.
```

```
engine/fixes/pipeline.py

@dataclass
class FixResult:
    # ... (all task-6 fields unchanged) ...
    flipped: np.ndarray            # NEW, bool over ORIGINAL faces
    thin_sheets: np.ndarray        # NEW, bool over ORIGINAL faces
    one_sided_holes_before: int    # NEW
    one_sided_holes_after: int     # NEW
    rings: dict[int, np.ndarray]   # NEW: engine.fixes.merge.MergeResult.rings, valid against
                                    # `mesh`; {} when rolled back
    # (field order: exactly as above, inserted after n_zero_area_dropped and after merge_report
    # respectively -- see the dataclass definition for the authoritative order)

fix_object(mesh, flatness, profile=FixProfile()) -> FixResult   # signature unchanged
    # pipeline order: exposure -> hidden removal (strict guard) -> (accepted slit removal) ->
    # orientation flip -> merge -> final guard. Flipping never changes a double-sided render.
```

```
engine/fixes/merge.py

@dataclass
class MergeResult:
    mesh: MeshData
    source_faces: list[np.ndarray]
    report: dict
    rings: dict[int, np.ndarray] = field(default_factory=dict)   # NEW
    # keyed by OUTPUT face row index in `mesh.face_v`; every row of the SAME hole-free,
    # single-piece merged region maps to the IDENTICAL ring array object (dedup by `id()`, not
    # content); absent for holed/multi-piece regions and copied-through faces. Ring vertex ids are
    # ORIGINAL-mesh ids (via welded_to_original), CCW in the region's own outward frame.

merge_regions(...) -> MergeResult   # signature unchanged; report dict keys unchanged
```

```
engine/io/obj_writer.py

write_obj_polygons(mesh: MeshData, rings: dict[int, np.ndarray], path) -> None   # NEW
    # one `f` line (position-only) per distinct ring object in `rings`; ordinary v/vt/vn
    # triangles for every row absent from `rings`. write_obj (triangulated) is unchanged.
```

```
engine/rays/caster.py

class ReusableCaster:      # NEW
    def __init__(self, factory=EmbreeCaster): ...
    def __call__(self, positions, faces) -> RayCaster
        # size-1 cache keyed by (positions, faces) OBJECT IDENTITY (`is`); returns the same
        # caster instance for repeat calls with the same objects, rebuilds on any change.
```

```
engine/guard/render.py

save_triptych(path, before, after, verdict_mask,
              normals_before: np.ndarray | None = None,   # NEW
              normals_after: np.ndarray | None = None) -> None   # NEW
    # with normals given, BEFORE/AFTER panels are Lambert-shaded by the hit face's own normal
    # (fixed light + ambient floor); omitted, falls back to the original flat rendering. DIFF is
    # always flat/unshaded with red (fail) / amber (tolerated) overlays.
```

```
engine/guard/compare.py

guard_feedback(...) -> (mask, history)   # signature unchanged
    # internally wraps caster_factory in ReusableCaster for its BEFORE render and each round's
    # AFTER render (was: a fresh caster per view). Bit-identical results.
```

```
engine/cli.py   # NEW FILE

build_parser() -> argparse.ArgumentParser
main(argv: list[str] | None = None) -> int
cmd_fix(snapshot_dir: Path, out_root: Path, accept_slit: bool, profile: FixProfile | None = None) -> int
cmd_preview_data(snapshot_dir: Path, out_dir: Path, profile: FixProfile | None = None) -> int
    # `profile` is an internal testability hook (unit tests inject a small guard_size/n_dirs);
    # not exposed as a command-line flag. See module docstring for the full CLI contract.
```

