# Reconcile of the side rebuild into feat-dashboard (brief 03)

Date: 2026-09-25. Main checkout, branch `feat-dashboard`, from ef12b98. Merged `feat/side-rebuild`
at fafd4d6 (its worktree `.claude/worktrees/side-rebuild` was only read). Brief:
`docs/superpowers/records/briefs/03-reconcile-and-verify.md`, steps 1-5.

**Status: DONE_WITH_CONCERNS.** The merge keeps every line of both branches. The one test the merge
broke is fixed in its own commit. One composition gap in the final guard, found by reading, is
closed with a test. Both real runs pass, no merge rolls back, and the owner's two `.skp` files are
rewritten (A 08:52, B 08:50). The owner's ramp is a clean wall in the written `.skp`. Concerns are
at the end.

| Commit | What |
|---|---|
| 68f6d15 | `Merge branch 'feat/side-rebuild' into feat-dashboard` (textual resolution only) |
| a89f771 | `test(engine): the solidify stub carries the side rebuild's replaced mask` |
| 82adc60 | `fix(engine): a removed fragment's pixel is never a crack the merge opened` |
| ca463c2 | `test(engine): the faces the side rebuild invents reach the debris pass protected` |

**Suite:** `542 passed in 130.67s (0:02:10)` at ca463c2, clean tree
(`python -m pytest engine/tests -q -p no:cacheprovider`; 497 on feat-dashboard at ef12b98, 427 on
the side-rebuild branch). On the merge tree alone: 540 collected, 539 passed, 1 failed (section
2); with a89f771 and 82adc60: 541 passed.

## 1. The merge (68f6d15)

`git merge --no-ff --no-commit feat/side-rebuild` stopped on five files, as the dry run said.

| File | Conflict | Resolution |
|---|---|---|
| `engine/cli.py` | `cmd_fix`'s closing prints. The side rebuild added the `backface_px final=...` line before `wrote <out_dir> (and N QA images)`. feat-dashboard replaced that line with the QA-written / "QA sheet NOT written" branch, because the QA sheet is an optional export and `qa` may not exist. | Both kept: the backface_px line first, then feat-dashboard's branch. The side rebuild's `len(qa)` line is gone because feat-dashboard's branch replaces it. |
| `engine/fixes/pipeline.py` | `FixResult`: the side rebuild added `backface_px` before `feedback_history`; feat-dashboard rewrote `feedback_history`'s comment for `"fragment_rays"`. | Both kept: `backface_px` with its comment, then feat-dashboard's comment. |
| `engine/tests/fixtures/build.py` | Both append fixtures at the end. | Both blocks, feat-dashboard's first. |
| `engine/tests/test_cli.py` | Both append tests at the end. | Both blocks, feat-dashboard's first. |
| `engine/tests/test_guard.py` | Both append tests at the end. | Both blocks, feat-dashboard's first. |

Auto-merged files were read hunk by hunk:
- `engine/guard/compare.py`. Both sides changed `_classify`. feat-dashboard added `PX_GROWN`,
  limited the fragment excuse to what AFTER may show, and moved `base = codes.copy()` BEFORE the
  fragment stamp. The side rebuild added its opened-crack block after the border-shift step.
  `solidify_feedback` is the side rebuild's alone. See section 3 for the one interaction.
- `engine/fixes/pipeline.py`'s other hunks: solidify's `replaced` beside feat-dashboard's
  protected faces, the back-face counts beside `exposed_final`, and `FixResult(...)`.
- `engine/cli.py`'s report.json and preview-data hunks, and `engine/tests/test_pipeline.py`.

Checks on the merged tree (scratch `ast_check.py`, and a diff of diffs):
- Every file the merge touched parses. No top-level name is bound twice in any of them, and no
  conflict marker is left.
- Over `engine/`, the merged tree's change lines against feat-dashboard are exactly
  feat/side-rebuild's own change lines since the merge base (e182922), and the reverse holds too.
  The only exception is where blank separator lines fall between appended blocks. So nothing of
  either side was lost or rewritten.
- `engine/` imports nothing from `api`, `spike`, fastapi or sqlalchemy. trimesh is imported only
  in `engine/rays/`, and ctypes only in `engine/io/skp_writer.py`.

