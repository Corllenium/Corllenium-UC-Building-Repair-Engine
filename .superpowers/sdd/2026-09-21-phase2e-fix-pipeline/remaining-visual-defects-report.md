# Brief 11: the defects still visible after brief 10 (report)

Brief: `docs/superpowers/records/briefs/11-remaining-visual-defects.md`, with the review of brief 10
(`review-brief10.md`) folded in. Branch `feat-dashboard`, main checkout. Final state measured at
HEAD 861003c. Other sessions' commits interleave with these. The only one of theirs that
touches `engine/` is 9dcd1ad, `engine/cli.py`'s owner copy, merged in f885fd9; the final runs
include it.

**Status: DONE_WITH_CONCERNS.** Items 1 and 2 are fixed. Items 3 and 4 are traced and measured,
but the engine is unchanged, because every change tried measured worse. All the review items are
done or declined with a measurement. M2 is not fixed, and a strict xfail test pins it.

## Commits, in order

| # | Commit | Item | What |
|---|---|---|---|
| 1 | 4019987 | brief item 1 (A1, brief 10 item 7) | a thin face is wound like the sheet it belongs to, measured in back pixels |
| 2 | 0a81860 | brief item 2 (A2) | a bottom covers the whole footprint, built round what already lies on its plane; broken undersides measured and kept |
| 3 | 281a569 | R10-C1 | a real underside is the bottom of the body above it, fascia or no sky |
| 4 | af6ebf4 | R10-I2 | a wall overlapping an earlier wall is built over the rest of its side |
| 5 | c50f664 | R10-C1 / I2 tests | the regression tests af6ebf4 left out (see Concerns, the git incident) |
| 6 | 2d672bb | R10-I3 | a piece belongs to its slab in 3-D, bottoms too; a wall's look waits for the guard |
| 7 | 9461830 | R10-I1 | rule 6 sees only through volumes confirmed apart from the guard; what it hides is kept |
| 8 | 0e601de | R10-M1 | a lost rule-6 pixel over a replaced piece always restores the piece, never the face |
| 9 | 25521af | R10-M3 | the rule-6 tests pin the mechanisms they are named for |
| 10 | 5e2e50e | R10-M2 | pinned (strict xfail): a real top under a landing with no underside |
| 11 | c2841e7 | R10-M6 | pinned reading (block, not overhang); every CLI summary counts the blocks |
| 12 | fc5cccd | R10-M6 / item 3 | the report lists every underside the hull test judged, with its fraction |
| 13 | 6873b70 | R10-M4 | the underside reach gets its own constant; walls the ceiling or the slab depth miss are reported |
| 14 | e825af0 | R10-M5 | docstrings that no longer matched |

