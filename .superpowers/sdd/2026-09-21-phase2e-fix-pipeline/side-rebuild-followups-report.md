# Side rebuild follow-ups (brief 10, with review part 2), 2026-09-25

Main checkout, branch `feat-dashboard`, from e27eb79. Brief:
`docs/superpowers/records/briefs/10-side-rebuild-followups.md`, items 1-8 and the review part 2 items
(`review-side-rebuild.md`) the coordinator added mid-task, R2-C1 and R2-C2 first. Item 9 is the
owner's decision and was not touched. Every number below was measured in this session, on the
snapshots `ce26e0392ab0` (A) and `0b290ec0bcb4` (B), with `.venv/Scripts/python.exe`. The one
exception is the 0f24da4 column of section 7, which is taken from the brief.

**Status: DONE_WITH_CONCERNS.** Every item has a commit or a traced answer. Both files pass, neither
merge rolls back, and the runs are deterministic (the final runs' `report.json` and `fixed.obj`
are byte-identical to the run before them). The concerns are at the end. The biggest ones:
- A's owner `.skp` could not be replaced: SketchUp has it open (Errno 13).
- A's back faces seen from outside are 608 pixels above e27eb79. C2 removed walls that were invented
  under a real underside, and those walls had been hiding the margin strip's reversed cells.
- B's walkway arm is only partly closed from below (triage B1).

| Commit | Item |
|---|---|
| 9f64ae9 | item 1 `fix(engine): the cap guard judges a slab's new shell together` |
| c2b1611 | item 2 `fix(engine): max_thickness is set from the files' own side depths` |
| 8c729c1 | R2-C2 = item 3 `fix(engine): top or underside is decided by looking below and above` |
| 3561127 | R2-C1 (+ M3) `fix(engine): the side rebuild never leaves a new face on a piece it gave back` |
| 01cc420 | R2-I1 `fix(engine): a piece belongs to the slab, and a wall keeps its side's look` |
| 444d0ef | R2-I2 `fix(engine): a lower surface is where the slab's own sides end` |
| 170141f | R2-M1 `fix(engine): an opened crack is measured across, and only the sky or an exposed side may show` |
| eb920df | R2-M5 `test(engine): the plan reports its replaced pieces, and the plate beside the box ships` |
| c56018d | R2-M4 `docs(engine): docstrings the side rebuild left stale` |
| f7e27d1 | item 6 (triage B1) `fix(engine): a block standing on a slab is not an underside; the slab runs on beneath it` |

Other sessions committed three record commits in between (855848d, 62846f6, 0e88d8c). They are not
mine.

**Suite:** the full engine suite had 542 passing at e27eb79. At f7e27d1 its final line is
`566 passed in 199.63s (0:03:19)`.

## 1. Item 1: the cap guard judges a slab's new shell together (9f64ae9)

**Cause.** Every cap-guard rule read what the INPUT showed at a pixel, which is a mesh without any
new face. So each new face was judged as if the rest of its shell did not exist.
`slab_beside_a_lower_top`, with the guard on:
- round 0 refused the plate's 2 bottom faces, which cover the box's underside seen through the
  wall's opening (outside the plate);
- round 1 refused the 2 wall faces, which cover the same underside through the bottom's reopened gap;
- nothing of the shell was kept.

**Rule 6, named and counted (`through_shell_px`):**
- A pixel's ray meets its new face on the FRONT (from outside), crosses the inside of a slab, and
  leaves through another new face kept in the same state, met on its back, before BEFORE's hit.
  What BEFORE showed there was seen THROUGH that slab, and the slab is now a solid.
- The path is sampled (every 2 in, 3 to 32 points), and every sample must be `INTERIOR_INSIDE`. So a
  fin under a slab keeps the per-face refusal.
- **Refused together** (`_refuse_together`): when a round refuses the face a rule-6 pixel leaves
  through, the pixel is re-cast in the same round against the shell that is left. If it no longer
  leaves through a kept face, its new face is refused too (or the replaced piece it covers is
  restored), until nothing more falls.
  - The re-cast is exact: a ray beyond a refused step wall that still leaves through the lower
    slab's wall keeps its face. Test: a naive closure fails it.
  - It took B's cap guard from 9 rounds (the cap is 8) to 5, with identical shipped meshes.

**`_underside`.** It no longer takes a floor below a slab's sides for the slab's existing bottom.
This is the limit `_lower_surface` already had (review I1).

