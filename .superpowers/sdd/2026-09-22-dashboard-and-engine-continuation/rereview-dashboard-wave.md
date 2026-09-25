# Re-review: `feat/dashboard-wave` at `6f33222` (passes 2 and 3 on top of pass 1)

This review is read-only. It covers pass 2 (e98126f..80c5f38) and pass 3 (ca1b8f1..6f33222). It checks them against:
- `.superpowers/sdd/2026-09-22-dashboard-and-engine-continuation/review-dashboard-wave.md` (findings I1-I8 and m1-m12);
- `fix-wave-1-brief.md` (items D7 and D9-D12);
- the pointer brief `docs/superpowers/records/briefs/05-dashboard-fix-wave.md`.

All `file:line` references are at `6f33222` unless marked otherwise. Every "fails without the fix" claim below was
measured by mutation: I undid the fix in a scratch copy and re-ran the test.

## Verdict: **Changes required**

| Severity (new findings) | Count |
|---|---|
| Critical | 0 |
| Important | 2 |
| Minor | 12 |

Most of pass 3's claims hold:
- These are fixed: I1, I3, I4, I5, m1, m3, m7, m8, m9, m10 and m11.
- The tests for I1, I3, m1, m10 and m11 fail when the fix is undone (measured).
- Both reverts are clean.
- D7, D9 (the API side, as the controller ruled), D10, D11 and D12 are done as written.
- D12 calls the engine's own `engine.cli._write_skp`. Only a run the engine passed replaces the owner's `.skp`.

Two things in the AFTER panel still block the merge. Both are the misreporting the wave was meant to remove:
1. **N1.** The panel still says "FLAT REGIONS MERGED" for any run whose stored report comes from before this branch. That covers
   every run in the live database, including the run behind v4. The 09-23 check found that run's merge rolled back.
2. **N2.** The run report that pass 3 loads on mount (the I2 fix) replaces the result of the run that just finished. When that
   run fails with an exception, its error text disappears at once. The panel then shows the previous run ("Run PASSED") or
   the empty placeholder. This breaks D3's "a failed run shows its error".

Several items are only partly done:
- **I2 and I6.** The ledger still misreports.
- **m5.** The asset check can never match a textured model, so the M5 backfill is dead code for real models.
- **m2, m4 and m6.** Their tests cannot fail.
- **m12.** The image-rollback caveat is still there.

## Evidence produced for this re-review

- **API tests: 32 passed, 0 failed, 9 warnings (all deprecations), in 663 s.**
  - Run from a detached scratch worktree at `6f33222`, with `PYTHONPATH` pinned to it (the engine and api imports were checked
    to resolve there, not in the main checkout). Venv Python 3.12.10.
  - No other pytest process was running beforehand.
  - Every session created its own `fixer_test_<pid>_*` database and dropped it. Before and after my three sessions,
    `pg_database` held only `fixer` and `fixer_test`.
- **Web: vitest 35/35 (7 files).**
  - `vite build` passes, with the usual warning about a chunk over 500 kB (617 kB).
  - `vue-tsc --noEmit` reports 8 errors. 3 are the pre-existing `Viewport.ts` errors (the same as on the merge base). The other 5 are
    new, in `web/src/api/client.test.ts:5,12,16,39,59` (`Cannot find name 'global'`, added by 85cad10). See n9.
- **Engine: not run.** The branch does not touch `engine/`. Pytest collects 549 tests at `6f33222` and 566 on the merged tree.
- **Mutation checks.** Each mutant restores the pre-fix code and runs the finding's own test:

  | Mutant | Test | Result |
  |---|---|---|
  | I3: write raw reference ids | `test_source_faces_maps_to_original_face_ids_and_obj_lines` | **fails** (`assert (40 == -1 or 40 < 40)`) |
  | m1: remove the view whitelist | `test_guard_view_validation` | **fails** (`200 == 404`) |
  | m11: remove the filename checks | `test_import_path_traversal_rejected` | **fails** (`../test_cube.obj` → 201) |
  | m10: old CORS (`*` with credentials) | preflight from `http://evil.com` | echoes `allow-origin: http://evil.com`, so `test_cors_configuration` fails |
  | I1: pass-1 `describeResult.ts` | new `describeResult.test.ts` | **6 of 7 fail** |
  | m2: remove the output-dir cleanup | `test_fix_atomic_rollback_on_exception` | **still passes** (vacuous directory check) |
  | m4: restore the pass-1 flatness rule | `test_stored_flat_materials_enforced_to_zero_std` | **still passes** (vacuous) |

