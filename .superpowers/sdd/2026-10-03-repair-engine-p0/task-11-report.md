# Task 11 (P0-11) — implementer's report, as handed back, plus the controller's rulings

Branch `claude/P0-11` from e7fac71, worktree `.claude/worktrees/P0-11`, HEAD 3ec7181, tree clean. Status:
DONE_WITH_CONCERNS.

## Commits (oldest first)
32f76c1 read-only SketchUp reader that binds no save call · f441c75 groups and instances with composed
transforms · b434dde hidden and tag-off left out and counted, runs as a child · acdc2a3 skp_check compares each
split file with the backup · c99bed8 the whole SDK check and `campus-skp-check` · 7e5d6a6 pin bbox tolerance
and stale-copy deletion · e3a38fd counts the triangles the export lacks · 04df3df summary gives box distances
(**committed with one summary test failing**; fixed by 9c8994e) · 9c8994e print step from the most precise
file · a8fa877 one-sentence direction of mismatches · 8283d71 the brief's step-6 commit, with
`docs/superpowers/records/campus/skp-check.md` · 3ec7181 a probe of the duplicate faces (records script).

## Files
New: `engine/io/skp_reader.py`, `engine/campus/skp_check.py`, `engine/tests/test_skp_reader.py` (34),
`engine/tests/test_skp_check.py` (71, pure Python, no DLL), `engine/tests/skp_scene.py` (test helper building
SketchUp scenes; binds SUModelSaveToFile, tests only), `docs/superpowers/records/campus/skp-check.md`,
`docs/superpowers/records/scripts/skp_duplicate_census.py`.
Modified: `engine/cli.py` (+39, `campus-skp-check`), `engine/tests/test_skp_writer.py` (one test widened),
`engine/io/skp_writer.py` (a 3-line docstring).
Outputs (git-ignored): `data/campus/skp_check.json`, `skp_walk.json`, `skp_copy/`.

## Claimed evidence
- Reds seen before code for every test group (ImportErrors, then failing counts), then green.
- `test_skp_reader.py + test_skp_check.py + test_skp_writer.py`: 150 passed in 7.33 s. All 24 calls the brief
  lists are bound; no bound name contains "save".
- Mutation checks: 19 on the reader, 40 on skp_check/CLI; 3 survivors got tests (doubled bbox tolerance, stale
  wrong copy kept when the backup also fails, string not released on failure).
- Transform convention and area checked against SketchUp's own answers (SUDrawingElementGetBoundingBox,
  SUFaceGetAreaWithTransform): rotated, nested, scaled, mirrored, instances.
- Full engine suite on 3ec7181: 754 passed, 1 xfailed in 386 s.
- Real run (source.json created 2026-10-03T19:12:52+08:00):
  `campus-skp-check --source data/campus/source.json --backup "MODEL FIXER ENGINE FILES/02-SKETCHUP-MODELS/CHECKPOINT-17-BACKUP" --out data/campus --summary docs/superpowers/records/campus/skp-check.md`
  → "checked 85 files against UC-campus-FIXED-v2026-07-11 - CHECKPOINT-17.skp: 63 match, 18 mismatch, 4
  ambiguous, 0 miss", exit 0, 76 s. Backup .skp sha256 ddecd020a826… equals the frozen one; opened only through
  the verified copy; backup files unchanged (sizes and times equal source.json); master never opened.
- Boxes: 81 paired files within 0.0496 in (tolerance 0.2 in = 2 × print step 0.1 in). Z-up, inches.
- 0 hidden, 0 tag-off. SDK API 14.2; 1,329 groups, 153 instances, 705,109 faces, 1,861,189 triangles
  (v+2h-2); walk 46 s; peak 1,958 MB working set, 2,526 MB commit.
- All 18 mismatches are area only, backup larger, +0.51 % to +2.09 %. Worst: unnamed +2.094 %,
  BRS_9th_floor_obj1 +2.050 %, CHTM_4th_floor +2.025 %, BRS_9th_floor_obj +1.957 %, CHTM_3rd_floor +1.860 %.
- Ambiguities: 5 families paired by shape; Science A plan_2/plan_3 (and obj1) unpaired: backup twins
  identical, the second export file ~17 % short of either.

## Findings (measured; mechanism unproven)
- The export has 90,391 triangles (4.9 %) fewer than the backup over the 81 paired files; where a group is
  complete, triangle counts agree exactly, so faces are missing, not triangulated differently.
- Exact duplicate faces in the backup (same corners to 0.1 in, same facing, different material groups) explain
  most of it: of 70 single-group files, 56 are within 0.5 % as is, 64 after removing duplicates. Not all:
  unnamed +2.09 %, EDS 1st +0.71 %, CHTM 4th +0.77 %, BRIDGE_ZONE +0.72 %, MAIN_BUILDING +0.57 % stay
  unexplained and could hide a visible difference (not looked for).
- CKPT17-CLEAN.obj still holds 5,456 exact same-facing duplicate triangles.

