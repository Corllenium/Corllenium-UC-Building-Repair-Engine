# Review since b2134e9, part 2: the side rebuild, its merge, briefs 08 and 09 (brief 04)

Independent read-only review, 2026-09-25. Everything is read at `e27eb79`, the head of
`feat-dashboard` when the review started, never the working tree. Every `file:line` below is at
`e27eb79`.

Scope, by commit:
- **The side rebuild** (`feat/side-rebuild`): ff4a0ec, 65e566c, f57cb17, 9562aa3, 6233671,
  0f24da4, f58243d, 6eb6fb8, cb85e0d, 8d238c4.
- **The merge**: 68f6d15 and a89f771, 82adc60, ca463c2.
- **Brief 08**: 536fca7, 74adf48, 2f0692e, 8515461, e33ccce, 4f0ae03, 4571a91, 938dc66, fdc66e3,
  2242b9e, c78bd77, d570927.
- **Brief 09**: 3386c4f, 62bee9d, 54fbce5, 3d30327.

The four reports were read in full: `side-rebuild-report.md`, `reconcile-side-rebuild-report.md`,
`review2a-fixes-report.md` and `sliver-rays-report.md`.

## How it was checked

- **Scratch worktree.** A detached worktree at `e27eb79` sits in this folder (`wt/`, removed at
  the end). `PYTHONPATH` was pinned to it, and `engine.__file__` was confirmed inside it.
- **Engine suite.** **542 passed in 161.11 s**, which is the count the reconcile report gives
  (`suite_e27eb79.txt`). No engine file changed between ca463c2 and `e27eb79`: the five commits
  in between are records only.
- **Not re-run:** the authors' mutation tables for briefs 08 and 09.
- **Probe scripts.** Twelve probes and two trace scripts sit beside this file. Each builds a small
  synthetic mesh, runs the committed engine (mostly `fix_object`), and prints what ships.
  - Most probes run at two guard sizes: 240 x 160, and the real default of 900 x 600.
  - Where it matters they also run at the real files' scale: a 2000 in slab, where a guard pixel
    spans about 2 to 3 in.
  - To run one: `PYTHONPATH=<tree at e27eb79> .venv/Scripts/python.exe <probe>`.
- **Not done, by rule.** No real data was run, the CLI was not run, the SketchUp GUI was not
  opened, and the API tests were not run. Statements about files A and B rest on the reports and
  are marked unverified where they matter.

## Verdict: Changes required