- **Probes** (scratch copies, never committed), both against unmodified code:
  - An unchanged re-import of a textured model whose row has `asset_sha256` NULL gives **2 versions**; the backfill did not happen.
  - A run that fails after the `.skp` step ends as `status=failed`, `fixed_version_id=None`, and **the owner copy exists**.
- **I3 geometric check** on `slab_with_sawtooth_side`, with the API's profile:
  - Mesh: 40 input faces, 4 replaced, 46 reference faces, 12 output faces.
  - With the API's mapping: 0 of 68 (output face, source face) pairs are off-plane.
  - With raw reference ids read as input ids: 6 of 76 are off-plane.
  - Ground truth (raw ids against the reference mesh): 0 of 88.
- **A genuine engine report**, from `fix_object` + `engine.cli._build_report` on the live model's snapshot
  (`data/snapshots/ce26e0392ab0`, 4,692 tris), using the merged tree's engine and the profile the dashboard sends (`n_dirs=128`):
  - The run took 100.7 s of `fix_object` alone, measured while the API suite ran.
  - Result: 917 tris, passed, merge not rolled back, final backface 21,553 px.
  - The committed `describeResult` rendered it correctly: heading, run verdict, a guard line with grown, backface 21,553,
    border shift 167, 162 skirts / 16 bottoms, 52 edges / 81 pieces replaced, and the merge attempt as passed.
  - I then added `rolled_back` to that report and failed its `cap_guard_passed` invariant. The output was the rollback heading
    with its reason, "Run FAILED", and `failed: cap_guard_passed`.
- **Live database** (a read-only session):
  - `alembic_version = 0001_initial`, and `model_versions` has no `flat_materials` column.
  - v1 is a snapshot with `asset_sha256` NULL and a texture asset named `mumi_littletiles_ltstone_-7.png`. Its MTL material
    is `mumi_littletiles_ltstone_-7`.
  - v2-v4 are fixed versions. Runs 1-3 each store the pre-branch 11-key report: no `merge_report`, no `guard_final`, no
    `invariants`.