## 2. The test the merge broke (a89f771)

The merge tree failed one of 540: `test_fragments.py::test_fix_object_never_removes_a_face_solidify_invented`.
- The test is feat-dashboard's (74adf48, brief 08). It stubs solidify with
  `SolidifyResult(mesh, new_faces, report)`.
- The side rebuild (65e566c, SR2) made `replaced` a required field, so the stub raised TypeError
  before `fix_object` ran.
- The test's assumption broke, not the engine. The stray is appended to the SOLIDIFIED mesh, so
  the input's replaced mask is solidify's own. The stub now passes `replaced=made.replaced`.
- Every assertion is unchanged and passes. The closed slab gets no wall or bottom from the side
  rebuild (reference = slab + the stray). The stray is protected, it ships, and the run passes.

## 3. How the two branches compose

**The pipeline order.** solidify, now with the side rebuild, runs first and hands back the
reference. The reference is the input's faces minus the replaced pieces, in order, then every
invented face. Everything after runs on that reference:
- the exposure and the hidden pass;
- the debris pass (rays through each piece, then the fragment guard);
- the folds;
- the overlap pass, the merge and the guards.

Consequences:
- **Invented faces are protected exactly as before.** `SolidifyResult.new_faces` marks every face
  solidify invented over that layout, walls and bottoms of the side rebuild included.
  `fix_object` hands `new_faces[kept]` to `detect_fragments` and `detect_folds` as `protected`,
  the path 74adf48 made for solidify's earlier walls and bottoms. So an invented face is never a
  sliver and never part of a fragment, and a fold holding one is only reported.
- **ca463c2 pins it.** On `slab_with_sawtooth_side`, whose 4 teeth are replaced by one wall, the
  fragment report's `n_protected_faces` equals the invented faces the hidden pass left, and none
  is removed. Mutation, run on a scratch copy of HEAD: taking the invented faces as the rows past
  the INPUT's face count fails the test. That is the pre-side-rebuild layout, "solidify only
  appends", and it is off by exactly the replaced pieces. It fails only this test.
- **Replaced pieces are never debris candidates.** They are not in the reference.
  `side_exposure`, which the rays, the fragment guard and the final guard read, is measured with
  the rebuilt sides closed.
- **The bbox invariant (M2)** compares the vertices that surviving reference faces use. Replaced
  pieces are not reference faces.
- **On the real files**, solidify, the cap guard and the hidden pass give exactly the side-rebuild
  branch's numbers: the same reference (A 4,933, B 7,443 triangles), the same cap-guard rounds,
  and the same hidden removals (A 2,063, B 2,734). The branches first differ at the debris pass.

**The one interaction in the final guard (82adc60).** feat-dashboard now takes `base` before the
fragment stamp. So a pixel whose BEFORE hit is removed debris, and whose AFTER shows a side the
reference never exposed, keeps its failing base class, `codes == base`. The side rebuild's
opened-crack block selects failing pixels by that test, so it also took these and excused a debris
removal that uncovered the inside as a sub-tolerance `border_shift`. Neither branch did that:
- on feat/side-rebuild every removed-debris pixel was `fragment_removed`;
- feat-dashboard had no opened-crack rule.

Measured on the new test's scene. A 0.02 in sliver fills `_crack_scene`'s crack and is the debris
removed; 25 pixels fall through to the lower surface. Final guard at 0.15 in, scratch
`opened_crack_scenario.py`:

| Engine | lower side exposed | lower side NOT exposed (the inside) |
|---|---|---|
| feat-dashboard alone (ef12b98) | fragment_removed 25, passed | moved_other 25, **passed False** |
| feat/side-rebuild alone (fafd4d6; no `exposed_after`) | fragment_removed 25, passed | fragment_removed 25, passed |
| merge (a89f771) | fragment_removed 25, passed | **border_shift 25, passed True** |
| 82adc60 | fragment_removed 25, passed | moved_other 25, passed False |

The opened-crack rule now skips a pixel whose BEFORE hit is removed debris. The merge did not
open that gap. What a removal may uncover is already decided by the fragment rule (review C2).
- SR6's own tests still pass: an opened 0.02 in crack is a border shift, and a lost triangle
  still fails.
