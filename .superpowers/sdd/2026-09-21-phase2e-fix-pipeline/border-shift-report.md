# Border shift: the merge guard measures instead of counting

Commit `022a67b` on `feat-dashboard` (parent `e57462d`):
`fix(engine): the merge guard measures border shifts instead of counting them`.
The commit body adds a short explanation under that subject line. The trailer is
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

Staged by name: `engine/guard/compare.py`, `engine/fixes/merge.py`, `engine/fixes/pipeline.py`,
`engine/cli.py`, `engine/tests/test_guard.py`, `engine/tests/test_pipeline.py`,
`engine/tests/test_cli.py`, `preview/index.html`. `docker-compose.yml` (another session's work) and
the 19 untracked files were not touched, and they are still modified/untracked after the commit.

Engine suite, run fresh before the commit:
`.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider` -> **`337 passed in 44.10s`**
(baseline at e57462d: 322 passed; the 15 new test items are listed below).

## What changed

### `engine/guard/compare.py`
- A new pixel code, `PX_BORDER_SHIFT = 9`.
- `compare_views(..., border_shift_tol: float = 0.0)`. When the tolerance is above 0.0 and
  `geometry_before` or `geometry_after` is missing, it raises a `ValueError` that names
  `border_shift_tol` and the geometry. This works like the existing flicker-cap check.
- The measurement runs in `_classify` as the last step, after the ring. It follows the same
  "probe" pattern as the ring and tie tests: `compare_views` builds `_border_probe(geometry_before,
  geometry_after, tol)` once per call, and `classify_pixels` takes it as `border=`. Only pixels
  classed `PX_EDGE_FLICKER` whose BASE class is `PX_HOLE`, `PX_MOVED_SAME_FLAT` or
  `PX_MOVED_OTHER` are measured. Material-change flicker is never measured.
  - **Disappeared** means AFTER missed, or `t_after > t_before`. The distance is taken from
    BEFORE's hit point to the nearest AFTER triangle.
  - **Appeared** covers every other case (AFTER nearer, or BEFORE missed). The distance is taken
    from AFTER's hit point to the nearest BEFORE triangle.
  - A pixel with distance `<= tol` becomes `PX_BORDER_SHIFT`. Any other measured pixel stays
    `PX_EDGE_FLICKER`, and the per-view cap applies to it exactly as before.
- `_point_triangle_distance` gives the exact point-to-triangle distance. It uses the perpendicular
  where the foot lands inside the triangle, and otherwise the nearest point on the three edge
  segments. A zero-area triangle therefore counts as its edges.
- `_nearest_triangle_distance` searches every triangle of the other mesh, in any plane. It is
  brute-force numpy behind an axis-aligned bounding-box prefilter expanded by the tolerance, and
  works in blocks of 4,000,000 point x triangle pairs. `np.minimum.at` makes it deterministic. It
  adds no new dependency and does not use trimesh.
- `ViewVerdict.border_shift` is a new last field, and `totals["border_shift"]` is a new key. The
  count is always reported, never counts as a failure and is never capped. Because re-classed
  pixels leave `PX_EDGE_FLICKER`, they drop out of `edge_flicker` and its
  hole/moved/material breakdown automatically.
- The `classify_pixels` docstring gains two sections. "THE BORDER-SHIFT MEASUREMENT" describes
  the class and how it is measured. "WHY A MEASUREMENT AND NOT A COUNT" explains two things:
  - the ring works in the image plane, so it cannot say how far anything moved;
  - a count measures how many pixel centres an edge crosses, not how far the edge moved.

  The file A numbers it quotes are the ones measured below. The `compare_views` docstring
  describes `border_shift_tol`, the `ValueError`, and the fact that `passed` ignores
  `border_shift`.

### `engine/fixes/merge.py`
- A new shared helper, `default_collinear_tol(quanta) -> RING_TOL_QUANTA * max(quanta)`.
  `merge_regions` now uses it for its default, with no change in behaviour: the existing
  `test_merge` equivalence test, default versus explicit `1.5 * max(quanta)`, still passes.

### `engine/fixes/pipeline.py`
- `border_shift_tol = min(default_collinear_tol(topo3.quanta), profile.depth_tol_max)`. This is the
  same derivation `merge_regions(mesh_overlapped, topo3, ...)` has just used. The number is not
  written out a second time.
- `_guard_against_original` takes the tolerance explicitly:
  - `guard_after_removal`: `(cap 0.0, border_shift_tol 0.0)`;
  - `guard_merge_attempt`: `(edge_flicker_cap_final, border_shift_tol)`;
  - `guard_final` on a rollback: `(edge_flicker_cap_final, border_shift_tol)`.
- `guard_feedback`, `fragment_feedback` and `solidify_feedback` never build a border probe, so
  they stay at 0.0 by construction.

### `engine/cli.py`: two lines, kept minimal for the `feat/skp-export` merge
- The guard line reads
  `CHTM_SIDE_WALK_2nd_floor: 4692 -> 1117 tris, passed=True, border_shift=59`. The count comes
  from the final guard.
- `preview-data` writes a new stats key, `"guard_border_shift_px"`. The page cannot show a
  number that preview-data does not write, and the existing
  `test_preview_data_writes_every_stat_and_edge_list_the_page_reads` enforces this.
- `report.json` carries the count through `totals` of every guard with no other change. The
  per-view dicts (`_view_verdict_dict`) were deliberately left alone (see Concerns).

### `preview/index.html`
- The new count sits right after the flicker count:
  `59 border-shift px: tolerated sub-tolerance border movement (each one measured within the
  merge's own border tolerance, never capped)`.
- The flicker label's parenthetical was reworded from "a boundary that moved less than the
  tolerance" to "a boundary the ring could not rule out, capped per view". The old wording now
  describes border shift, not the flicker that remains. The substring "flicker px tolerated",
  which the existing test checks, is kept.
- Verified in the Browser pane at `http://localhost:5180/` with file A selected. The `#honest`
  header reads "... 0 damaged px of 2,058,592 (0.000 %). 0 flicker px tolerated (...) · 59
  border-shift px: tolerated sub-tolerance border movement (...) · ... · merge kept." The AFTER
  pane reads "1,117 triangles · 76.2 % fewer than exported · 177 flat regions".

## TDD record

**RED.** All tests were written first. Run against the unchanged engine, 16 items failed, each for
the intended reason:
- `TypeError: compare_views() got an unexpected keyword argument 'border_shift_tol'` (8 guard
  items);
- `AttributeError ... _nearest_triangle_distance` (1 item);
- the pipeline spies saw `(0.0001, 0.0)` where they expected `(0.0001, tol)` (3 items);
- the guard line had no `border_shift=` (1 item);
- `KeyError: 'guard_border_shift_px'` (1 item);
- the page substring was missing (1 item);
- the updated identity test was missing the `border_shift` key (1 item).

The row-aligned tests first confirmed their premise against today's code before reaching the new
keyword: 74 px, every one promoted to flicker. The grazing and head-on strip tests pass the keyword
on their first call, so a scratch script checked their premise against today's code separately:
- grazing lost strip: 74 px, all `edge_flicker_hole`;
- head-on lost strip: 148 plain holes, 0 flicker;
- grazing growth: 74 px, all `edge_flicker_moved`.

**GREEN.** `test_guard.py` passed 59/59 after the `compare.py` change, then the whole suite
passed 337/337.

The tests:

| test | what it pins |
|---|---|
| `test_a_border_moved_a_hundredth_of_an_inch_along_a_pixel_row_is_a_border_shift` | A plate's top edge lies exactly along pixel row 64 of a fixed `_FRAME` camera, 0.005 in above and below the row's pixel centres, so the whole 74-px run flips. The test first asserts `edge_flicker == edge_flicker_hole == 74` and `passed False` at cap 0 and tol 0 (the pixels really reach the ring). It also asserts a fail at cap 1e-4, since 74 px is more than 1e-4 x model_px. At tol 0.15: `border_shift == 74`, `edge_flicker == 0` and passed at cap 0. At explicit tol 0.0 the totals are identical to today's. |
| `test_an_internal_border_moved_...[retreats]` / `[advances]` | The same 0.01 in at an internal silhouette (plate 10 in over a floor). Base class is a move, and both the "disappeared" and "appeared" branches are exercised: 74 flicker-moved px become 74 border-shift px and the view passes. |
| `test_a_two_inch_strip_lost_at_a_border_still_fails_where_the_ring_calls_it_flicker` | Seen 1 degree off the plate, the ring's 0.15 in image-plane radius spans 8.6 in of surface. The 2 in lost strip therefore does reach flicker (74 px). Measured, the displacement is 1.9 in, so at tol 0 and tol 0.15 there are 74 flicker px, 0 border shift, and the view fails. |
| `test_a_two_inch_strip_lost_at_a_border_is_a_hole_even_beside_the_new_edge` | Head-on, the 2 in loss gives 148 holes and 0 flicker. Row 64 sits 0.05 in from the new edge, so a rule that measured every failing pixel would have excused it. Only flicker is measured, so it stays a hole. |
| `test_a_surface_appearing_an_inch_beyond_its_border_still_fails_where_the_ring_calls_it_flicker` | A plate 1 in over a floor grows 1 in, seen at grazing incidence. This gives 74 flicker-moved px measured at 0.9 in, so they stay flicker and the view fails at either tolerance. |
| `test_a_material_change_is_never_measured_away_as_a_border_shift` | `_stacked_pair(0.1, upper_material=1)` stays `edge_flicker_material == 1` with `border_shift 0` and fails. The same shift in one material gives `border_shift 1` and passes. |
| `test_border_shift_tol_above_zero_without_both_geometries_is_an_error` | A `ValueError` for no geometry and for only `geometry_before`. Tolerance 0.0 needs neither. |
| `test_the_border_shift_distance_is_exact_and_blind_to_which_plane_a_triangle_lies_in` | Checks the helper directly: interior perpendicular 3, beside an edge 4 (its plane would say 0), past a corner 5, past the hypotenuse sqrt 2, a collinear triangle 3. A perpendicular WALL 1 in away beats a coplanar triangle 4.9 in away, and a point out of reach returns `inf`. |
| `test_pipeline::test_the_merge_guard_measures_border_shifts_at_the_merges_own_tolerance` | A `compare_views` spy on `box_with_partition` sees exactly `[(0.0, 0.0), (1e-4, min(1.5 * max quanta, 0.5))]`. The removal guard gets tolerance 0.0. |
| `test_pipeline::test_the_guard_of_a_rolled_back_run_measures_border_shifts_too` | A forced rollback gives `[(0,0), (1e-4, tol), (1e-4, tol)]`: the final guard of the fallback gets the tolerance too. |
| `test_pipeline::test_a_coarse_precision_export_cannot_excuse_a_border_shift_wider_than_depth_tol_max` | With survey coordinates, `collinear_tol` is 1.5 in and the merge guard gets 0.5; the removal guard gets 0.0. |
| `test_cli::test_cmd_fix_prints_the_final_guards_border_shift_count` | The guard line carries `border_shift=17` and report.json totals carry 17 (patched totals). |
| `test_cli::test_preview_data_reports_the_final_guards_border_shift` | `stats["guard_border_shift_px"] == 17`. |
| `test_cli::test_preview_page_shows_tolerated_border_shift_next_to_the_flicker_count` | In the page, `${s.guard_border_shift_px` sits between the flicker count and the z-fight count, labelled "tolerated sub-tolerance border movement". |

**Changed existing test.** `test_identity_all_counts_zero_and_passed` compares the WHOLE totals
dict literally, so it gained `"border_shift": 0`. The totals really do have a new key; the test
was not weakened. The three `test_cli.py` tests sit in the middle of the file, next to the
flicker tests, so a merge with a branch that appends at the end stays clean.

No test written from the brief failed against the implementation, so nothing was adjusted after
the fact.

## Real data

Commands run:
- `.venv/Scripts/python.exe -m engine.cli fix data/snapshots/ce26e0392ab0 --out data/output`,
  run twice;
- `... fix data/snapshots/0b290ec0bcb4 --out data/output`;
- `.venv/Scripts/python.exe -m engine.cli preview-data <snapshot> --out preview/data` for both.

All exited 0. The merge tolerance is `border_shift_tol = min(1.5 * 0.1, 0.5) = 0.15` in on both
files, and it happens to equal `depth_tol`.

### File A: `CHTM_SIDE_WALK_2nd_floor` (ce26e0392ab0)
- **Triangles:** 4,692 input, 4,848 reference (after solidify), 2,579 after removal, **1,117
  shipped**. At e57462d it was 2,579 shipped because the merge was rolled back.
- **Merge:** **kept**, no `rolled_back` key. `converged True`, `merge_rounds 2`,
  `regions_merged 177`, `faces_copied 358`, `regions_skipped {new_vertex: 1}`,
  `keep_all_regions 1`.
- **Guard totals** (`model_px` 2,058,592; `fragment_removed` 23 in every guard):

  | guard | passed | holes | material_changed | moved_same_flat | moved_other | zfight_tie | crack_closed | edge_flicker (hole/moved/material) | border_shift |
  |---|---|---|---|---|---|---|---|---|---|
  | `guard_after_removal` | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0/0/0) | 0 |
  | `guard_merge_attempt` | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0/0/0) | **59** |
  | `guard_final` (same report: the merge shipped) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0/0/0) | **59** |

