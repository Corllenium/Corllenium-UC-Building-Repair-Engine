# SDD ledger — plan: docs/superpowers/plans/2026-09-26-3d-error-filter.md

Spec: docs/superpowers/specs/2026-09-26-3d-error-filter-design.md (read; binding).
Worktree: D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter, branch feat/error-filter, from 27545ba.
Run SDD scripts from the main checkout with explicit refs (feat/error-filter or SHAs); both share one object store.

## Pre-flight scan (2026-09-26 03:30)

| Tasks | Shared file / interface | Produces vs consumes | Found |
|---|---|---|---|
| 1 ↔ 2 | `double_layers()["pair_list"]` | 1 returns `[i, j, shared, opposite]` sorted; 2 iterates `for i, j, _s, _o in dl["pair_list"]` | consistent |
| 1 ↔ 3 | `engine/fixes/overlap.py::double_layers` | 1 changes the return dict; 3 replaces the pixel stage (from `ids_all = ...`) and keeps the output, its test reads `result["pair_list"]` | consistent; 3 runs after 1 |
| 2 ↔ 3 | `two_sided_wall` fixture; px > 0 | 2 appends the fixture and asserts the flicker spot value > 0; 3's equality test uses the fixture | consistent; 3 after 2 |
| 2 ↔ 4 | `find_errors`, `two_sided_wall` | 4's `cmd_errors` calls `find_errors`; its test uses the fixture | consistent |
| 2 ↔ 5 | `find_errors(read_obj(path), FixProfile())` | route output = 2's dict | consistent |
| 5 ↔ 6 | `api/routers/errors.py::write_errors`, `errors_file` | 6 imports `write_errors` into versions.py; errors.py imports no router, so no import cycle | consistent |
| 2 ↔ 8 | errors-file keys | engine: counts (7 kinds), faces (5 face kinds), open_edges, cracks, flicker_pairs, spots (7 kinds) = TS `ErrorsFile` | consistent |
| 7 ↔ 8 | `ErrorsFile` type | 7 imports the type from 8 | 8 before 7 (plan's Order) |
| 8 ↔ 10 | `overlayFaces`, `blinkColors`, `openEdgeSegments`, `crackPoints`, `partnersOf`, `kindsOf`, `ERROR_KINDS`, `defaultFilter` | all defined in 8 with the signatures 10 calls | consistent |
| 9 ↔ 10 | Viewport `setErrorOverlay`, `setErrorBlink`, `setErrorLines`, `setErrorPoints`, `flyTo`, `originOffset` | defined in 9 exactly as 10 calls them | consistent |
| 6 ↔ 11 | AFTER errors file after a fix run | 11 checks it in the browser | consistent |

| Task | Self-consistency |
|---|---|
| 1 | test asserts count 1, opposite, shared == area on `back_to_back_pair` (one partial opposite-wound double layer) — matches the fixture's docstring; code adds `pair_list` to both return paths |
| 2 | fixtures and assertions checked by hand: two_sided_wall pairs {(0,2),(1,3)} (identical triangles; (0,3),(1,2) share only the diagonal); box_with_partition faces 12, 13 hidden (fixture docstring); cube face 0 turned sees only the closed interior on its front -> ORIENT_FLIP; square: 4 open edges; t_junction_strip: T-vertex 4 at (10,10,0), face 6 zero-area; JSON round trip needs only lists/ints/floats/bools — the code produces those |
| 3 | replacement keeps `partners`, `plane_index` (built just above `ids_all`) and turns `px_plane` back into a list for the output code; `tri = positions_c[faces]` exists at the function's top; equality test's reference rebuilds partners from `pair_list` and counts as the old loop did (the first face itself is excluded because `partners[f]` never holds f). Risk: pixels exactly on a partner's edge could differ by tolerance (caster `_contains` vs barycentric eps 1e-6) — the equality test would show it |
| 4 | `_load_snapshot` needs exactly one .obj — the test writes one; `write_obj(mesh, path)` signature as used in api conftest |
| 5 | routes `/api/versions/{id}/errors` do not collide with versions' `/api/versions/{id}` |
| 6 | variable names in `run_fix_pipeline` confirmed: `profile` (~l.340), `result` (~l.358), `settings`, `logger` (l.27); insertion before the success `return fix_run` (~l.560), not the except path (~l.573) |
| 7 | `checkResponse`, `API_BASE` exist in client.ts |
| 8 | test expectations recomputed by hand (priority colours, blink swap, origin shift, palette wrap) — consistent with the code |
| 9 | no unit test (WebGL); vue-tsc gate |
| 10 | `pickedFace` shape confirmed (`viewKind`); `decodeMeshbuf`, `fetchMeshbuf` already imported |

## Rulings

- Ruling: execute in the worktree `.claude/worktrees/error-filter` (branch `feat/error-filter`), not the shared main checkout — other sessions and records edit the main checkout — costs one merge into feat-dashboard at the end.
- Ruling: implementers run from the worktree root with `"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"` and `PYTHONPATH` = the worktree root; the plan's relative `data/...` paths mean `D:/PROJECTS/UC MODEL FIXER/data/...` (data/ is git-ignored and not in the worktree) — costs nothing if wrong beyond a path error the implementer sees at once.
- Ruling: the web tasks run `pnpm --dir web install --frozen-lockfile` once in the worktree before vitest — node_modules is not in a fresh worktree — costs a minute.
- Ruling: Task 11 (deploy + browser check) is done by the controller, not a subagent — it touches the live containers and ends with screenshots for the owner, who asked "I should be able to see it in the dashboard" — if wrong, a subagent would have to redo the checks.
- Ruling: order 1, 2, 3, 4, 5, 6, 8, 7, 9, 10, 11 as the plan's Order section says.

## Progress
- Task 1: dispatched 03:35 (implementer haiku, BASE 27545ba)
- Task 1: implementer DONE 0fde3ca (611 passed + 1 xfailed); review dispatched (sonnet), package review-27545ba..0fde3ca.diff
- Task 1: review — spec ✅; Important (plan-mandated): pair_list sort order (-shared, i, j) untested (fixture has one pair); Minor: docstring omits pair_list; Minor: report shows bare `pytest` commands.
- Ruling: add an ordering test with >= 2 pairs of different shared area, and update the docstring in the same fix round — the sort is a stated part of the interface the plan gives; the docstring is one line in the function being edited — costs one small test if wrong.
- Ruling: subagent commits may carry their own model's Co-Authored-By line (0fde3ca says Claude Haiku 4.5) instead of the plan's "Claude Opus 5.5" — the plan wrote the controller's trailer; naming the model that made the commit is the truthful attribution — costs a trailer mismatch in history if the owner wanted one line everywhere.
- Task 1: minor (deferred): TDD evidence in task-1-report.md shows bare `pytest`, not `.venv/Scripts/python.exe -m pytest` (counts match the baseline, so the right interpreter is likely).
- Task 1: fix round 1/5 (2 addressed, 0 open; commits 0fde3ca..5b6ebb2)
- Task 1: complete (commits 27545ba..5b6ebb2, review clean)
- Task 2: dispatched (implementer haiku, BASE 5b6ebb2)
- Task 2: implementer DONE b24da59 (7 passed; engine 619 + 1 xfailed); review dispatched (sonnet)
- Task 2: review — spec ✅, Approved; ⚠️ fixture at file end: checked, two_sided_wall is the last def (2304-2314 of 2314).
- Task 2: minor (deferred): `find_errors(mesh, profile=FixProfile())` mutable default (plan-mandated; same pattern as fix_object).
- Task 2: minor (deferred): cracks spots all carry value 0.0, so "worst first" is vertex order for that kind (plan-mandated).
- Task 2: minor (deferred): task-2-report.md states wrong line counts for the new files (cosmetic).
- Task 2: complete (commits 5b6ebb2..b24da59, review clean)
- Task 3: dispatched (implementer sonnet, BASE b24da59)
- Task 3: implementer stalled (stream watchdog, waiting on a background suite); uncommitted work intact (overlap.py, test_overlap.py, profile script); resumed 09:50 to finish in the foreground
- Task 3: implementer DONE_WITH_CONCERNS 9dd065c — slice 342.4 s -> 19.5 s (17.6x), pairs 6376 = 6376, px 33934 -> 33918; exact px-equality fails on back_to_back_pair (153027 vs 153028) and split_double_layer (102019 vs 102022): rays grazing exactly a partner's edge (reference = Embree float32 + coincident tol; new = barycentric eps 1e-6); two_sided_wall exact. Suite 621 passed / 2 failed / 1 xfailed; a monolithic suite run took 4,085 s vs ~400 s chunked (machine contention).
- Ruling: the pixel-equality tests allow |new - reference| <= max(5 px, 0.01% of the reference) for back_to_back_pair and split_double_layer and stay EXACT for two_sided_wall — both methods approximate rays that graze a partner's edge, the pair set is identical, and a logic error would move counts far more than 0.01% — costs, if wrong, a few edge pixels of flicker count vs the old method (16 of 33,934 on the real slice), which changes no ranking the viewer shows.
- Task 3: ruling applied b2540b8 (overlap 23 passed, errors 7 passed); review dispatched (sonnet) over b24da59..b2540b8
- Task 3: review — spec ✅, Approved (CSR expansion checked over 200 random trials; ray parametrization matches buf.depth; outputs unchanged; no dead code).
- Task 3: minor (deferred): overlap.py:528 dense CSR `starts` line has no arithmetic comment (plan-mandated code).
- Task 3: minor (deferred): overlap.py:521 redundant `.astype(np.int64)` on buf.tri.
- Task 3: note: profile_double_layers.py was added per the plan's Order section (outside the task brief's file list), not scope creep.
- Task 3: complete (commits b24da59..b2540b8, review clean)
- Task 4: dispatched (implementer haiku, BASE b2540b8)
- Task 4: implementer DONE c9460ed (CLI tests 60 passed); CHTM5 raw: hidden 12,870, flicker_diff 5,668, flicker_same 4,793, cracks 3,884 faces/points; find_errors wall 40.8 s; review dispatched (sonnet)
- Task 4: review — spec ✅, Approved; ⚠️ commit body checked (counts + 40.8 s recorded); imports fine (60 CLI tests pass).
- Ruling: find_errors' cracks 3,884 on the raw export vs the plan's "near 2,241" is the plan's error, not a defect — 2,241 is the fix report's merge-stage T-vertex count, measured after 13,072 hidden faces were already removed; hidden 12,870 (raw) vs 13,290 (solidified reference) differs for the same kind of reason — costs, if wrong, a crack count that disagrees with some other measure the owner reads.
- Task 4: minor (deferred): cli.py dispatch mixes a bare `if` (fix) with `if/elif` (preview-data, errors); `snapshot` vs `snapshot_dir` arg name (plan-mandated); `profile or FixProfile()` truthiness (plan-mandated); Path-coercion style.
- Task 4: complete (commits b2540b8..c9460ed, review clean)
- Ruling: plan amended (owner saw an empty CHTM 5 panel: the meshbuf takes 12.5 s per request, no loading sign) — new Task 12 caches the packed meshbuf per version (data/meshbuf/version-<id>.bin), and Task 10 gains a per-panel loading message; order now 1-6, 12, 8, 7, 9, 10, 11 — the owner was told these two fixes join the build — costs two small tasks.
- Task 5: dispatched (implementer haiku, BASE c9460ed)
- Task 5: implementer DONE 4a998da (3/3; API suite 47/47); review dispatched (sonnet)
- Ruling: plan amended — Task 13 real textures in the viewer (owner: "where's the texture"; approved), Task 14 facade layer in find_errors + the filter (owner asked to highlight the outward-facing facade; approved); order now 1-6, 12, 14, 8, 7, 9, 10, 13, 11 — costs two tasks.
- Plan committed f4fac78 + 1d945d2 (Task 13, Task 14 with Task 8/10 facade amendments, spec Amendments section, Global Constraints facade row). task-14-brief.md extracted; its expected values checked on the worktree (facade_probe.py): cube facade = 0..11; box_with_partition facade = 0..11, hidden = [12, 13].
- Pre-flight rows for the amendments: 14 ↔ 8 `layers.facade` / `layer_counts.facade` / `spots.facade` = TS `ErrorsFile.layers` / `layer_counts` / `spots` — consistent; 8 ↔ 10 `countOf` defined in 8, used by 10's legend — consistent; 13 ↔ 9/10 Viewport `loadModel(data, versionId?)` — Task 13 runs after 9 and 10 and amends their files — consistent by order.
- Task 5: review — spec ✅, Approved; all four named risks (route collision, atomic write, path safety, import cycle) checked clean against the source.
- Task 5: minor (deferred): GET /errors for a version id that does not exist says "not computed yet" (404) rather than "Version not found" (plan-mandated code; the spec's "unknown version is refused" still holds: 404).
- Task 5: minor (deferred): write_errors' tmp name is fixed (version-<id>.json.tmp); two concurrent POSTs for one version could interleave the tmp file (no torn read of the final file).
- Task 5: complete (commits c9460ed..4a998da, review clean)
- Task 6: dispatched (implementer haiku, BASE 4a998da)
- Task 6: implementer DONE e661224 (test_errors 4/4, test_versions 6/6); full API suite deferred to Task 11 (17.5 min, CPU shared with the errors-page build)
- Ruling: the 3D filter pauses after Task 6's review; the owner asked where the Errors & fixes page is (spec efad19a, never planned) — it goes first, plan docs/superpowers/plans/2026-09-26-errors-and-fixes-page.md — costs the 3D filter a few hours
- Task 6: review dispatched (sonnet), package review-4a998da..e661224.diff
- Task 6: review — spec ✅, Approved (block on the success path after the owner-copy block; variables in scope; failure cannot change the response; test targets a fresh version id).
- Task 6: Important (parked, plan-mandated): find_errors on the AFTER mesh runs synchronously before the response; on a large building it adds an exposure pass + a 26-view double-layer pass inside nginx's 600 s. Ruling: measure it on CHTM 5th floor in Task 11 (a dashboard fix run is only done if the owner asks); if it adds more than 60 s, move it to a background thread — costs one small follow-up task if it proves slow.
- Task 6: minor (deferred): log text "errors file for fixed version %s" dropped the brief's "failed" (logger.exception already logs at error level).
- Task 6: complete (commits 4a998da..e661224, review clean)
- PAUSED after Task 6 for the Errors page (owner 11:45). Resume at Task 12.
- Finding (controller, 12:40, while measuring for the Errors page): find_errors' "open_edges" counts every edge used by one face, which includes T-junction sub-edges (covered on the other side by a longer edge). CHTM 5th floor: 3,074 "open" = 346 truly open (edge class 2) + 2,678 T-junction (class 4) + a few degenerate; A shipped 427 vs 378 class-2. Ruling for resumption: the 3D filter's green "Open edges" layer must show edge class 2 only (T-junction edges are already the cyan crack points), else the owner sees thousands of false holes — costs a small change in find_errors + its test when the filter resumes.
- Finding: vue-tsc -b fails on feat-dashboard with 3 pre-existing errors in web/src/three/Viewport.ts (332, 333, 360); Task 9 (Viewport draw) should fix them in passing since it edits that file.
- RESUMED 13:15 (Errors page live). Task 12: dispatched (implementer haiku, BASE e661224).
- Ruling: plan amended — Task 15 (open edges = edge class 2; t_junction_strip 10 -> 7 measured, CHTM 5th floor expected ~346 instead of 3,074) runs after Task 14 (same file); Task 9 gains Step 0 fixing the 3 pre-existing vue-tsc errors in Viewport.ts (cast like setXRay; faceIndex != null) so its type gate can pass; order now 1-6, 12, 14, 15, 8, 7, 9, 10, 13, 11 — costs one small task.
- Task 12: implementer DONE 91cde5a (test_versions 7 passed); review dispatched (sonnet)
- Task 14: dispatched (implementer haiku, BASE 91cde5a) while Task 12's review runs (disjoint files: engine/detectors vs api/)
- Task 14: implementer DONE 0e15aee (errors + CLI 69 passed); review dispatched (sonnet)
- Task 12: review — spec ✅ (verbatim; header parse checked against meshbuf.py), Needs fixes. Critical: the fixed version-<id>.bin.tmp name lets two concurrent first requests interleave writes and replace a corrupt buffer into the cache, trusted forever. Important: no format guard on cached files (a future meshbuf VERSION bump would keep serving old bytes); the importer's flat_materials backfill is an undocumented exception to version immutability (converges today). Minors: tmp debris on failure; the test checks only x-tris-count.
- Ruling: fix the Critical (mkstemp + os.replace + cleanup), add the MAGIC/VERSION guard (rebuild on mismatch) with a test, document the backfill dependency in a comment, assert content-type in the test — the cache is trusted forever, so a corrupt or stale file would never heal — costs one small fix round.
- Task 12: fix round 1/5 dispatched (resumed implementer, haiku)
- Task 14: review — spec ✅, Approved (hidden provably unchanged vs 91cde5a; facade = EXP_OUTSIDE & ok; ints for JSON; slit faces in neither list by construction; old errors files tolerated by the web accessors). Minors (deferred): the report's diff stat and line numbers are off by one or two.
- Task 14: complete (commits 91cde5a..0e15aee, review clean)
- Task 15: dispatched (implementer haiku, BASE 0e15aee) while Task 12's fix round runs (disjoint files)
- Controller slip (13:40): the task-brief script ran with the shell still in the errors-page worktree and wrote task-15-brief.md into that worktree's .superpowers; removing that folder with rm -r also deleted the worktree's TRACKED ledger copies (never committed as deletions) — restored at once with git checkout -- .superpowers; brief copied to the main workspace. Rule kept: absolute paths and git -C only, never cd.