- **Live API** (GET requests only):
  - It serves the pre-branch code (11 paths).
  - `/api/versions/1/meshbuf` and `/api/versions/4/meshbuf` both return 404 "OBJ file missing on disk". The rows store Windows
    `\` paths and the container runs Linux. This predates the branch; see Deployment.
- **Merge:** `git merge-tree --write-tree feat-dashboard 6f33222` is clean (tree `3a9e0b0`). `api.main` imports on the merged tree
  and serves 14 routes.

---

## Findings and brief items: status

| Item | Status | Evidence |
|---|---|---|
| **I1** AFTER panel misreports engine output | **Verified fixed** (for reports the engine produces) | `describeResult.ts:98-109` reads `backface_px.final.total`. `:68-71` gives the run verdict from `report.passed`. `:56-62` lists invariants that are `false`. `:93-95` adds `grown`, and `:86-93` prints "not reported" for missing keys. `WorkspaceView.vue:102-113` shows the run verdict apart from the guard line and colours the tri count by it. The `.skp` line comes from `report.skp` (`:146-161`), and solidify and side rebuild are shown (`:117-126`). Tests: 6/7 fail against pass-1 code. The genuine report of the live model renders correctly. Remaining gap: reports from before the branch (N1). |
| **I2** hardcoded heading after reload | **Partly** | `GET /api/versions/{id}/run` (`versions.py:239-262`) is tested by `test_versions.py:170-207`. The run loads on mount (`WorkspaceView.vue:439-447`). The fallback heading is the neutral "Fixed Version" (`:92`). But runs from before the branch still get "FLAT REGIONS MERGED" (N1), and the reload overwrites a run that failed with an exception (N2). No web test covers the mount load. |
| **I3** `source_faces.json` holds reference ids | **Verified fixed** | `versions.py:418-431` maps `orig = flatnonzero(~replaced_input)`, turning `r` into `orig[r]` and invented faces into -1. That matches the engine's contract, `FixResult.reference_mesh` and `replaced_input`, at `engine/fixes/pipeline.py:342-354`. The contract is unchanged on feat-dashboard (`solidify.py:74`). The geometric probe and the mutation both confirm it. The web labels -1 as "invented face (solidify)" (`faceInspection.ts:14-16`). |
| **I4** guard modal dead, D9 missing | **Verified fixed** (minor gaps, n7) | The run writes the PNGs and reports which ones exist (`versions.py:444-459`). The button is hidden when there are none (`WorkspaceView.vue:65`) and shows the real count (`:69`). The modal lists only those views. The legend is corrected (`:218`). Test: `test_fixes.py:45-64`. The failing-view PNGs are written but can never be listed or served (n7). |
| **I5** D7 skipped, `faceId + 1` shown | **Verified fixed** | See D7 below. `faceId + 1` is gone (git grep). |
| **I6** D10-D12 missing, ledger misreports | **Partly** | D10-D12 are done (pass 2). The ledger, `progress.md:34-53`, has not changed since c0f2ea4. It still cites commits that do not exist (`ec77c9b`, `f63aee2`, `086d790`; `git cat-file` fails), says "D7: Blocked", lists D9-D12 as other features (line 49 even describes the reverted soft delete with migration 0003), and reports "21 passed". It merges cleanly into feat-dashboard as it stands (n5). |
| **I7** rescan | **Fixed (reverted, clean)** | The revert is 8200292. No route is left (OpenAPI lists 14 paths), and no client function, button or test remains. The net diff of `api/routers/models.py` against 5791cee holds only the `selectinload` and 409/422 changes. |
| **I8** soft delete + migration 0003 | **Fixed (reverted, clean)** | The revert is ef9edcc. `0003_model_hidden.py` is gone, and the Alembic heads are `['0002_flat_materials']` (chain 0001 → 0002). No `hidden` or `archived_at` remains in `api/models.py` or `api/schemas.py`, and there are no DELETE or restore routes. |
| **m1** D1 test could not catch traversal | **Verified fixed** | `test_fixes.py:5-42` creates `data/fixed/x.png`, asserts 404 for the traversal views, and asserts 200 for `+z`. With the whitelist removed the test fails. |
| **m2** orphan dirs, no traceback, empty error | **Fixed in code; the directory check in its test is vacuous** | Cleanup on both failure paths (`versions.py:497-506`), `logger.exception` (`:503`), and a `"Type: msg"` error (`:507`). The test checks `data/fixed/<failed run id>` (`test_fixes.py:252-254`). The run directory, however, is named after the id the rollback burned. Measured: the failed run got id 7 and left `data/fixed/6`. So the test passes with the cleanup removed (n3). |
| **m3** atomicity test failed too early | **Fixed** (main point) | `test_fixes.py:205-260` raises in `_build_report` after the fixed version has been flushed, then asserts that no fixed version and no asset row were added. The 409 test still pokes `_active_model_fixes`, and the lock is still per-process; both are acceptable with the single-worker CMD. |
| **m4** stored flat set only partly enforced | **Fixed in code; test vacuous** | `versions.py:335-342` sets 0.0 for every stored-flat material. The test (`test_fixes.py:309-331`) uses the untextured cube, and for that cube the pass-1 rule already gave 0.0. It passes with the pass-1 rule restored (n3). |
| **m5** M5 backfill without an asset check | **Not fixed** (latent today; n4) | `importer.py:129-131` keys the old row's texture assets by file name (`granite.png`; rows are written with `tex_path.name`, `:200`). `:135-137` keys the new snapshot's by material name (`snap.textures` is keyed by material, `engine/io/snapshot.py:217`). The two can never be equal for a textured model, so a duplicate version is created (probe: 2 versions). The only textured test (`test_importer.py:160-182`) covers the "assets differ" case, which passes for the wrong reason. |
| **m6** web tests test hand-made shapes | **Partly** | `Retry-After` parsing is tested through the real `checkResponse` (`client.test.ts:15-36`). The `describeResult` fixture is now close to a real engine report. `ModelsView.vue:109-120` uses `Promise.allSettled`, but its test (`ModelsView.test.ts:45-61`) runs `Promise.allSettled` on two local mocks and never loads ModelsView, so it cannot fail. The no-auto-retry behaviour is still untested (n3). |
| **m7** overlays disagree with the engine | **Verified fixed** | `EDGE_SOFT = 5` (`Viewport.ts:10`) matches `engine/topo/edges.py:5`. Creases now come from the meshbuf's `edge_class` (`:237-261`), and soft edges no longer draw as outlines (`:169`). Geometry is built only when its layer is switched on (`:263-274`; `clear()` resets it on reload). The layer is renamed "Removed Faces" and uses the mapped ids. No Viewport tests (as before). |
| **m8** workspace UX | **Verified fixed** | Hotkeys work while a checkbox has focus (`useLayers.ts:44-56`, with a test). The fake run `id: 0` is gone (`triggerFix`, `WorkspaceView.vue:493-506`), and so is `onImageError`. |
| **m9** test DBs left behind | **Verified fixed** | `conftest.py:13-42` wraps setup and `yield` in try/finally. `db_helper.py:76-98` drops the databases of dead PIDs at session start, and `:68-73` warns when a drop fails. It has a test. Nothing was left after my runs. |
| **m10** CORS `*` with credentials | **Verified fixed** | `main.py:16-22` allows only `http://localhost:5190`, without credentials. The test fails against the old config. |
| **m11** import path built from a client string | **Verified fixed** | `importer.py:26-31` rejects separators and requires an exact match against `scan_source_directory`. Mutation-tested. The aside in the review, an unbounded `FixProfileConfig`, is still open (n12). |
| **m12** deployment notes | **Partly** | The N+1 is fixed with `selectinload(...ModelVersion.assets)` (`models.py:19,30,50`). The image-rollback caveat now applies to 0002 (see Migration). |
| **D7** | **Done as written** | See the D7 section below. |
| **D9** | **Done (the API side, per the ruling)** | See the D9 section below. |
| **D10** | **Done as written** | See the D10 section below. |
| **D11** | **Done as written** | See the D11 section below. |
| **D12** | **Done, with gaps** | See the D12 section below. |