- **Failing views:** none in any guard. The largest remaining `edge_flicker` in any view is 0.
  The 59 former flicker pixels, now border_shift, are spread over 18 views. View 0
  `[-0.987, -0.993, -0.989]` had 14 (5 hole, 9 moved) against a cap of 11.4. Every other view
  was under its cap: v25 5/11.3, v8 5/8.3, v3 4/10.2, v11 4/10.7, v23 4/8.3, v9 3/10.6,
  v14 3/10.7, v16 3/10.7, v17 3/8.3, v19 2/6.8, v22 2/10.1, v24 2/3.4, v2 1/8.2, v4 1/7.8,
  v6 1/6.7, v20 1/8.5, v21 1/7.4. In every view, every other class is identical to e57462d's
  report.
- **Measured displacements** (scratch `bs/diag_border.py`, using the engine's own helper): the 48
  disappeared pixels are at most 0.0623 in from the merged mesh (median 0.0260); the 11 appeared
  pixels are at most 0.0184 in from the original (median 0.0066). None is above 0.15.
- **Invariants:** `material_count_same, bbox_same, area_not_grown, cap_guard_passed,
  guard_passed` all True. **passed True**.
- **One-sided holes:** 569,539 before, 119,527 after.
- **Diff against e57462d's report.json:** only these fields changed:
  - `guard_merge_attempt.passed`;
  - the flicker fields, moved into `border_shift`;
  - the new `border_shift` keys;
  - `merge_report.rolled_back` / `rolled_back_reason` (now absent);
  - `tris_after` (2,579 -> 1,117);
  - `one_sided_holes_after` (119,529 -> 119,527).
- **Determinism:** two runs gave byte-identical `report.json`, sha256
  `fbe72e726d6853d60ab6b1968b978cc598524d5051b522c818ef429753b1c898` for both.

### File B: `CHTM_2nd_to_3rd_building_sidewalk_outside` (0b290ec0bcb4)
- **Triangles:** 7,227 input, 7,434 reference, 4,736 after removal, **602 shipped**, unchanged.
- **Merge:** kept. `converged True`, `merge_rounds 1`, `regions_merged 90`, `faces_copied 110`,
  `regions_skipped {overlap: 2, new_vertex: 1}`, `keep_all_regions 0`.
- **Guard totals** (`model_px` 2,424,975; `fragment_removed` 14):

  | guard | passed | holes | material_changed | moved_same_flat | moved_other | zfight_tie | crack_closed | edge_flicker (hole/moved/material) | border_shift |
  |---|---|---|---|---|---|---|---|---|---|
  | `guard_after_removal` | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0/0/0) | 0 |
  | `guard_merge_attempt` | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0/0/0) | **43** |
  | `guard_final` (same report) | True | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0/0/0) | **43** |

