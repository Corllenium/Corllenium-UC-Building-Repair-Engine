# Engine round, 2026-09-23 — E1..E4

Branch `feat-dashboard`. Baseline before this round: `engine/tests` 164 passed; `git status` clean
apart from the untracked files belonging to another session (never staged, never touched).

Skill named up front: `superpowers:test-driven-development` (every item below is test-first) and
`superpowers:verification-before-completion` before any "done" claim.

---

## E1 — `fix(engine): degenerate faces are removed only through the strict guard`

Commit `9fa4fe5`.

### The defect

`engine/topo/adjacency.py::degenerate_mask` is RELATIVE:

```python
return area <= 1e-7 * np.maximum(longest, 1e-300) ** 2
```

so a 1,000-inch-long sliver up to 0.0002 in wide is "zero area" while being real, hittable
surface. `fix_object` dropped every such face unconditionally (`zero_area_full = ~topo.ok`, folded
straight into `drop`) with no guard check at all — while the removal guard's BEFORE render used
`topo.face_w[topo.ok]`, i.e. a *different*, sliver-free face set. Any pixel ray that hit a sliver
in the real BEFORE (which does use all faces, in `_guard_against_original`) saw a different
material behind it in AFTER. That is file B's `material_changed = 12`.

### The change (`engine/fixes/pipeline.py`)

* Every render in the function now casts against the SAME face set: all faces (`topo.face_w`,
  materials `mesh.face_material`). `ok_ids` / the `[topo.ok]` subsetting is gone.
* Pass-1 candidates = `(exposure_class == EXP_HIDDEN) | ~topo.ok`. `classify_exposure` gives every
  `not ok` face `EXP_DEGENERATE`, so the two halves are disjoint and `n_hidden_candidates` keeps
  its old meaning exactly.
* One `guard_feedback(..., strict=True)` over all faces; the surviving mask is split:
  `removed_hidden = removed & ok`, `removed_degenerate = removed & ~ok`,
  `restored_degenerate = ~ok & ~removed`.
* `n_zero_area_dropped` is now what was actually removed. New `n_degenerate_restored: int` and
  `restored_degenerate: np.ndarray` (bool over ORIGINAL faces) on `FixResult`; `report.json` gains
  `n_degenerate_restored`.
* The slit pass runs over the all-faces state pass 1 leaves (`~removed_pass1`).
* `drop = removed_hidden | removed_slit | removed_degenerate`. Everything downstream unchanged.
  `merge_regions` already copies through faces with `face_region < 0`, which is what a surviving
  degenerate face is, so no merge change was needed.

### TDD evidence

Tests written first, run, seen to fail, then implemented.

1. `test_a_genuinely_collinear_zero_area_face_is_still_removed` — `t_junction_strip()`'s
   `(0,10,0)-(10,10,0)-(20,10,0)` stitch has exactly zero area, is never a first hit, so the strict
   guard sees no changed pixel: `n_zero_area_dropped == 1`, `n_degenerate_restored == 0`.
2. `test_hidden_numbers_are_unchanged_by_a_zero_area_face_sharing_the_mesh` — the E1(c) regression
   check at fixture level. New fixture `box_with_partition_and_stitch()` adds a midpoint vertex on
   the cube's own `(0,0,0)-(10,0,0)` edge and stitches `(0, mid, 1)`. Asserts
   `(n_hidden_candidates, n_removed_hidden, n_restored_by_guard)` are byte-for-byte those of the
   stitch-free fixture `(2, 2, 0)`, the stitch is never counted as hidden, and both runs ship 12
   faces.
3. `test_a_sliver_that_only_the_relative_test_calls_zero_area_is_kept_by_the_guard` — new fixture
   `floor_with_sliver()`: a 1,200x1,200 floor quad (material 0) at z=0 with a 1,000 x 0.0001 in
   triangle (material 1) floating 5 in above it. Area 0.05 vs the threshold
   `1e-7 * 1000**2 = 0.1`, so `degenerate_mask` calls it zero-area. `coord_decimals=6` keeps the
   width from being welded away (a new keyword on the `_mesh` fixture helper).

   The test computes the camera from `ortho_first_hit`'s own framing code for the fixture's
   `frame_points`, picks the centre pixel, solves where that pixel's ray crosses the sliver's
   plane, and rebuilds the fixture with its apex/centre line exactly there — then asserts the
   camera is byte-identical to the placeholder one (so the aim is valid) and that
   `before.tri[row, col] == 2`, i.e. the sliver IS hit in BEFORE. After `fix_object`:
   `n_degenerate_restored == 1`, `restored_degenerate == [F, F, T]`, `n_zero_area_dropped == 0`,
   `guard_after_removal.passed`, and exactly one face of material 1 in `result.mesh`.

