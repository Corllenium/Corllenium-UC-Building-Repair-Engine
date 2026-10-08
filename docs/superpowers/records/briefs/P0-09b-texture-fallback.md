# Brief P0-09b — no silent texture fallback in campus-materials

Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal
P0-09's second review found that `engine/campus/materials.py::_find_texture_file` still falls back to
any file with the same basename when a material's exact MTL-relative texture path is missing, and does
not flag it. A material then silently takes another folder's texture bytes. All 379 real textures
resolve by exact path, so `data/campus/materials.json` must not change. Spec §1 (`materials.json`, look
keys).

## Base, branch, merge
- Base `feat/repair-p0`; branch `hermes/P0-09b`; worktree `.hermes/worktrees/P0-09b`. Claude merges.

## Items
### Item 1 — a missing exact path is a missing texture
- **Test first** (`engine/tests/test_campus_materials.py`, new test): `folder_b/tile.png` is absent and
  `folder_a/tile.png` exists. A material whose `map_Kd` is `folder_b/tile.png` gets `missing_texture: true`,
  is not given folder_a's bytes, and does not share folder_a's look. See it fail on the base commit.
- Remove the basename fallback from `_find_texture_file`.
- **Done when:** the new test passes and the materials tests are green.

### Item 2 — test hygiene (from the same review)
- The test at `test_campus_materials.py:~200` writes `escape.png` into `tmp_path.parent`. Put the MTL in a
  subfolder of `tmp_path`, so the `..` case stays inside `tmp_path`.
- The fabricated-`source.json` CLI test runs from the source.json folder, so a mutant that resolves `--out`
  against that folder survives. Run it from a different cwd. Add a decoy `SRC-TEX` elsewhere, and assert that
  the sibling of the MTL is the one used.
- **Done when:** both tests pass. Show that each catches its mutant: revert P0-09's `--out` handling, then its sibling
  `SRC-TEX` rule, one at a time in your worktree, paste the failing output, and restore the file (`git checkout -- <file>`)
  before you commit. A mutant is never committed.

## Acceptance commands
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_campus_materials.py engine/tests/test_campus_source.py -q -p no:cacheprovider )
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09b" && PYTHONPATH="$PWD" "$PY" -m engine.cli campus-materials --source "D:/PROJECTS/UC MODEL FIXER/data/campus/source.json" --out "D:/PROJECTS/UC MODEL FIXER/data/p009b_check/materials.json" )
```
Expected: green; the real output's sha256 is still `28a0e0d328e025246f4908cb5e5dcde61862daec5fca1ed051b58aaec38e06a5`. Do not
overwrite `data/campus/materials.json`.

## Rules for this job
- Change only `engine/campus/materials.py` and `engine/tests/test_campus_materials.py`. Existing tests may be
  edited only as Item 2 says.

## Report
- Write `docs/superpowers/records/hermes/P0-09b-report.md` with real output. Commit with `Hermes-Job: P0-09b`.
- Hand in: `tools/jobs.py done P0-09b --branch hermes/P0-09b`.
