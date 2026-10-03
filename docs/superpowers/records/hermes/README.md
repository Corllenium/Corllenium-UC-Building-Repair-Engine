# Hermes job reports

One file per job: `<job id>-report.md`, written in the job's branch and committed with the work. Claude
reads it together with the diff before reviewing. Paste **real output**, never a summary of output you
did not see. If a command failed, paste the failure and say what you did about it.

Format:

```markdown
# <job id> — <title>

- Branch: hermes/<job id>   Base: <sha of feat/repair-p0 when the worktree was made>
- Commits: <sha> <subject>, one per line
- Brief: <path or plan#task-N>

## Items
### Item 1 — <name>: DONE | NOT DONE | PARTLY
- Tests added: `test_a`, `test_b`
- Red run (before the code): <paste the failing pytest lines>
- Green run (after): <paste the passing pytest lines>
- Notes: anything surprising, any choice you made and why

## Acceptance command outputs
<each command from the brief, then its real output, in a fenced block>

## Unsure about
<plainly: what you could not finish, could not verify, or are not sure is right>
```

Claude's review checks:
- the diff against the brief;
- that no file outside the brief changed: `engine/guard/**`, `FixProfile` thresholds and existing tests
  must not change unless the brief says so;
- that the acceptance commands give the same output when Claude re-runs them.
