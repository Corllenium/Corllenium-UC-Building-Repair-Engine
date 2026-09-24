# Solidify review fixes, stray-fragment removal, visual QA sheet

Branch `feat-dashboard`, on top of `b2134e9` (265 passed). Six reviewed fixes to
`engine.fixes.solidify` and its cap guard, then two new features. Every item is one commit, each
written test-first: the test was run and watched fail before the implementation existed.

Untouched throughout, as instructed: `docs/superpowers/specs/2026-09-21-uc-model-fixer-design.md`
and every untracked file in the tree. `engine/fixes/merge.py` is **not touched by any commit in
this round** — two peer commits land there afterwards.

---

## S-C1 `fix(engine): cap guard cover rule uses the original exposure, not the solidified one`

Commit `a528705`.

### The defect

`solidify_feedback`'s rule 3 allowed an invented face to cover a pixel whose BEFORE hit was an
original face *"whose exposure ON THE SIDE THE RAY MET IT is 0 in the SOLIDIFIED mesh"*. That
mesh already contains the covering face, so the covering face is what drove the exposure to 0.
The rule consulted its own effect and therefore always agreed with itself.

The consequence the reviewer described, reproduced as `slab_with_partial_underside`: a slab whose
three skirts measure 9.8 in but whose real underside is only 4 in down and covers half the
footprint. `_has_bottom` sees 50 % coverage, decides there is no bottom, and invents one at
-9.8 that boxes the real underside in. Its solidified exposure goes to 0, the cap guard allows
the cover, and the strict hidden pass then deletes the real underside — with the cap guard, the
removal guard and the final guard all passing.

### The rule now

A BEFORE pixel whose hit is the FRONT side of an original face may be covered only while that
face's FRONT exposure **measured on the ORIGINAL mesh** is below `FixProfile.cover_max_exposure`
(default 0.10). Background and back-side hits are unchanged.

Three choices worth stating:

- **Front exposure, not double-sided.** The rule already knows which side the ray met, from the
  same `n . view_dir` rule 2 reads. Covering a face's front does not hide its back, and the
  module's existing per-side argument (`open_box_with_cells`, wound inward throughout) applies
  unchanged.
- **A threshold, not `== 0`.** A face seen only through an opening never measures exactly 0 by
  ray sampling. `compartment_with_deep_wall`'s far wall — 8 x 8 in, 45 in behind a 10 x 10 in
  opening — measures 0.0039 at 512 directions and 0.0078 at the shipped 128.
- **No pipeline reorder.** The brief allowed reordering `fix_object` so the input mesh's exposure
  was available before solidify. It was not needed: `_cap_guard` now measures
  `compute_side_exposure(positions_c, faces_before, ...)` — the original faces cast against
  themselves — which *is* the original mesh's exposure and is strictly cheaper than the
  solidified-mesh array it replaces (fewer faces, one caster, taken once before any round).
  `ok` stays all-True there, deliberately: a relatively-degenerate sliver is real hittable
  surface and is rendered as one, so giving it the 0.0 a `not ok` face gets would have made every
  sliver in the file free to cover.

### Tests (written first, watched fail)

- `test_a_bottom_that_would_box_in_the_real_underside_is_refused_by_the_cap_guard` — failed with
  `assert 0 >= 1` on `cap_guard_removed`, which is the defect exactly: nothing was refused. Now
  the bottom is still invented at 9.8 in, one of its two triangles is refused, the underside's
  front exposure in the solidified mesh is still > 0, and `fix_object` does not remove it.
- `test_a_wall_seen_only_through_a_side_opening_may_be_covered_and_is_then_removed` plus
  `test_fix_object_closes_the_compartment_and_removes_its_deep_wall` — the case rule 3 exists
  for, which the new rule must not break. 0 faces refused, 2 faces newly hidden, both removed
  end to end, run passes.

The two fixtures were already in the working tree from an interrupted earlier attempt. I read
them, measured them, and they are correct as written: the underside's front exposure is 0.50 and
the deep wall's is 0.0039, which is what their docstrings claim. They are committed here.

### Behaviour change, stated plainly

**`open_box_with_cells` is no longer closed.** Its skirt is planned and built and then refused,
because it would cover the near partition — which sits 3 in inside a whole missing side of a
10 x 10 x 10 box and measures **25 %** front exposure on the original mesh. That is not "seen
only through an opening" by any reading, and the old rule permitted it only through the
circularity above. Even at `cover_max_exposure = 0.20` it is refused.

Three tests pinned the old behaviour. They now pin the new one and say why, and each still tests
what it was written for:

| test | before | now |
|---|---|---|
| `..._open_box_gets_its_missing_side_and_becomes_closed` | skirt kept, 4 faces newly hidden | renamed `..._open_box_is_skirted_but_the_cap_guard_will_not_hide_its_partitions`: 2 refused, 0 newly hidden, and it measures the 25 % that causes it |
| `..._a_top_sheet_wound_downwards_is_still_a_top_sheet` | asserted the surviving skirt's z range | asserts `top_regions` picks the LID not the floor, and the measured thickness is 10.0 — which is what this test is about |
| `..._fix_object_closes_the_open_box_and_then_removes_both_partitions` | box closed, partitions removed | renamed `..._leaves_the_open_box_open_when_its_partitions_are_plainly_visible`; the end-to-end capability is covered by the compartment fixture instead |