Suite at 861003c: **607 passed, 1 xfailed** (the xfail is M2's pinned defect)
(`.venv/Scripts/python.exe -m pytest engine/tests -q`, 340 s).

Real-data runs, since the coordinator's rule, always passed
`--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"`, and `--out data/output`.

## Brief item 1: A1, reversed cells in the margin strip (4019987)

- **Cause.** The big landing's sloped underside on file A is one plane of 234 faces. The cells of
  its east strip that have no top above them are single faces of that plane. They are exposed on
  both sides, so they are thin, and the per-face rule never flips a thin face. They were wound up
  while the rest of the underside faces down. So they showed their backs to every view from below
  (five purple strips), and SketchUp drew a line between every two cells wound opposite ways
  (brief 10 item 7).
- **Rule.** `orient_sheets` joins faces into sheets through shared edges:
  - two faces join when their planes agree within the coplanar angle and they lie on opposite
    sides of the edge (a fold is not a sheet);
  - in a sheet whose windings disagree, the THIN faces take the side the whole sheet is more
    exposed on;
  - a face that another face lies on is never re-wound.
- **Measured.** A flip changes no double-sided render. So one render over the 26 guard views
  counts each face's pixels per side, and a sheet is re-wound only when its back pixels do not
  go up.
- **Numbers.** On file A, 3 sheets were made consistent and 19 faces re-wound. Back pixels before
  the merge went 19,426 -> 18,367 (final run), and the A1 close-up went from 6,938 / 4,508 back
  pixels to 473 / 67. On file B there was nothing to re-wind.

## Brief item 2: broken undersides (0a81860)

- **Cause of A2's stepped border, traced.** A bottom was triangulated from the MERGE's outline of
  its top. That outline leaves overlapping triangles out of its union (merge rule 3), so on file A
  regions 11 and 9 lost 628 and 2,473 sq in. The lower landing's underside had two holes, 628 and
  194 sq in, and its inner walls drew stepped lines through them.
- **Fix.**
  - The bottom keeps the old outline triangulation, which is what the cap guard was measured
    against.
  - It then FILLS the part of the footprint the outline leaves out.
  - Where a triangle lies over a face already on the bottom plane, or over an earlier bottom, it
    is cut locally instead of being laid on top.
- **Declined as the brief worded it: rebuilding a broken underside as one clean bottom.** It
  measured worse on both files in every variant. Back pixels from outside, against 20,478 on A and
  2,787 on B without it:

  | Variant | Back pixels |
  |---|---|
  | per region | A 29,670 |
  | per slab | A 20,488 |
  | footprint bottoms | B 11,083 |

  The cap guard judges each new face alone. Where one face is refused, the pieces under it come
  back, the faces lying on them are refused next, and a patchwork with holes is left.
- Broken undersides are therefore measured and reported (`undersides_broken`: A 13, B 11) and
  kept as they are.
- **Result.** Hole 2 is closed and hole 1 is partly closed. A2's close-up went from
  687 / 1,440 / 1,119 back pixels to 277 / 292 / 0.

## Brief item 3: B region 107 (B1), and the 0.99 hull bar at region 134

No engine change. The trace below comes from `trace_guard.py`, a re-execution of the guard's own
`solidify_feedback` with logging added, so every rule is applied, rule 6 included.

- **What is refused.** Region 107 has 78 new faces: 40 kept and 38 refused, all
  `covers_outside_footprint`.
- **Where the refusals start.** In round 0 at 2d672bb (before I1), few faces failed on their own
  pixels:
  - the south walls at y 24008 (groups 67 and 73), 2 to 16 px each, over region 117's side at
    x 2397.4, 250 to 550 in east;
  - wall 7606, 13 px over region 59's face at y 24204.9;
  - two bottom faces at x 2043 to 2122, 50 and 11 px, over the underside of block 149 at
    x 2122 to 2161;
  - two more bottom faces, 1 px each, over region 117's side.
- **Why those pixels fail.** They are seen through the slab under ramp blocks 149, 106 and 134.
  The slab runs under those blocks: its sides run the whole length, and nothing lies below any
  block's underside (rays straight down from 870 grid points under 134 hit nothing, as under the
  taken blocks 115, 147 and 148). But item 6's hull test took none of the three:

  | Block | Judged against | Fraction inside the hull |
  |---|---|---|
  | 149 | top 107 | 0.750 |
  | 106 | top 107 | 0.000 |
  | 134 | top 92 | 0.987 |

  So no planned volume covers the slab under them, and a new face whose ray crosses it covers
  something "outside every volume". Everything else (the whole west end, the east walls) fell in
  the same round or later, refused together through rule 6's re-cast, or lying on restored
  pieces.
- **After I1.** Region 107 sees no sky (it runs under the ramp), so rule 6 no longer sees through
  it. Its west-end bottom now fails in round 0 on its own pixels, over region 43's underside
  (z 2094.5, 78 in above the slab's top) seen up through the slab's open west end. The final mesh
  is byte-identical before and after I1.
- **Verdict: the refusals are right for the plan they judge.** Each refused face would hide what
  BEFORE showed, outside every planned volume. What is wrong is the plan: it has no slab under
  three of the ramp's blocks.
- **Fixes tried and measured** (`fix_object`, nothing written):
  - Judging each block against the hull of the whole joined slab takes 134, 106 and 149. But it
    also takes B's 205 and 189 (the fascia-rule undersides), and on file A 166 (an 88,996 sq in
    underside), 310, 288 and 721. That is C1's damage on A. Declined.
  - A hull bar of 0.98 takes 134 and nothing else on either file (the next candidates are 0.750
    on B and 0.476 on A). B goes to 535 triangles and back faces 2,869 -> **3,555**. A is
    unchanged. Declined.
