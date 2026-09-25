# Review of brief 10: the side-rebuild follow-ups (9f64ae9 .. f7e27d1)

This is an independent, read-only review, done on 2026-09-25. Everything was read at `dc24e9a`.
The working tree was not used, because another session is editing engine code there. Every
`file:line` below refers to `dc24e9a`.

**Scope.** Ten commits:
- 9f64ae9: rule 6 and `_refuse_together`
- c2b1611: `max_thickness` raised to 50 in
- 8c729c1: `_is_underside`
- 3561127: C1 (no double layers)
- 01cc420: I1 (piece belonging, wall material)
- 444d0ef: I2 (lower surfaces)
- 170141f: M1 (opened cracks)
- eb920df, c56018d: tests and docstrings
- f7e27d1: item 6 (a block standing on a slab)

**Read in full:**
- the brief `docs/superpowers/records/briefs/10-side-rebuild-followups.md`;
- the author's report `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/side-rebuild-followups-report.md`;
- review part 2 (`review-side-rebuild.md`), its probe scripts, and the session record's map of
  which file handles which error.

## How it was checked

**Scratch worktree.** A detached worktree was made at `dc24e9a` (`wt/`, removed at the end).
`PYTHONPATH` was pinned to it, and `engine.__file__` was printed by every probe to confirm the path.

**Engine suite.** `566 passed in 271.35s`. This is the count the report gives.

**Probes.** The probe scripts are in `probes/`, next to this file, and each one's output is in an
`out_*.txt` file beside it. Each probe:
- builds a small synthetic mesh;
- runs the committed engine (`fix_object`, or `solidify` as the tests call it);
- prints what ships.

They run at the default 900 x 600 guard, and at 240 x 160 where a probe says so. Where scale
matters they also run at the real files' scale (2000 in, where one guard pixel spans 2 to 3 in).

To run one:

    PYTHONPATH="<tree>;<probes>" .venv/Scripts/python.exe <probe>.py

**Before/after comparisons.** Older commits were compared in two ways:
- **Exported trees.** `git archive <commit> engine` was extracted into scratch folders for
  e27eb79, 8c729c1 and 3561127. These were deleted afterwards; the same command recreates them.
