# Review 2a fixes report (brief 08)

Date: 2026-09-25. Branch `feat-dashboard`, main checkout. Base 670ad50, engine HEAD d570927.
Source: `review-hermes-fixes.md` (review 2a: 1 Critical, 1 Important, 11 Minor) and brief
`docs/superpowers/records/briefs/08-review2a-fixes.md`.

**Status: DONE_WITH_CONCERNS.** All twelve items are committed test-first. Both real runs pass,
and the owner's two `.skp` files were rewritten (A 05:47, B 05:49). Two slivers the new rule still
removes (file A, faces 3540 and 4659) open sub-pixel slots onto surfaces the reference never showed.
Details are in Concerns.

**Suite: `462 passed in 119.01s`** at d570927 (baseline 431 at 670ad50).

## Commits, in order

| # | Commit | Item |
|---|---|---|
| 1 | 536fca7 | C1: a sliver is debris only when one of its long edges is an open border; width bound derived |
| 2 | 74adf48 | faces solidify invented are never fragment or sliver candidates |
| 3 | 2f0692e | I1: the fragment join through T-junctions is pinned |
| 4 | 8515461 | M2: the bbox invariant allows the merge's own border movement |
| 5 | e33ccce | Minor 1: guard images and preview know the new pixel classes |
| 6 | 4f0ae03 | Minors 3, 6: the border shift is a clearance; the QA sheet over-draws SketchUp |
| 7 | 4571a91 | Minor 5: the ON_FACE_TOL sweep restated on the current output |
| 8 | 938dc66 | Minor 7: a failed QA sheet or `.skp` is recorded and leaves nothing stale |
| 9 | fdc66e3 | Minor 8: a failed run says the previous `.skp` was kept; a passing one clears a stale FAILED copy |
| 10 | 2242b9e | Minor 9: `fragment_removed_cap` sized from the real files |
| 11 | c78bd77 | Minor 4: every guard report says what its grown pixels became |
| 12 | d570927 | Minor 11: what `_PAIR_BLOCK` bounds, and the measured peak memory |

Also on the branch between items 2 and 3, from another session: 0534b8b (docs, SR6 claim). Every
commit above left the suite green (444, 447, 449, 450, 455, 455, 455, 457, 460, 462, 462, 462).
4571a91, a comment-only change, was run on an archived copy of its own tree (engine and preview):
`455 passed in 113.44s`. Every other count was run on exactly the committed content.

## Items

### 1. C1: sandwiched slivers (536fca7)

**Rule.** A thin face (quality < 0.02, area ≤ 4 sq in, width ≤ the bound) is a sliver only when
one of its LONG edges is an OPEN border. A long edge is one whose opposite corner lies within the
bound of it. Open means three things: no other face uses the edge, no other face's vertex lies
inside it, and it lies inside no other face's edge. All three are within `contact_tol`, the
T-junction tolerance.

A partner within that tolerance belongs to the edge of the thin face it lies nearest. A face
thinner than the tolerance has all three edges within it of each other, so without this every
partner would count for every edge. Thin faces with no open long edge are kept and counted as
`n_sandwiched_thin_faces`.

**Width bound.** It is no longer the constant 0.15. `sliver_width_bound(quanta, profile)` is
`min(default_collinear_tol(quanta), depth_tol_max)`, the same derivation as the final guard's
border-shift tolerance: 0.15 in on the real files, 1.5e-4 in at the fixtures' own print step. The
`FixProfile.sliver_max_width` field is removed; `fragment_report` records `sliver_max_width` and
`contact_tol`.

**Tests.** Tests that need `slab_with_strays`' 0.02 in needle named now give the fixture the real
files' print step through a new fixture helper, `printed()`. `test_fragments.py`'s old
"narrow strip is a sliver" assertion now asserts the opposite: a sandwiched strip 0.05, 0.1 or
0.14 in wide is NOT a sliver. New tests cover:
- T-joined bases (a vertex inside the base, or the base inside a longer edge);
- a needle whose only open edge is its short end;
- nearest-edge attribution;
- the derived bound;
- E2b's real-scale case: the detector alone, and `fix_object` at 2000 in with rays down the strip.

**Mutations.** Each part of the rule fails a test when disabled:

| Part disabled | Tests failing |
|---|---|
| Whole rule | 11 |
| Vertex partner | 1 |
| Edge partner | 1 |
| Long-edge definition | 1 |
| Nearest-edge attribution | 1 |

**E2b** (`e2b_interior_strip_large.py`):

| Strip width | 670ad50 | After |
|---|---|---|
| 0.05, 0.10, 0.14 in | removed, `passed` True, **97/97** rays down the strip hit z = -8 | not a sliver, not removed, `passed` True, **0/97** |

The "After" run is at 536fca7 (2 min 16 s). The same result at d570927 is under Experiments at
HEAD.

### 2. Invented faces are never candidates (74adf48)

`detect_fragments(..., protected=)`. `fix_object` passes solidify's `new_faces`.
- A protected face is never a sliver.
- A component holding one is never a fragment: taking only its original faces would leave
  invented ones hanging.