On the real file A the rule alone is nearly inert: cap-guard removals 157 → **158**, faces newly
hidden 96 → **83**. The numbers the brief expects to improve (removals well below 157) are S-I4's
to move, not this item's.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **268 passed** (265 + 3).

---

## S-I4 `fix(engine): skirts use the local edge height`

Commit `cccaa4c`.

### What changed

`_edge_thickness` now returns one entry per open edge **in edge order, `None` included**, where
it used to return only the resolved numbers — which is precisely why they could only ever be used
as one per-region statistic. Each edge is extruded to its own clamped height; the region's median
is the fallback for an edge that resolves to nothing, and those are counted as
`skirt_edges_fallback`. `down()` is keyed by `(vertex, height)`, so two edges of one region that
measured different depths get two different shifted vertices at the corner they share, and the
vertical STEP between their skirts is what the mesh gets. That is correct — the slab really is
that thickness on one side and that thickness on the other.

### Fixtures

`slab_with_two_depths` — one top region, a flat **hexagon**, already skirted to 1.3 in at `x = 0`
and 9.8 in at `x = 2u`, four open edges each taking its depth from the end it touches. Two design
points, both paid for by a first attempt that failed:

- **A hexagon, not a rectangle.** `_edge_thickness` takes the deepest side face reaching *either*
  endpoint, so on a 4-corner ring every open edge touches a deep corner and all four measure
  `deep`. A genuine kink at `x = u` is a corner the union cannot simplify away, which a collinear
  midpoint would be.
- **The existing sides are outward-wound skirts of the slab itself**, not free-floating fins. My
  first version hung four fins off the corners; they are exposed on both faces (front 0.39–0.50),
  so the new skirts covered them and the cap guard refused 7 of 10 new faces. The fixture was
  testing rule 3, not S-I4. Real skirts are met on their BACK from inside, which rule 2 allows
  unconditionally, so `cap_guard_removed == 0` and the test measures only what it is about.

`bare_top_quad` — a single quad and nothing else, so not one edge resolves: four skirts, four
fallbacks, no bottom (`bottom_thickness_unresolved`).

### Tests (written first, watched fail: `KeyError: 'skirt_edges_fallback'`)

- `test_each_open_edge_is_extruded_to_its_own_measured_height` — 4 skirts, 0 fallbacks, 0 refused,
  and the eight skirt triangles bottom out at −9.8 (four) and −1.3 (four), with the shallow pair
  hanging off the shallow end. `thickness_per_region` is 5.55, the median, and is now only a
  fallback — which is the whole point.
- `test_a_measured_edge_height_is_still_clamped_into_the_profile_bounds` — the same 1.3 in comes
  back as 2.0 under the default `min_thickness`. Stated rather than tuned away.
- `test_an_edge_whose_height_cannot_be_measured_is_counted_as_a_fallback`.

### Real data, solidify alone

| | file A | file B |
|---|---|---|
| skirts (fallback) | 99 (1) | 42 (5) |
| bottoms added / already there | 21 / 83 | 14 / 56 |
| cap guard refused | **159** of 418 | **95** of 365 |
| faces newly hidden | **71** (was 83 after S-C1, 96 at `b2134e9`) | 30 |

**This item alone makes file A worse, not better, and here is why:** a step between two skirts of
different heights is itself an opening, and rays go through it. The bottom is still placed at the
region's median, so on a region whose edges range 1.3–9.8 the bottom now sits below some skirts
and above others. S-I5 puts the bottom at the shallowest resolved height, which is the half of
this change that closes the steps from underneath.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **271 passed** (268 + 3).

---

## S-I5 `fix(engine): bottom at the shallowest measured depth, deeper existing bottoms respected`

Commit `b5e7f48`.

### What changed

**Where the bottom goes.** The region's SHALLOWEST resolved skirt height, not its median. At the
median the bottom hangs below the shallow skirts — leaving the vertical steps S-I4 creates open
from underneath, which is the one direction a bottom exists to close — and cuts the deep ones in
half. The shallowest is the only depth at which the bottom meets a skirt instead of crossing one.
Reported per region as `bottom_depth_per_region`, beside `thickness_per_region`, which is now
only the fallback for unmeasurable edges.

**Whether it needs one.** `_has_bottom`'s downward search reaches `h + bottom_search_extra`
(24 in) rather than `h + tol`. `h` is the shallowest measured height, and a slab thicker in the
middle than at its rim already has an underside deeper than that. Stopping at `h` declared such a
region bottomless and invented a second bottom ABOVE the real one — the same defect S-C1 catches
after the fact, and this is the half that never creates the face. Bounded, not unbounded: a slab
100 in above a floor does not have that floor for an underside.

### Tests (written first, watched fail)

- `test_the_bottom_goes_at_the_shallowest_resolved_skirt_height` — one bottom, every vertex of it
  at −1.3, where the median would have put it at −5.55.
- `test_an_existing_underside_deeper_than_the_shallowest_skirt_counts_as_a_bottom` — the same slab
  with a real plate 11.8 in down: `bottom_exists`, nothing invented, the plate untouched and still
  the lowest thing in the mesh.
- `test_a_bottom_is_not_found_beyond_the_extra_search_depth` — at `bottom_search_extra = 2.0` the
  same plate is out of range and a bottom is invented. The search is bounded on purpose.

### Real data, solidify alone

| | file A | file B |
|---|---|---|
| bottoms invented / already there | 21 → **9** / 83 → **96** | 14 → **8** / 56 → **62** |
| cap guard refused | 159 → **134** of 290 new faces | 95 → **69** of 276 |
| faces newly hidden | **68** | **23** |

