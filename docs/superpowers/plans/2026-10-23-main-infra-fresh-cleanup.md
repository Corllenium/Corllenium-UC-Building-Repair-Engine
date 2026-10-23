# Fresh MAIN INFRA cleanup and dashboard status implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` after owner review, task by task. Product code is test-first and model validation is independent. Reset/deletion is already authorized. Deployment/restarts are not authorized by this plan.

**Goal:** Clean seven already-cut fresh floors without facade damage or missing visible coverage, and show their actual model version and progress in the existing Corllenium planning dashboard.

**Architecture:** Frozen raw package -> equivalent engine input -> guarded floor candidates -> independent validation -> owner acceptance -> versioned artifacts/display. Progress is separate from acceptance.

**Tech Stack:** Existing Python/NumPy/Embree engine in 05, artifacts in 04, Next.js/React/Three.js/Hono planning dashboard in 02.

**Spec:** `../specs/2026-10-23-main-infra-fresh-cleanup-design.md`.

## Global constraints

- Source: `Z:\PC-4-STORAGE\UC MODELS\UPDATED MINECRAFT MODEL\MAIN INFRUSTRUCTURE`.
  Read only through verified snapshot operations. Owner scale: **1 block = 1 metre**.
- Preserve cuts, corners, facade look/UVs and visible coverage. No guard/FixProfile or
  AGENTS.md sections 3-6 changes; no broad default pipeline or blocked repair operations.
- `$PY` = `D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe`. Run modules with `-m`
  from the task worktree with `PYTHONPATH` bound to it. No bulk artifacts/caches on C:.
- Separate raw/candidate/accepted data; one geometry worker; explicit floor identity.
  Other sessions' dirty files/worktrees remain their owners'. Commit named files only.
- Commands below are proposed checks, not executed results. Save actual output in ledger.
  Rebuilds/restarts/live writes/deployment retain the project approval gates.

## Review focus

1. Nonplanar/concave polygons keep real corners/rendered coverage (Task 2).
2. UV seams/opposite-facing sheets cannot disappear as duplicates (Task 3).
3. Stale source/run/cancelled events cannot imply completion (Task 4).
4. Missing assets/partial status/stale heartbeat remain explicit/recoverable (Tasks 4-5).
5. Local origins/scale cannot become guessed stacking or double conversion (Tasks 2,5).

## Task 1: Retire obsolete work and establish one current plan

**Consumes:** Owner deletion instruction, failed reports and exact path/hash inventory.
**Produces:** Reset report, removed-job archive, deletion/readback receipt and current queue pointer.

- [x] Archive five original job records; inventory obsolete plan paths and six OBJ
  variants with explicit failed guards. Record exclusions, hashes and failure evidence.
- [x] Recheck process absence/hashes; resolve every target under named project/staging
  roots. Delete exact files nonrecursively; stop on drift. Preserve raw data, snapshots,
  code, diagnostic reports and other outputs not demonstrated failed.
- [x] Remove five obsolete live job entries; regenerate QUEUE.md; read back absence,
  archive and queue membership. Report exact counts and any denied deletion.
- [x] Update HANDOFF, session history and task ledger; commit only named job files.

## Task 2: Qualify lossless import

**Files:** Review/port sandbox `engine/io/minecraft_floor.py`, its existing focused
test, `tools/repair_fresh_main_infra.py` and its existing test. No parallel importer.
**Consumes:** Verified 36-file raw package, scale decision, original polygons/corners.
**Produces:** Equivalent engine input, polygon/corner provenance and frame manifest.

- [x] Reproduce exact 1F line 10224/4F line 36210 failure on frozen raw. Add regression
  tests for those records, nonplanar/concave/bow-tie/degenerate polygons, UV seams,
  winding and reversible frame conversion. Unsupported/ambiguous cases report blockers.
- [x] Run RED: `$PY -m pytest engine/tests/test_minecraft_floor.py -q -p no:cacheprovider`.
- [x] Implement minimal explicit tessellation retaining actual 3D corners/attributes,
  matching the recorded raw importer's reference. No flattening, face dropping or
  guard relaxation. Record source-polygon-to-triangle/corner provenance.
- [x] Establish exporter source-to-block mapping/up-axis; record forward/inverse matrix
  and determinant using 1 metre/block. Test 1000/25.4 inches/metre, no double conversion
  and preservation of local coordinates after round trip.
- [x] Run GREEN, import both pilots, read OBJ/MTL/textures back and inspect matched
  raw-versus-import renders. Check provenance/cut borders/coverage. Commit evidence/code.
  Failed equivalence blocks cleanup and any claim that the source preview is qualified.

## Task 3: Qualify cleanup on pilots, then remaining floors

**Files:** Review/port sandbox `engine/fixes/precut_cleanup.py`, its focused test,
and existing scoped runner/tests. Start from its exact-duplicate-only route.
**Consumes:** Task 2 baseline/provenance, unchanged guards and fresh signed targets.
**Produces:** Candidate/edit log/stage audit and independent acceptance evidence per floor.

- [x] Add RED tests: exact same-direction duplicates; material/UV/normal differences
  remain; opposite-facing sheets remain; excluded/unknown passes never execute;
  failed pass rolls back. Run `$PY -m pytest engine/tests/test_precut_cleanup.py -q -p no:cacheprovider`.
- [x] Implement minimal allowlisted cleanup. Run GREEN and changed-area regressions;
  commit before owner-facing deliverables. No duplicate framework/default pipeline.
