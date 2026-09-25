# Brief 15 — one wall per side plane where the export drew a side twice (no flicker in Unity)

Source: brief 14's report, `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/zfight-sources-report.md`
(branch `feat/coincident-pairs`, commit 9f39e7f), with its scripts in
`docs/superpowers/records/scripts/brief14/`.

The owner's goal (2026-09-25 21:45) is **no flicker in Unity**. The measurements at 281a569:
- **A:** 28 double-layer sources, 3,723.5 sq in, 10 of them opposite-wound, 141 px in the 26 guard
  views.
- **B:** 2 sources, 49.3 sq in, 7 px.

Every source is a PARTIAL overlap of two layers that the export already draws, mostly sides drawn twice
in pieces. The merge adds none. Seven of A's opposite pairs are same-wound in the export: the per-face
flip turned one layer and not the other. The guard's `zfight_tie` counts none of this, because it only
sees pixels whose winning face changed between the reference and the shipped mesh.

Where: after brief 11 lands, because brief 11 owns `engine/fixes/solidify.py`. Start from brief 11's
final commit. Test-first, one commit per item, stage by name. Real runs go to their own `--out` and
`--skp-dir` folders.

## Items

1. **Every run reports what can still flicker.** Add brief 14's measurement to `report.json`:
   `double_layers` with the count, the area, the pixels over the 26 views, and a per-plane list. Do it
   test-first, and keep it cheap enough for every run.
2. **One wall per side plane.** In solidify's side rebuild, where a side plane of a slab carries
   overlapping pieces of that slab, replace them with ONE wall over their union.
   - The pieces can overlap partially and have any winding.
   - The wall is wound outward by exposure and keeps the pieces' material. Pieces of different
     materials are kept and reported.
   - The pieces must belong to the slab in 3-D (review R10-I3).
   - Where the union needs no new vertex, do it. Brief 14 measured 9 of A's 14 source planes like
     that, carrying 95% of the area and 95 of the 141 px. They include the lower-landing walls
     (3,439 sq in, 56 px; the largest is 1,307 sq in at x 1275.6) and the riser at x 1305.14 (a
     19.7 x 19.7 in square whose four corners exist).
   - Where the union needs new vertices, solidify may add them only under its existing rules: measure
     and report.
   - The guard is not loosened. Never delete a side without the wall that replaces it.
3. **Finish.**
   - Suite count.
   - Both real runs, with `double_layers` before and after (target: 0 on every replaced plane), back
     faces, triangles, every guard total, invariants and passed.
   - The SketchUp audit.
   - Close-ups of the lower-landing walls and the riser, before and after, read and described.
   - Report: `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/one-wall-per-side-plane-report.md`.

Not in this brief:
- flipping overlapping layers together;
- the plane-cover rule (6.0 sq in on A);
- dropping exact same-wound triangles after the merge (24.6 sq in).

Brief 14 measured all three. Each is a wider rule, and none is needed if item 2 lands.
