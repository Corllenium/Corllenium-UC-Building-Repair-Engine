# Brief 07 — fixes from review part 1 (guards, fragments, CLI)

Source: `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/review-since-b2134e9.md` (verdict: Changes
required). Probe scripts that reproduce each finding: `docs/superpowers/records/scripts/review-probes/`
(run with `PYTHONPATH=<tree root>`). C1, I1 and M1 are NOT here: they are folded into the side
rebuild (brief 02), which rewrites the same solidify and cap-guard code.

Where: worktree `D:\PROJECTS\UC MODEL FIXER\.claude\worktrees\review-fixes`, branch
`feat/review-fixes`, created from `feat-dashboard`. The side rebuild also edits `engine/guard/compare.py`,
`engine/fixes/pipeline.py` and `engine/cli.py` on its own branch: keep your hunks in other functions
where you can (fragment classification, `fragment_feedback`, the `.skp` copy, report fields), so the
later merge stays small. Append fixtures at the END of `engine/tests/fixtures/build.py`.
Test-first, one commit per item.

## Items

**C2 `fix(engine): fragments connect through T-junctions and their own pixels are judged`**
(review C2). The fragment detector (`engine/detectors/fragments.py`) builds components over shared
welded edges only, so a patch of real surface joined to its neighbours only through T-junctions
(export T-junctions are everywhere: 353 on A, 363 on B at the merge input) is classed as debris; the
fragment-mode guard never judges a candidate's own pixels (`compare.py` `fail = fail & ~mine`) and the
final guard excuses them by name, uncapped. Probe: a 3 x 1 in infill patch in a slab top is removed
and a hole ships with `passed` True. Fix: connect components across T-junctions (a vertex lying on
another face's edge, the tolerance `analyse_topology` uses) and across coplanar contact; in fragment
mode permit a candidate's own pixel only when AFTER shows background or a face side that is exposed on
the reference, never the inside of a closed shell; cap `fragment_removed` per view like
`crack_closed`; write every removed component (face ids, area, bbox) to `report.json`. Then report,
with close-up renders, what the current rules removed on the real files (A 3 fragments + 15 slivers,
B 12 slivers) and whether any of it was real surface.

**I2 `fix(engine): a failed run does not replace the owner's SketchUp file`** (review I2).
`engine/cli.py` writes and copies the `.skp` whatever `result.passed` is. Copy into the skp folder
only when the run passed; on a failed run keep the previous copy and write
`<name>.fixed.FAILED.skp` beside it; say so on the CLI line and in `report.json` (`skp.copied_to`).
Test with a forced failing run and an existing file in the skp folder.

**M8 (same commit as I2 or its own):** an unexpected exception in the QA or `.skp` step leaves the
previous run's `report.json` beside the new OBJs: write (or delete) `report.json` before the optional
exports, or catch `Exception` in `_write_skp` and record it.

**M3 `fix(engine): the guard measures growth over background like a loss`** (review M3). A pixel where
BEFORE missed and AFTER hit is `PX_OK` today, so a merge bug that grows a silhouette is invisible to
every guard (d505241 accepts per-region growth up to `collinear_tol x perimeter`). Class it as a
failing base (for example `PX_GROWN`) and let the existing ring and border-shift measurement excuse it
exactly like a loss (appeared point within tolerance of the BEFORE mesh). Report per file how many
pixels this re-classes on A and B; the final guards must still pass, or the finding is real and must be
reported.

**M4 (with M3):** the border-shift "displacement" is the clearance to the nearest triangle of any
surface. Measure first against triangles of the same material near the BEFORE hit's plane, or correct
the docstrings to say clearance; say which and why.

**M2 `fix(engine): the bbox invariant compares the vertices faces use`** (review M2): the current
invariant compares the whole `positions` array, which merge/removal/flip never touch, so it cannot
fail. Compare the bbox of used vertices. Test: a shipped mesh reduced to one face fails it.

**M7:** `engine/guard/qa_render.py::polygon_edges` claims to return what SketchUp will draw, but the
writer hides class 1/5 edges of copied rows and the S1 lines. Feed the QA sheet the same hidden-edge
decision (or correct the docstring) so the render sheet stops showing fans SketchUp hides.

**M6:** re-run the `ON_FACE_TOL` sweep in `engine/io/skp_writer.py` on the current output and restate
its numbers.

## Finish

Suite count; both real runs from the worktree root with outputs inside the worktree
(`"/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m engine.cli fix "D:/PROJECTS/UC MODEL FIXER/data/snapshots/<id>" --out data/output --skp-dir "OBJ FIXED RESULT"`);
per file: triangles, fragments removed with their list, grown pixels, every guard total, invariants,
passed; the SketchUp audit (`docs/superpowers/records/scripts/skp_edge_audit.py`); two QA images read.
Report `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/review-fixes-report.md` (force-add) ending
with `## Public signatures`.