## Brief items

### D7
> "`GET /api/versions/{id}/faces/{face_id}`: snapshot -> `{face_id, line, material, vertices}` from the OBJ `face_line`; fixed ->
> additionally `source_faces: [{face_id, line}]` from `source_faces.json`. Web: BEFORE shows "source line N"; AFTER shows "merged
> from N original faces (lines ...)" or the single source line; delete the `faceId + 1` fabrication. Tests for both version kinds."

**Done as written.**
- The endpoint is `versions.py:147-236`. For a fixed version it finds the source snapshot through `FixRun.fixed_version_id`.
- The web text is in `faceInspection.ts`, and the inspector is at `WorkspaceView.vue:171-186`.
- Tests: `test_versions.py:124-167` and `test_fixes.py:149-201`.
- Minor gap (n6): a fixed version from before the branch has no `source_faces.json`. Its AFTER pick then prints the *fixed* OBJ's own
  line as "source line N".

### D9
> "if the PNG writer lives only in `engine/cli.py`, move it to `engine/guard/render.py` … the run writes the six PNGs under its
> directory; the modal lists only views that exist; the button is hidden when none. Test: after a run the six files exist and the
> endpoint serves one."

**Done, for the API side.** The engine move was deferred by the controller's ruling.
- The API calls the private `engine.cli._write_guard_images` with the same arguments the CLI builds (`versions.py:444-454` against
  `cli.py:445-452`).