- **Mutations.** A mechanism was switched off inside `dc24e9a` by monkeypatching one function
  (rule 6 off; `_refuse_together` made a no-op; rule 6's path check removed).

**Not done, by rule.** No real data was run and the CLI was not run. Statements about files A and B
rest on the report and are marked unverified.

## Verdict: Changes required

Review part 2's C2 is still reachable. `_is_underside` takes the real underside of an overhang for
a top when:
- the block above the underside does not see sky;
- the block is taller than 52.5 in;
- or a fascia hangs from the underside's free edge.

In each case a bottom is invented under it, the hidden pass deletes the real underside, and
`passed` is True at the default 900 x 600 guard. The fascia case needs the real files' scale for
this.

Rule 6 makes this worse. It removes the only check the cap guard still had on a wrong slab
volume: a thing outside the slab showing through it. On the same scene with a post behind the
overhang:
- **rule 6 off:** the walls are refused and the underside ships;
- **rule 6 on:** the walls are kept and the underside is deleted.

Two more commits regress common shapes:
- **3561127.** At a step between two slabs that both lost their shared side, the lower wall is
  refused whole, and a band of the side the input already had open stays open (160 sq in in the
  probe).
- **01cc420.** A real piece in the middle of a side is no longer a piece, so that side stays half
  open.

It also still deletes parts of objects near a slab's sides and bottoms.

Findings: **1 Critical, 3 Important, 6 Minor.**

---

## Critical

### C1. A real underside is still taken for a top and deleted: C2 survives for shaded, tall and fascia'd overhangs

**Where:**
- `engine/fixes/solidify.py:339-346`, `_is_underside`'s ABOVE test. It counts only surfaces of
  `sky` regions (`sky = set(regions)` at `:943`, which are the sky-seeing tops). The reach is
  `max_thickness + side_band` (`:990`, 52.5 in).
- `solidify.py:322-338`, its BELOW test. One own side hanging `min_thickness` (2 in) or more below
  a free edge makes the region a top, with nothing weighing it against the sides standing up.
- A region taken for a top has its faces made shell faces (`solidify.py:1047-1048`, `:1282`).
  `compare.py:1776-1783` then lets its own invented bottom cover them as interior. So a wrong
  classification ends in deletion, with no second check.

**Failure** (`probes/probe_underside_variants.py`, `probes/probe_underside_fascia_real_scale.py`).
The scene is review part 2's own `overhang_beside_a_slab`:
- L, a closed slab, z -8..0.
- B, a closed block overhanging open air.
- B's underside U is flush with L's top.

| Variant | What it adds | What ships |
|---|---|---|
| base (the regression test) | nothing | U ships whole, 1,600 sq in at z 0 |
| shaded | a roof box over B, so B's top sees no sky | U deleted, 1,600 sq in of invented floor at z -8, `passed` True at 240 x 160 and at 900 x 600 |
| tall | B 60 in tall | the same |
| fascia | a 3 in fascia quad hanging from U's free x = 80 edge | 40 in scale: U deleted at 240 x 160 (floor at z -3); refused at 900 x 600 (`covers_below_bottom`) and U ships. 400 in and 2000 in scale, 900 x 600: U deleted, 160,000 and 4,000,000 sq in of floor at z -3, `passed` True |
| shaded + a sign hung under the overhang (touching nothing) | a closed box, m1 | all 12 of the sign's faces deleted: 2 replaced as pieces of the invented bottom, 10 by the hidden pass |

In every failing run the cap guard's first round reads **0 failing pixels**. This is exactly
review part 2's C2: the brief ordered it fixed first. The fix covers only undersides whose block
is sky-seeing, no taller than 52.5 in, and has no own side hanging.

**Real files (unverified).** A has 21 continued regions processed as tops, and B has 16
(`undersides_not_tops` 78 of 99 and 7 of 23). Nothing in the run reports a real underside deleted
under its own invented bottom. The five regions the report measured (33, 467, 166, 244, 502) have
a sky-seeing slab 9.8 in above them. A shaded, tall or fascia'd underside among the others would
show up in no count.

**Fix:**
1. Decide on the evidence along the free edges:
   - A real underside has its block's sides STANDING UP along its free edges. In all three probes
     that is 120 of 120 in.
   - A real top has its slab's sides hanging, or nothing (the broken case).
   - Weigh the standing length against the hanging length, instead of letting one hanging row
     of 2 in or more decide.
2. For the surface met above, accept one within the standing sides' own measured height (the
   block's height), not only a sky-seeing one within 52.5 in.
3. The rule must still separate these fixtures: review M2's fixture (a riser along 40 of 120 in,
   which is a top), the open-landing variant (M2 below), region 33, and the three probes.
4. Pin the shaded, tall and fascia variants as tests at 2000 in.
5. As a safety net that can be measured on A and B, report and refuse any case where the hidden
   pass deletes faces of a no-sky continued region that were exposed on the input, under that
   region's own invented bottom. That is C2's exact signature.

---

## Important

### I1. Rule 6 makes a wrong slab volume authorise itself for everything seen through it

**Where:**
- `engine/guard/compare.py:1786-1804` and `:1350-1391`. Rule 6 allows a pixel whose ray enters a
  kept new face from outside and leaves through another kept new face, provided the path between
  them is `INTERIOR_INSIDE`.
- That path is judged by `_interior_test` (`solidify.py:1620-1667`, ANY region's planned volume,
  `:1658`). This is the same plan that built the faces (`solidify.py:1239`, `:1251`, `:1253`).
- Rule 5 already trusted the plan for what lies INSIDE the volume. Rule 6 extends that trust to
  whatever lies BEHIND it, outside every slab.
- The only thing that used to catch a wrong volume was the guard seeing geometry outside the slab
  through it. Review part 2's I2 note: "the guard therefore catches this only when something
  outside the footprint shows through".

**Failure** (`probes/probe_rule6_post_beyond_the_overhang.py`). The scene is C1's shaded overhang
plus a post: a closed box beyond the overhang (y 50..51, z -6..-2), outside every slab, seen from
-y through the open air under U. The same commit was run twice, once with `_through_closed_shell`
monkeypatched to allow nothing:

| At 900 x 600 | Walls kept | Wall faces refused | U | Floor at z -8 | Round 0 |
|---|---|---|---|---|---|
| rule 6 off | 0 of 3 | 6, `covers_outside_footprint` | ships, 1,600 sq in | 1,600 | 15,139 failing px |
| rule 6 on (as committed) | 3 of 3 | 0 | **deleted** | 1,600 | 0 failing, **15,139 `through_shell_px`** |

The result is the same at 240 x 160 (1,030 px). All the pixels that caught the wrong plan became
rule-6 pixels.

**Answers to the brief's questions:**
- **Can rule 6 hide real exterior geometry?** Yes, wherever the plan closes a gap that should stay
  open. The rule checks the path only against the plan itself, so it cannot tell a missing side
  from an opening.
- **Does the joint judgement accept faces that would each have been refused?** Yes, by design.
  In the probe, six faces each refused alone for covering something visible outside every slab
  are accepted together.
- **When the volume is right, rule 6 is sound.** A solid slab does hide what lies behind it (see
  "Checked and found sound").
- **The open-landing case (M2)** shows the same thing on a sky-seeing top. A wall built inside the
  real slab is kept on 4,702 rule-6 pixels.

**Fix:**
1. Allow rule 6 only through shells whose volume is confirmed independently of the guard:
   - a sky-seeing top (or a block standing on one);
   - its depth taken from its own measured sides;
   - not a no-sky continued region, not a fallback height, and not a lower surface deeper than
     its sides plus the band (the report already lists those).

   Every other shell keeps the per-face refusal. By reading, `slab_beside_a_lower_top`, the case
   item 1 was written for, would still pass: the plate is a sky-seeing top with measured 8 in
   skirts.
2. Measure what rule 6 hides, as the project's rules require. Per run, report the distinct
   original faces outside every volume whose pixels only rule 6 allowed, with their input
   exposure.
3. Never let the hidden pass delete a face outside every volume whose last exposure was taken by
   rule-6 pixels.

### I2. "One new face per footprint" refuses a wall that only partly overlaps another: a step loses its lower side (regression from 3561127)

**Where:**
- `solidify.py:1731-1733`. A new face is refused when it lies on ANY earlier new face of another
  group. This applies to walls as well as bottoms.
- `_Planes.lying_on` (`:1685-1707`) counts opposite windings (`|cos|`, `:1694-1695`) and any
  overlap above 0.1 % (`:1705`).
- The refusal is reported as `coincides_with_existing_face`, although the face it lies on is a new
  one, and only part of it overlaps.

**Failure** (`probes/probe_step_between_two_slabs.py`). A is a slab with its top at z 0, 8 in
deep. B sits beside it, top at -4, 8 in deep. Both lost the side between them at x = 40. The
shipped plane x = 40, by height band:

| Band | dc24e9a | 8c729c1 (the commit before) |
|---|---|---|
| z -4..0, A's riser | 160 of 160 | 160 |
| z -8..-4, the interface | 160 | 320 (two layers, enclosed between the two solids, not visible) |
| **z -12..-8, B's side below A** | **0 of 160** | 160 |

- **At dc24e9a:** B's wall is refused whole (2 faces), so the band under A's bottom is open again,
  exactly as the export left it. `passed` True.
- **At 8c729c1:** the step was closed, and its double layer lay inside the solid.

**Real files (unverified).** B's z-fight ties fell 46 -> 0 with this commit. The report's
"coincides" refusals (A 9 wall faces, B 18) may include steps like this one; nobody traced them.

**Fix:**
- Build the later wall only over the part of its side that no earlier wall covers. The `built`
  coverage that `_wall_pieces` already computes gives that part; here it is z -12..-8.
- Or refuse a new face only when it lies WITHIN an earlier one, not when it merely overlaps.
- Report this refusal under its own reason.
- Add the step as a test.

### I3. "A piece belongs to the slab" (01cc420) is judged in the side's 2-D frame and only for walls

**Where:**
- `solidify.py:644-666`, `_attached`. Distances are measured between polygons projected into the
  side's (u, v) frame (`:750-755`), and to two lines: the top edge and the wall's PLANNED foot
  (`:793-797`). How far in front of the side a face stands, anywhere within the 2.5 in band, is
  ignored.