**Tests** (fixture `slab_with_fins_beside_a_post` appended):
- The three tests SR6 left checking only the plan now go through the guard: the rewritten SR5
  test, the floor test, and the underside-edge test.
- The whole shell is refused together when one wall is refused.
- A fin below the slab is still refused face by face, and the post beyond it never changes.
- Unit tests of `_through_closed_shell` and `_refuse_together`.
- Mutation: removing the path check fails the unit test (`[True, True, False]` against
  `[True, False, False]`).

**A test that changed with the requirement.** SR2's `test_a_railing_seen_through_an_open_slab_is_never_covered`
asserted that a railing seen THROUGH an open slab never changes. Only an open slab can satisfy
that, which is the opposite of this item. It is rewritten, not weakened
(`..._is_hidden_only_through_the_closed_slab`):
- the railing is never replaced;
- a pixel of it changes only where the line of sight to it crosses the slab's volume, and that
  count is exactly 0 elsewhere.

**Real data.** A 1,062 triangles, back faces from outside 18,868 (20,945 at e27eb79). B 532 and
4,480 (5,993). Ramp close-up 574 / 1,431 / 610 (948 / 2,674 / 590).

## 2. Item 2: `max_thickness` from the files (c2b1611)

**Measured.** Every OWN side (how far it reaches below the outline edge it hangs from, weighted by
the length it runs), with solidify's own planning:

| | A: 21,761.3 in over 138 regions | B: 28,019.4 in over 88 regions |
|---|---|---|
| p50 / p90 / p99 / max | 9.84 / 29.52 / 49.21 / 49.21 | 9.84 / 39.37 / 39.37 / 51.67 |
| (0, 10] | 84.8 % | 72.0 % |
| (20, 30] | 9.9 % | 2.6 % |
| (36, 39.39] | 0.4 % | 13.0 % |
| > 45 | 4.4 % (all 49.21) | 0.1 % (one 51.67 run) |

- Representative depths above 36 in: A 852 (49.21) and 857 (39.37); B 92, 107, 115, 174 and 310
  (39.37).
- The deepest slab is A's region 852, at 49.21 in by all 816.9 in of its own side. No side face of
  A stands taller.
- B region 820's 51.67 in run covers 39.4 of its 157.6 in (representative depth 22.14), so it is
  not a slab's depth.
- **The ceiling is 50 in** (it was 36). It sits above every slab of both files and still clamps that
  run and any deeper fin.

Tests: a 39.37 in block and a 49.21 in block keep their depth; a 60 in side is clamped.

**Real data.** B: back faces 4,480 -> 3,178; region 92's volume over the 26 guard views 1,434 -> 189.
A: one more side piece replaced, nothing else changed.

## 3. R2-C2 = item 3: top or underside, by looking below and above (8c729c1)

**Cause.** SR6 counted a no-sky region that a top runs into as an underside only when EVERY own side
of it stands up. One hanging side made it a top: a bottom was invented under it, and the hidden
pass deleted the real underside.
- The review's probe shipped 1,600 sq in of invented floor 8 in low, with `passed = True`.
- **On file A it fired at region 33.** All 16 of its faces (19,777 sq in, exposure 0.46 on the
  input) were deleted under its own invented walls and bottom, 29.52 in deep. That is the depth of
  a neighbour's side hanging along the edge it shares with the top.
- The review's suspects 467, 166 and 244 were processed as tops at e27eb79, but their bottoms were
  refused and 0 of their faces were deleted. So C2 had not fired there.

**Rule (`_is_underside`).**
- **Below:** no own side hangs `min_thickness` or more below an edge the region does NOT continue
  across. A side along a continued edge is the neighbour's.
  - Measured on A: the real tops under the upper landing, 9 and 784, hang 29.52 in from such edges
    (68.9 in and 49.2 in of side).
  - The slivers beside undersides hang 1.1-1.21 in (467, 166).
  - Region 33 hangs nothing there (its 29.6 in of hanging side all lies along a continued edge).
- **Above:** at least half of the rays straight up (4 per face) meet a sky-seeing surface within
  `max_thickness + side_band`.
  - Regions 33, 467, 166, 244 and 502: 66-100 % do, at the 9.8 in depth of the slab above.
  - Region 784 meets region 6, which is not sky, so it stays a top.
- This also answers **item 3** (region 33 at ratio 22.9 against 9 and 784): the ratio is not the
  test, the side along a continued edge is.
- It also answers **review M2** (`probe_real_top_taken_for_underside.py`): the floor under the
  landing is a top again, its open sides are walled, and it gets its bottom.

