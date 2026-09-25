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
| SR side rebuild (+ review C1, I1, M1 as SR4, SR5; SR6 ramp) | briefs/02-SR-side-rebuild.md | .claude/worktrees/side-rebuild / feat/side-rebuild | - | 2026-09-25 08:05 | DONE: f58243d, 6eb6fb8, cb85e0d, 8d238c4, report fafd4d6; 427 passed on the branch; A 876 tris / B 486, backface_px final A 20,793 / B 6,006, ramp close-up 948 px (input 43,696); no rollback; passed. Waiting for the merge (brief 03) |
| Reconcile + verify | briefs/03-reconcile-and-verify.md | main checkout / feat-dashboard | - | 2026-09-25 10:55 | DONE_WITH_CONCERNS: merge 68f6d15, a89f771 (stub needs `replaced`), 82adc60 (opened-crack rule kept off removed-debris pixels), ca463c2 (side-rebuild walls protected, pinned), report f8e72bb; 542 passed; A 1,044 / B 530 tris, passed, no rollback, backface_px final A 20,945 / B 5,993; ramp close-up of the written .skp 948 px; A report.json byte-identical over two runs |
| Review part 1 (to ce48932, no side rebuild) | briefs/04-review.md | read-only | - | 2026-09-24 19:45 | DONE: Changes required (C1, C2, I1, I2 + 9 minor); review-since-b2134e9.md |
| Review fixes C2, I2, M2-M4, M6-M8 | briefs/07-review-fixes.md | .claude/worktrees/review-fixes / feat/review-fixes | - | 2026-09-24 20:30 | DONE: 431 passed; merged into feat-dashboard; report 4f2fe22; A 15 removed (0 real surface), B 6 removed (0 real surface) |
| Review 2a (Hermes's brief-07 commits a1e0349..4f2fe22) | briefs/04-review.md | read-only | - | 2026-09-25 00:15 | DONE: Changes required (1 Critical sandwiched slivers, 1 Important T-junction join untested, 11 minor); review-hermes-fixes.md |
| Review 2a fixes | briefs/08-review2a-fixes.md | main checkout / feat-dashboard | - | 2026-09-25 06:20 | DONE: 12 commits 536fca7..d570927, report 64023ad; 462 passed; A 1,033 / B 596 passed; 10 of 21 old removals were real surface, all kept now |
| Sliver ray confirmation + folds | briefs/09-sliver-ray-confirmation.md | main checkout / feat-dashboard | - | 2026-09-25 08:10 | DONE: 3386c4f, 62bee9d, 54fbce5, 3d30327, report d9673c1; 497 passed; A 1,031 / B 600; slots A 3540, 4659 refused; folds A 34/43, B 22/31 |
| Review part 2 (side rebuild, merge, briefs 08 and 09) | briefs/04-review.md | read-only, committed state at e27eb79 | - | 2026-09-25 12:05 | DONE: Changes required (C1 double layers from restored pieces, C2 real underside deleted, I1 band replaces any face, I2 floor taken as lower surface, 5 minor); review-side-rebuild.md; all folded into brief 10 |
| Dashboard fix wave | briefs/05-dashboard-fix-wave.md | Hermes's own worktree (--worktree), branch feat/dashboard-wave | Hermes (gemini-3.8-flash, one-shot, started by the Claude controller) | 2026-09-25 12:35 | running |
| Leftovers | briefs/06-leftovers.md | main checkout | - | queued | any time a slot is free |
| Side rebuild follow-ups | briefs/10-side-rebuild-followups.md | main checkout / feat-dashboard | Claude subagent (brief 10) | 2026-09-25 11:15 | running |
| Visual triage 2026-09-25 | (inline prompt; output docs/superpowers/records/visual-triage-2026-09-25.md) | read-only, data/visual_triage/2026-09-25 | Hermes (gemini-3.8-flash, one-shot, started by the Claude controller) | 2026-09-25 12:35 | running |
