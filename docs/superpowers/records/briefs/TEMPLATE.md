# Brief <job id> — <one-line goal>

Template for every queued job, Claude's or Hermes's. A plan task (`docs/superpowers/plans/…#task-N`)
already in this shape counts as the brief. Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal
What the job delivers, and why the owner needs it, in 2-4 lines. Name the spec section it implements.

## Files
- Create: `exact/path.py`, `engine/tests/test_exact.py`
- Modify: `exact/path.py` (which function, what changes)
- Read only: the inputs (for example `data/campus/source.json`)

## Interfaces
- Consumes: the names, types and files from earlier jobs.
- Produces: the exact signatures, JSON fields and files that later jobs rely on.

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

## Rules for this job
- Anything the job must not touch, beyond `AGENTS.md`.
- Any owner exception this job relies on (`AGENTS.md` §4), and how it is measured.

## Report
- Hermes: `docs/superpowers/records/hermes/<job id>-report.md` (format: `../hermes/README.md`).
- Claude: the plan's SDD ledger.
- Hand in with `tools/jobs.py done <job id> --branch <branch>`.