Tests: the probe as a regression test (B's underside ships whole, 1,600 sq in at z 0, 0 at -8), and
M2.

**Real data.**
- Undersides: A 64 -> 78 of 99 continued regions; B 5 -> 7 of 23.
- Region 33 ships whole.
- The big landing's row of shards, its long thin diagonal and the walkway notch in SketchUp's view
  from below are gone. They were walls and bottoms invented under 467, 166 and 244.
- A's back faces rose 18,868 -> 22,029: those walls, hanging 2.91 in under 467, had hidden the
  margin strip's reversed cells (section 6, A1).

## 4. R2-C1: no double layer of the rebuild's own making (3561127)

- Before every cap-guard round, and before the verification, the guard refuses every kept new face
  lying ON a piece present in that state (`lies_on_a_restored_piece`, counted as
  `refused_on_pieces`), until none is left.
- A new face lying on a new face another group built before it is refused before any pixel is
  judged. This is one bottom per footprint.
- `side_pieces_given_back` counts the pieces given back because their wall, or the bottom over
  them, lost a face (M3): A 32, B 113.

Tests: the three probes are regression tests, one at 2000 in scale, and one in the top's own
material. Double layers are 0; they were 21.33, 14.46 and 1,600 sq in.

**Real data.** A 933 triangles, back faces 21,830. B 508 and 3,001. **B's final-guard z-fight ties
46 -> 0** (item 4). Region 92's volume 189 -> 7 back pixels.

## 5. R2-I1, R2-I2, R2-M1, M4, M5

- **I1 (01cc420).**
  - A piece must be ATTACHED to the slab: its connected part of the side reaches the top edge or
    the wall's foot, within the depth tolerance. The sign 1.2 in in front of a missing side ships
    at 2000 in scale; the teeth and the ramp's low pieces are still taken.
  - A wall takes the material, and the UV scale, of the side it replaces. On a side of several
    edges, a wall replacing nothing takes the look of the walls along the same side. The concrete
    side ships as 320 sq in of m1.
  - B: 388 sq in of rebuilt side moved from the top's `ltstone_-5` to `ltstone_-3`, the side it
    replaces. A unchanged.
- **I2 (444d0ef).**
  - A lower surface is the slab's only where the most of its own side length ENDS on it
    (`_sides_end_on`, each side's foot measured locally against the surface's plane). The same
    applies to `_underside` (`_ends_here`).
  - A side whole at its own depth is never extended down to it.
  - `lower_surface_deeper_than_sides` reports A 12 regions and B 7, among them the ramp (39.37
    against 33.74 in).
  - The bench and the floor's top ship.
  - On the real files it keeps B's ramp (49 % of its own side ends on its underside) and drops A's
    inner plates (171, 358, 376: a plate 3.5 in down, their sides ending at 7.03 in).
  - A 917 triangles, 21,553. B's shipped geometry is face-for-face unchanged (6 more bottoms were
    built where a partition had passed for one, and were then hidden).
- **M1 (170141f).**
  - The opened crack is measured ACROSS it, in BEFORE's own plane and material: the crack is no
    wider than the tolerance when the point `tol - d` further on, away from the nearest surface,
    lies on that surface again.
  - Only the sky or a side the reference exposed may show through, as the fragment rule reads it.
  - A crack 0.16 in wide along x at slope 0.4 is 0.149 in across and passes; 0.20 in fails.
  - The existing 0.02 in test now says what shows through; the requirement changed.
  - Both files are byte-identical to the previous commit.
- **M5 (eb920df).** `_planned` reports the pieces it would replace (pinned on the sawtooth side).
  `slab_beside_a_lower_top`'s test pins what `fix_object` ships.
- **M4 (c56018d).** The stale docstrings are updated: `solidify_feedback`, `cover_max_exposure`,
  and the CLI's `.skp` copy. The session record's cap-guard cell is in docs/, outside `engine/`,
  and is left for the controller.

## 6. Item 6: what the renders showed, spot by spot

Close-ups use the side-rebuild report's method (`side-rebuild/closeup.py`'s section-box renderer),
with the input beside each run's `fixed.obj` and its written `.skp`. They are all in
`scratchpad/brief10/closeups/`. Evidence also came from the visual triage's 84 renders and the 30
SketchUp views of A (item-2 state).

