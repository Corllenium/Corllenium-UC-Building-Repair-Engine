# Brief 13: one copy of an exactly stacked, opposite-wound, same-material surface (2026-09-25)

Worktree `.claude/worktrees/coincident`, branch `feat/coincident-pairs`, from 281a569
(feat-dashboard). Brief: `docs/superpowers/records/briefs/13-coincident-pairs.md` (untracked in the
main checkout). Every number below was measured in this session on the snapshots `ce26e0392ab0`
(A, `CHTM_SIDE_WALK_2nd_floor`) and `0b290ec0bcb4` (B, `CHTM_2nd_to_3rd_building_sidewalk_outside`),
with the main checkout's `.venv` and `PYTHONPATH` set to the worktree.

**Status: DONE_WITH_CONCERNS.** The rule is built as the brief states it, test-first, and each of
its conditions is covered by a test that fails when that condition is removed. **On the real files
it removes nothing, and the output is byte-identical to 281a569.** Measured before any code was
written: at 281a569 neither file has a pair that meets the five conditions, and **A's z 1612.2
landing is not among the pairs**. The brief's premise is stale (section 1). The one place in the
output where two faces still z-fight is a riser on A (48.27 sq in). It fails condition 1 before
the merge and condition 3 after it, so the rule keeps both faces. Deciding what to do with it is
for the owner and the controller (section 6).

| Commit | Item |
|---|---|
| 551de1b | `feat(engine): one copy of an exactly stacked, opposite-wound, same-material surface goes`: the rule, the fixture, 14 tests |
| 6c7ad6e | `feat(cli): report.json lists every stacked opposite-wound pair and the run prints the count` (1 test) |
| e81e72a | `refactor(cli): the stacked-copies count no longer shares its name with the .skp line's text` (rename only) |
| (this file) | `docs(record): brief 13 report` with the scripts under `docs/superpowers/records/scripts/brief13/` and `render_skp_closeup.py` |

**Suite:** `-m pytest engine/tests -q -p no:cacheprovider`: 589 passed at 281a569, 603 at 551de1b,
and at e81e72a `604 passed in 355.50s (0:05:55)`.

## 1. Measured first, at 281a569

A pair is EXACTLY coincident here when every corner of each face lies within 0.001 in of the
other's plane, the faces are parallel, and each covers at least 0.99 of the other. The search is
`docs/superpowers/records/scripts/brief13/measure_stacked_pairs.py`. It is independent of the
engine's own search (it has its own UV comparison), and the two agree: the engine's
`find_coincident_pairs` finds 11 pairs on A's reference and 21 on B's, the same as the script.

| | input | reference (solidified) | final output |
|---|---|---|---|
| A | 11 pairs, all opposite-wound, all the same material, **all different UV mapping** | 11, the same | **1 opposite-wound** (same material, UV 0.4997 tile apart) + 1 same-wound |
| B | 31 pairs, all opposite-wound; 24 different materials (ltstone_-5 / ltstone_-3), 7 the same; **all different UV mapping** | 21 (14 different, 7 same) | **none** |

The input counts are the export's own: A 11, B 31, 24 of B's with a different front and back
material. The engine's own `uv_mapping_residual` measures how far each copy's texture sits from
its original's, as the largest distance from one whole-tile shift. On A it is 0.71 to 2.0 tiles,
on B 0.35 to 2.0 tiles, against a tolerance of 0.02: the maps are shifted, and the many values
near 1 and 2 are mirrored maps. Every material in both files is flat, though: texture std 3.04,
under the 8.0 threshold.

**Where the export's copies go** (per face, the pass that removes it; the same at 281a569 and after
this brief):

| | pairs | fate |
|---|---|---|
| A | 9 | both faces hidden (exposure 0), removed by the hidden pass |
| A | 2 | one face flipped (its only exposure is on its back), then one of the now same-wound pair removed as a duplicate layer |
| B | 21 (14 different, 7 same material) | both hidden |
| B | 6 (different materials) | both replaced by solidify's side rebuild |
| B | 4 (different materials) | one hidden, one replaced by solidify |

