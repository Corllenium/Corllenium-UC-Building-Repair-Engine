# Sliver rays report (brief 09)

Date: 2026-09-25. Branch `feat-dashboard`, main checkout. Base 7c7840f. Commits 3386c4f and
62bee9d (engine), then 54fbce5 (scripts). The side-rebuild session then committed de14a09 and
a462a60 on top; both are docs only. Last, 3d30327 corrects a docstring in `piece_rays.py`. The real
runs used the engine at 54fbce5, whose code is the same.
Source: brief `docs/superpowers/records/briefs/09-sliver-ray-confirmation.md`, from brief 08's report
(`review2a-fixes-report.md`, concern 1) and review 2a (`review-hermes-fixes.md`, C1 fix alternative 2).

**Status: DONE_WITH_CONCERNS.**
- Both real runs pass, and the owner's two `.skp` files were rewritten (A 08:00, B 08:01).
- File A's two sub-pixel slots are closed: faces 3540 and 4659 are now refused by the rays and ship.
- File B's fold 5750/5751 is resolved: 5751 goes, and 5750 stays because it alone closes the gap.
- Concern: resolving folds also changes which lines SketchUp draws. On file A one new line is drawn
  inside a surface, 88 in long (Concerns 1).

**Suite: `497 passed in 175.18s (0:02:55)`** at 3d30327 (HEAD). It was the same at a462a60:
`497 passed in 176.17s`. The baseline was 462 at 7c7840f.

## Commits, in order

| # | Commit | Item | Suite after |
|---|---|---|---|
| 1 | 3386c4f | `fix(engine): a debris removal is confirmed by rays through the piece itself` | 478 (see note) |
| 2 | 62bee9d | `feat(engine): folds are detected, and a member goes only where the rest still covers it` | 497 |
| 3 | 54fbce5 | `fix(records): the review 2a T-junction stub scripts run again` | 497 (no engine change) |
| 4 | 3d30327 | `docs(engine): piece_rays says what the rays did to brief 08's pieces, exactly` | 497 (docstring only) |

Note on the 478: that count was run before a docstring-only edit to `piece_rays.py`. The committed
content then ran `test_piece_rays.py` alone: 16 passed. 497 was run on exactly the content
committed in 62bee9d, and again at a462a60 and at HEAD.

3d30327 corrects two sentences 62bee9d's level rule made wrong. The docstring had said no piece
brief 08 judged harmless is refused (1983, 3711 and 5229 are), and that every real-surface piece is
refused (5751 alone is not). It also restates the float32 artefact range.

## Item 1: rays through the piece (3386c4f; rule refined in 62bee9d)

### The rule (`engine/guard/piece_rays.py`)

A candidate UNIT is a fragment component (whole) or a sliver (alone). Its faces are sampled with
points (below). For each point p and each exposure direction w, (p, w) is a LINE of the unit when
a viewer out along w sees the unit at p on the whole reference: nothing of the reference lies on
the ray from p toward w. A face level with p (within `TIE` = 1e-6 in along the ray) does not hide
it. That is a tie: a double layer or a fold member is still seen there.

Each line is then followed on from the viewer through p, in AFTER. AFTER is the reference without
`already_removed` (the hidden pass and the zero-area drop) and without every unit still marked.
What the line meets first is one of:
- the sky;
- a face side the reference exposed (`side_exposure`, the same data the fragment guard and the
  final guard read);
- a face LEVEL with p. The line itself met that face at the same place on the reference, so its
  side was seen whatever the sampled exposure says;
- a side never exposed.

A unit with any line of the last kind is refused. Units are put back one per round, and every unit
still marked is then judged again. The unit put back first is one that fails even when judged
alone; otherwise the lowest. So of two pieces that fail only because each covers the other, one
stays and the other goes.

`fix_object` runs the rays first, then `fragment_feedback`. When the pixel guard puts faces back,
the rays run again with those faces in place, and the guard again, until neither puts anything
back.

**How many points, and why.** 256 per face, one per equal-area stratum. The strata are
`slices` fans from the apex over equal parts of the longest edge, times `bands` equal-area bands
toward the apex. They are as square as the face allows, with never fewer than 4 bands. A needle
therefore gets 64 slices along its length and 4 across; file A's 16.2 in lip 3540 is sampled every
0.25 in.

Measured with the module itself on brief 08's captured references (`engine_rays_real.py` below),
128 directions, each piece alone:
- 3540 opens its slot along **219 of 15,360** lines at 256 points.
- At 64 points it opens it along **0 of 3,840**: 16 slices x 4 bands, and the slot falls between
  the slices.

64 is too few for a needle. 256 is the least count tried that finds 3540's slot. A face costs
0.02 to 0.10 s.

**Float64 near the piece.** Embree stores vertices as float32. On file B, around 5750, its hits
strayed 6.2e-5 in outside face 5752's 129 in edge, and one ray leaked through 5751 at 1.1e-4 in
inside its edge. That is a sizeable part of a strip 0.0015 in wide. So every ray is cast in float64
for its first `REACH` = 1 in from p: Moller-Trumbore over only the faces whose boxes reach within
1 in of that point, with a 1e-9 barycentric slack so shared edges do not leak. Beyond that, embree
takes over, recentred on the unit.