| Spot | Where | Before (e27eb79 / item 2) -> now | Cause | Fixed |
|---|---|---|---|---|
| A: shards along the big landing's edge, the long diagonal, the walkway notch (SketchUp view from below) | big landing underside | present -> gone | walls and bottoms invented under undersides 467, 166, 244 | yes, C2 |
| A1 margin strip, x 2673.2-2683.1 | big landing's east edge | close-up view 0: 1,356 -> 6,938 back px; lines 12 (were 17) | a 9.9 in sloped thin sheet whose cells alternate in winding (572, 552, 573 up; 576, 683, 689, 568, 614 down). The flip leaves thin sheets as they are, so half shows purple from below. Newly visible since C2 removed the invalid walls that hid it | no |
| A2 stepped lines, lower landing underside | z 1582.7 | unchanged; underside closed (close-up view 0 687 back px, as before) | the export's partial bottom (31,907 sq in ships) beside region 11's rebuilt bottom (4,128 sq in of pieces replaced). Coplanar and same material, but they meet along a stepped T-junction border (43 of the 53 drawn edges there are open borders), so they are two regions for the merge | no |
| A3 slot at the curb block | x 1019-1098 | both solids closed (the input's purple strip is gone) | the gap is in the export: two separate solids | not an engine defect |
| A4 jagged perimeter | big landing, lower right | shards gone; purple cells along the edge are A1's | C2 / A1 | partly |
| A5 layers under the lower landing | side view | the hanging plate is gone, the strip cluster reduced | invented faces under undersides | yes, C2 |
| B1 tray, B3 panels and slot | walkway arm | landing end closed; arm's far part still stepped | the 1 m slab under the stairs has no top face of its own (the blocks' bottoms lie in its plane) and no -y side in the input | partly, f7e27d1 |
| B2 stepped fin | under the arm's sloped part (not the ramp) | thin plate gone with C2, triangular fin gone with C1 | invented faces kept on given-back pieces, under undersides | yes |
| B4 junction ticks, B8 knife edge | ramp junction, far-left arm | unchanged | not traced | no |

**B1 (f7e27d1).** An underside a top runs into is where a block STANDS ON the top's slab when all
three hold:
- the top has a measured depth;
- none of the top's own sides hangs along the edges they share;
- the underside lies within the top's outline (0.99 of it inside the convex hull of the top's
  footprint).

Then the edges into it stay continued, and the slab's volume and bottom take in its footprint. Its
faces become the slab's top shell, and its own open edges are walled as the slab's side.

Measured before choosing:
- "no own side hangs" alone flags 15 regions of A, among them 57 and 455, which are real undersides;
- the hull bar leaves none of A (0.00 for both) and selects B's 115, 134, 147, 148 (0.99-1.00);
- the engine takes 3 of them (134 sits at the bar).

Tests: a block inside the slab's top; a block at its edge over a missing side. Mutation: no walls on
the blocks' edges fails the second.

Real data:
- A byte-identical.
- B back faces 3,001 -> 2,787; wall faces refused 116 -> 96; the landing's bottom keeps 41 of 61
  faces (25 of 49 before).
- Region 107's part of the arm keeps only 18 of 40 walls and 20 of 36 bottom faces (refused as
  covering outside the footprint; not traced to the pixel).

## 7. Item 4: the measures that got worse than at 0f24da4

| Measure | 0f24da4 | e27eb79 | now | Explanation |
|---|---|---|---|---|
| reference back px, A | 266,112 | 454,537 | 458,599 | 95.4 % lie on faces the flip step turns before anything ships (B: 99.2 % of 363,610). 225,661 of those are faces of regions now taken for undersides, which invented bottoms hid at 0f24da4. Not a defect: the final count is what ships |
| wall faces refused, A | 157 | 392 | 212 | 27 regions. Mostly walls planned on the margin strip's cells and on small stair regions between the lower walkway and the big landing (550, 572, 576, 637, 480; 709, 289, 755, 308, 171), most with no measured depth. Each covers something outside every slab. The refusal is right; the planning of walls on thin sheets is the excess |
| bottom faces refused, A / B | 108 / 40 | 230 / 61 | 71 / 61 | A is now below 0f24da4. B: 34 outside the footprint (the arm's far part, B1), 19 partial underside (review C1's protection), 6 coincide (one bottom per footprint), 2 lie on a given-back piece |
| B z-fight tie px | 3 | 46 | 0 | the coincident layers C1 removed. Fixed |
| B pieces restored | 3 | 14 | 6 | pieces whose pixel failed. The given-back ones are now counted separately (113) |
| B T-junction lines | 24 (older writer) | 20 | 15 | below 0f24da4 |

