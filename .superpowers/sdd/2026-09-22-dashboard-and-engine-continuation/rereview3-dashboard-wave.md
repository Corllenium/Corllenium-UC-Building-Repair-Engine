# Re-review round 3: `feat/dashboard-wave` at `da8ba85` (pass 4)

This review is read-only. It covers the 16 pass-4 commits `55e728b..da8ba85` (on top of `6f33222`). It checks them against
the second review, `.superpowers/sdd/2026-09-22-dashboard-and-engine-continuation/rereview-dashboard-wave.md`:
- the Important findings N1 and N2;
- the Minor findings n1-n12;
- the items it left "partly" done: I2, I6, m2, m4, m5, m6, m12 and D12.

All `file:line` references are at `da8ba85` unless marked otherwise.

A "fails without the fix" claim below was measured by mutation, in a detached scratch worktree at `da8ba85`:
1. I undid the fix in the worktree.
2. I ran the fix's own test.
3. I restored the file from `da8ba85` with checkout filters, and checked that `git status` was clean afterwards.

## Verdict: **Approved with follow-ups**

| Severity (new findings) | Count |
|---|---|
| Critical | 0 |
| Important | 0 |
| Minor | 6 (plus 2 nits) |

**Blocking findings from round 2: all fixed.**
- **N1 is fixed.** The fix's tests fail without it. It was also checked on the live database's three stored reports. The new test
  fixture is the live run-3 report, key for key and value for value.
- **N2 is fixed.** The fix's tests fail without it. I also replayed WorkspaceView's `triggerFix` → `reloadModel` sequence on real
  API payloads: the failed run's error stays on screen.
- **The D12 copy timing (n1) is fixed.** The owner's `.skp` is copied only after the report is built and the database commit
  succeeds.
  - The injected-failure test fails without the fix.
  - The real-DLL copy for a passing run is tested, and that test fails when the copy is removed.
  - An engine-failed run leaves the owner's file alone (probe).
- **The SketchUp lock and the posix paths are correct for new rows.** Neither breaks existing rows natively or the Linux container.

**Merge:** the branch merges cleanly into feat-dashboard's current tip `97da65a` (tree `6deb6a0`). The merged tree's API suite
passes: **39 passed, 0 failed**.

**Nothing new is Critical or Important.** Six Minor findings remain. These should be fixed at merge time or right after it:
- **M1.** A database failure after the first commit deletes a committed version's files. The run is then recorded as failed after
  the owner's `.skp` was already replaced.
- **M2.** A failed owner copy is never recorded.
- **M3.** The m4 test is still vacuous, and the ledger says it was fixed.
- **M5.** The ledger still misreports in a few places.

---

## Evidence produced for this re-review

- **API at `da8ba85`: 39 passed, 0 failed, 9 warnings (deprecations), in 643.6 s.**
  - Run from the scratch worktree with `PYTHONPATH` pinned to it. The `api` and `engine` imports resolved to the worktree. Venv
    Python 3.12.10.
  - No other API pytest was running. Another session was running engine tests only, which do not touch Postgres.
  - Every session created and dropped its own `fixer_test_<pid>_*` database.
  - `pg_database` held `fixer`, `fixer_test`, `postgres` and the templates before my runs. It held the same after all 16 of my
    pytest sessions: the full run, the merged run, 13 mutants and the probes.
  - The SketchUp DLL is installed here (`C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUpAPI.dll`). So
    `test_fix_run_writes_skp_and_copies_to_skp_dir` really ran (PASSED, not skipped). It wrote into the test's temporary
    `skp_out`, never the owner's folder.
- **Web at `da8ba85`: vitest 46/46 (8 files).**
  - `vite build` passes, with the usual warning about a chunk over 500 kB (617.63 kB).
  - `vue-tsc --noEmit` reports 3 errors, all the pre-existing `src/three/Viewport.ts:332,333,360`. The 5 `client.test.ts`
    errors from round 2 are gone.
  - I re-ran vitest after all mutations: 46/46.