- [x] Run 1F with unchanged guards/full-source comparison. Hidden/coplanar passes need
  separate test/evidence before enabling. Refusal keeps last passing state and records
  exact blocker. Triangle reduction alone is never the target.
- [ ] Separate agent runs existing `engine.validate` against fresh look/UV samples and
  owner-signed targets. Inspect external/pedestrian/interior eye-height and 26-view,
  cut-floor, stair/facade images. Publish validation.json/images; unsigned targets or
  missing evidence block acceptance. No builder self-acceptance.
- [ ] Repeat for 4F; only after both pilots pass run 2F/3F/5F/6F/7F sequentially. Owner
  accepts/rejects each floor. Failed candidate never enters an accepted reference.

## Task 4: Show actual progress before long cleanup runs

Execute before Task 2 real-data work. Queued/importing/blocked floors must be visible
even if import never succeeds; preview remains gated on Task 2 equivalence.

**Files:** 05 `tools/main_infra_progress.py`, `tools/tests/test_main_infra_progress.py`;
02 `dashboard/lib/buildings/{types.ts,seedData.ts,freshMainInfraStatus.ts,freshMainInfraStatus.test.ts}`,
`dashboard/components/buildings/{BuildingPipelineView.tsx,DualModelCanvas.tsx}`,
`dashboard/public/building-repair-status.json`. Inspect/reuse existing publisher.
**Consumes:** Stage events/heartbeat/proof references. **Produces:** Canonical main-checkout
`data/main-infra-fresh/current.json` plus versioned published status/preview refs.
Run artifacts: `data/main-infra-fresh/<source_revision>/<run_id>/`.

**Interface:** `schema_version`, `building_id=MAIN_INFRA`, `source_revision`, `run_id`,
`source_label`, `scale_metres_per_block=1`, `updated_at`, `last_work_event_at`,
`heartbeat_at`, `floors`. Each floor: `floor_id`, `state`, `step`, `blocker`,
`source_preview`, `candidate_preview`, `accepted_preview`, `evidence_refs`,
`validator_ref`, `owner_decision_ref`. Missing proof is never inferred.
Before freeze, source_revision is null, source state is explicitly not_frozen and
no preview or acceptance reference is valid. Freeze assigns the manifest revision.

- [x] Add RED tests for partial JSON, schema/building mismatch, stale source/run,
  cancelled late events, >90s heartbeat age, blocked state and missing/mismatched
  Validator/owner proof. Other buildings' state must remain unchanged.
- [x] Add interaction regressions proving `handleRunSimulatedEngineFix` and
  `handleApproveAndPush` cannot fabricate fresh MAIN INFRA metrics, validation,
  approval or publication. Imported AFTER data alone cannot grant acceptance.
- [x] Implement atomic replace and real step events/10s heartbeat. Reuse publishing,
  no new database/server/scheduler. Worktree-only JSON is not live integration.
- [x] Implement pure version-aware merge: reject old MAIN INFRA completedUnits,
  poll 5s, show last work event separately from heartbeat, show stale after 90s.
- [x] Reuse seven-floor view with step/state/time/blocker/evidence. Source label:
  `Fresh source - not cleaned`. Candidate stays candidate; remove inherited all-done
  claims for this source. Preserve design, keyboard access and narrow layouts.
- [x] Replace fresh MAIN INFRA simulation/approve-push controls with real worker
  state, read-only evidence and persisted owner verdict from the existing workflow.
  If no persisted verdict is available, keep acceptance blocked. No invented commit
  or new approval backend belongs in this status/display slice.
- [x] Run `$PY -m pytest tools/tests/test_main_infra_progress.py -q -p no:cacheprovider`.
  In 02 dashboard run `npm test -- lib/buildings/freshMainInfraStatus.test.ts`,
  `npm run typecheck`, `npm run lint`, `npm run build`. Inspect real blocked/running/
  stale/review states and keyboard access. Save output/screenshots, then commit.

## Task 5: Adopt correct previews and accepted model revision

**Files:** Existing preview publisher, Task 4 helpers/views, 04 accepted package manifest.
**Consumes:** Qualified raw preview and independently validated/owner-accepted floor package.
**Produces:** Revisioned assets and a concrete reviewed planning-dashboard deploy candidate.

- [ ] Add RED tests for MTL/texture URL resolution, old preview-cache rejection,
  unaccepted candidate refusal, source-switch invalidation, atomic adoption/rollback,
  ordinary fresh 7F identity and local floor placement.
- [ ] Package referenced textures/materials under revisioned preview paths. Exclude
  failed/deleted outputs. Separate source/candidate/accepted refs and test explicit
  display frame. Browser uses served URLs, never Z: paths.
- [ ] Select fresh raw source only after Task 2 equivalence, labelled uncleaned. Adopt
  accepted reference per floor only after independent proof/owner verdict. Retain
  floor selector; no assembled view until placement evidence exists.
- [ ] Run targeted tests/typecheck/build and browser interaction/readback. Inspect
  actual textures, seven identities, comparisons/evidence links, reload persistence,
  cache invalidation and saved artifacts with comparable before/after frames.
- [ ] Record code/artifact revisions, hashes, acceptance refs and rollback. Present
  deploy candidate for separately required hosting approval. Do not touch fixer
  services/database as part of this planning-dashboard integration.

## Order and checkpoints

Task 1 -> Task 4 -> Task 2 -> Task 3 -> Task 5. After each step update ledger,
canonical progress, HANDOFF section 2, session history and queue. Commit named files.
Distinguish source preview, candidate, Validator pass, owner acceptance and deployment.