- **The 0.99 bar at 134.** By every measurement available, 134 is a block like 115, 147 and 148:
  its underside sits in the slab's top plane, nothing lies below it, and the block stands 11 to
  31 in above it. But taking it measures worse, so the bar stays at 0.99. The judgement rests on
  that measurement, not on an argument.
- **What fc5cccd adds.** `interface_candidates` in the report now lists every candidate, the
  review's "show B's three regions to the owner":
  - B taken: 115 (1.000), 148 (1.000), 147 (0.991);
  - B not taken: 134 (0.987), 149 (0.750), 106, 205, 189 (0.000);
  - A: none taken, candidates from 0.476 down.

## Brief item 4: B4 and B8

No engine change. For every purple face in a close-up, `back_faces_in_box.py` compares the
section-box render with the WHOLE model: the face's back exposure (64 directions) and its
file-level back pixels over VIEWS_26.

- **The earlier spots were in the wrong places.** The spots "b4" (x 2560-2800, y 23640-23950) and
  "b8" (x 970-1700, y 23990-24215) used since brief 10 are not where the triage saw B4 and B8:
  - `b4j` (x 2820-3000, y 23360-23560) is the ramp junction in `top.png`;
  - `b8toe` (x 2560-3060, y 22600-22900) is the far left of `px.png`, which is B's -y end.

  All the purple in "b4" (13,166 px), "b8" (112,233 px) and "b8x" (215,012 px) is a section-box
  artefact. Every one of those faces has back exposure 0.000 in the whole model and 0 file-level
  back pixels. The box
  cuts away the geometry that hides their backs.
- **B4, the junction (b4j).**
  - The input junction was a mess of layered, mixed-winding pieces: 30,637 / 32,085 / 18,821 back
    pixels in the three views. Now the surfaces are clean: 3,923 / 6,180 / 2,884, the same as
    brief 10's final.
  - In the whole model the purple faces there carry **134 of B's 2,869** back pixels. 90 of those
    are on two pieces of the ramp's sloped underside at its edge by the junction (faces 360 and
    366, x 2870-2949, y 23447-23477). They are seen from oblique views: rays straight down there
    meet the top, in the input as in the final.
  - Short lines inside the surface remain where the fan's triangles meet. Not fixed.
- **B8, the knife edge, is in the export.**
  - B's -y end is the TOE of a ramp. Its walking surface (n -0.15, 0, 0.99) starts at z 1779.53
    at x 2616.7, exactly on its own flat underside (r510 at z 1779.53). So the thickness is zero
    at x 2616.7 and 9.8 in at x 2683.1.
  - The engine keeps that geometry and removes the toe's back-facing underside layers: back pixels
    15,927 / 3,796 / 31,642 in the input against 2,499 / 19 / 0 now.
  - **One engine artefact is left.** `min_thickness` raises the toe's knife-edge walls to 2 in, and
    they hang below the input's lowest point. The cap guard refuses 7 of the 8 triangles (6
    `covers_below_bottom`, 1 `covers_outside_footprint`) and keeps one: face 7558 of region
    809's group 54, a 9.8 x 2 in triangle at x 2616.7, y 22651-22661, z 1777.5-1779.5, which
    no rule refused. It carries 12 file-level back pixels.
  - Not fixed. Refusing it needs either a lone-face rule, or a wall clamp that contradicts the
    `min_thickness` specification (`test_a_measured_edge_height_is_still_clamped_into_the_profile_bounds`).

## Review of brief 10

- **C1 (281a569).** Top or underside is decided by the body above as well as the sky:
  - BELOW counts a side only when it hangs as deep as the slab that runs into the region;
  - ABOVE also holds where the face straight above is the top of a body whose own sides reach
    down to the region;
  - all the review's probes (shaded, tall, fascia, sign, real-scale fascia) are tests.

  Measured on every candidate of both files: A has 0 verdicts changed; B has 3 small regions
  (39, 189, 205) that become undersides through the fascia rule.

  **Not done as worded:** "never invent a bottom that covers a face whose original exposure shows
  it is seen from below". That would forbid the bottoms of real tops seen only from below through
  their missing bottom: A's 9 and 784, and B's 107 (up 0.000, down 0.407). A stricter
  body-above rule turned 7 of A's undersides and 10 of B's regions (the stair blocks among them)
  the other way.