- **Engine: not run.** The 16 commits touch no file under `engine/`. Pytest collects 549 tests at `da8ba85` and 573 on the
  merged tree.
- **Merged tree** (`git merge-tree --write-tree feat-dashboard da8ba85`, with feat-dashboard at `97da65a`): clean, tree `6deb6a0`.
  - Since the merge base, feat-dashboard changed nothing under `api/`, `web/`, `alembic.ini` or `pyproject.toml`. The merged
    `api/` and `web/` are therefore byte-identical to `da8ba85`.
  - The engine functions the API imports keep their signatures: `_build_report`, `_write_guard_images`, `_write_skp`, `fix_object`.
    `FixResult` only gains `sheet_flipped` and `sheet_report`.
  - `api.main` imports on the merged tree and serves the same 14 OpenAPI paths.
  - Merged API suite: **39 passed, 0 failed**, 9 warnings, in 923.1 s. It was slower because another session's full engine
    suite ran at the same time.

### Mutation checks (each restores the pre-fix code and runs the finding's own test)

| # | Mutant | Test(s) | Result |
|---|---|---|---|
| N1 | `describeResult.ts` from `6f33222` | `describeResult.test.ts` | **2 of 9 fail** (`'…FLAT REGIONS MERGED'` received; `true` received for `guardPassed`) |
| N2 | `resolveActiveRun` always returns the fetched run | `runResolution.test.ts` | **2 of 8 fail** |
| A (n1) | owner copy back inside `_write_skp` (`copy_dir=settings.skp_dir`), before the commit | `test_fix_run_failure_after_skp_does_not_replace_owner_skp` | **fails**: `'new fixed skp content' == 'original owner skp content'` |
| L (D12) | post-commit owner copy disabled | `test_fix_run_writes_skp_and_copies_to_skp_dir` (real DLL) | **fails**: `skp_out/cube.fixed.skp` missing |
| B (n2) | `with _skp_lock:` removed | `test_skp_writing_is_serialized_by_lock` | **fails** |
| C (m12) | fixed-version asset paths back to `str()` | `test_run_fix_endpoint` | **fails**: `'\\' not in 'fixed\\1\\cube.fixed.obj'` |
| D (m12) | snapshot asset paths (importer) back to `str()` | all 10 importer tests, `test_get_meshbuf` and `test_run_fix_endpoint` | **all pass**: untested (M4) |
| E (m2) | `out_dir` cleanup removed from the exception handler | `test_fix_atomic_rollback_on_exception` | **fails**: `data/fixed/1` exists (the test is no longer vacuous) |
| F (m4) | pass-1 flatness rule restored | `test_stored_flat_materials_enforced_to_zero_std` | **still passes**: vacuous (M3) |
| G (n4/m5) | new textures keyed by material name again | `test_m5_backfill_succeeds_for_unchanged_textured_model` | **fails**: 2 versions |
| H (n11) | second manifest read restored | `test_find_source_file_does_not_redundantly_read_manifest` | **fails**: 2 reads |
| I (n10) | sanitizer bypassed | `test_fix_pipeline_sanitizes_mesh_name` | **fails**: status `failed` |
| K (n7) | whitelist back to the six axis views | `test_guard_view_includes_and_serves_failing_views` | **fails**: 404 |
| K2 (n7) | failing views no longer listed in `guard_views` | `test_guard_images_written_by_run`, `…_failing_views` | **both pass**: untested (M4) |
| M (n8) | skipped `.skp` gets a `path` again | `test_fix_run_succeeds_when_skp_dll_absent`, lock test | **both pass**: untested (M4) |
| n6 | `faceInspection.ts` from `6f33222` | `faceInspection.test.ts` | **1 of 5 fails** |
| m6 | `loadModelsData` with `Promise.all` | `ModelsView.test.ts` | **1 of 5 fails** |