### One finding worth keeping

The first attempt aimed at the VIEWS_26 entry with the most negative z — which is
`(-0.987, -0.993, -0.989)`, the corner diagonal, not straight down (both have z = -0.989). It
missed, and `BruteCaster` hit the same pixel while `EmbreeCaster` did not. Cause: embree takes ray
origins as float32 and `ortho_first_hit` stands the camera off by `2 * diag` (~3,400 here), so on a
corner-diagonal view all three origin components are ~2,000 and lateral position quantises to
~1.2e-4 — wider than the sliver. Straight down, only the z component is large (and z error slides
along the ray, not across it) while x/y are ~40, quantised to ~4e-6. The test now selects the view
closest to `(0, 0, -1)` and says why in its docstring.

This also explains the real file: a *maximally* degenerate sliver is at best ~0.8 of a float32
quantum of the ray origin wide, which is why file B produced only 12 offending pixels out of
540,000 x 26 rather than a solid band. The ratio is scale-invariant, so it cannot be tuned away —
it is a property of the relative degeneracy threshold against float32 ray origins.

### Suite after E1

`167 passed` (164 baseline + 3 new).

---

## E2 — `fix(engine): boundary-shift tolerance becomes a ring test at the merge's own bound`

Commit `332fa70`.

### The defect

`PX_EDGE_FLICKER` needed (1) a miss in the pixel's 3x3 BEFORE neighbourhood and (2) a sub-pixel
coverage change of at most 2/25 over a 5x5 axis-aligned sub-ray grid. Both halves assume the
shifted boundary has SKY on one side, so the rule only ever worked at the model's OUTER silhouette;
and a 5x5 axis-aligned grid flips whole columns of 5 at once for a straight boundary. File A's
merge converges to 1,894 triangles and is then rolled back over ONE pixel (view
`(-0.987, 0.007, -0.989)`, pixel `(530, 338)`) classed `moved_same_flat`, where the boundary of a
merged region moved by at most the collinearity tolerance (`1.5 * max(axis quanta)` = 0.15 in) and
the ray met an adjacent stair region 16.3 in closer — an INTERNAL silhouette, with no background
anywhere near it.

### The change (`engine/guard/compare.py`, `engine/guard/views.py`)

Applied to EVERY would-be failure pixel — hole, `moved_same_flat`, `moved_other`,
`material_changed` — not only to holes:

* Cast 16 rays around the pixel's own ray, offset in the IMAGE PLANE: 8 at radius `depth_tol` and
  8 at `depth_tol / 2`, at k*45 degrees, in BOTH geometries, from the same camera frame
  (`HitBuffers.ring_origins`, replacing `subpixel_origins`; `_ring_probe` in compare.py; all ray
  casting still goes through the `engine.rays.caster` interface).
* The pixel is `PX_EDGE_FLICKER` iff **(1)** at least one AFTER ring ray reproduces BEFORE's centre
  verdict AND **(2)** at least one BEFORE ring ray reproduces AFTER's. "Reproduces" = a hit whose
  point lies within `depth_tol` of the centre-hit face's plane with the same material, or a miss
  when the centre was a miss (`_ring_reproduces`). Otherwise the original failure class stands.
* Radii are in WORLD units, so the rule is independent of image resolution — the question it
  answers is geometric.
* Both halves are required, so a surface that really vanished (1 fails) or really appeared (2
  fails) still fails.
* `_neighbour_miss`, `_coverage_probe`, `_FLICKER_GRID`, `_FLICKER_COVERAGE_TOL`,
  `HitBuffers.subpixel_origins` and the now-unused `_pitch` are deleted.
* `classify_pixels` keeps its public signature except `coverage=` → `ring=`; it is now a thin
  wrapper over a private `_classify` that also returns the BASE codes, so `compare_views` can report
  the breakdown without measuring displacement twice.
