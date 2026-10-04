# Task 15 (P0-15): the implementer's report (handed back as text, recorded by the controller) and the controller's rulings

Status: DONE_WITH_CONCERNS. Branch `claude/P0-15`, worktree `.claude/worktrees/P0-15`, 10 commits on 7211b82, HEAD ef23d13.
Raw outputs: `<session scratchpad>/p0-15/`.

## Commits
- 5197052: reversed floors get probes, under a lid (carried 1, 6).
- caa81c2: `check_caster` compares faces; viewpoints must be (k, 3); face ids checked (carried 2-4).
- b92fc14: two P0-14 mutants now die (carried 5).
- 369d763: look keys, print step, depth tolerance, texture sizes, face fingerprints.
- eb67ca5: checks 1, 2, 3.
- 9d19bf9: evidence crops.
- 7d573ad: the `validate` command (the step-5 message).
- 1747ad6: `validate` reuses the reader's peak-memory helper, so `cli.py` binds no ctypes; v0 no-allowed-classes test.
- 7c415a3: docs.
- ef23d13: barycentric weights as area ratios. This fixed a false UV failure on a sliver, found by the identity sweep.

**Files:** new `engine/validate/checks.py`, `evidence.py`, `engine/tests/test_validate_checks.py` (50). Edited: `viewpoints.py`, `visibility.py`, `sampling.py`, `validate/__init__.py`, `engine/cli.py`. In `test_validate_core.py`: one import-line addition plus appended tests.

## Tests
- validate_core 59 + validate_checks 50 = 109 passed.
- Full suite at ef23d13: 945 passed, 1 xfailed.

**Carried items** (first run 6 failed / 53 passed, then 59 passed):
1. **Reversed floors** (deviation, concern 1): a downward face is ground only if its headroom ray ENDS on a surface (a lid).
   - CHTM 5th probes 1,397 → 1,403 (+6, 0 lost).
   - All 87 snapshots: 122,526 → 124,116; 0 cells lose a probe, 1,590 gain one.
2. `check_caster`: red then green.
3. `_rows`: red then green.
4. Face ids: red then green.
5. **Mutants:**
   - blocker tolerances reach-1.0, -0.4 and reach now die (reach-0.05 survives; the test pins 0.1 and 0.5);
   - vote thresholds ≤12, ≤14, ≤17 and ≤20 now die.
6. **Wording and limits measured:**

   | Reversed in-room faces | Probes kept of 20 |
   |---|---|
   | ceiling + 1 wall | 18 |
   | ceiling + 2 walls | 13 |
   | floor + ceiling | 20 |
   | all inner faces | 0 |

## The checks
- Every BEFORE-visible sample is asked of AFTER from its best-conditioned viewpoint (largest |cos|, preferring front).
- **COVER:** BEFORE's own visibility ray into AFTER. A first hit more than `max(2 × print step, 0.05 in)` in front covers; it does not use the 0.02 step-off.
- **PRESENT:** a short ray from outside the tolerance window. If the first hit is not right, every face crossed is found by hand in float64. The sample is met if ANY crossed face has its look, UV (mod 1, 1 texel from the PNG header) and front where BEFORE saw the front.
- Print step = the export's precision (0.1 in on CHTM, so the tolerance is 0.2 in).
- **Check 3:** deleted, replaced or covered. Suspect faces (fingerprint = snapped corners + winding + look) get 1,024 extra directions.
- **Check 2:** `find_errors` BEFORE vs AFTER against `engine/validate/targets.json`. Unsigned gives REPORT_ONLY. `find_errors` is imported lazily, and a subprocess test proves the Validator loads no guard, fixes or vis.
- **Evidence:** 256 px orthographic crop pairs from the same camera, coloured by look; back faces mixed 50/50 purple.
- **CLI:** `validate --before <snapshot> --after <obj> --materials <json> --out <dir>` gives exit 0 on PASS and 2 on FAIL. Options `--targets`, `--area-per-sample`, `--min-per-face`; a non-default density writes "NOT AN OWNER VERDICT".
- Check mutants killed (15+): never covered; tolerance ×2, ÷2 or ignored; worst viewpoint; front ignored; every face suspect; no mod 1; half texel; window ÷4; extra samples counted in check 1; look ignored; no back tint; AFTER coloured with BEFORE's colours; and more.

## Real data
**Identity on CHTM 5th** at the owner's density, via the command at ef23d13: verdict PASS.
- textures: 275,918 samples seen, 0 failed;
- problems: REPORT_ONLY, counts equal;
- nothing_deleted: 0, 0, 0;
- 634 s, peak working set 580 MB, commit 1,215 MB;
- 441,300 samples, 8,052 of 20,599 faces visible, 128 directions, 24 cameras, 1,403 probes.

**Damaged CHTM 5th** (30 faces deleted, 15 flipped, 15 given another look; density 144): FAIL with 11,347 failed samples (deleted 8,122, look 1,402, side 1,804, uv 19) and 11 sites with crops, in 428 s. The crops show it plainly: a deleted slab reveals the stairs behind it, and a flipped wall turns purple.

**Identity sweeps** over 84 of 87 snapshots (densities 100, 144, 200; the two biggest stopped unfinished): 0 failures after the barycentric fix.
- Before the fix there was 1 sample on a PE_1st_Floor sliver, 1,190 in long and 0.0008 in wide: 3.3e-4 barycentric error, 2.5 texels.

## Concerns
1. Item 1 deviates from the carried text: the lid rule instead of `|n_z| > 0.9`, which breaks two existing tests. An open-air reversed floor with nothing above gets no probe; outside viewpoints still see it.
2. The verdict is FAIL if any check FAILs. Check 2 REPORT_ONLY does not block; `problems.signed` is reported.
3. Check 3 is judged per sample (stricter than per face), and also reports `faces_unmet`, `faces_partly_unmet` and `faces_covered`. A look change fails check 3 as well as check 1.
4. "Plus every probe": every probe is already a standard viewpoint. The 1,024 extra directions go to suspect samples no standard viewpoint saw.
5. Sites join touching 6 in cells, out to the lattice spacing (up to 4 cells).
6. The `targets.json` shape is defined here: `{"signed": true, "kinds": {"hidden": 0, "open_edges": null, "x": {"max": 5}}}`. P0-13 must write it.
7. Speed: about 10.6 min per floor at the owner's density (9 min of casts, 1.5 min for the two `find_errors`). A process pool is possible later.
8. Float32: faces thinner than about 1e-4 in are missed by Embree, and the float64 by-hand step covers them. trimesh's near-parallel drop is not fixed.
9. `cli.py` imports `engine.io.skp_reader._peak_memory_mb`, a private helper, to avoid ctypes.
10. `find_errors` on an empty AFTER without errors passed is unguarded.

## Controller's rulings (2026-10-04)
- **Concern 1, ACCEPTED.** The lid rule keeps the two existing tests' meaning and gives the +6 on CHTM 5th with 0 lost. An open-air reversed floor is still seen from outside.
- **Concerns 2-5, ACCEPTED.** Per-sample check 3 is stricter than the brief, which is the safe side.
- **Concern 6:** P0-13's sheet writes this `targets.json` shape. Noted in its dispatch.
- **Concern 7:** noted for P3 (validate per floor after repairs; a process pool later). The owner's density is not lowered.
- **Concern 9:** at merge time `engine/campus/winprobe.py` (from P0-12, now in feat/repair-p0) holds the Windows probes, so the reviewer judges whether validate should use it instead of a private helper.
- **Concern 10:** Minor; for the review.
