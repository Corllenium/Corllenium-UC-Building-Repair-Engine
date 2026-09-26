# Final-review fix round: 3D error filter (feat/error-filter)

The one fix dispatch after the final whole-branch review. The full review is in
`final-review-report.md` in this folder: read the I1-I4 sections and M1, M2, M3, M5, M6 and M8
there first. They hold the file:line, the measurements and the fixes proposed.

- **Worktree:** `D:\PROJECTS\UC MODEL FIXER\.claude\worktrees\error-filter`, branch `feat/error-filter`, HEAD `ae905ac`.
- **Report file:** `D:\PROJECTS\UC MODEL FIXER\.superpowers\sdd\2026-09-26-3d-error-filter\final-fix-report.md`.

## Fix these

### I1: toggles walk both errors files (`web/src/views/WorkspaceView.vue`, about lines 545-546 and 608-613)
- Make `errorsBefore` and `errorsAfter` `shallowRef<ErrorsFile | null>(null)`. The files are never
  mutated; check this, and replace any in-place mutation with a new object.
- Remove `{ deep: true }` from the watcher over `[errorFilter, errorsBefore, errorsAfter]`.
  `errorFilter` is `reactive`, and Vue 3.5 still traverses a reactive source in an array. Check that a
  kind toggle, Isolate and Blink still redraw.

### I2: depth bias as a fixed NDC offset (`web/src/three/Viewport.ts`, about line 490)
- Replace `gl_Position.z -= 0.0005 * gl_Position.w;` with a view-space pull toward the eye, after
  `#include <project_vertex>`:
  `gl_Position = projectionMatrix * vec4(mvPosition.xyz * 0.998, 1.0);`
  This keeps the pixel and moves only the depth (0.2 % of the distance).
- First confirm the viewport's camera is a `PerspectiveCamera`. With an orthographic camera, scaling
  toward the eye would move the pixel.
- Keep it for both the points (cracks) and the lines (open edges).
- Rewrite the comment above it so it states what the code now does.

### I3: in Isolate or X-ray, a click picks the ghost wall (`Viewport.ts`, about lines 460-478 and 534-552)
- In `setErrorOverlay`, keep the overlay's face-id list (`this.overlayFaceIds`). Clear it in `clear()`
  and whenever the overlay is removed.
- In the click handler: when isolate or X-ray is on and the overlay mesh exists, raycast the overlay
  first. On a hit, report `overlayFaceIds[hit.faceIndex]` as the face. Otherwise use today's path,
  surface plus `faceOrder`.
- Check the overlay material's `side`. The raycaster skips back-facing triangles on a FrontSide
  material, and most interior flicker faces face away from some view. Make the pick work from both
  sides without changing how the overlay looks.
- Put the choose-the-face logic in a small pure function, for example in `web/src/utils/errorLayers.ts`
  or next to it. Test it with vitest (overlay hit wins in isolate/X-ray; surface otherwise; overlay miss
  falls back).

### I4: "Zero-area and stray bits" holds only zero-area faces (`engine/detectors/errors.py:61`)
- **Ruling:** follow the spec's owner decision and add the stray-fragment and sliver candidates. Do not
  relabel.
- In `find_errors`:
  - `ok_ids = np.nonzero(ok)[0]`.
  - `fr = detect_fragments(positions_c, faces[ok_ids], profile, contact_tol=1.5 * float(topo.quanta.max()), max_width=sliver_width_bound(topo.quanta, profile))`.
    These are the same tolerances `engine/fixes/pipeline.py` about line 747 passes. There is no
    `protected` argument: nothing is invented here.
  - `loose` = the zero-area faces (`~ok`) ∪ `ok_ids[fr.fragments | fr.slivers]`, sorted, no duplicates.
  - Add `"loose_parts": {"zero_area": n, "fragments": n, "slivers": n}` to the returned dict.
  - Say in the module docstring that fragments and slivers are candidates: the pipeline also passes
    them through `fragment_feedback` before removing any.
- **Test** (`engine/tests/test_errors.py`): a fixture with a one-face stray piece puts it in `loose`,
  and a zero-area face stays in `loose`. Reuse a fixture from `engine/tests/fixtures/build.py` or
  `engine/tests/test_fragments.py` if one fits; otherwise append a new fixture at the END of `build.py`.