* `ViewVerdict` and `totals` gain `edge_flicker_hole`, `edge_flicker_moved`,
  `edge_flicker_material`, which sum to `edge_flicker`; `report.json`'s per-view dicts carry them.
* Lookup tables for the ring are padded with one row so a `-1` (miss) reads material `-1` and an
  all-zero (undefined) plane rather than wrapping — and an empty geometry stays safe.
* One real bug fixed in passing: `mat_before`/`mat_after` were only filled where BOTH sides hit, so
  a would-be hole had material `-1`. The ring test needs BEFORE's material at a hole, so they are
  now filled for every hit pixel. `material_changed` is still `both & (mat_before != mat_after)`,
  unchanged.

### `edge_flicker_cap` semantics — unchanged, deliberately

* `guard_feedback` casts **no ring at all**. At its cap of 0.0 a flicker pixel fails exactly like
  the class it came from, so not classifying is the identical outcome — and it saves 16 rays per
  failing pixel per round. Removals can never hide behind this rule.
* The final merge guard still uses `FixProfile.edge_flicker_cap_final` (1e-4), judged per view
  against that view's `model_px`.
* `edge_flicker_cap > 0.0` without both geometries still raises `ValueError` (there is no ring to
  cast, so the cap would tolerate nothing while looking as though it tolerated something).

### TDD evidence

Written first, run, seen to fail on the classification (their scene-construction assertions passed
from the start), then implemented.

* `test_boundary_shift_under_tolerance_at_an_internal_silhouette_is_edge_flicker` — new
  `_stacked()` scene: a lower slab at z=0 under an upper slab at z=10 covering `x <= edge_x`,
  viewed straight down, so the edge is an internal silhouette with no background anywhere in the
  image. The upper slab is 0.8 of a pixel tall and the edge moves 0.1 in (< the 0.15 `depth_tol`)
  straddling one chosen pixel centre, so exactly ONE pixel swaps — deterministic by construction,
  asserted. Result: `edge_flicker == 1`, `edge_flicker_moved == 1`, `moved_same_flat == 0`,
  `passed False` at cap 0.0 and `passed True` at cap 1e-4 (model_px ~13,700, so 1e-4 tolerates one).
  The OLD rule could never reach this pixel.
* `test_a_material_boundary_shift_under_tolerance_is_edge_flicker_material` — same scene, upper
  slab in material 1: base class `material_changed`, so `edge_flicker_material == 1`, tolerated at
  cap 1e-4 and failing at cap 0.0.
* `test_a_boundary_shift_far_beyond_tolerance_stays_a_failure_at_any_cap` — the same edge moved
  2 in (> `2 * depth_tol`), full-height slab: >100 swapped pixels, `edge_flicker == 0`,
  `moved_same_flat` == every one of them, `passed False` at caps 0.0, 1e-4 and 1.0.