- The change only removes a path the merge created.
- It changed nothing on the real files. Every view of every guard, on both files, has 0 pixels in
  a failing class. The fix only acts on a removed-debris pixel that still fails after the tie,
  crack and ring tests, and there is none.

## 4. Real runs (engine ca463c2)

`python -m engine.cli fix data/snapshots/<A|B> --out data/output`, then `preview-data` for both.
All exited 0. Order and times: A 08:47:05-08:48:28, B 08:49:09-08:50:31, A again
08:50:31-08:52:06, then preview-data 08:52:06-08:54:42.

| | A `CHTM_SIDE_WALK_2nd_floor` | B `CHTM_2nd_to_3rd_building_sidewalk_outside` |
|---|---|---|
| triangles in / reference / out | 4,692 / 4,933 / **1,044** | 7,227 / 7,443 / **530** |
| passed | **True** | **True** |
| invariants | material_count_same, bbox_same, area_not_grown, cap_guard_passed, guard_passed: all True | all True |
| merge | 147 regions merged, none skipped, **not rolled back** (merge `tris_after` 1,044 = shipped); T-vertices 418 -> 0, 112 edges split | 72 merged, 1 skipped (overlap), **not rolled back** (530 = shipped); T-vertices 377 -> 0, 41 edges split |
| backface_px input / reference / final | 568,683 / 454,537 / **20,945** | 464,939 / 373,002 / **5,993** |
| sides_rebuilt | 92 edges, 2,672.6 in | 35 edges, 1,179.7 in |
| side pieces replaced | 105 (walls 49, bottoms 56); 7 restored | 45 (walls 45); 14 restored |
| interior faces covered | 598 | 442 |
| wall faces refused | 392: outside footprint 355, below bottom 32, coincides 5 | 90: outside 56, below bottom 28, coincides 6 |
| bottom faces refused | 230: outside 222, partial underside 7, coincides 1 | 61: outside 40, partial underside 19, below bottom 2 |
| cap guard (new, failing, removed, restored) | passed: (962, 23,668, 569, 10), (393, 1,705, 44, 1), (349, 6, 3, 0), (346, 0, 0, 0) | passed: (406, 14,699, 116, 29), (290, 2,798, 27, 1), (263, 234, 2, 0), (261, 0, 0, 0) |
| removed: hidden / zero-area / overlap | 2,063 / 217 / 16 | 2,734 / 79 / 5 |
| debris removed | 2 slivers, 0 fragments, **26 fold members** | 1 sliver, 0 fragments, **6 fold members** |
| slivers removed | 3852 (0.0519 sq in, 0.0077 in wide; 16,384 lines, 0 inside; feat-dashboard's 3908, same bbox) and **3491, new** (0.0267 sq in, 0.0044 in wide, x 2582.5-2594.5 at y 22826.9; 1,082 lines, 0 inside) | 5590 (0.0638 sq in, 0.0047 in; 15,567 lines, 0 inside; feat-dashboard's 5634, same bbox) |
| refused by the rays | 4 units: slivers 3496 (256 lines reach an unexposed side) and 4554 (3,841); fold members 3112 (1,199) and 3717 (464) | 3: fold members 5629 (41), 5632 (82), 5804 (89) |
| folds | 36 found: 30 resolved, 6 left (3 protected, 3 refused by the rays); 3 duplicate pairs | 14 found: 7 resolved, 7 left (4 refused by the rays, 1 protected, 1 different materials, 1 neither covered); 1 duplicate pair |
| fragment detector | 11 components, 3 protected (313 protected faces); 16 thin, 12 sandwiched | 4 components, 0 protected (113 protected faces); 8 thin, 7 sandwiched |
| flipped / thin sheets | 640 / 65 | 723 / 3 |
| `.skp` | 622 faces, 1,397 edges, 426 hidden, writer's lines inside surfaces 5; 0 missing, 0 unexpected; `sketchup_check_changed` False; copied to `OBJ FIXED RESULT` | 211 faces, 571 edges, 146 hidden, 4; 0 / 0; False; copied |
| QA / preview-data | 21 images / 1,044 shipped, damaged 0, guard passed | 21 images / 530, damaged 0, guard passed |

