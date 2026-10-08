# SDD ledger — plan: D:/PROJECTS/UC MODEL FIXER/docs/superpowers/plans/2026-10-08-jev-and-claude-mods.md

Spec: docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md §9 (owner-approved 2026-10-03).
Controller: session "Jev + mods" (2026-10-08). Peer session "3d uc building repair engine" holds feat/repair-p0 merges, P0-13/16/18, verified worktree, P0 ledger.

## Start state (measured 2026-10-08)
- TYPESAFE_API_KEY: not in user env or process env. typesafe-sdk: not installed (pip show exit 1).
- Queue: P0-17, M1, M2, M3 ready; P0-16, P0-18 claimed by peer.
- feat/repair-p0 green at 83b89a8 (peer: 1273 passed, 1 xfailed).

## Pre-flight scan
| Item | Check | Finding |
|---|---|---|
| A1 (P0-17) vs Task 17 text | interface vs live SDK docs | Noul has no confidence; state is a dict → Rulings 1-2 |
| A1 vs constraint "key from process env only" | owner decision 2026-10-08 | owner chose repo-root .env → Ruling 3 |
| A1 truth source | Task 17 says Task 10 inventory; plan says campus_map.json | Ruling 4 |
| A1 vs A2 | A2 needs P1-K1 | A2 not in this run |
| B1/B2/B3 vs A1 | no shared files | clean |
| B3 | needs pilot + owner decision 4 | not built this run |
| Spec line 42 ("TypeSafe not used") vs §9 | stale row | fix in records commit on feat-dashboard |

Ruling: Noul → answer=p>=0.5, confidence=max(p,1-p) — the SDK gives no Noul confidence; gate 0.8 means p>=0.8 or <=0.2 — if wrong, the coverage numbers for Noul questions shift.
Ruling: key read from env, else only the TYPESAFE_API_KEY line of repo-root .env — owner decision 2026-10-08 overrides the plan's "process env only" — if wrong, revert to env-only (one function).
Ruling: pilot truth = campus_map.json, groups not listed = SITE — owner-confirmed map exists; Task 10 text predates it — if wrong, accuracy numbers move.
Ruling: TypeSafe Claude skill install blocked by auto-mode classifier; owner installs it himself — docs read directly instead.

## Log
- P0-17: claimed (Claude); worktree .claude/worktrees/P0-17, branch claude/P0-17, BASE 83b89a8.
- P0-17: engine-builder (sonnet) dispatched in background with task-P0-17-brief.md; report → task-P0-17-report.md.
- M1: claimed (Claude). Mod at C:/Users/Future26/.claude/dev-mods/246a631b-a54c-4c22-b753-957622c1fbf4/uc-guard (hooks/register.ts, hooks/rules.ts, tests/rules.test.ts).
  - RED: stub check() → 13 deny assertions failed, allow cases passed.
  - GREEN: claude plugin test (2.1.293 CLI; PATH claude is 2.1.258 without `test`) → 20 pass, 0 fail.
  - validate: passed (author warning fixed). tsc 5.7.3 (web/node_modules) with the skill's tsconfig + allowImportingTsExtensions → exit 0.
  - Still open: live denial seen by owner (needs hot reload), copy to tools/claude-mods/uc-guard + README, rules-reviewer.