- Test: `test_fixes.py:45-64`.

### D10
> "`api/__main__.py` runs uvicorn on `settings.api_host` (127.0.0.1) / `settings.api_port` (8190); the `.claude/launch.json` api entry
> becomes `python -m api`; CORS allows only `http://localhost:5190` with `allow_credentials=False`; the `data_dir` default resolves
> relative to the repo root."

**Done as written.**
- `api/__main__.py:5-7`; `launch.json` gains an `api` entry (there was none before); `main.py:16-22`; `settings.py:7,14`.
- Tests: `test_health.py:12-46`.
- Note: Docker keeps `uvicorn … --host 0.0.0.0`. That is correct there, since `python -m api` would bind 127.0.0.1 inside the container.

### D11
> "api test fixtures get distinct geometry (and one test keeps the identical-bytes-two-names case from D0); `ModelsView.vue` matches
> file names exactly, not `endsWith`; `syncViewports` copies `zoom` and `fov` too."

**Done as written.**
- The fixtures are cubes of 8, 10, 12, 14, 16, 18 and 20.
- The identical-bytes case is `test_importer.py:124-150`.
- Exact matching is in `modelMatching.ts:4,8`.
- The zoom/fov copy is `Viewport.ts:384-388`, with a test.

### D12
> "after a fix run the API calls the engine's SketchUp writer … and writes `<run dir>/<name>.fixed.skp` plus the latest copy
> `OBJ FIXED RESULT/<name>.fixed.skp` (folder configurable via settings `skp_dir` …); `report.json` and the run response carry the
> path and the writer's summary; the workspace shows "SketchUp file: <path>" with a copy button. When the DLL is absent the run still
> succeeds and the UI says the SketchUp file was skipped and why. Tests with the DLL skip cleanly when it is missing. Also show the new
> guard totals … and `guard_merge_attempt`." Pointer brief: "the API run should call the same code path, not a copy of it."

**Done, with gaps.**

What is done:
- The API imports and calls `engine.cli._write_skp` (`versions.py:15,461-469`). That is the CLI's own function, not a copy.
- It passes `copy_dir=settings.skp_dir`, whose default is `<repo>/OBJ FIXED RESULT` (`settings.py:18`).
- Inside it, **only a run the engine passed replaces `<name>.fixed.skp`**. A failed run goes to `<name>.fixed.FAILED.skp` and the
  owner's file is kept (`engine/cli.py:396-414`).
- The report and the response carry the block (`FixRunOut.skp`).
- The UI shows the path with a Copy button, or the reason it was skipped (`WorkspaceView.vue:146-161`).
- The DLL-absent test passes (`test_fixes.py:354-371`).
- The totals and the merge-attempt verdict are shown.

Gaps:
- **The copy happens before the run is committed** (n1). The probe showed a run recorded as `failed`, with no fixed version, that had
  already replaced the owner's `.skp`.
- **The SketchUp C API is not serialized** across concurrent runs on different models (n2).
- `skp.path` is set even for a skipped run (n8).
- `test_fixes.py:334-351` asserts nothing when `written` is false, rather than skipping. No test checks that a failed run leaves the
  owner's file alone.
- The API copies the orchestration around the writer (`versions.py:376-486` against `cli.py:436-477`): the mtl/tex copy, the flat
  set and the report assembly. It is equivalent, but it has no QA sheet and it uses the stored flat set (intended by D6).
- In the Docker deployment the DLL cannot exist (the container is Linux), so every run there reports "SketchUp file skipped".

## Reverts
Both reverts are clean in the net result:
- No rescan or soft-delete route, function, button, test, ORM column or schema field remains (git grep, OpenAPI).
- The migration directory holds only `0001_initial` and `0002_flat_materials`.

The live database never received 0003: it is still at `0001_initial`.