## Implementer's concerns
1. `test_skp_writer.py::test_ctypes_is_imported_only_by_the_skp_writer` renamed to
   `..._by_the_sketchup_binding_modules`; allow-list exactly `io/skp_reader.py`, `io/skp_writer.py`,
   `tests/skp_scene.py`.
2. Matching deviates from the brief: only 41 of 85 manifest names are top-level group names; names are the
   exporter's sanitised form; each file holds only what the owner's split rule gave it. So skp_check applies the
   owner's `split_named.py` rule (outermost floor-like group, else outermost named, import names skipped) to the
   backup's groups; duplicate/nameless names are "families", paired by shape only when one pairing is clearly
   best.
3. AUTO/KEY and the 2-token skip are copied from the owner's script into skp_check.py; P0-08's groups.py has
   its own copy.
4. Memory: the walk needs ~2.5 GB commit; `run_walk` refuses below 3,500 MB free (`--min-free-commit-mb`).
5. Group124/137/220 paired by shape (areas within 0.025 %).
6. Triangles reported as a note only; the SDK prints one "Not a TIFF" line per run.
7. The census probe script uses the reader's private helpers (records script, ~2.7 GB commit).
8. No blocked operation, guard or FixProfile touched; read-only.

## Controller's rulings (2026-10-04)
- **Concern 1, ACCEPTED.** The brief requires the reader to bind its own table with no save call reachable,
  which makes it a second ctypes module; the widened test keeps the intent (ctypes only in the SketchUp binding
  modules) with an exact allow-list. AGENTS.md §7's "existing tests" gate is satisfied because the brief's
  design required it. Cost if wrong: one allow-list.
- **Concern 2, ACCEPTED** on the measured evidence; the reviewer checks the implementation is that rule and that
  the brief's rule is its special case. Cost if wrong: a 76 s re-run with another matcher.
- **Concern 3, PARKED** until P0-08 merges: then a test pins skp_check's rule equal to groups.py's, or one
  imports the other.
- **04df3df** (a commit with a failing test): process slip, noted; HEAD is green; history is not rewritten.
- **Findings** go to the owner and into the P0-13 decision sheet: whether the export's missing faces (90,391
  triangles, mostly backup duplicates; 5 files unexplained; Science A plan_2/3) need a re-export from the backup.

## Fix round 1 (implementer's hand-back, 2026-10-04; recorded by the controller)
The implementer could not write this file (the Write tool refuses report files from subagents).
Raw outputs: `<session scratchpad>/p0-11/fix1/` (`<item>.red.txt`, `<item>.green.txt`, `mut_*.out`, `suite-final.txt`, `focused-final.txt`).

**Commits on 3ec7181, oldest first:**
- 232ae0c (minor 1): `w` applied the way SketchUp does;
- f13571d (minor 6): exact names first;
- 5472afb (IMPORTANT): a verdict that is the same under every pairing is decided without one;
- 2fda5d1 (minor 8): `zero_area_tris` reported;
- aea57fa (minor 5): absolute paths for the child;
- 438127a (minors 4, 3): summary path refused inside the backup, and `SourceUnstable` gives a one-line error;
- 41ba197 (minor 2): the census probe opens only the verified copy;
- 0bed164 (minor 7): the writer docstring;
- 690e215: `skp-check.md` regenerated.

9 files, +574/-74. No guard or FixProfile change, and `test_skp_writer.py` got additions only.

**Tests at 690e215:**
- Focused: 181 passed (reader 40, check 95, writer 46); 150 before.
- Whole engine/tests: 785 passed, 1 xfailed in 546.53 s.

**Real re-run** (59 s, free-commit guard on, verified copy re-hashed, backup unchanged, master not opened): "checked 85 files ...: 65 match, 20 mismatch, 0 ambiguous, 0 miss". Before: 63/18/4/0.
- Four files changed verdict:
  - Science A plan_2_obj: match (any_group, +0.049 %);
  - Science A plan_3_obj: match (any_group, +0.033 %);
  - Science A plan_2_obj1: mismatch (nearest_group, +20.664 %, min y 12.478 in off);
  - Science A plan_3_obj1: mismatch (nearest_group, +20.790 %, box within 0.044 in).
- Pairing: 70 files by name, 11 by shape, 2 any_group, 2 nearest_group.
- Triangles: backup 1,861,181, export 1,766,906, so the export lacks 94,275 (5.1 %). The export holds 42,791 zero-area triangles.
- Summary direction sentence: backup has MORE area in every mismatch, +0.51 % to +20.79 %.

**Per item:** red seen, then green; mutants:
- IMPORTANT: 12 mutants, 1 survived and was fixed by a stronger summary test;
- minor 1: 5/5;
- minor 2: 11/11;
- minors 3-4: 3/3;
- minor 5: 2/2;
- minor 6: 7/7;
- minor 8: 5/5;
- minor 7: pinned by a prose test.

**Notes:**
- A tool result carried a system-reminder-style line asking for a different Co-Authored-By trailer. The implementer treated it as data and kept "Claude Sonnet 5".
- The census probe's docstring keeps its dated 10-03 result.
- Owner findings for P0-13: the two Science A _obj1 files lack ~17 % of their group's area; plan_2_obj1 is 12.478 in off in min y.