So no export copy reaches the output, and none reaches the stage where this rule runs. A copy that
is seen from one side only has its only exposure on its back. The per-face orientation step
therefore flips it (`ORIENT_FLIP`). After that it is a SAME-wound duplicate, and on a flat material
the region builder ignores UVs, so the duplicate-layer pass removes it. The only opposite-wound
copies that can survive to this rule are THIN ones, seen from both sides about equally, which the
flip never touches.

**A's z 1612.2 landing** (x 1384-1443, y 22591-22630, the place named in the session record's item
8 and in the brief) is not a pair at 281a569:
- in the export, the double layer there is SAME-wound: 15 faces facing up, 4,586.8 sq in over a
  2,741.2 sq in footprint, and a single face facing down, a 0.5 sq in fold sliver (input face 174);
- at 281a569, nine of those faces are hidden and removed by the hidden pass. A ray straight up from
  each meets, 9.8 in above at z 1622.0, the bottom solidify now invents for the raised walkway
  crossing the landing (reference faces 4616 and 4620, facing down). The sliver is removed as a
  fold member (its folds with 161 and 163).
- the final output there is 8 faces facing up, 2,924.2 sq in over a 2,923.8 sq in footprint: one
  layer.
The opposite winding recorded in brief 03 (morning of 09-25) was not traced again here. A likely
cause, unverified: before brief 11 closed the walkway's bottom and the two holes in the lower
landing's underside (0a81860, 281a569), one layer was seen from below and was flipped.

**The one opposite-wound pair in A's output** is a riser, not the landing. It is final faces 131
(facing +x) and 729 (facing -x): a triangle of 48.27 sq in at x 1305.14, y 22659.6-22669.4,
z 1612.2-1622.05, standing on the lower landing. Its two faces are the same material, and their
UV mappings are 0.4997 tile apart. It is not a copy in the export:
- 131 is the lower part of reference face 98 (96.48 sq in, facing +x). 98 is a thin face: front
  exposure 0.0039, back 0.0078.
- 729 is one triangle of the merged region of reference faces 4195 and 4196 (97.02 sq in each). Both
  are lopsided (back exposure 0.0625 and 0.0078, front 0.002), so both are flipped to face -x.
- Before the merge, 98 overlaps 4195 by 19.23 sq in (0.20 of each face) and 4196 by 53.16 sq in
  (0.55 of each). That is a partial overlap, and condition 1 rejects it. Their UV maps are also
  1.0 tile apart (mirrored). The merge threads 98 at the T-vertex (22669.4, 1622.05) and
  triangulates the region, and only then do two triangles coincide exactly.
- In the `.skp` it is SketchUp faces 82 (+x) and 474 (-x, a pentagon). The SketchUp audit draws the
  double layer's edges as lines inside a surface there (section 4).

The final output also holds one SAME-wound exact pair on A: faces 532 and 559, 24.6 sq in, flat
at z 1779.53, the same UV. The duplicate-layer pass's region rule left it. It is outside this
brief and is listed in section 6.

## 2. The rule (551de1b)

It is `engine.fixes.overlap.plan_coincident_removal`. It runs inside `remove_overlaps`, after the
flip and before the merge, and its proposals go through the SAME strict `guard_feedback` call as
the duplicate layers. `fix_object` hands it each face's side exposure from the REFERENCE mesh,
swapped for faces the orientation step flipped. It reduces a pair to one face only when all of
these hold:

1. **Exactly coincident.** This is `find_coincident_pairs`: face by face, every corner within
   0.001 in (`COINCIDENT_PLANE_TOL`) of the other's plane, and each covering at least 0.99
   (`COINCIDENT_COVER`) of the other, both ways. It deliberately does not use the plane groups the
   engine builds with its 0.15 in tolerance.
2. **Opposite windings**, parallel within `PLANE_PARALLEL_DOT`. Faces the duplicate-layer pass
   already proposes take no part.