- **I2 (af6ebf4, tests c50f664).**
  - A wall is built only over the part of its side that no earlier coplanar wall covers. A bottom
    is built round earlier bottoms in its plane (item 2).
  - `_coincident_new_faces` tests ORIGINAL faces only.
  - The step probe's band is closed.
  - A is unchanged (its 9 coincidence refusals are now trimmed walls). B has 112 more back pixels
    (2,757 -> 2,869): the inner sides of region 107's south walls, now partly kept, seen from
    below through that region's refused bottom (item 3). b1 view 1 shows +85.
- **I3 (2d672bb).**
  - A piece's connectivity to the slab is judged in 3-D; the plan's made-up foot is no anchor.
  - A face lying in the side's plane is always a piece.
  - Bottoms get the same belonging test.
  - A wall's look is decided after the cap guard (`walls_relooked`).

  Four tests (7 cases): 6 cases failed before and all 7 pass after. The seventh, the sign at
  40 in, passed before on its outcome alone and now pins its mechanism by counting pieces. Both
  real files are byte-identical to c50f664's output.
- **I1 (9461830).**
  1. Rule 6 samples its path only through volumes confirmed apart from the guard: sky-seeing tops
     as deep as their own measured sides. It is not allowed through a region reached only by
     continuation, a fallback height, or a lower surface deeper than its sides plus the band.
  2. What rule 6 hides is measured (`seen_through_shell`, with input exposure).
  3. The hidden pass never deletes such a face (`kept_from_hidden_pass`).

  The post probe (with the wrong plan forced, since C1 now reads it right) went from 1,030 rule-6
  px to 6 walls refused, and the underside ships. A plate seen only through a closed slab is now
  kept.

  Real files:
  - B's final mesh is unchanged.
  - **A pays one visible cost.** Two 2 in walls are no longer kept: region 572, whose 2.0 in depth
    is the fallback, and its neighbour 683, at x 2680, y 22955. Sides rebuilt went 52 -> 50 edges,
    triangles 884 -> 881, back pixels 18,372 -> 18,348, model pixels -47. In the close-up that
    slab edge beside the notch shows its top edge with no side under it again.
  - `seen_through_shell` is 0 faces on both files in the returned state.

  The test `test_a_new_face_that_coincides_with_an_existing_face_is_refused` was re-aimed. Its
  plate faces down and sees sky past the slab, so it was planned as a top with no measured depth.
  Its fallback shell (7 faces) is now refused; the slab's own bottom still closes round the plate.
- **M1 (0e601de).** A lost rule-6 pixel over a removed piece always restores the piece and never
  refuses the face. The probe is a unit test: two pixels, and "already restoring", each gave
  (1, [0, 2, 3], [7]) and now give (0, [2, 3], [7]). Both real files are byte-identical.
- **M2 (5e2e50e). Not fixed; pinned.** `real_top_under_an_open_landing` is a strict xfail. It
  fails today at `undersides_not_tops == 0` (it reads 1). The rule that fixes this scene flips
  7 regions of A and 10 of B (see C1).
- **M3 (25521af).** Each re-aimed test now fails under the mutation of the mechanism it is named
  for (`m3_mutations.py`):
  - "refused together" fails with `_refuse_together` a no-op and with rule 6 off. The wall is now
    refused in round 0 by its own pixels: a post under the plate, with rule 6 denied to rays
    entering through the wall. Round 0 removes 4 faces, 2 of them together.
  - The fin test fails without the path check (0 rule-6 px over the post, against 494 without
    the check).
  - The sign test at 40 in fails at 3561127, where the sign was a piece and the guard restored
    both its faces.
- **M4 (6873b70).**
  - `UNDERSIDE_REACH` = 52.5 in, its own constant.
  - `walls_clamped_by_the_ceiling` (0 on both files) and `walls_deeper_than_their_slab` (A 21
    walls in 4 regions, B 9 in 4) are reported.
  - **The per-slab clamp was measured and declined.** It contradicts S-I4 (the two-depth slab's
    deep walls would stop at 3.8 in instead of 9.8). On the real files it is worse on both: A
    881 -> 874 triangles and 18,348 -> 18,362 back pixels; B 513 -> 515 and 2,869 -> 2,945.