The brief quotes 39 tie pixels and 33 T-junction lines for B. Those came from an earlier state. At
e27eb79 this session measured 46 and 20. The SketchUp writer changed between 0f24da4 and e27eb79
(8ee9e4d: it hides lines inside surfaces), so the 0f24da4 line count is not directly comparable.

## 8. Item 5: the ramp's upper-left piece and view 1

It is the section box, not the model. Every one of view 0's back pixels starts INSIDE the landing's
slab: the close-up box begins at x 2640 and the landing ends at 2673.2. The rays meet the landing's
bottom, or the ramp's top, from within.
- e27eb79: 948 of 948.
- Now: 580 of 580.
- View 1: 1,404 of 1,440 now (2,638 of 2,674 at e27eb79). The other 36 enter where the box's floor,
  z 1860, cuts the ramp's far end (its underside is at 1858.27 there).

View 1 is 1,440 now, which meets the ~2,500 target, though that number measures the cut. Seen from
outside (the 26 guard views, the whole model), the ramp's volume shows **3** back pixels: 23,608 in
the input, 21 at e27eb79.

## 9. Item 7: lines inside flat surfaces on A

A had 17 lines at e27eb79 (20.3 ft) and has 12 now (11.2 ft). Traced on the shipped polygons: 13 of
17 then and 8 of 12 now pair to two faces. Every pair but one is coplanar, same material, with
OPPOSITE windings (180 degrees). SketchUp draws the edge between faces of opposite orientation.
- The three long lines along x = 2673.2 at e27eb79 (39.4, 39.3 and 29.5 in) lay between the margin
  strip's down-wound cells (normal (0.147, 0, -0.989)) and the up-wound ones. They are gone now.
  The strip's 9.9 in cross lines remain.
- The rest lie between an invented wall and an export face wound the other way, on the lower
  landing's sides (x 1275.6; y 22669.4; y 22826.9 at x 2582-2594).
- One 1.5 in pair has the same winding and was not traced further.

The cause is the thin sheets the flip leaves as they are (A1). This is not fixed.

## 10. Item 8: sliver 3491