* `test_a_removed_face_beside_a_pre_existing_gap_is_a_hole_at_any_cap` (existing, the "removed strip
  wider than `2 * depth_tol`" case) — unchanged and still passing: no AFTER ring ray can reach the
  removed strip's plane, so (1) fails and every pixel stays a hole.
* `test_a_thousandth_of_an_inch_of_boundary_shift_is_edge_flicker` (existing, EXTERNAL silhouette)
  — kept, with its rationale rewritten to the ring rule and strengthened with the breakdown
  (`edge_flicker_hole == 1`) and the per-view verdict.
* `test_silhouette_pixel_is_classed_edge_flicker_and_fails_at_cap_zero` → rewritten as
  `test_a_would_be_hole_is_never_flicker_without_the_geometry_to_ring_test_it`. The old test fed
  synthetic buffers with no geometry and relied on the 3x3 precondition alone; under the new rule
  the honest statement is that without geometry nothing is ever flicker — which is exactly the
  property `guard_feedback` depends on. Nothing it protected was weakened: the "fails at cap 0.0"
  assertion moved into the real-geometry external test above.
* `test_identity_all_counts_zero_and_passed` — totals dict equality extended with the three new
  keys.

### Suite after E2

`170 passed`.

---

## E3 — `test(engine): pipeline rollback on guard failure and post-removal guard assertions`

Commit `7e5b02f`. Tests only; no production change.

* `test_rolled_back_when_the_final_guard_fails_and_guard_final_is_the_shipped_mesh` —
  `merge_regions` is monkeypatched to return a CONVERGED merge whose mesh has lost one visible face
  (`remove_faces` on the real merged mesh, `source_faces` subset to match). Asserts
  `merge_report["converged"] is True`, `rolled_back is True`,
  `rolled_back_reason == "guard_failed"`, the shipped mesh is exactly the flipped-but-unmerged one
  (192 faces, `face_v` identical to the input, `source_faces == [[i]]`, `rings == {}`), and that
  `guard_final` describes THAT mesh: `passed is True` with every total zero.

  Verified non-vacuous, measured in the same session: the DISCARDED candidate's own guard reports
  `passed = False, {holes: 0, material_changed: 0, moved_same_flat: 9612, moved_other: 0,
  edge_flicker: 0}` over the same 131,484 model pixels. (A closed box loses a half-side to a
  "moved" region rather than to holes, because the ray then reaches the opposite inner wall.) So
  the all-zero assertion genuinely separates the shipped mesh from the candidate.
* `test_guard_after_removal_is_spotless_on_box_with_partition` — `guard_after_removal.passed` and
  every total zero (per view as well as in aggregate, all 26 views), including the new flicker
  breakdown, after the two sealed partition triangles are removed.

### Suite after E3

`172 passed`.

---

## E4 — `chore(engine): re-run fixes on both real files, refresh preview data`

**No commit.** `git diff HEAD -- engine/` is empty after E4: the outputs under `data/` and
`preview/data/` are git-ignored and nothing under `engine/` changed, so per the brief that commit
is skipped.

All six commands run, in order, all succeeding (`engine.cli fix` returns 2 when `passed` is False,
which is its documented contract, not a crash):

```
python -m engine.cli fix data/snapshots/ce26e0392ab0 --out data/output                            40.9 s
python -m engine.cli fix data/snapshots/0b290ec0bcb4 --out data/output                            55.1 s
python -m engine.cli fix data/snapshots/ce26e0392ab0 --accept-slit --out data/output_accept_slit  48.2 s
python -m engine.cli fix data/snapshots/0b290ec0bcb4 --accept-slit --out data/output_accept_slit  48.6 s
python -m engine.cli preview-data data/snapshots/ce26e0392ab0 --out preview/data                  36.6 s
python -m engine.cli preview-data data/snapshots/0b290ec0bcb4 --out preview/data                  37.4 s
```

### File A — `CHTM_SIDE_WALK_2nd_floor`, default

```
hidden candidates / restored / removed : 1853 / 34 / 1819
degenerate removed / restored          : 217 / 0
flipped / thin sheets                  : 844 / 47
one_sided_holes before / after         : 570046 / 116041
triangles before / after               : 4692 / 2656
merge                                  : 2656 -> 1894, 169 regions, converged=True,
                                         rolled_back=True, reason="guard_failed"
guard_after_removal                    : passed=True, every total 0 (model_px 2,059,414)
guard_final (of the SHIPPED mesh)      : passed=True, every total 0
                                         (edge_flicker 0 / hole 0 / moved 0 / material 0)
invariants                             : all True.   passed: True
feedback (hidden)                      : r0 2070 cand, 223 failing px, 34 restored;
                                         r1 2036 cand, 0 failing px
```

Every one of the brief's known numbers matches exactly: 1,853 / 34 / 1,819 hidden, 217 zero-area,
844 flipped, merge 1,894 before rollback.

### File A — `--accept-slit`

```
hidden candidates / restored / removed : 1853 / 34 / 1819
slit removed                           : 163   (feedback: r0 164 cand, 3 failing px, 1 restored)
degenerate removed / restored          : 217 / 0
flipped / thin sheets                  : 761 / 47
one_sided_holes before / after         : 570046 / 116874
triangles before / after               : 4692 / 2493
merge                                  : 2493 -> 1731, 137 regions, converged=True,
                                         rolled_back=True, reason="guard_failed"
guard_after_removal                    : passed=False, {holes 0, material_changed 0,
                                         moved_same_flat 991, moved_other 0,
                                         edge_flicker 15 (hole 0 / moved 15 / material 0)}
guard_final                            : identical totals, passed=False
invariants                             : guard_passed False.   passed: False
```

### File B — `CHTM_2nd_to_3rd_building_sidewalk_outside`, default

```
hidden candidates / restored / removed : 2411 / 30 / 2381
degenerate removed / restored          : 79 / 0
flipped / thin sheets                  : 842 / 103
one_sided_holes before / after         : 465146 / 90543
triangles before / after               : 7227 / 4767
merge                                  : 4767 -> 1282, 93 regions, converged=True,
                                         rolled_back=True, reason="guard_failed"
guard_after_removal                    : passed=False, {holes 0, material_changed 11,
                                         moved_same_flat 0, moved_other 0,
                                         edge_flicker 1 (hole 0 / moved 0 / material 1)}
                                         all 12 in ONE view, (1.013, 1.007, 0.011), model_px 25,586
guard_final                            : identical totals, passed=False
invariants                             : guard_passed False.   passed: False
feedback (hidden)                      : r0 2490 cand, 436 failing px, 30 restored;
                                         r1 2460 cand, 12 failing px, 0 restored
```

Known numbers match exactly: 2,411 / 30 / 2,381 hidden, 79 zero-area, 842 flipped, merge 1,282
before rollback.

### File B — `--accept-slit`

```
slit removed                           : 181   (feedback: r0 193 cand, 155 failing px, 12 restored)
flipped                                : 758
one_sided_holes before / after         : 465146 / 90977
triangles before / after               : 7227 / 4586
merge                                  : 4586 -> 1139, 72 regions, converged=True,
                                         rolled_back=True, reason="guard_failed"
guard_after_removal / guard_final      : passed=False, {holes 0, material_changed 11,
                                         moved_same_flat 424, moved_other 0,
                                         edge_flicker 3 (hole 0 / moved 2 / material 1)}
invariants                             : guard_passed False.   passed: False
```

### Difference 1 — file B's 12 pixels are NOT the slivers; the brief's diagnosis was wrong

E1 is implemented exactly as specified, and `n_degenerate_restored == 0` on file B: the strict
guard confirmed all 79 degenerate faces removable. 11 `material_changed` + 1
`edge_flicker_material` remain, in the same view the brief names.

The feedback loop says why it could not fix them: round 1 ends with **12 failing pixels and 0
restored** — it stops because `restore` is empty, i.e. the BEFORE first-hit face at those pixels is
not a removal candidate at all. Measured, per pixel (snapshot re-loaded and `guard_feedback`
re-run at the production 900x600 profile):

```
px(245,207) BEFORE face 2654 mat=1 t=5867.727923 ok=True removed=False | AFTER face 73 mat=0
            t=5867.727923  dt=0
... 11 more: BEFORE face 2654 or 2655 (mat 1), AFTER face 73 (mat 0), every one dt == 0 ...
```

`dt == 0` to the last bit, and faces 2654/2655 are `ok=True` (NOT degenerate) and were restored by
the guard in round 0 — so **both** faces are present in **both** renders. This is two exactly
coincident triangles of different materials (duplicated coplanar geometry in the SketchUp export),
and which one embree returns from `intersects_location(multiple_hits=False)` depends on the BVH,
which differs because the AFTER geometry has 2,460 fewer faces. It is a coincident-surface
tie-break, not lost or changed geometry, and no amount of removal-guard feedback can fix it:
there is no candidate to restore.

So the brief's stated cause ("these 79 faces are dropped with no guard check ... pixel rays that
hit a sliver in BEFORE see a different material behind it in AFTER") does not hold for these 12
pixels. E1 is still right on its own terms — it closes a real hole in the guard, proved by the
sliver fixture test — but it was never going to move file B's number, and it did not (12 -> 11+1,
the 1 being the ring test rescuing one boundary pixel of the same cluster). **Nothing was tuned.**

