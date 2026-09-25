# Brief 13 — one copy of an exactly stacked, opposite-wound, same-material surface (owner's decision)

**The owner's decision (2026-09-25 21:45, in the session):** the stacked copies may be removed "so that
it won't flick in Unity". Before this, brief 10 item 9 recorded it as waiting for the owner. File A
ships two copies of the same surface, stacked with opposite windings, on its lower landing at z 1612.2
(from the export). Unity draws both with the double-sided campus shader (`CampusDoubleSided.cs`,
`_Cull = 0`), so they z-fight: they flicker.

Until now the project's blocked-operation rule, "never treat opposite-normal coincident pairs as
duplicates", kept both. It is enforced in two places:
- `engine/fixes/overlap.py`: a face goes only when its own region covers it, and an opposite-wound
  copy is its own region.
- `engine/fixes/orient.py` rule 3: "never a face another face lies ON".

The rule exists because such a pair can be a real two-sided surface with a different material on
each side. **That case stays protected.** The exception is exactly this and nothing wider.

## The rule to add

Reduce a pair to ONE face only when all of these hold, each measured and not assumed:
1. **Exactly coincident.**
   - Same plane, within the print precision (0.001 in).
   - Each outline covers the other at least 0.99, both ways. A partial overlap is not a copy.
2. **Opposite windings.** Same-wound duplicates are already the overlap pass's job.
3. **The same material on both faces, and the same UV mapping modulo whole tiles.** Otherwise the look
   from one side would change, and a different-material pair keeps both faces, as before.
4. **Which one stays.** Keep the face whose FRONT faces the side the pair is seen from, by the
   original mesh's exposure. The owner checks in SketchUp, where a back face shows as a purple patch,
   and back pixels from outside must not go up. Seen from both sides: keep the one facing the larger
   exposure, and report it.
5. **Guard and report.**
   - The final guard still passes with no loosened tolerance. A double-sided render does not change
     except at the pair's z-fight tie pixels, which the guard already classes as `zfight_tie`.
   - Report every pair removed: face ids, area, plane, material, which side was kept and why.

The removed face is dropped whole, like every other removal. No vertex is moved or invented.

## Measure first, both files, at HEAD

Count every exactly coincident opposite-wound pair in the final output of A and B, by material
(same or different), with area and location. Confirm A's lower landing at z 1612.2 is among them, and
say whether B has any. Hold the counts against the export's own numbers, measured 2026-09-21 on the
input: A 11 exact duplicate faces, all opposite winding; B 31, all opposite winding, 24 of them with a
different front and back material.

## Tests (test-first; append fixtures at the END of `engine/tests/fixtures/build.py`)

- A slab plus an exactly coincident opposite-wound copy of its top, same material: one face per
  position remains. The kept one faces up (the exposed side). The guard passes.
- The same copy with a DIFFERENT material: both stay.
- A copy offset 0.01 in, or covering only half: both stay.
- A copy with the same material but UVs shifted by half a tile: both stay.
- For each test, name the change that would make it fail. Undo the fix once and see it fail.

## Finish

- Engine suite. Both real runs, with their OWN folders so they do not overwrite brief 11's:
  - `--out "D:/PROJECTS/UC MODEL FIXER/data/out_b13"`
  - `--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch/b13"`
- Per file:
  - triangles, back faces input/reference/final, `zfight_tie` px, every guard total, invariants,
    passed;
  - the pairs removed and kept;
  - the SketchUp audit (`skp_edge_audit.py`) of the written `.skp`;
  - a close-up render of A's lower landing before and after, read and described.
- Report: `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/coincident-pairs-report.md`.