**Every guard total.** Model px are A 2,065,994 and B 2,432,650 in every guard. Every count not
listed is 0: holes, material_changed, moved_same_flat, moved_other, edge_flicker (and its four
parts), grown and zfight_tie_grown.

| Guard | A | B |
|---|---|---|
| `guard_after_removal` | passed; fragment_removed 33 | passed; zfight_tie 38, fragment_removed 6 |
| `guard_merge_attempt` (= `guard_final`) | passed; crack_closed 2, fragment_removed 33, border_shift 143; grown_base 63 = border_shift_grown 63 | passed; zfight_tie 46, crack_closed 4, fragment_removed 6, border_shift 36; grown_base 5 (border_shift_grown 3, crack_closed_grown 2) |

**Determinism.** Two runs of A (finished 08:48 and 08:52) give a byte-identical `report.json`, sha256
`f9db2f086c503e52dbe7d04b0a4bc324bf16b8068ff807156ca7662be6a91ae0`. B's is `c919bdd2...13dd35`
(one run).

## 5. Against the side-rebuild branch alone and feat-dashboard before the merge

The three sets of numbers come from each run's own `report.json`:
- feat-dashboard's owner files of 08:00/08:01 at 3d30327, kept before the rerun;
- the side-rebuild worktree's 07:28/07:30 run at 8d238c4;
- this merge.

"Threading off" is the merged engine with the merge's two threading passes replaced by no-ops
(scratch `no_threading.py`). It writes nothing into the repo.

| | feat-dashboard (before) | side rebuild alone | merge | merge, threading off |
|---|---|---|---|---|
| A triangles | 1,031 | 876 | **1,044** | 901 |
| B triangles | 600 | 486 | **530** | 481 |
| A back faces, final | 119,504 (one-sided holes) | 20,793 | **20,945** | 20,784 |
| B back faces, final | 21,948 | 6,006 | **5,993** | 5,994 |
| ramp close-up back px, views 0 / 1 / 2 | 9,639 / 31,751 / 34,269 | 948 / 2,674 / 590 | **948 / 2,674 / 590** | - |
| A merge input / regions / copied | 2,591 / 178 / 101 | 2,586 / 147 / 125 | 2,609 / 147 / 145 | 2,609 / 147 / 145 |
| B merge input / regions / copied | 4,746 / 90 / 74 | 4,609 / 71 / 39 | 4,618 / 72 / 43 | 4,618 / 72 / 43 |

**Against the side rebuild alone.** Solidify, the cap guard and the hidden pass are identical. Two
things differ after them.
1. **The debris pass is feat-dashboard's.**
   - The side-rebuild branch forked before briefs 07-09, so its debris pass judged by pixels
     alone. It removed on A 15 fragments, 17 slivers and 35 duplicate-layer faces, and on B 11
     slivers and 10 duplicate-layer faces. (Of the 21 pieces brief 07's rules removed, brief 08
     found 10 were real surface.)
   - The merge removes on A 2 slivers, 26 fold members and 16 duplicate-layer faces, and on B 1
     sliver, 6 fold members and 5 duplicate-layer faces. The slivers and fold members are
     confirmed by the rays through each piece; the duplicate-layer faces by the strict guard.
   - More faces reach the merge: A 2,609 against 2,586, B 4,618 against 4,609.
   - With the threading off, the merged output differs from the side rebuild's by A +25 and B −5
     triangles, and A −9 and B −12 back-face pixels. That is what this pass changes, together with
     whatever else of 28d63df the two no-op passes do not switch off (not separated).
2. **The merge threads T-junction vertices** (28d63df). T-vertices go 418 -> 0 on A and 377 -> 0
   on B, against 140 and 71 left with the threading off.
   - That costs A 143 and B 49 triangles: 1,044 against 901, 530 against 481. It is the same trade
     as T1 (A 902 -> 1,013 then).
   - It moves the back-face count by A +161 and B −1 pixels. A's +161 were traced with scratch
     `backface_threading.py`, `backface_threading2.py` and `backface_threading3.py`:
     - 154 of them are on face 696 and 27 on face 131, in views looking up (116 in view 13). They
       sit at one spot on the lower landing: z 1612.2, x 1383.9-1442.9, y 22590.7-22630.1.
     - There the shipped surface is a DOUBLE LAYER: two coincident faces with opposite windings,
       in the threaded AND the unthreaded output alike. At (1425, 22605, 1612.2) they are faces
       140 (−z) and 696 (+z) threaded, and 122 (−z) and 627 (+z) unthreaded.
     - Both outputs meet it at the same depth (difference 0.000000 in). Only which of the two
       coincident faces the ray tracer reports first changes, and with it whether the pixel counts
       as a back face. The reference's own first hit there is a back face too.
     - This is a tie flip, not a change of geometry. The double layer comes from the export: the
       reference faces covering those points (178 and 4054, 4055 and 4523, 4053) are all input
       rows, below the 4,587 the input keeps after 105 replaced pieces.