### Difference 2 — file A's merge still rolls back; the ring test correctly refuses that pixel

This matches the brief's own known numbers ("merge 1,894 before rollback"). The merge candidate's
guard is now:

```
compare_views #1 (the merge candidate, cap 1e-4): passed=False
  {holes 0, material_changed 0, moved_same_flat 1, moved_other 0,
   edge_flicker 1 (hole 1 / moved 0 / material 0)}
  view (-0.987, 0.007, -0.989), model_px 101,972 : moved_same_flat 1   <- the failure
  view ( 0.013, 1.007,  1.011), model_px 107,441 : edge_flicker 1      <- tolerated (1 <= 10.7)
```

I measured the 16 ring rays at that exact pixel (530, 338):

```
BEFORE centre: face 2540, t=3318.6637, plane [-0.14648, 0, 0.98921, 24.4795]
AFTER  centre: face  938, t=3302.3477, plane [-0.14656, 0, 0.98920, 14.7953]   (16.32 in nearer)
|n . d| = 0.597 for both -> the two surfaces are PARALLEL, 9.68 in apart

condition (2)  BEFORE ring -> AFTER's centre plane : all 16 rays hit faces 2577/2579 at
               distance 0.0020 from plane_after            -> SATISFIED (0.0020 <= 0.15)
condition (1)  AFTER  ring -> BEFORE's centre plane: all 16 rays hit face 938 at
               distance 9.7359 from plane_before           -> FAILS     (9.7359 >> 0.15)
```