### Probes
All of these were run on scratch copies and never committed.
- **N1 on the live data** (a read-only query of `fix_runs`, then the committed `describeResult` called as `WorkspaceView.vue:285`
  calls it):
  - Runs 1-3 (fixed v2-v4) all render the heading "INSIDE REMOVED, FACES FLIPPED · merge not reported", then "Run PASSED" and
    "Guard PASSED (totals not reported)". There is no merge-attempt line.
  - The new test fixture (`describeResult.test.ts:273-294`) has exactly the live run 3's 11 keys and values.
- **N2 on real API payloads:**
  - A run whose engine raised gives `{id 7, status failed, fixed_version_id null, report_json null, error "ValueError: …"}`.
  - `GET /versions/5/run` returns the previous run (id 4, completed).
  - Replayed through `loadVersionRunOnMount` → `resolveActiveRun` → `describeResult`, the panel shows run 7, "Fix Run Failed"
    and the error. That holds with a previous fixed version, with none, and when fetching the previous run fails.
  - The pre-fix code showed run 4 as "…FLAT REGIONS MERGED", `runPassed: true`.
- **D12 owner copy.** One cached engine result drove every run below, and `_write_skp` was faked so the copy logic runs quickly:
  - **P1, the engine fails the run** (`passed=False`): status `failed`. The owner's `cube.fixed.skp` is untouched. The new file goes
    to `cube.fixed.FAILED.skp`. `copied_to` and `previous_kept` are stored in both the database and `report.json`.
  - **P1b, a passing run after it:** the owner's file is replaced and the stale FAILED copy is deleted. The deletion
    (`removed_stale_failed_copy`) is recorded nowhere (M2).
  - **P1c, the owner copy raises `PermissionError`:** status `completed`, and the owner's file is unchanged. The database and
    `report.json` hold `written: true` and `copied_to: null`, with **no `copy_error`**. `skp_summary` names the run-directory
    path (M2).
  - **P2, the second commit raises** (after the first one succeeded):
    - The response is 201, `status: failed`, with the simulated error.
    - The owner's file **was replaced**.
    - Run 4 is committed as `completed` with fixed v5, but its run directory was deleted, so `GET /versions/5/meshbuf` returns 404
      "OBJ file missing on disk".
    - v5 is now the model's latest fixed version (M1).