- Protected faces still join components, and still count as neighbours in the open-border test.
- The report counts `n_protected_components` and `n_protected_faces`.

Test: `fix_object` with solidify made to invent a detached 2 sq in triangle. The same triangle is
removed as a stray when the EXPORT carries it, and ships when solidify invented it.

Real file A: face 4721, the bottom triangle under face 174, is now kept. A's `fragment_report`
shows `n_protected_components` 1 and `n_protected_faces` 58. It is not a coincident duplicate: it
lies 9.84 in below face 174. Face 174 itself is a double layer on 173/175 (see the verdicts
below).

### 3. I1: the T-junction join pinned (2f0692e)

New fixture `slab_with_stub_on_t_junctions` (E3b): an upright 5.7 x 0.6 in quad whose feet lie
inside a 2000 in slab's diagonal edge. Tests:
- the detector joins it through `n_joined_by_tjunction`, with coplanar contact contributing 0;
- `fix_object` ships it;
- the patch test also asserts `n_joined_by_tjunction > 0`.

With the union disabled, all three fail; the `fix_object` test fails because the stub is removed.
This was re-checked after item 10's tighter cap.

E3b at HEAD, run as a scratch copy that passes `max_width` (see Concerns): joined by 1
T-junction, stub kept, `passed` True.

### 4. M2: bbox invariant within the border tolerance (8515461)