Refusals are now below the 157 the brief wanted beaten, though not "well below". Faces newly
hidden is **68 against the 96 at `b2134e9`** — the opposite direction from the brief's
expectation. Stated, not tuned; the diagnosis is in the closing section of this report.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **274 passed** (271 + 3).

---

## S-I3 `fix(engine): bottom triangulation skips are counted and partial bottoms refused`

Commit `f1b6aec`.

### What changed

`_add_bottom` had five silent `continue`s and emitted whatever parts it did manage. All six ways
a part can be refused — `empty_outline`, `polygon_failed`, `invalid_polygon`, `cdt_failed`,
`non_polygon_part`, `corners_unmapped` — are now counted into `bottom_skips`, and **any one of
them refuses the whole region's bottom**, counted as `bottoms_partial_refused` and never reported
as added.

Why all-or-nothing: a bottom missing one triangle is a hole in the underside, and that is worse
than no bottom at all. The rest of the bottom still hides whatever is above it, so the hidden
pass deletes the real geometry and the hole is what ships. The triangle list is built before the
builder is touched, which also means a refused bottom invents no vertices.

### Tests — and an honest note about how they reach the branch

**No fixture in this repo produces a skip, and neither real file does** (both report six zeros).
`b2134e9`, which added the non-polygon guard, says the same of that branch: *"a non-polygon part
would have crashed, so a result that exists never had one"*. I tried to build one — a diagonal
pinch in a grid slab, which I expected to make a self-touching ring — and GEOS resolved it into
two ordinary holes, giving a perfectly valid polygon.

So the two refusal tests drive the branch directly and say so in their docstrings: one replaces a
single part of the REAL CDT's output with a `LineString`, one makes GEOS raise. What is under
test is solidify's verdict, not shapely's behaviour. A third test pins six zeros and a complete
bottom on a clean run, so the counters cannot silently start counting.

Both real files are unchanged by this item.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **277 passed** (274 + 3).

---

## S-I2 `fix(engine): the cap guard is an invariant`

Commit `f32d035`.

### What changed

A round of `solidify_feedback` measures its `failing_pixels` **before** applying its own
removals, so a loop cut off at `max_rounds` left a history describing a mesh that is not the one
it handed back — and `cap_guard_removed` was the only trace that anything might still be wrong.
The loop now always ends with a render-only verification of the state it returns, appended as one
extra round with `"removed": 0`, so `history[-1]["failing_pixels"] == 0` is always a statement
about the returned mask.

`SolidifyResult.report["cap_guard_passed"]` publishes that, vacuously True when nothing was
invented. `fix_object`'s `invariants` gain `cap_guard_passed` and `passed` depends on it.

Why it has to be an invariant and not just a report: **every other guard in the run compares
against the SOLIDIFIED mesh.** If the cap guard never converged, the reference itself is covering
something a person can see, and no later guard would ever notice — they would all agree with a
picture that is already wrong.

`FixProfile.cap_guard_max_rounds` (8) makes the limit a setting rather than a literal.

### Tests (written first, watched fail)

- `test_a_cap_guard_that_never_converged_fails_the_whole_run` — gives the guard **no rounds at
  all** on `slab_with_partial_underside`. That is the cleanest way to leave a solidified mesh
  that has never been corrected, and it is the honest way to reach this branch: no fixture in the
  repo needs more than one removal round, so `max_rounds = 1` would converge and prove nothing.
  8,498 failing pixels, nothing removed, `cap_guard_passed` False, `passed` False.
- `test_a_converged_cap_guard_is_reported_as_passed`, and
  `test_a_run_with_nothing_to_solidify_passes_the_cap_guard_vacuously` (both `--no-solidify` and a
  closed box).

`test_box_with_partition_removes_only_the_sealed_partition` asserts the whole `invariants` dict
and now lists the new key — an expected consequence, not a weakening.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **280 passed** (277 + 3).

---

## S-M `fix(engine,preview): solidify docstrings, face_line marker, preview labels`

Commit `9c52695`.

Four statements that were not true of the code under them.

**1. "over ORIGINAL faces".** Every per-face array in `FixResult` is sized over the REFERENCE
mesh, which solidify makes longer than the input. `exposure_class`, `removed_hidden`,
`removed_slit`, `restored_degenerate`, `flipped`, `thin_sheets`, `removed_overlap`,
`restored_overlap`, `source_faces` and the ids in `overlap_pairs_diff_material` now say so, and
`reference_mesh` lists them in one place with the rule that makes the confusion survivable: the
input's faces are the reference's first `input.n_faces` rows, so the two agree below that bound
and only there. `_newly_hidden` now says which MESH each of its two exposure measurements is
taken against — the original alone, then the whole solidified mesh — not merely which faces they
are over. The module docstring states the cap rule it now applies.

**2. `face_line` on invented faces.** They got `n + 1, n + 2, …`: real row numbers belonging to
OTHER faces, which would send anyone chasing a defect to the wrong row. Now `-1`. (`merge` takes
the minimum line of a region it rebuilds, so a region mixing invented and read faces reports −1,
which is true of it.)

**3. The overlap tie-break docstring — a real finding, not a wording fix.** It claimed *"a whole
stacked layer is one patch, so the smaller LAYER loses"*. That is false for the case the rule
exists for: two EXACTLY coincident layers weld to the same vertices, so they share the same
welded edges and `_patch_of` unions them into **one** patch. Measured on
`stacked_duplicate_slab`: 144 candidates, **one patch of 144**, and what decides all 72 removals
is entirely the second key (higher face id loses). The patch size only decides anything for
layers that merely overlap rather than coincide. `test_two_exactly_stacked_layers_are_one_patch_not_two`
pins the corrected statement, so it cannot drift back.

