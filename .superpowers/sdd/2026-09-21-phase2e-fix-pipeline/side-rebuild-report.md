# Side rebuild round (SR0-SR5, M1), 2026-09-24/25

Branch `feat/side-rebuild` (worktree `.claude/worktrees/side-rebuild`), from feat-dashboard a54d1ce;
the controller merged feat-dashboard at b3b9ad3 in as ce79c44 after SR0. Every number below was
measured in this worktree with `.venv/Scripts/python.exe`; every run of the real files used the
snapshots `ce26e0392ab0` (A) and `0b290ec0bcb4` (B) from the main checkout, `--out data/output`,
`--skp-dir "OBJ FIXED RESULT"`.

**Status: DONE_WITH_CONCERNS.** Every item is committed and tested. Both files pass, neither merge
rolls back, and `report.json` is byte-identical over four runs of A and two of B. But the owner's own
photograph, file B's ramp side, is broken again at HEAD: it was a mostly clean wall after SR2
(f57cb17), and the review fixes SR4 and SR5 reopened it. The fix that restores it is measured below
and was NOT committed, because it makes file A's merge roll back on one pixel (section 7).

**Update, SR6 (section 9, HEAD 8d238c4):** the ramp is a clean wall again (its close-up 948 back
pixels, input 43,696), both merges hold, back faces seen from outside are A 20,793 and B 6,006, and
the section lists what was wrong in sections 1-8.

| Commit | Item |
|---|---|
| ff4a0ec | SR0 `feat(engine): count back faces seen from outside` |
| (ce79c44) | controller's merge of feat-dashboard (b3b9ad3), not mine |
| 65e566c | SR2 `feat(engine): solidify rebuilds a broken side instead of preserving it` |
| f57cb17 | SR2 follow-up `fix(engine): a side is measured at its own depth and a top runs on under a landing` |
| 9562aa3 | SR4 = review C1 `fix(engine): the cap guard measures back-side covers` |
| 6233671 | SR5 = review I1 `fix(engine): an open edge takes its height from the slab's own sides` |
| 0f24da4 | M1 `test(engine): the cap guard's cut-off path is verified after a round that removed faces` |

SR1 was investigation only (no commit). SR3 found no orientation defect, so there is no
`fix(engine): faces of a closed slab face outward` commit (section 5).

Suite at HEAD 0f24da4, clean tree, rerun on 2026-09-25 before this report was committed:
**`415 passed in 66.97s (0:01:06)`** (`python -m pytest engine/tests -q -p no:cacheprovider`; 373 at a54d1ce).

## 1. SR0: back faces seen from outside

`engine.fixes.orient.backface_pixels` renders a face set over the 26 guard views and counts, per view,
the pixels whose FIRST hit is a face met on its back side (`n . d > 1e-9` along the ray). This is
SketchUp's blue-purple, and a one-sided renderer drops those pixels. `backface_counts` counts renders
already made; the pipeline counts the reference from the final guard's own renders. `fix_object`
reports `FixResult.backface_px = {"input" | "reference" | "final": {"total", "per_view"}}`; all three
are framed on the reference. `report.json` carries it, and the CLI prints
`backface_px final=N (input=..., reference=...)`. `one_sided_holes` is now the sum of
`backface_pixels`, so `one_sided_holes_before/after` are unchanged.

