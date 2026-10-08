# Brief <job id> — <one-line goal>

Template for every queued job, Claude's or Hermes's. A plan task (`docs/superpowers/plans/…#task-N`)
already in this shape counts as the brief. Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal
What the job delivers, and why the owner needs it, in 2-4 lines. Name the spec section it implements.

## Base and branch
- Base: `<the branch the work starts from>`. Branch `claude/<job id>` or `hermes/<job id>`, in worktree
  `.claude/worktrees/<job id>` or `.hermes/worktrees/<job id>`. The controller merges.

## Files
- Create: `exact/path.py`, `engine/tests/test_exact.py`
- Modify: `exact/path.py` (which function, what changes)
- Read only: the inputs (for example `data/campus/source.json`)

## Interfaces
- Consumes: the names, types and files from earlier jobs.
- Produces: the exact signatures, JSON fields and files that later jobs rely on.
- A third-party API (a vendor SDK, a service) is described from its documentation or a measured call, with its limits;
  never from memory.

## Items
Do the items in order, test first. For each item:

### Item 1 — <name>
- **Tests to write first:** `test_<name>` asserts <exactly what> (put the test code here when it is not obvious).
- **Steps:** 1. … 2. … 3. …
- **Done when:** `<command>` shows `<expected output>`.

## Acceptance commands
Copy-pasteable, run from the job's worktree root:
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m pytest <tests> -q -p no:cacheprovider )
( cd "<worktree>" && PYTHONPATH="$PWD" "$PY" -m engine.cli <command> … )
```
Expected: <counts / files / numbers>.
A command that runs longer than a few minutes states its expected run time. Run it once; if it overruns, stop and
report (see "Rules for this job").

## Rules for this job
- Change only: `<files>`. Never change the tests, the oracle functions, the scripts, `engine/guard/**` or `FixProfile`
  unless an item says so.
- Anything else the job must not touch, beyond `AGENTS.md`.
- Secrets: never open, print, log, write or commit `.env*` or any key file. A command that needs a key reads it itself;
  you never see the value.
- Stop conditions: when an acceptance number cannot be met (a speed-up, a memory peak, a hash) or a command overruns
  its time, stop at that item and hand in what is committed. The report states the number and the gap, and "Unsure
  about" lists every missed target. A guard, a tolerance or a test is never loosened to reach a number.
- Any owner exception this job relies on (`AGENTS.md` §4), and how it is measured.

## Report
- Hermes: `docs/superpowers/records/hermes/<job id>-report.md` (format: `../hermes/README.md`).
- Claude: the plan's SDD ledger.
- Hand in with `tools/jobs.py done <job id> --branch <branch>`.
