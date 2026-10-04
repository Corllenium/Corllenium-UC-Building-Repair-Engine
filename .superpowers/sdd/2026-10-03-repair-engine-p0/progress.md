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
- P0-09 round-2 re-review (hermes-reviewer, sonnet): CHANGES on note 1 only (the basename fallback is unflagged; the probe shows a material silently taking another folder's bytes). Notes 2-6 addressed; 11 mutants killed; full engine 668 + 1 xfail; sha 28a0e0d3 reproduced.
  - Ruling: merge now and queue follow-up P0-09b (drop the fallback, plus two test-hygiene fixes) -- all 379 real textures resolve by exact path, so no data changes, while 4 jobs wait on P0-09 -- costs a later small materials.py change if wrong.
  - Merged into feat/repair-p0 (478326b); cli.py conflict with campus-index resolved by keeping both. After the merge: 102 targeted tests pass; campus-materials and campus-index both reproduce their committed files byte for byte (28a0e0d3, 1e470740).
  - P0-09b brief and queue entry: d396f5d, c8de489.
- P0-10 claimed by Claude; worktree .claude/worktrees/P0-10 (claude/P0-10 from feat/repair-p0 478326b). Implementer dispatched (engine-builder, sonnet). Report: task-10-report.md. Carried from P0-08's review: assign by idx["split"], never by path tuple.
- HERMES.md §2 and §3 wording fixed (5341a13, prompt audit F6, F17); handover tests 16 passed. To report to the owner.
- 2026-10-04 ~09:20: transient network timeouts (Errno 10060) cut off both Hermes runs (S1 after commit 97ee358, Item 1; S3 before any code) and the P0-10 implementer (API timeout after reading the brief). TCP 443 to Google and Anthropic checked OK at 09:22. Relaunched both Hermes runs with continue prompts (S1: before-baselines only from the base commit; S3: finish Item 0 first), and resumed P0-10 by message.
- P0-11 fix round 1: DONE (9 commits to 690e215, all findings addressed test-first with mutants; 181 focused, 785 + 1 xfail engine; real re-run 65/20/0/0). The hand-back is recorded in task-11-report.md (subagents cannot write report files: the Write tool refuses them, so the P0-10 agent was told to return its report as text). Scoped re-review dispatched (rules-reviewer, sonnet) on review-3ec7181..690e215.diff.
- Correction: HANDOFF §2's update header said 10:00; the real time is the commit time of d35b5a1. Fixed.
- P0-11 re-review (rules-reviewer, sonnet): PASS. All 9 findings addressed; 181 focused passed; old vs new on the stored walk gives exactly 4 Science A files changed; skp-check.md equals render_markdown(JSON); mutants caught. Residuals: relative --dll not resolved; the "Ambiguous" sentence omits the files > groups case.
  - done + review --pass; merged into feat/repair-p0 (76d74bb). cli.py conflict resolved by keeping all three campus commands. After the merge: 283 targeted tests pass, and --help lists 7 commands.
  - Ruling: residuals plus parked concern 3 (pin skp_check's split rule to groups.py) go to follow-up P0-11b (hermes); brief and queue 8248566.
- P0-14 claimed; worktree .claude/worktrees/P0-14 (claude/P0-14 from 76d74bb). Implementer dispatched (engine-builder, sonnet); the report comes back as text.
- Hermes queue: P0-09b and P0-11b ready. They launch when the S1 and S3 runs end (two Hermes runs at a time).
- P1-S1 handed in by Hermes (97ee358 code, e1863ee report; continuation run 0.58 USD).
  - 31 passed; full engine 670 + 1 xfail.
  - tvertex_check identical True x3: A 15.2x, B 23.3x, CHTM 5th 26.4x (pairs 522,061 vs 173,409,192).
  - Before and after sha256 equal (base-code baselines): chtm5 errors 237ddd85, A e724822f, B ebeea4ed.
  - find_errors on CHTM 5th: 98.1 s -> 76.2 s.
  - Review dispatched (hermes-reviewer, sonnet) on .superpowers/sdd/2026-10-03-repair-engine-p1-p2/review-7ff3a4c..e1863ee.diff, including a run on the 142,234-tri unit.
- Hermes runs launched: P0-09b and P0-11b (small, disjoint files), alongside P1-S3.
- P0-09b handed in by Hermes (d5f4132, 0.85 USD): the basename fallback is removed and the new test was red on the base; two tests are tightened, with both mutants shown failing; materials+source 36 passed; the real output sha is 28a0e0d3. Review dispatched (hermes-reviewer, sonnet) on review-76d74bb..d5f4132.diff.
- P0-11b handed in by Hermes (c8fcd35 + 2067bc3, 1.17 USD): --dll resolved; the Ambiguous sentence is complete; split_path added with a pin test (0 differences over 1,346 paths); 105 passed. Review dispatched (hermes-reviewer, sonnet) on review-76d74bb..2067bc3.diff, with a check that split_path is a thin adapter, not a second copy of the rule.
- P0-09b review (hermes-reviewer, sonnet): PASS. Every claim reproduced, all six mutant variants fail the new tests, and all 379 textures resolve by exact path. Merged into feat/repair-p0 (715b64c); 36 passed after the merge.
  - Parked Minors: the new test pins only the tex_dir half of the removed fallback (an mtl_path.parent/rel.name re-add survives); the report's base hash 76d74bb17d84 and commit 157435b are wrong (pre-amend).
  - Ruling: HERMES.md step 6 now says never amend, and copy hashes from git log after the last code commit -- the second stale-hash report (P0-08 had 670aff5) -- costs nothing.
- P0-11b review (hermes-reviewer, sonnet): PASS. compare() on the saved walk hashes identically on base and branch (65/20/0/0); split_path is a two-line adapter; the pin skips cleanly without the index. Merged into feat/repair-p0.
  - Parked Minors, for the end-of-P0 review: split_path is test-only code (drop it, use key(*reversed(p))); the pin covers this index, not the regexes (also assert AUTO/KEY pattern and flags equal); the module docstring and the definition wording miss "no more files than groups".
- Ruling: P0-12 goes to Hermes now, Steps 1-4 plus a 3-unit smoke run into data/census_smoke/. Step 5 (all 85) is held for Claude until S1 and S3 merge -- the census real run must use the fast code, or the 92-142 k units time out -- costs a separate run step later.
- P1-S1 review (hermes-reviewer, sonnet): PASS.
  - Identical on 81 of 87 real units, 3,600 fuzz scenes, tol 0-10 in and degenerate tables.
  - 142,234-tri unit: old 865 s, new 3.25 s (266x), 5.2 M pairs, 522 MB tracemalloc peak.
  - Important follow-up: pair lists are unbounded Python lists (~37 B/pair).
  - Minors: the report text ("bounded cell", "pure NumPy") is inaccurate; no docstring; a dead branch; 3-D diagonals cost (extent/cell)^3 lookups; t differs in the last bit (no decision flips in 210 M pairs).
  - review --pass; merged into feat/repair-p0 (89098ee); 31 topo tests pass; full engine suite running on the integration branch.
  - Ruling: merge now, with follow-up P1-S1b (memory bound + clean-ups) for Hermes -- real units peak at 522 MB, fine for the census at --jobs 4 -- costs a later small change.
- Full engine suite on feat/repair-p0 at 89098ee (P0-08, 09, 09b, 11, 11b, P1-S1 merged), BLAS threads 1: 836 passed, 1 xfailed in 610 s.
- P0-10 implementer: DONE_WITH_CONCERNS (10 commits to 2a86b40).
  - 79 units (69 floor, 3 element, 7 site), 4 split proposals, 85/85 splits covered, 1,766,906 tris.
  - Known cases: 4 of 5 met. Main_Infra came out as 3 parts, not 7; the Science A duplicates appear only at a 0.5 in identity tolerance.
  - The brief's constants failed on real slabs (19.7-54 in thick) and were changed, each measured.
  - 738 + 1 xfail engine.
  - Rulings in task-10-report.md:
    - the 0.5 in identity is allowed (read-only comparison key, not a weld; both exact and tolerant numbers reported; never used to merge);
    - the constants are accepted;
    - Main_Infra 7, CHTM L12 and the weak tables go to the owner via P0-13.
  - Task review dispatched (rules-reviewer, opus) on review-478326b..2a86b40.diff.
- P0-14 implementer: DONE_WITH_CONCERNS (ce5aa37, 9e4d3a6, 8f8ffee, ecbcb30).
  - 40 tests; engine 851 + 1 xfail; mutation-checked per rule; independence enforced by an AST import test.
  - Smoke on sidewalk A and CHTM 5th: 1.25-2.4 M sample-viewpoint pairs/s.
  - Concern 1: 181 of 1,577 CHTM 5th probes (11.5 %) sit inside walls; the headroom ray cannot tell air from a solid taller than 83 in.
  - Ruling: fix before review (a correctness concern) with a majority back-face filter over 26 rays per candidate. A reversed ceiling then keeps its probes, because only the up ray sees a back face. Fix round 0 sent with tests (a)-(d) and a measurement. Costs one round if wrong.
  - Ruling: roof and terrace probes are kept (stricter is safe).
  - Concerns 3-12 carried to P0-15: the E5/E4 allowed-change class for the inward copy, the best-conditioned viewpoint, chunked casting, probes from BEFORE reused for AFTER.
- P0-10 task review (rules-reviewer, opus): CHANGES. Spec ✅, rules ✅.
  - Outputs verified: z_range parts partition MAIN_BUILDING and Main_Infra exactly; the md is byte-identical; the JSON is equal.
  - Important 1: 4 rules untested (slab window, lowest base, 100 in storey collapse, look key in the fingerprint).
  - Important 2: KeyError at inventory.py:543 for an element in band 0 below every floor.
  - 5 Minors: the missing flag attaches to every unit of a group; chained 0.5 in identity (a 1.17 in cluster) and its wording; the footprint second condition not stated in the md; member sha256 copied, not hashed; SITE pairs never compared.
  - Fix round 1 sent to the implementer (resumed) with all findings.
- P0-12 handed in by Hermes (1579a76 code, 16c6ba0 + e147fd2 report, 2.01 USD).
  - 9 census tests; engine 824 + 1 xfail; tools 121.
  - Smoke on 3 units into data/census_smoke/ in 76 s. CHTM 5th fix plan: E8 346, E3 12,870, E1 1,055, E2 29, E4 6,522 (pairs), E5 7,425 (pairs), E6 3,884, E7 null.
  - Review dispatched (hermes-reviewer, sonnet) on review-39a1275..e147fd2.diff: the timings=None path is byte-identical, the errors file format is the CLI's, pair vs face units are labelled, and the child processes are robust.
- Hermes run launched: P1-S1b (memory bound for the T-junction search), alongside P1-S3.
- P0-14 fix round 0: DONE (2513c1e).
  - Majority back-face vote: CHTM 5th probes 1,577 -> 1,397; 177/181 flagged dropped, 4 on-plane ties kept.
  - The open floor is untouched (all 1,386 zero-back probes kept); 4 other real floors are similar.
  - Engine 860 + 1 xfail.
  - The controller viewed chtm5_probes_after_vote.png: regular lattice kept, drops on wall lines.
  - Task review dispatched (rules-reviewer, opus) on review-76d74bb..2513c1e.diff; report in task-14-report.md.
- P0-14 task review (rules-reviewer, opus): PASS.
  - Visibility semantics verified with hand-built scenes; the vote keeps a reversed-ceiling room and drops probes inside walls.
  - CHTM 5th: 1,397 probes, deterministic.
  - Throughput 1.43 M pairs/s. The estimate for 500 k samples x 1,600 viewpoints is 1.6 GB and about 9.3 min per mesh.
  - Important, carried to P0-15: reversed walkable floors get no probes (closed_room with a reversed floor: 0 of 20; CHTM 5th: 6 cells).
  - 7 Minors carried: the step-off jumps < 0.02 in layers; check_caster faces equality; _rows shape; face id validation; LEVEL wording; 2 surviving mutants; trimesh near-parallel first_hit.
  - done + review --pass; merged into feat/repair-p0 (7211b82); 49 tests pass after the merge.
- P0-15 claimed; worktree .claude/worktrees/P0-15 (claude/P0-15 from 7211b82). Carried items in task-15-carried.md (6 required, plus design notes). Implementer dispatched (engine-builder, sonnet).
- P0-10 re-review (rules-reviewer, sonnet): PASS. All 7 findings addressed; reverts and the probe verified; the md is byte-identical and the JSON has 0 differing leaves.
  - done + review --pass; merged into feat/repair-p0 (a15c466). cli.py conflict resolved by keeping campus-skp-check and campus-inventory.
  - After the merge: 269 targeted tests pass, and the real run's md equals the committed blob (the working-tree copy is CRLF by autocrlf).
- P1-S3 Hermes run stopped at the 2 h limit, with commit 276d3a9 (the grid) plus uncommitted optimisations (cell size, a 2D box pre-filter, plane clustering). The controller ran the S3 tests on that state: 19 passed. Relaunched to commit, then run Item 2 (acceptance on 4 snapshots, before/after sha, full suite) and the report, with no more optimisation unless a target fails.
- P0-12 review (hermes-reviewer, sonnet): CHANGES.
  - Verified: step-1 tests red on base; timings=None byte-identical; errors files byte-identical to the CLI; E4+E5 = 13,947 pairs; robust children.
  - Important:
    1. a missing materials map falls back silently to material names (CHTM 5th E4/E5 6,522/7,425 by name vs 6,966/6,981 by look);
    2. Science A units are classified as SITE;
    3. error units render as zero rows, and the run reports completed with exit 0;
    4. __import__("ctypes") dodges the ctypes-confinement test.
  - Minors: plan units unlabelled; FIX_PLAN_TABLE unused; summed time shown as wall time; census.json written only at the end.
  - Rulings:
    - the census uses inventory.py's prefix table (one rule) after merging feat/repair-p0 into its branch;
    - a missing look map is an error;
    - the Windows probes move to engine/campus/winprobe.py, allow-listed in test_skp_writer.py (an existing-test edit allowed by ruling);
    - census.json is written after every unit.
  - Notes queued; Hermes fix run launched (3 Hermes runs now: S3 finish, P1-S1b, P0-12 fix).
- P1-S1b handed in by Hermes (6efd262, acb78c5, 32c8a86 report; 1.12 USD).
  - Bounded numpy pair chunks: the 142 k unit peaks at 279.7 MB (was 499); full-scan fallback for long edges.
  - 33 passed; engine 838 + 1 xfail.
  - tvertex_check identical True x4: CHTM 5th 24.3x, 142 k unit 403x.
  - Review dispatched (hermes-reviewer, sonnet) on review-89098ee..32c8a86.diff.
- P1-S1b review (hermes-reviewer, sonnet): CHANGES.
  - Exactness confirmed: 155 runs; the 142 k digest equals P1-S1's; peak memory follows the chunk size.
  - Important: buffer overflow after a flush when an edge's candidates exceed the 65,536 buffer (a 270x270 grid + diagonal at chunk 80 k raises ValueError; the default is safe below ~500 k vertices, so every real unit is safe).
  - Important: the many-candidates branch is untested.
  - Minors: the diagonal test has no T-vertex; chunk_pairs < 1 gives a cryptic error.
  - Notes queued; Hermes fix run launched.
  - Not on the census path: S1 itself is merged and correct.
- P0-12 fix round (Hermes 51accbc merge + 8 commits to 955fb78, 3.06 USD): all 7 notes.
  - Smoke "3 units (3 ok, 0 timeout, 0 error) ... 43.92 s wall (51.60 s unit sum)"; CHTM 5th E4 6,966 / E5 6,981 pairs by look.
  - Census tests 13; engine 982 + 1 xfail; tools 121.
  - Scoped re-review dispatched (hermes-reviewer, sonnet) on review-51accbc..955fb78.diff.
- P0-12 re-review (hermes-reviewer, sonnet): CHANGES on note 1 only.
  - Notes 2-7 and the merge are addressed: building_of on all 85 stems, ERROR/TIMEOUT rows and exit codes, the winprobe allow-list exact, atomic writes survive a kill, E4/E5 6,966/6,981.
  - Left: _run_worker (census.py:313-325) falls back to the snapshot's materials.mtl and swallows errors, so a missing or empty --materials still reports ok.
  - Notes queued; Hermes fix round 2 launched.
- P1-S1b fix round (Hermes a800430..6a63975, 1.24 USD): all 4 notes; the grid test reproduced the ValueError on 32c8a86; 38 passed; tvertex identical x3 (CHTM 5th 30.8x); engine 843 + 1 xfail. Scoped re-review dispatched (hermes-reviewer, sonnet) on review-32c8a86..6a63975.diff.
- P1-S3 finish run stopped at the 2 h maximum (11:24-13:24). The code was committed (9e34d77: cell size, 2D box pre-filter, plane clustering), with no report.
  - Cause: the acceptance script's tracemalloc pass on the OLD function for the 91,714-tri unit is far too slow -- Claude's script design.
  - No orphaned processes: Hermes.exe 25944 is the owner's desktop app; 60092 is the P0-12 fix2 run.
  - Ruling: the controller runs the acceptance itself (AGENTS.md §7.5 requires a controller re-run anyway): each double_layers call in its own process, peak working set via GetProcessMemoryInfo, equality by digest; Item 0 after-runs on 9e34d77 into data/s3_check/after2.
  - The S3 before-baselines equal S1's independent before-baselines (237ddd85, e724822f, ebeea4ed).
  - Then a short Hermes run writes the report and runs the full suite.
- P1-S1b re-review (hermes-reviewer, sonnet): PASS. All 4 notes; 630 resize combinations, 0 failures; exact on CHTM 5th and on the 270x270 grid (its oracle ran 1,895 s). Merged into feat/repair-p0.
- P1-S3 controller acceptance, part 1 (on 9e34d77):
  - S3 + overlap tests: 42 passed.
  - Item 0 after-runs into data/s3_check/after2: sha256 EQUAL to before for chtm5 errors (237ddd85), A report (e724822f) and B report (ebeea4ed).
  - find_errors on CHTM 5th: 55.7 s wall with S3 alone (98 s before).
  - The per-call step failed first on Claude's own ctypes signature bug (argtypes missing for GetProcessMemoryInfo); fixed, tested on one call, and the 8 calls re-launched.
- P0-12 fix round 2 (Hermes f87dd8e + 5c74d44, 2.03 USD): the worker fallback was deleted; two worker tests were red on 955fb78; census 15 passed; CHTM 5th E4/E5 6,966/6,981; engine 984 + 1 xfail. Re-review dispatched (hermes-reviewer, sonnet) on review-955fb78..5c74d44.diff.
- P1-S3 controller acceptance, part 2 (9e34d77; each call in its own process, BLAS 1):

  | Unit | Equal digest | Old | New | Speed-up | Peak WS old -> new |
  |---|---|---|---|---|---|
  | A | yes | 7.46 s | 4.84 s | 1.5x | 205 -> 219 MB |
  | B | yes | 7.82 s | 4.16 s | 1.9x | 209 -> 233 MB |
  | CHTM 5th | yes | 34.25 s | 10.13 s | 3.4x | 477 -> 497 MB |
  | Gymnasium_5th_floor_and_roof (91,714 faces) | yes | 543 s | 168 s | 3.2x | 668 -> 1,250 MB |

  - Targets: exactness met; CHTM 5th >= 3x met; 91 k >= 5x NOT met; new peak <= old NOT met.
  - Ruling: merge for the census (exact and 3.2-3.4x faster; units stay far below the 1,800 s timeout), with a follow-up S3b for speed and memory -- the census runs at fewer jobs because of memory -- costs one follow-up job.
  - In flight: Hermes writes the report and runs the full suite (no code); hermes-reviewer reviews the code (2b9b0a4..9e34d77) and the memory culprits; the controller profiles the new function on the 91 k unit for S3b.
- S3 profile, new double_layers on Gymnasium_5th_floor_and_roof (91,714 faces), cProfile, 179 s:
  - set.update 97.2 s (163,702 calls): candidate-pair dedupe in a Python set;
  - double_layers' own Python 25.6 s;
  - ndarray.tolist 9.6 s (122,943) and triu_indices 11.9 s (122,942): per-cell pair building;
  - dict.setdefault 4.0 s (6.1 M): per (face, cell) entry;
  - shapely intersection 6.6 s (one vectorised call); renders ~12 s.
  - S3b direction: build (face, cell) entries with numpy, generate pairs per cell vectorised, and dedupe with np.unique on int64 keys (i*N + j). This also cuts the memory, since a Python set of millions of ints is the likely 1,250 MB peak.
