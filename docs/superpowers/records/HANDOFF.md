# HANDOFF — how any agent (Hermes, Claude, a person) continues this work

Read this whole page before touching anything. It is kept current by whoever works last; the
"Current state" section carries a timestamp. If it is older than the newest commit on
`feat-dashboard`, trust `git log` and the ledger tail over it.

Companion files:
- `docs/superpowers/records/2026-09-24-session-record.md` — the goal, the map of which engine file
  handles which error, the full history with measured results. Read section 1 and 3 first.
- `docs/superpowers/records/WORK-CLAIMS.md` — who is working on what right now. **Claim before you
  start, release when you stop.**
- `docs/superpowers/records/briefs/` — complete, self-contained task briefs, numbered in queue order.
- `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/progress.md` — the ledger: every ruling and
  measurement in order. Append to it after every step.

## 1. What the owner wants (one paragraph)

Clean the SketchUp OBJ exports of the CHTM sidewalk (file A `CHTM_SIDE_WALK_2nd_floor`, snapshot
`data/snapshots/ce26e0392ab0`; file B `CHTM_2nd_to_3rd_building_sidewalk_outside`, snapshot
`data/snapshots/0b290ec0bcb4`) into clean solid slabs for Unity: remove (not hide) hidden inside
faces, triangle edges on flat surfaces, stacked duplicate layers and stray fragments; never delete a
side mesh, rebuild broken or missing sides; only the model's outline edges may be visible. After every
run the latest `.skp` of each file must be in `OBJ FIXED RESULT/` for the owner to check in SketchUp
2026. Work visually: every round ends with renders that are looked at, not only numbers.

## 2. Current state (2026-09-26 00:15, written by the Claude controller)

**Update 2026-10-19 22:00 (claude-argon, STAGING-ENGINE-4-5-V2):** owner-requested MAIN INFRA floors 4 and 5 run on freshly updated `MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.blend` into `MAIN-INFRA-FLOORS-4-5-ENGINE.blend`, work dir `engine-7floors-4-5-v2`. Because a live Blender session re-saves V2 (21:50:57 and 21:56:50), the run reads the sha256-checked copy `MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-215650.blend` (`0d3ffedb…d8a8`). Launched 21:59 (PID 47836); export done 21:59 (4F 45,004 tris, 5F 34,464 tris); 4F engine running. See [STAGING-ENGINE-4-5-V2-report.md](STAGING-ENGINE-4-5-V2-report.md).

**Update 2026-10-19 21:10 (claude-vertex-opus, STAGING-ENGINE-1-6-7-V2):** owner-requested MAIN INFRA floors 6, 7 and 1 run into `MAIN-INFRA-ALL-FLOORS-ENGINE-STAGED.blend`, work dir `engine-7floors-v2`. The V2 input is re-saved by a live Blender session, so the run reads the hash-checked copy `MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-210156.blend`. Launched 21:08 (PID 41992); export done 21:25; 1F done 21:33 (16,354 -> 7,217 tris), 6F done 22:23 (30,518 -> 15,712 tris), both guards failed on 26 of 26 views; 7F next. See [STAGING-ENGINE-1-6-7-V2-report.md](STAGING-ENGINE-1-6-7-V2-report.md).

**Update 2026-10-19 (codex-sol, STAGING-ENGINE-2-3):** owner-requested MAIN INFRA floors 2–3 run started against FIXED-CUTS-V2, isolated artifacts in `engine-7floors-2-3`. Export complete; repair pending. Current runner rejects obsolete `--stage-failed`; equivalent default stages all floors. See [STAGING-ENGINE-2-3-report.md](STAGING-ENGINE-2-3-report.md).

**Update 2026-10-17 (Codex, STAGING-T123-V1):** synchronized the two missing Blender staging test files from siege-jev-gate to main; all five requested files now have identical SHA-256s. The five requested pytest modules pass in each checkout (81 passed each). Receipt and read-only Blender inspection pass: 12 CHTM floors, self-contained buildings staging, restored ARCHI ceiling present, current environment CHTM LOD0 99,310 triangles; all three `.blend` hashes unchanged. Both CHTM runners compile/import, but `run_chtm_3rd_and_4th_floors.py` lacks a `--stages` CLI. That pre-existing untracked file remains untouched pending the owner's exception. Details and actual output: [STAGING-T123-V1-report.md](STAGING-T123-V1-report.md).

**Update 2026-10-09 afternoon (the repair-engine controller session): P2 started.**
- **P2-E8a merged** (76ca35a): solidify as the strict E8 engine; `engine.cli repair-unit`. Covered after rollback 0 on
  sidewalks A and B and CHTM 5th; most pieces rolled back (kept 4/66, 10/54, 8/209).
  - Owner questions open: (1) should the Validator judge every line of sight to a sample (both sides) instead of one?
    (2) may a kept piece be visible itself when it hides nothing?
- **P2-E8b merged** (ed278b7): the narrow flat fill. No real hole qualifies before E6 joins the T-junctions (ruling
  R9); the fill measurement and the pictures follow E6. The Validator's one named class `fill_site` re-measures
  every limit itself; `validate --edit-log` gives it the fills.
- **P2-E8c merged** (9cae2d2): `needs_modelling.json` per unit (sidewalk A 143 spots, sidewalk B 142, CHTM 5th 395)
  plus the read-only SketchUp helper `tools/sketchup/needs_modelling_views.rb`. The helper has not been run in
  SketchUp yet; it waits for the owner's OK to try it once on a working copy.
- **E3 merged** (7258652): hidden faces, interior-aware, with a dense pre-filter. Its output still showed small
  visible patches under a denser check, which led to the owner's floor.
