# Final-review fix round: report (feat/error-filter)

Implementer: Claude Opus 5.5, 2026-09-26. Brief: `final-fix-brief.md`; findings: `final-review-report.md`.

- **Worktree:** `D:\PROJECTS\UC MODEL FIXER\.claude\worktrees\error-filter`, branch `feat/error-filter`.
- **Base:** `ae905ac`. **Head:** `41cabf8`. 9 commits, 16 files, +686 / -64.
- **Status: DONE_WITH_CONCERNS.** Every item is implemented, tested and committed. The engine and
  web gates pass. The **API gate did not run**: the test Postgres (`fixer-db`, 127.0.0.1:5490)
  exited (code 255) when the machine restarted at about 22:32 and was still down at the end. The
  rules forbid starting containers. See Concerns.
- Nothing was written to `data/errors/`, `data/meshbuf/`, the database, `docker-compose.yml`, the
  Docker files or `UC ENVIRONMENT BUILDING`. The only data written is `data/errors_check/chtm5-before.json`
  and `chtm5-after.json`. No server, container or browser was started. No subagents were used.
  `web/tsconfig.tsbuildinfo` stays untracked.

## Commits

| Commit | Item |
|---|---|
| `6eba359` | I1: the errors files are shallowRefs; the watcher is not deep |
| `7470f78` | I2: crack dots and open edges are pulled 0.2 % toward the eye in view space |
| `7b1aa69` | I3: Isolate/X-ray picks the overlay face first (`chooseFace`) |
| `6614f19` | I4: `loose` also holds the stray-fragment and sliver candidates; `loose_parts` |
| `586120f` | M2: `ERRORS_VERSION = 2`; GET answers 404 for a stale or unversioned file |
| `f2efaf4` | M5: no `pair_list` in fix reports |
| `f67288e` | M6: isolation, AFTER `n_faces` = `tri_count`, `find_errors` read-only |
| `89dd4f5` | M1 + M3: a failed fetch reaches the banner as null; a file of another size is refused |
| `41cabf8` | M8: grey on texture error, fallback options, one texture per URL, disposed once |

Every message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Files were staged
by name. The repo stores CRLF in its blobs, and the new files were committed the same way: there is
no line-ending churn.

## Items

### I1: toggles walked both errors files (`6eba359`)
- **Changed:**
  - New `web/src/composables/useErrorFiles.ts` holds `errorFilter` (reactive), `errorsBefore` and
    `errorsAfter` (both `shallowRef<ErrorsFile | null>(null)`), and one watcher,
    `watch([errorFilter, errorsBefore, errorsAfter], redraw)`, with no `deep`.
  - `WorkspaceView.vue` uses it; the watcher body is now `redrawErrors()`, unchanged.
- **No in-place mutation, checked by grep:**
  - WorkspaceView only assigns whole files (`reloadModel`, `onFindErrors`) or reads them.
  - ErrorsPanel only reads `before` and `after`. Its `v-model`s are on the filter.
  - In errorLayers, `.push` goes into the partner-index cache and `.sort` runs on a new array.
  - So nothing needed replacing.
- **Tests** (`useErrorFiles.test.ts`, 4):
  - a kind, Isolate and Blink toggle each redraw once;
  - a file arriving, being replaced or being dropped redraws;
  - a file is kept as it came (`toBe`, `isProxy` false);
  - a filter toggle reads **0** values of either file. A counting Proxy saw **98** reads per toggle
    on the tiny fixture before the fix.
- **RED:** the proxy and read-count tests failed. **GREEN** after the fix.

### I2: depth bias (`7470f78`)
- **Camera confirmed perspective.** `Viewport.ts:58`, `new THREE.PerspectiveCamera(42, 1, 0.1, 1e6)`,
  is the only camera. Nothing assigns another. There is no `logarithmicDepthBuffer`. In three r170,
  `project_vertex` declares the view-space `vec4 mvPosition` and then sets
  `gl_Position = projectionMatrix * mvPosition`.