Two defects ship visible damage while every guard passes (`passed = True`), on scenes of a few
dozen faces:
- **C1.** The side rebuild lays a new face ON an original face whenever the cap guard gives a
  replaced piece back while keeping the face over it. It also bottoms two coincident top regions
  twice. The coincidence rule (review C1's fix) never looks at either case. The result is a
  z-fighting double layer ("texture on texture"), made by the fix itself.
- **C2.** A slab's UNDERSIDE that a top runs into is still processed as a top when a neighbour's
  side hangs along one of its edges. Its invented bottom then covers it through the shell
  exemption, and the hidden pass deletes the real underside. This is S-C1's failure, surviving
  SR6's underside test.

Two more need fixing before the next owner check:
- **I1.** Rule 4 replaces ANY face in the 2.5 in band. It changes a side's material, and at the
  real files' scale it deleted a separate object standing outside the slab.
- **I2.** One deep own side lets `_lower_surface` take the floor under an open slab as the slab's
  own underside. Rule 5 then lets the walls box in, and the hidden pass delete, whatever stands in
  between.

Both also ship visible damage with `passed = True`. They are rated Important, not Critical, only
because nobody has yet shown their trigger on A or B. I1 needs a side of another material, or an
object within 2.5 in of a broken side. I2 needs a deep own side over an enclosed space.

The merge composes both branches correctly. 82adc60 is sound. Briefs 08 and 09 hold up under
their own terms (see "Checked and found sound").

Findings: **2 Critical, 2 Important, 5 Minor.**

---

## Critical

### C1. The fix makes coincident double layers: a new face over a piece the guard gave back, and two bottoms over one top

**Where:**
- `engine/fixes/solidify.py:1357` and `:1368`: `_coincident_new_faces` compares a new face only
  with ORIGINAL faces, and never with its own group's pieces
  (`cand[replaced_group[cand] != new_group[f]]`), because those are to be removed.
- The cap guard gives pieces back and keeps the new faces laid on them, in three places:
  - `engine/guard/compare.py:1418-1421`: a wall that loses any face gives back ALL its pieces,
    while its other faces stay.
  - `compare.py:1446-1451` (`reveal`) and `:1514-1516`: a piece whose pixel fails is restored,
    "and the new face is kept".
  - `compare.py:1422-1424` (`piece_cover`, SR6): a bottom's piece comes back when ANY face over it
    is refused, while the other faces over it stay. This path is the same code shape, and was not
    reproduced separately.
- Walls are deduplicated across regions through `built_walls` (`solidify.py:598-605, 934`), but
  nothing deduplicates bottoms (`solidify.py:960-978`).
- Pieces lie ON the new face's plane as a rule. SR1 measured a broken side's faces at a median
  0.0 in (A) and 0.017 in (B) from the new face's plane (side-rebuild report section 2).

**Failure 1: a piece given back under its kept wall** (`probe_restored_piece_double_layer.py`,
`probe_restored_piece_detail.py`, `dbg_restore_reason2.py`):
- Input: `slab_with_sawtooth_side` with the teeth in the side plane and in material m1 (the top is
  m0). One tooth reaches 3 in below the slab.
- At 900 x 600, the cap guard runs three rounds: (0, 9,572 failing, 0 refused, 1 restored),
  (1, 9,478, 3, 0), (2, 0, 0, 0).
- Faces 41, 48 and 49 were refused, all as `covers_outside_footprint`. Face 41 belongs to the
  wall over tooth 35, so the group rule gave tooth 35 back. Face 40 of the same wall was kept, and
  it lies on the tooth: **21.33 sq in coplanar, m0 over m1.**
- `passed` is True. The fold pass reports the pair (`[35, 38]`) and never proposes it. The overlap
  pass only reports it (different materials).
- With the teeth in the top's own material (`probe_restored_piece_same_material.py`) the result
  is the same. The shipped x = 0 plane holds 300 sq in of faces over a 278.7 sq in union:
  - the fold's reason is "protected";
  - the overlap pass finds the pair but removes nothing, because neither face is fully covered;
  - `passed` is True.

**Failure 2: the same at the real files' scale** (`probe_piece_below_wall.py`):
- Input: a closed slab whose x = 0 side is missing except one tooth in the plane, its tip 3 in
  below the slab.
- **2000 in slab:** the tooth's fin shows in 8 pixels, so it is restored. One wall face is
  refused and the other kept: **a 14.46 sq in coincident double layer ships**, `passed` True.
- **40 in slab:** both wall faces are refused instead. No double layer, but no side is rebuilt
  either.

**Failure 3: two bottoms for two coincident tops** (`probe_double_bottom.py`):
- Input: a closed-sided slab with no bottom whose top is a double layer of m0 and m1. Such pairs
  exist in the export: B had 39 different-material overlap pairs at b2134e9.
- Each top region gets its own bottom at 8 in, 0 are refused, and the shipped underside is
  **1,600 sq in of m0 exactly over 1,600 sq in of m1**. `passed` is True at both sizes.

**Why nothing catches it:**
- The cap guard itself: once tooth 35 was back, round 2 counted 0 failing pixels with face 40
  still on it. At every one of the tooth's pixels, the ray tracer's tie between the two coplanar
  faces went to the tooth, so face 40 was never the first hit there. That is why review C1 asked
  for a geometric coincidence test in the first place: pixels cannot see a coincident pair.
- The final guard compares against the solidified reference, which already has both layers.
- `detect_folds` reports such a pair and never proposes it: "protected" or "different materials"
  (`engine/detectors/folds.py:94-95`).
- The overlap pass removes a face only when the other faces of its OWN region cover 99 % of it
  (`engine/fixes/overlap.py:17-21`). A partial overlap, or one across two regions (another
  material, or the other winding), stays.

**Real files (unverified).** Three measurements are consistent with this:
- The side rebuild raised B's final-guard z-fight ties from 2 to 46 px (reconcile report section
  9.5).
- A has 7 and B 14 restored pieces of KEPT walls and bottoms, each lying in its new face's band.
- The pieces of every wall that lost a face (A 392, B 90 refused wall faces) are not counted at
  all (M3).

**Fix:**
1. Make coincidence part of every round, not a one-off before the first round:
   - refuse any kept new face that lies on an original face present in the current state,
     restored pieces included;
   - or, when a piece is restored, refuse the faces of its own group that lie on it.