Baseline, before any other change (run at 13:51 on ce79c44, the merge that contains SR0's ff4a0ec):

| | input | reference | final |
|---|---|---|---|
| A | 569,539 | 566,368 | **119,610** |
| B | 465,111 | 396,069 | **21,959** |

## 2. SR1: what the cap guard refused, and why (investigation)

Method: `sr1_collect.py` re-runs solidify's planning and the cap guard line for line, with
bookkeeping. It reproduces the engine's history exactly: A 288 / 25,670 / 133 in round 0, then
155 / 3 / 1; B 284 / 9,611 / 90, then 194 / 4 / 3. Every failing pixel of the round that refused
its new face is classed by the point BEFORE saw there:

- **a (a piece of the side or bottom being closed):** within 6 in of the new face's plane and within
  30 degrees of parallel.
- **b1:** under the refused face's own top region, between the top and the region's bottom depth,
  behind the wall plane.
- **b2:** as b1, but between the bottom depth and the deepest wall.
- **b3:** inside ANOTHER top region's volume.
- **c:** anything else.

| failing pixels | A (25,673) | B (9,615) |
|---|---|---|
| a, side/bottom piece | 6,749 (26.3 %): skirts 61, bottoms 6,688 | 2,764 (28.7 %): skirts 1,446, bottoms 1,318 |
| b1, inside to bottom depth | 5,763 (22.4 %) | 2,907 (30.2 %) |
| b2, inside to deepest wall | 8,143 (31.7 %) | 1,730 (18.0 %) |
| b3, inside another slab | 3,561 (13.9 %) | 986 (10.3 %) |
| c, outside every slab | 1,457 (5.7 %): 675 under a top but outside its depth, 458 in front of the wall plane, 284 not under any top, 40 below the deepest wall | 1,228 (12.8 %): 674, 506, 36, 12 |
| covered faces a / b / c | 78 / 309 / 49 | 62 / 223 / 68 |
| front exposure of the covered face, p10-p90, a | 0.49-0.50 | 0.23-0.49 |
| same, b | 0.15-0.49 | 0.23-0.50 |
| same, c | 0.18-0.50 | 0.39-0.49 |

**Distance of class a from the new face's plane:**
- A: median 0.0, p90 1.98, p99 1.98, max 5.79 in. 3,692 pixels at 0-0.05 in and 3,035 at 1-2 in.
- B: median 0.017, p90 1.45, p99 2.35, max 5.90 in. Beyond 3 in there are only 7 (A) and 15 (B)
  pixels.
- So `FixProfile.side_band = 2.5` in, with a ceiling of `SIDE_BAND_MAX = 3.0` in.

**By refused face:** of A's 134, 89 saw only a or b (4 saw only c); of B's 93, 45 saw only a or b
(1 only c). A first pass that had not yet split b3 out of c counted 68/8 and 27/5. The covered
faces are plainly visible (exposure 0.15-0.5), which is exactly why the old rule 3 refused them.

**Worst spots** (clusters of refused faces, weighted by failing pixels):

*File A:*
1. **Region 11**, the lower landing (x 1098-1413, y 22433-22827, top z 1612.2). a 3,660 / b1 3,005 /
   c 550. Its underside is a sawtooth STRIP of bottom at exactly the measured 29.52 in, and a
   diagonal side of triangles. The old bottom met the strip in its own plane and was refused. From
   below (close-up `A_r11_below`), BEFORE is a purple triangle lattice across the top's underside;
   AFTER (the pre-SR2 output) is still purple across most of it, because the bottom was refused, and
   the purple ends in a sawtooth where the partial bottom strip begins.
2. **Region 173**, a sloped slab (x 2142-2417, y 22551-23221): b2 7,474, b3 2,114. In the pre-SR2
   output (close-up `A_r173_v0`, from above) its top is one clean face, but its front edge shows a
   row of box-like pieces with purple between them, and a purple strip runs along its east side.
3. **Region 51/576**, small landings at z 1656/1779.

*File B:*
1. **Region 92**, the upper landing (x 2082-2673, y 23850-24205, z 2015.8): b1 2,158, a 1,303,
   c 667, b3 216, b2 185. Its east side (x 2673.2, 354 in long) is a broken row of triangles,
   purple from outside.
2. **Region 596**, b2 1,532.
3. **Region 299**, a sloped slab (x 2988-3293, y 23496-23654): a 1,155.

**The owner's sawtooth is file B, region 309:** the ramp between the upper landing (region 92) and
the lower slab, x 2673-2949, y 23654-24205, z 1897.6-2015.8, at the place the controller described
(teeth with gaps under the sloped edge between the upper landing and the lower slab). Close-up
`B_ramp_teeth_v0` (view (0.581, 0.814, -0.12), from
outside) shows its diagonal side as a row of triangular teeth, with purple back sides and gaps you
see through into the ramp. That view has 43,696 back-face pixels in the input.

**SR1 conclusion:** the problem is as the brief describes. Broken sides were preserved because walls
went only on open edges and the cap guard refused to cover anything visible. SR2 proceeded.

## 3. SR2: rebuild a broken side (65e566c, f57cb17)

**Walls.** Every outline edge of a top region is considered, except where the top CONTINUES into
another top surface: a probe 0.5 in outside the edge finds a top-like face whose plane passes
through the edge. In each edge's side band (half-width `side_band`, parallel within 30 degrees):
- If the band's faces cover the side at its own depth, the side is **whole** and nothing is built.
  So an existing side is never an open edge, even behind a T-junction (file B region 38; review C1
  failure 2).
- Otherwise a wall is built from the top edge down to the edge's measured height, and the band's
  faces (mostly inside the edge's span) are **replaced**: removed with the wall's acceptance.

**Bottoms.** A bottom replaces the pieces in its band the same way.

**Cap guard.** `solidify_feedback` gains two named changes:
- Rule 4: a replaced piece's pixel showing the new face within the band.
- Rule 5: a pixel whose BEFORE hit was reached through the inside of a slab. The point judged is
  0.25 in in front of the hit (never behind the new face), inside a top region's footprint, between
  its top and its depth.

A failing pixel on a replaced piece restores the piece. A top face is never removed or covered.

**Reference mesh and reports.** The reference mesh is the input minus the replaced pieces, then the
new faces; `FixResult.replaced_input` says which. The report gains `sides_rebuilt`,
`side_pieces_replaced` (with `_by`), `side_pieces_restored`, `interior_faces_covered`,
`walls_refused` / `bottom_faces_refused` (with reasons), `sides_intact`, `edges_continued` and
`top_regions_continued`. The CLI prints them, and preview-data maps input faces through the
replaced mask.

**Tests** (fixtures appended to `build.py`): the sawtooth side is replaced by a clean outward wall
over the whole 40 x 8 in side, and the rib seen through its gaps is covered, then removed, with back
faces from outside 0; a railing 2 in outside (inside the band) and a wall 6 in outside are never
replaced or changed, even seen through an open slab; a half side gets the rest built, and a post
outside is unchanged; a side behind a T-junction gets nothing; two tops meeting at a T-junction get
no wall; the rebuild is deterministic.

**Found on real data, fixed in f57cb17.**
- *A's merge rolled back.* One `moved_same_flat` pixel in view 13. Measured cause: region 11's bottom
  was put 15.22 in down, 14.3 in above its real partial bottom. The side-band search stopped at
  measured + band + 1 (11.72 + 2.5 + 1) and reported that cutoff as the side's depth; the side face
  in that plane is 29.52 in deep. The failing pixel sat 0.004 in from the merged real bottom's
  border, so the merge's small border change exposed the invented bottom behind it.
  - Fix: the side is measured at its own depth (searched down to `max_thickness`), and only what
    HANGS from the top edge counts.
- *The lower landing runs on under the upper one* (regions 784 and 9 see no sky, so they were not
  processed as tops). Region 11's wall faces under them were refused as `covers_outside_footprint`
  (faces 4725-4729), and two of its bottom faces as `covers_below_bottom` (4720, 4722).
  - Fix: a region a top continues into is processed as a top.
- *Walls built this run measured nothing.* Only original faces measure a side, so walls this run
  built give no depth to another region's bottom.
- *Textured materials could not merge invented faces.* Every invented face's UVs are now projected
  from one origin, so a textured material can merge them (both files' materials are flat, so their
  output is unchanged).

At f57cb17: A 1,516 triangles, back faces 20,582; B 676, 7,869. B's owner view: 43,696 -> **2,274**
(`B_sr2_ramp_teeth_v0`): walls stand along most of the sloped side, with a few small gaps and purple
slivers.

## 4. SR4 = review C1, SR5 = review I1, M1

**SR4 (9562aa3).** Rule 2 is gone: a covered hit is judged by the ORIGINAL exposure of whichever side
the ray met (`compute_side_exposure`'s back half). The inner side of the shell being closed is still
covered through rule 5.
- A BOTTOM may not take a face PARALLEL to it as interior, unless it is one of its pieces or a top
  surface (the shell). This restores S-C1's verdict on `slab_with_partial_underside` in both windings
  (review failure 1): the real underside at -4 in ships.
- A new face lying ON an existing face (parallel within 1 degree, every corner within the depth
  tolerance, overlapping) that is not one of its own pieces is refused before any pixel is judged,
  as `coincides_with_existing_face`.
- Both probes are regression tests. The duplicate-skirt probe was already fixed by SR2's
  whole-side test.
- S-I4's height tests now assert the extrusion plan with the guard bypassed. Without a floor,
  `slab_with_two_depths`' 9.8 in skirts are refused below the 1.3 in bottom, and a test records
  that.

**SR5 (6233671).**
- An edge takes its height only from the slab's OWN sides: side faces with an edge lying along an
  outline edge, which covers sharing it and starting at the top through a T-junction. It takes the
  shallowest of them, at the edge's ends or along it. The deepest-at-either-endpoint rule and the
  60 in radius search are gone; `skirt_search_radius` is kept and documented as unused.
- The bottom goes no deeper than the region's shallowest existing side, closed sides included.
- `regions_deeper_than_own_sides` reports every region with a wall deeper than, or a bottom below,
  its shallowest side: 44 regions on A, 26 on B.
- The deep-corner probe is a regression test (2 in slab stays 2 in). `two_level_slab`'s fin no
  longer measures its open edge (8 in, and the skirt stays).

**M1 (0f24da4).** A `cap_guard_max_rounds=1` test: round 0 removes faces from
`slab_with_partial_underside`, `history[-1]` is round 1 with 0 failing and 0 removed, and
`cap_guard_passed` is True. Test only; the behaviour was already right.

## 5. SR3: orientation of the closed slabs

Per final face with back pixels, the final mesh's own `compute_side_exposure`, and the verdict
`classify_orientation` would give it:

| HEAD | back px | wound right (front >= back), seen through an opening | two-sided sheet | flip candidate |
|---|---|---|---|---|
| A | 21,766 on 407 faces | 14,828 (68.1 %), 353 faces | 6,927 (31.8 %), 51 faces | 11 px, 3 faces |
| B | 18,617 on 124 faces | 14,796 (79.5 %), 111 faces | 3,821 (20.5 %), 13 faces | 0 |

Thin sheets reported by the pipeline (on the reference): A 79 -> 85, B 18 -> 25. On the final mesh:
A 62, B 14. Flip candidates anywhere in the final mesh: A 5 (3 of them show back pixels, 11 px in
all), B 0. On closed slabs no face shows its back to the outside. What remains is back sides seen
through remaining openings (refused walls and bottoms), and genuinely two-sided sheets on unclosed
or free-standing parts (at f57cb17 the largest was a vertical face at (2319, 23221), front exposure
0.49 and back 0.26). `classify_orientation`'s thresholds and thin-sheet rule are not the cause, so
there is no SR3 fix (at f57cb17 the split was the same: 71.0 % / 29.0 % / 1 px on A).

## 6. Real data at HEAD 0f24da4

| | A `CHTM_SIDE_WALK_2nd_floor` | B `CHTM_2nd_to_3rd_building_sidewalk_outside` |
|---|---|---|
| triangles in -> reference -> out | 4,692 -> 5,489 -> **1,512** (baseline 902) | 7,227 -> 7,504 -> **632** (baseline 555) |
| sides_rebuilt | 119 edges, 3,377.5 in | 19 edges, 482.6 in |
| side_pieces_replaced | 56 (walls 37, bottoms 19); 16 restored | 35 (walls 35); 3 restored |
| interior_faces_covered | 1,007 | 361 |
| walls_refused | 157 faces: covers_outside_footprint 101, covers_below_bottom 27, coincides_with_existing_face 19, covers_at_or_above_top 10 | 123: outside_footprint 62, below_bottom 50, coincides 11 |
| bottom faces refused | 108: outside 80, coincides 13, above top 12, partial underside 3 | 40: outside 28, below bottom 12 |
| bottoms added / existing | 85 / 117 | 17 / 76 |
| tops continued (no sky) | 99 | 23 |
| invented vertices | 947 | 410 |
| cap guard rounds (new, failing, removed, restored) | (1086, 4447, 174, 21), (912, 252, 48, 0), (864, 7, 7, 0), (857, 2, 2, 0), (855, 2, 2, 0), (853, 0, 0, 0) | (464, 14312, 104, 44), (360, 566, 46, 0), (314, 420, 2, 0), (312, 0, 0, 0) |
| hidden removed | 2,058 (baseline 1,985) | 2,607 (baseline 2,566) |
| thin sheets | 85 (baseline 79) | 25 (baseline 18) |
| backface_px input / reference / final | 569,549 / 266,112 / **21,766** (baseline 119,610) | 465,286 / 366,067 / **18,617** (baseline 21,959) |
| guard_after_removal | passed; model_px 2,084,238, fragment_removed 36 | passed; model_px 2,426,251, fragment_removed 12 |
| guard_merge_attempt = guard_final | passed; crack_closed 2, fragment_removed 36, border_shift 113 | passed; zfight_tie 3, crack_closed 4, fragment_removed 12, border_shift 26 |
| merge | 250 regions merged, none skipped, **not rolled back** | 102 merged, 1 skipped (overlap), **not rolled back** |
| invariants | all True (material_count_same, bbox_same, area_not_grown, cap_guard_passed, guard_passed) | all True |
| passed | **True** | **True** |
| .skp | 1,046 faces written, 0 missing, 0 unexpected, `sketchup_check_changed` false | 242 faces written, 0 missing, 0 unexpected, `sketchup_check_changed` false |
| merge not rolled back: evidence | merge attempt passed; output = merged mesh (merge `tris_after` 1,512) | merge attempt passed; output = merged mesh (632) |

**Determinism:** at HEAD 0f24da4, four runs of A give a byte-identical `report.json` (sha256
4fd2bcf2...0be8d: 21:39 and 21:40 on 09-24, 00:09 and 00:21 on 09-25). Two runs of B match too
(9409ba32...f56c96: 00:09 and 00:32 on 09-25). The re-run `.skp` audits reproduce the ones
below byte for byte.

### .skp audit (`docs/superpowers/records/scripts/skp_edge_audit.py`, PYTHONPATH = worktree)

```
CHTM_SIDE_WALK_2nd_floor.fixed.skp: 1046 faces, 2408 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)      36      73.0 ft
  hidden (soft)                                                    668    3920.9 ft
  visible, non-manifold (3+ faces)                                  79     155.7 ft
  visible, open border (1 face)                                   1291    3296.8 ft
  visible, shape edge > 5 deg                                      334    1158.8 ft
    line inside a surface:    55.7 in  [1374.0, 22708.8, 1582.7] -> [1374.0, 22748.2, 1622.0]
    line inside a surface:    55.7 in  [1315.0, 22787.5, 1622.0] -> [1315.0, 22826.9, 1582.7]
    line inside a surface:    55.7 in  [1413.4, 22708.8, 1622.0] -> [1374.0, 22708.8, 1582.7]
    line inside a surface:    49.2 in  [1442.9, 22590.7, 1612.2] -> [1413.4, 22630.1, 1612.2]
    line inside a surface:    49.2 in  [1442.9, 22708.8, 1622.0] -> [1413.4, 22708.8, 1582.7]
    line inside a surface:    44.0 in  [1787.4, 22669.4, 1647.4] -> [1767.7, 22630.1, 1645.5]
  visible open edges split:
    open edge = real border of the model                                       806    2305.2 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)      107     194.6 ft
    open edge lying on an angled face (face meets a surface it does not split)   378     797.0 ft
      T-junction line:   118.1 in  [2594.5, 23063.1, 1766.4] -> [2594.5, 22945.0, 1766.4]
      T-junction line:    68.9 in  [1610.3, 22669.4, 1625.4] -> [1610.3, 22600.5, 1625.4]
      T-junction line:    68.9 in  [1610.3, 22600.5, 1625.4] -> [1610.3, 22669.4, 1625.4]
      T-junction line:    49.2 in  [1374.0, 22748.2, 1612.2] -> [1374.0, 22708.8, 1582.7]
      T-junction line:    49.2 in  [1315.0, 22826.9, 1582.7] -> [1315.0, 22787.5, 1612.2]

CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp: 242 faces, 769 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)       9      43.5 ft
  hidden (soft)                                                    115    1328.7 ft
  visible, material border (coplanar)                               12     229.3 ft
  visible, non-manifold (3+ faces)                                  32      50.4 ft
  visible, open border (1 face)                                    453    1791.3 ft
  visible, shape edge > 5 deg                                      148    1703.1 ft
    line inside a surface:   157.5 in  [2240.0, 24126.1, 2015.8] -> [2397.4, 24126.1, 2015.8]
    line inside a surface:   118.1 in  [2082.5, 24126.1, 2015.8] -> [2200.6, 24126.1, 2015.8]
    line inside a surface:    39.4 in  [2082.5, 24165.5, 2015.8] -> [2082.5, 24126.1, 2015.8]
    line inside a surface:    39.4 in  [2200.6, 24126.1, 2015.8] -> [2200.6, 24086.7, 2015.8]
    line inside a surface:    39.4 in  [2397.4, 24195.0, 2015.8] -> [2397.4, 24195.0, 1976.4]
    line inside a surface:    39.4 in  [2358.1, 24047.4, 2015.8] -> [2397.4, 24047.4, 2015.8]
  visible open edges split:
    open edge = real border of the model                                       282    1144.6 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)       24      38.8 ft
    open edge lying on an angled face (face meets a surface it does not split)   147     607.9 ft
      T-junction line:    39.7 in  [2121.8, 24204.9, 2042.2] -> [2082.5, 24204.9, 2047.4]
      T-junction line:    39.7 in  [2200.6, 24204.9, 2031.8] -> [2161.2, 24204.9, 2037.0]
      T-junction line:    39.7 in  [1885.6, 24204.9, 2073.2] -> [1846.2, 24204.9, 2078.4]
      T-junction line:    35.7 in  [2358.1, 24204.9, 2011.1] -> [2322.6, 24204.9, 2015.8]
      T-junction line:    35.7 in  [2322.6, 24195.0, 2015.8] -> [2358.1, 24195.0, 2011.1]
```

Compared with the record's audit at 8ffbda3: A had 731 faces with 21 lines inside a surface and 100
T-junction lines, and now has 1,046 faces with 36 and 107 (the new walls and bottoms add faces and
T-junctions). B went from 248 faces with 5 and 36 to 242 faces with 9 and 24. These files use this
branch's older SketchUp writer; the writer softening on feat-dashboard (8ee9e4d) is not in this
branch.

### QA images and close-ups at HEAD (read with the Read tool)

All read again on 2026-09-25 from the HEAD outputs (A's regenerated that day).

- **A `side_low_a`**: the long landing, the ramp and the lower block read as solid slabs; the
  landing's front edge is clean on the left, but its right-hand underside edge still shows a strip
  of small broken faces.
- **A `obl_top_a`**: the tops read as clean surfaces, with a few stray lines along the upper
  landing's far edge; the lower-left landing's top is a triangle fan, and **a row of teeth still
  shows along its diagonal edge**.
- **A `obl_bot_a`**: the undersides read as closed surfaces; region 11's staircase and sawtooth
  remain as lines on them, and the right-hand part carries many region borders and triangle fans.
- **B `side_low_a`**: the stepped landings read as solids, but a cluster of thin triangles hangs
  under the ramp's lower end, and the right lower slab is drawn as a triangle fan.
- **B `obl_top_a`**: the tops are clean single faces, but an opening between the upper landing and
  the ramp shows inner faces, the ramp's sloped side still shows thin teeth, and the far right slab
  is a triangle fan.
- **B `obl_bot_a`**: the far-left and far-right undersides are clean single faces; the middle slabs
  read as trays from below, with side walls hanging lower than undersides that carry broken pieces
  and lines.
- **Close-up A region 11 from below** (`A_head_r11_under_v0`): the input's large purple underside is
  closed, 201,682 -> 2,470 back pixels, with three small purple triangles left and the staircase
  as lines.
- **Close-up B region 92, east side** (`B_head_r92edge_v0`): the top is one clean face, but a purple
  band still runs the full length under the edge (42,774 -> 41,219 back pixels). Measured at HEAD:
  all 6 wall faces built there are refused as `covers_below_bottom`, under a 0.26 in bottom.
- **Close-up B ramp, the owner's photograph** (`B_head_ramp_teeth_v0`): the teeth are gone, but no
  wall stands along most of the sloped side, so a long purple band shows through it: 16,930 back
  pixels (input 43,696; f57cb17 2,274).

**Are the slab sides clean walls now?** Only in part. Where a wall was built and kept (119 edges on
A, 19 on B), it is an outward wall over the whole side, and A's region 11 underside is closed.
**Not clean at HEAD:** the owner's ramp side on B and B's region 92 east side (purple where the
walls were refused), the teeth along A's lower landing's diagonal edge, and B's middle undersides,
which read as trays.

## 7. The regression on the owner's ramp, and the fix not committed

**Measured cause at HEAD** (region 309, the ramp; B run through `solidify` with the cap guard
observed, 2026-09-25):
- The ramp's sloped side is 10 outline edges, plus a 4.3 in corner edge. The slab's own sides give
  them heights of 7.87-39.37 in (SR5).
- Along the longest, the 85.4 in edge, the broken side's pieces are only its LOWER part: the faces
  in the side's plane within the edge's span sit 28.2-39.4 in down, and nothing hangs from the top
  edge. `_wall_pieces` therefore takes no pieces there (coverage 0).
- SR5 caps the bottom at the region's shallowest existing side, **5.62 in** (report:
  `shallowest_side` 5.62, `deepest_side` 39.37, `deepest_wall` 36.0), so the slab's volume ends
  5.62 in down.
- The cap guard refuses **all 14** of the ramp's new wall faces: 11 as `covers_below_bottom`, 2 as
  `coincides_with_existing_face` (SR4's rule, on the pieces not taken), 1 as
  `covers_outside_footprint`.
- At f57cb17 walls stood along most of this side (owner view 2,274). Then rule 2 let every
  back-side cover through unmeasured, there was no coincidence rule, edge heights came from the old
  search, and there was no bottom cap. SR4 and SR5 together reopened the side; the owner view was
  not measured between them.

**The fix that works for B** (`combo_fix.patch` in the scratchpad, 116 lines, not committed):
- Every band face mostly inside the edge's span is a piece, whether or not it reaches the top.
- The wall reaches down to the deepest of its pieces, measured under the sloped edge.
- The slab's volume for rule 5 reaches down to its deepest wall or own side, since the sides
  enclose that space.

With it:
- B: owner view back pixels 16,930 -> **1,955** (4,230 and 3,078 in the two other views); wall
  refusals 123 -> 46; 57 edges rebuilt. But B's total is **not** better: 19,980 back pixels against
  18,617 at HEAD, and 679 triangles against 632.
- **File A's merge rolls back** (3,132 triangles out). The merge attempt fails on one
  `moved_same_flat` pixel in view 15 (nearly horizontal, along +y), at (1824.8, 22708.8, 1650.9).
  - BEFORE, that pixel hit an original face of region 58, a gently sloped surface (y
    22708.8-22748.2) seen edge-on, within 0.0003 in of the face's edge: a graze.
  - After the merge, the point lies in neither the source triangles nor the merged region, so the
    ray goes on to merged region 33, 48.5 in behind.
  - BEFORE's ring rays hit surfaces 29.7-57.3 in from AFTER's hit, so the ring test cannot excuse
    the pixel.
  - Why these variants expose this graze and HEAD does not was not established.
- feat-dashboard's `merge.py` (T-junction threading), swapped into a scratch copy of the combo
  engine, **does not fix it**: A's merge attempt again fails on one `moved_same_flat` pixel and
  rolls back (location not re-traced).
- The parts alone do not help:
  - No bottom cap: A rolls back on the same pixel (traced). B's owner view is 17,870, though B's
    total falls to 12,318.
  - Volume alone: A rolls back (3,141 triangles; pixel not traced). B's ramp is unchanged (16,930),
    because the pieces are still not taken.
  - Pieces alone: A rolls back (3,118 triangles; pixel not traced). B's ramp is unchanged (16,930).

Because a rolled-back merge is not an acceptable end state, HEAD stays at 0f24da4. The patch is the
measured next step once A's graze pixel is dealt with. Two options, both for the controller to
decide: a merge that reproduces region 58's border exactly, or a final-guard rule, named and
measured, for a pixel whose BEFORE hit lies within 0.001 in of its face's edge.

## 8. Concerns

1. **The owner's ramp side on file B is broken at HEAD** (section 7), and so is region 92's east
   side; A's lower landing still shows teeth along its diagonal edge. B's back pixels are 18,617
   against 21,959 at baseline; they were 7,869 at f57cb17. The uncommitted fix clears the owner's
   spot (1,955) but does not lower B's total (19,980) and rolls A's merge back.
2. **SR5's bottom cap follows the review literally** ("no deeper than the shallowest existing side,
   closed sides included"). It picks 5.62 in (region 309) or a 0.26 in lip (region 92) as a slab's
   bottom depth. Ignoring lips thinner than `min_thickness` made B worse (24,676) and rolled back A,
   so it is not committed.
3. **File A's output has more faces than before**: 1,512 triangles against 902; 1,046 .skp faces
   against 731 (517 at ce79c44); 36 lines inside flat surfaces against 21. The new walls and bottoms
   do not always merge with the coplanar remnants they meet (triangle fans on A's underside, B's
   far-right slab).
4. **99 regions on A are processed as tops because a top continues into them** (floors under
   landings). This is measured to be right for regions 784 and 9, but not inspected one by one.
5. **Thin sheets rose** (A 79 -> 85, B 18 -> 25). They are free-standing or unclosed two-sided parts;
   SR3 found no orientation cause.
6. **Not touched: the review's C2, I2, M2 and the dashboard items.** A dry `git merge-tree` of
   feat-dashboard (74adf48, which contains the review fixes 19f97cc) into HEAD auto-merges
   `engine/cli.py`, `engine/fixes/pipeline.py` and `engine/guard/compare.py`, and conflicts only in
   `engine/tests/fixtures/build.py` and `engine/tests/test_cli.py`. The merged result was not built
   or tested; the controller reconciles.

## 9. SR6 (2026-09-25): lips, sloped sides, and the grazing pixel

**Status: DONE_WITH_CONCERNS.**

Met on both files (table below):
- back pixels under both limits;
- no merge rollback, both passed;
- the three probes unchanged;
- the ramp close-up at 948 in view 0, the view tracked since SR1;
- A's lower-landing edge rebuilt.

Not met as written:
- The ramp close-up's view 1 measures 2,674, above the 2,500 target.
- B region 92's "east side" is not a side (corrections below). Its real sides are only partly
  rebuilt, and 2,927 back pixels remain in its volume.

The concerns are listed at the end of this section.

| Commit | Item |
|---|---|
| f58243d | item 2 `fix(engine): a thin lip never sets a slab's bottom` |
| 6eb6fb8 | item 1 `fix(engine): a sloped top's walls follow the ground` |
| cb85e0d | item 1 follow-up `fix(engine): a slab's lower surface is the one surface most of its rays meet` |
| 8d238c4 | item 3 `fix(engine): the grazing pixel is no border shift; its causes are fixed at the source` |

**Commit order.** Item 2 was committed before item 1 because item 1 depends on it. Item 1 searches
for a slab's lower surface from item 2's representative depth. From the lip-driven depth SR5 gave,
the search stops 24 in below 5.62 in and never reaches the ramp's underside at 39.37 in.

**Suite:** `427 passed in 65.48s (0:01:05)` at HEAD 8d238c4, with only this report uncommitted
(`python -m pytest engine/tests -q -p no:cacheprovider`; 415 at 0f24da4).

### Item 2: a thin lip never sets a slab's bottom

**Measured.** SR5 capped the bottom at the shallowest own side, measured by its vertical extent:
- **B, region 309 (the ramp):** a 5.62 in lip, face 7105, running 13.1 in along the outline.
- **B, region 92 (the landing):** a 0.26 in lip, face 692, running 29.5 in. It lies on the edge at
  y 24195.0 (x 2247.8-2279.3), not on the east side where the brief places it.
- **A, region 11 (the lower landing):** 9.85 in, from faces standing UP from its top (the risers of
  the steps). All 15 of its own faces shallower than 29.52 in reach 0.0 in below their edges and
  stand 9.85 in tall.

Measured below the edge each own side lies along (risers reach 0), and weighted by the length it
runs along that edge:

| region | own-side length reaching below | representative (length-weighted lower median) | SR5's cap |
|---|---|---|---|
| B 309 | 804.1 in, 24 own faces, 5.62 to 39.37 in deep | 33.74 in | 5.62 in |
| B 92 | 1,452.3 in; 28 of its 73 own faces reach nothing below their edge | 39.37 in | 0.26 in |
| A 11 | 1,152.9 in, all of it 29.52 in deep; 15 of its 44 own faces reach nothing below | 29.52 in | 9.85 in |

SR5's cap was shallower than the representative depth in 56 of the 202 regions measured on A, and
38 of the 93 on B.

**Rule:**
- An own side is measured by how far it reaches below its edge.
- The representative depth is the length-weighted lower median: the shallowest depth down to which
  at least half of the own side length goes. A tie goes to the shallower depth, so
  `slab_with_two_depths` (half 1.3 in, half 9.8 in) keeps S-I5's 1.3 in bottom.
- The bottom goes no deeper than the representative depth.
- An own side shallower than it measures no edge's height and is not a whole side. The side below it
  is completed.
- Review I1's protection is unchanged, because only own sides count: `probe_deep_corner` prints the
  same as at 0f24da4 (2.0 in).

**Tests:** a lip never sets the bottom; a riser is not a side.

**SR5's test changed with the rule.**
- Old test: `test_the_bottom_is_no_deeper_than_the_shallowest_existing_side`. The 4 in side capped
  an 8 in slab's bottom at 4 in.
- New test: `test_a_side_shallower_than_the_slabs_representative_depth_is_completed`. The 4 in side
  is completed to 8 in and the bottom goes at 8 in. It checks the plan, with the guard bypassed.
- The requirement changed (SR6 item 2), so the test was rewritten, not weakened.

### Item 1: a sloped top's walls follow the ground

**Measured.** The ramp is a sloped slab 39.37 in thick.
- All 49 centroid rays from its top meet a surface below, median depth 39.369 in.
- 42 of those rays meet region 314, its underside. Region 314 is parallel to the top: normal z
  -0.92 against the top's +0.92.
- On the 85.4 in edge, the broken side's pieces sit 28.2-39.4 in down, just above the underside,
  and nothing hangs from the top edge (section 7).
- At 0f24da4 no piece was taken on that edge (coverage 0), and the bottom was capped at the 5.62 in
  lip. The cap guard refused all 14 new wall faces.

**Rule.** A slab has a LOWER SURFACE when rays straight down from its top meet one:
- within reach of its representative depth (+ `bottom_search_extra`);
- no deeper than its own sides go, + `side_band`. A floor under a thin slab is the ground, not its
  underside (review I1). With that check removed, the floor test fails: 4 walls go down to the
  floor instead of 0.

Then:
- Every wall under the slab's outline goes down to that surface at EACH end: a trapezoid over a flat
  underside, a parallelogram over a parallel one.
- The side is judged whole over that trapezoid.
- Any band face mostly inside the wall is a piece, whether or not it reaches the top.
- No bottom is invented, and the slab volume the cap guard reads follows the surface's plane.

On the real files:

| | regions with a lower surface | walls built down to it | of them trapezoids |
|---|---|---|---|
| A | 101 | 73 | 16 |
| B | 64 | 30 | 6 |

**Follow-up (cb85e0d).** The first version fitted a plane to every point the rays met.
- On the ramp, 41 of the 196 rays first meet another face above the underside: faces of other
  regions inside the slab.
- At the wall ends, some of those faces face up only 0.4 to 0.6 in above the underside (regions
  833, 846 and 851, at 38.97 and 38.79 in).
- The fit came out tilted:
  - wall ends measured 34.8 to 37.2 in;
  - the broken side's walls were refused as below the slab's bottom;
  - the intact side at y 24204.9 was judged broken and got new walls in place of its pieces.

The lower surface is now the one face region most of the rays meet, if it takes at least half of
them: region 314 takes 154 of 196. Its plane is fitted to the points met on it alone, and every end
of the ramp's walls now measures 39.37 in.

**Tests:** low pieces are replaced down to the underside; a trapezoid over a flat underside; a floor
under a thin slab is not its lower surface; an inner block face does not tilt the lower surface.

### Item 3: the grazing pixel

With items 1 and 2, file A's merge was rolled back on two pixels (3,168 triangles out). Both were
measured exactly as the border-shift rule measures: distance from BEFORE's hit point to every AFTER
triangle, against the 0.15 in tolerance.

| | view 2, pixel (202, 178) | view 15, pixel (315, 436), on the combo patch's face and edge |
|---|---|---|
| base class | hole | moved_same_flat |
| centre measured | 0.0001 in | 0.0049 in |
| AFTER ring rays on BEFORE's surface | 16 of 16 | 10 of 16 |
| BEFORE ring rays on AFTER's centre | 0 | 0 |
| ring rays that changed, measured | none | 6: 0.44, 0.72, 1.99, 1.99, 1.99, 1.99 in |
| verdict | a crack the merge opened: a sub-tolerance border movement | NOT a border shift: surface up to 2 in away is gone |

**The two numbers for the view 15 pixel.**
- The brief's 0.0003 in (section 7) is the pixel's distance to the edge of its own BEFORE face.
- 0.0049 in is the border-shift measure: the distance to AFTER's surface.
- Section 7's "region 58" is the merge's region number. In the solidify topology, the pixel's face
  (1071) and faces 1078 and 1079 are all in region 57.

**View 2, a classification gap.** The border-shift measurement looked only at edge-flicker pixels.
The flicker test needs a BEFORE ring ray to reproduce AFTER's centre, which is impossible through a
crack BEFORE never had.

`_classify` now measures such an opened crack itself: AFTER's ray went further or missed, and AFTER's
ring still meets BEFORE's surface. It also measures every ring ray around the pixel whose verdict
changed, each within the same tolerance. No new tolerance is added.

Tests:
- A 0.02 in crack the merge opened (the crack test's mirror image) is a border shift, 25 px.
- A lost triangle still fails.
- The existing "2 in strip lost beside a new edge" test still fails, as it should.

**View 15, a real change, fixed at the source.**
- Six ring rays met faces 1078 and 1079 in BEFORE. The hidden pass had deleted both faces in that
  run.
- Both faces are in region 57, which is no top but a slab's underside:
  - none of its 160 faces sees sky;
  - rays up meet the slab's tops, a median 9.83 in above;
  - rays down meet nothing.
- SR2's continuation had taken region 57 for a top running on, and built its bottom 2 in below it.
  Rays up from under faces 1078 and 1079 meet that bottom (face 5337) 2 in below them.
- The cap guard kept that bottom. With it in place, the hidden pass deleted the real underside's
  faces above it.
- 64 continued regions of A and 5 of B are such undersides: every own side stands up from the
  outline, and rays down from every one of them meet nothing.
- They are no longer processed, and a top's edge that ran only into one is a side. The continuation
  still passes through them, so regions 9 and 784 (tops under A's upper landing, with hanging
  sides) are still processed, their bottoms at 29.52 in.
- Tests: the underside is not taken for a top; an edge that ran only into an underside is walled.

**Two more causes, found through their back faces, each measured and tested.**
- *A point ON a slab's top or bottom plane was judged outside it.* The error was the precision of
  the ray hit on quantized coordinates:
  - A's lower-landing bottom: all 4,395 such points at 3.05e-6 in below it.
  - B: 3 points within 0.001 in of a plane, 3.4e-4 to 7.9e-4 in out. One of them, on the ramp
    (region 309), was judged at or above its top.

  Within `EPS_IN` (0.02 in, the engine's own "just off a surface" constant) of either plane, a point
  is now inside.
- *One refused face of a bottom gave back every piece of that bottom.*
  - A's lower landing: one of its 33 bottom faces lies over faces of regions 800 and 810 that
    straddle its diagonal side. It is rightly refused as coincident.
  - Under the group rule, the bottom's pieces (the real partial bottom) then came back. 16 more
    bottom faces were refused as `covers_a_partial_underside`, and only 16 were kept.
  - The landing's 80 in cell at x 1200, y 22560 then showed 7,926 back pixels (90 at 0f24da4).

  A bottom's piece now comes back only when a face over it is refused (`piece_cover`). Walls keep
  the group rule.
  - The lower landing's bottom keeps 31 of its 33 faces, at its real 29.52 in.
  - The landing's volume shows 2,245 back pixels (7,631 at 0f24da4).
  - Test: one forced refusal far from the strip leaves the strip replaced.

### Acceptance, at HEAD 8d238c4

| | A `CHTM_SIDE_WALK_2nd_floor` | B `CHTM_2nd_to_3rd_building_sidewalk_outside` |
|---|---|---|
| backface_px final (limit) | **20,793** (21,766) | **6,006** (18,617) |
| ramp close-up back px, view 0 (target about 2,500) | - | **948** (input 43,696; f57cb17 2,274; 0f24da4 16,930); views 1 and 2: 2,674 and 590 |
| merge rolled back | **no** (147 regions merged) | **no** (71 merged, 1 skipped for overlap) |
| passed | **True** | **True** |
| triangles in -> reference -> out | 4,692 -> 4,933 -> **876** (0f24da4 1,512; baseline 902) | 7,227 -> 7,443 -> **486** (0f24da4 632; baseline 555) |
| probes (`probe_deep_corner`, `probe_reversed_underside`, `probe_duplicate_skirt`) | output identical to HEAD 0f24da4, all three | |

**The acceptance spots, over the 26 full-model guard views (no crop box):**
- **B, the ramp's volume:** 6,202 back pixels at 0f24da4 -> **2**.
- **B, region 92's volume:** 11,080 -> **2,927**.
- **A, the lower landing's volume (region 11):** 7,631 -> **2,245**.

### Real data at HEAD 8d238c4

| | A | B |
|---|---|---|
| sides_rebuilt | 92 edges, 2,672.6 in | 35 edges, 1,179.7 in |
| side_pieces_replaced | 105 (walls 49, bottoms 56); 7 restored | 45 (walls 45); 14 restored |
| interior_faces_covered | 598 | 442 |
| walls_refused | 392: covers_outside_footprint 355, covers_below_bottom 32, coincides 5 | 90: outside 56, below bottom 28, coincides 6 |
| bottom faces refused | 230: outside 222, partial underside 7, coincides 1 | 61: outside 40, partial underside 19, below bottom 2 |
| bottoms added / existing | 21 / 117 (0f24da4 85 / 117) | 11 / 77 (17 / 76) |
| undersides_not_tops | 64 (of 99 continued) | 5 (of 23) |
| invented vertices | 589 (947) | 268 (410) |
| cap guard rounds (new, failing, removed, restored) | (962, 23668, 569, 10), (393, 1705, 44, 1), (349, 6, 3, 0), (346, 0, 0, 0) | (406, 14699, 116, 29), (290, 2798, 27, 1), (263, 234, 2, 0), (261, 0, 0, 0) |
| hidden removed | 2,063 (2,058) | 2,734 (2,607) |
| thin sheets | 65 (85) | 3 (25) |
| backface_px input / reference / final | 568,683 / 454,537 / **20,793** | 464,939 / 373,002 / **6,006** |
| guard_after_removal | passed; model_px 2,065,994, fragment_removed 49 | passed; model_px 2,432,650, zfight_tie 38, fragment_removed 12 |
| guard_merge_attempt = guard_final | passed; crack_closed 2, fragment_removed 49, border_shift 81 | passed; zfight_tie 39, crack_closed 2, fragment_removed 12, border_shift 33 |
| invariants | all True | all True |
| .skp | 527 faces, 1,281 edges, 0 missing, 0 unexpected | 184 faces, 567 edges, 0 missing, 0 unexpected |

**Determinism:** two runs of A give a byte-identical `report.json`, sha256 8003b028...9221613c. B's
is be840a62...ed08cfb5.

### .skp audit (`docs/superpowers/records/scripts/skp_edge_audit.py`, PYTHONPATH = worktree)

```
CHTM_SIDE_WALK_2nd_floor.fixed.skp: 527 faces, 1281 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)      30      73.6 ft
  hidden (soft)                                                    289    2474.4 ft
  visible, non-manifold (3+ faces)                                  40      88.1 ft
  visible, open border (1 face)                                    676    1433.7 ft
  visible, shape edge > 5 deg                                      246    1153.6 ft
    line inside a surface:   124.5 in  [1275.6, 22826.9, 1582.7] -> [1275.6, 22708.8, 1622.0]
    line inside a surface:    55.7 in  [1374.0, 22708.8, 1582.7] -> [1374.0, 22748.2, 1622.0]
    line inside a surface:    55.7 in  [1315.0, 22787.5, 1622.0] -> [1315.0, 22826.9, 1582.7]
    line inside a surface:    55.7 in  [1413.4, 22708.8, 1622.0] -> [1374.0, 22708.8, 1582.7]
    line inside a surface:    49.2 in  [1442.9, 22590.7, 1612.2] -> [1413.4, 22630.1, 1612.2]
    line inside a surface:    49.2 in  [1442.9, 22708.8, 1622.0] -> [1413.4, 22708.8, 1582.7]
  visible open edges split:
    open edge = real border of the model                                       328     717.5 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)       68     133.3 ft
    open edge lying on an angled face (face meets a surface it does not split)   280     582.9 ft
      T-junction line:   121.7 in  [1275.6, 22708.8, 1612.2] -> [1275.6, 22826.9, 1582.7]
      T-junction line:    49.2 in  [1374.0, 22748.2, 1612.2] -> [1374.0, 22708.8, 1582.7]
      T-junction line:    49.2 in  [1315.0, 22826.9, 1582.7] -> [1315.0, 22787.5, 1612.2]
      T-junction line:    49.2 in  [1374.0, 22630.1, 1612.2] -> [1334.7, 22630.1, 1582.7]
      T-junction line:    44.3 in  [2673.2, 23358.4, 1777.5] -> [2633.9, 23338.7, 1772.2]

CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp: 184 faces, 567 edges
  hidden (soft)                                                    112    1481.8 ft
  visible, material border (coplanar)                               13     227.7 ft
  visible, non-manifold (3+ faces)                                  16      41.2 ft
  visible, open border (1 face)                                    289     936.3 ft
  visible, shape edge > 5 deg                                      137    1730.5 ft
  visible open edges split:
    open edge = real border of the model                                       133     421.3 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)       33      54.0 ft
    open edge lying on an angled face (face meets a surface it does not split)   123     461.0 ft
      T-junction line:    39.7 in  [2121.8, 24204.9, 2042.2] -> [2082.5, 24204.9, 2047.4]
      T-junction line:    39.7 in  [2200.6, 24204.9, 2031.8] -> [2161.2, 24204.9, 2037.0]
      T-junction line:    39.7 in  [2397.4, 24195.0, 2005.9] -> [2358.1, 24195.0, 2011.1]
      T-junction line:    39.7 in  [2358.1, 24195.0, 2005.1] -> [2397.4, 24195.0, 2000.0]
      T-junction line:    39.7 in  [2043.1, 24012.9, 2055.1] -> [2082.5, 24012.9, 2049.9]
```

**Against 0f24da4:**
- A: 1,046 -> 527 faces; 36 -> 30 lines inside flat surfaces; 107 -> 68 T-junction lines; 79 -> 40
  non-manifold edges.
- B: 242 -> 184 faces; 9 -> 0 lines inside flat surfaces; 24 -> 33 T-junction lines; 32 -> 16
  non-manifold edges.

### QA images and close-ups at HEAD 8d238c4 (read)

- **A `obl_top_a`:**
  - The staircase line that the baseline drew across the lower landing's top is gone (zoomed crop,
    baseline beside SR6).
  - A triangle fan now spans that top from its corner, and a few short line fragments lie along its
    diagonal edge. The diagonal side stands as a wall.
  - The upper landing's top carries short line fragments and small outlines along its far edge.
- **A `obl_bot_a`:** no holes show in the undersides. Region 11's step lines remain; the far landing
  carries region borders and fans.
- **A `side_low_a`:** the slabs read solid. A strip of thin triangles remains under the far landing's
  right edge.
- **B `obl_top_a`:** the tops read as single faces, except the far right slab: a triangle fan with a
  cluster of thin triangles at its corner nearest the middle slabs.
- **B `obl_bot_a`:** the far undersides are clean single faces. The middle slabs still read as trays
  from below.
- **B `side_low_a`:** the landings read as solids. Thin triangles still hang under the far right
  slab's left end, and a few slivers under the upper landing.
- **Close-up of the owner's ramp** (`B_sr6_ramp_teeth_v0`, input beside 8d238c4): one continuous
  wall along the whole sloped side, no teeth and no gaps.
  - 948 back pixels.
  - What is left: one purple strip at the far left, at the landing end. I did not check its cause.
- **Close-up A region 11 from below** (`A_sr6_r11_under`): 201,682 -> 2,745, and 148,958 -> 24,389.
- **Close-up A diagonal side** (`A_sr6_diag`): 47,150 -> 51, and 13,331 -> 2,508.
- **Close-up A region 173** (`A_sr6_r173`): 91,506 -> 7,002.

**Are the slab sides clean walls now?** On the ramp and A's lower landing, yes, measured above.
**Where not:**
- B region 92, walls: its 7 walls along x 2121-2397, y 24013-24126, where the stairs rise from it,
  are all refused as `covers_outside_footprint`. On its south edge by the ramp, 3 of the 4 wall faces
  are refused as `covers_below_bottom`.
- B region 92, bottom: it sits at 36 in, with 32 of its 49 faces kept. Its walls and bottom are
  clamped to 36 in (`max_thickness`), while its representative depth is 39.37 in.
- 2,927 back pixels remain in its volume.

### Corrections to sections 1-8

- **Region 92's "east side" (sections 2, 6 and 8) is not a side.** Its edge at x 2673.2 is where
  the landing runs on into the ramp's top, at the same height (z 2015.75). The purple band under it
  in `B_head_r92edge_v0` came from the close-up's crop box: rays start at the box face, which cuts
  through the ramp's slab, so the render shows its inside.
  - The same close-up, re-rendered at 8d238c4 (42,774 -> 43,879), and a wider box
    (34,584 -> 35,229, which cuts region 310 instead) measure the cut, not the model.
  - The measurement that stands is the 26-view one above: 11,080 -> 2,927.
  - Crop-box close-ups show a slab's inside wherever the box cuts it; read with that in mind.
- **Section 8 concern 4 was wrong for 64 of those 99 regions.** It said "99 regions on A are
  processed as tops because a top continues into them", and measured them right only for regions
  784 and 9. The 64 are undersides (item 3).
- **Section 7's "region 58"** is the merge's region number for the grazing pixel's surface. In the
  solidify topology that surface is region 57 (item 3).
- **The SIDE_BAND_MAX comment in `solidify.py` said 10 pixels beyond 3 in on file A.** The measured
  figure is 7; the comment is corrected (f58243d).

### What got worse, measured

Against 0f24da4. I did not break these down by cause.

- **Reference back pixels** (the solidified mesh, before removal and merge):
  - A: 266,112 -> 454,537. The 64 undersides no longer get a bottom, which I expect is most of this
    rise; I did not measure that. A's final count is lower (21,766 -> 20,793).
  - B: 366,067 -> 373,002.
- **Refusals on A:**
  - wall faces 157 -> 392, 355 of them as covering outside the footprint;
  - bottom faces 108 -> 230, 222 of them outside.
- **Refused bottom faces on B:** 40 -> 61.
- **Z-fight ties on B:** 3 -> 39 pixels in the final guard. They are tolerated and the guard
  passes.
- **Restored pieces on B:** 3 -> 14.
- **B's .skp:**
  - T-junction lines: 24 (38.8 ft) -> 33 (54.0 ft);
  - material-border edges: 12 -> 13 (229.3 ft -> 227.7 ft).

### Concerns

1. **The underside test misses some undersides.**
   - The test needs every own side to stand up. Some continued regions of A have nothing below them
     but a little own side hanging, so they are still processed:
     - region 467: 2,353.9 in of own side rising, 44.3 in hanging;
     - region 166: 1,129.4 in rising, 10.1 in hanging;
     - region 244: 805.2 in rising, 9.1 in hanging.
   - They look like undersides with a neighbour's side hanging from a shared edge. I have not
     checked that.
   - Region 467's bottom is mostly refused: 98 of its 121 faces (97 as outside the footprint), 23
     kept. Back pixels remain there.
   - I added no ratio threshold. On A's 13 continued regions with some hanging side and nothing
     below, rising-to-hanging length ratios are:
     - 2.6 to 4.2 for seven of them, among them the real tops 9 and 784;
     - 18.7 to 111.8 for six (502, 33, 467, 709, 244, 166).
   - I have not checked which of those six are undersides. Region 33 (ratio 22.9) is 29.52 in
     thick, like 9 and 784.
2. **`max_thickness` (36 in) is below these files' 39.37 in blocks** (LittleTiles, 1 m).
   - Region 92's walls and bottom stop at 36 in, 3.37 in above its sides' bottoms.
   - Walls down to a measured lower surface are clamped only to the search reach; walls from own
     sides are clamped to 36 in.
3. **The cap guard judges each new face against a mesh that lacks the other new faces.**
   - Where a wall and a bottom are both needed, each covers what shows through the other's opening,
     and both are refused.
   - `slab_beside_a_lower_top` shows it. With the guard on, its 2 wall faces and 2 bottom faces are
     all refused as `covers_outside_footprint`, and no new face is kept.
   - The test asserts the plan, with the guard bypassed.
4. **The item 3 commit (8d238c4) holds four fixes**: crack measurement, undersides, plane precision
   and bottom piece cover. The brief asked for one commit per item. The commit message and this
   section separate them.
5. **Reconciling with feat-dashboard.** This round touches `_classify` (a new block after the border
   step, which feat-dashboard also rewrote) and `solidify_feedback` (`piece_cover`) in
   `engine/guard/compare.py`. Expect conflicts there, besides `build.py` and `test_cli.py`.

## Public signatures

Only what changed this round.

```
engine/fixes/orient.py
face_unit_normals(positions_c, faces) -> np.ndarray                                  # NEW (SR0)
backface_counts(rendered, normals) -> list[int]                                      # NEW (SR0)
backface_pixels(positions_c, faces, face_ids, views, size, caster_factory=EmbreeCaster)
    -> list[int]                                                                     # NEW (SR0)
one_sided_holes(...) -> int          # unchanged signature; now sum(backface_pixels(...))
```

```
engine/fixes/pipeline.py
@dataclass
class FixProfile:
    side_band: float = 2.5           # NEW (SR2), capped at solidify.SIDE_BAND_MAX
    skirt_search_radius: float = 60.0   # kept, UNUSED since SR5

@dataclass
class FixResult:
    backface_px: dict                # NEW (SR0) {"input"|"reference"|"final": {"total", "per_view"}}
    replaced_input: np.ndarray       # NEW (SR2) bool over INPUT faces: pieces solidify replaced
    # reference_mesh = input minus replaced_input, in order, then solidify's new faces

fix_object(mesh, flatness, profile=FixProfile()) -> FixResult    # signature unchanged
```

```
engine/fixes/solidify.py
SIDE_WHOLE_FRACTION = 0.99; PIECE_MAX_ANGLE_DEG = 30.0; SIDE_BAND_MAX = 3.0      # NEW (SR2)
_COINCIDENT_ANGLE_DEG = 1.0                                                          # NEW (SR4)

@dataclass
class SolidifyResult:
    mesh: MeshData
    new_faces: np.ndarray
    report: dict
    replaced: np.ndarray             # NEW: bool over INPUT faces

solidify(mesh, topo, profile) -> SolidifyResult   # signature unchanged; report gains:
    # sides_rebuilt {edges, length}, side_pieces_replaced, side_pieces_replaced_by
    # {walls, bottoms}, side_pieces_restored, interior_faces_covered,
    # walls_refused {faces, reasons}, bottom_faces_refused {faces, reasons}, sides_intact,
    # edges_continued, top_regions_continued, open_outline_edges, side_band,
    # regions_deeper_than_own_sides [{region, shallowest_side, deepest_side, deepest_wall,
    # bottom}]; skirts_added now counts every wall BUILT (missing or broken side)

_own_side_rows(topo, rings, sides, tol) -> (set[int], dict[(a, b), list[int]])       # NEW (SR5)
_edge_thickness(topo, edges, own, along, side_low, vertex_sides) -> list[float | None]  # CHANGED
_wall_pieces(faces, pa, pb, q, h_measured, h_wall, band, claimed, built=None,
             max_depth=0.0) -> (pieces, coverage, measured_depth | None)            # NEW
_bottom_pieces(faces, foot, normal, origin, bottom_h, band, claimed) -> list[int]    # NEW
_continues(topo, ok_ids, caster, normals, edges, top_min_nz, tol)
    -> (np.ndarray, list[set])                                                       # NEW
_underside(topo, members, caster, h, tol, fraction, search_extra=24.0) -> (bool, float)  # NEW
_interior_test(volumes, new_group, group_region, centre)   # NEW; returns the rule-5 test callable
_coincident_new_faces(solid, new_faces, new_group, replaced_group, ok_input, tol)
    -> np.ndarray                                                                    # NEW (SR4)
_cap_guard(original, solid, new_faces, guard_size, n_dirs=128, cover_max_exposure=0.10,
           max_rounds=8, *, replaced_group=None, new_group=None, side_band=0.0, volumes=None,
           group_region=None, parallel_interior_ok=None, shell_faces=None, refused_before=None)
    -> (mesh, new_faces, history, removed, detail, keep)                             # CHANGED
_newly_hidden(original, solid, topo, profile, replaced) -> (int, int)                # CHANGED
```

```
engine/guard/compare.py
INTERIOR_INSIDE = 0; INTERIOR_OUTSIDE_FOOTPRINT = 1; INTERIOR_BELOW_BOTTOM = 2
INTERIOR_AT_OR_ABOVE_TOP = 3; INTERIOR_UNMEASURED = 4; INTERIOR_UNDERSIDE = 5       # NEW

solidify_feedback(positions_c, faces_before, faces_after, is_new, front_exposure_before,
                  cover_max_exposure=0.10, views=VIEWS_26, size=(900, 600),
                  caster_factory=EmbreeCaster, max_rounds=8, *, replaced_group=None,
                  new_group=None, side_band=0.0, interior=None, interior_step=0.25,
                  back_exposure_before=None, parallel_interior_ok=None, shell_faces=None,
                  refused_before=None)
    -> (keep, history, detail)       # CHANGED: returns 3; keep also False for replaced originals
    # history rounds gain pieces_restored, replaced_px, interior_px
    # detail = {"replaced", "interior_faces", "refused_reason"}
```

```
engine/cli.py
report.json: + "backface_px"; profile + "side_band"
stdout: + "backface_px final=... (input=..., reference=...)" and a "sides rebuilt: ..." line
preview-data stats: + "side_pieces_replaced"; the BEFORE pane marks replaced pieces as removed
```

**SR6 (f58243d, 6eb6fb8, cb85e0d, 8d238c4).** One public signature changed: `solidify_feedback`
gained the keyword `piece_cover`. The solidify report gained three keys:

```
engine/fixes/solidify.py
solidify(mesh, topo, profile) -> SolidifyResult   # signature unchanged; report gains:
    # representative_side_per_region {region: depth | None},
    # walls_to_lower_surface {regions, walls, trapezoids}, undersides_not_tops;
    # regions_deeper_than_own_sides entries gain representative_side

_own_side_depths(topo, along, sides, tol)
    -> (dict[int, float], list[(depth, run)])                                        # NEW (item 2)
_representative_depth(runs) -> float | None                                         # NEW (item 2)
_edge_thickness(topo, edges, own, along, side_low, vertex_sides, row_depth=None,
                lip_below=None) -> list[float | None]                               # CHANGED (item 2)
_wall_pieces(faces, pa, pb, q, h_measured, h_wall, band, claimed, built=None,
             max_depth=0.0, min_side=0.0, h_ends=None)
    -> (pieces, coverage, measured_depth | None)                                    # CHANGED (items 1, 2)
_lower_surface(topo, members, caster, ok_ids, normals, reach, fraction, deepest_own,
               band, top_min_nz, top_normal, top_origin)
    -> (plane coef, depth) | None                                                   # NEW (item 1)
_bottom_piece_cover(solid, new_group, replaced_group, group_kind)
    -> dict[int, np.ndarray]                                                        # NEW (item 3)
_cap_guard(..., refused_before=None, piece_cover=None)                              # CHANGED (item 3)
_interior_test(volumes, new_group, group_region, centre)   # signature unchanged; a volume is now
    # (foot, normal, origin, depth, lower-surface plane | None), and a point within EPS_IN of the
    # top or bottom plane is inside
```

```
engine/guard/compare.py
solidify_feedback(..., refused_before=None, piece_cover=None)                       # CHANGED (item 3)
    # piece_cover {piece: the new faces over it}: a bottom's piece comes back only when one
    # of those faces is refused; pieces not in it keep the group rule
_classify(...)   # signature unchanged; an opened hairline crack is measured as a border shift
```

```
engine/tests/fixtures/build.py (appended at the end)
slab_with_a_lip(size=40.0, deep=12.0, lip=2.0, lip_length=8.0, with_lip=True, riser=0.0,
                riser_length=10.0)
sloped_slab(length=80.0, width=40.0, rise=20.0, thickness=12.0, flat_underside=False,
            side="missing", strip=(8.0, 12.0), inner_plate=None)
slab_beside_a_lower_top(size=40.0, box_height=10.0, plate_depth=8.0)
slab_with_a_bottom_strip(length=60.0, width=20.0, depth=8.0, strip=20.0)
```