- **M5 (e825af0).** Docstrings corrected:
  - `_underside`'s rationale, with the probe's measurement;
  - `_is_underside`'s depths (29.52 in deep along 29.6 in; 8 in deep);
  - `INTERFACE_HULL_FRACTION`, now with the measured fractions;
  - the 60 in skirt test.

  Not changed: the session record's cap-guard cell, which is in docs/ and outside this brief.
- **M6 (c2841e7, fc5cccd).**
  - `test_a_block_at_a_slabs_edge_is_read_as_a_block_not_an_overhang` pins the chosen reading:
    the block is counted, the bottom fills the notch (400 sq in), and the underside is deleted.
  - `fix` prints the block count in every summary, with the tops read as undersides, the walls
    relooked, and rule 6's confirmed volumes.
  - The report lists the candidates (item 3).

## Finish

Both real runs at 861003c. Their fixed OBJs are byte-identical to 6873b70's run. preview-data ran
for both: 4,801 and 7,480 triangles written to `preview/data`.

| | A: CHTM_SIDE_WALK_2nd_floor | B: CHTM_2nd_to_3rd_building_sidewalk_outside |
|---|---|---|
| triangles in / reference / out | 4,692 / 4,801 / **881** | 7,227 / 7,480 / **513** |
| backface_px input / reference / final | 569,108 / 455,211 / **18,348** | 464,939 / 362,905 / **2,869** |
| sides rebuilt | 50 edges, 1,454.5 in (162 walls built) | 35 edges, 1,163.7 in (83 built) |
| bottoms rebuilt | 16 added (2 filled, 3 built round); 108 already had one | 15 added (2 filled, 1 built round); 68 already had one |
| pieces replaced | 83 (walls 29, bottoms 54), 5 restored | 90 (45, 45), 6 restored |
| walls / bottom faces refused | 212 / 69 | 94 / 55 |
| cap guard (new, failing, removed, restored, rule-6 px) | (473, 11,169, 212, 6, 572), (247, 2,049, 51, 0, 0), (192, 0, 0, 0, 0): passed | (478, 16,782, 94, 39, 1,127), (363, 1,534, 17, 0, 778), (346, 315, 3, 0, 51), (343, 0, 0, 0, 0): passed |
| removed | hidden 2,065, zero-area 217, overlap 11, slivers 2, folds 32, refused by rays 4 | hidden 2,771, zero-area 80, overlap 3, slivers 1, folds 6, refused by rays 3 |
| flips | 653 per face, 19 by sheets (3 sheets), 55 thin | 723, 0, 3 thin |
| guard after removal | passed; model_px 2,058,175, fragment_removed 37 | passed; 2,433,490, fragment_removed 10 |
| guard merge attempt = final | passed; zfight_tie 1, fragment_removed 38, border_shift 159, grown_base 66, border_shift_grown 66 | passed; crack_closed 4, fragment_removed 10, border_shift 35, grown_base 5, border_shift_grown 3, crack_closed_grown 2 |
| merge | 127 regions, not rolled back, T-vertices 373 -> 0 | 64 regions (1 skipped: overlap), not rolled back, 361 -> 0 |
| invariants | all true | all true |
| passed | **True** | **True** |
| rule 6 | 90 confirmed volumes; not: no sky 19, no measured depth 5, lower surface deeper 10; 0 faces seen only through a shell | 65; not: 12 (107 among them), 1, 5 (the ramp 309 among them); 0 |

All other guard counts are 0.

### SketchUp audit (`skp_edge_audit.py` on `data/skp_scratch`)