The ramp close-up is identical: see section 8.

**Against feat-dashboard before the merge: the side rebuild itself.**
- The reference grows: A 4,846 -> 4,933, B 7,418 -> 7,443.
- Broken sides are replaced by walls and bottoms (A 105 pieces: 49 by walls, 56 by bottoms; B 45,
  all by walls). The inside seen through them is covered and then removed by the hidden pass:
  A 1,985 -> 2,063 hidden, B 2,566 -> 2,734.
- The merge sees fewer, larger regions (A 178 -> 147, B 90 -> 72) and more copied faces on A.
- Thin sheets fall: A 79 -> 65, B 18 -> 3.
- Pixels showing a back face fall on A from 119,504 to 20,945 (−82 %), and on B from 21,948 to
  5,993 (−73 %).
- Net triangles: A +13, B −70.

## 6. SketchUp audit (`docs/superpowers/records/scripts/skp_edge_audit.py`, owner's files)

```
CHTM_SIDE_WALK_2nd_floor.fixed.skp: 622 faces, 1397 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)      17      20.3 ft
  hidden (soft)                                                    426    2890.4 ft
  visible, non-manifold (3+ faces)                                  79     159.4 ft
  visible, open border (1 face)                                    564    1077.6 ft
  visible, shape edge > 5 deg                                      311    1228.2 ft
    line inside a surface:    39.4 in  [2673.2, 22826.9, 1778.1] -> [2673.2, 22787.5, 1778.1]
    line inside a surface:    39.3 in  [2673.2, 23299.3, 1778.1] -> [2673.2, 23260.0, 1778.1]
    line inside a surface:    29.5 in  [1275.6, 22826.9, 1582.7] -> [1275.6, 22826.9, 1612.2]
    line inside a surface:    29.5 in  [2673.2, 23338.7, 1778.1] -> [2673.2, 23309.2, 1778.1]
    line inside a surface:    12.4 in  [2594.5, 22826.9, 1776.2] -> [2582.2, 22826.9, 1774.4]
    line inside a surface:    11.1 in  [2673.2, 23338.7, 1778.1] -> [2683.1, 23343.6, 1779.5]
  visible open edges split:
    open edge = real border of the model                                       380     718.3 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)        3      12.3 ft
    open edge lying on an angled face (face meets a surface it does not split)   181     347.0 ft
      T-junction line:    88.0 in  [1334.7, 22630.1, 1582.7] -> [1413.4, 22630.1, 1622.0]
      T-junction line:    39.4 in  [2633.9, 23063.1, 1777.5] -> [2673.2, 23063.1, 1777.5]
      T-junction line:    19.7 in  [1305.1, 22649.7, 1622.0] -> [1305.1, 22669.4, 1622.0]
CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp: 211 faces, 571 edges
  hidden (soft)                                                    146    1792.6 ft
  visible, material border (coplanar)                               14     228.0 ft
  visible, non-manifold (3+ faces)                                  31      81.8 ft
  visible, open border (1 face)                                    209     712.6 ft
  visible, shape edge > 5 deg                                      171    1802.4 ft
  visible open edges split:
    open edge = real border of the model                                       126     400.6 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)       20      42.3 ft
    open edge lying on an angled face (face meets a surface it does not split)    63     269.7 ft
      T-junction line:    39.7 in  [2121.8, 24204.9, 2042.2] -> [2082.5, 24204.9, 2047.4]
      T-junction line:    39.7 in  [2200.6, 24204.9, 2031.8] -> [2161.2, 24204.9, 2037.0]
      T-junction line:    39.7 in  [2397.4, 24195.0, 2005.9] -> [2358.1, 24195.0, 2011.1]
      T-junction line:    39.7 in  [2358.1, 24195.0, 2005.1] -> [2397.4, 24195.0, 2000.0]
      T-junction line:    39.7 in  [2043.1, 24012.9, 2055.1] -> [2082.5, 24012.9, 2049.9]
```