**4. The preview BEFORE pane.** It was the REFERENCE mesh under a heading reading "as exported",
so it showed skirts and bottoms the export never had. `preview-data` now writes:

- `before` — the original export: geometry, materials, hidden flags, **and the BEFORE edge lists,
  built from the INPUT mesh's own topology** (15 segments for `slab_with_three_skirts`, not the
  reference's 18) so no skirt outline floats there with no surface under it. Both meshes are
  framed on the same centre, so the panes stay registered.
- `reference` — only what solidify added and the cap guard kept.
- `stats.tris_added_by_solidify` and `stats.cap_guard_passed`.

The page heads the pane "BEFORE · the original export", leads with `tris_input`, draws the added
block in its own green behind an "added by solidify" toggle (off by default), and names the
reference count, what was added and the cap guard's verdict in the note beneath.

### Tests

`test_an_invented_face_carries_no_line_number`,
`test_preview_data_before_pane_is_the_original_export_not_the_reference`,
`test_preview_data_before_edges_belong_to_the_original_export`,
`test_preview_page_says_its_before_pane_is_the_original_export`,
`test_two_exactly_stacked_layers_are_one_patch_not_two`. The docstring corrections in (1) have no
test of their own — they are documentation — except where (3) turned into a behavioural claim.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **285 passed** (280 + 5).

---

## F1 `feat(engine): stray fragment detector and reviewed removal`

Commit `5169e68`.

### What it is

New package `engine/detectors/` (`fragments.py`), run in `fix_object` after the hidden-face
removal and before the flip, on by default (`FixProfile.accept_fragments`; CLI
`--keep-fragments` turns it off).

- **Fragments** — connected components over SHARED WELDED EDGES. A component is debris when its
  total area is under `fragment_max_area` (4 sq in), or it is a single face, or its longest
  bounding-box extent is under `fragment_max_extent` (6 in) — and **never** when it holds a face
  bigger than `fragment_max_area` on its own.
- **Slivers** — faces attached to the main body with `4*pi*area/perimeter^2 < sliver_q` (0.02)
  **and** area at most `fragment_max_area` (see finding 2). Reported separately.
- **The guard** — `engine.guard.compare.fragment_feedback`, FRAGMENT mode: the only pass in the
  engine allowed to change the picture, and only at its own candidates' pixels. The final guard
  excuses those pixels by name through `compare_views(..., removed_before=...)`, as a new class
  `PX_FRAGMENT_REMOVED` counted as `fragment_removed` and never a failure.

`FixResult` gains `removed_fragments`, `n_fragment_components`, `n_removed_fragments`,
`n_removed_slivers`, `n_restored_fragments` and `fragment_report` (component counts plus the ten
smallest components the rules did NOT catch, as evidence for the thresholds). report.json, the
preview stats and the preview page show them; `ViewVerdict` and every guard total gain
`fragment_removed`.

### Three findings on file A, each of which changed the design

The first implementation passed every fixture test and **failed file A**. Each fix below was
found by measuring, not guessed, and each now has a test.

**1. Excuse the pixels; do not drop the faces from the final guard's BEFORE.** My first version
made the final guard compare against "the reference minus the fragments". File A:
`passed=False`, **749 `moved_same_flat` pixels**, merge rolled back to 2,561 triangles. The
hidden pass had judged the picture WITH the debris in it, so a face it deleted could be invisible
only because a sliver covered it — and a BEFORE without the sliver puts the deleted face back on
screen. The brief's own wording ("tolerates exactly the fragment pixels") was the right rule:
any pixel whose BEFORE first hit (in the WHOLE reference) is a removed fragment is excused, which
covers whatever was behind it too.

**2. A sliver must be small, not just thin.** `4*pi*area/perimeter^2` is scale-free: a
630 x 4 in strip of real sidewalk scores 0.006, deeper into "needle" than a 1 in whisker. On file
A's reference **285 faces score under 0.02, the largest 391–793 sq in**, and the fragment guard
cannot save them — it tolerates a candidate's own pixels by construction. Slivers are now also
bounded by `fragment_max_area`, the same bound the component rule already applies; file A's
candidates fell from 33 to 16 and the excused pixels from 10,168 to 23. Not a new threshold, and
not a weakening of the brief's rule: the brief's example is a needle, and a 793 sq in strip is not
one.

**3. The fragment guard must render the SAME BEFORE as the final guard, and blame what actually
went.** One pixel remained, and it rolled the merge back. Traced along the ray: three faces
coincide at t = 3877.525 — 869 (removed by the hidden pass; the render's pick), 782 (kept, but its
edge stops just short of the pixel) and 783, a 0.108 sq in sliver (q = 0.00022) that was the only
surface left holding it. Rendered against the post-hidden mesh, the pixel looked like the sliver's
own and it went; the final guard, rendering the whole reference, saw face 869's pixel become a
31.8 in fall-through. Now:

- BEFORE is the whole reference; earlier removals are passed as `already_removed` and dropped
  from AFTER only.
- A failing pixel blames every candidate its BEFORE ray meets **in front of AFTER's first hit**
  (removal-only, so those are exactly the surfaces no longer there). A tie-set blame — within
  `depth_tol` of the first hit — was tried and is not enough: `VIEWS_26` has near-horizontal views
  (z ≈ 0.011) where a 0.01 in gap is an inch along the ray.
