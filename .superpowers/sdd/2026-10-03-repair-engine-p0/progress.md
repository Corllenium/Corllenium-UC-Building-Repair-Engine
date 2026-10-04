# SDD ledger — plan: D:/PROJECTS/UC MODEL FIXER/docs/superpowers/plans/2026-10-03-repair-engine-p0.md

Spec: docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md (2a748d4, approved by the owner 2026-10-03). Plan: 9ccd7d5.

## Pre-flight scan

| Pair / task | Produces → consumes | Found |
|---|---|---|
| T1 → T3, T4 | `AGENTS.md` sections 3-7 → skill and agent bodies link them; HERMES.md step 1 | consistent |
| T2 → T4, T6, Hermes | `jobs.py next --for --as`, `done --branch`, `render` → HERMES.md steps 2 and 7, Task 6 | names match |
| T7 → T8, T9, T11, T12 | `source.json`: `clean_obj.path`, `clean_mtl.path`, `textures`, `snapshots[].dir`, frozen `SRC-TEX/` under `source/<sha12>/` | consistent (T9 takes SRC-TEX next to the frozen MTL) |
| T8 → T10, T11 | `group_index.json` `split{name: tris, paths}` | consistent |
| T9 → T10, T12, T14, T15 | `materials.json` look keys | consistent |
| T12 modifies `engine/detectors/errors.py` (`timings=None`) | the result is unchanged when None (its own test) | no other P0 task edits errors.py |
| T14 → T16 | closed-room fixture appended at the END of `fixtures/build.py` | consistent |
| T13 → T15 | `engine/validate/targets.json` (check 2 is REPORT_ONLY until signed) | consistent |
| T2 self | 9 tests listed = "9 passed" | consistent |
| T7 self | 3 tests listed | consistent |
| Global constraint vs Tasks 1-5 | "every job on its own branch" vs. the queue not yet existing | **Ruling:** Tasks 1-5 run directly on `feat/repair-p0` (the controller, or one subagent at a time); job branches start with Task 6 — costs nothing |