`bbox_same` now compares the used-vertex bbox within `border_shift_tol`. The comment records why
deleted faces are left to the guards: 0b4b8e9 compared every reference face and went red (the
stray at `slab_with_strays`' top shrank the bbox); f285ef3 then compared only surviving faces.

New fixture: `plate_with_offset_corner` (E4). The one-face test still fails an 8 in shrink.

E4 `closed=False jitter=0.1`:

| | `bbox_same` | `passed` |
|---|---|---|
| 670ad50 | False | False, with the guard passing and 532 border-shift px |
| HEAD | True | True |

### 5. Minor 1: guard images and preview (e33ccce)

- `_write_guard_images` passes `exposed_after=result.exposed_final` and applies
  `fragment_removed_cap` per view, as `compare_views` does.
- `_failing_view_indices` counts `grown`.
- `save_triptych` colours `PX_GROWN` blue (`_GROWN`).
- The preview's `guard_damaged_px` includes `grown`.
- `ViewVerdict`'s comment now says four classes sum to `edge_flicker`.
- The per-view `report.json` dicts now also carry `grown`, `edge_flicker_grown` and
  `border_shift`.

E-img at e33ccce: `guard_-z.png` went from 6 damage px to 6 excused px and 0 damage, matching the
real guard's 6.

At HEAD, E-img removes nothing. Its 2 sq in stray is 1.7e-3 of a 120 x 80 view, over item 10's
cap, so the images are pinned by tests that loosen the cap.

### 6. Minors 3, 6: docstrings (4f0ae03)

- `classify_pixels` now calls the border shift what it is: the CLEARANCE to the nearest triangle
  of the other mesh. It names `PX_GROWN` in the class list and in what fails, and points at the
  open-border rule as the defence that clearance cannot give.
- The comment in `_classify` is fixed the same way.
- `qa_render.py`'s module docstring and `cli.py`'s comment say the sheet draws every polygon
  outline the export writes, which is more than SketchUp draws.
- Two test comments said the same things and are fixed too.

### 7. Minor 5: ON_FACE_TOL sweep (4571a91)

Swept on both files' output at engine 4f0ae03 with the script in "Scripts" below. At every
tolerance:
- `faces` A 609, B 249;
- `edges` A 1,336, B 687.

| on_face_tol (in) | A: T-junction lines hidden | A: coplanar hidden | A: lines left inside | B: T-junction lines hidden | B: coplanar hidden | B: lines left inside |
|---|---|---|---|---|---|---|
| 0.001 to 0.03 | 16 | 33 | 3 | 3 | 3 | 14 |
| 0.05, 0.1 | 16 | 33 | 3 | 3 | 3 | 15 |
| 0.2 | 16 | 32 | 3 | 4 | 3 | 15 |

`ON_FACE_TOL = 0.02` sits inside the plateau.

### 8. Minor 7: M8 pinned (938dc66)

**`.skp` step.** A non-`SketchUpError` exception in `_write_skp` (an `OSError`, as a ctypes
access violation surfaces) is recorded with its type as `error`, and leaves no stale `.skp`.

**QA step.** The QA step still raised straight through `cmd_fix`: no `report.json`, no `.skp`, and
the previous run's 21 pictures still in `qa/`. It is now an optional export like the `.skp`:
- the previous pictures are deleted first;
- a failure is recorded in `report["qa"]` and printed;
- it does not decide `passed`.

A good sheet records `{"written": true, "images": 21}`. Both paths are tested with a stale
`report.json` present.

### 9. Minor 8: I2 gaps (fdc66e3)

- The docstring no longer claims "the copy replaces the previous run's".
- A passing run deletes a stale `<name>.fixed.FAILED.skp` and records `removed_stale_failed_copy`.
- A failed run's CLI line says "the run FAILED, so <owner file> was kept", or that there was no
  previous copy, and `report.json` records `previous_kept`.

### 10. Minor 9: `fragment_removed_cap` (2242b9e)

The cap went from 5e-3 to 1.2e-4, the largest per-view share recorded for the real files at
900 x 600 (file B, brief 07). Re-measured at 670ad50: A 4.8e-5 (7 px of a 145,828 px view), B 0.
At HEAD: 0 on both, because the three slivers A still removes and B's one cover no guard pixel.

Tests that need `slab_with_strays`' stray removed at 120 x 80 loosen the cap
(`_FIXTURE_FRAGMENT_CAP = 5e-3`). Two new tests:
- the default refuses that stray at 120 x 80;
- the default admits the same stray over a 2000 in slab.

### 11. Minor 4: grown re-class counts (c78bd77)

Every `ViewVerdict` and totals now carry `grown_base` (base class `PX_GROWN`) and what those
pixels became: `border_shift_grown`, `crack_closed_grown`, `zfight_tie_grown`, beside
`edge_flicker_grown` and `grown`. `grown_base` is always the sum of those five.

Real files, final guard:

| File | `grown_base` | became border shift | became crack / tie / flicker / grown | Split of `border_shift` |
|---|---|---|---|---|
| A | 39 | 39 | 0 / 0 / 0 / 0 | 141 = 102 losses + 39 growth |
| B | 8 | 8 | 0 / 0 / 0 / 0 | 55 = 47 losses + 8 growth |

This matches review 2a's observation that border shift rose on A from 106 to 141 and on B from
47 to 55 when `PX_GROWN` landed.

### 12. Minor 11: `_PAIR_BLOCK` (d570927)

The comment now says it bounds each block's candidate arrays, not the result.

Measured with tracemalloc around `_coplanar_contacts` on the detector's own input:

| File | Faces | Box pairs | In contact | Peak memory | Time |
|---|---|---|---|---|---|
| A | 2,644 | 32,089 | 10,653 | 6.3 MB | 0.07 s |
| B | 4,773 | 46,942 | 22,398 | 12.2 MB | 0.12 s |

A is the same at 670ad50.

### Experiments at HEAD (d570927)

| Experiment | Result |
|---|---|
| E4 | bbox_same True, passed True, border_shift 532 |
| E-img | removes nothing (cap, above) |
| E3b | stub kept, passed True (scratch copy with `max_width`) |
| E2b | widths 0.05, 0.10, 0.14 in: sliver False, removed False, passed True, 0/97 rays through the top |

## Real data (d570927; runs 05:46-05:51)

`python -m engine.cli fix data/snapshots/<A|B> --out data/output`, then `preview-data` for both.
All four exited 0. The first attempt at 01:07 finished A and was cut during B by the session
stall, so both files were re-run from scratch.

| | A `CHTM_SIDE_WALK_2nd_floor` | B `CHTM_2nd_to_3rd_building_sidewalk_outside` |
|---|---|---|
| Triangles in / reference / shipped | 4,692 / 4,846 / **1,033** (1,019 at 670ad50) | 7,227 / 7,418 / **596** (593 at 670ad50) |
| passed | **True** | **True** |
| Invariants | material_count_same, bbox_same, area_not_grown, cap_guard_passed, guard_passed: all True | all True |
| Merge | kept, 179 regions | kept, 90 regions |
| Removed | hidden 1,985; zero-area 217; overlap 48; slivers 3; fragments 0 | hidden 2,566; zero-area 79; overlap 23; slivers 1; fragments 0 |
| Fragment detector | 3 components (23 by shared edges; 19 T-junction joins, 1 coplanar); 15 thin faces, 12 sandwiched, 3 slivers; 1 protected component (58 protected faces) | 5 components (21; 16 T-junction joins); 8 thin, 7 sandwiched, 1 sliver; 40 protected faces |
| Fragment guard | 1 round, 3 candidates, 0 failing px, 0 restored | 1 round, 1 candidate, 0 failing, 0 restored |
| Cap guard | passed; 98 skirts, 9 bottoms, 134 invented faces refused | passed; 46 skirts, 8 bottoms, 93 refused |
| `.skp` | 609 faces, 1,336 edges, 3 lines left inside surfaces; `sketchup_check_changed` False; copied to `OBJ FIXED RESULT\CHTM_SIDE_WALK_2nd_floor.fixed.skp`; no stale FAILED copy | 249 faces, 687 edges, 14 lines inside; copied to `OBJ FIXED RESULT\CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp` |
| QA | written, 21 images | written, 21 images |
| preview-data | 1,033 shipped, damaged 0, guard passed | 596, damaged 0, guard passed |

### Every guard total

Model px: A 2,058,592 and B 2,424,975 in every guard. Every count not listed is 0 (holes,
material_changed, moved_same_flat, moved_other, crack_closed, edge_flicker and its four
breakdowns, fragment_removed, grown, crack_closed_grown, zfight_tie_grown).

| Guard | A | B |
|---|---|---|
| `guard_after_removal` | passed; all 0 | passed; all 0 |
| `guard_merge_attempt` (= `guard_final`) | passed; border_shift 141; grown_base 39; border_shift_grown 39 | passed; zfight_tie 2; border_shift 55; grown_base 8; border_shift_grown 8 |

Largest per-view `fragment_removed` share in the final guard: 0 on both files.

### Every removed piece, and whether it was real surface

**What was checked.** The 21 pieces removed at 670ad50 (the owner's previous `.skp`, regenerated
by Hermes at 19f97cc with the same engine): A's 14 slivers plus fragment 4721, and B's 6 slivers.
The 4 pieces removed now are a subset of them.

**Evidence per piece:**
- **Neighbours across each long edge**, found by the detector's own attribution. The run's
  detector input was captured; the reference-level neighbours of the 4 pieces removed now were
  checked separately.
- **Visible lines through the piece.** From 21 points inside the piece and 2,000 directions: the
  (point, direction) lines along which the piece is visible from outside on the reference. For
  each, what a viewer sees once the piece is gone:
  - `surface`: still something within 0.15 in;
  - `exposed`: a side the reference already exposed;
  - `INSIDE`: a side with exposure 0.

  This is the fragment guard's own-pixel rule applied with rays through the piece (review 2a's
  alternative fix 2), with AFTER built from the 670ad50 removal set.