Ruling: uc-guard also blocks Write/Edit of .env (plan said "reading") — Claude must never hold the key either way — if wrong, owner edits .env by hand anyway, no loss.
Ruling: PowerShell Set-Location is denied even inside parentheses — PowerShell parens do not scope location — if wrong, PS users lose one idiom; absolute paths work.
Ruling: result folders use a read-only allowlist (deny anything else unless the command names worktrees/verified); source folders use a write-verb denylist so engine reads still pass — if wrong, a legit command needs the verified path or the owner.
- M1 committed on claude/M1 (worktree .claude/worktrees/M1, base feat-dashboard fc0ab57): fc849ce. Repo copy at tools/claude-mods/uc-guard with README.
- Owner enabled hot reloading; uc-guard is live in this session.
- M1 review (rules-reviewer, opus) on fc0ab57..fc849ce: Spec ❌ / CHANGES.
  - Critical: docker compose global options (-p/-f) hid `up` (HANDOFF.md:351 command passed).
  - Important: find -delete/-exec not seen; psql -U fixer false positive; result-folder names in commit messages/records false positive; raw-text secret checks hit heredoc bodies, commit messages and grep patterns.
  - Minor: shell keywords; here-string; verified substring; .env* gaps; reason wording; PowerShell `.\`; Monitor; weak toBeDefined asserts; no toast/catch test.
  - Fail-safety sound; the three rulings above accepted (the result allowlist scoped to path-like words).
  - The live guard denied the reviewer's `grep -c <phone-config name>` and the controller's own ledger heredoc: finding 5 confirmed live.
Ruling: the controller fixes M1 itself (plan B1: "The controller builds it"); the re-review is still a separate rules-reviewer — if wrong, one extra review seat.
- M1 fix round 1/5: all Critical/Important + every Minor except the toast/catch test.
  - RED: new tests vs old rules → 11 fail / 13 pass. GREEN: 24 pass / 0 fail. tsc exit 0; validate passed.
  - Commit 5ea11fb.
Task M1: minor (deferred): no test for the toast or the fail-closed .catch (the test kit has no ui.toast implementation).
- P0-17 implementer: DONE_WITH_CONCERNS. Commits 2575300, 7e3dc02 on claude/P0-17 (BASE 83b89a8). 29 new tests; engine suite 1179 passed, 1 xfailed; no-key decide-pilot on real data → jev_pilot.json (85 groups, 391 materials, source none). typesafe-sdk 0.7.2 installed in main .venv; names checked by inspection.
  - Concerns: pilot.py written before its first test run (wrapper was red→green); extra engine/decide/pilot.py + Decision.error; unit-type truth compared in coarse classes; footprint_building from local OBJ bboxes; real network path never run; worktree pilot needs --source/--materials/--map/--env-file pointing at main checkout.
- M1 fix round 1/5 re-review: 13 addressed, 2 new Important (psql -d URI/conninfo passes; -t in MESSAGE_FLAGS drops cp -t/mv -t targets) + 4 minors (--out=, cat \.env, inVerified not reset, bare phone-config name = accepted trade-off).
- M1 fix round 2/5: RED 4 fail / 22 pass → GREEN 26 pass; tsc 0; validate passed. Fixes both Important + 3 minors.
Ruling: a bare `Corllenium-Phone-session-Config` word (no slash) is not treated as a path — it is usually a grep/log pattern; the session never runs from D:/PROJECTS — if wrong, one relative `ls` gets through.
- M1 fix round 2/5 re-review: all addressed; 3 new minors (git grep '\.env' denied; rsync -t taken as target; verified exemption leaks to sibling subshell).
- M1 fix round 3/5 (minors): RED 3 fail → GREEN 27 pass; tsc 0; validate passed. Commit on claude/M1 after a3ed9f1.
- Controller slip: `rm -rf <worktree>/.superpowers` after moving review packages deleted tracked files (P0-17: 109, M1: 114). Restored with `git checkout -- .superpowers`; both trees clean. Now only the package file is moved and the plan's empty folder removed.
- P0-17 review (rules-reviewer, opus): Spec ✅ Rules ✅ Approved; 8 minors. Concern rulings 1-6 accepted as the reviewer suggested.
Ruling: fix P0-17 minors 1-7 before merge (they change how the pilot numbers read: strict type accuracy, hint per row, hint labels, one client failure, CLI leak test, last .env line) — if wrong, one extra round of builder time.
- M1 fix round 3/5 re-review: all 3 addressed, no new Critical/Important. Verdict APPROVED.
Task M1: complete (commits fc0ab57..7b541c2, review clean after 3 fix rounds; 1 deferred minor: toast/.catch test).
Task M1: minor (deferred): `git add \.env` keeps its backslash now that git is a pattern verb (unlikely; a write, not a read).
- M1 queue: done → review --pass, so jobs.py shows "merged". The git merge into feat-dashboard waits for the peer's go (request sent).
- M2: claimed. Mod at dev-mods/.../uc-status (hooks/status.ts pure logic, hooks/register.tsx wiring, types/index.d.ts, tests/status.test.ts).
  - RED: stubs → 8 fail / 2 pass. GREEN: 10 pass. validate passed (tool.call hook given .catch). tsc exit 0.
  - Status line: branch · worktree · claimed jobs. Band: queue counts; files staged earlier this session that are dirty again in the main checkout; a reminder when a commit came after the newest .superpowers/sdd/*/progress.md change.
  - Still open: screenshot of real values (loads at turn end), repo copy + README, review.
Ruling: "the claimed job" shows every claimed job in the queue (both sessions claim as "Claude", so the queue cannot tell them apart) — if wrong, the line names one job too many.
Ruling: the ledger reminder compares against the newest progress.md of any plan — the queue has no session id — if wrong, the peer's ledger edit can hide our reminder.
- M1 merged into feat-dashboard: c22c952 (no-ff), after the peer's "go". uc-guard tests on the merged tree: 27 pass / 0 fail. Worktree .claude/worktrees/M1 removed. Peer told how to load the mod.
- Records: QUEUE.md rendered; HANDOFF §2 got its own dated Update block (the peer's left as is); a session-record history entry; spec line 42 ("DREX and TypeSafe are not used") brought in line with §9.
