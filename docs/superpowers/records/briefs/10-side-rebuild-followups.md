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

## Added from review part 2 (2026-09-25 12:10; `review-side-rebuild.md`, probes in `docs/superpowers/records/scripts/review2-side-rebuild/`) — do R2-C1 and R2-C2 FIRST

- **R2-C1 (Critical) the side rebuild makes its own z-fighting double layers.** The coincidence rule
  runs once, before the cap guard, and skips a wall's own pieces (`solidify.py:1368`); the guard can
  later give pieces back while keeping the wall faces lying on them (`compare.py:1418-1421`,
  `1446-1451`, `1514-1516`); and two coincident top regions each get their own bottom. Probes
  `probe_restored_piece_double_layer.py`, `probe_restored_piece_same_material.py`,
  `probe_double_bottom.py`: coplanar double layers of 21.3, 14.5 (at 2000 in scale) and 1,600 sq in
  ship with `passed = True`. Fix: when a piece is given back, give back (refuse) every new face lying
  on it; re-run the coincidence test after the guard's last round; one bottom per footprint however
  many coincident tops. Count the pieces given back because a wall lost a face (review M3).
- **R2-C2 (Critical) a real underside is still deleted.** The underside test treats a slab's
  underside as a top when a neighbour's side hangs along one of its edges (`solidify.py:773`); its
  invented bottom covers it through the shell exemption (`compare.py:1500-1507`); the hidden pass
  deletes the real underside and 1,600 sq in of invented floor ships 8 in lower, `passed = True`
  (`probe_underside_with_hanging_neighbour.py`; the suspects on A are regions 467, 166, 244). Fix:
  decide top versus underside by looking above AND below the region (sky above and the slab body
  below for a top), not by which sides hang; this also covers review M2
  (`probe_real_top_taken_for_underside.py`, a real top taken for an underside).
- **R2-I1 rule 4 replaces any face in the side band**: no check of material or of belonging to the
  slab, so a concrete side ships as a wall in the paving material and, at real scale, a sign standing
  1.2 in outside the slab is deleted as a piece (`probe_side_material.py`, `probe_object_in_band.py`).
  Fix: a piece must share the wall's material (the wall takes the replaced side's material, not the
  top's) and be connected to the slab's outline (edge-adjacent or within the band along the outline,
  not merely near its plane).
- **R2-I2 one deep own side lets the floor under an open slab become its "lower surface"** and rule 5
  then boxes in whatever stands there (`probe_lower_surface_floor.py`: a bench and the lower slab's
  top deleted, `passed = True`). Fix: accept a lower surface only when the slab's own sides reach it
  along a real, length-weighted share of the outline; never extend a side that is whole at its own
  depth; report every region whose walls or volume were set by a lower surface deeper than its
  representative depth plus `side_band`.
- **R2-M1** the opened-crack rule excuses a crack up to 2 x the border tolerance and never asks what
  shows through (`probe_opened_crack_width.py`): measure against AFTER triangles in BEFORE's own
  plane and material, require AFTER to show sky or an exposed side, pin a case between 0.15 and
  0.3 in. **R2-M4** stale docstrings (`solidify_feedback` "only faces are ADDED" and rule 2;
  `cover_max_exposure` "FRONT side"; `cli.py:12-13` "overwriting"; the session record's cap-guard
  cell). **R2-M5** two SR6 tests pin plans that never ship (`test_a_top_edge_that_ran_into_an_
  underside_only_is_a_side`, `_planned` reports no replaced pieces): test shipped behaviour.
Every probe above becomes a regression test that fails before the fix and passes after.

Finish as brief 03 (both runs, audit, close-ups of the ramp and B region 92 read), report
`side-rebuild-followups-report.md`.
