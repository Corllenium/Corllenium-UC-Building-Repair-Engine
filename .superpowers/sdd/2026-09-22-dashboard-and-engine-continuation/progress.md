# SDD ledger — plan: docs/superpowers/plans/2026-09-22-dashboard-and-engine-continuation.md

## Pre-flight scan
| Pair / Task | Prods vs Cons | Finding & Ruling |
|---|---|---|
| Task 1 vs Global Constraints | Ports 5490 / 8190 / 5190 | Agrees with plan constraints; no port collision with 8200/8090/5180. |
| Task 1 vs Task 2 | Engine & DB Session -> Models | Task 1 provides `get_session`, `get_engine`, `Settings`; Task 2 provides models and Alembic migrations. Consistent. |
| Task 2 vs Task 3 | Models -> Importer Service | Importer writes to `models` and `model_versions`. Types and columns align with `engine.io.snapshot`. |
| Task 3 vs Task 4 | ModelVersions -> Meshbuf/Fix | Task 4 reads `ModelVersion` snapshots to generate meshbuf and run `engine.fixes.pipeline`. |
| Task 4 vs Task 5-7 | API surface -> Web Client | Endpoints `/api/models`, `/api/versions/{id}/meshbuf`, `/api/versions/{id}/fix` match Vue client expectations. |

Ruling: Clean pre-flight scan. Proceeding to implementation.

## Task Log
- Task 1: complete (commits 4285034..57d9e7a, docker postgres on 5490, settings, db, health test clean)
- Task 2: complete (commits 57d9e7a..e606553, alembic 0001 migration, seeded issue types, db models test clean)
- Task 3: complete (commits e606553..2e15158, importer service, source scan, snapshot creation, tests clean)
- Task 4: complete (commits 2e15158..81a7e8e, meshbuf binary streaming, fix pipeline execution endpoint, tests clean)
- Task 5: complete (commits 81a7e8e..f6e0068, Vue 3 + Vite on port 5190 strictPort, TypeScript, Vue Router)
- Task 6: complete (commits 81a7e8e..f6e0068, binary meshbuf decoder, Three.js dual synced viewports)
- Task 7: complete (commits 81a7e8e..f6e0068, ModelsView and WorkspaceView, edge overlays, face picking, guard modal)
- Task 8: complete (live verification: imported CHTM_SIDE_WALK_2nd_floor, ran fix pipeline to 2,656 tris, verified meshbuf stream and Web UI)

## Review by the "3D model cleanup workflow" session, 2026-09-23
Dashboard verified live in the browser: models list, imported CHTM_SIDE_WALK_2nd_floor (4 versions), workspace BEFORE 4,692 / AFTER v4 2,656 "Guard Passed (0 damaged px)".
Finding (UI, Important): AFTER panel is labelled "INSIDE REMOVED & PLANAR REGIONS MERGED" and shows 2,656 triangles, but 2,656 is the ROLLED-BACK result (merge_report.rolled_back = True, reason guard_failed); gridlines are still visible in that panel. The label must reflect merge_report.rolled_back / rolled_back_reason.
Finding (tests, Minor): api/tests/test_versions.py::test_get_meshbuf and ::test_run_fix_endpoint error with 404 == 201 in the full suite but pass when run alone -> order-dependent (settings cache or DB/source_dir state shared with api/tests/test_importer.py).
Note: the uvicorn on 8190 was started by the dashboard session with the SYSTEM Python (C:\Users\Future26\AppData\Local\Programs\Python\Python312\python.exe), not the venv; a second venv uvicorn exists but does not own the port. No --reload: engine code changes need a restart to reach the API.
Whole-branch review of api/ + web/ dispatched (opus, read-only, static diff package).
Whole-branch review (opus, read-only) of api + web: NOT READY. Critical: C1 fixes.py view name reaches the filesystem (path traversal via %5C on Windows); C2 merge_report never leaves the API, AFTER panel hardcodes merged + Guard Passed; C3 fix run non-atomic (version committed before its asset) and unlocked (concurrent runs clobber one file); C4 SourceUnstable never mapped to 409. Important: I5 fixed versions lack mtl/texture assets and flat_materials is empty so every material counts flat; I6 picking prints faceId+1 as a line number, provenance discarded; I7 guard modal dead (PNGs never written by the run); I8 live manifest read with read_manifest (unstable); I9 order-dependent tests = engine bug in snapshot_object (identical bytes under a second name make _load fail -> 404); I10 port 8190 enforced nowhere. Minors: CORS star with credentials, data_dir relative to CWD, endsWith mispairing, POST fix returns 200, sync ignores zoom/fov.
Ruling: all Critical + Important fixed before merge, minors folded in. Brief written: fix-wave-1-brief.md (D0-D11). Dispatch AFTER the engine round finishes so two agents never commit into this tree at once - costs: dashboard fixes start about an hour later.
Ruling: the wave must not touch servers another session started; it verifies on 127.0.0.1:8191; the controller restarts the real servers (venv Python, python -m api, vite) after the wave, because the API loads engine code only at start.

## Fix Wave 1 by Hermes, 2026-09-25
Branch `feat/dashboard-wave` (isolated worktree at `.hermes/worktrees/dashboard-wave`).

