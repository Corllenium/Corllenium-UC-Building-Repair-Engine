# Dashboard fix wave 1 — brief (from the whole-branch review of 4285034..f6e0068)

Repo `D:\PROJECTS\UC MODEL FIXER`, branch `feat-dashboard`. Bash tool, POSIX syntax, repo path
`/d/PROJECTS/UC MODEL FIXER`. Python ALWAYS `.venv/Scripts/python.exe`; web commands `pnpm --dir web ...`.
PostgreSQL for tests is the running container `fixer-db` on 127.0.0.1:5490 (see `api/tests/conftest.py`).
Do NOT stop, start or restart the servers already running on 8190 / 5190 / 5180 (another session started
them); for live checks start your own uvicorn on 127.0.0.1:8191 and stop it when done.

Rules: test-first per item; one commit per item with the given message and the trailer
`Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Edit `api/`, `web/`, `.claude/launch.json`,
`docker-compose.yml`, and ONLY these engine files: `engine/io/snapshot.py` (D0), `engine/guard/render.py` +
`engine/cli.py` (D9 refactor). Never build a filesystem path from a client string. Never read the live export
folder except through `engine.io.snapshot` (`read_manifest_stable`, `snapshot_object`). Leave untracked
files alone (`OBJ FIXED RESULT/`, root `*.py` scripts). If `git commit` fails on `index.lock`, wait 5 s and
retry once.

## Items, in this order

D0 SUPERSEDED (2026-09-23) by the peer branch `claude/adoring-jennings-a76565` (F5 asset-aware snapshot
identity: a23b031 `_load` reads the one OBJ the content-named dir holds, 5f2c7f1 `SnapshotResult.asset_sha256`
and dirs named `<sha256[:12]>-<asset_sha256[:8]>`, 0c92b2d importer dedups on (model_id, sha256,
asset_sha256, kind)). Do NOT implement anything for D0. After the controller merges that branch, only verify:
`api/tests/test_versions.py` and `api/tests/test_importer.py` pass in any order, and report the count.

D1 `fix(api): guard image view names validated` — `api/routers/fixes.py`: `view` accepted only from a fixed
tuple of the six labels the writer produces; anything else -> 404 before any path is built. Test: `%5C..%5C..%5Cx`
and `../x` -> 404; assert no file outside the run directory is opened (monkeypatch `FileResponse`).

D2 `feat(api): run report carries merge_report, guard totals, provenance` — the fix-run report (stored and
returned) includes `merge_report` (converged, rolled_back, rolled_back_reason, tris before/after, regions
merged, skipped by reason, merge_rounds), `guard_after_removal` and `guard_final` (totals including the
edge_flicker breakdown, passed), `invariants`, `passed`, every `n_*` count, `one_sided_holes_before/after`,
and the profile used. Store `FixResult.source_faces` as asset `source_faces.json` (list of lists of ORIGINAL
face ids). Test on `engine.tests.fixtures.build.box_with_partition()` imported through the API.

D3 `fix(web): AFTER panel states what actually happened` — heading and status derived from the report by a
pure function `describeResult(report)` (vitest): rolled back -> "INSIDE REMOVED, FACES FLIPPED · merge rolled
back (<reason>)"; otherwise "INSIDE REMOVED, FACES FLIPPED, FLAT REGIONS MERGED"; the guard line shows real
totals (holes / moved / material changed / edge flicker) and passed or FAILED; nothing hardcoded; a failed run
shows its error instead of a blank panel.

D4 `fix(api,web): source folder rebuilding is 409, manifest mismatch is 422` — import and scan:
`SourceUnstable` -> 409 with `Retry-After: 5`; `ManifestMismatch` -> 422; unknown file -> 404. `importer.py`
reads the live manifest only via `read_manifest_stable`. `client.ts` exposes `status` and `retryAfter`;
`ModelsView.vue` shows "Export folder is being rebuilt, try again in N s" and never auto-retries. Tests for
all three statuses.

D5 `fix(api): fix run atomic, locked, per-run directory, 201` — run row, fixed version row and its assets are
committed in ONE transaction at the end; on exception nothing of that is persisted and the run is recorded
`failed` with the error text in a separate short transaction; an in-process lock per model id makes a second
concurrent request answer 409 "fix already running"; outputs go under `data/fixed/<run_id>/`; POST returns
201. Tests: `fix_object` monkeypatched to raise -> no `kind="fixed"` row, run failed; two sequential runs ->
two directories.

D6 `fix(api): fixed versions keep materials and the flat-material set of the import` — at import store the
flat-material NAMES on the version row (new Alembic migration if the column is missing); every later
`analyse_topology` / `fix_object` call for that model uses that stored set, never `{}`; pass
`profile.flat_texture_std`; fixed versions record `mtl` and `texture` assets (copy the snapshot files into the
run directory or reference them by path in the DB) so `header.materials[].texture` resolves for AFTER.
Test: the meshbuf of a fixed version has the same material and texture entries as its snapshot.

D7 `feat(api,web): picking maps to source lines` — `GET /api/versions/{id}/faces/{face_id}`: snapshot ->
`{face_id, line, material, vertices}` from the OBJ `face_line`; fixed -> additionally
`source_faces: [{face_id, line}]` from `source_faces.json`. Web: BEFORE shows "source line N"; AFTER shows
"merged from N original faces (lines ...)" or the single source line; delete the `faceId + 1` fabrication.
Tests for both version kinds.

D9 `feat(api): guard images written by the run` — if the PNG writer lives only in `engine/cli.py`, move it to
`engine/guard/render.py` as one function the CLI and the API both call (behaviour-preserving; CLI tests still
pass); the run writes the six PNGs under its directory; the modal lists only views that exist; the button is
hidden when none. Test: after a run the six files exist and the endpoint serves one.

D10 `chore(api): enforce host and port, CORS, data dir` — `api/__main__.py` runs uvicorn on
`settings.api_host` (127.0.0.1) / `settings.api_port` (8190); the `.claude/launch.json` api entry becomes
`python -m api`; CORS allows only `http://localhost:5190` with `allow_credentials=False`; the `data_dir`
default resolves relative to the repo root, not the current directory.