- **Paths:**
  - The live `version_assets` table has 6 rows with `\` separators (v1: obj, mtl and texture; v2-v4: obj).
  - Natively both spellings resolve (`exists()` is True for each).
  - On Linux the live row becomes a single file name (`/app/data/snapshots\ce26e0392ab0\CHTM_SIDE_WALK_2nd_floor.obj`), so it
    still 404s. That is unchanged from round 2.
- **Real export names:** of the 91 OBJ files in `CKPT17`, only the whole-scene `CKPT17-CLEAN.obj` has a name the sanitizer
  changes. Its first group line is `Mesh1 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model`. All 90 split objects are
  unaffected, including "CHTM 3rd floor", whose `o` name is `CHTM_3rd_floor`.

---

## Second-review findings: status at `da8ba85`

| Round-2 item | Status | Evidence |
|---|---|---|
| **N1** AFTER panel says "FLAT REGIONS MERGED" for reports that predate the branch | **Verified fixed** | `describeResult.ts:77-89`: with no `merge_report` the heading is "… · merge not reported". It never says merged or not rolled back, and `isRolledBack` is not displayed anywhere. `:65-70,91-96` gives "Guard not reported" instead of defaulting to PASSED. The mutation makes 2 of 9 tests fail. The live runs 1-3 render "merge not reported", and the test fixture equals the live run 3. New engine reports always carry `merge_report` (`engine/cli.py:232`), so they are unaffected. |
| **N2** a failed run's error is replaced by `reloadModel` | **Verified fixed** (for the session) | `runResolution.ts:10-20` keeps a `failed` run that has no fixed version unless the fetched run is newer. It is wired at `WorkspaceView.vue:444-445`, and `triggerFix` sets the run first (`:496-497`). The mutation makes 2 of 8 tests fail, and the real-payload replay shows the error in all three cases. The wiring was read, not run: no component test exists, and starting the web server is outside this review's rules. After a browser reload the panel shows the last completed run again, as the round-2 fix option allowed. |
| **n1** owner `.skp` copied before the commit | **Verified fixed** | `versions.py:477-486` calls `_write_skp(copy_dir=None)`. The owner copy is at `:516-540`, after `_build_report` (`:492`), the `report.json` write (`:506`) and `db.commit()` (`:513`). A pass writes `<name>.fixed.skp`; a failed run writes `<name>.fixed.FAILED.skp` and keeps the owner's file. That is the engine's rule (`engine/cli.py:396-414`), measured in P1. The test at `test_fixes.py:386` injects the failure in `_build_report`, after the `.skp` step, and fails without the fix (mutant A). The real-DLL test at `:345` fails when the copy is removed (mutant L). Remaining gaps: M1 and M2. |
| **n2** SketchUp C API not serialized | **Verified fixed** | A module-level `_skp_lock` (`versions.py:33`) is held around the only SketchUp entry point in `api/` (`:477-486`). `_write_skp` catches every exception (`engine/cli.py:388-393`), so the lock always releases. Mutant B fails. The lock is per process: that is right for the single uvicorn worker, and it does not serialize against a CLI process running at the same time. |
| **n3** tests that cannot fail | **Partly** | Now real: the m2 directory check (E fails), m5's textured positive case (G fails), and m6's `loadModelsData`, which `ModelsView.vue:110` now calls (its mutant fails). The D12 test now skips when nothing was written (`test_fixes.py:356-357`). **Still vacuous:** the m4 test (F passes; M3). |
| **n4 / m5** backfill keys never match | **Verified fixed** | `importer.py:128-130` keys by `tex_path.name`, matching the stored rows (`:193`). The positive test at `test_importer.py:185` fails without the fix (G). |
| **n5 / I6** ledger misreports | **Partly** | All 55 hash citations (43 distinct commits) now resolve to commits on the branch, and passes 1-4 are separated. It still labels pass 1's test-DB work as D10, cites a route that never existed, has no measured counts, and claims n3 in full (M5). |
| **n6** a pre-branch AFTER pick shows "source line N" | **Verified fixed** | `faceInspection.ts:19` now says "no provenance recorded for this version". The API returns `source_faces: []` for such versions (`versions.py:190-240`), and that also reaches `:19`. The mutation fails 1 of 5. |
| **n7** failing guard views unreachable; legend | **Verified fixed** | `fixes.py:16-18` whitelists `fail_0..fail_25` (engine `VIEWS_26` indices; `engine/cli.py:348`), and `versions.py:473-475` lists the ones that exist. `WorkspaceView.vue:218` adds the violet z-fight tie, and `:342-344` names the views. Mutant K fails. The listing itself is untested (K2 passes; M4). |
| **n8** skipped `.skp` still has a path | **Fixed in code, untested** | `versions.py:487-490,495`. Mutant M passes (M4). |
| **n9** `vue-tsc` errors from `global` | **Verified fixed** | `vue-tsc` reports 3 errors, all pre-existing in `Viewport.ts`. |
| **n10** file names from the OBJ's `o`/`g` text | **Verified fixed** | `versions.py:36-43,358-359` falls back to `model_<id>`. Mutant I fails. Nit: for names with other characters the dashboard's owner copy is no longer named like the CLI's. Today that is only the whole-scene `CKPT17-CLEAN.obj`. |
| **n11** import sleeps three intervals | **Verified fixed** | `importer.py:29,46-47` reuses the scan's manifest map. Mutant H fails. Behaviour is unchanged for the real folder: it has no root manifest and no name is in both the root and `split/`. |
| **n12** `FixProfileConfig` unbounded | **Verified fixed** | `schemas.py:53-68`. The bounds fit the engine's units: exposure and flicker cap are fractions (`engine/vis/exposure.py:113-122`), and texture std is in 0-255. The web's profile (`n_dirs` 128) is inside them. Test: `test_fixes.py:470`. |
| **I2** heading and run after reload | **Verified fixed** | The mount load goes through `loadVersionRunOnMount` (`runResolution.ts:22-32`, 3 tests). The heading for pre-branch runs is N1's, and the overwrite is N2's. |
| **m2** orphan directories | **Verified fixed** | The test is now real (E). |
| **m4** stored flat set | **Fixed in code; test still vacuous** | M3. |
| **m6** web tests on hand-made shapes | **Verified fixed** | See n3. `client.test.ts:70-82` also pins "no auto-retry on 409". |
| **m12** deployment notes | **Partly** | The N+1 fix stands. New rows are posix at all 7 write sites (`versions.py:398,415,426,452`; `importer.py:169,181,194`). The 6 live rows keep `\`, so the Linux container still 404s the live model. There is no code for them, and the image-rollback caveat is still not documented in the branch. Both are raised only as owner decisions in feat-dashboard's record (`12a5f62`). See M6. |
| **D12 gaps** from round 2 | **Fixed**, except M1 and M2 | The copy comes after the commit (n1). The lock (n2). `path` only when written (n8). The test skips instead of asserting nothing. There is now a test that an exception-failed run leaves the owner's file alone; the engine-failed case was checked only by probe P1. |

## The four questions

1. **A report without a merge section: "merge not reported", never merged and never "not rolled back".** Yes.
   - Shown on the real v4 report shape. The test fixture is identical to the live run 3, and the live runs 1-3 render that heading.
   - The test fails without the fix.
   - Nothing else in the panel speaks for the merge. The "merge attempt" line needs `guard_merge_attempt`, which old reports
     lack.
2. **A run that fails with an exception keeps its error after `reloadModel`.** Yes.
   - The unit tests fail without the fix.
   - The replay on the real API payload shows the error with and without a previous fix.
   - This holds for the session. A browser reload shows the last completed run.
3. **The owner's `.skp` is copied only after the report is built and the commit succeeds, and only for a passing run.** Yes.
   - The order is build → `report.json` → commit → copy.
   - An engine-failed run writes `<name>.fixed.FAILED.skp` beside the owner's file and leaves the owner's file untouched. That is
     the engine's own rule (P1).
   - The injected-failure-after-`.skp` test exists and fails without the fix.
   - Caveat (M1): if the database fails after the first commit, the generic handler deletes that committed run's files and records
     a new failed run, after the owner copy already happened.
4. **The lock and the posix paths.** Both are correct.
   - The lock serializes every SketchUp C API call in the process and always releases.
   - New rows are posix. Natively the existing backslash rows still resolve (measured).
   - The Linux container is not made worse:
     - `./data` is shared, so rows written natively now resolve there.
     - Without the DLL, `written` is false and the post-commit copy is skipped (`versions.py:517`).
     - `skp_writer` imports nothing Windows-only at module level.
   - Not done: the 6 existing backslash rows still 404 in the container (M6).
   - The container side was checked by reading and by path semantics, not by running a container (outside this review's rules).

## Did the 16 commits break anything else?

- **API behaviour.**
  - The changes are the intended ones: 422 for an out-of-bounds profile, sanitized output names, the failing views listed and
    served, and the owner copy after the commit.
  - All 39 tests pass. The engine interface the API uses is unchanged on feat-dashboard.
  - The sanitizer renames no current split export.
  - The n11 change is behaviour-neutral for the real export folder.
- **Web panels.** No regression found.
  - The describeResult changes affect only reports with no merge or guard data.
  - `formatViewName` handles `fail_<i>`.
  - The ModelsView refactor keeps the same error flow.
  - Nit: "Guard not reported" is drawn in the failure colour (`WorkspaceView.vue:113`, via `guardPassed=false`). Neither old
    nor current reports can reach it.
- **Tests that now pass vacuously or cover nothing.**
  - The m4 test (M3).
  - Three changes with no test at all: importer posix, fail-view listing, and n8 (M4).
  - The new lock test only checks that the lock is held during the call, not that two runs serialize. That is enough to catch
    removal (B).
- **Ledger truthfulness.** Improved, but not accurate yet (M5).

## New findings

### Critical
None.

### Important
None.

### Minor

**M1. A database failure after the first commit deletes the files of a committed fixed version, and records the run as failed after
the owner's `.skp` was replaced.**
- **Where:**
  - The post-commit block (`versions.py:516-540`) sits inside the route's `try`.
  - Its generic handler (`:549-564`) assumes nothing was committed: it runs `rollback()`, then `shutil.rmtree(out_dir)`, then
    records a new failed run.
  - Only `OSError` is caught inside the block (`:533`). A database error in the second `commit()` or `refresh()` (`:531-532`)
    therefore reaches that handler.
- **Probe P2** (the second commit raises): the response is `status: failed`, and the owner's file already holds the new model.
  - Run 4 stays `completed` with fixed v5, but `data/fixed/4` is gone.
  - `GET /versions/5/meshbuf` returns 404 "OBJ file missing on disk".
  - v5 is the model's latest fixed version. From reading the code: `WorkspaceView` picks it (`:368-372`), and `reloadModel`
    stops at the 404 on `:441` for every load, until a new run.
- **Scope:** the trigger is rare (the database failing within a second of a successful commit). The same flaw already existed for
  the `refresh` at `:514` (pass 3). The 16 commits widen the window.
- **Fix:**
  - Move the owner copy out of the `try`, or give it its own `except Exception` that logs and records `copy_error`.
  - Never `rmtree` the directory of a run that is already committed.

**M2. A failed owner copy, and the removal of a stale FAILED copy, are recorded nowhere.**
- **Where:** `copy_error` (`versions.py:533-534`) and `removed_stale_failed_copy` / `stale_failed_copy_error` (`:535-540`) are set
  on the in-memory dict after the last commit, or with no commit at all.
- **Probe P1c:** the database and `report.json` hold `written: true`, `copied_to: null` and no error. The UI shows "SketchUp file:
  `<run dir>\cube.fixed.skp`" (`describeResult.ts:164`) and gives no sign that `OBJ FIXED RESULT` still holds the old model.
  The engine's own comment names the likely cause: "the owner still has the previous file open" (`engine/cli.py:406`).
- **Probe P1b:** the removal is not recorded either. The CLI records both in `report.json`.
- **Root cause:** the API copies the engine's copy rule (`versions.py:517-540` against `engine/cli.py:396-414`) instead of calling
  it. The pointer brief asked for "the same code path, not a copy of it".
- **Fix:**
  - Commit after the whole block, including the error branches, and show `copy_error` in the panel.
  - Better: have the engine expose the copy step as a helper that both callers use.

**M3. The m4 test is still vacuous, and the ledger says it was fixed.**
- **Where:** `test_fixes.py:318-341`.
  - The new line `:338` patches `texture_flatness`, but the imported cube has no MTL (`engine/tests/fixtures/build.py:17`,
    `mtllib=None`). So `versions.py:328-335` never calls it.
  - The patch also returns a dict where the real function returns a float (`engine/io/mtl.py:49-51`).
  - Mutant F (the pass-1 rule) still passes.
- `progress.md:80` claims "non-zero std inputs".
- **Fix:** use a textured fixture whose texture std is non-zero, like the importer tests' `textured_source_dir`, and assert that
  the stored-flat material reaches `fix_object` at 0.0.

**M4. Three pass-4 changes have no test.**
- The snapshot rows' posix paths (`importer.py:169,181,194`): mutant D passes. The new assertion (`test_versions.py:45-49`)
  checks only the fixed version's rows.
- The listing of failing views (`versions.py:473-475`): mutant K2 passes. The only fail-view test writes its PNG after the run.
- The n8 "no path when skipped" rule (`versions.py:487-490,495`): mutant M passes.

**M5. The ledger still misreports in places** (`progress.md`).
- `:47` labels pass 1's test-DB work (`f5adf2a`) "D10". The brief's D10 is host/port/CORS/data dir (`fix-wave-1-brief.md:73`),
  done in pass 2 (`ac94bdc`, `:54`). `:48` leaves D10 out of pass 1's divergences.
- `:52` says D7 uses `GET /api/versions/{id}/source_faces`. That route never existed: `e98126f` adds `/faces/{face_id}`.
- There are no measured test counts anywhere, although round 2 asked for them.
- `:80` (n3) is false for m4 (see M3).
- `:82` (m12) says "container portability" but does not mention that the live rows are unchanged.
- What is fixed: every commit hash cited now exists on the branch.

**M6. The live model still cannot be shown by the Linux container; m12 is fixed for new rows only.**
- The 6 live `version_assets` rows keep `\` separators (measured read-only). No migration, one-off script or read-side
  normalization ships.
- The 0002 image-rollback caveat is also still only in feat-dashboard's record.
- Both are raised there as owner decisions (`12a5f62`: "one-line SQL fix").
- This is not a regression. It needs the owner's decision and a rewrite of those 6 rows before the Docker dashboard can show the
  live model.

**Nits.**
- `ResultDescription.mergeReported` (`describeResult.ts:9`) is declared but never set.
- The failure colour for "Guard not reported" (see above).
- The n10 name divergence for `CKPT17-CLEAN.obj` (see the table).

## Merge readiness

- **Clean merge.** `git merge-tree --write-tree feat-dashboard da8ba85` gives tree `6deb6a0` with no conflicts, against
  feat-dashboard's current tip `97da65a`, one commit past `12a5f62`.
- **Merged `api/` and `web/` equal `da8ba85`.** The engine interface is unchanged, and the app imports and serves 14 paths.
- **Merged API suite:** 39 passed, 0 failed. The merged web tree is the same as `da8ba85`'s (46/46).
- **Before or at the merge** (doc-only or small):
  - Correct the ledger (M5), including the measured counts: API 39, web 46, 3 pre-existing `vue-tsc` errors.
- **Follow-ups** (not blocking):
  - M1 and M2 (the post-commit block).
  - M3 and M4 (tests).
  - M6 (the owner's decision on the 6 rows).
  - The deployment items already recorded: nginx `proxy_read_timeout`, and no DLL in the container.

## Test counts measured

| Suite | Tree | Result |
|---|---|---|
| API (`pytest api`) | `da8ba85` | **39 passed**, 0 failed, 9 warnings, 643.6 s |
| API (`pytest api`) | merged `6deb6a0` | **39 passed**, 0 failed, 9 warnings, 923.1 s (CPU shared with another session's engine suite) |
| Web (`vitest run`) | `da8ba85` (= merged) | **46 passed** (8 files); re-run after the mutations: 46/46 |
| Web `vue-tsc --noEmit` | `da8ba85` | 3 errors, all pre-existing (`Viewport.ts:332,333,360`) |
| Web `vite build` | `da8ba85` | passes (617.63 kB chunk warning) |
| Engine | — | not run (no engine change); 549 collected at `da8ba85`, 573 merged |
| API mutants | `da8ba85` | 13 run: 9 fail as they should, 4 pass (F vacuous; D, K2, M untested) |
| Web mutants | `da8ba85` | 4 run: all fail as they should |

Counts against pass 3: API went from 32 to 39 (7 new tests), and web from 35 to 46 (11 new tests, 8 files).

## Housekeeping

- **Removed:**
  - My scratch worktree (`scratchpad/rereview3/wt`). `git worktree remove` unregistered it. It stopped on pnpm's over-long
    paths, so I deleted the rest with the `\\?\` prefix.
  - The merged-tree extract.
- **Kept in `scratchpad/rereview3/` as evidence:**
  - `api_full.log`, `api_merged.log`, `mutate_api.out` and `mutlogs/`.
  - `mutate_api.py`, `test_zz_rereview3_probes.py`, `probe_out.json`, `probe_n1_live.mjs`, `probe_n2_flow.mjs` and
    `live_runs.json` (the read-only export of the live `fix_runs`).
- **Left untouched:**
  - No test database is left.
  - The main checkout was not touched. It is still on feat-dashboard, with the same working-tree state as at the start.
  - The first review's worktree (`scratchpad/review-dash/wt`, detached at `c0f2ea4`) is still registered. It is not mine.