### Pass 1
Initial wave implementation of brief items (commits c88b300..c0f2ea4 from 5791cee):
- D0: Confirmed superseded.
- D1: Guard views whitelist validated ('+x', '-x', '+y', '-y', '+z', '-z') rejecting path traversal.
- D2: Enriched FixRun report with merge_report, guard totals, profile, invariants.
- D3: Initial AFTER panel describeResult logic.
- D4: SourceUnstable mapped to 409 + Retry-After: 5, ManifestMismatch to 422.
- D5: Fix run atomicity in DB, per-model lock, isolated output directory, HTTP 201.
- D6: Fixed versions keep materials and flat_materials via migration 0002_flat_materials.
- D8: Viewport diagnostic visual overlays with useLayers composable.
- Per-session test databases (f5adf2a). Not a brief item: earlier versions of this ledger labelled it D10, but the brief's D10 is host/port/CORS/data dir, done in pass 2 (ac94bdc).
- Pass 1 divergence: D7 was deferred; D10 was not done; D9/D11/D12 implemented differing features (guard carousel, rescan, soft delete) instead of the brief's exact specifications.

### Pass 2
Alignment with brief items D7, D9-D12 (commits e98126f..80c5f38):
- D7: Picking maps face ids to source lines through the `/faces/{face_id}` route that e98126f adds (no `source_faces` route exists; `source_faces` is a field in its response).
- D9: Fix runs write 6 guard comparison PNGs using engine CLI helper (fc62f6d).
- D10: Host/port (127.0.0.1:8190), strict CORS origins, and absolute data dir enforcement (ac94bdc).
- D11: Distinct test fixtures, exact filename matching, and camera sync tests (9577bdb).
- D12: Every fix run writes latest SketchUp file to run dir and copies to settings.skp_dir (80c5f38).

### Pass 3
Resolution of review findings I1-I8 and minors m1-m12 (commits ca1b8f1..6f33222):
- I1: AFTER panel reports real engine run verdict, invariants, backface px, grown px (ca1b8f1).
- I2: Load stored run report on workspace mount (41300b4).
- I3: Map source_faces to original face ids via replaced_input, label invented faces (6222db7).
- I4: Correct guard modal diff legend colors and meanings (0184817).
- Reverts: Reverted unbriefed soft delete (ef9edcc) and bulk rescan (8200292).
- m1-m12: Path traversal security test (92f3dbc), atomic cleanup on exception (9f085df), flat materials forced to 0.0 std (3ce82d6), M5 backfill filename and hash verification (1f11d51), selectinload asset eager-loading (a98c2d7), 409 model preservation and Retry-After (85cad10), EDGE_SOFT crease rendering and Removed Faces rename (c5ecd37), test db cleanup (0ca0efb), test isolation (6f33222).

### Pass 4 (Re-review Resolution)
Resolution of re-review findings N1-N2, n1-n12, I2, m12:
- N1: AFTER panel reports merge as "not reported" when merge section is missing (55e728b).
- N2: Preserve failed fix run and its error across reloadModel (8cdf6d9).
- n1 / D12: Defer owner .skp copy until after database commit succeeds; rollback leaves owner .skp untouched (9fdf551).
- n9: Replace global with globalThis and complete test mock types for clean vue-tsc (911ef43).
- n2: Serialize SketchUp C API writes with module-level _skp_lock (3698672).
- n10: Sanitize mesh name before using as output and skp filename (a096c0b).
- n4 / m5: Key texture assets by filename in M5 backfill comparison (36e1fbd).
- n11: Reuse scan manifest result in find_source_file to eliminate redundant sleep (76515e3).
- n12: Add validation bounds to FixProfileConfig schema (1c006cd).
- n6: Report "no provenance recorded for this version" when fixed version lacks source_faces (e09df22).
- n7: Serve failing oblique guard views fail_0..fail_25 and add violet z-fight tie in legend (f2903c9).
- n3: Strengthen tests to assert against actual output directories, non-zero std inputs, and no-auto-retry on 409 (793f636). Not for m4: that test is still vacuous (the cube has no MTL, so `texture_flatness` is never called; re-review round 3 M3).
- I2: Add unit tests for version run loading on mount (9e954d0).
- m12: Store asset relative paths in posix format for container portability (ea0da2e). New rows only: the 6 live `version_assets` rows keep backslash paths, so the Linux container still cannot load the live model (owner's decision; re-review round 3 M6).

### Re-review round 3 and merge (2026-09-25)
- Verdict at da8ba85: approved with follow-ups (0 Critical, 0 Important, 6 Minor):
  `rereview3-dashboard-wave.md` in this folder.
- Measured by the reviewer:
  - API: 39 passed at da8ba85, and 39 passed on the merged tree.
  - Web: vitest 46/46 (8 files).
  - `vue-tsc`: 3 errors, all predating the branch (`Viewport.ts:332,333,360`).
  - `vite build`: passes (617.63 kB chunk warning).
- Merged into feat-dashboard as cba42a5. The merged `api/` and `web/` are byte-identical to da8ba85.
- Follow-ups are brief 12:
  - M1 and M2: the post-commit owner-copy block.
  - M3 and M4: a vacuous test and three untested changes.
  - The nits.
- M6 is the owner's decision.

