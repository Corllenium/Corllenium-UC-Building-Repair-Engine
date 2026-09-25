# Brief 14 — what can still flicker in Unity (after brief 13)

The owner's goal (2026-09-25 21:45) is "no flicker in Unity". Brief 13 found its premise gone at
281a569. A's z 1612.2 landing is already a single layer: the export's double layer there was
same-wound, and the hidden and fold passes remove it. The export's exact opposite-wound copies (A 11,
B 31) are all removed before the new rule's stage. So brief 13's rule, built and tested with 14 tests,
removes nothing on either file.

Two sources are still in A's output:
- An opposite-wound riser pair at x 1305.14, 48.27 sq in. It is a partial overlap (20% and 55% before
  the merge), with textures half a tile apart. Brief 13's rule rightly keeps it, and it z-fights.
- A same-wound duplicate at z 1779.53, 24.6 sq in, which survives the duplicate-layer pass.

B has none.

Where: the brief-13 agent continues, in the same worktree `.claude/worktrees/coincident` on branch
`feat/coincident-pairs`. Brief 13's rules apply.

1. **Measure every z-fight source** in A's and B's final output: any two faces whose outlines overlap
   within one plane by more than 1 sq in, same or opposite winding, any material. Give area, winding,
   material, UV offset and `zfight_tie` pixels, and trace each to the pass that makes or keeps it.
2. **The same-wound duplicate at z 1779.53.** Find out why the duplicate-layer pass keeps it. If that is
   a defect within the existing rules, fix it test-first. If it needs a wider rule, do not widen:
   write the rule and its measured effect for the owner.
3. **The riser pair at x 1305.14.** Find what makes the partial overlap. If the merge makes it, fix it
   there. If solidify's side rebuild should replace it with one wall, do NOT edit
   `engine/fixes/solidify.py`, which brief 11 is changing: write the exact change down for the next
   brief.
4. **Finish:**
   - suite count;
   - both real runs, with `zfight_tie` before and after;
   - close-ups of each fixed spot, read and described;
   - report at `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/zfight-sources-report.md`.