File B has no "line inside a flat surface" row: the audit found none.

Against the two baselines, audited the same way (the side-rebuild files with its own, older
writer):

| Audit class | A before | A side rebuild | A merge | B before | B side rebuild | B merge |
|---|---|---|---|---|---|---|
| faces / edges | 588 / 1,321 | 527 / 1,281 | **622 / 1,397** | 254 / 690 | 184 / 567 | **211 / 571** |
| hidden (soft) | 397 | 289 | 426 | 149 | 112 | 146 |
| lines inside a flat surface | 8 / 48.8 ft | 30 / 73.6 ft | **17 / 20.3 ft** | 2 / 1.6 ft | 0 | **0** |
| T-junction lines on a coplanar face | 3 / 54.9 ft | 68 / 133.3 ft | **3 / 12.3 ft** | 20 / 47.2 ft | 33 / 54.0 ft | **20 / 42.3 ft** |
| non-manifold | 76 | 40 | 79 | 51 | 16 | 31 |
| material borders | 0 | 0 | 0 | 12 | 13 | 14 |
| open edge = real border | 232 | 328 | 380 | 200 | 133 | 126 |

- A's double-layer lines at x = 2515.8 (511.8 in inside a surface, 551.3 in T-junction) are gone.
  The longest line inside a surface is now 39.4 in.
- A has more lines inside surfaces than before the merge (17 against 8), but a shorter total
  (20.3 against 48.8 ft). Three of the six longest lie along x = 2673.2 at z 1778.1
  (y 22787-23339), and a fourth starts there. What they separate was not traced.
- A's 88.0 in T-junction line at y = 22630.1 is brief 09's accepted fold trade.
- B's 20 T-junction lines were identified before as material seams and double layers (T1 report);
  they were not re-traced here.

## 7. Renders of the written `.skp` files, read

`docs/superpowers/records/scripts/render_skp.py` into `data/skp_render/A` and `data/skp_render/B`.
A: 622 faces -> 1,037 SketchUp triangles, 971 drawn edges. B: 211 faces -> 524 triangles, 425
drawn edges. Read with the Read tool, with crops where a spot needed a closer look.

- **A `obl_top_a`**:
  - Every top reads as one clean surface: the walkway, the big landing and the lower landing.
  - The lower landing's diagonal side stands as a wall. 4 or 5 short dashes lie on its top along
    that edge, with a small zigzag where it meets the ramp's curved foot.
  - No triangle fan is drawn on the lower landing's top.
  - The big landing's far edge still carries a strip of small outlines, boxes and ticks.
- **A `obl_bot_a`**: no holes.
  - The walkway's underside is one surface.
  - The lower landing's underside keeps the staircase-shaped step lines, with a few small
    triangles by the ramp.
  - The big landing's underside carries a fan of thin triangles along one edge, a long thin
    diagonal triangle and small outlines.
  - A small dark triangle hangs under the walkway's start.
- **A `side_low_a`**: the landing, the ramp and the lower block read as solid slabs. A thin wedge
  still runs under the big landing's right-hand underside edge.
- **B `obl_top_a`**:
  - Every top reads as a single face, including the far-right slab, which was a triangle fan on
    the side-rebuild branch's own file.
  - Along the long sloped slab left of the middle, side panels hang below the slope as a stepped
    fin. There is also a small triangular fin and two thin slivers along the edge.
  - A tiny cluster sits at the right-hand junction.
- **B `obl_bot_a`**:
  - The far-left and far-right undersides are single clean faces.
  - The middle slabs still read as trays: side walls hang below a recessed underside with
    internal steps and partitions.
- **B `side_low_a`**:
  - The landings and the ramp's sloped side read as solids.
  - Under the upper-left landing, wall panels hang at different depths, with a see-through slot
    between two of them (not matched to a region number here).
  - At the far-right slab's left end, a few short broken lines and a thin sliver remain.

## 8. The owner's ramp in the WRITTEN `.skp` (file B, region 309)

