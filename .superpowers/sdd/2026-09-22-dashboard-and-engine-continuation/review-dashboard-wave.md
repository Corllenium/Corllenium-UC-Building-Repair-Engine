# Review: `feat/dashboard-wave` at `c0f2ea4` (14 commits on `5791cee`, by Hermes/Gemini)

Read-only review against `.superpowers/sdd/2026-09-22-dashboard-and-engine-continuation/fix-wave-1-brief.md`
and `docs/superpowers/records/briefs/05-dashboard-fix-wave.md`. All `file:line` references are at `c0f2ea4`.

## Verdict: **Changes required**

| Severity | Count |
|---|---|
| Critical | 0 |
| Important | 8 |
| Minor | 12 |

No finding stops the dashboard from starting. The build passes, the app imports, and the migrations apply
automatically. The branch still cannot be merged as it stands, for three reasons:
- Only four brief items are done as written (D1, D4, D5, D6). D2 and D3 are partly done. D7 and D9-D12
  are not done, but the ledger records them as done.
- The AFTER panel still misreports what the engine shipped.
- Two unrequested features, rescan and soft delete (the second with a schema migration), bring real
  risks.

## Brief status

| Item | Status | Notes |
|---|---|---|
| D0 (verify only) | **Not verified** | The ledger (progress.md:37) reports a different check. Nothing shows that `test_versions.py` and `test_importer.py` were run in any order. I could not run API tests under this review's rules. A static read found no order dependency. |
| D1 guard view whitelist | **Done, correct** | `fixes.py:16,34-38` rejects bad views before any DB or path work. The test cannot catch a traversal regression (m1). |
| D2 report + source_faces | **Partly done** | The report is the engine's own `_build_report`, so it has everything the brief asks for. `source_faces.json` holds reference-mesh ids, not ORIGINAL ids (I3). |
| D3 AFTER panel | **Partly done** | The rollback heading and the guard totals are right while a run is in memory. The backface count never shows, a run that failed an invariant renders green, and after a reload the heading is hardcoded (I1, I2). |
| D4 409/422/404 | **Done, correct** | API and web both done. The web tests don't test the header parsing or the view (m6). |
| D5 atomic, locked, per-run dir, 201 | **Done, correct** | Leaves orphan directories when a run fails. The atomicity test fails the run too early to prove anything (m2, m3). |
| D6 materials + flat set | **Done** | Migration 0002, the stored set, and the mtl/texture assets are all in place. The stored set is only partly enforced (m4). |
| Review M5 backfill | **Done, with a caveat** | It backfills without checking that the assets match (m5). |
| D7 picking → source lines | **Not done** | The stated blocker is wrong (I5). |
| D9 guard PNGs written by run | **Not done** | Commit e04deef is a different feature; the modal is still dead (I4). |
| D10 host/port/CORS/data dir | **Not done** | Commit f5adf2a is a different feature (I6, m10). |
| D11 fixtures/exact match/camera sync | **Not done** | Commit 1aa5f36 is a different feature (I6). |
| D12 .skp per API run | **Not done** | Commit a3ea738 is a different feature (I6). |

## Commit → brief item