- **Open length.** 2,000 points along the piece at half its local height, with rays along ±normal;
  "open" means nothing within 0.15 in of its plane. Measured in three meshes: the reference
  without the piece, the mesh shipped at 670ad50, and the mesh shipped now.
- **A close-up sheet per piece** in `data/output/<name>/removed/`: an overview along the normal,
  then strips along the whole piece from both sides, each showing the piece with it, without it,
  shipped now, and shipped at 670ad50. Per-piece data is in `evidence.json` beside them.

**File B:**

| Face | w x L (in) | 670ad50 / now | Long edges across | Lines that saw it, after removal | Open at 670ad50 / now | Verdict |
|---|---|---|---|---|---|---|
| **5750** | 0.0159 x 85.9 | removed / kept | 5751 (coplanar, opposite winding, folded over it), 5755, 5749 | 888 lines: 441 surface, 33 exposed, **414 INSIDE** (with 5751 also gone) | **85.87 in** / 0.09 | **Real surface.** With 5751, the only surface closing the top of the ramp's side wall (x = 2948.84) under the walking surface 5752. |
| **5751** | 0.0164 x 128.9 | removed / kept | 5752 (the ramp top, 90°), T-joined 5748/5749/5750/5755; 5753; 5750 | 0 lines reach it (5750 lies over it) | **80.05 in** / 0.06 | **Real surface as a pair.** 670ad50 removed both and shipped an ~86 in x 0.016 in crack under the ramp's edge. Closed now, but the fold draws two lines in the `.skp` (Concerns). |
| 1173 | 0.0012 x 23.8 | removed / kept | 802, 1171, 820 (all 90°) | 10,311: **10,240 INSIDE** | 23.73 / 0.38 | **Real surface**: a 0.001 in riser closing a step. |
| 5229 | 0.0042 x 39.8 | removed / kept | 5228, 4571, 4572 (90°) | 0 lines reach it | 39.80 / 0.16 | Interior, not visible: its removal opened a crack no viewer can reach. |
| 5634 | 0.0047 x 27.4 | removed / **removed** | e0 open only after the hidden pass removed coplanar 5635 across it; 5620/5633/5637; 5618/5639 | 0 lines reach it | 27.09 / 27.09 | Not visible: an interior strip beside hidden 5635. Removal harmless. |
| 6148 | 0.0047 x 27.4 | removed / kept | 6149, 6146, 6144 (90°) | 10,536: **10,413 INSIDE** | 27.37 / 0.10 | **Real surface**: a riser, 5634's mirror twin. |

**File A:**

