# Task 6 report -- pipeline + invariants

Branch `phase2e-fix-pipeline`. New file: `engine/fixes/pipeline.py`. New fixture:
`engine/tests/fixtures/build.py`'s `gridded_box`. Tests appended to `engine/tests/test_pipeline.py`
(see "Naming collision" below). One prerequisite hardening in `engine/guard/compare.py` per
decision 5, its own commit, test-first.

## Decision 5: `compare_views` flicker-cap hardening (done first, its own commit)

`compare_views(edge_flicker_cap > 0.0)` without `geometry_before`/`geometry_after` used to let the
3x3-neighbourhood test decide `PX_EDGE_FLICKER` on its own -- flagged as a known gap in the task-5
fix-round-2 report ("The 3x3-only path is still reachable and still silent... safe only at
`edge_flicker_cap = 0.0`"). Added a check at the top of `compare_views`: `edge_flicker_cap > 0.0`
without both geometries now raises `ValueError`, matching the existing `allow_depth_fallback`
pattern.

This broke three existing tests whose whole premise was exactly that unsafe path:

- `test_a_removed_face_beside_a_pre_existing_gap_is_a_hole_at_any_cap`'s "blind" case demonstrated
  the defect on purpose (a removed face beside a pre-existing gap tolerated at `cap=1.0` with no
  geometry). Changed to assert the `ValueError` instead of the old silent `passed is True`.
- `test_edge_flicker_within_the_cap_passes` / `test_edge_flicker_above_the_cap_fails` tested cap
  arithmetic using hand-built `HitBuffers` with a whole pixel's triangle dropped -- with real
  geometry, a WHOLLY dropped pixel is correctly reclassified `PX_HOLE` by the coverage check (25/25
  sub-rays lost), not flicker, so these tests' premise (a nonzero cap with a hand-built "flicker"
  buffer and no geometry) is no longer reachable at all. Deleted; their intent (cap tolerance) is
  now covered by two new assertions added to `test_a_thousandth_of_an_inch_of_boundary_shift_is_
  edge_flicker`, which already has real geometry and exactly one genuine flicker pixel (a boundary
  shift, not a full removal) out of 949 model pixels: `edge_flicker_cap=2e-3` (`> 1/949`) passes,
  `edge_flicker_cap=5e-4` (`< 1/949`) fails.
- `test_interior_hole_fails_at_any_cap`'s nonzero-cap calls now pass a trivial placeholder
  `(positions, faces)` pair (a single triangle) via a new `geometry` kwarg on `_flicker_report`.
  It is never actually ray-cast in that scenario (the dropped pixel is not on the 3x3 silhouette,
  so `classify_pixels` never calls the `coverage` callable), so any valid, constructible geometry
  works.

New test: `test_edge_flicker_cap_above_zero_without_geometry_is_an_error`.

RED:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_guard.py -q
FAILED test_a_removed_face_beside_a_pre_existing_gap_is_a_hole_at_any_cap
FAILED test_edge_flicker_cap_above_zero_without_geometry_is_an_error - Failed: DID NOT RAISE ValueError
2 failed, ... (before the ValueError check existed)
```
(the two soon-to-be-deleted tests were passing before the change and were removed as part of the
same edit, not left red.)

GREEN:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_guard.py -q
........................                                                 [100%]
24 passed in 1.68s
```
Full suite: `111 passed` (112 - 2 deleted + 1 new).

Commit: `045c2b9 fix(engine): flicker cap above zero requires geometry`.

## Naming collision: `engine/tests/test_pipeline.py`

The brief says "Files: Create `engine\fixes\pipeline.py`, `engine\tests\test_pipeline.py`", but
`engine/tests/test_pipeline.py` already existed, testing `engine/pipeline.py` (`analyse_topology`,
`flat_material_indices`) -- a different module from this task's `engine/fixes/pipeline.py`.
Renaming or overwriting it would have deleted that module's only coverage. Resolved by appending
`fix_object`'s tests to the same file, under a clearly labelled section, rather than creating a
second, confusingly-similar file name (`test_fix_pipeline.py` or similar). Both modules' tests now
live in that one file; nothing already there was changed.

## What I implemented