## Progress
- Task 1: complete 3663629 (AGENTS.md single rules source, CLAUDE.md imports it, HANDOFF §4 + HERMES.md §2 link; tools/tests/test_agents_md.py 3 passed) -- done by the controller on feat/repair-p0
- Task 5: complete (pruned 3 stale worktree records; created .claude/worktrees/repair-p0 on feat/repair-p0 and .claude/worktrees/verified detached at 9ccd7d5; engine suite in verified running)
- Task 2: dispatched (implementer sonnet, worktree .claude/worktrees/P0-02 on claude/P0-02 from feat/repair-p0 @9ccd7d5)
- Task 4: complete cdb0cfc (HERMES.md §0 queue entry point, briefs/TEMPLATE.md, hermes/README.md report format, WORK-CLAIMS note; test_handover_docs 3 passed)
- Task 3: complete a9785a2 (3 skills + 5 agents; test_claude_assets 8 passed after fixing 2 agent bodies that lacked the literal 'never dispatch')
- Task 5 (cont.): verified worktree engine suite at 9ccd7d5 -- 633 passed, 1 xfailed (the known strict xfail), exit 0, 7 min 40 s
- Task 7: taken by the controller in .claude/worktrees/P0-07 (claude/P0-07 from a9785a2), before the queue exists (ruling above). Red: collection ImportError. Green: 3 passed.
  - Ruling: the plan's fixture wrote fake PNG bytes; the snapshot importer opens every texture with Pillow (texture_flatness), so the fixture writes a real 2x2 PNG -- the plan's test was wrong, not the code -- costs nothing; plan text to be corrected with the records.
  - Design note: textures are copied from the list the frozen MTL names (not by listing SRC-TEX), so the live tree is opened only through copy_verified; the 156 unused SRC-TEX files are not copied.
  - Real run started (read-only on the export; outputs in the main checkout's data/campus and data/snapshots); engine suite running in P0-07.
- Task 2: implementer DONE_WITH_CONCERNS a196f99 (claude/P0-02, base 9ccd7d5). Brief's 9 verbatim tests plus 39 extra; tools/tests 90 passed; 12 mutations caught; contention with 8 processes clean. The harness refused the subagent's report write, so the controller wrote task-2-report.md from its returned text.
  - Ruling (concern 1): Task 6 seeds P0-01..P0-06 first and walks each to merged (add, claim, done, review --pass) so later dependencies resolve; P0-06's who is `claude`. An absent dependency stays unsatisfied (typo safety) -- costs 6 extra queue rows.
  - Ruling (concern 3): keep test_jobs_extra.py -- it pins the CLI line format Hermes parses, the lock limits and the atomic save -- costs nothing.
  - Ruling (concern 8): `who` in {hermes, either} is how a job is "hermes-ok"; spec wording to be aligned in the records.
- Owner approved the Jev pilot (2026-10-03): plan Task 17 added (2b7a706); the owner sets TYPESAFE_API_KEY (an app restart is needed for this session's shells to see it); only text leaves the machine; never geometry, guard or Validator decisions.
- Task 7: complete pending review -- commit 7b6419d on claude/P0-07. Engine suite in P0-07: 636 passed, 1 xfailed. Real run 18:01-18:29 (28 min, 1 s stability wait per live file): 85 files, 1,766,906 triangles, 0 mismatches against the manifest; 379 textures, 0 missing; clean OBJ c1020bcf41f0; backup .skp ddecd020a826 (149,707,861 B), .skb 2c819a05c653 (149,707,906 B).
- Task 2 review (sonnet): Spec ✅; Quality needs fixes. Important: the lock wait spins at 100 % CPU when O_EXCL raises PermissionError with no lock file (no deadline check, no sleep). Minors:
  - the main_root test passes even with the wrong code in a main checkout;
  - the Windows retry and BOM paths are untested;
  - CLI stdout is cp1252 with CRLF, so piped `next` output carries a trailing CR -- matters for Hermes;
  - `--as` names are not checked for control characters;
  - `claim --for` is an extra, noted.
  Fix round 1 sent to the same implementer.
- Owner, 2026-10-03:
  - the local dashboard was DOWN for about 6 days (the containers exited about Sep 27, then a reboot with Docker Desktop not started); with the owner's OK, Docker Desktop was started and the same 3 containers brought up with `docker start` (db healthy first); health 200, errors v6 200 (version 2), /errors 200.
  - Jev pilot approved (P0 task 17); the owner sets TYPESAFE_API_KEY.
  - Jev in the engines: proposed decision hooks -- rules, then Jev as a suggestion, then the owner; a question type is promoted to automatic only at >= 95 % agreement over >= 50 cases; never for geometry deletion, guards or the Validator. To go into the spec and the P1 kernel.
  - Hosting: the dashboard, an agents API and GitHub automation, on a NEW small cloud VM with Docker. The owner creates the account; the API stays FastAPI. The Corllenium cPanel host is shared (no Docker, PostgreSQL 13, HTTP 508 at about 30 concurrent requests) and is not used.
  - GitHub record repo: Corllenium/Corllenium-UC-Building-Repair-Engine, PUBLIC by the owner's choice, full history and all branches. HierArch24 has READ only, so the owner must grant Write. gitleaks 8.30.1 over all 386 commits: no leaks.
- Task 7 review (sonnet): Spec FAIL -- `source.py` stat-ed the live tree (`src_tex.exists()`) outside snapshot.py. Quality needs fixes:
  - frozen folder named by the OBJ only (source.json hashes mismatched the frozen files after an MTL or texture change);
  - basename dedupe dropped same-name textures;
  - minors: rename race, rmtree, Windows paths and `..`, empty manifest or no backup accepted, relative paths.
- Task 7 fix round 1 (controller = implementer): 9 regression tests red, then 12 passed; commit 170b763.
  - New snapshot.copy_if_present, so the presence check stays in snapshot.py.
  - An access-audit test hooks os.stat, open, scandir and listdir under the export. Mutation check: putting a direct exists() back makes the audit FAIL with the offender named; restored.
  - Ruling: the frozen folder is `<sha12>-<asset8>` (the brief said `<sha12>`), mirroring snapshot_object's asset digest -- costs nothing downstream, since consumers read paths from source.json.
  - Ruling: `textures` keys are MTL-relative posix paths (`SRC-TEX/a.png`), not basenames -- Task 9 maps materials by their map_Kd path.
  - Added `rejected_textures` (paths leaving the export).
  - Engine suite re-running; the real freeze re-running with the fixed code (the old data/campus/source/c1020bcf41f0 folder in the old format stays as a harmless leftover).
- Owner: n8n runs on the Corllenium Hostinger VPS, which may also host the dashboard and agents API (its specs, or key-based SSH, are needed from the owner).
- Push to Corllenium/Corllenium-UC-Building-Repair-Engine: BLOCKED by the auto-mode classifier as [Data Exfiltration] when using the Siege project's token through with-env.mjs. Not worked around; tokens in D:\PROJECTS\Corllenium-Phone-session-Config deliberately not read. The owner was given 2 options: run the push themselves (exact commands given), or add a permission rule. The `corllenium` remote was NOT added (the whole command was denied).
- Task 2: fix round 1 done 118654a (lock wait: deadline check, then stale check, then always a 10-40 ms pause -- 200,001 spins/1.9 s became 43 attempts and a JobError at 1.01 s; main_root tested against a real linked worktree; Windows replace/unlink retries and BOM tested; CLI UTF-8 + LF (piped next = b'...hermes/A\n'); holder names one line; tools/tests 105 passed; 16 mutants caught). Re-reviews dispatched for Task 2 and Task 7.
- Task 2 re-review (sonnet): all 5 ADDRESSED, no new breakage, 63 jobs tests confirmed. Nits parked:
  - the second-stat live-lock guard is untested;
  - DEL, U+0085 and U+2028 are accepted in names;
  - a test leaves stdout reconfigured;
  - the give-up message wording under contention.
- Task 2: complete -- merged into feat/repair-p0 as 84d5914; tools/tests on the merge: 119 passed.
- Ruling: merge the reviewed foundation (feat/repair-p0: AGENTS.md, CLAUDE.md, HERMES.md entry, skills, agents, jobs.py, and Task 7 once its re-review passes) into feat-dashboard BEFORE the owner starts Hermes. Hermes is opened on the main checkout and must find the new HERMES.md and tools/jobs.py there. The end-of-P0 final review still covers everything. Costs one earlier merge.
- Task 7 re-review (sonnet): all 8 ADDRESSED, approved. Two minors fixed at once (9669ade):
  - drive-relative texture paths (`C:foo.png`, `C:../x.png`) are now rejected (any part with ":");
  - the audit now hooks lstat, os.open, access and io.open, plus a positive control (>10 accesses seen from snapshot.py).
  16 passed. Engine suite at 170b763: 645 passed, 1 xfailed.
- Task 7: complete -- merged into feat/repair-p0.
- Real freeze re-run with the fixed code (18:44-19:12): source.json created 19:12:52. 85 files, 1,766,906 triangles, 0 mismatches against the manifest; 379 textures keyed SRC-TEX/<file>, 0 missing, 0 rejected; frozen folder data/campus/source/c1020bcf41f0-8357ebc2; all paths absolute.
- Foundation merged into feat-dashboard (2126ce6). Queue seeded:
  - P0-01..05 and P0-07 walked to merged;
  - P0-06 claimed by Claude (completes when the first Hermes job merges);
  - P0-08..17 ready with who and dependencies.
  QUEUE.md committed (9051c1c).
- H1 (read-only VPS inventory) brief efcef1e, queued for Hermes (01cafff). HERMES.md: the owner may name a job (b41d7e7).
- Owner used Hermes to add the `corllenium` remote and push all 26 branches (around 18:30). Since then 4 are behind (feat-dashboard, feat/repair-p0, claude/P0-02, claude/P0-07) and claude/P0-11 is missing. Claude does not push there (classifier denial); the owner was given `git push corllenium --all`.
- P0-11 (SDK cross-check) dispatched (sonnet, general-purpose with the engine-builder role inline; the project agents load only at session start), worktree .claude/worktrees/P0-11 from e7fac71.
- QUEUE READY for Hermes: H1 (named), then P0-08 and P0-09 via "do the next job".
- H1 (Hermes, the first owner-started Hermes job) reviewed by the controller: report only, 4/4 items with real output, Hermes-Job trailer, no secret patterns. PASS; merged into feat-dashboard (c46ff0e). P0-06 done and merged (6afa11e).
- VPS facts (H1):
  - Ubuntu 24.04, x86_64; 2 vCPU (EPYC 9354P); 7.8 GiB RAM, 4.4 GiB available; 96 GB disk, 52 GB free;
  - Docker with Compose v5.3.0; Traefik on 80/443 with Let's Encrypt and the Docker provider (a new subdomain needs only labels on `n8n_default`);
  - busy: 3 n8n instances, the bext stack (with ollama), nfac, corllenium web and stage.
  Implication: the VPS hosts web + API + DB; heavy compute (census, find_errors, fix, validate) stays on this PC and its results are synced up.
- Owner: "jev I want him to decide and validate the facade". Answered: Jev is text-only and cannot see geometry; the facade proof stays with the Validator. Proposed addition: a close-up visual facade check (before/after renders of every outside wall compared by Gemini vision through Hermes), plus Jev deciding facade fixes (E5 winner, E8 opening). To go into the engines plan.
- Owner asked for Claude to "ping" Hermes directly: one-shot `hermes.exe -z <prompt> --in <main checkout> --usage-file data/hermes_runs/<run>/usage.json` (the same mechanism as auto_continue). Run 1003-1923-next started for the next queue job (expected P0-08).
- Owner asked to configure and run Anthropic's Prompt Audit (claude-api shared/prompt-audit.md) with a subagent as the work goes on: prompt-auditor agent + uc-prompt-audit skill + AGENTS.md §7 item 7 (0d2f15e; asset tests 13 passed). First full-surface audit dispatched (opus); report and proposed diff to docs/superpowers/records/prompt-audit/; nothing is applied without review, and §3-6 changes go to the owner.
- P0-08 (Hermes run 1003-1923-next): handed in ac953f0 on hermes/P0-08 for 1.63 USD (gemini-3.8-flash, 109 calls, 11.7 M tokens, mostly cache reads). Claims: red then 4 passed; test_cli 60 and tools 119 green; real run 179 paths, 225 runs, 85 splits, 85/85 matching names and triangle counts (1,766,906). Reviewer: hermes-reviewer (sonnet) re-runs everything in a scratch worktree. Hermes run 1003-1939-next started for the next job (expected P0-09).
- P0-08 review (hermes-reviewer, sonnet): CHANGES. Every number reproduces (85/85, 1,766,906, output sha equal to Hermes's) and the scope is clean. Problems:
  - the naming-rule and run-length tests pass even with the rules broken;
  - the fixture's quoted g-syntax is invented (real: `g Mesh7587 minecraft_quartz_block_side__1_29 Eds_2nd_Floor_obj Model`), and the report said "unsure about: nothing";
  - the comment misnames the slot after Mesh# (a group name in 162 lines);
  - index_by_split's odd int subclass;
  - a str path silently returns [];
  - the report has a stale hash and claimed counts without output.
  - Ruling: store the fuller path tokens[1:-1] (Task 10 needs inner named groups such as BRIDGE) and apply the owner's skip of that slot inside split_name, so the split stays exact -- costs one fix round.
  Notes sent with `jobs.py review P0-08 --changes`; Hermes fix run started (prompt names the job, worktree and notes).
- P0-09 (Hermes run 1003-1939-next): handed in dc54986 for 0.94 USD (79 calls): 10 tests; real run materials 391, textured 379, images 86, looks 97. hermes-reviewer dispatched.
- Lesson for Hermes briefs: the report's "Unsure about" must not say "nothing" when a fixture was invented rather than copied from the real file; the brief template could ask for the real sample lines to be pasted. Raise it in the next prompt-audit pass.
- Prompt audit #1 (full surface, opus): 21 findings, 10 with hunks, 11 flags. Report and diff in docs/superpowers/records/prompt-audit/.
  - Applied 399804f, the 13 non-AGENTS hunks:
    - F1: uc-handoff's YAML frontmatter was invalid, so its description never loaded; confirmed fixed in the skill list;
    - tools/tests now parses frontmatter with PyYAML; the old header raises ScannerError;
    - the prompt-auditor fetches with Python urllib, because curl is hook-blocked.
  - Owner decisions:
    - F5: the owner decides AGENTS.md §3-6; Claude may fix wording elsewhere and report it;
    - D10, D11, F14, F15, F16 approved and applied (40a69ae).
  - tools tests 121 passed; the AGENTS/asset/handover tests 16 passed.
  - Open flags for a later wording pass:
    - F6: HERMES.md §2 restates AGENTS.md and has drifted;
    - F7: the auto_continue prompt diverges (latent; it is rebuilt in P5);
    - F17: HERMES.md §3 is a 09-24 snapshot;
    - F18: "golden unit" means one set in uc-repair-rules (CHTM 5th + sidewalks) and another in the spec (CHTM 5th + 3 from the census);
    - F19: Claude's one-shot Hermes prompt hard-codes feat/repair-p0 (fix in the next prompt: use the base the brief names);
    - F20: the containers named in AGENTS.md are defined only in uncommitted files (another session's).
- P0-09 review (hermes-reviewer): CHANGES. The data is right: 391/379/86/97, every one of the 379 texture shas equals source.json, an independent partition gives the same 97 looks, materials.json sha 28a0e0d3. Problems:
  - the resolver tries the basename first, so same-name textures collapse;
  - absolute and `..` map_Kd paths are opened;
  - the CLI hard-codes the repo path and guesses paths;
  - 7 test mutants survive;
  - Tr is ignored;
  - the report has a stale hash and no suite line.
  Notes queued. The Hermes fix run waits until the P0-08 fix run ends (one Hermes run at a time until P5).
- Ruling: run the P0-09 Hermes fix in PARALLEL with the P0-08 fix -- P0-09 is on the critical path (P0-10, 12, 14, 17 wait for it); the runs use separate worktrees, branches and data files, and the queue file is locked -- costs about 1 USD and a small risk of the two runs interfering, mitigated in the prompt (each told the other's paths). The one-run-at-a-time rule stays for the automatic runner (P5). The prompt no longer hard-codes a base branch (audit F19).
- P0-08 fix round (Hermes 608d6e5, 1.46 USD): Hermes reports red 6/6 then green, 82 + 119 regressions passed, real campus-index 1,346 paths / 1,325 runs / 85 splits, 85/85 manifest match. Scoped re-review dispatched (hermes-reviewer, sonnet) on review-ac953f0..608d6e5.diff: the 7 notes, new breakage, acceptance re-run to scratch, and why paths rose 179 -> 1,346.
- Owner order (2026-10-03, mid-session): "the first model we tested in CHTM is that floor where you highlight colour-coded the errors; once we do that to all buildings we proceed to fix it ... it captures all errors we need to fix". Recorded in the spec §2 and plan Task 12: the census keeps each unit's whole error file (data/campus/errors/<unit>.json, the dashboard's format); showing every unit in the dashboard is a follow-up job that needs the owner's OK for the live DB; P3 fix runs start only after every building has its map.
- Ruling: queue P1-S1 (T-junction spatial hash) now, ahead of the P1 plan's order, on base feat/repair-p0 -- find_t_vertices is inside find_errors, so S1 makes the all-building error census (the owner's first priority) faster; S1's exit criteria (identical output, >=10x on CHTM 5th) do not need the census -- costs one Hermes run (~1-2 USD) and a small merge if P1's integration branch wants it later.
- Owner follow-up (2026-10-03): "coloring will take too much, that's for you, the record so that you know what you will fix; maybe after you fix I will have filters for each specific floor ... in the n8n workflow for every specific floor, if we create the proper engine flow script used for every building, we know what we will fix: what step, what script". Applied:
  - spec §2 and plan Task 12: the error files are the engines' record; no owner colouring or dashboard import now (the dashboard import, if wanted after the fix, needs the owner's OK for the live DB);
  - Task 12 adds a per-unit fix plan (kinds -> engines in pipeline order; E4/E5 by the look split);
  - spec §6: one engine flow for every floor, run as an n8n workflow on the VPS; compute stays on the PC; the PC-side runner pulls jobs (H2 designs the link).
- Profile, find_errors on CHTM 5th (20,599 tris, BLAS threads 1, cProfile on): 103.2 s total; double_layers 62.9 s (61 %), find_t_vertices 19.6 s over 2 calls, build_regions 12.5 s, detect_fragments 12.7 s (includes the 2nd find_t_vertices), rays 5.7 s. Both S1 and S3 should land before the census real run, or the 92-142 k units time out at 1,800 s.
- 2026-10-04 08:16 (session idle overnight):
  - P0-08 re-review: CHANGES, doc-only. Notes 1-6 addressed, code and data reproduce (6 red on ac953f0 then green; 82 + 119; full engine 655 + 1 xfail; campus-index byte-identical; 85/85). Left: stale hash 670aff5, unpasted output for depth 19 / 1,899 / 162, groups.py:15 line number, split_name default documented, shlex branch untested. 179 -> 1,346 paths is the expected effect of tokens[1:-1] (1,345 distinct slot names, 796 minecraft_*). Task 10 must assign by idx["split"], never by path tuple. Queued; Hermes doc round launched (data/hermes_runs/*-P0-08-fix2).
  - P0-09 Hermes fix run (20:13) was stopped by the 30-minute background limit, with +210/-42 uncommitted edits and no report. Relaunched with a 2-hour limit; continues from the edits and commits before the full suite.
  - P0-11 implementer: DONE_WITH_CONCERNS, HEAD 3ec7181, 12 commits.
    - Real check: 63 match, 18 mismatch (area only, backup larger, +0.51 to +2.09 %), 4 ambiguous (Science A twins), 0 miss.
    - The export lacks 90,391 tris (4.9 %), mostly backup duplicates; 5 files are unexplained.
    - Full engine suite: 754 passed, 1 xfail.
    - Rulings, in task-11-report.md: concern 1 (ctypes allow-list test widened) ACCEPTED; concern 2 (owner's split rule for matching) ACCEPTED; concern 3 (duplicated rule vs groups.py) PARKED to P0-08 merge; 04df3df committed red, noted.
    - Task review dispatched (rules-reviewer, opus) on review-e7fac71..3ec7181.diff.
- P0-08 round 2 (Hermes e2a4bd4, 0.47 USD): doc-only, as asked (report hashes, pasted output depth 19 / 162 / 1,899, groups.py:15 line 2214652, split_name docstring, a quoted-g-line test). Controller check: diff is comments, a docstring and one test; groups+source+cli 83 passed. review --pass; merged into feat/repair-p0 (5674331).
- Merged feat-dashboard into feat/repair-p0 (bd35e53) so P0 worktrees carry the current rules, plans and the owner's order.
- P1-S1 (Claude's tests, rolling-brief rule): 21 tests + docs/superpowers/records/scripts/tvertex_check.py on claude/P1-S1-tests (7ff3a4c, from feat/repair-p0 bd35e53). Validated before commit:
  - a throwaway grid prototype passes all 21;
  - 5 mutants fail (no tol pad -- caught only after adding the 600-height flat-edge test; huge cells; numpy int keys; all vertices as candidates; no hints);
  - the acceptance script with the prototype: identical True on A, B, CHTM 5th; CHTM 5th 4.82 s -> 0.75 s (6.4x, a per-edge Python loop), so the brief asks for vectorised pairs to reach >= 10x.
  - Brief docs/superpowers/records/briefs/P1-S1-tvertex-hash.md and the queue entry committed on feat-dashboard (b2803a8). Hermes run launched (data/hermes_runs/*-P1-S1).
- Prompt-audit note: the new briefs and Hermes one-shot prompts count as Hermes prompts (AGENTS.md §7.7). They are batched into one scoped audit before the P0 phase merge, rather than one audit per brief.
- P0-11 task review (rules-reviewer, opus): CHANGES. Spec ✅, rules ✅, no save path reachable; 150 passed; 7 mutants killed; skp-check.md byte-identical to render_markdown(skp_check.json).
  - IMPORTANT: unpairable families stay out of match/mismatch even when every candidate is outside tolerance. The Science A _obj1 files are ~17 % short and plan_2_obj1 is 12.5 in off in y; the summary's "ambiguous" definition is false.
  - 8 Minors: transform w row ignored; census probe opens any --skp; SourceUnstable not caught in the CLI; summary path not refuse_inside; child paths relative; family_of strips digits; writer docstring; zero_area_tris unreported.
  - Fix round 1 sent to the implementer (resumed) with all findings.
- P0-09 fix round 2 (Hermes 0e0054f + 62541e8, 1.36 USD, relaunched with a 2 h limit): 4 new tests red on dc54986, then 19 green; materials+source 35, tools 119; real run sha 28a0e0d3 unchanged; full engine 668 + 1 xfail. Scoped re-review dispatched (hermes-reviewer, sonnet) on review-dc54986..62541e8.diff.
- double_layers profile, CHTM 5th, 35 s: per-pair Python dominates (117,259 candidates, np.cross/plane_basis + shapely each; 13,947 kept); the all-pairs bbox stage is ~9 s and quadratic; renders 3.8 s.
- P1-S3 (Claude's tests): 19 tests + docs/superpowers/records/scripts/double_layers_check.py on claude/P1-S3-tests (2b9b0a4, from feat/repair-p0 5674331). Validated:
  - a throwaway grid prototype passes all 19 and is equal on sidewalks A and B (1.0-1.2x only, since its per-pair loop is still Python);
  - 5 mutants fail (offset buckets, all pairs per plane, unpadded cells, pairs by j first -- caught only after the chained three-layer test -- and pixels counted per chunk -- caught only with layers 0.05 apart).
  - Ruling: search by position, not by plane offset (the plan's wording), because tilted layers far from the origin defeat offset buckets -- costs nothing if wrong, since the tests decide.
  - Brief and queue e50d0fe; targets >= 3x CHTM 5th, >= 5x on the 91,714-tri unit, peak memory no higher. Hermes run launched in parallel with S1 (different files).