```
b393ce36e8f61d8c
CHTM_SIDE_WALK_2nd_floor.fixed.skp: 562 faces, 1201 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)       7       6.8 ft
  hidden (soft)                                                    426    3110.4 ft
  visible, non-manifold (3+ faces)                                  44      84.5 ft
  visible, open border (1 face)                                    415     722.9 ft
  visible, shape edge > 5 deg                                      309    1215.6 ft
    line inside a surface:    29.5 in  [1275.6, 22826.9, 1582.7] -> [1275.6, 22826.9, 1612.2]
    line inside a surface:    19.7 in  [1334.7, 22669.4, 1622.0] -> [1315.0, 22669.4, 1622.0]
    line inside a surface:     9.8 in  [1305.1, 22669.4, 1612.2] -> [1305.1, 22669.4, 1622.0]
    line inside a surface:     9.8 in  [1305.1, 22669.4, 1622.0] -> [1295.3, 22669.4, 1622.0]
    line inside a surface:     9.8 in  [1315.0, 22669.4, 1622.0] -> [1305.1, 22669.4, 1622.0]
    line inside a surface:     1.5 in  [2673.2, 23023.8, 1779.5] -> [2673.2, 23023.8, 1778.1]
  visible open edges split:
    open edge = real border of the model                                       233     394.5 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)        4       8.1 ft
    open edge lying on an angled face (face meets a surface it does not split)   178     320.2 ft
cd145a27b191ac77
CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp: 184 faces, 527 edges
  hidden (soft)                                                    129    1568.3 ft
  visible, material border (coplanar)                               15     233.4 ft
  visible, non-manifold (3+ faces)                                  14      38.7 ft
  visible, open border (1 face)                                    175     497.7 ft
  visible, shape edge > 5 deg                                      194    1862.2 ft
  visible open edges split:
    open edge = real border of the model                                       106     251.7 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)       15      31.8 ft
    open edge lying on an angled face (face meets a surface it does not split)    54     214.3 ft
```

Against brief 10's final:
- A: lines inside flat surfaces 12 -> 7 (11.2 -> 6.8 ft); T-junction lines 4 -> 4 (12.0 -> 8.1
  ft); non-manifold edges 68 -> 44.
- B: no lines inside; T-junction lines unchanged at 15 (31.8 ft).
- The CLI's own skp count ("lines inside surfaces") reads 5 on A and 2 on B.

The SketchUp bridge was not running ("Could not connect to Sketchup"), so no real SketchUp views
were exported.

### Close-ups, before (brief 10's final .skp) and after (this run's .skp)

Counts are back pixels inside the section box, per view.