2. Make a wall all-or-nothing: when one of its faces is refused, refuse the others too, so
   nothing stays on the pieces it gives back. Or give walls `piece_cover` too.
3. Test each new face against the faces this run already built (as `built_walls` does for walls),
   and never build a bottom face on an existing bottom face.
4. Keep the three failure probes as regression tests. At least one must run at the 2000 in scale.

### C2. An underside with a neighbour's side hanging along it is processed as a top, and the hidden pass deletes it

**Where:**
- `solidify.py:773` is SR6's underside test. A no-sky region that a top runs into counts as an
  underside only when EVERY own side stands up (`max(row_depth.values()) <= tol`). One hanging
  face makes it a top.
- `solidify.py:792` and `:994-995`: every processed region's faces become `shell_faces`.
- `compare.py:1500-1507`: a bottom may take a PARALLEL face as interior when it is a shell face.
- `compare.py:1484-1499`: rule 5 reads the point 0.25 in in front of the hit against the region's
  own volume. Here that volume's "top" is the underside itself, and its depth is the invented
  bottom's.

**Failure** (`probe_underside_with_hanging_neighbour.py`):
- Input:
  - L is a closed slab: top z = 0 over x 0..40, bottom -8.
  - B is a closed block beside it, x 40..80, z 0..20, overhanging open air.
  - B's underside is flush with L's top, so L's x = 40 edge continues into it. L's own 8 in side
    lies along the underside's x = 40 edge: that is the hanging "own side".
- Solidify:
  - takes B's underside for a top (`top_regions_continued` 1, `undersides_not_tops` 0,
    representative depth 8 in);
  - builds a bottom 8 in below it and three 8 in walls hanging from its other edges;
  - refuses nothing. The cap guard's first round has **0 failing pixels**.
- The hidden pass then **deletes B's real underside** (faces 12 and 13).
- The shipped mesh has **0 sq in** left at z = 0 over B's footprint, and **1,600 sq in of
  invented floor at z = -8**. The block reaches 8 in lower than it does, on three new walls.
  `passed` is True at 240 x 160 and 900 x 600.

This is SR6 item 3's failure ("each got a bottom invented under the real underside ... which hid
the real underside for the hidden pass to delete"). SR6 fixed it only for undersides with no
hanging side.

**Real files (unverified).** The side-rebuild report (section 9, concern 1) lists continued
regions of A with a little own side hanging:
- 467, 166 and 244, and three more (502, 33, 709) with high rising-to-hanging ratios.
- Region 467 kept 23 of its 121 invented bottom faces.
- If 467 is an underside, which the report does not settle, those 23 faces lie under a real
  underside that the hidden pass then removed.

**Fix:**
1. Decide "underside" by what lies above and below the region, not by which way its own sides
   run. The author's own measurement for region 57 is the test: rays up meet this slab's top
   within its depth, and rays down meet nothing within reach.
2. Let a region's own faces be shell for its bottom only when the region sees sky (or passed that
   test). A bottom must never take a no-sky region's own parallel faces as interior.
3. Keep the probe as a regression test.

---

## Important

### I1. Rule 4 replaces any face in the band: a side's material changes, and at the real files' scale an object outside the slab is deleted

**Where:**
- `solidify.py:593-595` and `:642-644`: a piece is any eligible face with every corner within
  `side_band` (2.5 in) of the side plane, within 30 degrees of parallel, and at least half inside
  the window (`_PIECE_INSIDE_FRACTION`, `:139`).
- Nothing asks whether the face belongs to the slab: no material, connectivity or shell test.
- `solidify.py:890`: the wall takes the TOP region's material.
- `compare.py:1476-1483`: rule 4 measures only the distance from the piece's hit point to the new
  face's plane. The final guard compares against the reference, which already lacks the piece.

**Failure 1: the material** (`probe_side_material.py`). The sawtooth fixture's teeth are given m1
("concrete") under an m0 top. The x = 0 side ships as **320 sq in of m0, where the input had
128 sq in of m1**: 4 pieces replaced, 0 refused, `passed` True at both sizes. Every tooth pixel
changed material, and no rule names that or measures it.

**Failure 2: an object outside the volume** (`probe_object_in_band.py`):
- Input: `slab_with_half_side` with a sign in m1, standing 1.2 in in front of the missing half,
  below the top. The sign is one face, as SketchUp signs usually are.
- **40 in slab:** the sign is kept. Grazing guard pixels see its back through the 1.2 in slot and
  `reveal` restores it.