`engine/fixes/pipeline.py`:

- `FixProfile` (`n_dirs=128`, `slit_threshold=0.05`, `accept_slit=False`, `flat_texture_std=8.0`,
  `guard_size=(900, 600)`, `edge_flicker_cap_final=1e-4` per decision 2).
- `FixResult` -- extends the brief's sketch per decision 6 ("must carry enough to explain itself
  later"): `mesh`, `source_faces` (list of int64 arrays, ORIGINAL-mesh face indices, per decision:
  a whole region when merged, a single face otherwise), `exposure_class` (per ORIGINAL face),
  `removed_hidden` / `removed_slit` (bool, over ORIGINAL faces), `n_hidden_candidates`,
  `n_restored_by_guard`, `n_removed_hidden`, `n_removed_slit`, `n_zero_area_dropped`,
  `feedback_history` (`{"hidden": history, "slit": history | None}`), `guard_after_removal`,
  `guard_final` (both `GuardReport`), `merge_report`, `invariants`, `passed`.
- `fix_object(mesh, flatness, profile=FixProfile()) -> FixResult`, exactly the order in the brief:
  1. `flat_materials = flat_material_indices(mesh, flatness, profile.flat_texture_std)`,
     `analyse_topology(mesh, flat_materials)`.
  2. `depth_tol = 1.5 * max(topo.quanta)` (decision 4). Positions recentred ONCE to the ORIGINAL
     mesh's bbox centre (`topo.positions_w`'s own bbox); that frame renders every side, at every
     stage, before and after.
  3. `compute_exposure` / `classify_exposure` over the welded original mesh.
  4. Pass 1 (hidden): `guard_feedback(strict=True)` over the `ok`-only face subset (decision 1 --
     hidden removal gets the strictest guard, `edge_flicker_cap=0.0` internally as `guard_feedback`
     always uses).
  5. Pass 2 (slit, only when `profile.accept_slit` and there are slit candidates): a SECOND
     `guard_feedback(strict=False)` call, over the faces pass 1 leaves behind (i.e. with the
     confirmed-removable hidden faces already excluded from the renderable set) -- "after the
     hidden pass" read as: the slit guard's own BEFORE state already reflects the hidden removal.
  6. `remove_faces` with `drop = removed_hidden | removed_slit | zero_area` (decision: zero-area
     faces are always dropped alongside whichever candidates the guards confirmed).
  7. `analyse_topology` on the result, `merge_regions`.
  8. Two `compare_views` calls against the ORIGINAL (`guard_after_removal`, `guard_final`), both
     always given full geometry (`geometry_before`/`geometry_after`, `plane_before`/`plane_after`)
     so neither ever falls back to the noisier 3x3-only flicker test. `guard_final` uses
     `edge_flicker_cap=profile.edge_flicker_cap_final`; `guard_after_removal` uses `0.0`.
  9. Rollback (decision 3): a merge with `report["converged"] is False` is treated exactly like a
     failed final guard -- roll back to the un-merged (removal-only) mesh, set
     `merge_report["rolled_back"] = True` and `merge_report["rolled_back_reason"]` to
     `"not_converged"` or `"guard_failed"`, and recompute `guard_final` against the FALLBACK mesh
     (so `passed`/`invariants["guard_passed"]` reflect what actually shipped, not the discarded
     merge candidate).
  10. Invariants: `material_count_same` (`len(materials)` equal -- both `remove_faces` and
      `merge_regions` pass `materials` through unchanged, so this is a sanity check, not a live
      constraint), `bbox_same` (positions are never touched by either step, so this is also a
      by-construction sanity check, kept as defence against a future regression), `area_not_grown`
      (whole-mesh total triangle area, `<=` original `* (1 + 1e-6)`, mirroring `engine.fixes.merge`'s
      own per-region tolerance), `guard_passed` (`guard_final.passed`). `passed = all(invariants
      .values())` -- in every fixture and the real-data run this reduces to exactly
      `guard_final.passed`, since the other three invariants are guaranteed by construction; ANDing
      them in is defence-in-depth, not a behaviour change from "passed reflects the fallback's
      guard" (see Concerns).

Design decisions not spelled out in the brief or its binding decisions:

1. **Rendering the ORIGINAL and the FINAL mesh without a third `analyse_topology` call.** The
   brief's step list has exactly two `analyse_topology` calls (initial, post-removal); the merged
   (or rolled-back) mesh needs its own welded face array to render against `positions_c`, but
   `remove_faces` and `merge_regions` both leave `mesh.positions` untouched (same array, never
   re-indexed), so `weld_exact(mesh.positions, mesh.coord_decimals)` -- called once, directly, up
   front -- gives a `remap` that is valid for ANY mesh derived from that same `positions` array.
   `remap[final_mesh.face_v]` is used for both the after-removal and the final render, instead of
   a third full topology analysis (which would also rebuild the edge table and regions, unneeded
   just to render).
2. **`guard_after_removal`'s strictness and cap.** The brief only pins `guard_final`'s strictness
   (decision 2). `guard_after_removal` uses the SAME `strict_final` flag (true unless a slit face
   was accepted and removed) for the same reason decision 2 gives it: a slit removal is a
   person-accepted, colour-tolerant change, and that tolerance should apply consistently to both
   the immediate post-removal check and the final one. `edge_flicker_cap=0.0` there, matching what
   `guard_feedback` already enforced internally for every candidate it removed -- there is nothing
   left to tolerate at that checkpoint that the removal guards did not already decide.
3. **Both `compare_views` calls always get real geometry.** Even `guard_after_removal`'s
   `edge_flicker_cap=0.0` (which decision 5 does not require geometry for) is given
   `geometry_before`/`geometry_after`, so it always gets the coverage-aware classification rather
   than ever falling back to the noisier 3x3-only test.
4. **Second guard pass's "against the original" reading.** The brief's short-form order says
   "guard_feedback against the original" once, before the binding decisions split hidden and slit
   into two passes. Read literally, "against the original" describes the loop's own contract
   (`guard_feedback` always renders BEFORE once, over whatever `faces` it is given, and decides
   removability against that) rather than a literal instruction to re-render the pristine mesh
   for pass 2; decision 1's "after the hidden pass" phrasing only makes sense if pass 2's BEFORE
   state already excludes the hidden faces pass 1 confirmed. Implemented as: pass 2's `faces` /
   `candidates` are the render-set MINUS the confirmed-removable hidden faces, restricted to slit
   candidates within what remains. The ONE place "the original" is load-bearing and explicit in
   caps is the final guard, which is always the true original mesh, never an intermediate state --
   implemented as such (`before_original` computed once, reused for both `compare_views` calls).

## New fixture

`gridded_box(n=4, cell=2.5, uv_per_unit=0.05)` in `engine/tests/fixtures/build.py`: a closed cube
built from an `n x n` grid per face (`2 * n * n` triangles per face, `6 * 2 * n * n` total), the way
a SketchUp export cuts a flat panel into gridlines. Verified computationally before writing the
fixture-based tests (not guessed): `gridded_box(4, 2.5)` -> 192 faces, `topo.ok.all()`, exactly 6
regions, exposure `0.5` on every face (none hidden, none slit -- a closed box's own faces are only
ever half-blocked, double-sided exposure, never sealed on BOTH sides the way an interior partition
is), `merge_regions` -> 12 triangles, `converged: True`.

## TDD evidence

RED, before `engine/fixes/pipeline.py` existed:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_pipeline.py -q
ImportError while importing test module '...\engine\tests\test_pipeline.py'.
engine\tests\test_pipeline.py:16: in <module>
    import engine.fixes.pipeline as fix_pipeline
E   ModuleNotFoundError: No module named 'engine.fixes.pipeline'
```

Every fixture-behaviour number in the new tests (hidden/removed/restored counts, merge counts,
`source_faces` shapes, the rollback mesh's identity) was measured by running the real implementation
in a scratch script BEFORE being written into an assertion, per this repo's "measure, don't guess"
convention (e.g. `source_faces` lengths: 2-member per cube face, 32-member per `gridded_box` face
region -- discovered by inspection, not assumed).

GREEN:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_pipeline.py -q
.........                                                                [100%]
9 passed in 3.78s
```

