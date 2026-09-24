# Brief 06 — smaller leftovers found on the way (pick any; one commit each, test-first)

Measured, with where they were found. Mark each done in the ledger.

Engine, file B:
1. Region 74 (346 triangles) merges but draws as 17 triangles: rule 3 excludes 4 overlapping
   triangles (OBJ lines 11185, 11342, 11371, 11372), cutting a 6.1 sq in island off the region.
   (merge-new-vertex-report.md)
2. Region 79: two original triangles (OBJ 10834, 11402) folded onto the same side of their shared
   edge, 47.7 sq in covered twice; excluded whole by rule 3. A fold detector/fixer is missing.
3. Region 38: a solidify wall laid over an existing side face (solidify took the side's top edge,
   used by one face only, for an open edge). Should be fixed by the side rebuild; verify.
4. `zfight_tie` went 0 -> 2 pixels after b3b9ad3; cause not investigated.

Engine, both files:
5. Different-material overlaps (file B) are only reported; the owner's "which face wins" preference
   step is not built. Needs the owner's rule.
6. The guard never checks growth over background (a pixel where BEFORE saw background and AFTER sees
   a surface is classed OK); only the merge's area rule limits it. (border-shift-report.md)
7. `report.json` has `border_shift` only in the totals, not per view (one line in `engine/cli.py`).
8. The CLI never deletes stale `guard_fail_*.png` from earlier runs in the output folder.

SketchUp file:
9. Regions more than about 1e-3 in off their plane are written as soft-edged triangles, because
   SketchUp splits such polygons with hard edges (19 regions on A, 9 on B). Option to decide:
   flatten within half the print precision for the `.skp` only (vertices are shared, so check the
   neighbours stay planar).
10. Edges a wall stands on are never hidden (12 on A, 2 on B); coplanar pairs wound against each
    other are set soft but not smooth (15 on A, 1 on B); four edges along a 0.19 in sliver hole on A
    stay drawn. (skp-export-report.md, section S1)
11. Texture orientation in the SketchUp GUI is unverified; one face on A has collinear UVs in the
    export itself.

Process:
12. Review diff packages under `.superpowers/sdd/**/review-*.diff` are not versioned (large);
    regenerate from git when needed.