- **The Validator judges to the owner's floor (P2-V2, merged 0795710):** 4 pixels at 0.02 in per pixel per face
  per viewpoint, every line of sight, both sides; outside views only at or above the horizon (owner, 2026-10-10);
  the corner false positive is gone. CHTM 5th with E3 takes 24-30 minutes to validate (the lattice's casting);
  a cheaper cast is a follow-up.
- **The Unity floor pipeline** (spec `docs/superpowers/specs/2026-10-10-unity-floor-pipeline-design.md`, approved;
  plan `docs/superpowers/plans/2026-10-10-unity-import-check.md`): U1-B (the mirror Unity project) merged; U1-A
  (the Python check) with Hermes, fix made, hand-in pending; U1-C next.
- **Hermes jobs:** U1-A (changes made, not handed in), P2-H2 (ready).
- **Next:** the golden-floor proof run with the new judge, then an E3 fix round if needed, U1-C, and E1/E2/E4/E5/E6/E7.
- **P2-K0 merged** into `feat/repair-p1p2` (b43d27f): kernel prep for the new engines.
  - A new engine's stage that does not PASS is rolled back whole.
  - The edit log works for any engine.
  - Only E8 may add faces, and only the legacy observer may set the legacy marker.
  - A face with no material is its own look, `material:<none>`.
  - Suites: engine 1715 passed, tools 123. Byte-identical on sidewalks A and B.
- **P2-E8a in progress:** the strict solidify engine.
  - Ruling E8-R1: the guard's `cover_max_exposure` stays 0.10. The owner's "0 % visible" rule is enforced by the Validator, one site per rebuilt piece, with eye-height probes.
  - A piece that covers anything visible is rolled back; its hole goes to E8b or E8c.
- **Next:** E8b narrow flat fill, E8c needs-modelling queue, then E3, E1, E2, E4, E5, E6/E7.

**Update 2026-10-09 (the repair-engine controller session): phase P1 is complete and merged.**
- **`feat-dashboard` = c88ac1c + records.** It merges `feat/repair-p1p2`.
  - The end-of-P1 review (opus) found it READY TO MERGE; the fix round is e5d774d.
  - Suites: 1811 passed, 1 xfailed.
  - Ledger: `.superpowers/sdd/2026-10-03-repair-engine-p1-p2/progress.md`, which holds every ruling.
- **P1 delivered:**
  - **The repair kernel** (`engine/repair`):
    - typed edits, with the UVs and normals of new faces;
    - today's `fix_object` split into seven observe-only stages, byte-identical;
    - the Validator's focus mode, plus a conservative site judge (`engine/site_judge.py`);
    - per-stage site checks: attribute each failure, roll back the charged sites, confirm (`fix --kernel --validate-sites`).
  - **The Decider** (`engine/decide/decider.py`): owner > rules > providers, SUGGEST/AUTO; plus the Jev provider
    (AskProvider, from the Jev session).
  - **The topology memo, and hardening:**
    - one look-based flicker split;
    - `refuse_protected` on every writer;
    - `campus-unit-before` for whole-unit validation;
    - the SDK never opens the backup itself.
- **First per-stage verdicts (CHTM 5th, legacy stages, not rolled back):**
  - solidify covers 13,350 visible samples;
  - hidden removal deletes about 22,000;
  - orientation flips 274 to the wrong side;
  - the merge shifts UVs on 8,441.
  - These are the requirements for the P2 engines.
- **Incident 2026-10-09 10:21:** a sub-agent ran `taskkill /IM python.exe`, which ended every Python process on the
  PC; the Jev session's windows-mcp server was lost.
  - Recorded as project memory: stop only your own processes, by PID.
  - The uc-guard rule M1c (kill only by PID) is merged into feat-dashboard: ba11fb5, 2026-10-09, owner OK, reviewed,
    37/37. A session that loads uc-guard is denied `taskkill /IM`/`/FI`, pkill/killall, `Stop-Process -Name` and
    by-name Get-Process stops.
- **Reviewer launches:** some were refused by the permission check. The ledger names each review the controller did
  itself (K1 fix round, D1, K1b, K3b, S2).
- **Next:** P2. E8 strict solidify comes first, then E3, E1, E2, E4, E5, E6/E7, and V1/R1.

**Update 2026-10-08 late night (the Jev + mods controller session): P1-D2 merged; Jev sits behind the Decider.**
- **P1-D2 is merged into `feat/repair-p1p2` (3a2421b, by the repair-engine session):** engine + tools 1602 passed,
  1 xfailed.
- **`engine/decide/providers.py`:**
  - `AskProvider("jev", RemoteDecider(url) | JevDecider())` is a Decider provider. It returns SUGGEST answers only, and
    sends the owner source to `UNAVAILABLE`.
  - A per-run circuit breaker trips on a call-level failure, so a hung VPS costs one timeout.
  - `sync_confirmed(decider, data/decide/confirmed)` turns `decide-pull` files into `record_owner`.
- **`decider.py`:** an `Unavailable` marker, owner-approved. A temporary "cannot answer" (Jev off, unreachable) is
  logged and never cached, so switching Jev on takes effect at once. There is also a read-only `owner_answer`.
- The Decider chain is complete on P1: owner > rules > Jev (SUGGEST) > owner queue.

**Update 2026-10-08 night (the Jev + mods controller session): "Jev on the VPS" is built and merged; Jev stays off.**
- **`feat-dashboard` = e2a37ee:** `feat/jev-vps` is merged.
  - Spec: `docs/superpowers/specs/2026-10-08-jev-vps-service-design.md`.
  - Plan: `docs/superpowers/plans/2026-10-08-jev-vps-service.md`.
  - Ledger: `.superpowers/sdd/2026-10-08-jev-vps-service/progress.md`.
- **Built (J1-J8, each reviewed, plus a final whole-branch review):**
  - the `uc-fixer-decide` service (`deploy/vps/decide/`) with Postgres schema `decide`;
  - `RemoteDecider`, `decide-pull` and `decide-import-pilot` in `engine/decide/`;
  - the `/jev` review page;
  - the VPS compose service, nginx routes and runbook (`deploy/vps/README.md`).
- **Tests:** engine 1275 passed, 1 xfailed; service 153 + 114 skipped (Postgres pass 267); web 151.
- **End-to-end check, local and throwaway:** the import added 370 rows (85 groups × 4 + 30 materials), with no
  mismatch against the pilot. The cache hit from the real classifiers. Roles are enforced: nginx refuses
  `uc-engine` outside `/api/decide/`.
- **Browser check:** the `/jev` page at 375 and 800 px, with accept and change working.
- **Jev is OFF** (`DECIDE_JEV_ENABLED` unset). It is switched on only when the repair engine is ready, with the first
  live question `repair.next_step`, by the owner's decision.
- **Owner, open:**
  - **the VPS deploy:** the runbook steps, with the owner's explicit OK; he types the `uc-engine` password and the
    TypeSafe key himself;
  - **spec §3/§4 review:** the text was updated to match the build (uc-engine may also call import and health; the key
    and state_json definitions; `accepted` = owner-confirmed only);
  - **M2 `uc-status`:** check its status line;
  - **M3:** yes or no;
  - **an empty test Docker volume** (12f52767…) to remove;
  - **untracked files:** `Dockerfile.web` and the root `nginx.conf` are untracked, and the web-image step uses them.
- **Next:** P1-D2 (`AskProvider` behind the Decider, reserved for this session), once `feat-dashboard` reaches
  `feat/repair-p1p2`.

**Update 2026-10-08 evening (the repair-engine controller session): phase P0 is complete and merged.**
- **`feat-dashboard` = 8163bb0 + records:** `feat/repair-p0` was merged after the end-of-P0 final review.
  - The review (opus) found the branch ready to merge. A fix round followed and was re-reviewed PASS.
  - A scoped prompt audit of the briefs was applied.
  - Suites on the merged tree: 1320 passed, 1 xfailed.
  - P0 delivered: source freeze, group index, material looks, inventory, SDK check, census, Validator v0 with
    signed targets, agents/skills/queue, colour export, Jev helper with its pilot, and speed jobs S1/S3.
- **Correction recorded:** the census `flicker_diff` / `flicker_same` split pairs by material, not by look. The
  colour export now says MATERIAL. E5's different-look work is the census `flicker_split`, 514,573 pairs. P1-H1
  pins the look-based E4/E5 definition before the engines use it.
- **Jev pilot** (`data/campus/jev_pilot.json`):
  - when confident, building right 97.5 %, floor-or-not 98.6 %, floor number 95.3 %;
  - materials 74 % confident.
  - Owner deck: https://claude.ai/artifact/Fzc6Pu5W6iRnkndxBFimqV (private).
  - Owner decision open: where Jev helps first.
- **Parked:** four untracked Hermes report copies are on the branch `wip/main-untracked-hermes-reports`.
- **Next:** P1. Kernel K1 onward per `docs/superpowers/plans/2026-10-03-repair-engine-p1-p2.md`, plus P1-H1.

**Update 2026-10-08, end (the Jev + mods controller session): the Jev pilot is complete; the plan is done except the owner's answers.**
- **`feat/repair-p0` = 430f397** (P0-17b merged by the repair-engine session): engine + tools 1314 passed, 1 xfailed.
- **The full pilot** (from P0-17b, `python -m engine.cli decide-pilot --env-file`): 57 calls, 0 failed, 20.9 s.
  At confidence ≥ 0.8, against the owner-confirmed campus map:

  | Question | Accuracy | Coverage | Accuracy when accepted |
  |---|---|---|---|
  | Building | 96.5 % | 95.3 % | 97.5 % |
  | Type | 93.7 % | 89.9 % | 97.2 % |
  | Floor | 92.8 % | 92.8 % | 95.3 % |

  Materials: 289 of 391 accepted (74 %). The footprint hint alone is right 90 % of the time; Jev reaches 96.5 %.
  Output: `data/campus/jev_pilot.json`.
- **Merged into `feat-dashboard`:** M1 `uc-guard` (c22c952) and M1b, the `--env-file` exemption (b8df4ce).
- **M2 `uc-status`:** approved on `claude/M2` (90eeb6d); it merges after the owner's on-screen check.
- **Owner, open:**
  - decision 4, where Jev stays: map pre-fill, material categories for E5, review tie-breaks, review order;
  - M3, yes or no;
  - the M2 status-line check;
  - rotate the TypeSafe key, which was pasted in chat once.

**Update 2026-10-08, later (the Jev + mods controller session): P0-17 merged; the first real Jev pilot ran.**
- **P0-17 merged into `feat/repair-p0` (b1c66a2, by the repair-engine session):** engine + tools 1308 passed, 1 xfailed.
- **Key:** the owner's `.env` line was named `typesafe=`. It was renamed to `TYPESAFE_API_KEY=` by a script that printed
  only booleans. The wrapper finds it.
- **Pilot, materials (valid):** 391 materials, 290 accepted at confidence ≥ 0.8 (74 %). Stone 132, concrete 96,
  metal 29, glass 17. A 30-item spot check found every accepted answer right. 0.33 s and about 3.6k tokens per call
  of 20 questions. Output: `data/campus/jev_pilot.json`.
- **Pilot, group names (not valid yet):** all 17 batches got HTTP 400, because the API allows at most 10 Score levels
  and the floor question had 16. The fix, job **P0-17b** (the floor as a Choice, limits checked before any call), is
  in progress. After it, the pilot is re-run.
- **M2 `uc-status`:** approved after 2 fix rounds. One of them stopped a `git status` from taking the shared
  `index.lock`. Waiting on the owner's on-screen check, then the merge.
- **M1b:** lets `uc-guard` accept `python -m engine.cli ... --env-file`, so the engine can read the key. In review.

**Update 2026-10-08 (the Jev + mods controller session): M1 `uc-guard` merged; P0-17 under fix; M2 built.**
- Plan: `docs/superpowers/plans/2026-10-08-jev-and-claude-mods.md`; ledger `.superpowers/sdd/2026-10-08-jev-and-claude-mods/progress.md`.
- **M1 merged into `feat-dashboard` (c22c952):** `tools/claude-mods/uc-guard/`, a Claude Code mod. It denies:
  - writes to the CKPT17 export, master or backup;
  - a bare `cd`;
  - `git add -A` / `.`, `commit -a`, a bare `stash`, a force push;
  - compose/docker restarts of `fixer-*`, and `psql` on the live `fixer`;
  - reading `.env*`;
  - writes to the result folders outside `verified`.

  rules-reviewer approved it after 3 fix rounds; 27 tests. Load it with
  `claude --plugin-dir "D:/PROJECTS/UC MODEL FIXER/tools/claude-mods/uc-guard"`. It is live in this session through hot reload.
- **P0-17 (Jev wrapper) on `claude/P0-17`:** rules-reviewer approved it, minors in fix. `typesafe-sdk` 0.7.2 is in
  `.venv`. The `decide-pilot` run without a key works on the real data (85 groups, 391 materials, source "none").
  The real pilot waits for the owner's key in the repo-root `.env`.
- **M2 `uc-status`:** built (status line plus band, 10 tests); the screenshot check and review are next.
- **Owner, open:** the key line in `.env` (then say "key in"); after the pilot, decision 4 (where Jev stays) and
  whether to build M3.

**Update 2026-10-08 (the repair-engine controller session): P0-13, P0-16 and P0-18 merged; colour export published.**
- **`feat/repair-p0` = 83b89a8**, engine + tools suites 1273 passed, 1 xfailed.
  - P0-13: the owner's answers (`docs/superpowers/records/campus/decision-sheet-p0.md` §8) and the signed
    `engine/validate/targets.json`. Check 2 now gates: flicker x2, reversed and cracks must be 0; hidden, loose
    and open edges are listed.
  - P0-16: Validator mutation proof, the `floor-validator` agent and the `uc-validate-floor` skill
    (prompt-audited). Real v0 verdicts: CHTM 5th and sidewalks A and B all FAIL; record
    `docs/superpowers/records/campus/validator-v0-verdicts.md`.
  - P0-18: `engine.cli campus-errors-skp`. One colour-coded `.skp` per building plus SITE, with every error
    kind and grouping problem on its own tag.
- **Published (from `.claude/worktrees/verified` at 83b89a8):** `MODEL FIXER ENGINE FILES\04-COLORING\<BUILDING>\`
  holds `<BUILDING>-errors.skp` and its `.json` report, 10 files in 143 s with 0 faces refused. `_renders\` holds
  an all-buildings sheet and the decision-6 pictures (BRS-L05 obj vs obj1, BRS-L08).
- **Owner, open:**
  - decision 6 (BRS_5th obj1, BRS_9th obj1), with the pictures now in `_renders\`;
  - UV tolerance by texture contrast (P0-16 record);
  - the Supabase project; the GitHub repo creation; the htpasswd login.
- **Another controller session ("3d uc building repair engine (jev implementation)")** runs
  `docs/superpowers/plans/2026-10-08-jev-and-claude-mods.md`. It takes P0-17, M1, M2 and M3, keeps its own
  ledger and its own dated block here, and asks before merging into `feat/repair-p0`.
  - The owner's TypeSafe key goes in the git-ignored repo-root `.env`; agents never open `.env`.
- **Next for this session:** the end-of-P0 final review, then `feat/repair-p0` into `feat-dashboard`, then the P1
  kernel K1.

**Update 2026-10-04 09:03: the UC Repair Engine program (P0) is under way.**
- **What it is.** One repair engine per error kind, run over every floor of every building of CHECKPOINT-17.
  Each floor is validated by the owner's rule (`AGENTS.md` §6). Per building there is a comparison `.skp`
  in `MODEL FIXER ENGINE FILES\05-FIXING\`.
  - Spec: `docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md`.
  - Plans: `docs/superpowers/plans/2026-10-03-repair-engine-p0.md` and `...-p1-p2.md`.
  - Ledger: `.superpowers/sdd/2026-10-03-repair-engine-p0/progress.md` (every ruling is there).
- **Rules and roles.**
  - `AGENTS.md` is the one rules source.
  - Every job is in the queue (`tools/jobs.py list`; `docs/superpowers/records/QUEUE.md`).
  - Hermes takes `hermes`/`either` jobs, with Claude laying out the briefs and failing tests, reviewing and
    merging.
  - Integration branch for P0: `feat/repair-p0` (worktree `.claude/worktrees/repair-p0`).
- **Owner order (10-03):** the error map of every floor comes first. It is the engines' record of what to fix,
  with a fix plan per unit, and the per-floor flow runs as an n8n workflow. Fix runs on real buildings start
  only after that.
- **Done:** P0-01..09 and H1 merged. Data in `data/campus/`: `source.json` (85 splits, 1,766,906 tris),
  `group_index.json`, `materials.json` (97 looks).
- **In flight:**
  - P0-10 inventory (Claude);
  - P0-11 SDK cross-check, fix round 1. It found that the export lacks 90,391 tris against the backup, mostly
    backup duplicates, with 5 files unexplained; this goes to the owner's decision sheet P0-13;
  - S1 and S3 speed jobs (Hermes, against Claude's committed tests);
  - P0-09b queued.
- **Measured:** `find_errors` on CHTM 5th takes 103 s; `double_layers` is 61 % of it and `find_t_vertices`
  19 %. S1 and S3 must land before the census (P0-12), or the 92-142 k-tri units time out.

**Update 2026-09-26 23:30: the 3D error filter is merged and live.**
- **Merge.** `feat/error-filter` was merged into feat-dashboard as 0bfd433. The branch is on GitHub too.
- **The live images run 0bfd433** (API and web), rebuilt at 23:27.
  - Rollback images: `:pre-20260926-6`.
  - Backups:
    - database: `data/backups/fixer-20260926-2325.dump`;
    - the owner's verdicts: `validation-20260926-2325.json`;
    - the old CHTM errors file: `errors-version-6-20260926-2325.json`.
  - No migration ran.
- **What it is.** The workspace has an Errors column:
  - Find errors per version;
  - a legend of 7 kinds, with an (i) per kind that opens the Errors page's window, plus a facade layer;
  - isolate, blink, worst spots with fly-to;
  - a click on a face shows its kinds and the faces it fights;
  - real textures (toggle U).

  Plan `docs/superpowers/plans/2026-09-26-3d-error-filter.md`; ledger
  `.superpowers/sdd/2026-09-26-3d-error-filter/progress.md`.
- **CHTM 5th floor (model 2, version 6).** Its errors file was recomputed with `ERRORS_VERSION` 2 (37.5 s):
  - flicker 5,668 (texture on texture) + 4,793 (same material);
  - reversed 29, hidden 12,870;
  - zero-area and stray bits 1,055 (1,055 zero-area, 0 fragments, 0 slivers);
  - open edges 346, cracks 3,884, facade 5,765.

  An errors file from an older `find_errors` answers 404 "not computed yet", so the panel offers Find
  errors again.
- **After a reboot the dashboard stays down.** The machine rebooted at 22:31, and the containers' restart
  policy is "no". Bring it back with `docker start fixer-db fixer-api fixer-web`, in that order, waiting
  for the database to be healthy. Do not use `compose up`: the database container predates the compose
  file's last change and would be recreated.
- **Parked**, with the rulings in the ledger:
  - `classify_edges` downgrades some real open edges (engine; needs its own brief with A/B
    re-verification);
  - an in-flight guard on POST errors;
  - a memory bound on the flicker pixel stage;
  - the spec gaps M9;
  - `api/tests/test_health.py::test_settings_host_port_data_dir` fails in the main checkout because it
    reads the local `.env`. The owner started that fix as its own session.

**Update 2026-09-26 12:55: the Errors page is live** (`http://localhost:5190/errors`).
- The owner asked where the Errors & fixes documentation page was: only its spec existed. It was then
  redesigned with the owner (11:55-12:15) into a planning catalogue:
  - 10 kinds of error and 10 engine mistakes;
  - each kind opens a floating window (what it is, how it is found, why the Minecraft Little Tiles
    export has it, how much of each model, why unwanted in Unity, the solution, what was done, why some
    remain);
  - the owner gives a verdict per kind and model.
  Nothing in any model is fixed in this phase; the next phase plans scripts, engine work and machine
  learning against these verdicts.
- Plan `docs/superpowers/plans/2026-09-26-errors-and-fixes-page.md` (Tasks 1, 2, 8, 9, 10, 11); ledger
  `.superpowers/sdd/2026-09-26-errors-and-fixes-page/progress.md`; branch `feat/errors-page` in
  `.claude/worktrees/errors-page`.
- `feat/errors-page` was later merged into feat-dashboard (dee9801). The live images now come from
  feat-dashboard: see the 23:30 update above.
  - The first deploy of the page (API 2b63a26, web 3ac8331) has rollback images `:pre-20260926` and the
    database backup `data/backups/fixer-20260926-1246.dump`.
- **Data (git-ignored, never committed):**
  - The owner's 32 screenshots are in `data/errors_doc/img`, with `owner_images.json`, zipped to
    `data/backups/errors_doc-2026-09-26.zip`.
  - The owner's verdicts go to `data/errors_doc/validation.json`, written by the page. Read it before
    planning any fix.
- **Measured today, read-only:**
  - find_errors on A and B, as exported and as shipped: `data/errors/A-raw.json`, `A-after.json`,
    `B-raw.json`, `B-after.json`. They show errors left after the engine: A hidden 66, reversed 24,
    flicker faces 40, cracks 32; B hidden 27, flicker 4, cracks 25.
  - Edge classes: open edges A 250 → 378, which is not traced.

**Update 2026-09-26 11:40: the owner reopened the session for the 3D error filter** (understand a
building's errors in the dashboard, CHTM 5th floor as the example; nothing is fixed by it).
- Spec `docs/superpowers/specs/2026-09-26-3d-error-filter-design.md`; plan
  `docs/superpowers/plans/2026-09-26-3d-error-filter.md`; ledger
  `.superpowers/sdd/2026-09-26-3d-error-filter/progress.md` (force-added copy goes in with the records).
- Work happens on branch `feat/error-filter` in the worktree `.claude/worktrees/error-filter`. Tasks 1-5 are
  complete; order of the rest: 6, 12, 14, 8, 7, 9, 10, 13, 11. Task 11 (the controller's) rebuilds the
  dashboard by section 8 and shows the owner.
- CHTM 5th floor is in the live dashboard as model 2, version 6 (snapshot c0c877002500).

**The owner closed the session at 00:10 ("finish what we finish for now").**
- Nothing is running: the brief-15 agent is stopped, the auto-continue runner is stopped (STOP file,
  watcher ended), and Claude's scheduled auto-resume is cancelled.
- The main checkout has no uncommitted engine work. `docker-compose.yml` and the Docker files at the
  root stay uncommitted: another session wrote them.
- Branch `feat-dashboard` holds everything committed; see "Open work" below for where to pick up.

The owner's decisions of 21:45 are carried out:
- **Live database backed up** to `data/backups/fixer-20260925-2150.dump`.
- **The 6 `version_assets` rows** with backslash paths were rewritten to forward slashes (`UPDATE 6`).
- **The dashboard was rebuilt** from committed 281a569 (section 8):
  - nginx now has `proxy_read_timeout` / `proxy_send_timeout` of 600 s.
  - `fixer-api` and `fixer-web` were recreated at 21:55, and the API migrated the live database from
    0001 to 0002_flat_materials when it started.
  - The live model now loads in the container: every version's meshbuf returns 200 through nginx.
  - The old images are kept as `ucmodelfixer-api:pre-20260925` and `ucmodelfixer-web:pre-20260925`.
  - The container writes no `.skp` (there is no SketchUp DLL on Linux), so the owner's files still
    come from native runs.
- **One copy of each stacked, opposite-wound, same-material surface may be removed**: brief 13.

Owner files (refreshed 23:53 and 23:54 into `data/output_verified`) are built from the COMMITTED head
ab22ff3, which is brief 11's end, in the clean worktree `.claude/worktrees/verified`:
- File A: 881 triangles, back faces from outside 18,348 px, `.skp` sha256 31d4440c4270…
- File B: 513 triangles, 2,869 px, sha256 bd874b3573c7…
- Both passed, with all invariants true.
- The numbers equal brief 11's own runs. To refresh them from committed code again: in
that worktree `git checkout --detach <commit>`, then run `engine.cli fix` with
`--out "D:/PROJECTS/UC MODEL FIXER/data/output_verified" --skp-dir "D:/PROJECTS/UC MODEL FIXER/OBJ FIXED RESULT"`
for both snapshots (the file must not be open in SketchUp).

Done in the session:
- **Brief 11** is DONE_WITH_CONCERNS: 15 commits, 4019987..ab22ff3; 607 passed, 1 xfailed (M2). A has
  881 triangles and 18,348 back px, B 513 and 2,869; both passed. Its concerns are in
  `remaining-visual-defects-report.md`.
- **Merged:** the dashboard wave (cba42a5), and brief 12 (f885fd9, Hermes pass 5, reviewed).
- **Brief 15 item 1** is committed (3c54e77): every run reports `double_layers`.
- **The owner's files** come from committed ab22ff3.

Open work, in the order to pick it up:
1. **A read-only review of briefs 11 and 13 together**, with probes, as in every round.
   - Brief 11's biggest concerns: R10-I1 costs A two 2 in walls at x 2680, so the slab edge is a knife
     edge again; R10-I2 adds 112 back px on B; M2 is pinned as an xfail.
2. **Brief 15 item 2** (one wall per side plane, for no flicker) is parked UNVERIFIED on branch
   `wip/brief15-one-wall` (1795d38).
   - Its 7 tests passed, but the full suite and the real runs never ran.
   - Continue from that branch: suite, both real runs with `double_layers` before and after,
     close-ups, then merge after a review.
3. **Brief 13's branch `feat/coincident-pairs`** is not merged; it waits for the review in item 1. Its
   rule works but removes nothing today. Brief 14's measurements are on the same branch.
4. **Leftovers** (brief 06), and the D9 move of `_write_guard_images` to `engine/guard/render.py`.
5. **To turn automatic continuation back on:** `tools/auto_continue.py resume`, then `watch` in the
   background (section 7).

**If you take over one of these** (for example because Claude hit its usage limit): follow the
lapse rule at the top of `WORK-CLAIMS.md`, take the claim over in writing, run `git status` and
`git log` in that tree, and continue from the brief's remaining items. Uncommitted work in a tree is
work in progress: finish it, test it, commit it; never discard it.

## 3. The queue (do in this order)

| # | Brief | What | Status |
|---|---|---|---|
| 1 | `briefs/01-T1-tjunction-repair.md` | T-junction repair | DONE (28d63df, 03df53d, report 437e4ef) |
| 2 | `briefs/02-SR-side-rebuild.md` | side rebuild SR0-SR6 | DONE on feat/side-rebuild (fafd4d6), merged by brief 03 |
| 3 | `briefs/03-reconcile-and-verify.md` | merge the side rebuild, rerun, verify | DONE (68f6d15 + a89f771, 82adc60, ca463c2; report f8e72bb); 542 passed; A 1,044 / B 530 passed |
| 4 | `briefs/04-review.md` | review part 1 DONE (review-since-b2134e9.md); review 2a of Hermes's commits DONE (review-hermes-fixes.md); **part 2 (the side rebuild and the merge) NEXT** | read-only |
| 5 | `briefs/05-dashboard-fix-wave.md` | dashboard fixes D1-D12 | DONE by Hermes (passes 1-4, three reviews); merged as cba42a5 |
| 6 | `briefs/06-leftovers.md` | smaller leftovers | any time a slot is free |
| 7 | `briefs/07-review-fixes.md` | fixes from review part 1 | DONE by Hermes (merge 19f97cc) |
| 8 | `briefs/08-review2a-fixes.md` | fixes from review 2a | DONE (536fca7..d570927, report 64023ad) |
| 9 | `briefs/09-sliver-ray-confirmation.md` | rays through each debris piece, folds | DONE (3386c4f..d9673c1) |
| 10 | `briefs/10-side-rebuild-followups.md` | side rebuild gaps + review part 2 findings | DONE (9f64ae9..f7e27d1, report daeb84c) |
| 11 | `briefs/11-remaining-visual-defects.md` | margin-strip winding, broken undersides, B region 107, B4, B8 | DONE_WITH_CONCERNS (4019987..ab22ff3); review next |
| 12 | `briefs/12-dashboard-followups.md` | re-review 3 follow-ups M1-M4 and nits (API owner-copy block, tests) | DONE by Hermes pass 5; reviewed (engine 573, API 44, web 47, 5 of 5 mutation checks); merged as f885fd9 |
| 13 | `briefs/13-coincident-pairs.md` | one copy of each exactly stacked, opposite-wound, same-material surface (owner's decision 09-25 21:45) | DONE_WITH_CONCERNS on `feat/coincident-pairs` (not merged; review together with brief 11): the rule works but removes nothing at 281a569, where A's landing is already one layer |
| 14 | `briefs/14-zfight-sources.md` | what still z-fights on A: riser pair x 1305.14, same-wound duplicate z 1779.53 | DONE, measured and not fixed (9f39e7f): A 28 double layers (3,723.5 sq in, 141 px), B 2; all are export sides drawn twice; the fix is brief 15 |
| 15 | `briefs/15-one-wall-per-side-plane.md` | one wall per side plane where the export drew a side twice; `double_layers` in every report | item 1 committed (3c54e77); item 2 parked unverified on `wip/brief15-one-wall` (1795d38); stopped by the owner |

## 4. Rules (each one cost time when broken)

**Since 2026-10-03 the binding rules live in [`AGENTS.md`](../../../AGENTS.md) §3, with the blocked
operations in §4, the owner's decisions in §5 and the owner's validation rule in §6.** The list below is
the same text, kept for history. If the two ever differ, `AGENTS.md` wins.

- **Python**: always `.venv/Scripts/python.exe` from the repo root, run modules with `-m`
  (`-m pytest`, `-m engine.cli`). In a worktree use the main checkout's interpreter
  `"/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"` from the worktree root, and set
  `PYTHONPATH` to the worktree root for any plain `python script.py` (otherwise it imports the main
  checkout's engine).
- **Never touch**: any untracked file you did not create, the live export folder
  `D:\PROJECTS\UC ENVIRONMENT BUILDING\...`, the owner's campus model
  `D:\PROJECTS\UC\02-SKETCHUP\current\...skp`, and the running servers: the Docker containers
  `fixer-api` (8190), `fixer-web` (5190 and 5180, nginx) and `fixer-db` (Postgres 16, 5490).
  Rebuilding or restarting them, and any write to the live database `fixer`, is the owner's decision.
  The owner approved the 2026-09-25 rebuild (section 8).
- **API tests** (`pytest api`): since cba42a5 each session makes its own `fixer_test_<pid>_*` database
  and drops only its own (and ones left by dead processes), so runs of this code may overlap. A
  worktree or container on an older commit still drops the one shared `fixer_test`: never overlap two
  runs of such old code. Never touch the live database `fixer`.
- **Shared working tree**: other sessions edit this folder. Stage files by name, never `git add -A`
  or `git commit -a`. Big features go in their own worktree and branch; the controller merges.
  Foreign uncommitted edits get parked on a `wip/` branch, never discarded. Worktree `corllenium`
  (branch `corllenium/p1-ingest`) belongs to another session: leave it alone.
- **The owner's folder `OBJ FIXED RESULT/` holds only files built from COMMITTED code.** Every
  real-data run during work passes `--skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"`; after
  committing, refresh the owner's files from the clean worktree `.claude/worktrees/verified` (section 2).
- **Test-first**: write the failing test, see it fail, implement, see it pass. Commit after every
  item so a cut loses nothing.
- **Guards are never loosened by argument.** A change to what the guard tolerates must name the
  change and MEASURE it (example: border shifts are tolerated only up to the merge's own 0.15 in,
  measured per pixel). Only `engine/fixes/solidify.py` may invent vertices; the merge never moves or
  invents one.
- **Visual pass every round**: read `data/output/<name>/qa/*.png` and render the `.skp` with
  `docs/superpowers/records/scripts/render_skp.py`, audit it with `skp_edge_audit.py`, and say what
  you see. A log line is not evidence.
- **Records**: after every step append to the ledger, update section 2 of this page and the session
  record's history, and commit them (`git add -f` for files under `.superpowers/sdd/`).

## 5. How to verify a round (copy these)

```bash
.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider
.venv/Scripts/python.exe -m engine.cli fix data/snapshots/ce26e0392ab0 --out data/output --skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"
.venv/Scripts/python.exe -m engine.cli fix data/snapshots/0b290ec0bcb4 --out data/output --skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"
.venv/Scripts/python.exe -m engine.cli preview-data data/snapshots/ce26e0392ab0 --out preview/data
.venv/Scripts/python.exe -m engine.cli preview-data data/snapshots/0b290ec0bcb4 --out preview/data
PYTHONPATH="$PWD" .venv/Scripts/python.exe docs/superpowers/records/scripts/skp_edge_audit.py "data/skp_scratch/CHTM_SIDE_WALK_2nd_floor.fixed.skp"
PYTHONPATH="$PWD" .venv/Scripts/python.exe docs/superpowers/records/scripts/render_skp.py "data/skp_scratch/CHTM_SIDE_WALK_2nd_floor.fixed.skp" data/skp_render/A
```

Without `--skp-dir` the run writes the owner's `OBJ FIXED RESULT/`, which must hold only files built
from committed code (section 4).

Read in `data/output/<name>/report.json`: `tris_after`, `passed`, `invariants` (all true),
`merge_report.rolled_back` (must be false), `guard_final.totals` (holes, material_changed,
moved_same_flat, moved_other must be 0; edge_flicker within its cap; border_shift, zfight_tie,
crack_closed, fragment_removed are tolerated classes), `solidify_report.cap_guard_passed`.

## 6. Handing back

When you stop (limit reached, owner says Claude is back, or the job is done): commit at a clean point,
release your claim in `WORK-CLAIMS.md`, update section 2 here with what is done and what is left,
append to the ledger, commit those three files.

## 7. Automatic continuation while Claude is at its usage limit

`tools/auto_continue.py` runs outside Claude, so it keeps working when Claude's usage limit stops every
Claude agent. The Claude controller starts it in the background after every restart of the app:

```bash
.venv/Scripts/python.exe tools/auto_continue.py watch    # checks every 5 minutes, acts, supervises
.venv/Scripts/python.exe tools/auto_continue.py status   # what it sees and would do now; changes nothing
```

The rule it follows is written in `WORK-CLAIMS.md` (automatic continuation). In short, when Claude is
cut with the reset at least 45 minutes away, the running brief job goes to Hermes on branch
`hermes/auto-<run>` in `.hermes/worktrees/auto-<run>`, with the job tree's uncommitted work copied in
and a prompt that carries section 4's rules. Reviews stay with Claude. Everything a run did is in
`data/auto_continue/<run>/` (`prompt.md`, `hermes.out`, `usage.json`, `wip.patch`, `run.json`), one line
per event in `AUTO-CONTINUE-LOG.md`, and Hermes's report in the branch at
`docs/superpowers/records/hermes-auto/<run>-report.md`.

When Claude comes back:
1. Run `status`, read `WORK-CLAIMS.md` and `AUTO-CONTINUE-LOG.md`. Do not resume a job Hermes holds.
   To take it back early: `tools/auto_continue.py stop --kill` (the row is released as STOPPED with
   Hermes's commits so far), then `tools/auto_continue.py resume` so later cuts are covered again.
2. Review the branch `hermes/auto-<run>` like any worker's (a read-only reviewer with probes).
3. Merging it into `feat-dashboard`: the job's work in progress is STILL uncommitted in the job's tree;
   the runner copied it and did not move it (`data/auto_continue/<run>/wip.patch` is the copy). Park it
   first (`git stash push -- <those files>`), merge, check that nothing in the parked copy is missing
   from the merged files, and only then drop the stash.
4. Then continue the brief (claim the row again) and refresh the owner's files from the new commit.

Tested by `tools/tests/test_auto_continue.py` (a fake Hermes in a throwaway repository); run
`.venv/Scripts/python.exe -m pytest tools/tests -q -p no:cacheprovider`.

## 8. Rebuilding the Docker dashboard (only with the owner's OK)

The compose file builds from `.`, the main checkout's working tree. That tree holds other agents'
uncommitted work, so build the images from a clean worktree of a COMMIT instead. In git bash, set
`MSYS_NO_PATHCONV=1` for any `docker exec` that passes a container path.

```bash
git -C .claude/worktrees/dk checkout --detach <commit>
cp Dockerfile.api Dockerfile.web nginx.conf .dockerignore .claude/worktrees/dk/
pnpm --dir .claude/worktrees/dk/web install --frozen-lockfile
pnpm --dir .claude/worktrees/dk/web exec vitest run src/utils/errorsDoc.test.ts   # the Errors page's content must be valid
pnpm --dir .claude/worktrees/dk/web run build
docker exec fixer-db pg_dump -U fixer -d fixer -Fc -f /tmp/fixer.dump
docker cp fixer-db:/tmp/fixer.dump data/backups/fixer-<date>.dump
cp data/errors_doc/validation.json data/backups/validation-<date>.json   # the owner's verdicts (if the file exists)
docker tag ucmodelfixer-api ucmodelfixer-api:pre-<date>
docker tag ucmodelfixer-web ucmodelfixer-web:pre-<date>
docker build -t ucmodelfixer-api -f .claude/worktrees/dk/Dockerfile.api .claude/worktrees/dk
docker build -t ucmodelfixer-web -f .claude/worktrees/dk/Dockerfile.web .claude/worktrees/dk
docker compose -p ucmodelfixer up -d --no-build api web
```

- `pg_dump` and `docker cp` make the backup, before anything else touches the database.
- The two `docker tag` commands keep the old images, so a rollback is one command.
- The API runs `alembic upgrade head` on the live database when it starts.
- Check `docker logs fixer-api`, then that `/api/versions/<id>/meshbuf` returns 200 through port 5190.