Full suite:
```
$ .venv/Scripts/python.exe -m pytest -q -W error::DeprecationWarning
........................................................................ [ 62%]
............................................                             [100%]
116 passed in 7.65s
```
(111 after decision 5 + 5 new: `test_box_with_partition_removes_only_the_sealed_partition`,
`test_gridded_closed_box_has_nothing_hidden_and_merges_to_twelve_triangles`,
`test_fix_object_is_deterministic`,
`test_accept_slit_removes_a_barely_exposed_interior_face_under_a_colour_tolerant_guard`,
`test_rolled_back_when_merge_does_not_converge`.) No warnings.

### Tests written (`engine/tests/test_pipeline.py`, appended)

1. `test_box_with_partition_removes_only_the_sealed_partition` -- the 2 partition triangles are the
   only `EXP_HIDDEN` faces, both confirmed removable (0 restored), the 12 outer triangles stay 12
   (already minimal, cannot merge further), `passed` True, `guard_final` totals all zero, no slit
   pass ran (`feedback_history["slit"] is None`).
2. `test_gridded_closed_box_has_nothing_hidden_and_merges_to_twelve_triangles` -- `gridded_box(4,
   2.5)`: nothing hidden or slit, 192 -> 12 after merge, `passed` True, and every output face's
   `source_faces` entry is its whole 32-member region (measured, not assumed).
3. `test_fix_object_is_deterministic` -- two runs of `gridded_box(3, 2.5)` give identical
   `face_v`/`face_vt`/`face_vn`/`uvs`, `merge_report`, `invariants`, `guard_final.totals` and
   `source_faces`.
4. `test_accept_slit_removes_a_barely_exposed_interior_face_under_a_colour_tolerant_guard` --
   `open_box_with_cells()`'s "deep" partition (faces 12-13) measured as `EXP_SLIT` (exposure
   ~0.014-0.018, verified by direct computation before writing the test) with default `n_dirs=128`;
   left alone at `accept_slit=False` (mesh stays at 14 faces, no slit pass runs), removed at
   `accept_slit=True` with `flatness={}` (every material flat with no explicit entry) -- mesh drops
   to 12 faces, `passed` True.
5. `test_rolled_back_when_merge_does_not_converge` -- `gridded_box(4, 2.5)` (which `merge_regions`
   would otherwise collapse 192 -> 12) with `merge_regions` monkeypatched to force
   `report["converged"] = False`: the result is exactly the un-merged mesh (192 faces, `face_v`/
   `face_vt` identical to the input, `source_faces` all length-1 identity arrays),
   `merge_report["rolled_back"] is True`, `merge_report["rolled_back_reason"] == "not_converged"`,
   and the fallback's own guard still passes (identical geometry to the original).

The `ValueError` from decision 5 is covered by `test_edge_flicker_cap_above_zero_without_geometry_
is_an_error` in `engine/tests/test_guard.py` (see above), not `test_pipeline.py` -- it is a
`compare_views` contract, exercised directly against synthetic buffers, not through `fix_object`.

## Real-data check

`data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj`, `flatness =
{'mumi_littletiles_ltstone_-7': 3.04}`, default `FixProfile()` (`n_dirs=128`, `guard_size=(900,
600)`, `accept_slit=False`). Script:
`C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-MODEL-FIXER\5472478e-978d-426b-bab2-e7cf21699a70\scratchpad\task6_real_data_check.py`
(not part of the repo). Nothing was tuned to reach a number; this is the first and only run.