- **Failing views:** none. At e57462d the same 43 pixels (37 hole, 6 moved) were flicker spread
  over 19 views, all under their caps. Now they are border_shift and the remaining flicker is 0
  in every view.
- **Measured displacements:** the 40 disappeared pixels are at most 0.0623 in (median 0.0248);
  the 3 appeared pixels are at most 0.0234 in. None is above 0.15.
- **Invariants:** all True. **passed True**.
- **One-sided holes:** 465,082 before, 24,264 after.
- **Diff against e57462d's report.json:** only the flicker fields (moved into `border_shift`) and
  the new `border_shift` keys changed.

### preview-data
Both files' JSON was rewritten under `preview/data/`:
- A: `guard_border_shift_px 59`, `guard_flicker_px 0`, `guard_damaged_px 0`,
  `merge_rolled_back False`, `after_merged 1117`, `regions 177`;
- B: 43, 0, 0, False, 602, 90.

### QA images (file A, read with the Read tool)
- **`qa/top.png`:** the shipped mesh from above, drawn with few outlines. The two left slabs,
  the curved sweep into the walkway, the diagonal walkway and the big right-hand platform are
  each large plain regions. There are a stair-stepped outline and a few small leftover
  rectangles/triangles along the platform's right edge, and no triangle lattice on any top
  surface.