- A failing pixel no candidate was involved in is another pass's doing (the colour-tolerant slit
  pass, say), counted as `not_ours_pixels` and left to the final guard — so another pass's
  verdict can never make this one discard its work. An earlier "restore everything if a pixel
  cannot be blamed" rule did exactly that on the synthetic test below.

On file A the guard now catches exactly that one pixel in round 0, restores sliver 783 by name,
and round 1 is clean.

### Tests (`engine/tests/test_fragments.py`, 11)

Detector: a detached 2 sq in triangle is a fragment candidate; the detached 20 sq in quad is kept
and reported (its 5 in extent is under the extent threshold — the "no face over 4 sq in" rule is
what saves it); the attached needle is a sliver and never a fragment; nothing is a candidate on a
clean slab; the detector repeats itself exactly. Pipeline: the triangle and needle are removed and
the quad stays; the final guard excuses the stray pixels (`fragment_removed > 0`) with 0 holes /
material changes / moves, and excuses nothing with the pass off; `--keep-fragments` removes
nothing; `fix_object` is deterministic; the CLI flag parses.

`test_the_fragment_guard_sees_the_same_before_as_the_final_guard` pins finding 3 at the size of
the defect: a plate H already removed, 0.01 in above a 0.5 in strip S that is the only surface
left there. Called the OLD way (BEFORE = post-hidden mesh) S is removed — **the test reproduces
the defect**; called the new way S is restored by name, and the 6 silhouette pixels H's own
removal flickers are counted as not this pass's and never blamed on S.

Order, stated honestly: the detector and pipeline tests were written first and watched fail
(`No module named 'engine.detectors'`). The regression test for finding 3 was written after the
fix, from the file A trace; it proves itself by reproducing the defect through the old calling
convention in its first half.

### Tests changed

- `test_a_sliver_that_only_the_relative_test_calls_zero_area_is_kept_by_the_guard` now passes
  `accept_fragments=False`. Its 0.05 sq in DETACHED sliver is debris to F1, and F1's guard deletes
  it by design; the test's subject is the strict degenerate-face guard, unchanged. Same precedent
  as the three tests S1 gave `solidify=False`.
- `test_main_dispatches_to_cmd_fix` learns `--keep-fragments`; `test_identity_all_counts_zero_and_passed`
  lists the new `fragment_removed` total.

### Real data (full pipeline, default profile)

| | file A | file B |
|---|---|---|
| components | 23 | 18 |
| fragments / slivers removed | 3 / 15 | 0 / 12 |
| restored by the fragment guard | 1 | 0 |
| px excused as removed debris (final guard) | 23 | 14 |
| triangles | 4,692 → **1,590**, passed | 7,227 → **1,128**, passed |

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **296 passed** (285 + 11).

---

## F2 `feat(engine): visual QA sheet written by every run`

Commit `ab2d2fc`.

### What it is

`engine/guard/qa_render.py`, ported from `spike/17_visual_qa.py`.
`write_qa_sheet(mesh, polygon_edges, out_dir, size=(1600, 1000))` renders the spike's 12 views
and 9 close-ups (3 slices along the longer horizontal axis, each from above, below and the side),
shaded double-sided, hidden lines removed, and returns the 21 paths in the fixed order
`qa_file_names()`. `python -m engine.cli fix` writes them for the SHIPPED mesh under
`<run dir>/qa/`.

**The edges are the ones SketchUp will draw.** `polygon_edges(mesh, rings)` takes every merged
region's outer AND inner loops from the merge's rings — deduplicated by dict identity, as the
merge emits them — and never its triangulation diagonals, plus every triangle edge of a row
copied through (which is every row when the merge was rolled back and `rings` is empty). Inner
loops are drawn even though the ngon OBJ cannot carry them, because the SketchUp export does.

### Changes from the spike

- **Vectorised edge pass.** Every sample of every edge is projected and depth-tested in one go,
  sampled so consecutive samples are under a pixel apart, and drawn by marking each visible
  sample's pixel. A sample is visible when it is no further along the view ray than the surface
  its pixel shows, within three pixels (never under 0.5 in) — so an edge lying ON a visible
  surface is drawn, including at a crease, and one behind it is not.
- **Always 21 files.** A close-up slice with fewer than 3 vertices falls back to the whole-model
  frame instead of being skipped (the spike skipped it). A test can count the output.
- **Framing uses only referenced vertices.** `mesh.positions` keeps rows no face uses any more;
  framing on them could zoom out onto nothing.
- **`FixProfile.qa_size`** (default 1600 x 1000). Without it every `cmd_fix` test rendered 21
  full-size images and `test_cli.py` went from 14 s to 119 s; the CLI tests' fast profile now
  renders 160 x 100.

### Tests (`engine/tests/test_qa_render.py`, 6, plus one in `test_cli.py`)

Loops not diagonals; a hole's inner loop is drawn; every triangle edge when rolled back; an edge
under a 100 in plate is hidden from above (**0 px**) and drawn from below (**~90 px** — the small
quad's 80 in perimeter at 0.88 in per pixel; my first threshold of 100 was a guess and the
measurement corrected it); 21 files even with an empty slice; byte-identical PNGs across two
runs; `cmd_fix` writes all 21.

Order, stated honestly: the renderer was ported before its unit tests. The CLI test was written
first and watched fail on the missing `qa/` directory.