| Spot | Views | Before | After | What the image shows |
|---|---|---|---|---|
| A1 | 0, 1 | 6,938 / 4,508 | 473 / 67 | The margin strip's five purple strips are gone: the cells now face down like the rest of the underside. |
| A1 | 2 | 2,852 | 3,763 | A grazing view from above. The re-wound strip shows its back there: a thin sheet can face only one way, and the file-wide total went down. |
| A2 (a_low) | 0-2 | 687 / 1,440 / 1,119 | 277 / 292 / 0 | The stepped lines at hole 2 and the purple end strip are gone; one small purple triangle and the export's own zigzag border remain. |
| B1 | 0-2 | 829 / 3,251 / 306 | 829 / 3,336 / 306 | The same underside. The +85 in view 1 is I2: inner sides of partly kept walls seen through the refused bottom. |
| B4 (b4) | 0-2 | 3,232 / 9,161 / 773 | unchanged | Clean joint; all of the purple is a section artefact. |
| B4 (b4j) | 0-2 | 3,923 / 6,180 / 2,884 | unchanged | Input 30,637 / 32,085 / 18,821. Clean surfaces now, with a small notch at the crease and a few short lines. |
| B8 (b8, wrong end) | 0-2 | 100,682 / 0 / 11,551 | unchanged | Section artefact. |
| B8 (b8toe) | 0-2 | 2,499 / 19 / 0 | unchanged | Input 15,927 / 3,796 / 31,642. The export's wedge toe, now clean; one 2 in fin triangle at the -y corner. |
| Ramp (309) | 0-2 | 580 / 1,440 / 6,122 | unchanged | The same counts in all three views; view 2 inspected is identical. The ramp did not regress. |
| i1a (A, I1's cost) | 0-2 | vs 2d672bb: 70,520 / 34,531 / 17,648 | 70,520 / 34,531 / 16,246 | Hit pixels 138,757 -> 137,344 in view 1: the two 2 in walls under the slab edge by the notch are gone. |

## Concerns

1. **Git incident, fixed; the other session's commit is intact.**
   - The split used to commit I2 cut the test files at C1's markers. So af6ebf4 went in without
     C1's nine tests and without I2's own.
   - My `git commit --amend` then rewrote the other session's f8ba2a0 (it had landed on top) into
     ed3a505.
   - `git reset --soft f8ba2a0` restored their commit exactly. c50f664 restored the tests.
   - I did not amend again.
2. **I1 costs file A one visible side**: two 2 in walls at x 2680, y 22955, region 572 with a
   fallback depth. The owner may prefer the wall. Loosening the rule back would be argument, not
   measurement.
3. **B1 is still only partly rebuilt** (38 of 78 faces refused). The cause is the plan's missing
   slab under ramp blocks 106, 149 and 134, and both fixes tried measured worse (item 3).
4. **Hole 1 on A's lower landing is only partly closed.** Broken undersides are kept, not rebuilt,
   because rebuilding measured worse.
5. **M2 is not fixed**; a strict xfail pins it. The literal C1 wording ("never cover a face seen
   from below") was not implemented, for the reasons in C1 above.
6. **M4's per-slab clamp was declined** (measured worse on both files; contradicts S-I4).
7. **B4 still shows 134 file-level back pixels at the junction. B8's toe has one kept 2 in fin
   triangle** (12 px), a consequence of the `min_thickness` specification.
8. **Earlier close-ups were in the wrong places.** The "b4" and "b8" spots used since brief 10 are
   not where the triage saw B4 and B8, so earlier reports on them described other spots. `b4j` and
   `b8toe` are the right places.
9. **A claim went in before its measurement.** c2841e7's message named B's blocks (115, 147, 148;
   134 at the bar) before measuring them. fc5cccd's measurement confirmed all four.
10. **Owner files.** Before the `--skp-dir` rule, my runs at 18:49-18:50 replaced the owner's two
    files; the coordinator restored them. Every real run since wrote only `data/skp_scratch`. The
    owner's folder was not touched after the rule.
11. **Session notices.**
    - claude-mem cannot save memories: "Provider reported the inference allowance exhausted".
    - MCP `higgsfield-bridge` needs authorisation.
    - `ui-tars` and `windows-mcp` failed to connect.

    None of these affects this work.

## Public signatures

- `engine.fixes.orient.SheetOrientation(flip: np.ndarray, report: dict)` (dataclass)
- `engine.fixes.orient.orient_sheets(positions_c, faces, front, back, flipped, thin, ok, *, tol,
  angle_deg=COPLANAR_ANGLE, views=VIEWS_26, size=(900, 600), caster_factory=EmbreeCaster,
  centre=None) -> SheetOrientation`
- `engine.fixes.pipeline.FixResult`: new fields `sheet_flipped: np.ndarray`, `sheet_report: dict`.
  The hidden pass never deletes `SolidifyResult.seen_through_shell` faces, and it records
  `solidify_report["seen_through_shell"]["kept_from_hidden_pass"]`.
- `engine.fixes.solidify.SolidifyResult`: new field `seen_through_shell: np.ndarray | None = None`
  (bool over the input faces).
- `engine.fixes.solidify.UNDERSIDE_REACH = 52.5` (new). `INTERFACE_HULL_FRACTION = 0.99`
  (unchanged value).
- `engine.fixes.solidify.solidify(mesh, topo, profile) -> SolidifyResult`: unchanged signature. New
  report keys:
  - `undersides_broken`, `bottoms_already_there`, `bottoms_filled`, `bottoms_built_round`,
    `bottom_fill_skips`
  - `walls_relooked`, `rule6_volumes`, `seen_through_shell`, `interface_candidates`
  - `walls_clamped_by_the_ceiling`, `walls_deeper_than_their_slab`
- `engine.guard.compare.solidify_feedback(..., on_pieces=None, shell_interior=None)`: new keyword.
  `history[i]["through_shell_faces"]` and `detail["through_shell_faces"]` are new.
- `engine.cli`:
  - `report.json` gains `n_sheet_flipped` and `sheet_orientation`;
  - `fix` prints two new lines: `  sheets: ...` and
    `  tops read as undersides: N, blocks standing on slabs: N, walls relooked: N; rule 6 sees through N confirmed volumes (not: {...}), N faces seen only through a shell (N kept from the hidden pass)`.
