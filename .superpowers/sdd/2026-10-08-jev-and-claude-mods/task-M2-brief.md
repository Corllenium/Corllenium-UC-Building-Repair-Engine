### Task B2 = queue job M2: `uc-status` (status line plus a band)

**Gap:** the controller loses track of which job and worktree it is in, and of what is running. That cost a
compaction recovery today.

**What it does:**
- **Status line:** current branch, worktree name, and the claimed job from `data/jobs/queue.json`
  (`P0-17 claimed`).
- **Band above the prompt:**
  - counts of queue jobs by status;
  - a warning when the main checkout has uncommitted files in paths this session staged before;
  - a reminder when commits were made but the ledger (`.superpowers/sdd/*/progress.md`) was not touched since.
- **Data access:** read-only, through `$.fs` and `$.process` (`git`).

**Done when:** it is green, it shows correct values in a screenshot, and it is copied to `tools/claude-mods/uc-status/`.

