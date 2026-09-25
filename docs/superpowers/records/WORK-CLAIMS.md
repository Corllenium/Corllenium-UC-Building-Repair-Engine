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
| Dashboard fix wave, pass 1 | briefs/05-dashboard-fix-wave.md | .hermes/worktrees/dashboard-wave / feat/dashboard-wave | - | 2026-09-25 13:10 | DONE by Hermes (14 commits c88b300..c0f2ea4, api 21 / web 18 passed, about 6.40 USD): D1-D6 claimed done; D7 not done (misread as an engine change); D9-D12 done as DIFFERENT features than the brief (overlays, rescan, soft delete, per-session test DBs); migrations 0002, 0003 added |
| Dashboard fix wave, pass 2 (D7, D9-D12 as written) | briefs/05-dashboard-fix-wave.md | .hermes/worktrees/dashboard-wave | - | 2026-09-25 13:57 | DONE by Hermes: e98126f D7, fc62f6d D9 (API side; engine move noted), ac94bdc D10, 9577bdb D11, 80c5f38 D12; web 27 passed |
| Dashboard fix wave, pass 3 (review findings) | review-dashboard-wave.md | .hermes/worktrees/dashboard-wave | - | 2026-09-25 16:38 | DONE by Hermes (15 commits ca1b8f1..6f33222, about 4.60 USD): I1-I8 and m1-m12 fixed or already fixed; rescan and soft delete reverted; web 35 passed, api 32 passed (its report) |
| Re-review of feat/dashboard-wave passes 2+3 | read-only | committed state 6f33222 | - | 2026-09-25 17:35 | DONE: Changes required (0 Critical, 2 Important, 12 Minor); api 32, web 35 passed; vue-tsc 8 errors (5 new); rereview-dashboard-wave.md |
| Dashboard fix wave, pass 4 (re-review findings) | rereview-dashboard-wave.md | .hermes/worktrees/dashboard-wave | - | 2026-09-25 18:30 | DONE by Hermes (16 commits 55e728b..da8ba85, about 3.35 USD): N1, N2, n1-n12 claimed fixed; engine untouched; merge-tree clean |
| Re-review round 3 (pass 4 only) | read-only | committed state da8ba85 | Claude subagent (re-review 3) | 2026-09-25 18:50 | running |
| Review of feat/dashboard-wave (pass 1, c0f2ea4) | read-only | committed state c0f2ea4 | - | 2026-09-25 13:49 | DONE: Changes required (0 Critical, 8 Important, 12 Minor); review-dashboard-wave.md |
| Leftovers | briefs/06-leftovers.md | main checkout | - | queued | any time a slot is free |
| Side rebuild follow-ups | briefs/10-side-rebuild-followups.md | main checkout / feat-dashboard | - | 2026-09-25 17:12 | DONE_WITH_CONCERNS: 9f64ae9..f7e27d1, report daeb84c/4f84ccb; 566 passed; A 917 / B 506, backface final A 21,553 / B 2,787; A owner .skp NOT replaced (file open in SketchUp) |
| Review of brief 10 (rule 6 and the R2 fixes) | read-only | committed state dc24e9a | - | 2026-09-25 18:40 | DONE: Changes required (1 Critical: underside still taken for a top in 3 cases; 3 Important: rule 6 hides geometry when the plan is wrong, regression at steps, piece belonging 2-D/walls only; 6 Minor); review-brief10.md; folded into brief 11 |
| Remaining visual defects | briefs/11-remaining-visual-defects.md | main checkout / feat-dashboard | Claude subagent (brief 11) | 2026-09-25 17:45 | running |
| Visual triage 2026-09-25 | (inline prompt) | read-only, data/visual_triage/2026-09-25 | - | 2026-09-25 12:05 | DONE by Hermes (gemini-3.8-flash, 52 calls, about 0.55 USD): docs/superpowers/records/visual-triage-2026-09-25.md; top items verified by the controller (B middle slabs hollow from below; A big-landing margin line clutter) |