- **2000 in slab, 900 x 600:** both its triangles are **replaced, that is deleted**, with
  `passed` True. The sign lies outside the slab's volume, is another material, and touches
  nothing of the slab.
- The railing test passes only because the railing reaches 30 in above the top. Anything that
  stays below the top is a piece.

Piece removals are also the one removal in the engine not confirmed by rays. Up to half a piece's
area may lie outside the face that replaces it (`:642-644`), and only the cap guard's pixels see
that part (Failure 2 of C1).

**Fix:**
1. A piece must belong to the slab: it shares an edge or a T-junction with the top's outline,
   with another piece, or with an own side.
2. Keep a piece whose material differs from the wall's, and build only where nothing is. Or give
   the wall the pieces' own material when they share one. Or make rule 4 fail a pixel whose
   AFTER material differs from BEFORE's, which restores the piece.
3. Confirm each replaced piece with rays through it (`engine.guard.piece_rays`), as debris is
   since brief 09. Its lines must meet the new face within the band, or the slab's inside.

### I2. One deep own side lets the floor under an open slab become its "lower surface", and rule 5 then lets walls box in what stands there

**Where:**
- `solidify.py:1196`: `depth > deepest_own + band` is the only test that the surface met is this
  slab's own.
- `solidify.py:843`: `deepest_own` is the single deepest own side.
- `solidify.py:630-637`: with a lower surface, a side is judged over the trapezoid down to it. A
  side that is whole at its own depth therefore counts as broken, and is replaced.
- `solidify.py:846-853` and `:948-953`: walls and the slab's volume follow the surface.
- `compare.py:1484-1509`: rule 5 accepts whatever lies inside that volume. The volume is the
  builder's own plan, so any wrong depth authorises its own walls.

**Failure** (`probe_lower_surface_floor.py`):
- Input:
  - S is a slab with 2 in skirts on three sides and no bottom.
  - Its fourth edge lies along W, a wall face 32 in deep that S is attached to: an own side.
  - L is a lower slab with S's footprint, its top 24 in down.
  - A bench stands on L under S.
- S's representative depth is 2 in, yet L's top passes as S's lower surface (24 <= 32 + 2.5).
- The three WHOLE 2 in skirts are replaced by 24 in walls, and 0 wall faces are refused.
- The hidden pass deletes the bench (12 of 12 faces) and L's top. `passed` is True at both sizes.
- With W wider than S (y -10..50), all six wall faces are refused, because the guard sees W
  beyond the footprint through the open space. The guard therefore catches this only when
  something outside the footprint shows through.

**The brief's other three cases, checked by reading:**
- **Below ground: no.** Wall ends stop at the surface's plane, at least `min_thickness` and at
  most `reach` down (`solidify.py:851-852`), and the surface must be floor-like.
- **Over an opening: by design.** Up to 10 % of the rays may miss and up to half the hits may be
  other regions. The plane is then extrapolated over those parts, which is right for one slab of
  constant thickness.
- **Through a neighbour:** not reproduced.

**Fix:**
1. Accept a lower surface only when the slab's own sides reach it along a real share of the
   outline, length-weighted, not when the one deepest own side does.
2. Never extend a side that is whole at its own measured depth (a whole 2 in skirt) down to a
   lower surface. Extend only a side that is broken at every depth, which is the ramp's case.
3. Report every region whose walls or volume were set by a lower surface deeper than its
   representative depth plus `side_band`.

---

## Minor

**M1. SR6's opened-crack rule excuses a crack twice the border tolerance, and never asks what
shows through it.**
- **Where:** `compare.py:640-669` measures BEFORE's point against the nearest AFTER triangle of any
  surface. For a crack there is always a surface across it, so the crack's half-width is what
  gets measured.