**Reported per candidate.** `FixResult.fragment_ray_check` and report.json `fragment_ray_check`
give each unit's `points`, `lines`, `lines_level`, `lines_inside`, `inside_faces` (up to 5),
`refused` and `removed`. Every `fragment_removals` entry carries `lines` and `lines_inside`. Also
new: `n_refused_by_rays` and `feedback_history["fragment_rays"]`.

### Tests (`engine/tests/test_piece_rays.py`; fixtures appended to `build.py`)

**Required by the brief:**
- E2b's sandwiched strip in a 2000 in slab is refused, at widths 0.05 and 0.14. Tested alone,
  more than 90% of its lines reach the slab bottom's back. Tested through `fix_object` with the
  detector made to name it, it is kept and all 97 rays down it hit z = 0. On the engine before
  this commit the same run removed it with `passed` True (checked).
- A rim-lip slot is refused (`slab_with_lip_over_a_slot`: its long edge is open, so it is named a
  sliver, and it covers the slab's only opening). On the engine before this commit, `fix_object`
  removed it with `passed` True, and all 28 rays down the slot fell to z = -8 (checked). Now it is
  kept and those rays hit z = 0.
- A free needle standing on the slab, pointing into the sky, is removed, with lines > 0 and 0
  inside.
- A double layer lying on a coplanar face is removed. It lies either exactly in the top's plane or
  0.01 in above it: a 0.001 in lift was welded back into the plane, so the test uses the print
  step and asserts that the lift survives.
- Determinism, of the check and of `fix_object`.

**Also added:**
- Review C2's infill patch is refused as one two-face unit.
- Equal-area strata.
- All marked units are judged gone together, with one of two mutual covers going.
- The level rule.
- The covered semantics and `judge_alone` (item 2).

**Changed existing tests, deliberately:**
- `test_the_final_guard_judges_what_a_removed_fragment_uncovered` now also switches the rays off.
  It tests the final guard alone, and the rays are a third earlier defence.
- `test_every_removed_component_is_reported_with_its_faces_area_and_bbox` pins the new keys. Its
  old assertions stand unchanged.

**Mutations** (scratch copies of `engine/`): each one fails at least one test. The first four
were run at 3386c4f on `test_piece_rays.py`. The rest were run on the final code, on
`test_piece_rays.py` and `test_folds.py`.

| Mutation | Tests failing |
|---|---|
| Never refuse (at 3386c4f) | 8 |
| Level faces hide the piece | 5 |
| Each unit judged alone | 1 |
| One band | 1 |
| Never refuse (final code) | 11 |
| Refuse all failing units at once | 2 |
| No "fails alone" priority | 1 |
| Highest first | 1 |
| Level faces not counted as seen | 1 |
| Cover semantics ignored | 1 |

### Brief 08's 21 pieces, judged by the module (each alone, 256 points, 128 directions)

| File | Piece | Lines | Reaching an unexposed side | Rays | Brief 08's verdict |
|---|---|---|---|---|---|
| A | 3540 | 15,360 | 219 | refused | residual slot |
| A | 4659 | 12,181 | 3,738 | refused | residual slot |
| A | 3908 | 16,384 | 0 | confirmed | harmless lip |
| A | 49 / 174 / 1191 | 15,619 / 12,248 / 15,872 | 0 / 0 / 0 | confirmed | double layers |
| A | 3257 / 3342 | 8,192 / 8,192 | 8,192 / 8,192 | refused | real surface |
| A | 3610 / 3611 / 3612 / 3613 | 7,936 each | 7,935 / 7,936 / 7,936 / 7,936 | refused | real surface |
| A | 1983 | 5,984 | 5,797 | refused | "interior, 0 lines" -- wrong |
| A | 3711 | 8,192 | 8,189 | refused | "interior, 0 lines" -- wrong |
| A | 4721 | 7,025 | 0 | confirmed | solidify's own face |
| B | 5750 | 21,499 | 1,082 | refused | real surface (pair) |
| B | 5751 | 22,041 | 0 | confirmed | real surface (pair) |
| B | 1173 / 6148 | 8,192 / 8,192 | 8,192 / 8,016 | refused | real surface |
| B | 5229 | 7,424 | 7,424 | refused | "interior, 0 lines" -- wrong |
| B | 5634 | 15,616 | 0 | confirmed | harmless |

What the rays decide against brief 08's verdicts:
- **Real surface:** every piece is refused, except 5751 judged alone. 5750 and wall face 5753
  cover all of 5751; the pair removed together opened the crack, and judged together one of them
  would be kept.
- **Double layers, the lip 3908, 5634 and solidify's 4721:** all confirmed.
- **1983, 3711 and 5229**, which brief 08 called interior: refused. They are visible (next
  paragraph).

**Correction to brief 08.** 1983, 3711 and 5229 are not interior. They are seen from thousands of
lines, and their removal at 670ad50 opened views onto the inside. Brief 08's crack scan had
measured those openings (13.04, 8.69 and 39.80 in open at 670ad50), but its verdict relied on
`own_rays.py`:
- For 1983 and 5229, float32 rays started 1e-5 in off the piece met each piece's coincident twin
  (1982, 5233). Along the lines inspected, the twin was met 1.0e-5 to 8.5e-5 in *behind* the ray's
  own start.
- For 3711, own_rays' own visibility test sees all 2,048 of my stratified lines. Its 0 came from its
  21 points on one line.

All three are kept today (the open-border rule), so nothing ships wrong now.

## Item 2: folds (62bee9d)

### Detection (`engine/detectors/folds.py`)

A fold is two faces with three distinct corners each that:
- share exactly one edge;
- both have area;
- lie in one plane: each third corner within `contact_tol`, the T-junction tolerance, of the
  other's plane;
- have both third corners on the same side of that edge.

Exact duplicates share all three edges. They are counted (`n_duplicate_pairs`) and left to the
overlap pass. Two reasons mean a fold is never proposed and is only reported:
- "different materials" (the duplicate-layer rule);
- "protected" (a face solidify invented; the cap guard's question).

On the solidified references after the hidden pass there are 43 folds on A and 31 on B.

### Which member goes: coverage by rays, not the fold's shape

Each member is judged ALONE (`piece_rays.judge_alone`). It is covered when every line along which
it was seen, with it gone, meets a face level with it. The covered member is proposed: the smaller
one when both are covered, then the higher id. Proposed members are judged with every other
removal done as pieces that must STAY covered: `piece_ray_check(covered=...)` refuses them unless
`lines_level == lines`. That is stricter than debris, which may uncover the sky.

"Lies within the other" was the first design, and file B shows why it is wrong:
- 5750 lies within 5751 except for a sliver 0.0018 in wide below the ramp's edge. That sliver is
  all that closes the wall's top there. Removed alone, 1,082 of 5750's 21,499 lines reach
  unexposed sides (mostly the ramp top's underside 5752).
- 5751 does not lie within 5750, yet 5750 and wall face 5753 cover it along all 22,041 lines.

The level rule and one-per-round refusal came out of the fold members.
- **The level rule.** A 3059 was seen along 684 lines, and every one met its fold partner 3082
  level with it. So did all 29 lines through B 2254, which met 2253 level. In each case the side
  met was one the exposure's 4 points x 128 directions never found: 2253 samples 0.0 on both
  sides.
- **One per round.** With every failing unit refused at once, members that cover each other were
  both kept in a scratch run: B 859/908, 5673/5676, 5848/5851, and A 3155/3156/3761.

### Tests (`engine/tests/test_folds.py`, plus piece_rays tests)

**Detection:**
- a folded pair in either winding;
- a crossing pair;
- two materials, and solidify's faces: never proposed;
- exact duplicates are not folds.

**`fix_object`:**
- resolves the folded pair: face 2 goes, the top is whole, `passed`;
- keeps the lip over a slot and removes its cover (5750/5751 in miniature);
- leaves a crossing fold on a bare plate ("neither is covered by the rest"), where debris rules
  would have let the sky show;
- reports a fold it never proposed;
- removes the smaller of two covered members;
- judges fold members as covers;
- is deterministic.

**Mutations, on the final code** (`test_folds.py` and `test_piece_rays.py`): each fails at least
one test.

| Mutation | Tests failing |
|---|---|
| Opposite-side pairs counted as folds | 6 |
| Materials ignored | 2 |
| Protected faces ignored | 2 |
| Any member proposed, covered or not | 1 |
| Fold units judged as debris | 1 |
| The larger covered member first | 1 |

## Item 3: the review scripts (54fbce5)

`e3_tjunction_stub.py` and `e3b_tjunction_stub_large.py` failed at
`engine.__file__.split("review2a")[1]` (IndexError outside the review's scratch tree). After that,
they would have failed at the detector call, which lacked `max_width`. Both now pass
`max_width=sliver_width_bound(topo.quanta, FixProfile())` and print the engine path whole.

Run at 62bee9d, both finish. The stub is one component with the slab, joined through 1 T-junction
(0 by coplanar contact). It is not a fragment, and `fix_object` keeps it with `passed` True, 0
fragment pixels and 0 holes, at 40 in (240 x 160) and at 2000 in (900 x 600).

## Real data (runs 07:58:44 to 08:03:35, engine 54fbce5)

`python -m engine.cli fix data/snapshots/<A|B> --out data/output`, then `preview-data` for both.
All four exited 0. A took 76 s and B 79 s (fix, QA and `.skp`).

| | A `CHTM_SIDE_WALK_2nd_floor` | B `CHTM_2nd_to_3rd_building_sidewalk_outside` |
|---|---|---|
| Triangles in / reference / shipped | 4,692 / 4,846 / **1,031** (1,033 before) | 7,227 / 7,418 / **600** (596 before) |
| passed | **True** | **True** |
| Invariants | material_count_same, bbox_same, area_not_grown, cap_guard_passed, guard_passed: all True | all True |
| Merge | kept, 178 regions (179 before) | kept, 90 regions |
| Removed | hidden 1,985; zero-area 217; overlap 23 (48 before); slivers 1 (3 before); **folds 29**; fragments 0 | hidden 2,566; zero-area 79; overlap 7 (23 before); slivers 1; **folds 19**; fragments 0 |
| Refused by the rays | 4 faces: slivers 3540, 4659; fold members 3155, 3156 | 4 faces: fold members 859, 5673, 5676, 5848 |
| Ray rounds | 5; lines reaching unexposed sides 8,547, 8,328, 4,590, 935, 0 over 34 to 30 units | 5; 4,217, 1,837, 1,741, 1,025, 0 over 24 to 20 units |
| Fragment guard | 1 round, 30 candidates, 0 failing px, 0 restored | 1 round, 20 candidates, 0 failing px, 0 restored |
| Fragment detector | 3 components; 15 thin, 12 sandwiched, 3 slivers; 58 protected faces | 5 components; 8 thin, 7 sandwiched, 1 sliver; 40 protected faces |
| Folds | 43: **34 resolved**, 9 left; 3 duplicate pairs | 31: **22 resolved**, 9 left; 1 duplicate pair |
| Cap guard | passed; 98 skirts, 9 bottoms | passed; 46 skirts, 8 bottoms |
| `.skp` | 588 faces (609 before); 1,321 edges; 397 hidden; writer's lines inside surfaces 4 (3 before); copied to `OBJ FIXED RESULT` | 254 faces (249); 690 edges; 149 hidden; lines inside surfaces 9 (14 before); copied |
| QA | written, 21 images | written, 21 images |
| preview-data | 1,031 shipped, damaged 0, guard passed, 29 folds | 600, damaged 0, guard passed, 19 folds |

### The removal list, each piece's ray verdict

Fold members must stay covered, and every one below met a level face along every line
(`lines_level == lines`). "Unexposed" counts the lines that reached a side never exposed.

**File A (30 removed):**

| Face | Kind | Area (sq in) | Covered by | Lines | Unexposed |
|---|---|---|---|---|---|
| 39 | fold | 97.02 | 4230 | 224 | 0 |
| 42 | fold | 48.27 | 4231 | 3,899 | 0 |
| 49 | fold | 0.98 | 50 | 15,619 | 0 |
| 72 | fold | 1,743.16 | 90 | 7,970 | 0 |
| 106 | fold | 48.76 | 4236 | 3,997 | 0 |
| 145 | fold | 97.47 | 143 | 6,140 | 0 |
| 146 | fold | 96.48 | 143 | 6,894 | 0 |
| 174 | fold | 0.51 | 171 | 12,248 | 0 |
| 194 | fold | 437.04 | 4110 | 3,599 | 0 |
| 2643 | fold | 7.15 | 2641 | 7,962 | 0 |
| 2908 | fold | 12.15 | 2947 | 4,775 | 0 |
| 2909 | fold | 96.83 | 2903 | 3,059 | 0 |
| 3058 | fold | 96.74 | 3082 | 1,323 | 0 |
| 3059 | fold | 96.87 | 3082 | 684 | 0 |
| 3100 | fold | 21.61 | 3099 | 7,569 | 0 |
| 3300 | fold | 7.15 | 3098 | 7,314 | 0 |
| 3761 | fold | 28.24 | 3155 | 3,641 | 0 |
| 3842 | fold | 7.23 | 2640 | 7,679 | 0 |
| **3908** | **sliver** (0.0077 in wide) | 0.05 | -- | 16,384 | 0 |
| 4115 | fold | 96.92 | 4113 | 5,603 | 0 |
| 4165 | fold | 581.54 | 4623 | 374 | 0 |
| 4186 | fold | 290.77 | 4187 | 150 | 0 |
| 4220 | fold | 96.97 | 4226 | 0 | 0 |
| 4228 | fold | 48.46 | 4227 | 110 | 0 |
| 4263 | fold | 581.54 | 4264 | 224 | 0 |
| 4401 | fold | 144.65 | 4379 | 3,236 | 0 |
| 4531 | fold | 42.80 | 4495 | 4,266 | 0 |
| 4542 | fold | 64.94 | 4295 | 4,261 | 0 |
| 4549 | fold | 1,550.00 | 4248 | 6,263 | 0 |
| 4616 | fold | 290.48 | 4607 | 272 | 0 |

Refused on A:

| Face | Kind | Lines | Level | Unexposed | Faces met |
|---|---|---|---|---|---|
| **3540** | sliver | 15,360 | 0 | **219** | 2595, 2727, 2733, 2734, 3438 |
| **4659** | sliver | 12,181 | 24 | **3,738** | 899, 900, 1371, 1372, 1373 |
| 3155 | fold | 7,413 | 6,194 | 1,108 | -- |
| 3156 | fold | 3,173 | 3,078 | 95 | -- |

**File B (20 removed):**

| Face | Kind | Area (sq in) | Covered by | Lines | Unexposed |
|---|---|---|---|---|---|
| 451 | fold | 174.28 | 498 | 65 | 0 |
| 500 | fold | 9.21 | 499 | 69 | 0 |
| 908 | fold | 48.76 | 859 | 3,792 | 0 |
| 2142 | fold | 193.70 | 2141 | 144 | 0 |
| 2244 | fold | 193.70 | 2243 | 189 | 0 |
| 2251 | fold | 193.70 | 2252 | 0 | 0 |
| 2254 | fold | 193.70 | 2253 | 29 | 0 |
| 2256 | fold | 193.70 | 2263 | 0 | 0 |
| 2261 | fold | 193.70 | 2262 | 131 | 0 |
| 2280 | fold | 193.70 | 2140 | 200 | 0 |
| 2548 | fold | 169.74 | 2550 | 3,213 | 0 |
| 4125 | fold | 48.41 | 5016 | 0 | 0 |
| 4135 | fold | 43.89 | 4507 | 62 | 0 |
| 4457 | fold | 42.75 | 4455 | 100 | 0 |
| 4458 | fold | 42.75 | 4455 | 166 | 0 |
| **5634** | **sliver** (0.0047 in wide) | 0.06 | -- | 15,616 | 0 |
| **5751** | **fold** | 1.06 | 5750 | 22,041 | 0 |
| 5815 | fold | 38.78 | 5816 | 3,680 | 0 |
| 5817 | fold | 2.95 | 5816 | 2,567 | 0 |
| 5851 | fold | 60.58 | 5849 | 765 | 0 |

Refused on B (fold members):

| Face | Lines | Level | Unexposed |
|---|---|---|---|
| 859 | 4,198 | 3,000 | 1,198 |
| 5673 | 736 | 533 | 28 |
| 5676 | 1,116 | 951 | 136 |
| 5848 | 1,797 | 787 | 905 |

### Folds resolved and left

**Resolved on A (34 folds, 29 members):**
39/4230, 42/4231, 49/50, 49/4634, 72/90, 106/4236, 143/145, 143/146, 171/174, 173/174, 174/175,
194/4110, 2640/3842, 2641/2643, 2641/3842, 2903/2909, 2908/2947, 3058/3082, 3059/3082,
3098/3300, 3099/3100, 3155/3761, 3156/3761, 4113/4115, 4165/4623, 4186/4187, 4220/4226,
4227/4228, 4248/4549, 4263/4264, 4295/4542, 4379/4401, 4495/4531, 4607/4616.

**Left on A (9):**
- 7 are protected, each a solidify face folded over an original face: 266/4694, 4136/4692,
  4384/4840, 4399/4717, 4402/4716, 4738/4745, 4788/4790. The last covers 1,547 sq in twice, at
  x = 2515.8: the known double layer.
- 3155/3158 and 3156/3158 were refused by the rays. With every removal done, 1,108 and 95 lines
  no longer met a level face.

**Resolved on B (22 folds, 19 members):**
451/498, 499/500, 859/908, 2140/2280, 2141/2142, 2243/2244, 2251/2252, 2253/2254, 2256/2263,
2261/2262, 2548/2550, 4125/5016, 4135/4507, 4455/4457, 4455/4458, 4456/4457, 4456/4458,
**5750/5751** and **5751/5753** (both by removing 5751), 5815/5816, 5816/5817, 5849/5851.

**Left on B (9):**
- "Neither is covered by the rest" (3). Each member alone, as lines / level / unexposed:
  - **5303/5871, region 79**, 47.71 sq in covered twice: 5303 160 / 131 / 29; 5871
    142 / 130 / 12.
  - 2265/2266: 79 / 70 / 9 and 195 / 132 / 63.
  - 5668/5669: 153 / 3 / 28 and 64 / 2 / 22.
- Protected (1): 2645/7249.
- Refused by the rays (5): 859/861, 5673/5676, 5673/5677, 5676/5848, 5848/5851. This is one
  cluster of members that cover each other; its other members, 908 and 5851, went.

### Every guard total

Model px: A 2,058,592 and B 2,424,975 in every guard. Every count not listed is 0. The zeros are:
holes, material_changed, moved_same_flat, moved_other, crack_closed, edge_flicker and its four
breakdowns, grown, crack_closed_grown and zfight_tie_grown. Before this brief, `fragment_removed`
was 0 everywhere; the fold members' own pixels are what is excused by name now.

| Guard | A | B |
|---|---|---|
| `guard_after_removal` | passed; fragment_removed 35 | passed; fragment_removed 16 |
| `guard_merge_attempt` (= `guard_final`) | passed; fragment_removed 35; border_shift 141; grown_base 39; border_shift_grown 39 | passed; zfight_tie 2; fragment_removed 16; border_shift 55; grown_base 8; border_shift_grown 8 |

### SketchUp audit (`docs/superpowers/records/scripts/skp_edge_audit.py`, the owner's files)

```
CHTM_SIDE_WALK_2nd_floor.fixed.skp: 588 faces, 1321 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)       8      48.8 ft
  hidden (soft)                                                    397    2792.7 ft
  visible, non-manifold (3+ faces)                                  76     142.1 ft
  visible, open border (1 face)                                    486     932.0 ft
  visible, shape edge > 5 deg                                      354    1236.6 ft
    line inside a surface:   511.8 in  [2515.8, 23181.2, 1764.6] -> [2515.8, 22669.4, 1764.6]
    line inside a surface:    29.5 in  [1275.6, 22826.9, 1612.2] -> [1275.6, 22826.9, 1582.7]
    line inside a surface:    11.7 in  [2515.8, 22669.4, 1764.6] -> [2515.8, 22669.4, 1752.9]
    line inside a surface:     9.8 in  [1305.1, 22669.4, 1612.2] -> [1305.1, 22669.4, 1622.0]
    line inside a surface:     9.8 in  [1767.7, 22630.1, 1655.3] -> [1767.7, 22630.1, 1645.5]
    line inside a surface:     9.8 in  [1305.1, 22659.6, 1612.2] -> [1305.1, 22669.4, 1612.2]
  visible open edges split:
    open edge = real border of the model                                       232     498.6 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)        3      54.9 ft
    open edge lying on an angled face (face meets a surface it does not split)   251     378.6 ft
      T-junction line:   551.3 in  [2515.8, 22669.4, 1752.9] -> [2515.8, 23220.6, 1764.6]
      T-junction line:    88.0 in  [1334.7, 22630.1, 1582.7] -> [1413.4, 22630.1, 1622.0]
      T-junction line:    19.7 in  [1305.1, 22649.7, 1622.0] -> [1305.1, 22669.4, 1622.0]
CHTM_2nd_to_3rd_building_sidewalk_outside.fixed.skp: 254 faces, 690 edges
  VISIBLE LINE INSIDE A FLAT SURFACE (coplanar, same material)       2       1.6 ft
  hidden (soft)                                                    149    1498.9 ft
  visible, material border (coplanar)                               12     229.3 ft
  visible, non-manifold (3+ faces)                                  51     100.1 ft
  visible, open border (1 face)                                    311    1139.8 ft
  visible, shape edge > 5 deg                                      165    1801.8 ft
    line inside a surface:     9.8 in  [2870.1, 23437.1, 1807.2] -> [2870.1, 23437.1, 1817.1]
    line inside a surface:     9.8 in  [1491.9, 24165.5, 2104.3] -> [1491.9, 24165.5, 2094.5]
  visible open edges split:
    open edge = real border of the model                                       200     728.7 ft
    open edge lying ON a coplanar face (T-junction line inside a surface)       20      47.2 ft
    open edge lying on an angled face (face meets a surface it does not split)    91     363.9 ft
      T-junction line:    45.5 in  [2909.5, 23456.8, 1818.9] -> [2870.1, 23437.1, 1807.2]
      T-junction line:    44.0 in  [1413.2, 24165.5, 2094.5] -> [1373.8, 24165.5, 2114.2]
      T-junction line:    40.6 in  [1491.9, 24165.5, 2104.3] -> [1531.3, 24165.5, 2114.2]
      T-junction line:    39.7 in  [2121.8, 24204.9, 2042.2] -> [2082.5, 24204.9, 2047.4]
      T-junction line:    39.7 in  [2200.6, 24204.9, 2031.8] -> [2161.2, 24204.9, 2037.0]
```

Against the previous owner files (d570927), audited the same way:

| Audit class | A before | A now | B before | B now |
|---|---|---|---|---|
| Lines inside a flat surface | 6 / 45.5 ft | 8 / 48.8 ft | 5 / 13.2 ft | 2 / 1.6 ft |
| T-junction lines on a coplanar face | 2 / 47.6 ft | 3 / 54.9 ft | 24 / 55.4 ft | 20 / 47.2 ft |
| Non-manifold | 80 | 76 | 47 | 51 |

- **B.** The fold's two lines (85.9 and 43.0 in at x = 2948.8) and the 9.8 in line at
  (1610.0, 24008.0) are gone from "inside a surface".
- **A.** The two 1.5 in lines at x = 2673.2 are gone. Two lines are added to that class: 29.5 and
  9.8 in, both drawn before too, and reclassified because their face count changed (checked in the
  `.skp`: before, 1 face and 4 faces; now 2 each). One T-junction line is added: 88.0 in. It is
  new; see Concerns 1.

A point-set diff of every drawn (non-soft) edge, old file against new (`skp_draw_diff.py` below):

| File | Newly drawn | No longer drawn |
|---|---|---|
| A | 2 lines, 107.7 in: 88.0 in at y = 22630.1; 19.7 in at x = 1334.7, where fold 4186/4187 was | 1 line, 9.8 in |
| B | 6 lines, 112.9 in | 9 lines, 188.2 in |

### Close-ups, read

Written by `closeups9.py` (below) to `data/output/<name>/removed/b09_*.png`. Each sheet has an
overview along the face's normal, then strips along the whole face from its front and its back.
Each strip is shown with the face, without it, as shipped now and as shipped before (d570927).
Colours: red the face, blue surface in its plane, magenta something behind it (the inside), yellow
something in front, white sky.

- **A 3540** (`b09_kept_sliver_3540.png`; strips 16.5 in along x 0.006 in across):
  - With it, the lip is a red band between coplanar surface and magenta.
  - Without it, even on the full reference, the band is magenta: nothing else covers it.
  - Shipped now, the band is surface: the lip is back, and around it are the coplanar faces the
    hidden pass removed.
  - Shipped before, the band was solid magenta: the slot.
  - The back side is the same.
- **A 4659** (`b09_kept_sliver_4659.png`; 15.5 x 0.014 in): the same pattern, with a face in front
  (yellow) along one stretch. Now its band is surface; before it was magenta over its whole length,
  from both sides.
- **B 5751, removed** (`b09_removed_fold_5751.png`; 131.5 x 0.066 in):
  - Its band is surface with it, without it, shipped now and shipped before, with identical counts
    (36,246 / 36,249 px) and no magenta. 5750 and 5753 cover it exactly, as the rays said.
  - A small magenta sliver on the back at the far right exists on the reference with and without
    it (877 px), and is closed in both shipped meshes.
- **B 5750, kept** (`b09_kept_fold_5750.png`; 87.6 x 0.064 in):
  - With it, its band shows as red dashes where it wins the z-fight with 5751.
  - Without it, the dashes turn magenta from the front (854 px onto the inside) and white from the
    back (854 px more sky). That is the gap below the ramp's edge that it alone closes, and why it
    stays.
  - Shipped now and shipped before are solid surface, with the same 2 px magenta on the front.

## Concerns

1. **Resolving folds changes which lines SketchUp draws, and no rule measures that. On file A one
   new line is drawn inside a surface: 88.0 in, at y = 22630.1, from (1334.7, 1582.7) to
   (1413.4, 1622.0).**
   - That wall is drawn twice. One layer is a fan of triangles up to z 1612.2. The other layer has
     4549 and 4550, which the merge used to fuse into one polygon, so no diagonal showed.
   - 4549 is a fold member covered along all 6,263 of its lines, so it went. The part of it no
     other face covers is interior: none of its 16 sample points there is reached by any outside
     line, and the final guard counts 0 holes.
   - 4550 then ships alone, and its long edge lies across the fan. That is a T-junction line, and
     the writer keeps it because the corner above z 1612.2 has no face on the other side.
   - 4550 itself is not covered along every line: 3 of its 4,329 lines see past it. So removing it
     too would break the rule.
   - Across both files the drawn-line diff is: A 2 new (107.7 in) and 1 gone; B 6 new (112.9 in)
     and 9 gone (188.2 in).
   - Owner's decision. One follow-up would judge a double layer as a whole. Another would keep a
     fold member whose removal leaves part of its merged polygon lying over another layer.
2. **B's fold lines are no longer lines inside a surface, but a line still runs along the ramp's
   edge.** With 5751 gone, what is drawn there is the wall's top border: 5750's edge P-Q and
   5753's edge Q-S. They lie within 0.0164 in of the ramp top's own edge P-S, which was drawn before
   too. The point-set diff therefore counts nothing "gone" there. The two lines stopped being
   lines inside a flat surface; a real edge line along the ramp edge stays.
3. **Folds left.**
   - A has 9: 7 protected, each a solidify face lying folded over an original face, and 2 refused.
   - B has 9: 3 where neither member is covered (region 79 among them), 1 protected, and 5 refused.
   - Region 79 cannot be resolved by removing a member. Each covers area nothing else does, and a
     vertex where their edges cross would have to be invented.
   - The protected ones belong to the side rebuild. Its merge onto this branch waits for this
     brief, and it changes solidify's faces, so these counts will change.
4. **Fold members removed with 0 lines** (A 4220; B 2251, 2256, 4125) count as covered vacuously.
   No sampled line from outside reaches them, and the guards agree: no pixel changed.
   - Lines are samples, 256 points x 128 directions per face. A piece seen along very few lines can
     read as unseen. In scratch, B 5871 had 1 line at 16 points and 0 at 64.
5. **The fold pass takes over part of the overlap pass's work.** On A, overlap removals went from
   48 to 23, with 29 fold members. On B, from 23 to 7, with 19. Faces that qualified for both now
   go through the rays and the fragment guard instead of the strict guard.
6. **The exposure data under-reports barely visible sides.** The level rule covers ties.
   - A side met at depth is still judged by the sampled exposure.
   - The refusals of 3540 and 4659 rest on 219 and 3,738 lines meeting sides the exposure calls
     unexposed. The close-ups show those as magenta (more than 0.15 in behind the plane). That is
     consistent with brief 08's slots.
7. **The rule changed within item 2's commit.** The level rule and one-per-round refusal changed
   `piece_rays` after item 1 was committed. 62bee9d's message says so, with the measurements.
8. `progress.md` and `WORK-CLAIMS.md` were not touched. The side-rebuild session edited both
   meanwhile (de14a09, a462a60).

## Scripts

Scratch directory:
`C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-MODEL-FIXER\5472478e-978d-426b-bab2-e7cf21699a70\scratchpad\sliver-rays\`.

**Exploration:** `proto_rays.py`, `proto2.py`, `proto_folds.py`, `dbg_1983.py`, `dbg_twin.py`,
`dbg_fold.py`, `level_debug.py`, `fold_cover_real.py`, `folds_real.py`.

**Evidence:** `real_check.py` (scratch `fix_object`), `report_tables.py`, `line_faces.py`,
`skp_edges_on.py` and `dbg_4549.py` (Concern 1).

**Mutations:** `mutate.py`.

The captured references are brief 08's `%TEMP%\r2a\{A,B}\analysis.pkl` (engine 74adf48). Solidify,
exposure and topology are unchanged since then; `git log 74adf48..HEAD` touches none of them.

### `engine_rays_real.py` (the 21-piece table)

```python
data = pickle.load(open(sys.argv[1], "rb"))                    # brief 08's capture
ref, drop = data["reference"], np.asarray(data["drop"], bool)
topo = analyse_topology(ref)
pc = topo.positions_w - (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
front, back = compute_side_exposure(pc, topo.face_w, topo.ok, n_dirs=128)      # as fix_object
exposed = np.stack([front > 0.0, back > 0.0], axis=1)
for f in faces:
    for n in counts:
        r = piece_ray_check([np.array([f])], pc, topo.face_w, exposed, directions=fib_dirs(128),
                            already_removed=drop, n_points=n)
        print(f, n, r.verdicts[0])
```

### `skp_draw_diff.py` (drawn lines, old file against new; core)

```python
def drawn(path):              # every non-soft edge of the .skp, via engine.io.skp_writer.read_skp
    m = read_skp(Path(path), uvs=False, triangles=False)
    return [(e.start, e.end) for e in m.edges if not e.soft]
# sample every drawn edge every 0.5 in; an edge longer than 1 in more than half of whose samples
# lie over 0.05 in from every drawn edge of the other file is "new" (or "gone")
```

### `closeups9.py` (the sheets; core)

For each face: take the longest edge a-b, the unit normal n, u = (b - a)/|b - a| and v = n x u.
For each panel mesh (reference, reference without the face, shipped now, shipped before) and each
side (+n, -n), cast an orthographic grid from 2 in off the plane along -side, over 1.02 times the
face's length by its width plus 1.5 widths either side. Colour each hit by its signed depth from
the plane: within 0.15 in blue, in front yellow, behind magenta, none white.

## Public signatures

```python
# engine.guard.piece_rays (new)
N_POINTS = 256
MIN_BANDS = 4
REACH = 1.0          # inches cast in float64 from the piece before embree
TIE = 1e-6           # inches along a ray: a face this close to p is level with the piece
def strata_points(tri: np.ndarray, n: int = N_POINTS, min_bands: int = MIN_BANDS) -> np.ndarray: ...
@dataclass
class PieceRayCheck:
    confirmed: np.ndarray        # bool per unit, still marked
    verdicts: list               # per unit: {"faces", "points", "lines", "lines_level",
                                 #  "lines_inside", "inside_faces", "refused"} or None
    history: list                # per round: {"round", "units", "lines", "lines_inside", "refused"}
def judge_alone(units, positions_c: np.ndarray, faces: np.ndarray, side_exposure: np.ndarray, *,
                directions: np.ndarray, already_removed: np.ndarray | None = None,
                n_points: int = N_POINTS, caster_factory=EmbreeCaster) -> list[dict]: ...
def piece_ray_check(units, positions_c: np.ndarray, faces: np.ndarray, side_exposure: np.ndarray, *,
                    directions: np.ndarray, already_removed: np.ndarray | None = None,
                    marked: np.ndarray | None = None, covered=None, n_points: int = N_POINTS,
                    caster_factory=EmbreeCaster) -> PieceRayCheck: ...

# engine.detectors.folds (new)
@dataclass
class FoldResult:
    folds: list          # {"faces": [f, g], "edge": [u, v], "overlap_area", "reason"}
    report: dict         # {"contact_tol", "n_folds", "n_never_proposed", "n_duplicate_pairs"}
def detect_folds(positions_w: np.ndarray, face_w: np.ndarray, face_material: np.ndarray, *,
                 contact_tol: float, protected: np.ndarray | None = None) -> FoldResult: ...

# engine.fixes.pipeline
class FixResult:                         # new fields
    n_refused_by_rays: int
    fragment_ray_check: list             # per unit: {"kind": "fragment"|"sliver"|"fold", "faces",
                                         #  "points", "lines", "lines_level", "lines_inside",
                                         #  "inside_faces", "refused", "removed"}
    n_removed_folds: int
    fold_report: dict                    # detector report + "n_resolved", "n_left", "folds":
                                         #  [{"faces", "edge" (ends, input coords), "overlap_area",
                                         #    "members" (alone verdicts), "redundant", "verdict",
                                         #    "reason", "lines", "lines_level", "lines_inside"}]
# n_restored_fragments now counts candidates put back by the rays or the fragment guard;
# fragment_removals entries gain "lines", "lines_inside" (and kind "fold" with "covered_by");
# feedback_history gains "fragment_rays"; "fragments" rounds are numbered on across guard calls.
# private, new or changed: _debris_units(detected, reference_ids, fold_members),
#   _confirm_debris(units, positions_c, render_faces, render_material, flat_materials, depth_tol,
#                   drop, side_exposure, profile),
#   _fold_members(folds, face_w_local, reference_ids, positions_c, render_faces, side_exposure,
#                 drop, profile), _fold_report(folds, chosen, alone, reference_ids, removed,
#                 ray_check, positions_c, centre),
#   _fragment_removals(..., ray_check, covered_by)

# engine.cli
# report.json gains "n_refused_by_rays", "n_removed_folds", "fold_report", "fragment_ray_check";
# preview stats gain "n_refused_by_rays", "n_removed_folds"; --keep-fragments also keeps folds.

# engine.tests.fixtures.build (appended)
def slab_with_lip_over_a_slot(size=2000.0, height=8.0, length=16.0, width=0.1, slot=0.05): ...
def _slab_on_its_diagonal(name, extra_points, extra_faces, size, height, uv_per_unit=0.05): ...
def slab_with_standing_needle(size=2000.0, height=8.0, length=16.0, rise=0.05): ...
def slab_with_needle_lying_on_top(size=2000.0, height=8.0, length=16.0, width=0.05, lift=0.0): ...
def slab_with_folded_pair(size=40.0, height=8.0, apex=(0.6, 0.4), flip=False, material=0): ...
def slab_with_folded_lip_over_a_slot(size=2000.0, height=8.0, length=16.0, width=0.1, slot=0.05,
                                     cover=0.02, beyond=1.0): ...
def plate_with_crossing_fold(): ...
def slab_with_fold_lying_on_top(size=40.0, height=8.0): ...
```