- **Changed:** `DEPTH_BIAS_GLSL` is now a module export. Its value is
  `'#include <project_vertex>\n  gl_Position = projectionMatrix * vec4(mvPosition.xyz * 0.998, 1.0);'`.
  - Both `setErrorLines` and `setErrorPoints` use it.
  - The comment above it now says what the code does: same pixel, depth 0.2 % of the distance
    nearer, 6.5 in at CHTM's overview, 0.19 in at the 96 in fly-to.
- **Tests** (`depthBias.test.ts`, 4). They emulate the bias line on the CPU with three's own
  matrices, with the camera set up exactly as `loadModel` does for CHTM's 2,237 in diagonal:
  - the pixel is unchanged and the depth is nearer;
  - it still beats its own surface by more than 4 steps of a 24-bit depth buffer, at the overview
    and at 96 in;
  - a wall **12 in** in front at the overview hides it;
  - a wall **1 in** in front at 96 in hides it.
- **RED with the old line:** both wall tests failed.
  - At the overview the dot's depth was 0.998860 against the wall's 0.999358.
  - At 96 in it was 0.976247 against 0.976502.
  - The review's figure for the old reach is 1,363 in (114 ft) at the overview.
- **Not verified here:** that the GLSL compiles, and how it looks. I may not start a browser, and no
  offline GLSL validator is installed. The browser re-check at the worst crack spot (as in 997e71d)
  is the controller's. On reading the code: three resolves the include after `onBeforeCompile`, so
  `mvPosition` and `projectionMatrix` are in scope for the added line.

### I3: picking in Isolate / X-ray (`7b1aa69`)
- **Changed:**
  - The Viewport keeps `overlayFaceIds`, the face drawn in each overlay slot.
    - It is set when `setErrorOverlay` builds the overlay mesh.
    - It is cleared at the start of every `setErrorOverlay` call (each rebuild or removal) and in
      `clear()`.
  - The click handler works out `ghosted = isolate || xray`. When ghosted, it raycasts
    `parts.errors` first, then calls the pure `chooseFace(ghosted, overlayHit, overlayFaceIds,
    surfaceHit, faceOrder-when-textured)`.
  - `chooseFace` lives in `web/src/utils/errorLayers.ts`. A ghosted overlay hit wins and reports
    `overlayFaceIds[slot]`. Otherwise it takes the surface hit through `faceOrder`, as before.
- **Overlay `side`:** it was already `DoubleSide`, and only `surfaceMaterials()` ever change `side`.
  So the raycaster already meets overlay faces from behind. The material moved, unchanged, into
  `errorOverlayMaterial()`; its look is the same.
- **Tests:**
  - `errorLayers.test.ts`, `chooseFace` (4):
    - an overlay hit wins in Isolate/X-ray (face 42, not the wall);
    - with the surface opaque, the surface is picked, through `faceOrder`;
    - an overlay miss falls back to the surface;
    - missing everything gives null.
    - RED: 4 failed (`chooseFace is not a function`).
  - `overlayPick.test.ts` (2):
    - a real three.js `Raycaster` meets an overlay triangle from the front and from behind;
    - the material keeps its look (vertexColors, DoubleSide, polygonOffset -1/-1).
    - These pin behaviour that already held. Their RED was only the missing factory.
- **Not verified here:** the click itself in a browser.

### I4: "Zero-area and stray bits" (`6614f19`)
- **Changed** (`engine/detectors/errors.py`), per the ruling (no relabel):
  - `ok_ids = np.nonzero(ok)[0]`.
  - `fr = detect_fragments(positions_c, faces[ok_ids], profile, contact_tol=1.5 * float(topo.quanta.max()), max_width=sliver_width_bound(topo.quanta, profile))`.
    No `protected` argument.
  - `loose = np.union1d(zero_area, ok_ids[fr.fragments | fr.slivers])`, which is sorted and has no
    duplicates.
  - The file gains `"loose_parts": {"zero_area", "fragments", "slivers"}`.
  - The module docstring says fragments and slivers are candidates: the pipeline also passes each
    through `fragment_feedback` (and the rays) before removing any.