- **`qa/obl_bot_a.png`:** oblique from below. The left slab, stair undersides and the diagonal
  walkway read as clean planar regions, but the big sloped ramp face at the right-hand end is
  still a dense triangle lattice (a regular grid of small triangles) with long slivers in its
  upper band.
- **`qa/chunk2_bottom.png`:** a close-up of that right-hand end from below. The flat platform
  underside is one clean region, and the diagonal ramp beside it is **still a triangle lattice**:
  a regular grid of right triangles plus a fan of long slivers. It is not merged by this change,
  and this change never tried to merge it.

## Concerns

1. **The diagonal ramp is still a triangle lattice.** Nothing here touches the merge itself; this
   change only stops the guard throwing the merge away.
2. **A pre-existing blind spot, not changed here.** A pixel where BEFORE missed and AFTER hit is
   classed `PX_OK` by `_classify`. A surface that grows out over background is never flagged at
   all, so the brief's "BEFORE ray missed" branch is implemented but cannot be reached from
   `compare_views`. The only pixels ever measured are flicker, and those come from hole/move base
   classes, where BEFORE hit. Growth over sky is bounded only by the merge's own rule-9 area
   check (`collinear_tol * perimeter`) and the `area_not_grown` invariant.
3. **Per-view `border_shift` is not in report.json's `views`.** The `ViewVerdict` field exists,
   but `engine/cli.py::_view_verdict_dict` was left unchanged to keep the cli.py diff minimal. The
   totals carry it, and per view it equals the pre-change per-view flicker listed above. A later
   one-line cli change can add it.
