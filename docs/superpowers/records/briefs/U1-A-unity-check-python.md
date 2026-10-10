# Brief U1-A: the Unity import check, Python side (plan Tasks 1-5)

Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal

Build `engine.cli unity-check`. It compares an engine build (OBJ) with what Unity made of it (a "dump": OBJ + MTL +
`.unity.json` sidecar) and gives **UNITY-SAFE** or **BROKEN BY IMPORT**, by cause:
- missing, extra or flipped faces;
- material or texture lost, UV changed;
- a normal pointing against its face (the "black face" cause);
- a 16-bit index overflow;
- an engine error kind that got worse.

This is Part 1 of the spec `docs/superpowers/specs/2026-10-10-unity-floor-pipeline-design.md`. The owner's Unity
floors break on import; this check proves why. Pure Python, **no Unity needed**. Claude builds the Unity side (plan
Tasks 6-7) in parallel.

## Base and branch

- Base: `feat/repair-p1p2`.
- Branch `hermes/U1-A`, in worktree `.hermes/worktrees/U1-A`. The controller merges.

## Files

- Create:
  - `engine/unity/__init__.py`, `engine/unity/dump.py`, `engine/unity/align.py`, `engine/unity/check.py`;
  - the tests `engine/tests/test_unity_dump.py`, `test_unity_align.py`, `test_unity_check.py`,
    `test_cli_unity_check.py`.
- Modify: `engine/cli.py`. Add the `unity-check` sub-command and its handler `cmd_unity_check`, and add its `--out`
  to `_OUTPUT_ARGS`.
- Read only: `engine/io/obj_reader.py`, `engine/io/obj_writer.py`, `engine/io/mtl.py`, `engine/repair/types.py`
  (`print_step`), `engine/detectors/errors.py` (`find_errors`), and `engine/tests/fixtures/build.py` (`cube`).

## Interfaces

Exactly as the plan states them, in `docs/superpowers/plans/2026-10-10-unity-import-check.md`, Tasks 1-5 (and its
"The dump format" section):
- `read_unity_dump(obj_path) -> UnityDump(mesh, corner_normals, sidecar)`, and `DumpError`;
- `align(build, unity, scale, tol) -> Alignment`, `to_build_frame(points, a)`, and `AlignError`;
- `geometry_diff(build, dump) -> dict`;
- `surface_diff(build, dump, build_mtl, unity_mtl) -> dict`;
- `unity_check(build, dump, build_mtl, unity_mtl) -> dict` with `verdict` and `causes`;
- the CLI `engine.cli unity-check --build <obj> --unity <dump obj> --out <dir>`. Exit 0 = UNITY-SAFE,
  3 = BROKEN BY IMPORT, 2 = refused.

## Items

Do the plan's **Tasks 1, 2, 3, 4 and 5**, in order. Each task gives the failing tests (copy them as written), the
command to see them fail, the implementation, the command to see them pass, and the commit. Commit after each task,
staging files by name.

- **If a plan test fails for a reason the plan did not expect**, fix the implementation, never the test. If you are
  sure the plan's test itself is wrong, stop at that task and say so in the report under "Unsure about".
- In Task 5, read how `find_errors` returns each kind's count before writing `_kind_counts`. If its shape differs from
  the plan's guess, adapt `_kind_counts` to the real shape and say so in the report.

## Acceptance commands

```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
W="D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/U1-A"
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_unity_dump.py engine/tests/test_unity_align.py engine/tests/test_unity_check.py engine/tests/test_cli_unity_check.py -q -p no:cacheprovider )
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest tools/tests -q -p no:cacheprovider )
```

Expected:
- the first command: `19 passed`;
- the full engine suite: all pass, apart from its existing 1 xfailed (about 15 minutes);
- the tools suite: all pass.

## Rules for this job

- **Change only** the files listed under Files. Never change existing tests, `engine/guard/**`,
  `engine/validate/**`, `engine/repair/**` or `FixProfile`. No new Python dependency (there is no scipy).
- **Never open, read or touch** the owner's Unity project `D:/PROJECTS/UC/01-UNITY/UC-Campus`, the live export
  folder, the master `.skp`, the containers or the live database.
- **Never use a bare `cd`.** Use subshells as above. Stop only processes you started, by PID.
- **Secrets:** never open, print, log, write or commit `.env*` or any key file.
- **Stop condition:** if a plan test cannot pass without loosening it, stop at that task, hand in what is committed,
  and list it under "Unsure about".

## Report

- `docs/superpowers/records/hermes/U1-A-report.md`, in the format of `docs/superpowers/records/hermes/README.md`.
  Paste the real output of each acceptance command.
- Hand in with `tools/jobs.py done U1-A --branch hermes/U1-A`.