```
input faces: 4692
n_hidden_candidates: 1853
n_restored_by_guard: 34
n_removed_hidden: 1819
n_removed_slit: 0
n_zero_area_dropped: 217
faces before merge (removal only): 2656
faces after merge: 2062
final mesh.n_faces: 2062
merge converged: True
rolled_back: False
rolled_back_reason: None
invariants: {'material_count_same': True, 'bbox_same': True, 'area_not_grown': True, 'guard_passed': True}
passed: True
guard_after_removal totals: {'model_px': 2059414, 'holes': 0, 'material_changed': 0, 'moved_same_flat': 0, 'moved_other': 0, 'edge_flicker': 0}
guard_final totals (cap=1e-4): {'model_px': 2059414, 'holes': 0, 'material_changed': 0, 'moved_same_flat': 0, 'moved_other': 0, 'edge_flicker': 1}
guard_final.passed: True
hidden feedback history: [{'round': 0, 'candidates_remaining': 1853, 'failing_pixels': 223, 'restored': 34}, {'round': 1, 'candidates_remaining': 1819, 'failing_pixels': 0, 'restored': 0}]
slit feedback history: None

timing: read=0.023s fix_object=29.966s total=29.990s

expected: {'hidden_candidates': 1853, 'restored': 34, 'removed': 1819, 'zero_area': 217, 'faces_before_merge': 2656, 'faces_after_merge': 2062}
actual:   {'hidden_candidates': 1853, 'restored': 34, 'removed': 1819, 'zero_area': 217, 'faces_before_merge': 2656, 'faces_after_merge': 2062}
MATCH
```

**Exact match on every number given in the brief**, including the final guard's 0 holes / 0
material-changed / 0 moved (both classes) / 1 edge-flicker pixel, passing at `edge_flicker_cap =
1e-4` (the same single silhouette pixel the task-5 fix-round-2 report identified, view `(0.013,
-0.993, -0.989)`) -- no divergence to investigate, nothing tuned.

`fix_object` runtime: **29.97 s** (default `n_dirs=128`, `guard_size=(900,600)`, `max_rounds=8`
default). This is roughly hidden-guard (~12 s, per task-5's own measurement of the same feedback
loop) plus two more full 26-view `compare_views` passes at 900x600 with the sub-pixel coverage
probe (`guard_after_removal`, `guard_final`), each rebuilding an `EmbreeCaster` per view -- the
same "rebuild per view per round" cost documented as a known concern in the task-3/4 report, now
paid three times over (once inside `guard_feedback`, twice more for the two `compare_views` calls)
rather than once.

## Files changed

- `engine/guard/compare.py` (decision 5 hardening)
- `engine/tests/test_guard.py` (decision 5 tests, 3 existing tests updated/replaced)
- `engine/fixes/pipeline.py` (new)
- `engine/tests/fixtures/build.py` (added `gridded_box`; existing fixtures untouched)
- `engine/tests/test_pipeline.py` (fix_object tests appended; existing `engine.pipeline` tests
  untouched)

## Self-review

- No imports of `api`, `spike`, `fastapi`, `sqlalchemy` anywhere in `engine/` (grep, clean).
  `trimesh`/`embreex` appear only in `engine/rays/caster.py` and a docstring sentence in
  `engine/guard/views.py` saying they are never imported there (pre-existing, unchanged by this
  task).
- No random numbers in `engine/fixes/pipeline.py` or the new tests; the only `random` hits in
  `engine/` are pre-existing test-only RNGs in `test_caster.py`/`test_mtl.py`, both explicitly
  test-only and untouched.
- No vertex is moved or invented: `fix_object` never writes to `mesh.positions` (or any derived
  mesh's `positions`), and the recentred `positions_c` used for every render is a NEW array
  (`topo.positions_w - centre`), never written back into any `MeshData`.
- `guard_passed` / `passed` distinction: `invariants["guard_passed"] == guard_final.passed` always
  (by construction, no separate computation), and `passed = all(invariants.values())` -- verified
  in every fixture test and the real-data run that this equals `guard_final.passed` exactly,
  because `material_count_same`/`bbox_same`/`area_not_grown` are guaranteed by `remove_faces` and
  `merge_regions` never touching `materials`/`positions` and never growing area beyond float noise.

## Concerns

1. **Runtime.** ~30 s per `fix_object` call on the real model at default settings, dominated by
   three independent guard-render passes (the hidden `guard_feedback` loop, plus two whole-mesh
   `compare_views` calls) each rebuilding an `EmbreeCaster` per view. This is consistent with
   every prior task's own timing note on the same root cause (task-3/4's guard-feedback concern,
   now paid twice more); not changed here since caster reuse across rounds/calls is out of this
   task's scope and no number in the brief depends on it changing.
