# Brief 10 — side rebuild follow-ups (after the merge, brief 03)

Source: the SR6 section of `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/side-rebuild-report.md`
(on branch feat/side-rebuild, commit fafd4d6; after brief 03 it is on feat-dashboard). The side
rebuild works: the owner's ramp (file B region 309) went from 43,696 back pixels in its close-up to
948, file A 876 triangles, file B 486, back faces from outside A 20,793 / B 6,006, no rollback. These
are the known gaps it reported. Main checkout, test-first, one commit per item.

1. **The cap guard judges a needed wall and its bottom separately, so each blocks the other.** Each
   new face is judged against a mesh without the other new faces, so a wall is refused because the
   bottom's opening shows the inside, and the bottom because the wall's opening does
   (`slab_beside_a_lower_top`: all 2 wall and 2 bottom faces refused, nothing kept). Judge a region's
   new shell together (walls and bottom as one candidate set, refused together only when the set
   fails), keeping the per-face refusal for faces outside the region's volume. Three tests now check
   the plan with the guard bypassed (the rewritten SR5 test, the floor test, the underside-edge test);
   make them go through the guard.
2. **`max_thickness` (36 in) is below the files' 39.37 in blocks** (B region 92's walls and bottom stop
   at 36 in). Set it from the measured distribution of own-side depths on both files, with a stated
   ceiling.
3. **The underside test misses undersides with a small hanging side** (A regions 467, 166, 244; 98 of
   region 467's 121 bottom faces refused). Find a rule that separates real tops (A 9, 784 at
   thickness ratios 3.5 and 4.2) from undersides (region 33 at 22.9 has the same 29.52 in thickness);
   state it with the measurements.
4. **Measures that got worse than at 0f24da4** (reference back px A 266,112 -> 454,537; wall faces
   refused A 157 -> 392; bottom faces refused A 108 -> 230, B 40 -> 61; B z-fight tie px 3 -> 39,
   tolerated; B pieces restored 3 -> 14; B T-junction lines 24 -> 33): explain each after items 1-3,
   fix what is a defect.
5. The small back-facing piece left at the upper-left end of the ramp close-up
   (`B_sr6_ramp_teeth_v0.png`), and the ramp's view 1 at 2,674 back pixels (target about 2,500).

## Added after the merge (brief 03 report, `reconcile-side-rebuild-report.md`, 2026-09-25 10:55)

6. **What the renders still show wrong** (after the merge, owner's files at 08:50-08:52): file B's
   middle slabs look like trays from below; B's sloped slab hangs a stepped fin; panels hang at
   different depths with a see-through slot under B's upper-left landing; clutter along A's
   big-landing edge; step lines on A's undersides. Find each on the real files (close-ups), say which
   are side-rebuild gaps (items 1-3) and fix those; list the rest with their cause.
7. **Lines inside flat surfaces on A rose from 8 to 17** after the merge (shorter in total: 20.3 ft
   against 48.8 ft); three of the six longest lie along x = 2673.2. Trace them.
8. **Sliver 3491 on A** is a new removal after the merge (the rays confirm it); say why it became a
   candidate.
9. Not for this brief without the owner's decision: file A ships two copies of the same surface
   stacked with opposite windings on its lower landing at z 1612.2 (from the export; they z-fight in
   Unity). The project's blocked-operation rule forbids treating opposite-normal coincident pairs as
   duplicates, so removing one needs the owner's explicit OK.

Finish as brief 03 (both runs, audit, close-ups of the ramp and B region 92 read), report
`side-rebuild-followups-report.md`.