- **Measured** (`probe_opened_crack_width.py`, the test's own `_crack_scene` at 0.15 in):
  - cracks of 0.02 to 0.29 in give 25 `border_shift` px and pass;
  - 0.31 in fails.
- The test is named "narrower than its border tolerance" (`engine/tests/test_guard.py:1867`), yet
  the bound is 2 x tol. The fragment excuse asks whether AFTER shows the sky or an exposed side;
  this rule does not.
- **Fix:**
  - measure against AFTER triangles in BEFORE's own plane and material;
  - require AFTER to show the sky or an exposed side there;
  - pin a case between 0.15 and 0.3 in.

**M2. The underside test also takes a real top for an underside when its hanging sides are the
missing ones** (`probe_real_top_taken_for_underside.py`).
- A floor R under a landing continues from a sky-seeing top L. R's only own side is the riser up
  to the landing, and its two sides are open.
- R is counted in `undersides_not_tops`, and nothing is built under it. L's edge into R becomes a
  "side", and its wall is refused (`covers_outside_footprint`).
- The effect is a missed rebuild, not damage. C2's fix (look above and below) covers this too.

**M3. `side_pieces_restored` counts only restored pieces of KEPT groups** (`solidify.py:1062-1063`).
The pieces a wall gave back because it lost a face are counted nowhere. Those are where C1's
double layers come from.

**M4. Docstrings that no longer match the code:**
- `compare.py:1257-1266`, `solidify_feedback`: still says "Only faces are ADDED" and lists rule 2
  (back sides allowed) among the allowed changes. SR2 removes pieces, and SR4 removed rule 2.
- `engine/fixes/pipeline.py:127-132`, `cover_max_exposure`: says it reads the FRONT side. Since
  SR4 it reads whichever side the ray met.
- `engine/cli.py:12-13` still says the `.skp` is copied "the LATEST, overwriting the previous
  one". Since I2 and fdc66e3, only a passing run replaces the owner's copy.
- The session record's section 3 cap-guard cell:
  - it says "a new face lying on an existing one is refused" (not true, C1);
  - it leaves out rule 1, background covered unmeasured.

**M5. Two SR6 tests pin plans that never ship.**
- `test_a_top_edge_that_ran_into_an_underside_only_is_a_side` (`engine/tests/test_solidify.py:1164`)
  asserts a wall that the cap guard refuses whole on that fixture (the author's concern 3).
- `_planned` (`test_solidify.py:333-344`) also reports no replaced pieces, so no plan test covers
  replacement.
- The shipped behaviour of `slab_beside_a_lower_top` is untested.

---

## Checked and found sound

- **The merge 68f6d15 composes both branches.** `fix_object` at `e27eb79` runs, in order:

  | Step | `engine/fixes/pipeline.py` |
  |---|---|
  | Solidify, with the side rebuild | `:609` |
  | Exposure on the reference | `:623` |
  | The hidden pass | `:655` |
  | Debris and folds, through the rays then the fragment guard | `:699-756` |
  | Flip | `:760` |
  | Overlap | `:770` |
  | The merge, with its threading | `:788` |
  | The guards | `:842-877` |
  | The invariants | `:915-929` |

  - Invented faces reach `detect_fragments` and `detect_folds` as `protected` through
    `result.new_faces` over the reference layout (`:704-720`).
  - Replaced pieces never reach either, because they are not in the reference.
- **a89f771 and ca463c2** are test-only and meaningful.
- **82adc60** is sound. It only removes an excuse (`own` is initialised for runs without debris,
  `compare.py:537`), so it can make a run fail, never pass.
- **SR4 (review C1).**
  - A covered hit is judged by the original exposure of whichever side the ray met
    (`compare.py:1468-1471`).
  - The reversed-underside and duplicate-skirt probes are regression tests.
  - 0f24da4 (review M1) now tests the one-round cut-off path with a real verification round.
- **SR5 and SR6 item 2 (review I1).**
  - Only own sides measure (`solidify.py:216-255`), and review 1's deep-corner probe stays 2 in
    (`test_solidify.py:936-950`).
  - The representative depth is the length-weighted lower median, with ties going to the
    shallower depth, exactly as its docstring says (`:305-312`).
  - I2 is a new path around this rule, not a regression of it.
- **Brief 08.**
  - The open-border rule (`engine/detectors/fragments.py:364-423`) handles shared edges,
    T-vertices inside the edge, edges lying inside another face's edge, and nearest-edge
    attribution.
  - Protected faces are never debris, and a component holding one is never a fragment.
  - `bbox_same` holds within `border_shift_tol` (`pipeline.py:917-918`).
  - The CLI's failed-QA and failed-`.skp` paths work as described.
  - Review 2a's docstring items are fixed: the clearance wording (`compare.py:426`, `:605`) and
    `qa_render.py:11`. The one exception is M4's `cli.py:12-13`.
- **Brief 09.**
  - `piece_ray_check` ends only when no marked unit fails with EVERY marked unit gone. Refusing
    one unit per round therefore cannot let a harmful combination through. The fragment guard
    only puts faces back, and the rays judge again after it does.
  - Rays are cast in float64 near the piece. The level rule and the `covered` rule for folds
    (`lines_level == lines`) are what the report says.
  - Folds need one plane and the same side of the shared edge. Different materials and protected
    faces are never proposed.
- **Determinism** (`probe_determinism.py`). Two scenes that take the replace and restore paths
  were each run twice through `fix_object`. The shipped faces, materials, positions and the
  solidify, fragment and fold reports are identical: e7fbc141... and 24e752fe....
- **Docstring numbers match the reports:**
  - `_representative_depth`: 804.1 / 13.1 / 33.74; 1,452.3 / 29.5 / 39.37; 1,152.9 / 29.52;
    38 of B and 56 of A.
  - `_lower_surface`: 41 and 154 of 196; 34.8 to 37.2 in against 39.37 in.
  - `_interior_test`: 3.05e-6 in; 4,395; 3.4e-4 to 7.9e-4 in.
  - `SIDE_BAND_MAX`: 1.98 and 2.35 in; 7 and 15 px.
  - The underside comment: 64 and 5.
  - `piece_rays`: 219 of 15,360 at 256 points, 0 of 3,840 at 64.
  - The `ON_FACE_TOL` comment names the engine commit its sweep ran on.

## The authors' own concerns, re-checked

| Concern | Result |
|---|---|
| Side rebuild section 9, 1: the underside test misses some undersides | Confirmed, and the consequence is worse than stated: C2 (the real underside deleted, every guard passing) |
| Side rebuild 9.2: `max_thickness` 36 in is below the 39.37 in blocks | A design question; not re-measured |
| Side rebuild 9.3: the cap guard judges a wall and its bottom separately | Consistent with the code; M5 |
| Side rebuild 9.4 and 9.5: one commit for four fixes; reconcile conflicts | Process; the composition is checked above |
| Reconcile 9.5: B's z-fight ties 2 -> 46 px | Consistent with C1 (not traced on the real files) |
| Reconcile 9.7: A's double layer at z 1612.2 | From the export (the reference faces there are input rows); not C1's mechanism |
| Brief 08, 1: A's slots 3540 and 4659 | Closed by brief 09 (both refused by the rays) |
| Brief 08, 2: exposure is unreliable below `EPS_IN` | Still open. The rays read `side_exposure` for the face a line meets (`piece_rays.py:251`). That exposure is sampled `EPS_IN` off the face's plane (`exposure.py:88`) and is per face side, so a line meeting a large face at a spot nobody saw counts as exposed. This is review 2a's residual risk; not reproduced. |
| Brief 09, 1: fold resolution draws new lines (A +88 in) | Confirmed by reading. Nothing in `_fold_members` or `_confirm_debris` looks at edges, so the owner's rule "outlines only on the model's edge" is unmeasured there. One option: keep a member whose removal leaves its partner's edge lying across a coplanar same-material face. |
| Brief 09, 4: fold members with 0 lines removed | Consistent with the hidden pass, which treats a face no sampled line reaches as hidden |

## Probe scripts in this folder

| Script | Shows |
|---|---|
| `probe_restored_piece_double_layer.py`, `probe_restored_piece_detail.py` | C1 failure 1: a wall face kept on a tooth it gave back, 21.33 sq in, m0 over m1 |
| `probe_restored_piece_same_material.py` | C1 in one material: the fold and overlap passes leave it |
| `probe_piece_below_wall.py` | C1 at 2000 in (14.46 sq in); at 40 in, no side rebuilt |
| `probe_double_bottom.py` | C1 failure 3: two coincident bottoms, m0 and m1 |
| `probe_underside_with_hanging_neighbour.py` | C2: the real underside deleted, an invented one 8 in lower |
| `probe_side_material.py` | I1 failure 1: the side's material changed |
| `probe_object_in_band.py` | I1 failure 2: a sign outside the slab deleted at 2000 in |
| `probe_lower_surface_floor.py` | I2: a bench and a floor deleted under an open slab |
| `probe_opened_crack_width.py` | M1: cracks up to 0.29 in excused |
| `probe_real_top_taken_for_underside.py` | M2 |
| `probe_determinism.py` | two scenes, twice each: identical |
| `dbg_restore_reason.py`, `dbg_restore_reason2.py` | traces for C1 failure 1 (which wall, which tooth, which round) |

The outputs of the longer runs are beside them (`out_*.txt`), and the suite's is in
`suite_e27eb79.txt`.