- `_bottom_pieces` (`:867-888`) has no belonging test and no material test at all.
- `_side_looks` / `_wall_look` (`:1174-1175`) pick the wall's material from the candidate pieces
  BEFORE the cap guard (`:1285`) decides which pieces are really replaced.

**Failures** (`probes/probe_piece_attachment.py`, run at dc24e9a and at 3561127;
`probes/probe_bottom_piece_belonging.py`). All are at the default 900 x 600 guard, with
`cap_guard_passed` True.

**(a) An object touching a piece in projection is still deleted.** Scene "B tooth": a side missing
all but one tooth, plus a sign in the same material, 1.2 in in front of the tooth. Only their
projections overlap. At 2000 in, the tooth and **one of the sign's two triangles** are replaced,
exactly as at 3561127. So review part 2's I1 failure 2 survives for an object near a piece.

**(b) Bottoms never got the rule.** Scene: a slab with no bottom, and a "lamp" (a closed box,
m1) hanging 2 in BELOW the bottom plane and touching nothing. At both 40 in and 2000 in, **the
lamp's top face is replaced as a piece of the new bottom**, and the lamp ships open.

**(c) A real piece in the middle of a side is no longer a piece (regression).** Scene "C row": the
x = 0 side keeps only its middle strip (z -6..-2, full length). The strip touches neither the top
edge nor the foot, so it is not attached. The wall over the whole side then lies on it and is
refused (`coincides_with_existing_face`, 2 faces). How much of the x = 0 plane is covered:

| Scale | dc24e9a | 3561127 |
|---|---|---|
| 2000 in | 8,000 of 16,000 sq in | 16,000 (the strip replaced, the side closed) |
| 40 in | 160 of 320 | 320 |

**(d) The wall keeps the look of a piece the guard gave back.** Scene "A foot": the side is wholly
missing, and a sign (m1) 1.2 in in front of it reaches 2 in below the slab. Because its projection
crosses the planned foot, it is a candidate, and it is the only one, so the wall takes m1. The
guard then gives the sign back, because its lower part below the wall shows. **At 2000 in, the
16,000 sq in wall leaves solidify in the sign's m1**; at 3561127 it was in the top's m0. At 40 in
the one kept wall face is m1 too. No later pass changes a face's material.

