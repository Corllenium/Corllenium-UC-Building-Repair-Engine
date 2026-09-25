# Brief 12 — dashboard follow-ups from re-review round 3 (after the merge cba42a5)

Source: `.superpowers/sdd/2026-09-22-dashboard-and-engine-continuation/rereview3-dashboard-wave.md`
(approved with follow-ups: 0 Critical, 0 Important, 6 Minor). The branch was merged into
`feat-dashboard` as cba42a5; these are the Minor findings, to be fixed on top of it.

Where: worktree `.hermes/worktrees/dashboard-wave`, branch `feat/dashboard-wave`. First bring it up to
date with `git merge --ff-only feat-dashboard` (it is an ancestor of cba42a5). Test-first. For each
item, undo the fix once and see its test fail, then restore it. Report how you checked. One commit per
item with a body that says why. Stage by name. The controller merges.

Measured before this brief (the reviewer, at da8ba85 and on the merged tree): API 39 passed, web vitest
46/46, `vue-tsc` 3 errors that predate the branch (`src/three/Viewport.ts:332,333,360`), `vite build`
passes.

## Items, in this order (line numbers at da8ba85)

1. **M1: a database failure after the first commit deletes a committed run's files.**
   - The post-commit block (`api/routers/versions.py:516-540`) sits inside the route's `try`.
   - Its generic handler (`:549-564`) assumes nothing was committed. It rolls back, runs
     `shutil.rmtree(out_dir)`, and records a new failed run.
   - Probe P2 in the review: the second commit raises. The response is `failed`, and the owner's `.skp`
     was already replaced. The committed run 4 stays `completed` with fixed v5, but `data/fixed/4` is
     gone, so `GET /versions/5/meshbuf` returns 404.
   - Fix: the owner copy gets its own `except Exception`, which logs the error and records it as
     `copy_error`. Never `rmtree` the directory of a run that is already committed.
   - Test: inject a failure in the second commit. The committed run keeps its files and its meshbuf
     still loads.
2. **M2: a failed owner copy, and the removal of a stale FAILED copy, are recorded nowhere.**
   - `copy_error` (`versions.py:533-534`) and `removed_stale_failed_copy` / `stale_failed_copy_error`
     (`:535-540`) are set on the in-memory dict after the last commit.
   - Fix: commit after the whole block, including its error branches, and write the same keys into
     `report.json`.
   - Show `copy_error` in the AFTER panel (`web/src/lib/describeResult.ts:164` renders
     "SketchUp file: …"). The owner must see that `OBJ FIXED RESULT` still holds the old model and why.
     The engine names the likely cause, "the owner still has the previous file open"
     (`engine/cli.py:406`).
   - The API copies the engine's copy rule (`engine/cli.py:396-414`) instead of calling it. You may move
     that rule into one helper that both `engine/cli.py` and the API call. If you do, touch no other
     engine file, and the engine suite must stay green.
3. **M3: the m4 test is vacuous.**
   - `api/tests/test_fixes.py:318-341` patches `texture_flatness`, but the imported cube has no MTL, so
     `versions.py:328-335` never calls it. The patch also returns a dict where the real function returns
     a float (`engine/io/mtl.py:49-51`).
   - Fix: use a textured fixture whose texture std is non-zero, like the importer tests'
     `textured_source_dir`. Assert that the stored-flat material reaches `fix_object` at 0.0.
   - It must fail with the pass-1 rule restored (the review's mutant F).
4. **M4: three pass-4 changes have no test.** Each test must fail when its change is undone:
   - (a) the snapshot rows' posix paths (`api/services/importer.py:169,181,194`; the review's mutant D);
   - (b) the listing of failing guard views that the run itself wrote (`versions.py:473-475`; mutant K2);
   - (c) no `path` for a skipped `.skp` (`versions.py:487-490,495`; mutant M).
5. **Nits.**
   - `ResultDescription.mergeReported` (`describeResult.ts:9`) is declared but never set: set it or
     remove it.
   - "Guard not reported" is drawn in the failure colour (`WorkspaceView.vue:113`): use a neutral one.
6. **Ledger.** Append "Pass 5" to `.superpowers/sdd/2026-09-22-dashboard-and-engine-continuation/progress.md`.
   Give a commit → item table, and the measured counts exactly as printed: API, web vitest, `vue-tsc`
   error count. No claim without its count.

## Not in this brief (the owner decides)

- **M6:** the 6 live `version_assets` rows with backslash paths. The Linux container cannot load the
  live model until they are rewritten.
- The Docker rebuild, and nginx `proxy_read_timeout` (60 s; a run takes more than 100 s).

## Rules

- Never touch the live database `fixer`, the containers or the running servers.
- Never touch `OBJ FIXED RESULT/`: API tests write to their own temporary `skp_out`.
- Never touch `docker-compose.yml` or the Docker files.
- API tests (`pytest api`) use a per-session database `fixer_test_<pid>_*` since cba42a5, so they may run
  while another session runs its own.
- Run from the worktree root with `PYTHONPATH` set to it.
- Leave the engine alone apart from the optional M2 helper.
