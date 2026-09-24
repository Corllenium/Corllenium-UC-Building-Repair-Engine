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