## Migration 0002 on the live database
- **Live state:** the live database is at `0001_initial`, measured read-only. The chain is linear (0001 → 0002, head 0002).
- **The upgrade** adds one nullable JSON column (`0002_flat_materials.py:21`). That is a metadata-only change on Postgres 16, and it
  applies at container start (`alembic upgrade head` in `Dockerfile.api`).
- **Existing rows** get NULL. The code treats NULL as "recompute from the textures" (`versions.py:81-85,357-358,449-450`), as before.
- **The downgrade** drops only that column. **Safe.**
- **Rolling back to an older image** after 0002 has run still fails at start ("Can't locate revision"). It needs
  `alembic downgrade 0001_initial` with the new code first (m12). Document it with the deployment.

## Security
- **Guard images:** the whitelist runs before any database or path work (`fixes.py:16,34-38`). The path is built from the database
  row and the whitelisted view. Mutation-tested.
- **Assets and textures:** the name is used only in a parameterised lookup, and the path comes from the database row
  (`versions.py:100-144`). No traversal.
- **The new faces endpoint:** the face id is an integer and range-checked (`:169-170`). The file paths come from the database. No
  client string reaches the filesystem.
- **The SketchUp file path:** no endpoint serves it; it is only displayed.
  - The file names under the run directory and in the owner's folder are built from `mesh.name`. That is the OBJ's own `o`/`g` line
    (`engine/io/obj_reader.py:58-71`), and it is not sanitized (`versions.py:346-349`, `engine/cli.py:378,397-398`).
  - It is not a client string, but it does come from file content (n10).
- **Import filename:** exact match against the scan plus a separator check. Mutation-tested.
- **CORS:** one origin, no credentials. JSON bodies force a preflight, so cross-site POSTs to `/import` and `/fix` are blocked. The web
  calls `/api` on its own origin through the Vite or nginx proxy, so the single allowed origin costs nothing.

## Does the AFTER panel report what the engine ships?

**For every report produced on this branch, yes.** This was verified against a genuine `_build_report` of the live model, not only
against the hand-trimmed test fixture:
- rollback heading with its reason;
- failed invariants listed as failures, with "Run FAILED" kept apart from the guard verdict;
- backface pixels (`final.total`);
- grown pixels in the guard line;
- border shift, z-fight ties, closed cracks, the flicker breakdown, and the merge-attempt verdict;
- solidify and side rebuild.

The fixture in `describeResult.test.ts:5-114` is a trimmed copy of such a report. It keeps only 5 profile keys and 2 per-view
entries, but every key the function reads has the engine's shape.

**For the live data and for failed runs, no:** see N1 and N2.

## Would deploying break the running dashboard?
Nothing stops the app from starting:
- the build passes;
- the app imports on the merged tree;
- 0002 is additive and applies itself.