So this pixel is not a boundary that merely shifted between two surfaces. In BEFORE the far surface
is visible only within a radius smaller than `depth_tol / 2` of that pixel — a sub-0.15 wedge of
the lower ramp peeking out at a grazing angle — and in AFTER the merge closed that wedge entirely:
the far surface is nowhere within the ring. Condition (1) is the half of the rule that refuses to
tolerate a surface which really vanished, and it is doing its job. The rule is implemented exactly
as briefed (radii `depth_tol` and `depth_tol / 2`, 8 angles at k*45 degrees, image plane, both
geometries, one camera frame); 9.74 against 0.15 is a factor of 65, so this is not a
floating-point edge case. **Nothing was tuned.**

### Difference 3 (REGRESSION) — file A `--accept-slit` went from passing to failing

| | previous round | this round |
|---|---|---|
| `n_removed_slit` | 163 | 163 |
| merge candidate | 1,731 tris, kept | 1,731 tris, **rolled back** |
| `tris_after` (shipped) | 1,731 | **2,493** |
| `guard_final` | passed=True, `{moved_same_flat: 1008, edge_flicker: 1}` | passed=False, `{moved_same_flat: 991, edge_flicker: 15}` |

Cause, measured exactly:

```
strict_final = not (accept_slit and n_removed_slit > 0) = False
  -> the 991 moved_same_flat pixels cost nothing (that is the whole point of --accept-slit)
  -> but edge_flicker is still judged against edge_flicker_cap_final * model_px, PER VIEW
FAILING view (0.013, -0.993, 0.011): model_px 9,291, cap*model_px = 0.93, edge_flicker = 7
total failing pixels = 7  ->  passed = False
```

Seven of the ~1,008 previously-tolerated `moved_same_flat` pixels were reclassified as
`edge_flicker_moved` by the new rule, and they happen to sit in the smallest view of the set
(9,291 model px, so a 1e-4 cap allows less than one pixel). Under a NON-strict guard, promoting a
pixel from `moved_same_flat` to `edge_flicker` makes the report **stricter**, not laxer — the
opposite of what the flicker class is for.