| Face | w x L (in) | 670ad50 / now | Long edges across | Lines that saw it, after removal | Open at 670ad50 / now | Verdict |
|---|---|---|---|---|---|---|
| 49 | 0.0472 x 41.7 | removed / kept | 50; T-joined 42/47/127/128/4231/4232/4239; 4634 | 20,296: all surface (47 and 50 lie under it, depth 0) | 0 / 0 | Not real surface: a double layer. |
| 174 | 0.0245 x 41.5 | removed / kept | 175; 173; 171, 177 | 16,097: all surface (173/175 under it) | 0 / 0 | Not real surface: a double layer. |
| 1191 | 0.0314 x 66.3 | removed / kept | 1192 (85.8°); 1295; 1190 (6.6°) | 20,791: 20,773 surface, 9 sky, 9 exposed | 0 / 0 | Not real surface: folded into a crease, covered. |
| 1983 | 0.0061 x 13.0 | removed / kept | 1959; in 1933's edge; in 1961's edge (90°) | 0 lines reach it | 13.04 / 0.22 | Interior, not visible. |
| 3257 | 0.0007 x 39.8 | removed / kept | 3256, 3258, 3266 (90°) | 10,408: **9,850 INSIDE** | 39.80 / 1.00 | **Real surface**: a 0.0007 in riser. |
| 3342 | 0.0044 x 23.6 | removed / kept | 3358, 3340; in 3044's edge | 10,458: **10,422 INSIDE** | 23.61 / 0.14 | **Real surface.** |
| 3540 | 0.0015 x 16.2 | removed / **removed** | 2703, 3038 (+3539 coplanar, hidden); in 3039/2706 (+3435 hidden); **free edge open in the reference** | 19,422: 19,000 surface, 119 exposed, **303 INSIDE** | 16.19 / 16.19 | Lip on a rim, mostly harmless. But 1.6% of the lines that saw it now reach unexposed sides, because the hidden pass removed 3435, which lay coplanar under it. **Residual slot** (Concerns). |
| 3610 | 0.0017 x 7.5 | removed / kept | 3611 (coplanar); 3609; 3393, 2993 | 10,311: **9,400 INSIDE** | 7.43 / 0.05 | **Real surface**: one of a band of needles 3610-3613 closing a rim. |
| 3611 | 0.0038 x 16.2 | removed / kept | 3612, 2993; 3613 and T-joins; 3610 and T-joins | 10,285: **10,285 INSIDE** | 16.16 / 0.02 | **Real surface.** |
| 3612 | 0.0022 x 21.0 | removed / kept | 3611 and T-joins; in 3438's edge; in 2993's edge | 10,316: **10,216 INSIDE** | 21.03 / 0.12 | **Real surface.** |
| 3613 | 0.0028 x 8.7 | removed / kept | 3611, 3612, 2993; 2728; 3621 | 10,287: **10,248 INSIDE** | 8.68 / 0.02 | **Real surface.** |
| 3711 | 0.0028 x 8.7 | removed / kept | 3694, 3692; in 3044's edge | 0 lines reach it | 8.69 / 0.05 | Interior, not visible (3613's twin at y = 22669.4). |
| 3908 | 0.0077 x 13.4 | removed / **removed** | 1873, 2427 (+2422 hidden); 1867, 3909 (+3907, 3910 hidden); **free edge open in the reference** | 20,788: 20,491 surface, 297 exposed, 0 INSIDE | 13.42 / 13.42 | Not real surface: a lip on a rim. Removal shows only what is under it or already exposed. |
| 4659 | 0.0034 x 15.2 | removed / **removed** | in 2015's edge (+2014 hidden); in 2058/2023's edges (+2022 hidden); **free edge open in the reference** | 16,389: 11,657 surface, 124 exposed, **4,608 INSIDE (28%)**, median 29° off its plane | 15.20 / 15.20 | **Real cover.** With only the lip removed and hidden faces kept, ~3,100 lines already reach unexposed sides of kept faces 1812/1810. Just past its free edge the same lines hit the exposed top 2058. **Residual slot** (Concerns). |
| 4721 (fragment) | 0.0245 x 41.5 | removed / kept | all edges open (the rest of its invented bottom was hidden-removed) | 9,045: all exposed | 41.49 / 0.02 | Not export debris: a solidify-invented bottom triangle 9.84 in under 174. Its removal showed only sides already exposed; kept per item 2. |

**Tally of the 21 removed at 670ad50:**

| Verdict | Count | Faces |
|---|---|---|
| Real surface whose removal showed the inside through a crack that SHIPPED at 670ad50 | 10 | A 3257, 3342, 3610, 3611, 3612, 3613; B 1173, 6148, and the fold pair 5750+5751 |
| Interior: no outside line reaches them | 4 | A 1983, 3711; B 5229, 5634 (still removed) |
| Double layers | 3 | A 49, 174, 1191 |
| Rim lips | 3 | A 3908 (harmless); A 3540 and 4659 (residual slots, still removed) |
| Solidify's own face | 1 | A 4721 |

The earlier report's "none real surface" was wrong: ten were real surface, and all ten are kept
now.

**Images read with the Read tool:** B `kept_sliver_5750.png` and `kept_sliver_5751.png`, B
`removed_sliver_5634.png`, A `removed_sliver_4659.png` and `removed_sliver_3540.png`.
- The 5751 strip "shipped at 670ad50" shows the wall's top edge cut down along the fold pair,
  about 74-86 in of the 131 in strip. The strips "without it" and "shipped now" are continuous.
- The 5750 strip at 670ad50 shows a magenta (inside) line from the front and an open band from
  the back.
- The 5634 strip "with it" already shows the removed wall 5635 beside it as open.
- The 4659 and 3540 strips show each lip as a flap in an otherwise open (hidden-removed) wall
  plane.

### QA images read