- **Fixture:** `t_junction_strip_with_a_stray()`, appended at the END of `engine/tests/fixtures/build.py`.
  Face 6 is the zero-area stitch and face 7 a detached 2 sq in stray.
- **Tests** (`engine/tests/test_errors.py`):
  - `test_a_one_face_stray_is_loose_and_a_zero_area_face_stays_loose`: loose is `[6, 7]`,
    counts.loose is 2, parts are 1/1/0.
  - `test_an_attached_needle_is_loose_as_a_sliver_and_a_big_detached_quad_is_not`: the printed
    `slab_with_strays` gives `[32, 33]` with parts 0/1/1, and the 20 sq in quad stays out.
  - RED: `[6] != [6, 7]` and `[] != [32, 33]`. GREEN after.

### M2: schema version (`586120f`)
- **Changed:**
  - `ERRORS_VERSION = 2` is exported from `engine/detectors/errors.py` and written as `"version"`.
  - `GET /api/versions/{id}/errors` answers 404 "not computed yet" when the file is missing, when
    its version differs or is absent, or when it is not a JSON object.
- **Tests:**
  - Engine: `test_the_file_carries_the_current_schema_version`. RED was an ImportError; it is GREEN.
  - API: `test_a_stale_or_unversioned_errors_file_reads_as_not_computed_yet` covers version 1 (404),
    no version (404) and the current version (200). **Not run: the database was down.**
  - Instead I called the route directly on the same three files, with a scratch script using
    `Settings(data_dir=<scratchpad>)` (the route never touches the DB).
    - Before the change: 200 / 200 / 200.
    - After: 404 / 404 / 200.

### M5: `pair_list` in fix reports (`f2efaf4`)
- **Changed:** `engine/cli.py::_build_report` writes `double_layers` without `pair_list`. It is
  None-safe, because `FixResult.double_layers` may be None. `find_errors` still takes the list from
  `double_layers()`'s own return value, untouched. Nothing in `api/` or `web/src` reads it from a
  report.
- **Test:** `test_cmd_fix_reports_the_double_layers_that_can_still_flicker` now requires exactly
  `{count, area, px, planes}`. RED: extra item `'pair_list'`. GREEN after.

### M6: tests for stated requirements (`f67288e`)
- **Engine:** `test_finding_errors_changes_nothing_in_the_mesh`, over `two_sided_wall`,
  `box_with_partition` and `t_junction_strip_with_a_stray`. It copies `positions`, `face_v` and
  `face_material`, runs `find_errors`, and asserts they are equal after.
  - It passes on the real code.
  - **Mutation check:** I planted an in-place re-winding (`mesh.face_v[:, [1, 2]] = mesh.face_v[:, [2, 1]]`)
    in `find_errors`. All 3 cases failed. Then I removed it; `git diff --quiet` confirmed the file
    was identical to HEAD.
- **API:**
  - `test_a_fix_run_writes_its_after_errors_file` now asserts `n_faces ==` the AFTER version's
    `tri_count` (from `GET /api/versions/{id}`).
  - New `test_a_fix_run_completes_when_its_after_errors_file_fails`: `versions.find_errors` is
    monkeypatched to raise. The run must still be `completed`, and GET of the AFTER version's
    errors must answer 404.
  - **Neither has run: the database was down.**
- **Limit, measured:** `fix_object` leaves the test cube at 12 faces before, after and in the
  reference. So on this fixture, `n_faces == tri_count` cannot tell which mesh the AFTER file was
  computed from. It pins the numbering contract that the M3 guard relies on.