That follows directly from the brief ("applied to EVERY would-be failure pixel ...
`moved_same_flat` ... not only to holes", plus "keep `edge_flicker_cap` semantics exactly"), so I
implemented it as written and did not change the pass/fail arithmetic to hide it. The narrow fix,
if the reviewer wants it, is one line in `compare_views`: count a view's flicker pixels as failures
only when the class they came FROM would itself have failed — i.e. ignore `edge_flicker_moved`
pixels whose base class was `PX_MOVED_SAME_FLAT` when `strict` is False. The breakdown fields this
round adds are exactly what that needs, but it changes what `passed` means, so it is not mine to
decide unilaterally.

### Determinism

`fix data/snapshots/ce26e0392ab0` run a second time into a scratch directory produced a
byte-identical `report.json`, `.fixed.obj`, `.fixed.ngon.obj` and both guard PNGs (`cmp -s`, all
five IDENTICAL). No random numbers anywhere in the new code: the ring is `k * 45 degrees` at two
fixed radii.

### Guard images

Only the six axis triptychs are written (`engine.cli._AXIS_VIEWS` keeps the `VIEWS_26` entries with
exactly one non-zero rounded component), so **there is no oblique guard PNG to open** — including,
unfortunately, for file B's offending corner view `(1.013, 1.007, 0.011)`. I opened the `+z` one
the brief names and a second axis view instead.

* `data/output/CHTM_SIDE_WALK_2nd_floor/guard_+z.png` — looking down on the walkway: the BEFORE
  panel is blotched light and dark across the big slab and the ramp (each blotch a run of triangles
  whose winding faces away from the camera), the AFTER panel shows the same plan silhouette in one
  even tone once 844 faces are flipped and 1,819 removed, and the DIFF panel is uniformly pale with
  no red and no amber anywhere — the all-zero `guard_final` for this run, in picture form.
* `data/output/CHTM_SIDE_WALK_2nd_floor/guard_-x.png` — the same object edge-on from -x, showing
  the stepped ramp descending to the lower pad: BEFORE is again streaked with mis-wound bands along
  the deck and the stair treads, AFTER is evenly shaded, and the DIFF panel is again completely
  clean.

---

## Public signatures

(only what changed this round; everything else is unchanged from the last `## Public signatures`
section of `task-7-8-9-report.md`)

```
engine/fixes/pipeline.py

@dataclass
class FixResult:
    # ... unchanged fields ...
    n_zero_area_dropped: int          # MEANING CHANGED: how many degenerate faces the strict
                                      # guard CONFIRMED removable, not how many there were
    n_degenerate_restored: int        # NEW
    restored_degenerate: np.ndarray   # NEW: bool over ORIGINAL faces -- degenerate faces the
                                      # guard put back, which stay in the shipped mesh
    # (both inserted immediately after n_zero_area_dropped, before `flipped`)

fix_object(mesh, flatness, profile=FixProfile()) -> FixResult   # signature unchanged
    # pass 1 candidates are now (exposure_class == EXP_HIDDEN) | ~topo.ok, guarded over ALL faces

FixProfile   # unchanged
```

```
engine/guard/compare.py

_RING_ANGLES = 8    # replaces _FLICKER_GRID / _FLICKER_COVERAGE_TOL, both removed

classify_pixels(before_depth, before_tri, after_depth, after_tri, material_before, material_after,
                flat_materials, depth_tol, *, origins=None, direction=None, plane_before=None,
                plane_after=None, ring=None, allow_depth_fallback=False) -> np.ndarray
    # `coverage=` -> `ring=`. `ring(mask)` returns
    # (tri_before (P,16), point_before (P,16,3), tri_after (P,16), point_after (P,16,3)).
    # No ring (or no planes) => no pixel is ever PX_EDGE_FLICKER.

@dataclass
class ViewVerdict:
    view; model_px; holes; moved_same_flat; moved_other; material_changed; edge_flicker
    edge_flicker_hole: int       # NEW
    edge_flicker_moved: int      # NEW
    edge_flicker_material: int   # NEW  (the three sum to edge_flicker)

compare_views(...) -> GuardReport   # signature unchanged; `totals` gains the same three keys
guard_feedback(...) -> (mask, history)   # signature and results unchanged (casts no ring)
face_planes(...)   # unchanged

# removed: _neighbour_miss, _coverage_probe
```

```
engine/guard/views.py

class HitBuffers:
    def ring_origins(self, rows, cols, radii, n_angles=8) -> np.ndarray   # NEW
        # (len(rows) * len(radii) * n_angles, 3); concentric rings in the IMAGE plane around each
        # pixel's own ray, radii in WORLD units, pixel-major then radius then angle.
    # removed: subpixel_origins  (and the module-private _pitch helper)
```

```
engine/cli.py

_view_verdict_dict(v)   # now also emits edge_flicker_hole / _moved / _material
_build_report(...)      # report.json gains "n_degenerate_restored"
# no signature changes
```

```
engine/tests/fixtures/build.py

_mesh(name, positions, uvs, face_v, face_vt, materials=("m0",), face_material=None,
      coord_decimals=2, sig_digits=6)          # two new keyword args, defaults unchanged
box_with_partition_and_stitch(size=10.0) -> MeshData    # NEW
floor_with_sliver(apex_x=0.0, centre_y=0.0, half_width=5e-5, half_len=500.0,
                  half_floor=600.0, height=5.0) -> MeshData   # NEW
```