Sliver 3491 is input face 3535: 0.0267 sq in, 0.0044 in wide, in the plane y 22826.9, x 2582.5-2594.5,
facing -y.
- On the pre-merge engine (3d30327, exported read-only), the HIDDEN pass deleted it, together with
  its neighbours 3534, 3536 and 3538 (exposure 0 in that run's reference).
- Since the side rebuild it is exposed. The hidden pass keeps it, and the fragment pass takes it as
  a sliver on an open border. The rays confirm it: 1,082 lines at e27eb79 and 1,114 now, 0 reaching
  an unexposed side.
- The current engine does the same with solidify switched off.

## 11. Real data at f7e27d1

| | A `CHTM_SIDE_WALK_2nd_floor` | B `CHTM_2nd_to_3rd_building_sidewalk_outside` |
|---|---|---|
| triangles in / reference / out | 4,692 / 4,787 / **917** (1,044) | 7,227 / 7,471 / **506** (530) |
| backface_px input / reference / final | 569,108 / 458,599 / **21,553** (20,945) | 464,939 / 363,610 / **2,787** (5,993) |
| sides_rebuilt | 52 edges, 1,503.7 in (92) | 35 edges, 1,163.7 in (35) |
| side pieces replaced / restored / given back | 81 (walls 30, bottoms 51) / 5 / 32 | 79 (walls 45, bottoms 34) / 6 / 113 |
| wall faces refused | 212: outside the footprint 151, below the bottom 40, lies on a restored piece 12, coincides 9 | 96: outside 30, below 25, lies on 23, coincides 18 |
| bottom faces refused | 71: outside 60, lies on 6, partial underside 3, coincides 2 | 61: outside 34, partial underside 19, coincides 6, lies on 2 |
| undersides / blocks on slabs / lower surfaces | 78 of 99 / 0 / 97 regions (72 walls, 21 trapezoids) | 7 of 23 / 3 / 62 (30 walls, 5 trapezoids) |
| cap guard (new, failing, removed, restored, through-shell px) | (447, 5,409, 166, 6, 6,296), (268, 758, 48, 0, 2,410), (218, 728, 33, 0, 897), (183, 144, 7, 0, 45), (176, 0, 0, 0, 4) | (454, 15,446, 87, 44, 3,073), (344, 857, 20, 0, 1,095), (324, 181, 1, 0, 0), (323, 0, 0, 0, 0) |
| ramp close-up, views 0 / 1 / 2 | - | 580 / 1,440 / 6,122 (the section cut, section 8); from outside 3 |
| guard_after_removal | passed; fragment_removed 37 | passed; fragment_removed 10 |
| guard_merge_attempt = guard_final | passed; zfight_tie 1, fragment_removed 37, border_shift 167, grown_base 65 = border_shift_grown 65 | passed; crack_closed 4, fragment_removed 10, border_shift 35, grown_base 5 (border_shift_grown 3, crack_closed_grown 2) |
| merge | 133 regions, none skipped, **not rolled back**; T-vertices 379 -> 0 | 64 regions, 1 skipped (overlap), **not rolled back**; 353 -> 0 |
| invariants / passed | all True / **True** | all True / **True** |
| `.skp` | 540 faces, 1,183 edges, 0 missing, 0 unexpected; **owner copy NOT written: Errno 13** (SketchUp has it open) | 183 faces, 521 edges, 0 missing, 0 unexpected; owner copy written 17:12 |

Model pixels: A 2,058,222, B 2,433,241. Every guard count not listed is 0. preview-data ran for both
(exit 0; guard damaged px 0, flicker px 0, merge not rolled back).

The spot counts over the 26 guard views, from outside:

| Spot | input | e27eb79 | now |
|---|---|---|---|
| the ramp | 23,608 | 21 | 3 |
| B region 92 | 114,298 | 2,939 | 7 |
| A region 11 | 109,590 | 1,688 | 1,649 |

## 12. SketchUp audit (`docs/superpowers/records/scripts/skp_edge_audit.py`)

The final runs' `.skp` files are below. B's owner copy is the file below (same sha256, written 17:12).

A's owner copy is still the item-2 run's file (c2b1611). It was written at 11:50, and its sha256
matches that run's output. Audited, it reads 636 faces, 1,421 edges, and 17 lines inside flat
surfaces (20.3 ft). Every A run since the C2 run at 12:22 failed to replace it with Errno 13,
because SketchUp holds it open.

```
CHTM_SIDE_WALK_2nd_floor.fixed.skp: 540 faces, 1183 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)      12      11.2 ft
  hidden (soft)                                                    381    2788.7 ft
  visible, non-manifold (3+ faces)                                  68     136.0 ft
  visible, open border (1 face)                                    419     729.1 ft
  visible, shape edge > 5 deg                                      303    1225.3 ft
    line inside a surface:    29.5 in  [1275.6, 22826.9, 1582.7] -> [1275.6, 22826.9, 1612.2]
    line inside a surface:    19.7 in  [1334.7, 22669.4, 1622.0] -> [1315.0, 22669.4, 1622.0]
    line inside a surface:    12.4 in  [2594.5, 22826.9, 1776.2] -> [2582.2, 22826.9, 1774.4]
    line inside a surface:     9.9 in  [2683.1, 23063.1, 1779.5] -> [2673.2, 23063.1, 1778.1]
    line inside a surface:     9.9 in  [2683.1, 22945.0, 1779.5] -> [2673.2, 22945.0, 1778.1]
    line inside a surface:     9.9 in  [2673.2, 23102.5, 1778.1] -> [2683.1, 23102.5, 1779.5]
  visible open edges split:
    open edge = real border of the model                                       240     409.2 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)        4      12.0 ft
    open edge lying on an angled face (face meets a surface it does not split)   175     308.0 ft
      T-junction line:    88.0 in  [1334.7, 22630.1, 1582.7] -> [1413.4, 22630.1, 1622.0]
      T-junction line:    22.0 in  [2594.5, 23279.7, 1776.2] -> [2594.5, 23260.0, 1766.4]
      T-junction line:    19.7 in  [1305.1, 22649.7, 1622.0] -> [1305.1, 22669.4, 1622.0]
      T-junction line:    14.0 in  [2594.5, 23279.7, 1766.4] -> [2594.5, 23269.8, 1776.2]
CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp: 183 faces, 521 edges
  hidden (soft)                                                    129    1568.3 ft
  visible, material border (coplanar)                               15     233.4 ft
  visible, non-manifold (3+ faces)                                  14      38.7 ft
  visible, open border (1 face)                                    172     487.3 ft
  visible, shape edge > 5 deg                                      191    1873.7 ft
  visible open edges split:
    open edge = real border of the model                                       104     252.7 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)       15      31.8 ft
    open edge lying on an angled face (face meets a surface it does not split)    53     202.8 ft
      T-junction line:    39.7 in  [2121.8, 24204.9, 2042.2] -> [2082.5, 24204.9, 2047.4]
      T-junction line:    39.7 in  [2200.6, 24204.9, 2031.8] -> [2161.2, 24204.9, 2037.0]
      T-junction line:    39.7 in  [1885.6, 24204.9, 2073.2] -> [1846.2, 24204.9, 2078.4]
      T-junction line:    35.7 in  [2358.1, 24204.9, 2011.1] -> [2322.6, 24204.9, 2015.8]
      T-junction line:    35.7 in  [2322.6, 24195.0, 2015.8] -> [2358.1, 24195.0, 2011.1]
```

A: 17 -> 12 lines inside flat surfaces (20.3 -> 11.2 ft); 3 -> 4 T-junction lines (12.3 -> 12.0 ft).
B: 0 lines inside; 20 -> 15 T-junction lines (42.3 -> 31.8 ft).

## 13. Close-ups, read

- **The ramp (view 0).** The input's sawtooth is one grey wall. Item 1 turned the grey wedge beside
  the landing's end face grey. The purple left at the upper-left end is the landing seen from inside
  the section box (section 8).
- **B region 92 (the b1 box, from below and from -y).**
  - The input's arm is a lattice with purple bands.
  - The landing is a closed grey box from e27eb79 on.
  - At e27eb79, from -y, the arm's lower band showed panels at two depths with a slot between them.
    Now the landing end of the arm has one bottom, and its far part still shows recessed, stepped
    levels.
- **A big landing from below.**
  - The input is mostly purple.
  - At e27eb79 the underside was clean but carried hanging lines along its east edge.
  - Now those are gone, and five purple strips of the margin strip show along that edge (A1).
- **A lower landing from below.** The purple input underside is closed grey, with the stepped border
  between the rebuilt and the export's bottoms (A2), unchanged.
- **A3.** The curb block and the landing are two closed grey solids, with the export's gap between
  them. The input's purple strip is gone.
- **B from -y, four states.** The thin plate under the arm's sloped part went with C2, the
  triangular fin with C1; the two panels (B3) stay.

## 14. Concerns

1. **A's owner `.skp` is stale.** `OBJ FIXED RESULT/CHTM_SIDE_WALK_2nd_floor.fixed.skp` could not be
   replaced, because SketchUp has it open (Errno 13, in every run since 12:22). It still holds the
   item-2 file (11:50; 636 faces, 17 lines inside surfaces). The final file is
   `data/output/CHTM_SIDE_WALK_2nd_floor/CHTM_SIDE_WALK_2nd_floor.fixed.skp`. Close it in SketchUp
   and re-run A, or copy that file.
2. **A's back faces from outside are 21,553 against 20,945 at e27eb79.**
   - The margin strip's reversed cells are visible from below again: the A1 close-up reads 1,356 ->
     6,938 in view 0.
   - The walls that hid them were invented under a real underside (the C2 class).
   - The strip itself, a thin sheet with alternating windings, needs an orientation rule (a
     consistent winding across a coplanar sheet) or closing into a solid. Neither is in items 1-3.
3. **B1 is only partly fixed.**
   - The far part of the arm (region 107) still reads as stepped from below: walls 18 of 40 and
     bottom faces 20 of 36 are kept, the rest refused as covering outside the footprint, not traced
     to the pixel.
   - The input has no -y side under the whole arm.
   - Region 134 sits at the 0.99 hull bar, so the rule is near its edge there.
4. **Not fixed, with causes above:**
   - A2 (a T-junction border between the rebuilt and the export's bottoms);
   - item 7's lines (opposite windings);
   - B4, B8 (not traced).

   The coordinator's "rebuild a broken underside like a broken side" was realised only where C2 and
   B1 reach. A general underside rebuild was not implemented.
5. **Rule 6 lets a new face cover what lies OUTSIDE every slab** when that was seen through a slab
   now closed on both sides of the ray. It is named, counted, and tested against a fin and a post,
   but it is a new allowance, and a reviewer should read it.
6. **Tests changed with requirements, stated in their commits:**
   - the railing test (item 1);
   - the 0.02 in opened-crack test (M1);
   - SR6's plan tests (item 1, M5);
   - `_planned`.
7. **The session record's cap-guard cell** (review M4) is in docs/, which this brief could not edit.
8. **Item 9** (A's opposite-wound double layer at z 1612.2) is untouched, as the brief says.

## Public signatures

```
engine/fixes/pipeline.py
FixProfile.max_thickness: float = 50.0          # CHANGED (item 2; was 36.0)

engine/fixes/solidify.py
INTERFACE_HULL_FRACTION = 0.99                                                     # NEW (item 6)
solidify(mesh, topo, profile) -> SolidifyResult   # signature unchanged; report gains
    # side_pieces_given_back (R2-M3), blocks_standing_on_slabs (item 6),
    # lower_surface_deeper_than_sides [{region, lower_surface, representative_side}] (R2-I2);
    # undersides_not_tops now counts _is_underside's verdicts (R2-C2)
_is_underside(topo, members, edges, continued, along, sides, sky, caster, ok_ids, min_body,
              reach) -> bool                                                        # NEW (R2-C2)
_ends_here(runs, depth, band) -> bool                                               # NEW (R2-I2)
_sides_end_on(topo, along, sides, coef, band, tol) -> bool                          # NEW (R2-I2)
_underside(topo, members, caster, h, tol, fraction, search_extra=24.0, side_runs=None,
           band=0.0) -> (bool, float)                                               # CHANGED
_lower_surface(topo, members, caster, ok_ids, normals, reach, fraction, along, sides, band,
               tol, top_min_nz, top_normal, top_origin) -> (coef, depth) | None     # CHANGED
_attached(polys, members, lines, touch) -> np.ndarray                               # NEW (R2-I1)
_wall_pieces(..., h_ends=None, touch=EPS_IN)                                        # CHANGED
_wall_look(mesh, topo, faces, found, material, uv_scale, origin, normal)
    -> (material, uv_scale, pieces)                                                 # NEW (R2-I1)
_side_looks(mesh, topo, faces, frames, to_build, material, uv_scale, band) -> list  # NEW (R2-I1)
class _Planes  (lying_on(f, cand, tol) -> np.ndarray)                               # NEW (R2-C1)
_coincident_new_faces(...)   # signature unchanged; also against earlier groups' new faces
_new_faces_on_pieces(solid, new_faces, replaced_group, tol) -> dict[int, np.ndarray] # NEW (R2-C1)
_cap_guard(..., piece_cover=None, on_pieces=None)                                   # CHANGED

engine/guard/compare.py
solidify_feedback(..., refused_before=None, piece_cover=None, on_pieces=None)       # CHANGED
    # rule 6 (through_shell_px), refused together (refused_together), a new face on a present
    # piece refused (refused_on_pieces, reason "lies_on_a_restored_piece")
_SHELL_LIFT = 1e-3; _SHELL_SPACING = 2.0; _SHELL_MAX_SAMPLES = 32; _ON_SURFACE = 1e-6   # NEW
_through_closed_shell(start, direction, gap, entry, planes_after, shell_caster, shell_ids,
                      interior) -> (through, leave)                                 # NEW (item 1)
_refuse_together(refuse, restore, removed, records, shell_ids, planes_after, positions_c,
                 faces_after, caster_factory, interior) -> int                      # NEW (item 1)
_closest_points(points, triangles) -> (distance, closest)                           # NEW (R2-M1)
_border_probe(geometry_before, geometry_after, tol, material_before=None,
              material_after=None, plane_tol=0.0)    # CHANGED; the probe gains
    # crack_width_ok(points, before_faces) -> bool  (R2-M1)
_classify(...)   # signature unchanged; an opened crack is measured across, and only the sky or
                 # an exposed side may show through it (R2-M1)

engine/cli.py    # docstring only (R2-M4)

engine/tests/fixtures/build.py (appended at the end)
slab_with_fins_beside_a_post(post_y=30.0, post_x=(35.0, 55.0), post_z=(-9.0, -2.0))
_closed_box(P, uvs, fv, fvt, fm, x0, x1, y0, y1, z0, z1, material=0)
overhang_beside_a_slab()
real_top_under_a_landing()
slab_with_a_deep_tooth_in_its_side(teeth_material=1)
slab_with_one_deep_tooth(size=40.0, height=8.0)
slab_with_a_double_layer_top(size=40.0, height=8.0)
slab_with_a_concrete_sawtooth_side()
slab_with_half_side_and_a_sign(size=40.0) -> (mesh, sign faces)
slab_over_a_floor_with_a_bench()
slab_with_a_block_standing_on_it(size=60.0, depth=8.0, block=(20.0, 40.0), height=10.0,
                                 at_edge=False)
```
