# SDD ledger — plan: D:/PROJECTS/UC MODEL FIXER/docs/superpowers/plans/2026-10-08-jev-vps-service.md

Spec: docs/superpowers/specs/2026-10-08-jev-vps-service-design.md (owner-approved 2026-10-08, sections 1-4 + "build now, Jev off").
Integration branch: feat/jev-vps from feat-dashboard d78ff24. Jobs J1-J8 queued; J1 claimed.

## Pre-flight scan
| Pair / task | Check | Finding |
|---|---|---|
| J1 → J2/J6/J7 | jev.py question fields + wire codec consumed by service and client | same names in all tasks (qtype, subject, question_to_json, question_key) — clean |
| J2 → J3 | Store protocol method names | identical list in both tasks — clean |
| J2 → J4 | logic.answer/review/reask/import_items signatures; reask raises PermissionError | J4 maps PermissionError → 409, ValueError → 400/422, KeyError → 404 — clean |
| J4 → J8 | endpoint paths and bodies | table in J4 matches J8's client — clean |
| J6 → J7 | the HTTP helper for import | J7 reuses J6's auth/timeout helper — clean |
| J7 vs spec | spec: pilot import covers groups + 30 materials (file lacks the rest) | amended spec, plan matches |
| J5 | nginx snippet: `location = /api/decide/ask` with an `if` | exact-match location wins over the prefix; the service also checks roles — clean |
| J8 vs spec | spec said component tests; repo has no component-test lib | spec amended: logic in TS modules + Vitest |
| Each task | its tests vs its code | consistent |