### M1 + M3 (`89dd4f5`)
- **M1:** `errorsOrNull(fetching, label, report)` in `useErrorFiles.ts`. Both `fetchErrors` calls in
  `reloadModel` go through it. A rejection becomes one banner line,
  "Loading errors failed for BEFORE|AFTER: <message>", and reads as null. So the BEFORE block no
  longer throws, and the AFTER model, the run and the layers still load. A 404 was already null.
- **M3:** `fitToModel(file, modelFaces, report)` in the composable, and a new `Viewport.faceCount()`
  (the meshbuf's `header.counts.faces`, or null before any model).
  - `applyErrors` starts with `file = fitToModel(file, view.faceCount(), pushBanner)`.
  - On a mismatch nothing is drawn from the file.
  - The file is dropped from its own panel only, so that panel's "Find errors" button comes back.
  - The banner gets exactly one line, verbatim: "errors file does not match this model; press Find errors".
  - Cache file names are unchanged.
- **Tests** (`useErrorFiles.test.ts`, 4):
  - a rejected fetch reads as null with one banner line;
  - a file, or a 404, passes through with no banner;
  - a mismatched file is dropped from its panel only, with one banner line;
  - a fitting file, and any file while no model is loaded, passes.
  - RED: 4 failed (functions missing). GREEN after.
- **Not covered:** the calls inside `WorkspaceView.vue` itself. This repo's vitest has no DOM
  environment, so the view is never mounted in a test.

### M8: textures (`41cabf8`)
- **Changed** (`Viewport.ts`):
  - `texturedSurfaceMaterials(materials, versionId, load)` builds the textured facade's materials.
  - There is one `Texture` per URL, in a `Map<string, Texture>` that the viewport keeps for the
    load.
  - `loader.load(url, undefined, undefined, onError)`: on error, every material using that texture
    drops its map, takes the untextured path's own grey (`0.8 + (i % 5) * 0.04`) and gets
    `needsUpdate`.
  - The no-material fallback gets the same options as the others (DoubleSide, roughness 0.9,
    metalness 0, polygonOffset 1/1), with colour `0xcccccc`.
  - `clear()` goes through `disposeObjects(objects, textures)`, which disposes every texture exactly
    once, then resets the Map.
- **Tests** (`surfaceMaterials.test.ts`, 4). The stand-in loader fires its errors later, as the real
  loader does:
  - one load per file, and the Texture is shared;
  - a failed file turns both of its materials grey and leaves the others alone;
  - every material, the fallback included, has the same options;
  - a shared texture is disposed once.
  - RED: 4 failed (exports missing). GREEN after.

## CHTM 5th floor measurements (I4)

- **Snapshot:** `data/snapshots/c0c877002500-b7c2dc01/chtm_5ft_floor.obj`, sha256 `c0c877002500e14c…518de9f10`,
  20,599 faces. It was hashed before and after, and was unchanged.
- **Command:** `python -m engine.cli errors <snapshot> --out data/errors_check/chtm5-<before|after>.json`,
  run from the worktree root with PYTHONPATH pinned.

| | Before (`ae905ac`) | After (`6614f19`) |
|---|---|---|
| CLI wall time, idle machine | **47.7 s** | **50.8 s** |
| `counts.loose` | **1,055** | **1,055** |
| `loose_parts` | (absent) | `zero_area` 1,055, `fragments` 0, `slivers` 0 |

- The two files are identical in every other key.
- **`detect_fragments` alone** (in-process, `time.perf_counter` around just that call, with the same
  arguments as `find_errors`): **8.44 s, 8.99 s, 8.94 s** over 3 runs. `analyse_topology` before it
  took 13.8 s.
  - Its report: the model is 1 component (18 by shared edges, 17 joins through T-junctions, 0
    through coplanar contact).
  - It has 29 thin faces, and all 29 are sandwiched, so none is a sliver.
  - `contact_tol` = `max_width` = 0.15 in.
- **Controlled comparison:** the old `find_errors` (from `ae905ac`, loaded from a copy) and the new
  one, run alternately in one process on an idle machine.
  - Before: 57.1 s and 51.3 s.
  - After: 61.2 s and 62.1 s.
  - Mean difference: about **+7.5 s (+14 %)**, consistent with `detect_fragments`' own time.
  - The single CLI runs above differ by only 3.1 s, which is inside their run-to-run noise.
- **Machine load:**
  - My first BEFORE run took **666.3 s**. A headless Edge GPU process (`--use-angle=swiftshader`,
    started 15:56, profile `scratchpad\edge-prof2` in this session's scratchpad) was then using
    about 15.4 of the 16 logical CPUs. I did not touch it.
  - The machine restarted at about 22:32, and was idle from then on (the top process was under
    0.3 cores).
  - All the numbers in the table, and the in-process ones, were taken after that restart. I ran
    nothing else heavy during the timings.

## Gates (run at `41cabf8`)

| Gate | Result |
|---|---|
| `engine/tests/test_errors.py engine/tests/test_fragments.py engine/tests/test_cli.py` | **119 passed** in 72.3 s, exit 0 (16 + 43 + 60) |
| `api/tests/test_errors.py` (6 tests) and the fix-route tests in it | **NOT RUN**: test Postgres down (see Concerns) |
| `pnpm --dir web exec vitest run` | **16 files, 107 tests passed**, exit 0 (baseline at `ae905ac`: 12 files, 85 tests) |
| `pnpm --dir web exec vue-tsc --noEmit -p tsconfig.json` | **exit 0** |
| `pnpm --dir web run build` | **exit 0**. One warning: the main chunk is 666.66 kB (over 500 kB). I did not measure the baseline size. |

`git status` after the gates shows only `?? web/tsconfig.tsbuildinfo`.

## Structure added so the items could be tested

These are small, and each serves its own item:
- the composable `useErrorFiles` (I1, M1, M3);
- `DEPTH_BIAS_GLSL`, now a module export (I2);
- `errorOverlayMaterial()` and `chooseFace()` (I3);
- `Viewport.faceCount()` (M3);
- `texturedSurfaceMaterials()`, `disposeObjects()` and a `SURFACE_OPTIONS` constant (M8).

`web/src/utils/materialGroups.ts` is unchanged. No parked item (M4, M7, M9, M10, M11) was touched.

## Concerns

1. **API gate not run.** `fixer-db`, `fixer-api` and `fixer-web` exited (255) at the ~22:32 machine
   restart, and 127.0.0.1:5490 was still closed at the end. The rules forbid starting containers.
   - Four API tests of this round have never run: M2's stale-file test, M6's `tri_count` assertion
     and M6's isolation test. The other three existing tests in `api/tests/test_errors.py` were not
     re-run either.
   - M2's route logic was checked directly (see M2).
   - By reading: the POST and the AFTER file both write version 2, so the existing serve test should
     still match. Unverified.
   - Please run: `api/tests/test_errors.py` once `fixer-db` is up. For M6, also a mutation check:
     remove the `try/except` around the AFTER `write_errors` in `api/routers/versions.py` and watch
     the isolation test fail.
2. **I2 and I3 are unverified in a browser.** This covers the GLSL compiling, the dots and edges
   being hidden by walls at the overview, and a real click in Isolate or X-ray. The logic is
   unit-tested; the browser is the controller's.
3. **M1 and M3 wiring in `WorkspaceView.vue` is not covered by any test** (there is no DOM test
   environment). The helpers they call are.
4. **The M6 `tri_count` test is weak on the cube.** Before and after both have 12 faces, measured,
   so it cannot catch an AFTER file computed from the wrong mesh.
5. **CHTM exercises none of I4's new part** (0 fragments, 0 slivers). Its `loose` stays 1,055, and
   the new part is proven only by the fixtures. The cost is about +7.5 s per `find_errors` on CHTM.
