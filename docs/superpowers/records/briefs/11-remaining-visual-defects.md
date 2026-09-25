# Brief 11 — the defects still visible after brief 10

Source: brief 10's report `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/side-rebuild-followups-report.md`
(concerns and close-ups), the visual triage `docs/superpowers/records/visual-triage-2026-09-25.md`, and the
real SketchUp views of file A in `data/sketchup_views/A/` (exported through the SketchUp bridge with
`docs/superpowers/records/scripts/sketchup_views.rb`; back faces bright purple; X-ray).

Where: main checkout, branch `feat-dashboard` (HEAD after 4f84ccb; 566 tests). A read-only review of brief 10
runs in parallel on the committed state; its findings may be added to this brief. Test-first, one commit per
item with a body that says why, stage by name, append fixtures at the END of `engine/tests/fixtures/build.py`.
Current numbers: file A 917 triangles, back faces from outside 21,553 px; file B 506, 2,787 px; both passed.

## Items, in this order

1. **A's margin strip shows reversed cells (A1).** Along the big landing's east edge a thin strip of cells
   shows its back side from outside (A1 close-up view 0: 6,938 back px; five purple strips in the close-up).
   They are thin sheets (both sides exposed), which `engine/fixes/orient.py` never flips. Add a
   consistent-winding rule: within a connected sheet (faces sharing edges, near-coplanar), make the winding
   consistent, then orient the sheet as a whole so its more exposed side is the front; measure back pixels
   before and after; never flip a face the guard would see changing material or depth. Also brief 10 item 7:
   lines drawn inside surfaces where neighbouring faces are wound opposite ways.
2. **Broken undersides are kept, not rebuilt.** The real SketchUp views show the same class of problem as the
   broken sides: small tilted pieces, partial layers and stepped borders on the underside of a slab (A2:
   the stepped border between the rebuilt bottom and the export's own bottom on the lower landing). Extend the
   side rebuild to the bottom: when a slab's existing underside is broken (pieces within a band of the bottom
   plane, gaps, steps), build one clean bottom at the slab's own depth and replace the pieces, under the same
   measured guard rules (a piece must belong to the slab; nothing outside the slab's volume changes).
3. **B region 107 (B1) is only partly rebuilt**: 18 of 40 walls and 20 of 36 bottom faces kept, the rest
   refused as covering outside the footprint. Trace the refused faces to their pixels and say whether the
   refusals are right; fix what is wrong. Region 134 sits right at the 0.99 hull bar: say whether that bar is
   right with the measurements.
4. **B4** (notches and a tooth where the ramp meets the walkway) and **B8** (a knife-edge cantilever walkway
   in B's +X view): trace each to its cause and fix what is an engine defect; report what is in the export.

## Added from the review of brief 10 (2026-09-25 18:45; `review-brief10.md`, probes in `docs/superpowers/records/scripts/review10-probes/`) — do R10-C1 FIRST

- **R10-C1 (Critical) a real underside is still taken for a top** (`_is_underside`, `solidify.py:322-346`)
  when the block above does not see sky, when it is taller than 52.5 in, or when a fascia of 2 in or more
  hangs from one of its free edges: a bottom is invented under it, the hidden pass deletes the real
  underside, `passed = True` (probes `probe_underside_variants.py`, `probe_underside_fascia_real_scale.py`,
  `probe_block_or_overhang.py`; 1,600 sq in of invented floor 8 in low, a sign under the overhang deleted).
  Decide top versus underside by what the region's FRONT side faces (a surface facing down with the slab body
  above it is an underside whatever sees sky above), and never invent a bottom that covers a face whose
  original exposure shows it is seen from below.
- **R10-I1 rule 6 can hide real geometry** outside the slab when the planned volume is wrong
  (`probe_rule6_post_beyond_the_overhang.py`: a post behind a shaded overhang; rule 6 off: walls refused,
  15,139 failing px; rule 6 on: all counted as seen through a closed slab, the underside deleted). Bound rule 6
  by measurement independent of the plan (for example, the covered geometry must lie inside the slab's own
  measured volume from its original faces, not the planned one), or drop it if that cannot be done.
- **R10-I2 regression at steps** (`probe_step_between_two_slabs.py`): a new face lying partly on an earlier
  NEW face is refused whole, so the side band below the upper slab stays open (0 of 160 sq in; 8c729c1 closed
  it) and the reason reads `coincides_with_existing_face`. Coincidence must be tested against ORIGINAL faces
  only, and two new faces must be merged or trimmed, not refused.
- **R10-I3 "a piece belongs to the slab" is judged in 2-D and only for walls** (`probe_piece_attachment.py`,
  `probe_bottom_piece_belonging.py`): (a) an object 1.2 in in front of a piece whose projection touches it is
  still replaced; (b) bottoms have no belonging or material test (a lamp's top face 2 in below the bottom
  plane is replaced and the lamp ships open); (c) a real piece in the middle of a side (touching neither the
  top edge nor the foot) is no longer a piece, and the wall over it is refused (a regression from 3561127);
  (d) the wall takes the look of a candidate the guard later gives back. Fix all four in 3-D, for walls and
  bottoms, with the wall's look chosen after the guard.
- **Minors R10-M1..M6** as written in the review (M2: a real top under a landing with no underside taken
  for an underside; M3: tests that do not pin their mechanism, see `probe_mutations.py`; M4: max_thickness
  50 in fitted to these two files with 0.79 in to spare; M5: docstrings; M6: item 6 cannot tell a block on a
  slab from an overhang over a notch).
Every probe becomes a regression test that fails before the fix and passes after.

## Finish

Suite; both real runs (they write the owner's `.skp` only when the run passes and the file is not open in
SketchUp); per file: triangles, back faces input/reference/final, sides and bottoms rebuilt, pieces replaced,
every guard total, invariants, passed; the SketchUp audit; close-ups before and after of A1, A2, B1 (region
107), B4, B8 and the ramp (must not regress), read and described. If SketchUp is open with the bridge,
also export the real SketchUp views with `sketchup_views.rb` for the file that is open. Report
`.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/remaining-visual-defects-report.md`.