**Method.** It is the side-rebuild report's close-up method, reused unchanged:
`scratchpad/side-rebuild/closeup.py`'s `render`, with SR6's box (2640, 23620, 1860)-(2980, 23900,
2030) and views (0.581, 0.814, −0.12), (0.581, 0.814, 0.3), (0.9, 0.3, −0.05). Only hits inside
the box count, and a face seen from its back is tinted and counted.

The AFTER mesh is the `.skp` read back through SketchUp's C API (`read_skp`): SketchUp's own
triangles, each wound to its face's own normal (none needed rewinding), and only the edges
SketchUp draws. Scratch `skp_closeup.py`.

**Validated first on the side-rebuild branch's own outputs.** Its fixed.obj and its written
`.skp` both give 948 / 2,674 / 590 back pixels on 43,696 / 85,597 / 91,652 in the input, SR6's
numbers exactly.

| Ramp close-up, back px, views 0 / 1 / 2 | |
|---|---|
| input | 43,696 / 85,597 / 91,652 |
| feat-dashboard's owner file before the merge | 9,639 / 31,751 / 34,269 |
| side-rebuild branch, its written `.skp` | 948 / 2,674 / 590 |
| **merge, the written `.skp`** (and its fixed.obj) | **948 / 2,674 / 590** (same) |

Pixel diff of the merged and side-rebuild AFTER panels: 5, 11 and 2 pixels differ of 814,000 per
view.

**What view 0 shows** (`B_merged_skp_ramp_v0.png`, input beside the merge).
- In the input, the sloped side is jagged and see-through: triangular teeth, gaps and purple back
  faces.
- In the written `.skp` it is one continuous grey wall along the whole slope: no teeth, no gaps,
  no purple along it.
- What is left:
  - a thin purple plate under the landing's end face at the upper-left end, beside a narrow wedge
    between that end face and the new wall (brief 10 item 5);
  - one short drawn edge running from the wall's lower edge into the wall near the middle;
  - a 1-2 px tick on the underside.
- feat-dashboard's file before the merge still showed the sawtooth: teeth with gaps and purple
  between them.

## 9. Concerns

1. **The merge commit alone is not green.** 68f6d15 fails 1 of 540 tests, for the cross-branch
   reason in section 2. That fix went into its own commit, as the task asked, instead of into
   the merge. HEAD is green.
2. **Triangles against the side rebuild alone: A 1,044 against 876, B 530 against 486.** The
   threading costs 143 and 49 triangles, to take T-vertices to 0 (no cracks or sparkle in Unity).
   This is the same trade T1 made. Whether to keep it on these files is the owner's call.
3. **A's audit has more lines inside flat surfaces than before the merge** (17 against 8, though
   20.3 against 48.8 ft). Three of the six longest lie along x = 2673.2 at z 1778.1. Not traced.
4. **Still visibly wrong** (renders, section 7):
   - B's middle slabs read as trays from below, and under its upper-left landing panels hang at
     different depths with a see-through slot (brief 10 items 1-2 are the known causes of such
     gaps; this spot was not traced);
   - B's sloped slab hangs a stepped fin;
   - the purple plate at the ramp's landing end (brief 10 item 5);
   - on A: the clutter along the big landing's far edge, the step lines and fans on the
     undersides, and the thin wedge under the big landing's right edge.
5. **Worse than feat-dashboard before the merge, all tolerated or known:**
   - z-fight ties on B: 2 -> 46 px, never failures, 39 on the side-rebuild branch;
   - non-manifold edges on A: 76 -> 79 (B improves, 51 -> 31);
   - wall faces refused, and the other SR6 numbers brief 10 item 4 lists, are unchanged by the
     merge.
6. **The new A sliver 3491** was not removed on feat-dashboard before the merge. The rays confirm
   it (1,082 lines, 0 reaching an unexposed side). Why it became a candidate after the side
   rebuild was not traced.
7. **A ships a coincident double layer with opposite windings** on its lower landing at z 1612.2
   (x 1383.9-1442.9, y 22590.7-22630.1). It was found while tracing the threading's +161
   back-face pixels (section 5). Both layers come from the export, and they will z-fight in
   SketchUp and Unity. Neither the fold pass nor the duplicate-layer pass removed either one; why
   was not traced.

