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

## Finish

Suite; both real runs (they write the owner's `.skp` only when the run passes and the file is not open in
SketchUp); per file: triangles, back faces input/reference/final, sides and bottoms rebuilt, pieces replaced,
every guard total, invariants, passed; the SketchUp audit; close-ups before and after of A1, A2, B1 (region
107), B4, B8 and the ramp (must not regress), read and described. If SketchUp is open with the bridge,
also export the real SketchUp views with `sketchup_views.rb` for the file that is open. Report
`.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/remaining-visual-defects-report.md`.