The deployment itself (untracked `docker-compose.yml`, `Dockerfile.*` and `nginx.conf` in the main checkout) already has problems the
branch does not fix. The owner should know about them:
- **The live model cannot be shown in Docker today.** The asset paths are stored with Windows `\` separators, so the Linux container
  answers 404 for both meshbufs of model 1 (measured). The branch still stores `str(path)` (`versions.py:385,402,413,439`;
  `importer.py:176,188,201`). Rows written natively and rows written in Docker are therefore not portable. `.as_posix()` would fix
  new rows; the 4 live rows need a one-off rewrite.
- **Every real fix run goes past nginx's default 60 s `proxy_read_timeout`.**
  - Measured: `fix_object` alone took 100.7 s on the live model at `n_dirs=128`, and every API-test run on a 12-40-face fixture took
    38-91 s.
  - `nginx.conf` sets no timeout, so the browser gets a 504 and an alert saying "Fix failed" while the run completes and commits.
  - The branch copes: it shows no fake run, a second click answers 409 while the lock is held, and a reload shows the result.
  - The fix is `proxy_read_timeout 900s;` on `/api/`, or a background job with polling.
- **No `.skp` is ever written by the Docker API**, because there is no DLL on Linux. D12's owner workflow needs the native
  `python -m api`.

---

## New findings

### Critical
None.

### Important

#### N1. The AFTER panel says "FLAT REGIONS MERGED" for runs whose stored report predates the branch, including the live v4
- **Where:** `web/src/utils/describeResult.ts:73-79`.
  - A missing `merge_report` is read as "not rolled back", which gives the "merged" heading.
  - `:66` defaults a missing guard verdict to PASSED.
  - The display path is `WorkspaceView.vue:92,439-447`.
- **Failure scenario:**
  1. After deployment, open model 1 with the API running natively: `python -m api`, the D10 entry point. (Docker gets the same result
     once the meshbuf 404 above is fixed.)
  2. `fetchVersionRun(4)` returns run 3, whose stored report is `{name, tris_*, passed, n_* ×4, one_sided_holes_*, guard_passed}`.
  3. The panel renders "AFTER · INSIDE REMOVED, FACES FLIPPED, FLAT REGIONS MERGED · Run PASSED · Guard PASSED (totals not
     reported)".
  4. The ledger's 09-23 check (`progress.md:26`) found that 2,656-tri result to be a rolled-back merge. That is the review's original
     C2 misreport, on the owner's only model. It lasts until the next run creates a new fixed version.
- **Evidence:** the committed `describeResult` run on the live run-3 JSON (read-only query) returns exactly that heading, with
  `runPassed: true`.
- **Fix:**
  - When `report.merge_report` is absent, use a neutral heading ("merge result not recorded", or "report predates run reports").
  - Show "guard not reported" instead of defaulting to PASSED.
  - Add a test built from the pre-branch report shape.

#### N2. A run that fails with an exception no longer shows its error; the panel shows the previous run instead (a pass-3 regression of D3)
- **Where:** `WorkspaceView.vue:497-499` together with `:439-447`.
  - `triggerFix` sets `latestRun = run` and then awaits `reloadModel()`.
  - Since 41300b4, `reloadModel()` sets `latestRun` from the latest *fixed* version's run, or to `null` when there is none.
  - A run that failed with an exception has no fixed version (`versions.py:502-517`), so its `error` is replaced at once.
- **Failure scenario:**
  1. The engine raises on a model. The API correctly returns 201 with `status: failed` and `error: "ValueError: …"`.
  2. The AFTER panel then shows the previous fix's report ("Run PASSED", the green guard line) as if nothing had happened.
  3. With no previous fix, it shows "Click 'Run Fix Pipeline'…".
  4. D3's "a failed run shows its error instead of a blank panel" no longer holds. Pass 1 kept the error.
- **Evidence:** read from the code; not run in a browser, because starting the web server is outside this review's rules. No web test
  covers `WorkspaceView`.
- **Fix:** keep the run `triggerFix` received when it has no fixed version, or when it is newer than the fixed version's run. For
  example, skip the `fetchVersionRun` overwrite when `latestRun.status === 'failed' && !latestRun.fixed_version_id`, or make
  `GET /api/versions/{snapshot}/run` the source and show the newest run for that snapshot. Add a small test around this choice (a
  pure function, as `describeResult` is).

### Minor

1. **n1. D12 copies the owner's `.skp` before the run is committed.**
   - `_write_skp` runs at `versions.py:461-469`, before `_build_report`, the `report.json` write and `db.commit()` (`:472-493`).
     Any exception after it records the run as failed and removes the run directory, but the owner copy stays.
   - Probe: the owner's `probe_owner.fixed.skp` existed after a run recorded `status=failed, fixed_version_id=None`.
   - Fix: write into the run directory with `copy_dir=None`, commit, and then do the owner copy (the engine's pass/FAILED rule) and
     store the `copied_to` result.
2. **n2. The SketchUp C API is not serialized.**
   - The per-model lock lets two runs on different models proceed at once, in two threadpool threads. `write_skp` and
     `check_skp_validity` each wrap an `SUInitialize`/`SUTerminate` session (`engine/io/skp_writer.py:314-322`) with no lock.
   - Unverified whether overlapping sessions crash the process, but nothing prevents them.
   - Fix: a module-level `threading.Lock` around the `_write_skp` call in `versions.py`.
3. **n3. Tests that cannot fail.**
   - The m2 directory assertion checks the wrong id (`test_fixes.py:252-254`; measured).
   - The m4 test uses a model with no texture (`:309-331`; measured).
   - The m6 "ModelsView 409" test never loads ModelsView (`ModelsView.test.ts:45-61`).
   - m5 has no positive textured case (`test_importer.py:160-182`).
   - The D12 `.skp` test asserts nothing when nothing was written (`test_fixes.py:334-351`).
4. **n4 (m5). The M5 backfill check never matches a textured model.**
   - The key mismatch is described in the table (`importer.py:129-137`).
   - With file-name keys on both sides, the live v1's MTL and texture digests would match exactly (`f5be2306…`, `2e50e9d8…`;
     measured with a scratch snapshot).
   - It is latent today, because the export's OBJ for that model has changed since v1 (sha `49207d2b…` against v1's `ce26e039…`).
     A re-import makes a new version either way, and the UI hides Import for files already imported.
   - Fix: key `new_assets` by `tex_path.name`, and add the textured positive test (the probe above).
5. **n5. The ledger still misreports the wave.** See I6 (`progress.md:34-53`). Rewrite it with the real commits for passes 1-3, the
   real item status and the measured counts before merging.
6. **n6. For a fixed version from before the branch, AFTER picking prints the fixed OBJ's own line as "source line N".**
   - This comes from the fallback at `faceInspection.ts:19`, which `faceInspection.test.ts:41` locks in.
   - Fix: for `viewKind === 'after'` with no `source_faces`, say "no provenance recorded for this version".
7. **n7. Guard modal gaps.**
   - The run writes `guard_fail_<i>.png` for failing oblique views (`engine/cli.py:347-348`). The endpoint's whitelist
     (`fixes.py:16`) and `guard_views` (`versions.py:456-459`) cannot reach them, yet the empty state claims they exist
     (`WorkspaceView.vue:231`).
   - The legend (`:218`) leaves out violet z-fight ties (`engine/guard/render.py`, the `_TIE` row).
8. **n8. A skipped `.skp` still has a path.** `versions.py:470` sets `skp.path` to a `.skp` that was never written, and `:475`
   copies it into `skp_path`. Only set it when `written` is true.
9. **n9. Five new `vue-tsc` errors** in `client.test.ts` (`global`); use `globalThis`. `pnpm build` does not type-check, so the
   build still passes.
10. **n10. Output and owner-copy file names come from the OBJ's `o`/`g` text, unsanitized** (see Security). Reduce it to a safe
    file name, or use the model's database name.
11. **n11. An import now sleeps for three stability intervals before the snapshot is taken.**
    - `find_source_file` calls `scan_source_directory` (up to two `read_manifest_stable` calls, `importer.py:29,67`) and then reads
      the manifest again (`:52`). At 1 s each, every import is about 2 s slower.
    - Reuse the scan's manifest map.
12. **n12. `FixProfileConfig` is still unbounded** (`schemas.py:52-58`; the aside in m11). For example, `guard_size` or `n_dirs` can
    be made arbitrarily large while holding the model lock.

---

## Test counts measured
- **API:** `pytest api` at `6f33222` gave **32 passed**, 0 failed, 9 deprecation warnings, in 663.47 s.
- **Web:** `pnpm test` gave **35 passed** (7 files). `pnpm build` passes. `vue-tsc --noEmit` shows 8 errors: 3 pre-existing
  (`Viewport.ts`) and 5 new (`client.test.ts`).
- **Engine:** not run; the branch does not touch it. 549 tests collected at `6f33222`, 566 on the merged tree.
- These match pass 3's reported counts (API 32, web 35).

Housekeeping: I removed my scratch worktree (`scratchpad/rereview-dash/wt`). The first review's worktree
(`scratchpad/review-dash/wt`, detached at c0f2ea4) is still registered.