- **B `qa/nx.png`** (along +x, sees the ramp side wall at x = 2948.84): no crack visible at this
  scale. Still visible, from the side-rebuild scope: the fan of triangle edges at the ramp's right
  end (the sheet over-draws copied-row gridlines), and the open, broken left side showing its
  interior members.
- **A `qa/obl_top_a.png`**: the whole sidewalk. The sawtooth broken side along the lower-left
  diagonal and the stepped upper-right rim are unchanged (side-rebuild scope). There are a few
  short polygon-outline marks on the top, and no hole or missing face.

### SketchUp audit (`docs/superpowers/records/scripts/skp_edge_audit.py`, owner's files)

```
CHTM_SIDE_WALK_2nd_floor.fixed.skp: 609 faces, 1336 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)       6      45.5 ft
  hidden (soft)                                                    412    2810.7 ft
  visible, non-manifold (3+ faces)                                  80     155.2 ft
  visible, open border (1 face)                                    488     936.2 ft
  visible, shape edge > 5 deg                                      350    1214.4 ft
    line inside a surface:   511.8 in  [2515.8, 23181.2, 1764.6] -> [2515.8, 22669.4, 1764.6]
    line inside a surface:    11.7 in  [2515.8, 22669.4, 1764.6] -> [2515.8, 22669.4, 1752.9]
    line inside a surface:     9.8 in  [1305.1, 22669.4, 1612.2] -> [1305.1, 22669.4, 1622.0]
    line inside a surface:     9.8 in  [1767.7, 22630.1, 1655.3] -> [1767.7, 22630.1, 1645.5]
    line inside a surface:     1.5 in  [2673.2, 23023.8, 1779.5] -> [2673.2, 23023.8, 1778.1]
    line inside a surface:     1.5 in  [2673.2, 22748.2, 1778.1] -> [2673.2, 22748.2, 1779.5]
  visible open edges split:
    open edge = real border of the model                                       233     499.4 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)        2      47.6 ft
    open edge lying on an angled face (face meets a surface it does not split)   253     389.2 ft
      T-junction line:   551.3 in  [2515.8, 22669.4, 1752.9] -> [2515.8, 23220.6, 1764.6]
      T-junction line:    19.7 in  [1305.1, 22649.7, 1622.0] -> [1305.1, 22669.4, 1622.0]
CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp: 249 faces, 687 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)       5      13.2 ft
  hidden (soft)                                                    144    1485.0 ft
  visible, material border (coplanar)                               12     229.3 ft
  visible, non-manifold (3+ faces)                                  47      94.3 ft
  visible, open border (1 face)                                    315    1130.3 ft
  visible, shape edge > 5 deg                                      164    1811.7 ft
    line inside a surface:    85.9 in  [2948.8, 23496.2, 1828.7] -> [2948.8, 23574.9, 1863.2]
    line inside a surface:    43.0 in  [2948.8, 23574.9, 1863.2] -> [2948.8, 23614.3, 1880.4]
    line inside a surface:     9.8 in  [2870.1, 23437.1, 1807.2] -> [2870.1, 23437.1, 1817.1]
    line inside a surface:     9.8 in  [1610.0, 24008.0, 2104.3] -> [1610.0, 24008.0, 2114.2]
    line inside a surface:     9.8 in  [1491.9, 24165.5, 2104.3] -> [1491.9, 24165.5, 2094.5]
  visible open edges split:
    open edge = real border of the model                                       200     725.6 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)       24      55.4 ft
    open edge lying on an angled face (face meets a surface it does not split)    91     349.3 ft
      T-junction line:    45.5 in  [2909.5, 23456.8, 1818.9] -> [2870.1, 23437.1, 1807.2]
      T-junction line:    44.0 in  [1413.2, 24165.5, 2094.5] -> [1373.8, 24165.5, 2114.2]
      T-junction line:    40.6 in  [1491.9, 24165.5, 2104.3] -> [1531.3, 24165.5, 2114.2]
      T-junction line:    39.7 in  [2121.8, 24204.9, 2042.2] -> [2082.5, 24204.9, 2047.4]
      T-junction line:    39.7 in  [2200.6, 24204.9, 2031.8] -> [2161.2, 24204.9, 2037.0]
```

Notes on the audit:
- B's two longest lines inside a surface (85.9 in and 43.0 in at x = 2948.8) are exactly the edges
  of the kept fold pair 5750/5751.
- A's 551 in T-junction line at x = 2515.8 is the known double layer (session record 6.2).

## Concerns

1. **Two sub-pixel slots onto the inside still ship: file A, faces 3540 and 4659.** Their free
   (longest) edge is open in the reference itself, so the open-border rule names them, and no
   guard pixel meets them.
   - **4659** (0.0034 x 15.2 in): 28% of the lines that saw it now show sides the reference never
     exposed. That is so even with the hidden faces kept.
   - **3540** (0.0015 x 16.2 in): 1.6% of the lines, through coplanar face 3435, which lay under
     it and which the hidden pass removed because the lip covered it.
   - Both were also removed at 670ad50, so this is not new damage.
   - The fix the numbers point to is review 2a's alternative 2: confirm each sliver with rays
     through the candidate itself, and refuse it when one reaches an unexposed side.
     `own_rays.py` below is that check. Not done: this session was limited to the finish steps
     after item 12.
