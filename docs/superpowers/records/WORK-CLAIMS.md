# WORK CLAIMS — who is working on what

One row per job. Before starting a job, add or update its row with your name and the time, and
commit this file (or at least save it; it is read in the MAIN checkout by absolute path
`D:\PROJECTS\UC MODEL FIXER\docs\superpowers\records\WORK-CLAIMS.md`, also by workers in worktrees).
When you stop, set the status and release (holder `-`). Never work a job someone else holds.

**Claude at its usage limit:** a claim held by Claude (the controller or a Claude subagent) LAPSES
when Claude has hit its usage limit (the owner says so, or the job's tree shows no new commit or file
change for 30 minutes). Hermes then takes the job over: edit the row (holder `Hermes`, the time),
run `git status` and `git log` in the job's tree, and continue from the brief's remaining items;
uncommitted work there is the Claude agent's work in progress: finish, test and commit it, never
discard it. When Claude comes back it reads this file first and does NOT resume a job Hermes holds;
Hermes hands back by releasing the row after a clean commit.

| Job | Brief | Tree / branch | Holder | Since | Status |
|---|---|---|---|---|---|
| T1 T-junction repair | briefs/01-T1-tjunction-repair.md | main checkout / feat-dashboard | - | 2026-09-24 18:50 | DONE: 28d63df, 03df53d, report 437e4ef; A 1,013 / B 601 tris, T-vertices 0 |
| SR side rebuild (+ review C1, I1, M1 as SR4, SR5) | briefs/02-SR-side-rebuild.md | .claude/worktrees/side-rebuild / feat/side-rebuild | Claude subagent (SR) | 2026-09-24 18:34 | SR0 committed ff4a0ec; SR2 in progress; A's merge rollback being investigated; SR4/SR5 added 19:50 |
| Reconcile + verify | briefs/03-reconcile-and-verify.md | main checkout / feat-dashboard | Claude controller | queued | after T1 and SR |
| Review part 1 (to ce48932, no side rebuild) | briefs/04-review.md | read-only | - | 2026-09-24 19:45 | DONE: Changes required (C1, C2, I1, I2 + 9 minor); review-since-b2134e9.md |
| Review fixes C2, I2, M2-M4, M6-M8 | briefs/07-review-fixes.md | .claude/worktrees/review-fixes / feat/review-fixes | - | 2026-09-24 20:30 | DONE: 431 passed; merged into feat-dashboard; report 4f2fe22; A 15 removed (0 real surface), B 6 removed (0 real surface) |
| Review part 2 (side rebuild) | briefs/04-review.md | read-only | - | queued | after reconcile |
| Dashboard fix wave | briefs/05-dashboard-fix-wave.md | main checkout | - | queued | after review |
| Leftovers | briefs/06-leftovers.md | main checkout | - | queued | any time a slot is free |