## Public signatures

This reconcile changes no public signature of its own. `_classify` is private and its signature is
unchanged; since 82adc60 its opened-crack rule never takes a pixel whose BEFORE hit is removed
debris. What feat-dashboard gains from the merge is the side rebuild's, as recorded in
`side-rebuild-report.md`:

```
engine/fixes/orient.py
face_unit_normals(positions_c, faces) -> np.ndarray                                  # NEW (SR0)
backface_counts(rendered, normals) -> list[int]                                      # NEW (SR0)
backface_pixels(positions_c, faces, face_ids, views, size, caster_factory=EmbreeCaster)
    -> list[int]                                                                     # NEW (SR0)
one_sided_holes(...) -> int          # unchanged signature; now sum(backface_pixels(...))

engine/fixes/pipeline.py
FixProfile.side_band: float = 2.5                                                    # NEW (SR2)
FixProfile.skirt_search_radius: float = 60.0                                         # kept, UNUSED since SR5
FixResult.backface_px: dict          # NEW {"input"|"reference"|"final": {"total", "per_view"}}
FixResult.replaced_input: np.ndarray # NEW bool over INPUT faces
# FixResult.reference_mesh is now the input minus replaced_input, in order, then solidify's new
# faces (it used to start with every input face). FixResult keeps all of feat-dashboard's fields
# (fragment_removals, fragment_ray_check, n_refused_by_rays, n_removed_folds, fold_report,
# exposed_final, ...).

engine/fixes/solidify.py
SolidifyResult.replaced: np.ndarray  # NEW, REQUIRED: bool over INPUT faces
solidify(mesh, topo, profile) -> SolidifyResult   # signature unchanged; report gains the SR2-SR6
    # keys (sides_rebuilt, side_pieces_replaced(_by), side_pieces_restored,
    # interior_faces_covered, walls_refused, bottom_faces_refused, sides_intact, edges_continued,
    # top_regions_continued, undersides_not_tops, open_outline_edges, side_band,
    # regions_deeper_than_own_sides, representative_side_per_region, walls_to_lower_surface)
SIDE_WHOLE_FRACTION = 0.99; PIECE_MAX_ANGLE_DEG = 30.0; SIDE_BAND_MAX = 3.0; _COINCIDENT_ANGLE_DEG = 1.0

engine/guard/compare.py
INTERIOR_INSIDE = 0; INTERIOR_OUTSIDE_FOOTPRINT = 1; INTERIOR_BELOW_BOTTOM = 2
INTERIOR_AT_OR_ABOVE_TOP = 3; INTERIOR_UNMEASURED = 4; INTERIOR_UNDERSIDE = 5       # NEW
solidify_feedback(positions_c, faces_before, faces_after, is_new, front_exposure_before,
                  cover_max_exposure=0.10, views=VIEWS_26, size=(900, 600),
                  caster_factory=EmbreeCaster, max_rounds=8, *, replaced_group=None,
                  new_group=None, side_band=0.0, interior=None, interior_step=0.25,
                  back_exposure_before=None, parallel_interior_ok=None, shell_faces=None,
                  refused_before=None, piece_cover=None)
    -> (keep, history, detail)       # CHANGED: returns 3
_classify(...)   # signature unchanged; SR6's opened hairline crack is a border shift, never for a
                 # pixel whose BEFORE hit is removed debris (82adc60)

engine/cli.py
report.json: + "backface_px"; "profile" + "side_band"
stdout: + "  sides rebuilt: ..." after the solidify line, + "  backface_px final=N (input=...,
        reference=...)" before the "wrote <out_dir>" / "QA sheet NOT written" line
preview-data stats: + "side_pieces_replaced"; the BEFORE pane is the input mesh, replaced pieces
        drawn as removed

engine/tests/fixtures/build.py (the side rebuild's, appended after feat-dashboard's)
_slab_rows, slab_with_sawtooth_side, slab_with_railing_outside, slab_with_half_side,
slab_with_side_behind_a_t_junction, two_slabs_meeting_at_a_t_junction,
slab_continuing_under_a_landing, slab_with_a_lip, sloped_slab, slab_beside_a_lower_top,
slab_with_a_bottom_strip
```
