---
name: uc-repair-rules
description: Use before writing or reviewing ANY change to the UC MODEL FIXER engine (engine/fixes, engine/guard, engine/campus, engine/validate, engine/detectors) — the pre-flight checklist against the binding rules, the blocked operations and the owner's strict "nothing visible deleted" rule.
---

# UC repair rules — pre-flight checklist

The rules are in `AGENTS.md`:
- §3 binding rules;
- §4 blocked operations and the two owner exceptions;
- §5 owner decisions;
- §6 the owner's validation rule.

This checklist makes you apply them before the first line of code, and again before you hand in.

## Before you start

1. **Blocked operations (§4).** Could this change come near one? Tolerance weld, interior-face
   selection, generic hole fill, Make Manifold, Decimate or remesh, dissolve above 5°, opposite pairs
   treated as duplicates, a whole-campus job.
   - If yes, stop and ask the controller (Claude) or the owner.
2. **Guards.** Does it change what a guard tolerates (`engine/guard/**`, `FixProfile` thresholds, an
   invariant)?
   - Then the change must be named and MEASURED, test-first, and stated in the report.
   - Never argue a guard looser.
3. **Vertices.** Does it invent or move a vertex?
   - Only `engine/fixes/solidify.py` may invent vertices.
   - The E5 cut may add points only on the winning face's border.
   - The E8 flat fill uses existing points only.
4. **The owner's visible rule (§5, §6).** Could anything visible be deleted or covered, from outside or
   from eye height inside a floor?
   - Then it is not allowed: list it with a picture instead.
5. **Inputs.**
   - Only frozen snapshots under `data/`.
   - Never the live export folder, except through `engine/io/snapshot.py`.
   - Never the CHECKPOINT-17 master.
   - The backup only as a verified copy.
6. **Tests.** Which test fails today and passes after your change? Write it first and see it fail.

## Before you hand in

- The full suite of the area you touched is green (paste the counts).
- If the change affects geometry, run the Validator on a golden unit (CHTM 5th floor and the sidewalks)
  and paste its verdict.
- Your report lists every rule from §3-6 that the change touches, and the measurement for each.