**Fix:**
1. Judge attachment in 3-D: a shared edge or vertex, or the triangles themselves within `touch`,
   not their projections. Anchor to the foot only where the foot is a real edge (a lower surface,
   or an existing side's foot).
2. Give `_bottom_pieces` the same belonging test and material test.
3. Treat a face lying IN the side plane (|s| <= tol) inside the window as a piece, whatever it
   touches. Otherwise build the wall around it; do not refuse the wall whole.
4. Take the wall's look from the pieces the guard actually replaced (decide it after the guard).
   If there are none, take the neighbouring walls' look or the top's.
5. Add (a), (b), (c) and (d) as tests.

---

## Minor

**M1. `_refuse_together` refuses a new face where its docstring says the replaced piece is
restored** (`compare.py:1431-1440`).
- The first lost rule-6 pixel over a removed piece restores that piece.
- A second pixel over the same piece, or over a piece the main loop already chose to restore this
  round, falls through to `elif f not in refused` and **refuses the new face**.
- The main loop's rule (`compare.py:1809-1813`) and the docstring (`:1398-1401`) both say the face
  is kept.
- **Probe** (`probes/probe_refuse_together_piece.py`, the unit test's own scene):
  - one pixel: `(0, [2, 3], [7])`;
  - two pixels: `(1, [0, 2, 3], [7])`;
  - the piece already being restored: `(1, [0, 2, 3], [7])`.
- **Effect:** a new face is refused, its group gives its pieces back, and 3561127's rule then
  cascades. That is a missed rebuild, not damage.
- **Fix:** for a removed piece always `restore.add(x)` and never refuse `f`.

**M2. A real top under a landing with no underside is taken for an underside: review part 2's M2
returns.**
- **Probe** (`probes/probe_top_under_an_open_landing.py`): the M2 regression fixture, with only
  the landing's underside removed. That is the files' usual state; the solidify docstring calls
  them "a top sheet with partial skirts and almost no bottom".
- The rays go up through the open landing and meet its TOP, which sees sky, 20 in up.
- **Result:**
  - `undersides_not_tops` 1;
  - no bottom under R (0 of 1,600 sq in; 1,600 with the fixture's closed landing);
  - a wall is built at x = 40 **inside the real slab**, and rule 6 keeps it (4,702
    `through_shell_px`);
  - `passed` True.
- c2b1611 raised the reach from 38.5 to 52.5 in, which widens this case.
- **Fix:** the C1 evidence rule, plus this probe as a test.

**M3. Tests that do not pin the mechanism they are named for** (`probes/probe_mutations.py`,
`probes/probe_sign_test_before_fix.py`).
- `test_a_shell_is_refused_together_when_one_of_its_faces_fails` (`test_solidify.py:1285-1304`)
  **passes** both with `_refuse_together` a no-op and with rule 6 off. It forces the wall out
  before any pixel is judged (`refused_before`). Only the guard unit test
  (`test_guard.py:2039-2082`) pins the same-round re-cast. (The through-shell plate test and the
  railing test do fail when rule 6 is off.)
- `test_a_fin_below_the_slab_is_still_refused_face_by_face` (`test_solidify.py:1307-1323`)
  **passes** with rule 6's path check removed (`probes/probe_mutation_path_check.py`). The fins
  are refused for other pixels anyway. So the check its docstring describes is pinned only by the
  guard unit test (`test_guard.py:2006-2036`).
- `test_a_sign_standing_in_front_of_a_missing_side_is_never_a_piece[40.0]`
  (`test_solidify.py:1499-1511`) passes at 3561127, before its fix. Only the 2000 in case fails
  there.
- No test covers C1's three variants, I2, I3, or M2.
- **Fix:** give the "refused together" test a real round-0 refusal, so that `_refuse_together`
  has records to work on. Drop or re-aim the 40 in case.

**M4. `max_thickness` 50 in is backed by these two files, fitted with 0.79 in to spare, and it
also sets `_is_underside`'s reach** (`pipeline.py:114-127`; `solidify.py:990`).
- **The measurement does justify at least 49.21 in.** The docstring, the commit and the report
  agree: A 84.8 / 9.9 / 0.4 / 4.4 % at 9.84 / 29.52 / 39.37 / 49.21 in, B 72.0 % to 10 in and
  13.0 % at 36.26-39.37 in, and the deepest slab is A 852.
- **50 in is 0.79 in above that slab**, so the next LittleTiles step (59.05 in) would be clamped.
- **The same constant sets `_is_underside`'s reach** (52.5 in), which C1 and M2 depend on.
- **"Still clamping" B 820's 51.67 in run is not a benefit.** Read from the code, not probed: a
  broken side that deep gets a wall 1.67 in short of its own foot (`solidify.py:1056-1057`,
  `:1193`), so its pieces are given back.
- **Fix:**
  - give the reach a constant of its own;
  - clamp each wall to its region's representative depth plus the band, keeping the ceiling only
    as a sanity bound;
  - report the walls the ceiling clamps.

**M5. Docstrings that no longer match:**
- **`_underside`** (`solidify.py:1437-1441`) still justifies searching past `h`: "a slab that is
  thicker in the middle than at its rim ... invents a second bottom ABOVE the real one". Since
  9f64ae9 and 444d0ef it does exactly that. `probes/probe_thicker_in_the_middle.py` uses a closed
  slab with a rim bottom at -8 and a middle at -12:
  - at e27eb79: `bottom_exists 1`, nothing invented;
  - at dc24e9a: `bottom_exists 0`, and a bottom is invented at -8 across the whole footprint. It
    replaces the rim ring (input faces 10-17). In the middle it lies inside the solid, 4 in above
    the real underside.

  Nothing visible changes here, but the rationale is wrong. The slab's volume also stops at
  `bottom_h`, 4 in short of the real underside in the middle (`solidify.py:1253`).
- **`_is_underside`** (`:310`): "(29.6 in, 8 in)". Region 33's neighbour side is 29.52 in DEEP;
  29.6 in is its length (report section 3). The overhang's 8 in is a depth.
- **`test_a_side_deeper_than_any_slab_of_the_files_is_still_clamped`** (`test_solidify.py:1347-1348`):
  "deeper than any own side either file has but one 39.4 in run". A 60 in skirt is deeper than
  every own side, including that run, which is 51.67 in deep over 39.4 in.
- **`INTERFACE_HULL_FRACTION`** (`:143-148`) says the four regions 115, 134, 147 and 148 "lie
  0.99-1.00 inside". The engine takes 3 of them, with 134 sitting at the bar (report section 6).
  Say which (unverified).
- **The session record's cap-guard cell** (`2026-09-24-session-record.md:49`, updated in
  dc24e9a):
  - it still omits rule 1 (background covered unmeasured), as review part 2's M4 noted;
  - it paraphrases rule 6 as a face "seen only through" a closed slab, but rule 6 is per pixel,
    not "only".
- **The refusal reason `coincides_with_existing_face`** is also used for a new face lying on a new
  face (I2).

**M6. Item 6 cannot tell a block standing on a slab from an overhang over a notch or hole whose
sides the export lost** (`solidify.py:1018-1036`).
- The three tests (a measured depth, no own side along the shared edges, 99 % inside the top's
  convex hull) read nothing that differs between the two. A convex hull contains the notch of a
  U-shaped top, and the hole of a ring-shaped one, by construction.
- `probes/probe_block_or_overhang.py` runs the `at_edge` fixture itself: the block's underside is
  **deleted** by the hidden pass, and 400 sq in of bottom fills the notch. For a block, that is
  right. For a real overhang in the same shape, it is C1's damage.
- It is counted (`blocks_standing_on_slabs`, A 0 / B 3), which is good.
- **Fix:** keep the counter in every report summary, show B's three regions to the owner, and pin
  the ambiguity with a test, so that a future change to the rule has to say which reading it
  chose.

---

## Checked and found sound

**Rule 6's mechanics, given a correct volume** (9f64ae9):
- The entry face must be met on its front and the exit face on its back (`compare.py:1368`,
  `:1377`).
- The exit must lie before BEFORE's hit (`length < gap`). BEFORE is the whole input, so the path
  never crosses an original face.
- Every one of 3 to 32 samples must be inside a volume. The guard unit test fails when the path
  check is removed (the author's mutation, re-run here: `probes/probe_mutation_path_check.py`).
  The solidify-level fin test does not fail (M3).
- The re-cast in `_refuse_together` is exact against the reduced shell (its unit test).
- The verification round runs rule 6 too, so `cap_guard_passed` still describes the returned
  state.
- `through_shell_px` is recorded per round.
- `_SHELL_LIFT` (1e-3 in) is 16 times float32 noise at 1,000 in from the centre.

**The rewritten railing test is not weaker** (`test_solidify.py:698-735`). It pins
`changed_elsewhere == 0` for every pixel whose line of sight does not cross the slab's box, and it
fails with rule 6 off. So does `test_a_top_edge_that_ran_into_an_underside_only_is_a_side`.

**170141f (M1) is exact** (`probes/probe_crack_across.py`, the suite's own crack scene):
- A crack along x at slope 0.4 passes up to 0.161 in (0.1495 across) and fails from 0.162 in
  (0.1504 across), at a tolerance of 0.15. This confirms the commit's "0.16 -> 0.149 passes; 0.20
  fails".
- What shows through must be the sky or an exposed side.
- The change to the 0.02 in test follows a changed requirement, not a weakening.

**3561127's present-piece loop** (`compare.py:1677-1695`):
- It terminates, because `keep` only ever turns False.
- It runs before every round and before the verification.
- The three probes of review part 2's C1 are regression tests, and the double-bottom test pins
  `coincides_with_existing_face >= 2`.

**444d0ef:**
- `_sides_end_on` and `_ends_here` do what their docstrings say.
- Whole sides are never extended to a lower surface (`solidify.py:773-780`).
- Review part 2's I2 probe is a regression test: the bench and L's top ship.
- `lower_surface_deeper_than_sides` is reported.

**eb920df and c56018d:**
- `_planned` reports replaced pieces.
- `slab_beside_a_lower_top` pins what `fix_object` ships.
- The CLI's FAILED-copy wording matches `_write_skp` (`cli.py:361-410`).
- The docstrings of `cover_max_exposure` and `solidify_feedback` are right.

**The docstring numbers of max_thickness, `_representative_depth`, `_lower_surface` and the
`lower_surface_deeper_than_sides` comment** match the report.

**Determinism** (`probes/probe_determinism.py`):
- Four scenes, taking the rule-6, re-cast, block-on-slab and given-back-piece paths, each ran
  twice in one process, and the process was run twice.
- The hashes of the shipped mesh plus the reports (runtime removed) were identical in all four
  runs: `91fb457a..`, `8246c36d..`, `82c75419..`, `b1114c68..`.
- The new code orders every set and dict it iterates over (`sorted(...)`, and insertion order
  over ordered ids).

**The regression tests the brief asked for exist, and pin shipped behaviour:**
- R2-C1: three tests;
- R2-C2: the base case;
- review part 2's M2: the closed landing;
- R2-I1: material, and the sign at 2000 in;
- R2-I2: the bench;
- item 6: two tests.

## The author's concerns, re-checked

| Concern (report section 14) | Result |
|---|---|
| 1. A's owner `.skp` is stale (Errno 13) | Not code; not checked |
| 2. A's back faces 21,553 against 20,945 | Consistent with 8c729c1 taking 467 for an underside; not re-measured |
| 3. B1 only partly fixed; 134 sits at the hull bar | Consistent; M6 adds the ambiguity the other way round |
| 4. A2, item 7, B4 and B8 not fixed | Not re-checked |
| 5. Rule 6 covers what lies outside every slab | **Confirmed as a real risk: I1**, with a probe. It is sound only as far as the plan is |
| 6. Tests changed with the requirements | Railing: not weakened (mutation-checked). 0.02 in crack: the requirement changed. SR6's plan tests now go through the guard. But see M3 for the "refused together" test |
| 7. The session record's cap-guard cell | Updated in dc24e9a; still omits rule 1 (M5) |
| 8. Item 9 untouched | No reviewed commit touches it |

## Probe scripts in `probes/`

| Script (output) | Shows |
|---|---|
| `common.py` | helpers: boxes, the shipped area at a height, a face's fate, and rule 6 switched off |
| `probe_underside_variants.py` (`out_underside_variants.txt`) | C1: base, shaded, tall, fascia, and a sign under the overhang, at 240 x 160 and 900 x 600 |
| `probe_underside_fascia_real_scale.py` (`out_underside_fascia_real_scale.txt`) | C1: the fascia at 40, 400 and 2000 in |
| `probe_rule6_post_beyond_the_overhang.py` (`out_rule6_post.txt`) | I1: rule 6 off against on |
| `probe_step_between_two_slabs.py` (`out_step.txt`) | I2, at dc24e9a and 8c729c1 |
| `probe_piece_attachment.py` (`out_piece_attachment.txt`, `out_piece_attachment_at_3561127.txt`) | I3 (a), (c), (d). "A ground" is a control that 01cc420 did fix: a sign standing on a ground plate at the foot has one triangle replaced at 3561127 and none at dc24e9a |
| `probe_bottom_piece_belonging.py` (`out_bottom_piece_belonging.txt`) | I3 (b) |
| `probe_refuse_together_piece.py` (`out_refuse_together_piece.txt`) | M1 |
| `probe_top_under_an_open_landing.py` (`out_top_under_open_landing.txt`) | M2 |
| `probe_mutations.py` (`out_mutations.txt`), `probe_mutation_path_check.py` (`out_mutation_path_check.txt`), `probe_sign_test_before_fix.py` (`out_sign_test_before_fix.txt`) | M3 |
| `probe_thicker_in_the_middle.py` (`out_thicker_in_the_middle.txt`), `probe_thicker_detail.py` | M5, `_underside`'s rationale (the ring's faces 10-17 are replaced) |
| `probe_block_or_overhang.py` (`out_block_or_overhang.txt`) | M6 |
| `probe_crack_across.py` (`out_crack_across.txt`) | 170141f is exact |
| `probe_determinism.py` (`out_determinism_1.txt`, `out_determinism_2.txt`) | determinism |

The suite's own output is in `pytest-full.log`, beside this file.