### Result

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **303 passed** (296 + 7).

---

## Follow-up to F2 `fix(engine): the QA sheet no longer draws edges lying under a surface`

Commit `8046254` — a ninth commit, not one of the eight items, found by reading file A's own
sheet.

The first F2 renderer drew an edge sample when it was within a FLAT three-pixel depth tolerance
of the surface its pixel shows. File A's `top.png` showed short dashed edges on the right slab
that could not be edges ON it (from straight above, an edge on a flat slab draws solid).
Measured: in that view (1.10 in per pixel) about **6,000 drawn samples lay 0.5–3.3 in behind the
surface they were drawn over** — hidden edges bleeding through, on the one picture meant to be
trusted at a glance.

The tolerance is now per pixel: the depth change the HIT surface's own slope makes over three
quarters of a pixel (a sample is at most half a pixel diagonal from its pixel's ray), capped at a
slope of 20, plus `max(diag * 2e-4, 0.05 in)` of slack. An edge ON the visible surface meets
that bound — at a crease it lies on both faces' planes — and one behind it does not, however
close. Top-view samples drawn more than 0.5 in behind the surface: **~6,000 → 827**, the rest on
steep faces where the sub-pixel offset is genuine.

Tests, the first watched fail (92 px — the whole hidden outline — drawn through the plate): an
edge 2 in under a flat plate is not drawn from above and is from below; an edge ON a 60° roof is
still drawn from above, so the rule did not simply get stricter everywhere. **305 passed.**

---

## Finish

### Suite

`.venv/Scripts/python.exe -m pytest engine/tests -q` → **306 passed** (265 at `b2134e9`; +41),
at the final HEAD `c0bbc98`. Run twice: in the shared working tree (which holds other sessions'
uncommitted edits to `engine/io/snapshot.py`, `docker-compose.yml` and the design spec, none of
them mine), and in a clean detached worktree at HEAD with `PYTHONPATH` pinned to it
(`engine.__file__` checked): **306 passed** both ways, so the count belongs to the commits.
(The same check at `8046254` gave 305; `c0bbc98` below adds one test.)

### Real data — `python -m engine.cli fix <snapshot> --out data/output`, final code

| | file A `ce26e0392ab0` | file B `0b290ec0bcb4` |
|---|---|---|
| name | `CHTM_SIDE_WALK_2nd_floor` | `CHTM_2nd_to_3rd_building_sidewalk_outside` |
| skirts (fallback edges) | 99 (1) | 42 (5) |
| bottoms added / partial refused / already there | 9 / 0 / 96 | 8 / 0 / 62 |
| bottom skips (all six reasons) | 0 | 0 |
| vertices invented / outline unmappable | 142 / 1 | 208 / 1 |
| cap guard rounds (failing px, removed) | 3 (25,672 & 133; 3 & 1; 0 & 0) | 3 (7,918 & 67; 3 & 2; 0 & 0) |
| cap guard removals / `cap_guard_passed` | **134** / True | 69 / True |
| faces newly hidden by solidify | **68** (1,853 → 1,921) | 23 (2,411 → 2,434) |
| hidden candidates / restored / removed | 2,024 / 39 / 1,985 | 2,609 / 25 / 2,584 |
| zero-area dropped / degenerate restored | 217 / 0 | 79 / 0 |
| overlap pairs same (diff) / removed / restored | 140 (0) / 49 / 0 | 72 (4) / 23 / 0 |
| fragment components / fragments / slivers removed / restored | 23 / 3 / 15 / 1 | 18 / 0 / 12 / 0 |
| flipped / thin sheets | 780 / 79 | 827 / 16 |
| regions merged / `faces_copied` | 175 / 781 | 89 / 452 |
| `regions_skipped` | new_vertex 1, invalid_polygon 2 | overlap 2, new_vertex 1, invalid_polygon 1 |
| triangles input → reference → shipped | 4,692 → 4,848 → **1,590** | 7,227 → 7,434 → **1,128** |
| one-sided holes before → after | 569,539 → 119,530 | 465,082 → 24,267 |
| `guard_after_removal` | passed; 2,058,592 model px, `fragment_removed` 23, all else 0 | passed; 2,424,975 model px, `fragment_removed` 14, all else 0 |
| `guard_merge_attempt` (= `guard_final`) | passed; `edge_flicker` 25 (24 hole, 1 moved), `fragment_removed` 23, all else 0 | passed; `edge_flicker` 16 (16 hole), `fragment_removed` 14, all else 0 |
| strict_final | True | True |
| invariants | material_count_same, bbox_same, area_not_grown, **cap_guard_passed**, guard_passed — all True | all True |
| passed / merge rolled back | **True** / no | **True** / no |
| runtime, wall incl. the 21-image QA sheet (solidify part) | 82.3 s (16.9 s) | 81.0 s (16.8 s) |

`preview-data` for both into `preview/data`, regenerated at `c0bbc98`: reference 4,848 / 7,434
triangles of which 156 / 207 added by solidify, `hidden_in_export` 1,889 / 2,411,
`cap_guard_passed` True, `fragment_removed_px` 23 / 14, merge kept. The `fix` outputs above are
from `8046254`; `c0bbc98` touches only `preview-data` and the page, never `fix` or `report.json`.

**Determinism.** Two runs of file A: `report.json` byte-identical (sha256 `7d5a16ae1596397a…`),
and all 21 QA images byte-identical too.

### Against the brief's expectations — reported, not tuned

| expectation (file A) | got | |
|---|---|---|
| faces newly hidden by solidify well above 96 | **68** | **opposite direction** |
| cap-guard removals well below 157 | 134 | below, not "well below" |
| triangles below 1,600 | 1,590 | met, narrowly |
| both guards passing | cap guard and final guard pass | met |

Where the newly-hidden count went, measured item by item with solidify alone on file A: S-C1
96 → 83 (the cover rule now refuses to hide faces that were genuinely visible on the original
mesh), S-I4 83 → 71 (a step between skirts of different heights is itself an opening), S-I5
71 → 68 (bottoms invented 21 → 9, because 13 more regions are now recognised as already having a
deeper underside). Each reviewed fix costs some sealed faces, each for its own correctness reason.
The expectation assumed per-edge skirts would stop being refused; refusals fell only 157 → 134,
because S-C1 refuses more while S-I4 and S-I5 refuse less.

One hypothesis I did not test, labelled as such: `_edge_thickness` still resolves an edge to the
DEEPEST side face at either endpoint (the rule the brief kept). With per-edge extrusion that
overhangs wherever one corner carries a deep fin, and may account for much of the remaining 134.

### Three QA images, read (final code)

- **File A `qa/top.png`** — a plan view in which the flat regions (the stepped left platform,
  the connecting strip and the large right slab) are single outlined polygons while the diagonal
  ramp in the middle is still a dense web of copied-through triangles, and a few short dashed
  edge fragments remain near the lower middle of the right slab.
- **File A `qa/obl_bot_a.png`** — seen obliquely from below, the left platform shows its skirts
  as solid side walls over a stepped underside, the strip and the right slab's underside are
  single flat polygons, and the diagonal ramp and the right section's sloped lower face are
  heavily triangulated with long thin triangles.
- **File B `qa/chunk1_top.png`** — a close-up of the middle third: a long walkway whose top is
  one clean polygon with a thin curb along the far edge, and a side skirt along the near edge
  whose depth changes in small vertical steps (consistent with S-I4's per-edge heights), meeting
  a thicker slab on the right that shows its full depth as a solid block.

### Concerns

1. **File A hides fewer faces than at `b2134e9` (68 vs 96)**, against the brief's expectation;
   diagnosis above, nothing tuned.
2. **S-C1 changed behaviour on `open_box_with_cells`**: no longer closed (its partition is 25 %
   exposed through a whole missing side). Three tests were rewritten to pin that and say why.
3. **F1 deviates from the letter of the brief in two places, both forced by file A**: slivers
   are also bounded by `fragment_max_area` (the quality ratio alone flagged 793 sq in strips,
   which the fragment guard cannot protect), and the fragment guard renders the whole reference
   and blames candidates in front of AFTER's first hit, leaving pixels no candidate was involved
   in to the final guard. Without both, file A failed (749 phantom pixels, then 1 real one) and
   rolled its merge back.
4. **Tests that reach their branch artificially, stated in their docstrings**: S-I3's two
   refusal tests monkeypatch shapely (no fixture or real file produces a skip); S-I2's failing
   test gives the cap guard 0 rounds (no fixture needs more than one removal round).
5. **Order**: F1's coincident-surface regression test was written after the fix (it reproduces
   the defect through the old calling convention); F2's renderer was ported before its unit
   tests. Every other item was test-first.
6. **Two commits beyond the eight items**, both found by checking the real output rather than
   the tests: `8046254` (QA-sheet bleed-through, seen on file A's own sheet) and `c0bbc98` (two
   BEFORE-pane numbers still counted from the reference, seen on the live preview page).
7. `engine/fixes/merge.py` is untouched by all ten commits. `engine/tests/fixtures/build.py`
   gained `slab_with_two_depths`, `bare_top_quad` and `slab_with_strays` at its end, where the
   peer commits will also append.

---

## Second follow-up `fix(engine,preview): the BEFORE pane's counts are the export's own`

Commit `c0bbc98` — a tenth commit, found by loading the preview page with both real files' data
(the only way to check what a page says).

S-M made the BEFORE pane show the ORIGINAL export, but two numbers on it were still the
reference mesh's:

- **"N hidden inside"** read `stats.hidden`, which counts hidden faces over the REFERENCE,
  including faces solidify invented and the hidden pass removed again — which the export pane
  never draws. File A said 1,985 and drew 1,889; file B said 2,584 and drew 2,411.
  `preview-data` now also writes `hidden_in_export`, and the pane shows that; `hidden` keeps its
  meaning for any other reader.
- **"N % fewer"** was measured from the 4,848-triangle reference beside a pane leading with the
  4,692 exported. It is measured from `tris_input` now and says "fewer than exported": 66.1 % on
  file A, where it read 67.2 %.

Checked in the browser (http.server on 5180, not restarted) against regenerated data: no console
errors, the counts above, and the "added by solidify" layer drawn in its own green over the
x-rayed export. Test first: the `hidden_in_export` assertion and a page-source test watched fail.
**306 passed.**

---

## Public signatures

Only what changed this round; everything else is unchanged from the last `## Public signatures`
section of `guard-round-2026-09-23-report.md`.

```
engine/fixes/pipeline.py

@dataclass
class FixProfile:                                  # NEW fields, all with defaults
    bottom_search_extra: float = 24.0              # S-I5
    cover_max_exposure: float = 0.10               # S-C1
    cap_guard_max_rounds: int = 8                  # S-I2
    accept_fragments: bool = True                  # F1  (CLI --keep-fragments)
    fragment_max_area: float = 4.0                 # F1
    fragment_max_extent: float = 6.0               # F1
    sliver_q: float = 0.02                         # F1
    qa_size: tuple[int, int] = (1600, 1000)        # F2  (CLI only)

@dataclass
class FixResult:                                   # NEW fields, inserted before removed_overlap
    removed_fragments: np.ndarray                  # bool over REFERENCE-mesh faces
    n_fragment_components: int
    n_removed_fragments: int
    n_removed_slivers: int
    n_restored_fragments: int
    fragment_report: dict
    # every per-face array is documented as over the REFERENCE mesh (S-M)
    # invariants gain "cap_guard_passed"; passed depends on it (S-I2)
    # feedback_history gains "fragments" (None when the pass did not run)

fix_object(mesh, flatness, profile=FixProfile()) -> FixResult    # signature unchanged
```

```
engine/fixes/solidify.py

solidify(mesh, topo, profile) -> SolidifyResult    # signature unchanged
    # report gains: skirt_edges_fallback, bottom_depth_per_region, bottoms_partial_refused,
    #               bottom_skips {empty_outline, polygon_failed, invalid_polygon, cdt_failed,
    #               non_polygon_part, corners_unmapped}, cap_guard_passed
    # invented faces get face_line = -1

_BOTTOM_SKIPS = (...)                               # NEW (module-private)
_edge_thickness(topo, edges, sides, side_low, side_centroid, vertex_sides, radius)
    -> list[float | None]                           # was list[float]: one entry per edge now
_has_bottom(topo, members, caster, h, tol, fraction, search_extra=24.0) -> bool
_add_bottom(builder, topo, plan, down, material, uv_scale, welded_to_original, skips)
    -> tuple[bool, bool]                            # (added, skipped); all or nothing
_cap_guard(original, solid, new_faces, guard_size, n_dirs=128, cover_max_exposure=0.10,
           max_rounds=8)                            # exposure measured on the ORIGINAL faces
```

```
engine/guard/compare.py

PX_FRAGMENT_REMOVED = 8                                                     # NEW

classify_pixels(..., strict=False, removed_before=None) -> np.ndarray       # NEW kw removed_before
compare_views(..., allow_depth_fallback=False, removed_before=None) -> GuardReport   # NEW kw

@dataclass
class ViewVerdict:
    ... edge_flicker: int
    fragment_removed: int          # NEW (after edge_flicker); guard totals gain the same key
    edge_flicker_hole; edge_flicker_moved; edge_flicker_material

solidify_feedback(positions_c, faces_before, faces_after, is_new, front_exposure_before,
                  cover_max_exposure=0.10, views=VIEWS_26, size=(900, 600),
                  caster_factory=EmbreeCaster, max_rounds=8) -> (keep, history)
    # was front_exposure_after (solidified mesh); now the ORIGINAL mesh's front exposure
    # a loop cut off at max_rounds appends one render-only verification round ("removed": 0)

fragment_feedback(candidates, positions_c, faces, face_material, flat_materials, depth_tol,
                  already_removed=None, views=VIEWS_26, size=(900, 600),
                  caster_factory=EmbreeCaster, max_rounds=8,
                  crack_closed_cap=inf) -> (mask, history)                  # NEW
    # history: {"round", "candidates_remaining", "failing_pixels", "not_ours_pixels", "restored"}
```

```
engine/detectors/__init__.py                                                # NEW package
engine/detectors/fragments.py                                               # NEW

@dataclass
class FragmentResult:
    fragments: np.ndarray          # bool over the faces handed in
    slivers: np.ndarray            # bool, disjoint from fragments
    component: np.ndarray          # int64 component id per face
    report: dict                   # n_components, n_candidate_components,
                                   # n_above_threshold_components, n_fragment_faces,
                                   # n_sliver_faces, smallest_kept_components (<= 10)

detect_fragments(positions_w, face_w, profile) -> FragmentResult
```

```
engine/guard/qa_render.py                                                   # NEW

QA_VIEWS: dict[str, tuple[float, float, float]]          # 12 named view directions
QA_CLOSE_UP_VIEWS: tuple[tuple[str, tuple], ...]          # top / bottom / side
QA_SLICES = 3
qa_file_names() -> list[str]                              # the 21 names, in write order
polygon_edges(mesh, rings) -> np.ndarray                  # (E, 2) int64, SketchUp's edges
write_qa_sheet(mesh, polygon_edges, out_dir, size=(1600, 1000)) -> list[Path]
```

```
engine/cli.py

cmd_fix(snapshot_dir, out_root, accept_slit, profile=None, solidify=True,
        fragments=True) -> int                            # NEW kw fragments; writes <run>/qa/
build_parser()                                            # fix gains --keep-fragments
_profile_dict(p)                                          # gains every new FixProfile field
_build_report(...)                                        # report.json gains n_fragment_components,
                                                          # n_removed_fragments, n_removed_slivers,
                                                          # n_restored_fragments, fragment_report;
                                                          # guard views gain fragment_removed
cmd_preview_data(...)                                     # "before" is the ORIGINAL export; new
                                                          # "reference" block = faces solidify
                                                          # added; stats gain tris_added_by_solidify,
                                                          # hidden_in_export, cap_guard_passed,
                                                          # n_fragment_components,
                                                          # n_removed_fragments, n_removed_slivers,
                                                          # n_restored_fragments, fragment_removed_px
```