2. **Exposure is unreliable for faces thinner than `EPS_IN` (0.02 in).** Those faces are sampled
   0.02 in off their plane, in their neighbourhood. Example: 5634 measures 23-25% exposed per
   side, yet no outside line reaches any of 21 points on it. The sliver rule runs on the
   post-hidden mesh, so the hidden pass's choices decide which edges look open: 5634's open edge
   exists only because the hidden pass removed its coplanar neighbour 5635.
3. **The fold pair 5750/5751 now draws two lines in B's `.skp`** (85.9 + 43.0 in, the audit's two
   longest lines inside a surface). Keeping them closed the 86 in crack but traded a hole for a
   visible line. The two opposite-wound needles overlap, so one of them suffices; resolving the
   fold would remove the lines.
4. **`detect_fragments` now requires `max_width`** (like `contact_tol`, a property of the mesh). So
   the review's `e3_tjunction_stub.py` and `e3b_tjunction_stub_large.py` fail at their own detector
   call. They are left unchanged (engine-only edits); scratch copies pass
   `max_width=sliver_width_bound(topo.quanta, FixProfile())`. `e_img.py` runs but removes nothing
   at HEAD (item 10's cap).
5. **The ledger (`progress.md`) and `WORK-CLAIMS.md` were not touched.** The coordinator holds an
   uncommitted STALL line in `progress.md`; the ledger entry and releasing the claim are left to
   the coordinator.
6. **The first real run was interrupted.** At 01:09 it was cut during file B by the session stall.
   The owner's B `.skp` stayed at the 22:09 (19f97cc) version until the 05:49 re-run.

## Scripts

Scratch directory:
`C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-MODEL-FIXER\5472478e-978d-426b-bab2-e7cf21699a70\scratchpad\review2a-fixes\`.

- `analyse_real.py` captured the detector's input and the pickles.
- `closeups.py` rendered the sheets.
- `ref_partners.py` and `inside_debug.py` were diagnostics.

The ON_FACE_TOL sweep (cited by `engine/io/skp_writer.py`) and the two measurements the verdicts
rest on are reproduced here.

### `on_face_tol_sweep.py` (item 7)

```python
"""The ON_FACE_TOL sweep of `engine.io.skp_writer` on the CURRENT output of one real snapshot.

Runs `fix_object` exactly as `python -m engine.cli fix` does (default FixProfile), then writes the
shipped mesh with `write_skp` once per tolerance and prints how many lines each tolerance hides
(`tjunction_lines_softened`, `coplanar_edges_softened`) and how many lines inside a surface stay
drawn (`visible_lines_inside_surfaces`). `write_skp` reads the tolerance through the defaults of
`_hide_lines_inside_surfaces` and `_visible_edges`, so those are what the sweep sets. Writes only
into `<out_dir>`; never the owner's files.

usage: PYTHONPATH=<tree> python on_face_tol_sweep.py <snapshot_dir> <out_dir>
"""
import json
import sys
from pathlib import Path

import engine.io.skp_writer as skw
from engine.cli import _copy_assets, _load_snapshot
from engine.fixes.pipeline import FixProfile, fix_object
from engine.io.mtl import parse_mtl
from engine.pipeline import analyse_topology, flat_material_indices

TOLERANCES = (0.001, 0.005, 0.01, 0.02, 0.03, 0.05, 0.1, 0.2)
KEYS = ("faces", "edges", "tjunction_lines_softened", "coplanar_edges_softened",
        "visible_lines_inside_surfaces")

snap, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
_obj, mesh, flatness, _mtl = _load_snapshot(snap)
profile = FixProfile()
result = fix_object(mesh, flatness, profile)
_copy_assets(snap, out)
flat = flat_material_indices(mesh, flatness, profile.flat_texture_std)
topo = analyse_topology(result.mesh, flat, coplanar_angle=profile.coplanar_angle,
                        soft_angle=profile.soft_angle)
print(mesh.name, f"{result.mesh.n_faces} tris, passed={result.passed}")
rows = []
for tol in TOLERANCES:
    skw._hide_lines_inside_surfaces.__defaults__ = (tol,)
    skw._visible_edges.__defaults__ = (tol,)
    written = skw.write_skp(result.mesh, result.rings, result.face_region_final, topo,
                            parse_mtl(out / "materials.mtl"), out / f"sweep_{tol}.skp",
                            tex_dir=out / "tex")
    rows.append({"on_face_tol": tol, **{k: written[k] for k in KEYS}})
    print(json.dumps(rows[-1]))
(out / "sweep.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
```

### `own_rays.py` (visible lines through a piece; core)

For each piece, the scratch copy additionally prints the diagnostics quoted in concern 1:
- the view angles of the INSIDE lines;
- whether the same lines just past the free edge already met an unexposed side;
- what the reference minus only the piece meets.

```python
TOL, EPS, N_DIRS, N_PTS = 0.15, 1e-5, 2000, 21
data = pickle.load(open(sys.argv[1], "rb"))           # analyse_real.py's capture of one run
ref, drop = data["reference"], np.asarray(data["drop"], bool)
topo = analyse_topology(ref)
pc = topo.positions_w - (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
front, back = compute_side_exposure(pc, topo.face_w, topo.ok, n_dirs=128)   # as fix_object does
exposed = np.stack([front > 0.0, back > 0.0], axis=1)
normal = fr._unit_normals(pc[topo.face_w])
removed_fragments = np.asarray(pickle.load(open(sys.argv[3], "rb"))["removed_fragments"], bool)
dirs = fibonacci_sphere(N_DIRS)
for f in faces:
    a, b, c = corners of f, longest edge first
    pts = barycentric (1 - alpha - 1/3, alpha, 1/3), alpha in linspace(0.02, 0.64, 21)
    o = pts[0]                                             # recentre: float32 casters
    before = EmbreeCaster(pc - o, topo.face_w[all but f])
    gone = drop | removed_fragments; gone[f] = True
    after = EmbreeCaster(pc - o, topo.face_w[~gone])
    for every (point p, direction v): s = sign(v . n)
        visible = not before.any_hit(p + EPS * s * n, v)       # the piece is seen from outside
        if visible: g, t = after.first_hit(p + EPS * s * n, -v)  # what is seen there without it
            surface if t <= TOL; sky if no hit; exposed if exposed[g, side of g facing v]; else INSIDE
```

### `crack_scan.py` (open length; core)

```python
TOL, STANDOFF, N = 0.15, 2.0, 2000
for f in faces:
    a, b, c = corners of f, longest edge a-b first; n = unit normal
    s = (arange(N) + 0.5) / N; s_c = projection of c onto a-b
    pts = a + s * (b - a) + 0.5 * height_fraction(s) * (c - foot_of_c)     # half the local height
    for mesh in (reference without f, shipped now, shipped at 670ad50):
        open = False
        for d in (n, -n):
            tri, t = caster(mesh).first_hit(pts + STANDOFF * d, -d)
            open |= (tri < 0) | (STANDOFF - t < -TOL)     # passed the plane: sky or behind it
        print(open.mean() * |b - a|, "in open")
```

## Public signatures

```python
# engine.detectors.fragments
def detect_fragments(positions_w: np.ndarray, face_w: np.ndarray, profile, *,
                     contact_tol: float, max_width: float,
                     protected: np.ndarray | None = None) -> FragmentResult: ...
# FragmentResult.report gains: "contact_tol", "sliver_max_width", "n_protected_components",
# "n_protected_faces", "n_thin_faces", "n_sandwiched_thin_faces"
# (n_above_threshold_components now excludes protected components)
def face_width(positions_w: np.ndarray, face_w: np.ndarray) -> np.ndarray: ...        # unchanged
# private, new: _EdgeTables, _edge_tables(positions_w, face_w, contact_tol),
#   _open_long_edges(positions_w, face_w, faces, area, max_width, tables), _to_segment(points, a, b);
#   _components(positions_w, face_w, contact_tol, tables)

# engine.fixes.pipeline
def sliver_width_bound(quanta: np.ndarray, profile: FixProfile) -> float: ...        # new
class FixProfile:                        # field `sliver_max_width` REMOVED
    fragment_removed_cap: float = 1.2e-4  # was 5e-3
# fix_object: bbox_same compared within border_shift_tol; detector gets max_width and
#   protected=solidify's new_faces

# engine.guard.compare
class ViewVerdict:                       # new fields, default 0
    grown_base: int = 0
    border_shift_grown: int = 0
    crack_closed_grown: int = 0
    zfight_tie_grown: int = 0
# GuardReport.totals gains the same four keys

# engine.guard.render
_GROWN = (40, 110, 220)                  # PX_GROWN in save_triptych's DIFF panel

# engine.cli
# report.json: "qa": {"written": bool, "images": int[, "error": str, "reason": str]};
#   "skp" may carry "error", "previous_kept", "removed_stale_failed_copy",
#   "stale_failed_copy_error"; per-view guard dicts gain "edge_flicker_grown", "border_shift",
#   "grown", "grown_base", "border_shift_grown", "crack_closed_grown", "zfight_tie_grown";
#   "profile" no longer has "sliver_max_width".
# preview stats: guard_damaged_px now includes grown.

# engine.tests.fixtures.build (appended)
def printed(mesh, step=0.1): ...
def slab_with_t_joined_strip(width=0.1, length=29.5, size=40.0, height=8.0, join="vertex"): ...
def slab_with_stub_on_t_junctions(size=2000.0, height=8.0, foot=2.0, rise=0.6): ...
def plate_with_offset_corner(jitter=0.1, closed=False): ...
```