D11 `test(api,web): distinct fixtures, exact file matching, camera sync` — api test fixtures get distinct
geometry (and one test keeps the identical-bytes-two-names case from D0); `ModelsView.vue` matches file
names exactly, not `endsWith`; `syncViewports` copies `zoom` and `fov` too.

D12 `feat(api,web): every fix run writes the latest SketchUp file for the user` — after a fix run the API
calls the engine's SketchUp writer (`engine.io.skp_writer.write_skp`, from the SKP export task) and writes
`<run dir>/<name>.fixed.skp` plus the latest copy `OBJ FIXED RESULT/<name>.fixed.skp` (folder configurable via
settings `skp_dir`, default the repo-root folder the user checks); `report.json` and the run response carry the
path and the writer's summary; the workspace shows "SketchUp file: <path>" with a copy button. When the DLL is
absent the run still succeeds and the UI says the SketchUp file was skipped and why. Tests with the DLL skip
cleanly when it is missing. Also show the new guard totals (`zfight_tie`, `crack_closed`, the flicker breakdown)
and `guard_merge_attempt` in the report panel.

## Finish
`.venv/Scripts/python.exe -m pytest -q` (whole suite, real count), `pnpm --dir web test`,
`pnpm --dir web build`. Live check on 127.0.0.1:8191 with curl: import `CHTM_SIDE_WALK_2nd_floor.obj`
(expect 201 or 409), run the fix, fetch the report, fetch one guard PNG, fetch `/faces/0`; paste the outputs.
Write the full report to `fix-wave-1-report.md` next to this file, appending per item. Reply with only:
status, commit hashes in order, the three test/build result lines, the live-check outputs, concerns.
