---
name: uc-handoff
description: Use when taking, doing, handing in or reviewing a queued job in UC MODEL FIXER (tools/jobs.py) — for Claude and Hermes alike: claim, worktree, brief, report, done, review, merge, records.
---

# Taking and handing over queued jobs

The workflow rules are `AGENTS.md` §7. These are the exact steps.

`PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"`. Run `tools/jobs.py` from the main checkout
`D:\PROJECTS\UC MODEL FIXER`.

## Taking a job

1. `"$PY" tools/jobs.py next --for <claude|hermes> --as <your name>`
   - It prints `<id>  <brief>  <branch>`.
   - Exit code 3 means nothing is eligible for you now.
2. `git -C "D:/PROJECTS/UC MODEL FIXER" worktree add -b <branch> <.claude|.hermes>/worktrees/<id> <integration branch>`.
   P0's integration branch is `feat/repair-p0`.
3. Read `AGENTS.md`, then the brief. A path ending `#task-N` means that task of the plan.

## Doing it

- Item by item, test first: write the named test, see it fail, implement, see it pass, commit by name.
- Python always runs from the worktree root, in a subshell, with `PYTHONPATH` set (`AGENTS.md` §8).
- The real-data steps write only to `data/`, never to the owner's folders.

## Handing in

1. Write the report. Hermes: `docs/superpowers/records/hermes/<id>-report.md`, in the format of
   `docs/superpowers/records/hermes/README.md`. Claude: the plan's ledger.
   - Paste the real output of every acceptance command.
2. `"$PY" tools/jobs.py done <id> --branch <branch>`.

## Reviewing (Claude controller only)

1. `tools/jobs.py list --status awaiting-review`.
2. Make the diff: `git diff <integration>...<branch>`. Then:
   - dispatch `hermes-reviewer` (for Hermes branches) or `rules-reviewer` with the brief, the report and
     the diff;
   - re-run the brief's acceptance commands yourself, from a worktree of that branch.
3. **Pass:** `tools/jobs.py review <id> --pass`; merge the branch into the integration branch with
   `--no-ff`; remove the job worktree.
4. **Changes:** `tools/jobs.py review <id> --changes "<what and why>"`. The job goes back to its holder
   on the same branch.
5. `tools/jobs.py render`, then update the ledger, HANDOFF §2 and the session record, and commit them
   by name.
