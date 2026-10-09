# Task P2-E8b report: the narrow flat fill

**Current status: DONE_WITH_CONCERNS.** After ruling P2-E8b-R9 (keep R1 as written; the fill measurement moves to
after E6), items 2-4 were built on fixtures: commits 62a3666, 4867c6b, f00a7f3. See "Continuation after ruling R9"
at the end. The first round, kept as it was, follows.

**First-round status: NEEDS_CONTEXT.** Ruling E8b-R1 contradicts the data. On all three golden units, before and after E8a, **no
hole passes R1**: 0 candidate holes, so E8b would fill nothing, and the exit's six fill crops cannot exist. As the
dispatch says, I stopped here instead of loosening the ruling. Item 1 (the engine, rulings R1-R5, with its tests) is
committed. Items 2-4 (the Validator's `fill_site` class, the kernel wiring, and the CLI `fills` / `not_filled`) are
**not started**.

- Worktree: `D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/P2-E8b`, branch `claude/P2-E8b`, base 76ca35a.
- Commit: **724300b** `feat(p2-e8b): E8FlatFill plans the narrow flat fill (rulings E8b-R1..R5) and lists every refused hole`.
- Nothing touched in `engine/guard/**`, `engine/validate/**`, `FixProfile`, or any existing test. No live data,
  container or owner folder was touched. Real-data reads went to `C:/Temp/e8b/probe/`.

## Item 1: E8FlatFill (`engine/repair/engines/e8_fill.py`), done

Files:
- `engine/repair/engines/e8_fill.py`: `E8FlatFill` (name `E8b`, not legacy), `ear_clip`, and `FILL_MAX_DIAMETER = 39.37`
  as a named constant.
- `engine/tests/fixtures/holes.py`: `holed_slab`, a closed or open slab with holes on a lattice.
- `engine/tests/test_e8_flat_fill.py`: 12 tests.

What it does, in test order (the first rule that fails names the refusal):
- **R1.** It finds the components of the open edges. These are the same open edges `find_errors` counts
  (`analyse_topology`'s `EDGE_OPEN`).
  - A component in which some point has other than two open edges is refused: `not_a_simple_loop`.
  - **R2 planarity:** the loop's points must lie within `plane_tol = 2 × print_step` of their least-squares plane.
  - **R1 simplicity:** the loop must not cross itself in its plane (`self_crossing`).
  - **R2 neighbours:** every face on a loop edge must have its normal within 1° of the plane's and all its corners
    within `plane_tol` of the plane.
  - **Hole or patch border:** if all neighbours lie inside the loop, it is a patch's outer border, which is counted and
    never filled. If all lie outside, it is a hole. If they lie on both sides, it is refused.
  - **R1 inner loop:** the hole is refused when another open-edge loop lies inside it (`inner_loop`), or when any face
    passes through it (`faces_inside`).
- **R3.** The inscribed diameter comes from `shapely.ops.polylabel`, with a tolerance of 0.005 in.
- **R4.**
  - The neighbours must have one look, as `face_keys` keys a look.
  - They must all face one side.
  - One affine UV map, fitted with `fit_uv`, must leave a residual of at most 1e-3 on every neighbour corner.
- **R5.** The ear-clipping is written in the repo. It produces n − 2 triangles of positive area, whose areas must sum to
  the polygon's within 1e-6. The edit is `Edit(engine="E8", kind="add", new_points=None)` with:
  - `evidence["material"]`;
  - `new_face_uv` (the neighbours' UV map continued) and `new_face_normal`;
  - the mark for R6: `evidence["flat_fill"] = True` and `evidence["loop"]` (the vertex ids).
- **The list.** Every refused hole goes in `not_filled`, with its rule, reason, detail, vertex count, centroid, points
  and the measured value. `report` holds the counts and every hole's inscribed diameter, for the histogram.

Additions beyond the brief's letter. Each one only refuses more, never less:
- `faces_inside`: a post standing in a hole has no open edge inside it, but a fill would cut through it.
- `neighbours_on_both_sides` and `neighbours_face_both_ways`.
- `no_material`: `apply_edits` cannot write an add without a material index.

### Red, then green

The first red run, before the module existed:

```
E   ModuleNotFoundError: No module named 'engine.repair.engines.e8_fill'
ERROR engine/tests/test_e8_flat_fill.py
1 error in 0.98s
```

Green, the 11 tests of items 1 and 2 (one fill, the ear-clipper, and the six refusals of the brief):

```
...........                                                              [100%]
11 passed in 1.03s
```

I added `test_a_hole_a_post_passes_through_is_refused` after the code was written. To see it fail for the right
reason, I ran it with `_faces_inside` patched to return False:

```
engine\tests\test_e8_flat_fill.py:103: AssertionError
FAILED engine/tests/test_e8_flat_fill.py::test_a_hole_a_post_passes_through_is_refused
1 failed, 11 deselected in 0.63s
```

Then, unpatched: `12 passed in 0.89s`.

The tests cover:
- One square hole in a closed slab: 8 points, 6 triangles, no new point, area 400 within 1e-6, faces up, the
  neighbours' UV `(x, y) × 0.05` continued, and open edges 8 → 0.
- An L-shaped (concave) hole: 6 triangles, area 300, open edges → 0.
- `ear_clip` skipping collinear ears.
- Each refusal: a corner raised 3 print steps on a 16-point loop (0.023 in off the plane, against plane_tol 0.02); a
  wall at 90°; two looks; a UV seam (+0.37); a 60 in hole (diameter 60.0); an island inside a hole; and a post
  through a hole.

## Why I stopped: R1 against the data

I ran the engine in plan mode only (no kernel, no Validator) on the BEFOREs and on the E8a outputs. The E8a outputs
are the stage inputs `--engines E8` would give E8b: P2-E8a's own runs in `C:/Temp/e8a/*`, from the code that merged
as 76ca35a. Output saved in `C:/Temp/e8b/probe/r1_measure.txt`:

```
== swA BEFORE: faces 4692; open edges 250, cracks(T-vertices) 550
   components 81: {'open chain': 64, 'branching (a point with 3+ open edges)': 15, 'closed loop': 2}
   E8b: loops 2 -> outer boundaries 2, holes 0, planned 0; not_filled {'not_a_simple_loop': 79}
   chain ends 181: at a T-vertex 49
   open chains: edges per chain {1: 33, 2: 19, 3: 14, 4: 1, 5: 2, 6: 3, 7: 1, 8: 1}
== swA after E8a: faces 4696; open edges 256, cracks(T-vertices) 552
   components 84: {'open chain': 67, 'branching (a point with 3+ open edges)': 15, 'closed loop': 2}
   E8b: loops 2 -> outer boundaries 2, holes 0, planned 0; not_filled {'not_a_simple_loop': 82}
== swB BEFORE: faces 7227; open edges 326, cracks(T-vertices) 559
   components 94: {'open chain': 76, 'branching (a point with 3+ open edges)': 11, 'closed loop': 7}
   E8b: loops 7 -> outer boundaries 2, holes 0, planned 0; not_filled {'not_a_simple_loop': 87, 'self_crossing': 5}
   chain ends 197: at a T-vertex 25
== swB after E8a: faces 7241; open edges 353, cracks(T-vertices) 578
   components 100: {'open chain': 81, 'branching (a point with 3+ open edges)': 12, 'closed loop': 7}
   E8b: loops 7 -> outer boundaries 2, holes 0, planned 0; not_filled {'not_a_simple_loop': 93, 'self_crossing': 5}
== chtm5 BEFORE: faces 20599; open edges 346, cracks(T-vertices) 3884
   components 190: {'open chain': 173, 'closed loop': 4, 'branching (a point with 3+ open edges)': 13}
   E8b: loops 4 -> outer boundaries 3, holes 0, planned 0; not_filled {'neighbour_not_coplanar': 1, 'not_a_simple_loop': 186}
   chain ends 393: at a T-vertex 271
   open chains: edges per chain {1: 132, 2: 25, 3: 13, 4: 7, 5: 4, 6: 1, 7: 4, 8: 1}
== chtm5 after E8a: faces 20624; open edges 373, cracks(T-vertices) 3898
   components 198: {'open chain': 180, 'closed loop': 5, 'branching (a point with 3+ open edges)': 13}
   E8b: loops 5 -> outer boundaries 4, holes 0, planned 0; not_filled {'neighbour_not_coplanar': 1, 'not_a_simple_loop': 193}
```

The open-edge totals equal P2-E8a's `find_errors` figures (sidewalk A 250 → 256, sidewalk B 326 → 353, CHTM-L05
346 → 373; cracks 550 → 552, 559 → 578, 3,884 → 3,898). So the edge set is the right one.

What the closed loops are:
- **Sidewalk B's 5 `self_crossing` loops are bow-ties.** Each has 4 points in a vertical plane x = const, for example
  (2673.25, 22945.0, 1779.53), (2673.25, 22945.0, 1787.91), (2712.62, 22945.0, 1783.9), (2712.62, 22945.0, 1793.74).
  The two sloped sides cross, so these are twisted gaps between two ramp sides, not flat holes.
- **CHTM-L05's one hole** (8 points, centroid (1506.68, 23037.31, 2320.87)) has a neighbour at 90°, so R2 refuses it.
- **Every other closed loop is a patch's outer border.**

The open edges come mostly as **open chains**: 1 to 3 edges whose two ends are dead ends. On CHTM-L05, 271 of the 393
ends are T-vertices. A hole in this model is usually bordered by open edges plus a stretch along another face's edge
(a T-junction side), so its border is never a closed loop of open edges alone.

### What a broader R1 would yield (an upper bound, for the decision only; not built)

I took the open chains with two ends whose closing segment (end to end) lies along an existing non-open edge
(`C:/Temp/e8b/probe/r1_chains.txt`):

```
== swA: ... 'closing segment on an existing edge, planar, with area': 19 ... ; inscribed diameter quantiles [0.64, 6.22, 9.62, 9.68, 10.59, 13.62]
== swB: ... 'closing segment on an existing edge, planar, with area': 17 ... ; inscribed diameter quantiles [2.36, 19.68, 22.14, 26.25, 26.25, 27.22]
== chtm5: ... 'closing segment on an existing edge, planar, with area': 12 ... ; inscribed diameter quantiles [2.28, 4.92, 11.52, 19.69, 19.7, 19.7]
```

I put those through R2-R4 unchanged. Their neighbours are the faces on the open edges plus the faces on the closing
edge (`C:/Temp/e8b/probe/r1_broader.txt`):

```
== swA: open chains closed along an existing edge -> {'R2 neighbour not coplanar': 13, 'no area / not simple': 1, 'not planar': 1, 'would pass R2-R4': 6}
== swB: open chains closed along an existing edge -> {'R2 neighbour not coplanar': 12, 'R4 uv seam': 4, 'not planar': 1, 'would pass R2-R4': 1}
== chtm5: open chains closed along an existing edge -> {'R2 neighbour not coplanar': 9, 'no area / not simple': 18, 'would pass R2-R4': 3}
```

So even with R1 broadened that way, at most **6 / 1 / 3** holes would reach the Validator on sidewalk A, sidewalk B and
CHTM-L05. That is 10 in all, before the hole-or-border, inner-loop and Validator checks. A fill along a T-junction
side also leaves a T-junction where its edge meets the longer edge, so the crack count would not fall.

### The decision needed (controller or owner)

1. **Keep R1 as written.** E8b then fills nothing on the golden units, and every loop goes to E8c. Items 2-4 can still
   be built and tested on fixtures, but the exit's real-run figures and six crops would be empty.
2. **Broaden R1** to "open edges, closed by at most one segment lying along an existing face edge" (or another
   definition). This adds a case the brief does not name. The Validator class (R6: "inside that fill's own loop")
   would then also have to accept a loop with one non-open side.
3. **Re-scope E8b.** Most of the open structure is open chains and cracks, which no flat fill on existing points closes.

Items 2-4 do not depend on R1's definition and need no number changed, so they can go ahead once the controller says
which of these to follow.

## Acceptance commands

- New tests: red, then green (above).
- Full suites on 724300b: see below.
- Golden runs with `--engines E8`: **not run**, because `repair-unit` does not run E8b yet (item 4 is not started).
  The plan-only measurements above take their place for the decision.
- Visual pass: **not done**. No fill exists on any golden unit, so there is nothing to crop.

### Suites

```
engine/tests (on 724300b): 1772 passed, 1 xfailed in 758.72s (0:12:38)
tools/tests:               123 passed in 16.15s
```

Before this job the engine suite had 1,760 tests; the 12 new ones are this job's. The worktree is clean.

## Things I am unsure of, said plainly

- The after-E8a figures come from P2-E8a's own output files (`C:/Temp/e8a/*`), not from a fresh run on 76ca35a. Their
  open-edge and crack counts equal the figures P2-E8a reported.
- The "broader R1" numbers come from a scratch script (`probe_r1c.py` / `probe_r1d.py` in my scratchpad), not from
  committed code. They are an upper bound to help the decision, not a result.

---

# Continuation after ruling R9 (items 2-4)

The coordinator ruled (P2-E8b-R9):
- R1 stays as written.
- The flat fill runs last, after E6, which threads T-vertices into the long edges.
- The four extra refusals are accepted.
- Patch outer borders may stay counted rather than listed, but their count goes in report.json.

Items 2-4 were built test first, one commit per item, in the same worktree and branch.

## Item 2: the Validator's `fill_site` class, commit 62a3666

Files: `engine/validate/checks.py` (the only change in `engine/validate/**`) and
`engine/tests/test_validate_fill_site.py` (8 tests).

The class:
- `FillSite(faces, loop)` is the mark: the fill's AFTER face ids, and the hole's loop points in model coordinates.
- `validate(..., fills=[FillSite])` makes a covered sample `covered_by_fill` instead of `covered` only when both hold:
  - every line of sight that saw it in BEFORE and is blocked in AFTER ends on a marked fill's face;
  - the hit point is inside that fill's own loop: in the loop's plane within the depth tolerance, and inside its
    polygon or within the tolerance of its border.
- A line that still reaches the sample is no loss.
- `covered_by_fill` samples fail neither check. They are counted in `checks.textures.covered_by_fill` and
  `checks.nothing_deleted.covered_by_fill` (outside `reasons` and `covered`), and listed per fill in `fill_sites`:
  `honest`, `why`, `faces`, `samples`, `area_in2`, `before_faces`.
- **The mark is checked, never trusted.** A fill is honest only when:
  - every loop edge is an edge of exactly one BEFORE face (an open border of BEFORE);
  - those faces have one look;
  - the fill is in that look.

  A dishonest fill explains nothing.
- **A behaviour-preserving refactor** lets the class replay every line of sight:
  - the ray building of `_witnesses` moved, unchanged, into `_witness_rays`;
  - `_Judge.covered` became `_Judge.blocker`, which also returns the covering face and the hit point; `covered` calls
    it.

  Measured with no fills: the Validator and site-judge suites pass unchanged (213 passed in 28.50 s).

**My reading of the R6 wording** "every viewpoint line that saw it in BEFORE now ends on a fill" is: every such line
that AFTER BLOCKS must end on a fill. A line that still reaches the sample is not a loss, so it does not disqualify the
sample. This interpretation is lenient only toward samples that stay visible.

Red, then green:

```
E   ImportError: cannot import name 'FillSite' from 'engine.validate.checks'
1 error in 1.08s
--- after the change:
8 passed in 1.24s
```

What each scene gives. The fixture is an open floor (m0) over a room floor (m1) 100 in below. Hole A is 10 x 10 in; a
1 in strip of floor separates it from hole B.

```
proper           check3 PASS covered 0 by_fill 13 overlaid 0 | check1 PASS | sites [] | fill_sites [(True, 13, None)]
one cell larger  check3 FAIL covered 18 by_fill 13 overlaid 0 | check1 FAIL | sites [([50.08, 28.33, -100.0], {'covered': 9}), ([50.42, 55.83, -100.0], {'covered': 8}), ([41.67, 76.67, -100.0], {'covered': 1})] | fill_sites [(True, 13, None)]
unmarked         check3 FAIL covered 13 by_fill 0 overlaid 0 | check1 FAIL | sites [4 sites, all at z = -100, all 'covered'] | fill_sites []
other look       check3 FAIL covered 13 by_fill 0 overlaid 0 | check1 FAIL | sites [the same 4 sites] | fill_sites [(False, 0, 'the fill is in another look than its neighbours')]
```

- The three mutations of the brief FAIL check 3, each by `covered` samples on the room floor (z = -100).
- The one-cell-larger fill's extra 18 samples lie under hole B, outside loop A.
- A fourth test makes the declared loop round hole A plus the strip. That loop is not an open border of BEFORE, so the
  fill is not honest and the check FAILs.

## Item 3: kernel wiring and the engine choice, commit 4867c6b

Files:
- `engine/repair/kernel.py`, `engine/site_judge.py`, `engine/cli.py`;
- `engine/tests/fixtures/holes.py` (`floor_over_room`);
- `engine/tests/test_e8_flat_fill_kernel.py` (8 tests).

The kernel:
- An E8 add whose evidence carries `flat_fill` and `loop` is a flat fill. Its edit-log line gets `flat_fill: true` and
  `loop`.
- `_site_parts` also returns the kept fills (AFTER face ids and loop points). Every check run hands them to
  `judge.check(after, focus, fills=...)`, only when there are some, so the P1 fake judges still fit.
- `SiteJudge.check` turns them into `FillSite`s.
- The run record gets `covered_by_fill`.
- Each fill is its own site, and a charged fill is rolled back by the existing rule.

**One kernel behaviour change: a non-legacy stage that planned no edit writes no check line** to `edit_log.jsonl`. Its
record stays in `KernelResult.checks` and in report.json's `stages`. This was needed because `--engines E8` is now two
stages. The existing test `test_repair_unit_writes_the_fixed_obj_the_edit_log_and_the_report` asserts one check line;
on that fixture E8b finds nothing left after E8a. No existing test was edited.

The CLI:
- `REPAIR_ENGINES = ("E8", "E8a", "E8b")`. `E8` runs E8a, then E8b; `E8a` or `E8b` runs one; the stages always run in
  that order.
- The E8a report (`sites`, `pieces`, `solidify`) is computed from E8a's own edits and check, because the site ids of
  the two stages overlap.

Red, then green:

```
E       ValueError: not enough values to unpack (expected 1, got 0)   <- the fill was rolled back: no mark reached the judge
E       AssertionError: assert (0 == 0 and ['E8'] == ['E8', 'E8b']
E           ValueError: repair-unit runs only ('E8',); not ['E8a']
E       AssertionError: assert ('E8a' in 'usage: python -m engine.cli repair-unit ...
5 failed, 3 passed in 3.57s
--- after (with the existing repair-unit CLI tests):
19 passed in 4.69s
--- kernel, site judge, E8a, add-only-E8 and repair-types suites:
231 passed in 122.76s (0:02:02)
```

Three tests passed before the change, and that was expected:
- the dishonest fill and the unmarked fill are rolled back today too;
- the three-skirts one-check-line test passed because E8 was one stage then.

They guard the new behaviour.

## Item 4: report.json `fills`, `not_filled` and `fill_stats`, commit f00a7f3

Files:
- `engine/cli.py`;
- `engine/fill_review.py` (new; outside both packages, like `site_judge.py`);
- `engine/tests/test_cli_repair_unit_fills.py` (4 tests).

What report.json gets:
- **`fills`:** one row per kept fill: `site`, `loop`, `vertices`, `area`, `inscribed_diameter`, `look`, `centroid`,
  `normal`, and `crop` (`fills/fill-<site>.png`).
- **The crop:** BEFORE | AFTER, 256 px each with a 4 px gap. It is orthographic, looking straight at the hole from the
  side its neighbours face, so the view goes through the hole. It is drawn with the Validator's evidence renderer,
  with the loop outlined in yellow.
- **`not_filled`:**
  - every hole E8b refused, with its rule and reason, the four accepted extra reasons included;
  - every fill the site check rolled back: rule `E8b-R7`, reason `charged` with the Validator's reasons as `detail`,
    or `stage_rolled_back`.
- **`fill_stats`:**
  - `open_edges`, `components`, `loops`, `outer_boundaries` (patch borders, counted only), `holes`, `planned`,
    `kept`, `rolled_back`;
  - `not_filled_by_reason`, `plane_tol`, `max_diameter`;
  - `diameter_histogram` (bins 0-5, 5-10, 10-20, 20-39.37, 39.37-80, 80-160, >160 in).

Red, then green:

```
E       KeyError: 'fills'   (x4)
4 failed in 2.54s
--- first green attempt: IndexError in fill_review._half (the look table was read before face_look_ids filled it); fixed
4 passed in 2.77s
--- CLI area (fills, repair-unit, the flat-fill kernel tests, test_cli.py):
83 passed in 65.55s (0:01:05)
```

The brief's test 4 is `test_one_fillable_and_one_refused_hole_give_one_fill_and_one_not_filled_row`. On
`floor_over_room`, `--engines E8` gives:
- exit 0;
- one fill: 8 points, area 400, diameter 20.0, look `material:m0`, normal (0, 0, 1);
- one `not_filled` row: E8b-R3 `too_wide`, 24 points;
- 2 outer borders counted;
- the edit log has the fill as an `add` with `n_new_points` 0 and `flat_fill` true.

**Visual check of the crop** (`C:/Temp/e8b/croptest/out/fills/fill-0002.png`, viewed). The left half (BEFORE) shows
the room's blue floor through the square hole in the grey floor. The right half (AFTER) shows the hole closed in the
floor's own grey, flush with it. The yellow outline marks the same square in both halves.

The first version drew a 1 px outline, which vanished when the picture was viewed scaled down; it is now 2 px.

## Golden-unit runs with `--engines E8` (wiring on real data; 0 fills expected)

Commands, from the worktree root with `PYTHONPATH` set:

```
"$PY" -m engine.cli repair-unit --snapshot ".../data/snapshots/ce26e0392ab0" --engines E8 --out C:/Temp/e8b/swA --materials ".../data/campus/materials.json"
"$PY" -m engine.cli repair-unit --snapshot ".../data/snapshots/0b290ec0bcb4" --engines E8 --out C:/Temp/e8b/swB --materials ".../data/campus/materials.json"
"$PY" -m engine.cli repair-unit --unit CHTM-L05 --engines E8 --out C:/Temp/e8b/chtm5 --map ".../data/campus/campus_map.json" --source ".../data/campus/source.json" --materials ".../data/campus/materials.json"
```

Output (the rolled-back site lists are cut short):

```
CHTM_SIDE_WALK_2nd_floor: check E8 (E8, 66 edits, 66 sites): FAIL -> PASS; failing 3293 {'covered': 2937, 'overlaid': 2, 'uv': 354}; unknown 0; rolled back [...]; 2 run(s), 30.4 s
CHTM_SIDE_WALK_2nd_floor: check E8b (E8b, 0 edits, 0 sites): PASS -> PASS; failing 0 {}; unknown 0; rolled back [...]; 0 run(s), 0.0 s
CHTM_SIDE_WALK_2nd_floor: site checks done in 61.1 s (the whole kernel run)
CHTM_SIDE_WALK_2nd_floor: E8 built 66 pieces (59 walls, 7 bottoms); kept 4, rolled back 62 {'covered': 57, 'overlaid': 6, 'uv': 54}
CHTM_SIDE_WALK_2nd_floor: E8b found 2 closed loops (2 patch outer borders, 0 holes) among 84 pieces of open edges; filled 0, rolled back 0; not filled {'not_a_simple_loop': 82}
CHTM_SIDE_WALK_2nd_floor: covered after rollback 0; 4692 -> 4696 faces; 61.16 s; wrote C:\Temp\e8b\swA
swA exit 0 wall 63 s

CHTM_2nd_to_3rd_building_sidewalk_outside: check E8 (E8, 56 edits, 54 sites): FAIL -> PASS; failing 8408 {'covered': 8118, 'uv': 290}; unknown 0; rolled back [...]; 2 run(s), 140.4 s
CHTM_2nd_to_3rd_building_sidewalk_outside: check E8b (E8b, 0 edits, 0 sites): PASS -> PASS; failing 0 {}; unknown 0; rolled back [...]; 0 run(s), 0.0 s
CHTM_2nd_to_3rd_building_sidewalk_outside: site checks done in 174.3 s (the whole kernel run)
CHTM_2nd_to_3rd_building_sidewalk_outside: E8 built 54 pieces (40 walls, 14 bottoms); kept 10, rolled back 44 {'covered': 43, 'uv': 38}
CHTM_2nd_to_3rd_building_sidewalk_outside: E8b found 7 closed loops (2 patch outer borders, 0 holes) among 100 pieces of open edges; filled 0, rolled back 0; not filled {'not_a_simple_loop': 93, 'self_crossing': 5}
CHTM_2nd_to_3rd_building_sidewalk_outside: covered after rollback 0; 7227 -> 7241 faces; 174.42 s; wrote C:\Temp\e8b\swB
swB exit 0 wall 175 s

CHTM-L05: check E8 (E8, 216 edits, 209 sites): FAIL -> PASS; failing 16077 {'covered': 13350, 'overlaid': 41, 'deleted': 12, 'uv': 2674}; unknown 0; rolled back [...]; 2 run(s), 1030.1 s
CHTM-L05: check E8b (E8b, 0 edits, 0 sites): PASS -> PASS; failing 0 {}; unknown 0; rolled back [...]; 0 run(s), 0.0 s
CHTM-L05: site checks done in 1128.3 s (the whole kernel run)
CHTM-L05: E8 built 209 pieces (97 walls, 112 bottoms); kept 8, rolled back 201 {'covered': 192, 'deleted': 69, 'overlaid': 154, 'uv': 187}
CHTM-L05: E8b found 5 closed loops (4 patch outer borders, 0 holes) among 198 pieces of open edges; filled 0, rolled back 0; not filled {'neighbour_not_coplanar': 1, 'not_a_simple_loop': 193}
CHTM-L05: covered after rollback 0; 20599 -> 20624 faces; 1128.85 s; wrote C:\Temp\e8b\chtm5
chtm5 exit 0 wall 1130 s
```

`fill_stats` from each report.json:

```
swA exit 0 | fills 0 | not_filled rows 82 | stages [('E8', 66, 'PASS'), ('E8b', 0, 'PASS')] | seconds {'before': 0.03, 'kernel': 61.06, 'total': 61.16}
   fill_stats {'open_edges': 256, 'components': 84, 'loops': 2, 'outer_boundaries': 2, 'holes': 0, 'planned': 0, 'kept': 0, 'rolled_back': 0, 'not_filled_by_reason': {'not_a_simple_loop': 82}, 'plane_tol': 0.02} histogram [0, 0, 0, 0, 0, 0, 0]
swB exit 0 | fills 0 | not_filled rows 98 | stages [('E8', 56, 'PASS'), ('E8b', 0, 'PASS')] | seconds {'before': 0.05, 'kernel': 174.29, 'total': 174.42}
   fill_stats {'open_edges': 353, 'components': 100, 'loops': 7, 'outer_boundaries': 2, 'holes': 0, 'planned': 0, 'kept': 0, 'rolled_back': 0, 'not_filled_by_reason': {'not_a_simple_loop': 93, 'self_crossing': 5}, 'plane_tol': 0.02} histogram [0, 0, 0, 0, 0, 0, 0]
chtm5 exit 0 | fills 0 | not_filled rows 194 | stages [('E8', 216, 'PASS'), ('E8b', 0, 'PASS')] | seconds {'before': 0.35, 'kernel': 1128.34, 'total': 1128.85}
   fill_stats {'open_edges': 373, 'components': 198, 'loops': 5, 'outer_boundaries': 4, 'holes': 0, 'planned': 0, 'kept': 0, 'rolled_back': 0, 'not_filled_by_reason': {'neighbour_not_coplanar': 1, 'not_a_simple_loop': 193}, 'plane_tol': 0.002} histogram [0, 0, 0, 0, 0, 0, 0]
```

What these show:
- All three exit 0, with 0 fills, as expected.
- The E8a stage gives P2-E8a's own figures exactly: kept 4/66, 10/54 and 8/209, with covered after rollback 0.
- E8b runs on E8a's kept output: 256, 353 and 373 open edges, the P2-E8a after-figures.
- The diameter histogram is empty because no loop reached R3: CHTM-L05's one hole is refused at R2 first.
- E8b itself takes no measurable time (0 runs).

Time: 63 s, 175 s and 1,130 s. That is longer than P2-E8a's 39, 112 and 858 s for the same E8a stage, and the extra
time is all in E8a's focus runs (CHTM-L05: 1,030 s against 799 s). This is unverified; I believe it is load on the
shared PC, since the E8a code path is unchanged.

## Full suites on f00a7f3

```
engine/tests: 1792 passed, 1 xfailed in 789.05s (0:13:09)
tools/tests:  123 passed in 13.99s
```

That is 1,760 before the job plus 32 new tests: 12 for the engine, 8 for `fill_site`, 8 for the kernel and CLI wiring,
and 4 for the report fields. The worktree is clean.

## Concerns, said plainly

1. **A kernel behaviour change outside the brief's letter.** A non-legacy stage that planned no edit no longer writes a
   check line to `edit_log.jsonl`; its record stays in `checks` and `stages`. Without it, the existing CLI test that
   asserts one check line for `--engines E8` would have to change.
2. **The R6 reading.** I read "every viewpoint line that saw it" as every line AFTER blocks; a line that still reaches
   the sample does not disqualify it. On top of the brief, the Validator checks the mark itself: the loop must be an
   open border of BEFORE in one look, and the fill must be in that look.
3. **Refactors in the Validator.** `_witness_rays` and `_Judge.blocker` were factored out of `_witnesses` and
   `_Judge.covered` with no change of behaviour (the Validator and site-judge suites passed unchanged). They are still
   edits to `engine/validate/checks.py` beyond the new class, so a reviewer should look at them.
4. **The fill path is proven on fixtures only.** On real data E8b found 0 holes, so `fill_site`, the crops and the
   rolled-back rows have only run on fixtures until E6 lands.
5. **Coarse print step in the CLI fixtures.** Those fixtures round-trip through OBJ with integer coordinates, so their
   print step is 1 in (plane_tol 2 in). The real units have plane_tol 0.02 and 0.002 in.
6. **Times (unverified).** The golden runs took longer than P2-E8a's, all inside E8a's unchanged focus runs; I believe
   that is machine load.

---

# Fix round 1 (review: Spec PASS, Quality APPROVED; rulings P2-E8b-R10 and R11)

There is one commit per numbered item, each test first, on claude/P2-E8b.

## 1. Every stage writes its check line (ruling R10), commit cae238c

The kernel.py change that skipped the check line of a non-legacy stage that planned nothing is reverted. The edit log
is the audit trail.

**Edit to an existing test, sanctioned by R10:** `engine/tests/test_cli_repair_unit.py::
test_repair_unit_writes_the_fixed_obj_the_edit_log_and_the_report` now asserts
`sum("check" in line for line in lines) == 2` (one line per stage, since E8 runs E8a then E8b), where it was `== 1`.

My own tests changed with it:
- `test_a_stage_that_planned_nothing_still_writes_its_check_line` expects the E8b check line with `edits` 0.
- `test_repair_unit_e8_on_a_slab_e8a_closes_writes_one_check_line_per_stage` expects the stages `["E8", "E8b"]`.

```
--- red (tests changed, kernel not yet reverted):
FAILED engine/tests/test_e8_flat_fill_kernel.py::test_a_stage_that_planned_nothing_still_writes_its_check_line
FAILED engine/tests/test_e8_flat_fill_kernel.py::test_repair_unit_e8_on_a_slab_e8a_closes_writes_one_check_line_per_stage
FAILED engine/tests/test_cli_repair_unit.py::test_repair_unit_writes_the_fixed_obj_the_edit_log_and_the_report
3 failed, 16 passed in 5.58s
--- green (with the kernel's site-check, edit-log and rollback suites):
47 passed in 13.34s
```

## 2. The floor Validator receives the fills (ruling R11), commit 43071bd

Each flat-fill line of `edit_log.jsonl` now carries two more fields:
- `loop_points`: the loop in model coordinates.
- `after_faces`: the fill's face ids in the shipped AFTER.
  - The kernel computes them from the stage's kept result and carries them through any later non-legacy stage.
  - A rolled-back fill gets `[]`; a later legacy stage would make them `null`.
  - The OBJ writer keeps face order, so the ids hold in the written OBJ.

`engine.cli validate` gains `--edit-log <path>`:
- `fills_from_edit_log` reads the kept fills and hands them to the Validator.
- It refuses (exit 2, nothing written) a log whose fill faces are not, in the AFTER, faces with every corner on the
  loop's points.
- `validation.json`'s `inputs` names the edit log.

```
--- red:
E       KeyError: 'loop_points'
E       TypeError: cmd_validate() got an unexpected keyword argument 'edit_log'   (x2)
E       SystemExit: 2                                                             (the parser has no --edit-log)
4 failed in 1.67s
--- green:
5 passed in 2.34s     (with a fifth test: a rolled-back fill's line has after_faces [] and its loop_points)
--- with the kernel, CLI and refuse-protected suites:
215 passed in 119.61s (0:01:59)
```

The test the ruling asked for is `test_validate_with_the_edit_log_passes_check_3_by_fill_and_without_it_fails`. It
repairs `floor_over_room` with E8b from a snapshot folder, then validates the fixed OBJ against the snapshot:
- with `--edit-log`: check 3 PASS, covered 0, covered_by_fill > 0;
- without it, the same pair: check 3 FAIL, covered > 0.

## 3. The Validator re-measures R2 and R3 (AGENTS.md section 6), commit 5705df6

`_fill_shape_refusal` adds to the honesty check. The Validator keeps its own constants (`FILL_MAX_DIAMETER = 39.37`,
`FILL_NORMAL_TOL_DEG = 1.0`) and imports nothing from the engine. A marked fill is not honest when any of these holds:
- a face round the hole has no area;
- a face round the hole is more than 1° off the loop's plane, or has a corner more than the depth tolerance out of it;
- the loop crosses itself;
- the inscribed diameter plus 2 × polylabel's tolerance (0.005 in) is over 39.37 in.

The two new mutations:
- **A fill over a box's open bottom with walls at 90°.** The box is wound inward, so its inside's fronts are seen only
  through the opening. A first version wound the box outward; it covered nothing, and check 3 passed whatever the
  honesty check said.
- **A fill over a 60 in (1.52 m) hole over the room.**

```
--- red, run with _fill_shape_refusal patched to return None (the round's starting point):
FAILED engine/tests/test_validate_fill_site.py::test_mutation_a_fill_over_a_box_s_open_bottom_with_walls_at_90_degrees_fails_check_3
FAILED engine/tests/test_validate_fill_site.py::test_mutation_a_fill_over_a_hole_1_5_m_wide_fails_check_3
2 failed, 8 deselected in 0.54s     (both: assert ('PASS' == 'FAIL'))
--- green:
10 passed in 1.19s
--- the Validator, site-judge and fill suites:
219 passed in 29.94s
```

Measured on the box: the marked fill gives check 3 FAIL, covered 160, covered_by_fill 0, honest False. The reason
reads "90.000 deg and 30.0000 in off its plane".

## 4. Without fills, validation.json is unchanged, commit 267909b

`fill_sites`, `checks.textures.covered_by_fill` and `checks.nothing_deleted.covered_by_fill` are written only when
fills are given; None and an empty list write none of them. The site judge copies `covered_by_fill` only when it is
there; the kernel already reads it with a default of 0.

The new test `test_without_fills_validation_json_is_byte_for_byte_the_76ca35a_validator_s` loads the 76ca35a
`engine/validate/checks.py` with `git show`. It compares `json.dumps(report, indent=2)` bytes, timings aside, on an
existing case: a cube with one visible face deleted (check 3 FAIL, with sites). The test skips only when git cannot
show 76ca35a.

```
--- red:
E       AssertionError: no fills: no fill keys (fix round 1)
E           AssertionError: assert ('fill_sites' not in {...})
E       assert b'{\n  "versi...": []\n  }\n}' == b'{\n  "versi...": []\n  }\n}'
E         At index 389 diff: b'c' != b'd'          <- the old report has no covered_by_fill there
--- green (the Validator, site-judge, kernel-site-check and fill suites):
236 passed in 35.12s
```

I also edited my own earlier tests in this file, which expected the keys to be present and zero; they now expect them
absent.

## 5. Small items, commit e98d3b1

- `cli.fill_diameter_bins()` builds the histogram's edges from `e8_fill.FILL_MAX_DIAMETER`, read when called. It
  replaces the `FILL_DIAMETER_BINS` constant.
- A neighbour face with no area is refused as `neighbour_degenerate` (E8b-R2), and the report gets no NaN. Before the
  fix such a face slipped past R2 as NaN and was refused later, as `neighbours_on_both_sides`.
- R3 compares `diameter + 2 * _POLYLABEL_TOL` against the cap. A 39.37 in square hole is now refused; a 39.3 in one is
  still filled.

```
--- red:
E       AssertionError: a refused loop is left unfilled            (the 39.37 in hole was filled)
E       AssertionError: assert ('E8b-R1', 'n...n_both_sides') == ('E8b-R2', 'n...r_degenerate')
E       AttributeError: module 'engine.cli' has no attribute 'fill_diameter_bins'
--- green (engine, fills CLI, kernel and edit-log fill suites):
32 passed in 6.71s
```

The degenerate test monkeypatches the topology. `analyse_topology` leaves zero-area faces out, so the test flattens a
neighbour only in the positions the engine measures.

## Wiring check: sidewalk A, `repair-unit --engines E8`

```
CHTM_SIDE_WALK_2nd_floor: check E8 (E8, 66 edits, 66 sites): FAIL -> PASS; failing 3293 {'covered': 2937, 'overlaid': 2, 'uv': 354}; unknown 0; rolled back [...]; 2 run(s), 26.8 s
CHTM_SIDE_WALK_2nd_floor: check E8b (E8b, 0 edits, 0 sites): PASS -> PASS; failing 0 {}; unknown 0; rolled back [...]; 0 run(s), 0.0 s
CHTM_SIDE_WALK_2nd_floor: site checks done in 51.9 s (the whole kernel run)
CHTM_SIDE_WALK_2nd_floor: E8 built 66 pieces (59 walls, 7 bottoms); kept 4, rolled back 62 {'covered': 57, 'overlaid': 6, 'uv': 54}
CHTM_SIDE_WALK_2nd_floor: E8b found 2 closed loops (2 patch outer borders, 0 holes) among 84 pieces of open edges; filled 0, rolled back 0; not filled {'not_a_simple_loop': 82}
CHTM_SIDE_WALK_2nd_floor: covered after rollback 0; 4692 -> 4696 faces; 52.11 s; wrote C:\Temp\e8b\fix1_swA
swA exit 0 wall 53 s
```

The edit log has 2 check lines (E8 and E8b), as R10 requires.

## Full suites on e98d3b1

```
engine/tests: 1803 passed, 1 xfailed in 720.95s (0:12:00)
tools/tests:  123 passed in 14.17s
```

The worktree is clean.

## Still open, said plainly

- E8a's stage is named "E8" and E8b's "E8b". This is parked, as the coordinator asked.
- `after_faces` relies on the OBJ writer keeping face order. It does today (one `f` line per face, in order).
  `fills_from_edit_log` refuses a log whose ids do not land on the fill.
- The byte-comparison test needs git history containing 76ca35a; it skips, rather than fails, without it.