4. **Stale files in `data/output/CHTM_SIDE_WALK_2nd_floor/`.** `guard_fail_0.png` (03:33) and
   `guard_fail_16.png` (a day old) are left over from earlier runs. This run failed no view and
   wrote none, and the CLI never deletes old `guard_fail_*.png`. A reader could mistake them for
   this run's failures. They were not deleted here.
5. **The two tolerances coincide by construction.** `border_shift_tol` and `depth_tol` are both
   1.5 x max quanta clamped at 0.5, and on both files they are 0.15. They are separate
   derivations, `RING_TOL_QUANTA` versus `guard_depth_tol`, that coincide only because
   `RING_TOL_QUANTA = 1.5`. For that reason the page does not label the border tolerance with
   `guard_tol_in`.
6. **The documented limit.** Real damage no wider than about the ring radius at a border, which
   the ring calls flicker and which measures `<= 0.15` in, is now excused. That is the bound the
   merge is itself allowed to move a border by. Anything wider leaves interior pixels that are not
   flicker, so it still fails, as the 2 in and 1 in tests show.
7. **`engine/guard/render.py` has no colour for `PX_BORDER_SHIFT`.** No caller produces the code
   for a triptych today: the CLI's triptychs classify without a ring, so they have neither flicker
   nor border shift. Left unchanged.