- **Measure on CHTM 5th floor**, before and after the change, and report both:
  `python -m engine.cli errors "D:/PROJECTS/UC MODEL FIXER/data/snapshots/c0c877002500-b7c2dc01" --out "D:/PROJECTS/UC MODEL FIXER/data/errors_check/chtm5-<before|after>.json"`
  - Report the wall time, `counts.loose` and `loose_parts`.
  - Before the change, `loose` was 1,055.
  - Write only into `data/errors_check/`. Never write into `data/errors/`: the live dashboard serves
    that folder.
  - Commit the change whatever the time, and report the time.

### M2: stale errors files are served forever
- Export a constant `ERRORS_VERSION = 2` from `engine/detectors/errors.py` and write it as the file's
  `"version"`. The meaning changed in I4 and in Tasks 14 and 15.
- `GET /api/versions/{id}/errors` (`api/routers/errors.py`): a file whose `version` differs from
  `ERRORS_VERSION`, or has none, answers 404 "not computed yet". The panel then offers Find errors again.
- Test: a stale file (version 1) → 404; a current one → 200.

### M1: a failed errors fetch stops the workspace load (`WorkspaceView.vue`, about lines 683, 695 and 722)
- Wrap both `fetchErrors` calls so a failure shows in the existing banner and returns `null`. The
  BEFORE and AFTER models must still load.

### M3 (guard only)
- In `applyErrors`, refuse a file whose `n_faces` differs from the loaded meshbuf's `header.counts.faces`.
  Show one banner line ("errors file does not match this model; press Find errors") and draw nothing
  from it. Do NOT change the cache file names.

### M5: `pair_list` in every fix report
- `engine/cli.py::_build_report` (about line 230; the API's fix route uses the same function): write
  `double_layers` without `pair_list`.
- `find_errors` still uses `double_layers(...)["pair_list"]` from the function's return value. Leave that
  alone.
- Test: a fix report has `double_layers.count` and no `pair_list`.

### M6: tests for stated requirements
- Task 6 isolation: make `find_errors` raise inside the fix route (monkeypatch). The run still
  completes, and GET of the AFTER version's errors answers 404.
- The AFTER-file test (`api/tests/test_errors.py:30-36`) asserts that `n_faces` equals the AFTER
  version's `tri_count`.
- The read-only Global Constraint: copy `positions`, `face_v` and `face_material` before `find_errors`
  and assert they are equal after it.

### M8: texture details (`Viewport.ts`, about lines 242-259)
- `loader.load(url, onLoad, undefined, onError)`: on error, drop the map, set the material's colour to
  the same grey fallback the untextured path uses, and set `needsUpdate`.
- The "no material" fallback gets the same `polygonOffset` and `roughness` options as the others.
- Share one `Texture` per URL within a model load (a `Map<string, Texture>`). Dispose each texture
  once in `clear()`.

## Do not do

- M4, M7, M9, M10, M11: parked by the controller.
- Anything else the report lists.
- Refactors beyond these items.

## Rules

- Read-only on everything outside the worktree, except `data/errors_check/`. Never write to `data/errors/`,
  `data/meshbuf/`, the database, `docker-compose.yml`, the Docker files, or
  `D:\PROJECTS\UC ENVIRONMENT BUILDING\...`. Start no servers, containers or browsers: the controller
  checks the browser.
- Python is `D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe`. Run it FROM THE WORKTREE ROOT in a
  subshell with PYTHONPATH pinned:
  `(cd "D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest <tests> -q -p no:cacheprovider)`.
  `python -m` puts the cwd first on `sys.path`, and the editable install points at the main checkout.
- **Gates**, all in the worktree:
  - `engine/tests/test_errors.py engine/tests/test_fragments.py engine/tests/test_cli.py`;
  - `api/tests/test_errors.py` plus the fix-route tests you touch;
  - `pnpm --dir web exec vitest run` (all);
  - `pnpm --dir web exec vue-tsc --noEmit -p tsconfig.json` (exit 0);
  - `pnpm --dir web run build`.
- TDD: write each test first and watch it fail for the right reason.
- Commits: stage files by name, never `git add -A`. One commit per item or per small group. Every message
  ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never commit `web/tsconfig.tsbuildinfo`.
- No subagents.
- **Report:** in the report file, per item, list what changed, the test that proves it, and the commit.
  Also give the CHTM before/after measurements and the gate outputs (counts). Return only the status
  (DONE / DONE_WITH_CONCERNS / BLOCKED), the commit list, a one-line gate summary and any concerns.