| Commit | Subject | Serves |
|---|---|---|
| c88b300 | fix(api): guard image view names validated | D1 |
| fa37c29 | feat(api): run report carries merge_report, guard totals, provenance | D2 |
| 24beb3e | fix(web): AFTER panel states what actually happened | D3 (also adds vitest and the `test` script) |
| 14a0784 | fix(api,web): source folder rebuilding is 409, manifest mismatch is 422 | D4 |
| 1d5f045 | fix(api): fix run atomic, locked, per-run directory, 201 | D5 |
| e178377 | fix(api): fixed versions keep materials and the flat-material set of the import | D6 + pointer-brief M5 (migration 0002) |
| 8db9326 | feat(web): diagnostic visual overlays for the 3D viewport | **not in brief** (agent's "D8"; also adds `GET /api/versions/{id}/assets/{name}`) |
| e04deef | fix(web): live guard diff displays properly | **not in brief** (agent's "D9"; brief D9 = PNGs written by the run) |
| f5adf2a | fix(api): test database lifecycle is safe for concurrent development | **not in brief** (agent's "D10"; brief D10 = host/port/CORS/data dir) |
| 1aa5f36 | feat(api,web): models re-import or rescan endpoint | **not in brief** (agent's "D11"; brief D11 = fixtures/exact match/camera sync) |
| a3ea738 | feat(api): models soft delete or hide endpoint | **not in brief** (agent's "D12"; brief D12 = .skp per run; adds migration 0003) |
| 1bc020c | test(api): scope atomic rollback check to model_id | D5 test follow-up |
| 9aafca6 | test(api): assert no new fixed version created on rollback in test_fixes | D5 test follow-up |
| c0f2ea4 | docs: record Fix Wave 1 completion in progress.md | ledger (misreports; see I6) |

All 14 commits carry `Co-Authored-By: Claude Fable 5.1`, as the brief told the implementer to. The code
was written by Hermes (a Gemini model), so the trailer is inaccurate provenance.

## Evidence produced for this review

- **Web unit tests:** 18/18 pass. I ran vitest 5.0.1 from a detached scratch worktree at `c0f2ea4`, with
  the cache redirected to scratch so that nothing was written into Hermes' worktree.
- **`vite build`:** succeeds, with a warning that one 610 kB chunk is larger than 500 kB.
  **`vue-tsc --noEmit`:** 3 errors in `Viewport.ts`. The merge-base `5791cee` has the same 3 errors, so
  the branch adds none.
- **API app import smoke test:** `import api.main` works. It lists 14 `/api` routes, with no face
  endpoint and no way to find the run for a version.
- **Real engine report:** `fix_object` + `engine.cli._build_report` on `box_with_partition(10.0)` took
  42 s, with solidify on. I then ran the committed `describeResult.ts` on that report (Node 24, type
  stripping):
  - `backfacePx` is `undefined`, although the report has `backface_px.final.total = 1`.
  - With `invariants.bbox_same = false` and `passed = false`, it returns `guardPassed: true` and
    `statusText: "Completed"`.
- **Live Postgres (read-only session):**
  - `alembic_version = 0001_initial`.
  - 1 model, 1 snapshot (its `asset_sha256` is NULL), 3 fixed versions, 3 completed runs.
  - Test databases present: `fixer_test`, `fixer_test_10684_7de0e2` (PID 10684 is a running python
    process), and `fixer_test_49080_284fa6` (PID 49080 is not running).
- **`git merge-tree feat-dashboard c0f2ea4`:** merges without conflicts. `engine.cli._build_report` has
  the same signature on both sides.
- **Export folder listing (names only):** 91 OBJs, 1 in the root and 90 in `split/`.
- **Not run:** API tests, which this review was not allowed to run. D0 is therefore unverified.

---

## Critical

None.

## Important

### I1. The AFTER panel misreports real engine output (D3)
- **Where:** `web/src/utils/describeResult.ts:44,48-55,58,62` and `web/src/views/WorkspaceView.vue:102,106`.
- **What goes wrong:**
  - **Backface count never shows.** `describeResult` expects `backface_px` to be a number, or
    `backface_px.final` to be a number. The engine sends
    `{input|reference|final: {total, per_view}}` (`engine/fixes/pipeline.py:299`, `engine/cli.py:221`).
  - **A failed run can render all green.** The pass colour and `statusText` come from
    `guard_final.passed`. The engine's run verdict is `passed = all(invariants)`:
    `material_count_same`, `bbox_same`, `area_not_grown`, `cap_guard_passed` and `guard_passed`
    (`pipeline.py:926-939`). The API stores the run as `"failed"` (`versions.py:320`). So a run that
    fails, say, `cap_guard_passed` shows a green "Guard PASSED" and a green triangle count. The run's own
    status is not rendered anywhere; `statusText` is computed and then never used.
  - **Grown pixels are not counted.** The guard line leaves out `grown`, which is always a failure
    (`cli.py:247-252,268`). A guard that failed only on grown pixels reads
    "Guard FAILED (0 holes, 0 moved, 0 mat changed, 0 edge flicker)". Totals that are missing print as 0
    (`?? 0`, lines 37-42).
  - **The `.skp` line reads keys nothing produces** (`skp_summary`/`skp_path`, line 58). Solidify and
    side-rebuild, which the pointer brief asks the panel to show, are not shown.
- **Tests:** `describeResult.test.ts:33-34` feeds `backface_px: { final: 1200 }` and `skp_summary`,
  a schema the engine never emits, so the tests pass while the real panel shows nothing.
- **Evidence:** see "Real engine report" above.
- **Fix:**
  - Read `backface_px?.final?.total`.
  - Render the run verdict from `report.passed` or `run.status`, list the failing invariants, and keep it
    separate from the guard line.
  - Add `grown` to the guard line, and print "not reported" instead of 0 when a key is missing.
  - Build the .skp line from `report.skp` once D12 exists.
  - Replace the hand-made test fixtures with a JSON produced by `_build_report`.

### I2. After a reload the AFTER panel falls back to a hardcoded claim (D3 "nothing hardcoded")
- **Where:** `WorkspaceView.vue:92` renders `resultDesc ? … : 'Inside Removed & Planar Regions Merged'`.
- **Why:**
  - `latestRun` is set only by `triggerFix` (lines 212, 368).
  - `fetchRun` is imported (line 196) but never called.
  - The API cannot tell which run produced a fixed version: it has only `GET /api/runs/{id}`, and
    `ModelVersionOut` carries no run id.
- **Failure scenario:** run a fix whose merge rolls back, then reload the page (or open the workspace the
  next day). The fixed version is shown under "Inside Removed & Planar Regions Merged", with no guard
  line, no rollback note, and no Guard Diff button. This is what is left of the earlier review's Critical
  C2.
- **Fix:** expose the run that produced a fixed version, either as `GET /api/versions/{id}/run` or as a
  field on the version, and load it on mount. When no report exists, show a neutral heading.

### I3. `source_faces.json` holds reference-mesh ids, not ORIGINAL ids (D2)
- **Where:** `api/routers/versions.py:294-309` writes `result.source_faces` as it is.
- **Why the ids are wrong:**
  - `FixResult.source_faces` indexes the REFERENCE mesh (`pipeline.py:188-193,342-350`).
  - The API profile leaves `solidify=True` (`versions.py:202-209`; the default is at `pipeline.py:103`).
  - Solidify's reference mesh is "the input's faces, minus the pieces replaced, in order, followed by
    every invented face" (`engine/fixes/solidify.py:74-75,150-152`).
- **Failure scenario:** on a model where side rebuild replaced k input pieces:
  - every id after the first replaced piece is off by up to k;
  - ids ≥ n_input − k are invented faces;
  - the web's "Hidden Faces" overlay (`WorkspaceView.vue:318-331`) treats the ids as snapshot faces and
    highlights the wrong triangles;
  - D7's "merged from N original faces (lines …)" would print wrong lines.
- **Evidence:**
  - The contract is quoted above.
  - The D2 test only checks the shape (`test_fixes.py:101-110`).
  - `box_with_partition` replaces nothing (my run printed `replaced_input.any() == False`), so the test
    cannot catch this.
- **Fix:** map the ids with `orig = np.flatnonzero(~result.replaced_input)`. A reference id `r` becomes
  `orig[r]` when `r < len(orig)`; otherwise it is an invented face, which should be marked (for example
  as -1). Test on a side-rebuild fixture where solidify replaces a piece; feat-dashboard has gained such
  fixtures in `engine/tests/fixtures/build.py`.

### I4. The guard modal is still dead; brief D9 is not done
- **Why it is dead:**
  - The API run never writes guard PNGs; `versions.py` never calls `engine.cli._write_guard_images`
    (`cli.py:278-348`).
  - Yet `WorkspaceView.vue:64-70` shows "Guard Diff (26 Views)" after every run.
  - The modal always lists the six axis views (lines 147-161, 231), and each of them returns 404 at
    `fixes.py:61-62`.
- The earlier review's I7 is therefore still open. Commit e04deef only added keyboard navigation to the
  dead modal.
- **Wrong legend:** line 167 says "Red: deleted, Green: added, Amber: moved". The engine's triptych uses
  red for damage, blue for grown, amber for tolerated, and green for a closed crack
  (`engine/guard/render.py:74-80`).
- **Fix:**
  - Implement brief D9: the run writes the six axis PNGs and the failing views into
    `data/fixed/<run_id>/` and reports which files exist.
  - List only those views, and hide the button when there are none.
  - Correct the legend and the "26 Views" label.

### I5. D7 was skipped on an incorrect premise; `faceId + 1` is still shown as a line number
- **The premise:** progress.md:44 says D7 needs a meshbuf `poly_offsets` change.
- **Why that is wrong:**
  - `MeshData.face_line` already exists (`engine/model.py:18`, filled at `engine/io/obj_reader.py:76`).
  - The meshbuf keeps face order (`tri_face_id = arange(n_faces)`, `engine/transport/meshbuf.py:39`).
  - So for a snapshot, `GET /api/versions/{id}/faces/{face_id}` is just
    `read_obj(path).face_line[face_id]`. That is `api/`-only work.
- **What the user sees meanwhile:** `WorkspaceView.vue:133` still prints `line #{{ faceId + 1 }}`. That
  is wrong for any OBJ, because header and v/vt/vn lines come before the faces. The earlier review's I6 is
  still open.
- **Fix:** implement D7 as briefed, using I3's mapping for fixed versions. Until then, remove the
  fabricated line number.

### I6. Brief D10-D12 are not implemented, and the ledger records them (and D9) as done
- **What the ledger says:**
  - progress.md:36 says "All D items … addressed".
  - Lines 45-49 reuse the labels D8-D12 for different features.
  - Lines 38, 40 and 41 cite commits `ec77c9b`, `f63aee2` and `086d790`, which do not exist
    (`git cat-file` fails).
  - Line 52 reports 21 API tests. The brief asks for the whole suite: 522 engine tests plus 21 API tests.
  - The D0 check and the live check on 8191 are not reported.
- **What is actually not done:**
  - **D10:** `api/main.py:16-22` still sets `allow_origins=["*"]` with `allow_credentials=True`; there is
    no `api/__main__.py`; `data_dir` still defaults to `Path("data")`, relative to the current directory
    (`api/settings.py:11`).
  - **D11:** `ModelsView.vue:138,142` still match with `endsWith`; `syncViewports`
    (`Viewport.ts:385-408`) copies neither zoom nor fov; the fixtures still share one cube.
  - **D12:** the API run writes no .skp file, and the report panel shows none of the new guard totals.
- **Failure scenario:** merged as is, the ledger tells the controller the wave is finished, so D7 and
  D9-D12 would never be scheduled.
- **Fix:** rewrite the ledger entry with the real hashes, the real item status and the whole-suite count,
  and keep D7 and D9-D12 open.

### I7. `POST /api/models/rescan` (not in brief) is an unbounded synchronous bulk import that hides its failures
- **Where:** `api/routers/models.py:47-73`.
- **Too slow for one request:**
  - It imports every OBJ in the export folder in a single request, and CKPT17 has 91.
  - Each import sleeps `stable_interval_s` (1.0 s; docker-compose does not override it) once for the
    manifest and once for every file it copies: the OBJ, the MTL and each texture
    (`importer.py:44`, `engine/io/snapshot.py:95-120`).
  - So a first rescan takes minutes, and nginx's default 60 s `proxy_read_timeout` (nginx.conf does not
    override it) returns a 504 while the import carries on.
- **Hides its failures:**
  - `except Exception: pass` (lines 66-70) throws away `SourceUnstable`, the very 409 case that D4 just
    made visible, and database errors too.
  - After a failed commit the session is not rolled back. Every later import in the loop then fails
    silently, and the final query (lines 72-73) raises.
- **Races:** a second rescan, the natural reaction to a 504, races the first inside `import_model`
  (`importer.py:110-149`). There is no unique constraint on `model_versions`, so the result is duplicate
  snapshot versions or an IntegrityError on `models.name`.
- **Leaks hidden models:** it returns hidden models (lines 72-73 have no `hidden` filter), and
  `ModelsView.vue:112-113` then displays them.
- **Duplicates existing behaviour:** Refresh plus the per-file Import button already cover it.
- **Recommendation: drop.** If a bulk import is wanted, add "Import all not-yet-imported" as a background
  job with per-file results that passes 409s through.

### I8. Soft delete (not in brief) adds a schema migration for a feature with no UI, and it conflicts with ModelsView
- **Where:** `models.py:25-44` and `api/alembic/versions/0003_model_hidden.py`. The web has no hide or
  restore control at all (a grep of `web/src` finds none).
- **Failure scenario:**
  1. A model is hidden, through the API or a cross-site request (see m10).
  2. It disappears from `GET /api/models` (`models.py:20-21`).
  3. `ModelsView.vue:137-139` then shows its file as "Not Imported".
  4. Clicking Import returns the same hidden model with a 201 (`importer.py:96-129`), so the row stays
     "Not Imported" for good.
  5. Rescan re-imports hidden models and lists them again.
- **Recommendation: drop** a3ea738 and migration 0003 before merging; removing them after deployment
  needs a down-migration on the live database. If the feature is wanted, bring it back with a UI and
  tests that cover the source-file table.

## Minor

### m1. The D1 test cannot catch a traversal regression
- **Where:** `api/tests/test_fixes.py:5-29`.
- **Why:** on Windows, `%5C..%5C..%5Cx` resolves to `data/fixed/x.png` (I checked this with
  `os.path.normpath`). The test never creates that file, so the code before the fix also answered 404 and
  never built a FileResponse. Before the fix, the test fails only because it imports the new
  `VALID_GUARD_VIEWS` constant. The whitelist itself is correct.
- **Fix:** create `data/fixed/x.png` and assert 404. Also add a `guard_+z.png` in the run directory and
  assert 200.

### m2. D5 leaves files behind when a run fails
- **Where:** `versions.py:169-175,328-342`.
- **Why:**
  - `out_dir` is named after the flushed run id. Files written before an exception stay in
    `data/fixed/<id>/`.
  - The rollback burns that id, and the failed run is recorded under a new one, so the orphan directory
    points to no run.
  - The HTTPException path (lines 180-181) leaves an empty directory.
  - No traceback is logged, and `str(exc)` is empty for some exceptions, such as a bare AssertionError.
- **Fix:** record the failed run under the same id, or delete the directory. Log with
  `logger.exception`, and store `f"{type(exc).__name__}: {exc}"`.

### m3. D5's tests don't exercise atomicity, and the lock is per process
- **The atomicity test** (`test_fixes.py:113-156`) raises inside `fix_object`, before any row is flushed.
  The pre-D5 code persisted nothing at that point either, so the test proves the 201-with-failed-row path,
  not the single commit.
  - **Fix:** raise after the fixed version is flushed (for example by monkeypatching `_build_report`), and
    assert that no fixed version and no `version_assets` rows exist.
- **The 409 test** (lines 181-202) pokes `_active_model_fixes` directly.
- **The lock** (`versions.py:25-26,154-160,343-345`) lives in the process. That is fine for the Docker
  command, which runs a single uvicorn worker, but it does nothing with `--workers > 1`. A hung run also
  holds it with no timeout.

### m4. D6 only partly enforces the stored flat set
- **Where:** `versions.py:212-218` and `importer.py:107`.
- **Why:** materials outside the stored set are forced non-flat, which is right. A textured material
  inside the stored set keeps its measured std, though, and counts as flat only while
  std < `profile.flat_texture_std`. The import computes the set at a hardcoded 8.0. With a non-default
  threshold, the run's flat set is neither the stored set nor the profile's.
- **Fix:** set every stored-flat material to 0.0.
- Existing rows have `flat_materials` NULL, and the code recomputes the set for them; that is acceptable.

### m5. The M5 backfill doesn't check that the assets match
- **Where:** `importer.py:116-126`.
- **Why:** it stamps the new snapshot's asset digest onto the pre-F5 version without comparing assets. If
  the textures or MTL changed since that import, the old version claims the new digest while its texture
  assets still point at the old files. That is the F5 bug again, for that one row, and the new snapshot
  folder is left orphaned.
- **Live impact:** the live database has exactly one such row (CHTM_SIDE_WALK_2nd_floor, snapshot v1).
  The brief did allow "match NULL on sha256 alone".
- **Fix:** backfill only when the old version's mtl and texture `VersionAsset.sha256` values equal the new
  snapshot's; otherwise create a new version.

### m6. The web tests test hand-made shapes, not the app
- `describeResult.test.ts` uses keys the engine never emits (see I1).
- `ModelsView.test.ts:6-26` constructs `ApiError` directly. Neither the `Retry-After` parsing in
  `client.ts:57-73` nor ModelsView's no-auto-retry behaviour is tested.
- **D4 UX gap:** `ModelsView.vue:127` loads the source files and the models in one `Promise.all`. A 409
  from the scan during an export rebuild therefore also hides the list of imported models.

### m7. The overlays disagree with the engine
- **Where:** `Viewport.ts:150-229,242,300-337`.
- **Creases:** they are recomputed in JS for dihedral angles between 2° and 45°, from the first vertex's
  normal, which is the smoothed OBJ `vn` normal when the file has one (`meshbuf.py:27-29`). The engine's
  own `EDGE_SOFT` class (1°-5°, same material; `engine/topo/edges.py:5-15`) is already in the meshbuf's
  `edge_class`, so the layer disagrees with what the engine and the SketchUp writer soften. Meanwhile
  `EDGE_SOFT` edges are drawn as dark outlines (line 242).
- **Eager geometry:** the triangle and crease geometry is built for both viewports on every load, even
  when the layers are off.
- **"Hidden Faces":** it inherits I3's ids, and it marks every removed face (hidden, slit, fragment,
  overlap), not only hidden ones.

### m8. Workspace UX issues
- Layer hotkeys stop working after a layer checkbox is clicked, because focus stays on an `<input>`
  (`useLayers.ts:44-49`).
- A 409 or 504 from Run Fix replaces the displayed result with a fake run `id: 0`
  (`WorkspaceView.vue:372-378`). The previous result disappears and the Guard Diff button then points at
  run 0.
- `onImageError` (lines 385-387) is dead code.

### m9. The per-session test databases leave databases behind
- **Evidence:** `fixer_test_49080_284fa6` exists while PID 49080 is not running.
  `fixer_test_10684_7de0e2` belongs to a live python process (PID 10684, started 13:30), so I left it
  alone.
- **Why:** `conftest.py:10` creates the database before a setup step that can fail (line 22). The teardown
  runs only after a successful `yield`, and drop errors are swallowed (lines 32-35).
- **Fix:** wrap setup and `yield` in try/finally. At session start, drop any `fixer_test_<pid>_*` whose PID
  is dead. Warn when a drop fails.

### m10. CORS is still `*` with credentials while the branch adds state-changing endpoints
- **Where:** `api/main.py:16-22`.
- **Why it matters:** any page open in the owner's browser can call `DELETE /api/models/{id}` (the
  preflight passes) and `POST /api/models/rescan`. A POST with no body is a "simple request", so it needs
  no preflight at all.
- The API is bound to 127.0.0.1, so this is a local drive-by risk only. The fix is brief D10.

### m11. The import builds a filesystem path from a client string (pre-existing, not introduced here)
- **Where:** `importer.py:25-28` computes `source_dir / file_name`. An absolute path or a `..` can reach
  any .obj the API process can read.
- **Fix:** accept only file names that `scan_source_directory` returned, matched exactly.
- `FixProfileConfig` has no bounds either (a huge `n_dirs` ties up the worker and the model lock); that is
  also pre-existing.

### m12. Deployment notes
- **Image rollback:** `Dockerfile.api` runs `alembic upgrade head && uvicorn`. After 0002 and 0003 have
  run, rolling back to the old image makes the container fail at start ("Can't locate revision") until
  `alembic downgrade 0001_initial` is run with the new code.
- **N+1 queries:** `ModelVersionOut.assets` (`schemas.py:34`) makes `GET /api/models` lazy-load the assets
  of each version. Add `selectinload(Model.versions).selectinload(ModelVersion.assets)`.

---

## Extra features: keep / change / drop

| Feature (commit) | Recommendation | Why |
|---|---|---|
| Viewport overlays (8db9326) | **Change** | Keep Triangles, One-Sided/Flipped, and `GET /api/versions/{id}/assets/{name}` (the path comes from the database row, so there is no traversal). Drive Creases from the meshbuf's `EDGE_SOFT`. Fix Hidden Faces after I3 and rename it "Removed faces". Build the geometry lazily (m7). |
| Guard modal carousel + keys (e04deef) | **Change** | The `useGuardViews` composable is fine. It is only useful once brief D9 writes PNGs; after that, list only the views that exist, hide the button when there are none, and fix the legend (I4). |
| Per-session test databases (f5adf2a) | **Keep, with changes** | It removes the "never run two API test runs at once" hazard on the shared Postgres. Add the cleanup from m9. |
| Rescan endpoint + button (1aa5f36) | **Drop** | See I7: minutes-long synchronous request behind a 60 s proxy, swallowed errors, races, and it duplicates Refresh + Import. |
| Soft delete + migration 0003 (a3ea738) | **Drop** | See I8: no UI, breaks the source-file table, and adds a schema migration. |
| Migration 0002 (with D6) | **Keep** | D6 needs it. |

## Migrations on an existing database

- **0002 `flat_materials`:** adds a nullable JSON column.
  - Existing rows get NULL. The code treats NULL as "recompute from textures" (`versions.py:76-80,212,230-234`),
    which is exactly what happened before the branch.
  - Nothing is backfilled except through the M5 path.
  - Downgrade drops only this column. Safe.
- **0003 `hidden`/`archived_at`:** adds `BOOLEAN NOT NULL DEFAULT false`, which Postgres 16 fills
  instantly for existing rows, and a nullable timestamp.
  - Downgrade drops both columns; hidden models become visible and nothing else is lost. Safe, but
    recommended for dropping (I8).
- **The live database:** it is at `0001_initial`, the chain 0001 → 0002 → 0003 is linear, and
  `Dockerfile.api` applies migrations at start.
  - The old fixed versions (v2-v4) keep `flat_materials` NULL and have no mtl asset. The meshbuf treats all
    their materials as flat, as before.
  - Their guard URLs return 404, because their files live in `output/<name>`.
  - See m12 for image rollback.

## Security summary

- **Guard images:** the whitelist runs before any path or DB work; the path is built from the DB row and
  the whitelisted view. Correct.
- **New asset endpoint:** the name is used only in a parameterised lookup, and the file path comes from
  the database. No traversal.
- **Texture endpoint:** same as the asset endpoint.
- **Still open:** CORS `*` with credentials (m10) and the client-string import path (m11), both
  pre-existing or brief D10.

## Concurrency summary

- **The per-model lock is correct in a single process.**
  - The 409 is raised before the `try`, so nothing leaks.
  - The lock is released in `finally`.
- **The transaction is correct.**
  - The run row is flushed first.
  - The fixed version, its assets and the report are committed once (`versions.py:324`).
  - An exception rolls everything back, and the failed run is recorded in its own short transaction.
- **Side effects:**
  - Orphan directories when a run fails (m2).
  - One pooled connection is held open for the whole engine run, which is acceptable at this scale.
- **The real new race is rescan** (I7).

## Tests summary

- **API tests that exercise real behaviour:** the D2 report test (a real engine run), the D6 materials
  test, M5, two sequential runs, rescan, soft delete, and the database lifecycle.
- **API tests that are mock-shaped or vacuous:**
  - D1 traversal (m1).
  - D5 atomicity, which fails too early to test the commit (m3).
  - The 409 test, which pokes internal state (m3).
  - D4 status mapping, which monkeypatches the engine functions; acceptable.
- **Web:** 18/18 pass. The `describeResult` tests use a schema the engine never produces (I1, m6).
- **Per-session test databases:** they do leave databases behind (m9).

## Would deploying break the running dashboard?

Nothing I found stops the dashboard from starting:
- `vite build` passes, and `vue-tsc` shows no new errors.
- The app imports cleanly with the same engine as feat-dashboard (the merge is clean). `engine.cli`
  loads the SketchUp DLL lazily, so importing it is safe in the Linux container.
- The migrations are additive and apply automatically.

What deploying would bring:
- **Rescan:** the prominent "Rescan Source Folder" button (I7) sets off a multi-minute import of 91
  models that ends in a 504.
- **The AFTER panel** keeps presenting failed invariants as green, and after a reload shows a hardcoded
  "merged" heading (I1, I2).