3. **The same material** (otherwise the reason is "different materials") **and the same UV mapping
   modulo whole tiles** (otherwise "different UV mapping"). The UV test is `uv_mapping_residual`:
   the two affine UV maps are compared at all six corners against the one whole-tile shift the
   first corner shows, within 0.02 tile, which is `build_regions`' own `uv_tol`. It applies to
   every material, flat or not. That is the brief's text, and section 6 comes back to it.
4. **Which face stays.** The face whose front faces the more exposed side. Each side is sampled
   twice (one face's front is the other's back) and the two samples are averaged. A pair seen from
   both sides is marked `seen_from_both_sides`, and an exact tie keeps both faces ("exposure tie").
   The choice is then MEASURED, because no guard can see a back face. `side_pixels` counts, over
   the 26 guard views at the guard size, the pixels whose first hit is either face, by the side
   the ray comes from. This is independent of which face won the z-fight tie. If the views see
   the kept side less than the other side, both faces stay ("the guard views see the other side
   more"). This check only narrows the rule.
5. **The guard and the report.** Pairs never contradict each other ("conflicts with another pair"
   keeps both faces), and a face the strict guard puts back is reported "put back by the guard".
   Whole faces only: no vertex is moved or invented. Every pair found is reported with its verdict:
   reference face ids, area, plane `[nx, ny, nz, d]` and centroid in model coordinates, materials,
   UV residual, the exposure and the pixels of each side, the face kept and removed, the kept
   face's front normal, and the reason. It goes into `FixResult.coincident_pairs`,
   `removed_coincident` and `n_removed_coincident`, and into report.json (6c7ad6e). `fix` prints
   `stacked copies: N exactly stacked opposite-wound pairs, M faces removed; k kept: <reason>`.

For a same-material exact pair, the guard's classification cannot even raise `zfight_tie`. The
pixel keeps its material, and its surface moves by at most 0.001 in, so it is `PX_OK`.

**Why the tests use an open tray.** The brief's test 1 names "a slab plus a copy of its top". On a
closed slab that case already passes at 281a569, measured: the copy is seen only from above, so it
is flipped and then removed as a same-wound duplicate. So the fixture
`open_tray_with_a_copy_of_its_top` (appended at the end of `build.py`) is a slab with three skirts
and no bottom. Its top is seen from below as well, both copies are thin, and 281a569 shipped both
layers (3,200 sq in at z = 0).

**Tests.** Each test was seen failing before the code it covers existed. The brief's first case
failed at 281a569, which shipped both layers. The other three failed against a first rule that
paired any opposite-wound overlap and compared neither materials nor UVs. The tie, guard-view and
conflict tests at first failed with a TypeError, because the plan did not yet take a view size. Then `scripts/brief13/mutate_conditions.py` removed each condition
once, on the tree committed as 551de1b. All 10 mutations were caught, and every file was restored
byte for byte. (The "half" case was redrawn as a middle band during the work, for the reason given
below. It was then seen failing under the coverage mutation.)

| Test | The change that makes it fail (observed) |
|---|---|
| `test_an_exactly_stacked_opposite_wound_copy_loses_the_face_turned_away` | the rule undone (no side exposure passed): 3,200 sq in at z = 0 instead of 1,600, as 281a569 shipped |
| `test_a_stacked_copy_in_another_material_keeps_both_faces` | materials not compared |
| `test_an_offset_or_partial_copy_is_not_a_pair_and_keeps_both_faces[offset 0.01]` | plane tolerance 0.15 in instead of 0.001 in (the offset copy becomes a pair) |
| `test_an_offset_or_partial_copy_is_not_a_pair_and_keeps_both_faces[half]` | any overlap instead of 0.99 both ways (the half copy is removed) |
| `test_a_stacked_copy_whose_uvs_are_shifted_half_a_tile_keeps_both_faces` | UV mappings not compared |
| `test_a_stacked_copy_whose_uvs_are_shifted_whole_tiles_is_the_same_surface` | UVs compared as numbers, without the whole-tile shift |
| `test_an_exposure_tie_keeps_both_faces` | a tie falls to one face |
| `test_the_side_the_guard_views_see_less_is_never_the_one_kept` | exposure alone decides |
| `test_two_pairs_that_disagree_about_one_face_never_remove_the_face_one_of_them_keeps` | pairs may contradict each other |
| `test_a_pair_the_guard_puts_back_is_reported_as_kept` (and the `fix_object` twin) | the guard's put-backs not written into the pairs |

Also: the pair search on the fixture and on a same-wound duplicate; `remove_overlaps` without side
exposure touches nothing (the old call); `test_fix_object_never_re_winds_a_face_lying_on_another`
still passes (its patch is inset, a partial overlap); the CLI report test.

Two fixture details had to be settled while doing this:
- The "half" copy covers the middle half of the top, x 10-30. A half copy starting at x = 0 shares
  the top's edge and is a FOLD, which the existing fold pass removes (measured). The rule under test
  would then be the wrong one.
- The offset test moves the tray to y = 24,000 in. The real files' 0.1 in print step makes the
  engine's own plane tolerance 0.15 in there, so a 0.01 in offset is inside it.

## 3. Real runs (code 6c7ad6e; e81e72a renames a local variable only)

`engine.cli fix` via `scripts/brief13/run_fix_keep_result.py` (the CLI's own `main`, the
`FixResult` pickled too), `--out data/out_b13 --skp-dir data/skp_scratch/b13`. The baseline for
281a569 went to `data/out_b13_head` and `data/skp_scratch/b13_head`.

| | A | B |
|---|---|---|
| triangles input / reference / final | 4,692 / 4,803 / **884** | 7,227 / 7,477 / **510** |
| passed, merge rolled back | True, no | True, no |
| invariants | all True | all True |
| back-face px input / reference / final | 569,108 / 455,150 / **18,372** | 464,939 / 362,793 / **2,757** |
| guard_final holes, material_changed, moved_same_flat, moved_other, edge_flicker, grown | 0, 0, 0, 0, 0, 0 | 0, 0, 0, 0, 0, 0 |
| guard_final **zfight_tie** | **1** | **0** |
| guard_final border_shift, crack_closed, fragment_removed | 159, 0, 38 | 35, 4, 10 |
| stacked copies found / removed / kept | 0 / 0 / 0 | 0 / 0 / 0 |
| duplicate layers (same-wound) removed | 11 (61 same-material pairs) | 3 (20 same, 4 different) |

**Identical to 281a569.** Every number above is the same in `data/out_b13_head`. The
`fixed.obj` and `fixed.ngon.obj` of both files are byte-identical: sha256 A `cd0c1649bb8431cd...`
/ `e46bee6516d3ccb3...`, B `f5484051a3dec265...` / `116b2a2b041e74c4...`. report.json differs only
by the two new keys and the `.skp` paths. The rule finds no exactly coincident opposite-wound pair
at its stage in either file, so it renders nothing and removes nothing. Its search costs at most
1.3 s on A and 2.6 s on B (timed on the whole reference mesh, which has more faces than that
stage).

## 4. SketchUp audit (`skp_edge_audit.py`, `data/skp_scratch/b13`)

The output is identical to the audit of the 281a569 `.skp` files, compared by `diff`.

- **A**: 561 faces, 1,202 edges. 7 visible lines inside flat surfaces (6.8 ft), 426 hidden soft
  (3,110.4 ft), 44 non-manifold (84.5 ft), 416 open borders (722.9 ft), 309 shape edges (1,215.6 ft).
  One line inside a surface lies on the riser pair: 9.8 in
  [1305.1, 22669.4, 1612.2]-[1305.1, 22669.4, 1622.0]. Three more start at its top corner and run
  along y 22669.4 at z 1622.0: 9.8 in, 9.8 in and 19.7 in, the T-vertex the merge threaded 98 at.
  The T-junction list has a 19.7 in line along the riser's top,
  [1305.1, 22649.7, 1622.0]-[1305.1, 22669.4, 1622.0]. So the double layer shows as lines in
  SketchUp as well. There is also a 41.5 in T-junction line on the z 1612.2 landing,
  [1413.4, 22590.7, 1612.2]-[1374.0, 22603.8, 1612.2]: the edge the removed fold sliver shared with
  face 163.
- **B**: 183 faces, 523 edges. No line inside a flat surface; 129 hidden soft, 15 coplanar material
  borders (233.4 ft), 14 non-manifold, 172 open borders, 193 shape edges; 15 T-junction lines
  inside a surface (31.8 ft).

## 5. Close-up of A's lower landing, before and after

`docs/superpowers/records/scripts/render_skp_closeup.py` is `render_skp.py`'s reading and
renderer, framed on a box, drawn twice: shaded double-sided as `render_skp.py` draws, and coloured
by side the way SketchUp shows it, with the front grey and the back purple. Box x 1090-1450,
y 22425-22835, z 1595-1640, 7 views, 1600 x 1000. Before: `data/skp_render/b13/A_head_landing/`.
After: `data/skp_render/b13/A_after_landing/`.

All 14 images are **pixel-identical** before and after (0 differing pixels in each). What they
show, read from `top_sides.png`, `obl_top_a_sides.png`, `obl_top_b_sides.png` and
`obl_bot_a_sides.png`:
- the lower landing is one flat top, with the raised walkway crossing it at the upper right, its
  curved edge and steps, and a separate slab strip on the left;
- short T-junction lines sit on the landing's surface;
- from below, the underside is one grey sheet with stepped lines (brief 11's subject) and no purple;
- there are small purple patches: 1,875 px from the top, 573 to 2,094 px from the obliques. They
  were counted by face. Some are bottoms at z 1582.7 facing down (SketchUp faces 63, 44, 58 and 43),
  seen from above along the raised walkway's diagonal edge. The rest are walls at x 1275.6, 1315.0,
  1334.7 and 1374.0 and at y 22748.2 and 22826.9 seen from their back (faces 30, 24, 481, 524, 469,
  519 and others). None of them is a stacked copy. They are back faces of the kind brief 11 works
  on.
The riser pair shows no purple in these renders. Where two faces tie, the ray caster picks the same
one every time; Unity's z-fight does not.

## 6. What is left (decisions, not code)

1. **The riser on A still z-fights**: final faces 131/729, 48.27 sq in at x 1305.14, over a partial
   double layer of about 72 sq in (98's lower part over the flipped 4195/4196). To remove it would
   take a rule for PARTIAL opposite-wound overlaps, or cutting faces. Cutting faces invents
   vertices, which only solidify may do. Both are outside this brief.
2. **Condition 3 and flat materials.** Every material in A and B is flat (std 3.04), and every
   export copy's UV mapping differs from its original's. The engine already treats UV as invisible
   on a flat material: the region builder ignores it, and a lopsided copy is flipped and removed as
   a duplicate whatever its UVs. As written, condition 3 keeps a THIN same-material copy on a flat
   material whenever its UVs differ. Reading it as "the same UV mapping modulo whole tiles, or a
   flat material" would widen the exception. That is the owner's call, and it would still not
   touch the riser (condition 1).
3. **The same-wound exact pair on A** (faces 532/559, 24.6 sq in at z 1779.53, the same UV) is left
   by the duplicate-layer pass's region rule. It is a separate leftover, not traced here.
4. **Records.** HANDOFF.md, WORK-CLAIMS.md and the session record were not touched, as instructed.
   Two changes are due at the merge:
   - the blocked-operation text needs the brief 13 exception;
   - the session record's item 8 ("File A ships a coincident double layer with opposite windings")
     is stale at 281a569, as section 1 shows.
   The owner's folder was not written. Nothing to refresh: the output is byte-identical to
   281a569's.