2. **The "against the original" reading for the slit pass (design decision 4 above) is my
   inference, not literal text.** The brief's short-form order predates the binding decisions that
   split hidden/slit into two passes, and decision 1 only says the slit pass runs "after the
   hidden pass." I read that as: pass 2's BEFORE state already excludes the confirmed-removable
   hidden faces (so a person accepting a slit-face removal is deciding against what the object will
   actually look like once hidden removal has run), not as "render the untouched original a second
   time." This has no effect on the real-data run (`n_removed_slit: 0`, `accept_slit=False` by
   default) and is exercised only by the fixture test.
3. **`passed = all(invariants.values())` vs "passed reflects the fallback's guard."** The brief's
   rollback sentence names `guard_final.passed` specifically. I AND it with the three other
   invariants for defence-in-depth (a real bug that grew total area or touched `materials` should
   not silently report `passed = True` because the guard alone was blind to it), but this is an
   addition beyond the literal text. In every fixture and the real-data run the other three
   invariants are always `True` by construction, so the two readings coincide everywhere tested; if
   the controller wants `passed` tied to `guard_final.passed` alone, deleting the `all(...)` call in
   favour of `guard_final.passed` is a one-line change.
4. **`FixResult`'s field set extends the brief's literal dataclass sketch** per decision 6's
   instruction to carry "counts... the feedback history... both guard reports... the merge
   report... the invariants dict... passed" -- none of the brief's five named fields
   (`exposure_class`, `removed_hidden`, `removed_slit`, `guard_after_removal`, `guard_final`) were
   dropped, but `n_hidden_candidates`/`n_restored_by_guard`/`n_removed_hidden`/`n_removed_slit`/
   `n_zero_area_dropped`/`feedback_history` are new, not in the brief's own two-line signature.

## Public signatures

```
engine/guard/compare.py

compare_views(before, after, face_material_before, face_material_after, flat_materials, depth_tol,
              strict=False, plane_before=None, plane_after=None, edge_flicker_cap=0.0,
              geometry_before=None, geometry_after=None, caster_factory=EmbreeCaster,
              allow_depth_fallback=False) -> GuardReport
    # NEW: raises ValueError when edge_flicker_cap > 0.0 and either geometry_before or
    # geometry_after is None -- without both, flicker rests on the 3x3 neighbourhood test alone,
    # which is only safe at cap 0.0. Everything else about the signature is unchanged from the
    # task-5 fix-round-2 report.
```

```
engine/fixes/pipeline.py

@dataclass
class FixProfile:
    n_dirs: int = 128
    slit_threshold: float = 0.05
    accept_slit: bool = False
    flat_texture_std: float = 8.0
    guard_size: tuple[int, int] = (900, 600)
    edge_flicker_cap_final: float = 1e-4

@dataclass
class FixResult:
    mesh: MeshData
    source_faces: list[np.ndarray]        # one int64 array per output face -> ORIGINAL face indices
    exposure_class: np.ndarray            # per ORIGINAL face, engine.vis.exposure's EXP_* codes
    removed_hidden: np.ndarray            # bool, over ORIGINAL faces
    removed_slit: np.ndarray              # bool, over ORIGINAL faces
    n_hidden_candidates: int
    n_restored_by_guard: int
    n_removed_hidden: int
    n_removed_slit: int
    n_zero_area_dropped: int
    feedback_history: dict                # {"hidden": history, "slit": history | None}
    guard_after_removal: GuardReport      # ORIGINAL vs post-removal (pre-merge) mesh
    guard_final: GuardReport              # ORIGINAL vs the mesh actually shipped (merged or rolled back)
    merge_report: dict                    # engine.fixes.merge's report, plus "rolled_back" /
                                          # "rolled_back_reason" ("not_converged" | "guard_failed")
                                          # when the merge candidate was discarded
    invariants: dict                      # material_count_same, bbox_same, area_not_grown, guard_passed
    passed: bool                          # all(invariants.values())

fix_object(mesh: MeshData, flatness: dict[str, float], profile: FixProfile = FixProfile()) -> FixResult
```

```
engine/tests/fixtures/build.py

gridded_box(n=4, cell=2.5, uv_per_unit=0.05) -> MeshData   # closed cube, n x n grid per face,
                                                            # 6 * 2 * n * n triangles total
```