8. **Scratch files.** The diagnostics are in the session scratchpad under `bs/` (`premise.py`,
   `diag_border.py`, `summ.py`, `jdiff.py`, and the saved head/run1 reports). None is imported by
   the engine.

## Public signatures

Only what changed; everything else is unchanged.

```
engine/guard/compare.py

PX_BORDER_SHIFT = 9                                            # NEW pixel code

classify_pixels(before_depth, before_tri, after_depth, after_tri, material_before,
                material_after, flat_materials, depth_tol, *, origins=None, direction=None,
                plane_before=None, plane_after=None, ring=None, tie=None,
                allow_depth_fallback=False, strict=False, removed_before=None,
                border=None) -> np.ndarray                     # NEW kwarg `border` (a probe)

compare_views(before, after, face_material_before, face_material_after, flat_materials,
              depth_tol, strict=False, plane_before=None, plane_after=None,
              edge_flicker_cap=0.0, crack_closed_cap=inf, geometry_before=None,
              geometry_after=None, caster_factory=EmbreeCaster, allow_depth_fallback=False,
              removed_before=None,
              border_shift_tol: float = 0.0) -> GuardReport    # NEW kwarg, last
    # border_shift_tol > 0 without both geometries -> ValueError

@dataclass
class ViewVerdict:                                             # NEW last field
    border_shift: int
# GuardReport.totals gains "border_shift"

# private, new
_point_triangle_distance(points (N,3), triangles (N,3,3)) -> (N,) float64
_nearest_triangle_distance(points (P,3), triangles (F,3,3), reach: float) -> (P,) float64
_border_probe(geometry_before, geometry_after, tol) -> Callable[[points (P,3), gone (P,) bool], (P,) bool]
_classify(..., removed_before=None, border=None) -> (codes, base)
```

```
engine/fixes/merge.py

default_collinear_tol(quanta: np.ndarray) -> float             # NEW: RING_TOL_QUANTA * max(quanta)
merge_regions(mesh, topo, flat_materials=frozenset(), grid_size=GRID_SIZE,
              snap_tol=SNAP_TOL, collinear_tol=None) -> MergeResult   # signature unchanged
```

```
engine/fixes/pipeline.py

fix_object(mesh, flatness, profile=FixProfile()) -> FixResult  # signature unchanged
# FixProfile / FixResult unchanged; guard_merge_attempt and guard_final (also on rollback) run at
# border_shift_tol = min(default_collinear_tol(topo3.quanta), profile.depth_tol_max);
# guard_after_removal at 0.0
```

```
engine/cli.py

cmd_fix(...)            # signature unchanged; guard line gains ", border_shift=<guard_final count>"
cmd_preview_data(...)   # signature unchanged; stats gain "guard_border_shift_px"
```