Ruling: the service enforces roles from X-Remote-User and nginx additionally restricts /api/decide/ask to uc-engine; the container publishes no port, so only nginx can set the header — if wrong, a container on the internal network could forge the header (none exists besides the stack's own).
Ruling: J2 test runs use PYTHONPATH "$PWD;$PWD/deploy/vps/decide" (Windows separator) — if wrong, one test command needs the other separator.

## Log
- J1: claimed; worktree .claude/worktrees/J1 (claude/J1), BASE d78ff24; engine-builder dispatched.
- Peer aligned P1-D1 with J1: same qtype strings, subject conventions (<unit>:<site-id> for e4/e5/e8), cache key, owner lookup, raw-option answers; recorded in .superpowers/sdd/2026-10-03-repair-engine-p1-p2/D1-alignment-with-jev-vps.md. D1 defines its own registry (does not import the J1 fields).
- J1 implementer: DONE, 8f04db1; 46 decide tests pass; engine suite 1202 passed, 1 xfailed. Review dispatched.
- J1 review (rules-reviewer, sonnet): Spec ✅, Quality CHANGES.
  - Important: question_key sorted the Choice criteria (order collision); Score probability keys come back as str through JSON; weak tests.
  - Minor: _KIND KeyError; tag test lacks kinds; defaults hide malformed payloads.
Ruling: Choice criteria order is part of question_key (encoded as [label, description] pairs) — Jev sees options in order, so differently ordered questions are different questions — if wrong, two orderings cost two Jev calls instead of one. (Changes the key definition sent to the peer for P1-D1; peer told.)
Ruling: wire probabilities are string-keyed (JSON); consumers normalise (floor via _floor_to_int); pinned by a test — if wrong, a Score consumer must convert keys itself.
Task J1: minor (deferred): decision_from_json defaults (missing source → "error", missing answer → None) hide malformed payloads.
- J1 fix round 1/5 dispatched (resume implementer).
- J1 fix round 1: 0fbf300; RED 3 fail → GREEN; 56 decide tests pass (controller re-run).
- J1 re-review: all ADDRESSED/RULED, APPROVED.
Task J1: complete (commits d78ff24..0fbf300, review clean after 1 fix round). Merged into feat/jev-vps (integration worktree .claude/worktrees/jev-vps).
Task J1: minor (deferred): `import pytest` inside two test functions; duplicated docstring note in decision_from_json.
- J2: claimed; worktree .claude/worktrees/J2 (claude/J2) from feat/jev-vps.
- J2 implementer: DONE, 126032a; 13 service tests (11 brief + 2 settings) pass; decide engine tests 56 pass. Concern: reask json.loads of a truncated state. Review dispatched.
- J2 review (opus): Spec ✅ Rules ✅ Quality CHANGES.
  - Important 1: the same question twice in one call is paid twice and stored as 2 rows.
  - Important 2: accepted uses the decider default, not cfg.
  - Important 3: a cached owner-reviewed row returned Jev's answer, not the owner's.
  - Important 4: loose answer types in review.
  - Important 5 (brief vs spec): reask clears the owner's confirmed answer.
  - Minors: the cap is checked once per request; reask with a cut state; import does not normalise or validate; missing tests.
Ruling: reask refreshes Jev's fields but keeps status/owner_answer/reviewed_* — a confirmed fact never disappears silently; the owner changes it by reviewing — if wrong, the owner must review again to see a fresh Jev answer reflected as the fact.
Ruling: the cap is re-checked before each batch of 20; the full canonical state is stored in state_json (J3 schema gains `state_json jsonb`) — if wrong, one extra column.
- J2 fix round 1/5 dispatched (resume implementer) with findings 1-9.
- J2 fix round 1: e1e9cc0; RED 13 fail → GREEN 33 service tests; 56 decide engine tests. Notes: cap test uses cap 100/batch 1; J3 needs state_json jsonb; Settings.batch=20.
- J2 re-review: all ADDRESSED/RULED, APPROVED.
Task J2: complete (commits a3a26b1..e1e9cc0, review clean after 1 fix round). Merged into feat/jev-vps.
Task J2: minor (deferred → J4): import_items does not catch a non-dict `question` (AttributeError → 500); J4 validates the item shape (422).
Task J2: minor (deferred): MemoryStore keeps references to the caller's state_json/probabilities dicts (memory store only).
- J3: claimed; worktree .claude/worktrees/J3 from feat/jev-vps. Schema gains state_json jsonb (J2 ruling); answer/owner_answer jsonb.
- J3 implementer: DONE, f98e6f0 (red contract) + a345c12; with PG 83 passed/1 skipped; without 57/27 skipped. Concerns: list(q) also matches state text (as MemoryStore); ensure_schema no advisory lock; psycopg in J5 requirements. Review dispatched.
- J3 review (sonnet): Spec ✅ Rules ✅ Approved with one design call (q matched the state text, which the plan does not want) + minors (race on add, no retry after a DB restart, timestamps not UTC, dead code, negative limit, psycopg not in the image).
Ruling: the search `q` matches the subject only, in both stores (plan + web filterRows agree; state text would match almost every row) — if wrong, the owner cannot search by question text (not needed).
- J3 fix round 1/5 dispatched (resume implementer): subject-only q; on-conflict add; one retry on OperationalError; UTC ISO; drop REVIEWED.
Task J3: minor (→ J4): clamp negative limit/offset in routes. (→ J5): psycopg[binary] in requirements (already in the J5 brief).
- J3 fix round 1: 8f54f2a; RED 6 fail → GREEN 91 (with PG), 61+30 skipped without. Note: the UTC test passed before the fix because the container runs in UTC.
- J3 re-review: findings 1-5 ADDRESSED (4 in code, but its test was weak: the container is UTC), 6-7 RULED to J4/J5. No new Critical/Important. Reviewer accepts that the write retry may double-count add_call on a rare dropped commit (it over-counts toward the cap, so it fails safe).
- J3: one last Minor (a Postgres-only Manila-timezone UTC test, shown to bite) sent to the implementer; no further review round.
- J3 last minor: 4a801c3 (test file only); the Manila-zone UTC test bites (fails with +08:00 on the old _out). With PG 92 passed; without, 61 + 31 skipped.
Task J3: complete (commits d68ba37..4a801c3, review clean after 1 fix round + 1 minor). Merged into feat/jev-vps.
- J4: claimed; worktree .claude/worktrees/J4. Carried in: clamp limit/offset; validate import item shape (422); map PermissionError→409, RuntimeError (reask failure)→502, ValueError→400/422, KeyError→404.
- J4 implementer: DONE_WITH_CONCERNS, b3b8f59; 100 passed + 31 skipped (39 new). Concerns: review/reask rows also drop key/state; no generic 500 handler; concurrent identical asks both call Jev; docs/openapi disabled; app untested against PostgresStore. Review dispatched.
- J4 review (opus): Spec ✅ Rules ✅ Quality CHANGES.
  - Important: question fields were not type-checked (an int qtype or bad criteria were stored / would 500 on Postgres).
  - Minors: accept was not strict; accept+answer both allowed; offset had no upper bound; the 502 text was not allow-listed; no catch-all handler (raw OperationalError traceback could name host/user/db); HTTP tests miss Noul/Score; no Postgres pass; health lacks model; a report claim was wrong.
  - Concerns 1, 3, 4 accepted.
Ruling: the catch-all handler logs only the exception class name and returns 500 "internal error" — a raw psycopg error could name host/user/db in the server log — if wrong, debugging needs a reproduction rather than a log trace.
Ruling: concurrent identical asks may both call Jev (double tokens only; the store dedupes the row; one engine caller) — accepted, not fixed.
- J5 note (from J4 review): the container must publish no port; roles only hold behind nginx (X-Remote-User is set by nginx, replacing any client value).
- J4 fix round 1/5 dispatched (resume implementer), items 1-9.
- J4 fix round 1: 3b18e4f + 64d52fb; RED 33 → GREEN; 141 passed + 111 skipped (no PG), 252 passed on decide-test-pg.
  - Deviations accepted: the catch-all is middleware (Starlette re-raises after exception_handler, so uvicorn would still log the message); 422 bodies drop the input; an import item with question {} → 422.
Ruling: health returns engine.decide.jev.MODEL (no Settings.model field) — if wrong, one Settings field later.
- Found by the J4 implementer (a J3 defect): `question` jsonb reorders Choice criteria keys, so reask sends Jev a different option order (breaks the J1 ruling that order matters).
Ruling: store `question` as json (text-preserving), not jsonb; contract test for option order — nothing is deployed, so no migration — if wrong, a jsonb index on question is lost (none is used).
- J4 fix round 2/5 dispatched (resume implementer).
- J4 fix round 2: f74ab0f; question stored as json (and passed as psycopg Json, since Jsonb reorders server-side); RED 3 fail on PG → GREEN 256 (PG) / 143+113 skipped. Plan text (line ~425 'question jsonb') to correct in the final records.
- J4 re-review: all ADDRESSED/RULED; APPROVED. Minor NOT ADDRESSED (non-blocking): leak test not extended through import + review.
Task J4: complete (commits d02ce63..f74ab0f, review clean after 2 fix rounds). Merged into feat/jev-vps.
Task J4: minor (deferred): `create table if not exists` will not convert an existing jsonb `question` to json (nothing deployed; decide-test-pg is always --rm, so fresh).
Task J4: minor (accepted): 422 `loc` echoes the caller's own key names.
- J5: claimed; worktree .claude/worktrees/J5. Carried in: no published port (roles hold only behind nginx); psycopg[binary] in requirements; health shows model.
- J5 implementer: DONE_WITH_CONCERNS, 49d860e + ddc3c2f; 149 passed + 113 skipped; image builds; smoke OK (health 200/401, ask jev off, gab 403); nginx spoof test 403. Fixed a brief bug: DECIDE_JEV_ENABLED kept out of compose environment (it would override decide.env). Runbook uses docker save -o + scp (PowerShell pipes corrupt binary). Review dispatched.
- J5 review (opus): Spec ✅ Rules ✅ Quality CHANGES.
  - Important 1: nginx fails to start if uc-fixer-decide doesn't resolve (verified [emerg]) → a reboot or rollback takes the dashboard down.
  - Important 2: the container runs as root.
  - Minors: exact-match /ask misses /ask/; README key-command quoting + bash requirement; rewriting decide.env drops the Jev switch; no owner-OK line on steps 3-5; unpinned requirements; pydantic extra.
  - Auth holds: no bypass to /api/decide/*; /api/ stays GET-only; spoofed X-Remote-User replaced.
Ruling: nginx resolves uc-fixer-decide at request time (resolver 127.0.0.11 + variable proxy_pass) — the dashboard must never depend on the Jev container — if wrong, one DNS lookup per 10 s.
- J5 fix round 1/5 dispatched (resume implementer), items 1-8 incl. one Postgres pass of the full service suite.
- J5 fix round 1: 8d7d863, ec882ca, c173641, 27cb477. PG pass 262; nginx starts with no decide (502), recovers in ~14 s without reload; /ask, /ask/, /ask%3F as gab → 403; uid 999; pinned. Concern: static /api/ upstream still resolves at start (out of scope).
- J5 re-review: all ADDRESSED/RULED; APPROVED (reviewer's own probe: nginx starts without decide, recovers ~1 s, 7 /ask spellings → 403, /api/ stays GET-only).
Task J5: complete (commits 8a2cd44..27cb477, review clean after 1 fix round). Merged into feat/jev-vps.
Task J5: out of scope (pre-existing): the static /api/ location resolves uc-fixer-api at nginx start (a reboot without the api container stops nginx) — offered to the owner as a separate task.
- J6: claimed; worktree .claude/worktrees/J6.
- J6 implementer: DONE_WITH_CONCERNS, 091e0e2 + 9d0a3f6; 88 decide tests; engine suite 1244 passed, 1 xfailed. Extras: plain http refused except localhost; no redirects; whole-call deadline via a worker thread. Review dispatched.
- J6 review (opus): Spec ✅ Rules ✅ APPROVED; minors only.
  - Probes: a hung worker outlives ask (daemon thread, socket bounded by nginx's 60 s, never blocks the pipeline).
  - Minors: credentials in the URL accepted; wire `bool("false")` is True; decide-pull --out not anchored to data/; UC_DECIDE_URL not read; status hard-coded 200; wrong comment.
Ruling: fix all six J6 minors now (three touch spec rules: never accepted unless true, data/ only, UC_DECIDE_URL) — cheap; one scoped re-review — if wrong, one extra short round.
- J6 fix round 1/5 dispatched (resume implementer).
- J6 fix round 1: 35b120b; RED 3 fail + 6 error → GREEN: decide + cli 154 passed; service suite re-run after the wire change: see the next line.
  - after the wire change: service suite 149 passed + 113 skipped (controller re-run). Scoped re-review dispatched.
- J6 re-review: all six ADDRESSED; APPROVED.
Task J6: complete (commits 771ab30..35b120b, review clean after 1 fix round). Merged into feat/jev-vps.
- J7: claimed; worktree .claude/worktrees/J7.
- J7 implementer: DONE, ee193d5; 20 new tests; 5 decide files 114 passed; real dry run: groups 340 (85x4), materials 30; engine suite 1270 passed, 1 xfailed. Import uses a 60 s timeout per 200-item chunk. Review + local end-to-end (nginx + service + PG, throwaway) dispatched.
- Peer: P1-D1 merged into feat/repair-p1p2; P1-D2 offered. Plan sent: AskProvider(name, decider) in engine/decide/providers.py, branched from feat/repair-p1p2, wrapping any .ask-compatible decider (JevDecider now, RemoteDecider after the merge); claim after J8. Key compatibility confirmed (json.dumps defaults, ensure_ascii=True).
- Peer OK on the D2 plan. Note: wire.question_key exists only on feat/jev-vps → on D2 assert a hand-written expected hex; the cross-module equality test goes on the first branch holding both modules (after feat/jev-vps → feat-dashboard → feat/repair-p1p2).
- J7 review (opus): Spec ✅ Rules ✅ APPROVED (minors).
  - LOCAL END-TO-END (throwaway nginx + service + PG, real nginx.conf, fake logins) all PASS:
    - import added 370 / re-run skipped 370;
    - 0 answer/confidence mismatches vs jev_pilot.json;
    - accept + change → /confirmed exact;
    - role refusals OK;
    - real classifiers via RemoteDecider: 340/340 group cache hits, 30/30 spot-check hits (2 owner), 361 materials none/"jev off"; no rows added.
  - Leftover: one anonymous postgres volume (12f52767…, created 10:38:37Z) — the reviewer's `docker volume rm` was refused by the permission check; asked the owner.
  - Minors: wrong "85 x 4" label; a group with a missing snapshot would import under an unreachable key; untested name fallback; private _call (optional).
- J7 fix round 1/5 dispatched: skip + count unreproducible groups; label; fallback test.
- J7 fix round 1: c407c7b; RED 5 fail → GREEN 119; real dry run: 340 items from 85 groups, 30 from 30 spot-check materials, unreproducible 0.
- J7 re-review: all ADDRESSED; APPROVED.
Task J7: complete (commits e95644f..c407c7b, review clean after 1 fix round). Merged into feat/jev-vps.
Task J7: minor (deferred): pilot_import reuses the private RemoteDecider._call (optional public post()).
- J8: claimed; worktree .claude/worktrees/J8.
Ruling: J8 shows the texture file name as text; no thumbnail — the only texture route needs a model version id (/api/versions/{id}/textures/{name}) the review page does not have — if wrong, a later task adds a thumbnail lookup by version.
- J8 implementer: DONE_WITH_CONCERNS, 3a215c5 + 426e339; 25 new Vitest, web suite 132, vite build OK (with a scratchpad config aliasing vue/vue-router/three). Not verified: browser render, vue-tsc. client.ts: checkResponse exported. Review dispatched; the controller will do a browser check against a local service.
- J8 review (sonnet): Spec ✅ Quality CHANGES.
  - Important: (1) unfiltered first-500 fetch hides pending rows past id 500; (2) empty threshold selects all; (3) accept-all doesn't stop on a systemic failure; (4) load() overlap / busy flag.
  - Minors: re-ask prefix on 502; accessibility; missing tests.
- CONTROLLER BROWSER CHECK (local throwaway stack decide-ui-*: PG + service from feat/jev-vps + test nginx with fixed X-Remote-User per port; real decide-import-pilot added 370):
  - the page renders, with the "Jev off" banner and counts 30 pending;
  - Accept on Color_H08 → accepted by gab; /confirmed {"Color_H08":"concrete"};
  - at 375 px the row Accept/Change buttons overflow off-screen (only "Cha" visible);
  - at 800 px the tab row overflows ("Fix tie-breaks" cut).
- J8 fix round 1/5 dispatched (resume implementer) with review findings + layout bugs.
- J8 fix round 1: 757f867 + a4f5ea2; RED 14 → GREEN; web suite 147; build OK. The implementer told the two 404s apart by the service detail "unknown suggestion" — confirmed in app.py:164/176 (controller).
- CONTROLLER BROWSER RE-CHECK on the rebuilt page (same local stack):
  - 375 px: Accept + Change fully visible under each row;
  - 800 px: scrollWidth == clientWidth, no overflowing control;
  - Pending list server-filtered (Color_H08 gone after accept, 29 shown);
  - Change on littletiles_ltcolored0_-62 → status changed, owner "concrete" (string), counts 28/1/1.
- Scoped re-review dispatched.
- J8 re-review: all ADDRESSED; APPROVED.
Task J8: complete (commits de7fa09..a4f5ea2, review clean after 1 fix round; browser-checked). Merged into feat/jev-vps.
Task J8: minor (deferred): the stopping error shows in both the notice and the row; a systemic 502 on a single accept/change shows only on the row.
- Local UI stack (decide-ui-*) and image removed.
- All 8 tasks complete. Next: full suites on the merged branch + final whole-branch review (opus).
- FINAL whole-branch review (opus) of d78ff24..16355b9: CHANGES. No contract drift found.
  - Important: (1) uc-engine passes nginx for the whole dashboard and read API (probed); (2) the runbook lacks the web-image rebuild, PC-side setup and §8 post-deploy checks; (3) README line implies 0.8 accepts without review.
  - Minor: (4) service accepted=True at conf ≥ 0.8 (hand-off risk for P1-D2); (5) reserved tab qtypes not the agreed names; (6) bodyless reask → cross-site POST; (7) 502 shows "runs on the VPS"; (8) one ask of ~37 batches may exceed the 10 s client deadline.
  - All ledger deferred minors triaged: none blocks merge.
  - Doc mismatches listed (plan + spec).
Ruling: the service sets accepted=True only for owner answers (source "owner"); confidence is still returned — §2: the engine uses only confirmed answers, so `accepted` must never mean "confident" on this wire — if wrong, a future consumer wanting a confidence gate reads `confidence` instead.
Ruling: fix 1-7 + doc mismatches in ONE fix dispatch (claude/jev-final); 8 deferred to the Jev switch-on (fails safe as none).
- Full engine suite on merged feat/jev-vps (16355b9): 1275 passed, 1 xfailed in 534.08s (0:08:54)
- Final fix wave (claude/jev-final): a79736b nginx, 81218e3 service, 0e09414 web, 91a9fa7 runbook, e463ee7 docs.
  - Suites: service 153+114 skipped / PG 267; decide engine 119; web 151 (red seen first).
  - nginx probe: uc-engine 403 on / /jev /api/models, reaches the decide routes; gab 200; no login 401.
Ruling: Dockerfile.web and the root nginx.conf are untracked foreign files (AGENTS.md §3: never touch untracked files you did not create); the runbook names them and says which nginx.conf the box uses; committing them is the owner's decision — if wrong, the owner commits them separately.
- Docs-only follow-up dispatched (README note + spec §7 wording).
- Docs follow-up: 876100c (README untracked-build note; the box runs deploy/vps/nginx.conf; spec §7). Scoped re-review of the final wave dispatched.
- FINAL re-review of 16355b9..876100c: READY TO MERGE. All findings ADDRESSED/RULED; plan + spec mismatches all ADDRESSED.
  - New minors: README step 3 PowerShell `( cd web; … )` → `npm --prefix web run build`; post-deploy check 2 named import, not ask. Being fixed in one docs commit.
  - Owner note: spec §3/§4 text was rewritten to match the build (uc-engine may also call import and health; key and state_json definitions; endpoint shapes; accepted = owner only). Sections approved earlier — tell the owner.
- Docs fix 71cfa0e (npm --prefix web; post-deploy check 2 is a real one-question ask, getpass when no password; tested against an unreachable URL → URLError).
- Final wave merged into feat/jev-vps.
Final review: clean (READY TO MERGE). Branch feat/jev-vps complete; next: ask the peer, then merge into feat-dashboard.
- MERGED feat/jev-vps → feat-dashboard: e2a37ee (peer "go"; the peer verified merge-tree clean, no existing test modified, guard/validate/api untouched). Main checkout: service 153 + 114 skipped; decide engine 119. Integration worktree removed.
Ruling: this plan's SDD workspace is kept and committed (repo convention: ledgers are records, `git add -f`), not deleted as the generic SDD finish says — if wrong, the folder can be removed later.
