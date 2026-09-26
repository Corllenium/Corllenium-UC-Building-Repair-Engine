# Final whole-branch review: feat/error-filter (277a722..ae905ac)

Reviewer: Claude Opus 5.5, 2026-09-26. Scope: 23 commits, 26 files (the 3D error filter, Tasks 1-10 and 12-15;
Task 11 skipped). This review is also Task 13's gate.

Reviewed in three passes: engine, then API, then web. Each pass was checked against the spec
(`docs/superpowers/specs/2026-09-26-3d-error-filter-design.md`), the plan on feat-dashboard (2,137 lines,
including the Task 10 amendments) and the plan's Global Constraints. Wider context came from the HEAD
checkout at `.claude/worktrees/error-filter`.

## Evidence gathered in this review

Everything below was run in this session. Nothing was written to the worktree, index, `data/` or the database.

| Check | Result |
|---|---|
| `pytest engine/tests/test_errors.py api/tests/test_errors.py` (worktree root, PYTHONPATH pinned) | **14 passed** in 400 s |
| `pnpm --dir web exec vitest run` | **12 files, 85 tests passed** |
| `pnpm --dir web exec vue-tsc --noEmit -p tsconfig.json` | **exit 0**; `git status` unchanged before and after |
| AFTER-file round trip: `find_errors(result.mesh)` compared with `find_errors(read_obj(write_obj(result.mesh)))` after `fix_object`, on 4 fixtures | **identical** on box_with_partition, t_junction_strip, two_sided_wall and split_double_layer. The AFTER file numbers faces as the AFTER meshbuf does. |
| `split_double_layer` pair list (the sort-order test's fixture) | 3 pairs with distinct areas (20.0, 13.333, 6.667), so the test is not vacuous |
| Deep-watch cost (Node 24, the worktree's Vue 3.5.43, a synthetic file sized to CHTM's recorded counts) | see I1 |
| Depth-bias reach (arithmetic from `Viewport.ts`'s own camera setup) | see I2 |
| Catalogue ids used by `ERROR_KIND_CATALOGUE` | all 6 exist in `web/public/docs/errors.json` |

The scripts are in the session scratchpad: `bench_errors_reactivity.mjs`, `bench_fix_variant.mjs`,
`bench_synth.mjs` and `after_roundtrip.py`.

## Strengths

- **The engine is read-only by construction.**
  - `find_errors` only gathers detectors the pipeline already trusts: exposure, orientation, `double_layers`,
    the edge classes and T-vertices.
  - Face ids are `topo.face_w = remap[mesh.face_v]`, so they are the meshbuf's `tri_face_id`.
  - The facade is kept out of `KINDS` and `counts` exactly as the Global Constraints require.
- **The pixel stage of `double_layers` is fast and correct.**
  - It is a vectorised Möller–Trumbore over (pixel, partner) rows (`overlap.py:503-547`).
  - The CSR expansion is correct, and `t` uses the same unit-direction parametrisation as `buf.depth`.
  - Measured by the implementer: the 10,057-face slice went from 342 s to 19.5 s, and the whole of CHTM takes
    40.8 s, inside the spec's one-minute target.
  - The pixel count stayed equal to the old method's on the fixtures, with a documented, measured tolerance
    for edge-grazing rays.
- **The API is small and safe.**
  - Ids are `int` path parameters, so no path can be injected.
  - Both routes read the OBJ through the same `read_obj` as the meshbuf, so face numbers agree.
  - The meshbuf cache writes through `mkstemp` and `os.replace`, and has a MAGIC/VERSION guard with a test.
  - The fix run's AFTER file is fully isolated in `try/except` after the commit.
- **The web code has a sound structure.**
  - Pure, unit-tested `errorLayers.ts`.
  - `applyFacadeLook()` is the single writer of transparency, so X-ray and isolate no longer clobber each other.
  - Blink buffers are nulled on every overlay and length-guarded in the loop.
  - `toViewer`/origin subtraction is used consistently for lines, points and fly-to.
  - The watcher skips a panel while it is loading.
  - `clear()` disposes geometries, materials and texture maps. No three.js leak was found on reload.
- **Plan alignment is good, and the deviations are deliberate and documented.**
  - The default filter shows flicker only (owner feedback).
  - Lines and points are depth-tested with a bias instead of `depthTest: false`, after a browser finding.
  - The px equality test has a tolerance for edge-grazing rays.
  - Task 13 integrates through `applyFacadeLook`.

## Critical

None. Nothing loses data, writes outside `data/errors` and `data/meshbuf`, or breaks an existing feature.

## Important

### I1. Every legend, isolate or blink click deep-walks both errors files: about 0.8 s per click on CHTM, 2-3 s at 60k triangles

**Where:** `web/src/views/WorkspaceView.vue:545-546` (`ref<ErrorsFile | null>`) and `:608-613`
(`watch([errorFilter, errorsBefore, errorsAfter], …, { deep: true })`).

**What is wrong:** `ref()` makes each file deeply reactive, and `deep: true` makes the watcher `traverse()`
the whole returned array on every run. That includes every face id, every pair, every crack and every spot of
BOTH files, even when only a checkbox changed. The first assignment on each model load pays the same walk.

**Measured:** Node 24 with the worktree's Vue 3.5.43. The synthetic file is sized to CHTM's recorded counts
(5,668 + 4,793 flicker, 12,870 hidden, 1,055 loose, 346 open edges, 3,884 cracks, 5,765 facade, about 14k
pairs), about 108k leaf values in all. The callback does nothing, so this is the traversal alone.

| Scale | Traversal per toggle, production build | Traversal per toggle, dev build | First assignment | Heap |
|---|---|---|---|---|
| CHTM, about 20.6k triangles | 694-899 ms | 652-712 ms | 796 ms | 78 MB |
| 3x, about 61.8k triangles | 1.8-2.8 s | 1.9-5.6 s | 2.5 s | 217 MB |

`overlayFaces` through the proxy adds 108 ms (production) or 351 ms (dev) at CHTM scale, against 51 ms on the
raw object. This was not measured in the browser. Chromium runs the same V8 engine, so the order of
magnitude should hold there.

**Why it matters:**
- The owner's main interaction, toggling kinds, isolate and blink, freezes the UI for about a second on the
  worked example.
- It freezes for 2-3 s per click on a 60k-triangle building.
- Every model load pays the same cost once more.

**Fix:**
- Make the files `shallowRef<ErrorsFile | null>(null)`, or `markRaw` the fetched objects. They are never
  mutated.
- Drop `{ deep: true }`. A reactive source inside the array (`errorFilter`) is still traversed deeply by Vue
  3.5 when `deep` is left unset, while the refs are compared by identity.
- The same benchmark with this change runs the watcher on every toggle (6 of 6 runs) at 29-235 ms per toggle
  at CHTM scale, and that time is the `overlayFaces` rebuild itself.

### I2. The depth bias draws open edges and crack dots through about 114 ft of walls at the default view

**Where:** `web/src/three/Viewport.ts:490`
(`gl_Position.z -= 0.0005 * gl_Position.w`), used by `setErrorLines` (`:492-504`) and `setErrorPoints`
(`:506-518`).

**What is wrong:**
- A constant offset in NDC is not a constant distance. With this viewport's own camera settings
  (`near = size/2000`, `far = size*20`, loadModel's view at `1.45*size`), the view-space reach of a 0.0005 NDC
  pull is `1/d' = 1/d + 0.0005(f-n)/(2fn)`.
- For CHTM, with a 2,237 in diagonal and near 1.12 in:

  | Camera distance | Geometry in front that the dots and lines show through |
  |---|---|
  | 3,243 in (the default overview) | 1,363 in, **114 ft** |
  | 100 ft | 21 ft |
  | 50 ft | 5.9 ft |
  | 20 ft | 1.0 ft |
  | 96 in (the fly-to minimum) | 2 in |

- The code comment (`:486-489`) and commit 997e71d say the overlays "still los[e], correctly, to actual
  geometry in front of them (a nearer wall still hides them)". That holds only close up.

**Why it matters:**
- At every overview distance, interior open edges and crack points are drawn through the facade. They read as
  if they were on it, which misleads the "understand the errors" goal.
- Visibility changes with zoom.
- The spec asked for the opposite: only *hidden faces* are to be "drawn through walls".
- The numbers are computed from the code, not observed in a browser. The controller's check ("visible and win
  the depth test") agrees with them.

**Fix:** use a bias proportional to the distance, in view space. Scaling `mvPosition` toward the eye keeps the
same pixel and changes only the depth:
`'#include <project_vertex>\n  gl_Position = projectionMatrix * vec4(mvPosition.xyz * 0.998, 1.0);'`.
- That is 0.2% of the distance: 6.5 in at the overview (the 24-bit depth step there is 0.56 in) and 0.19 in
  at 96 in.
- It still wins the tie on its own surface, and a real wall in front hides it at every zoom.
- Re-check in the browser at the worst crack spot, as in 997e71d.

### I3. With Isolate or X-ray on, clicking a highlighted error face selects the ghost wall in front of it

**Where:** `web/src/three/Viewport.ts:534-552`. The raycast is only against
`this.parts.textured ?? this.parts.facade` (`:539`, `:546`). The overlay is built in `setErrorOverlay`
(`:460-478`), and its face-id list is not kept.

**What is wrong:**
- Isolate fades the surface to 8% opacity so that interior errors can be seen.
- The raycaster still returns the nearest surface triangle, ghosted or not. So a click on a red or blue face
  deep inside the building opens the card for the exterior wall face in front of it.
- The spec notes that "almost all" flicker pairs are back-to-back layers *inside* the building, and hidden
  faces are interior by definition.
- The controller's browser check clicked a face that was both facade and flicker, so it did not exercise
  this.
- This comes from reading the code; it was not reproduced in a browser.

**Why it matters:** the spec's "click a face to see what is wrong with it and which face it fights" does not
work for interior errors in the one mode made for finding them. It works only once the camera is inside the
building.

**Fix:**
- In `setErrorOverlay`, keep `this.overlayFaceIds = faces`.
- In the click handler, when `this.isolate || this.xray` and `this.parts.errors` exists, intersect
  `this.parts.errors` first and report `overlayFaceIds[hit.faceIndex]`.
- Otherwise fall back to the surface, which is today's path, including `faceOrder`.

### I4. "Zero-area and stray bits" shows only zero-area triangles

**Where:**
- `engine/detectors/errors.py:61` (`loose = np.nonzero(~ok)[0]`, where `ok` is only `~degenerate_mask`);
- the label at `web/src/utils/errorLayers.ts:24`;
- the (i) mapping at `web/src/utils/errorsDoc.ts:129` (`loose → 'fragments'`, whose catalogue title is
  "Zero-area triangles, slivers and stray fragments").

**What is wrong:**
- The spec's owner decision (Decisions table) and §2's source table put stray fragments in this kind
  (`detectors/fragments.py`).
- The plan's Task 2 narrowed it to degenerate faces without saying so.
- The legend and the (i) window still promise fragments and slivers. On CHTM the count, 1,055, is exactly
  the zero-area count.

**Why it matters:**
- A model whose stray fragments or slivers are its real problem reports none under a label that claims to
  cover them.
- It is an owner-approved kind that is silently incomplete. It is inherited from the plan, not an
  implementation slip.

**Fix, either:**
- (a) Add `detect_fragments(positions_c, faces, profile, contact_tol=1.5*float(topo.quanta.max()),
  max_width=<the pipeline's sliver_width_bound>)` and put
  `loose = ~ok | fr.fragments | fr.slivers`, with a fixture test for a one-face stray. Note in the file that
  these are candidates, since the pipeline also passes them through `fragment_feedback`; or
- (b) relabel the kind "Zero-area triangles" and point its (i) at a matching catalogue entry. Record the
  spec change.

## Minor

**M1. A failed `fetchErrors` aborts the rest of the workspace load.**
- **Where:** `WorkspaceView.vue:683` and `:695`, inside `reloadModel`'s single `try` (`:722-723`).
- **What:** any non-404 failure throws out of the BEFORE block. The AFTER model then never loads, the run is
  not resolved and `updateLayers()` is skipped, with only a `console.error`. The trigger is rare: a corrupt
  file or a 5xx.
- **Fix:** wrap both calls: `.catch(err => { pushBanner(...); return null })`. An optional overlay should
  never block the model.

**M2. Errors files are never refreshed.**
- **Where:** `engine/detectors/errors.py:104` writes `"version": 1`; the client never checks it.
  `web/src/components/ErrorsPanel.vue:5-10` offers Find errors only when no file exists.
- **What:** when `find_errors` changes, old files are served forever with no way to recompute from the UI.
  Tasks 14 and 15 already changed its semantics, and the parked `classify_edges` fix will change open edges
  again.
- **Fix:** bump the schema version on semantic changes, and have GET treat a mismatch as "not computed yet".
  A small "Recompute" link is also enough.

**M3. Both caches are keyed only by version id.**
- **Where:** `api/routers/versions.py:41-42` and `api/routers/errors.py:20-21`.
- **What:** after a database restore that reuses ids, which is the deploy rollback path, another model's
  meshbuf and errors file would be served. The viewer would draw them without complaint: `setErrorOverlay`
  colours whatever faces carry those ids, and fills ids past the end of `lastPositions` with zero-area
  triangles.
- **Fix:** add the version's `sha256` to the file names (or check it in a header). Have `applyErrors` refuse
  a file whose `n_faces` differs from `header.counts.faces`.
- This follows the codebase's existing assumption that ids are never reused (`data/fixed/<run_id>`), hence
  Minor.

**M4. POST `/errors` has no in-flight guard.**
- **Where:** `api/routers/errors.py:32-45`.
- **What:** two tabs, or BEFORE and AFTER pressed together, run duplicate 40 s+ computations in the
  threadpool. For the same version they also share one fixed `.json.tmp`, which is already a deferred item.
- **Fix:** add a per-version set and lock like `_active_model_fixes`, returning 409, and use `mkstemp` in
  `write_errors` as the meshbuf cache now does.

**M5. `pair_list` now lands in every fix report.**
- **Where:** `engine/fixes/overlap.py:562-566`, through `engine/cli.py:230`.
- **What:** every fix run's `report.json` and `fix_runs.report_json` now carry the full list of remaining
  pairs. The plan did not call for that; Task 1's interface was only `double_layers`' return value. It is
  small after a good fix, and large when a run leaves thousands of pairs.
- **Fix:** strip `pair_list` in `_build_report`, or keep only its length.

**M6. Test gaps for stated requirements.**
- **Task 6's isolation is untested.** Make `find_errors` raise and assert the run is still `completed` and
  GET returns 404.
- **The AFTER-file test** (`api/tests/test_errors.py:30-36`) asserts only `n_faces > 0`. Assert it equals
  the AFTER version's `tri_count`, or a POST recompute. The round trip above shows they agree today.
- **No test pins the read-only Global Constraint.** Snapshot `positions`, `face_v` and `face_material`
  before `find_errors` and compare after.

**M7. The pixel stage's memory has no bound (not measured).**
- **Where:** `engine/fixes/overlap.py:525-546`.
- **What:** the (pixel × partner) expansion builds about ten (N, 3) float64 temporaries per view. N is the
  covered pixels (up to 540k at 900×600) times the partner degree of the first-hit face. A large slab with
  hundreds of coplanar partner tiles reaches gigabytes.
- **Fix:** process the rows in chunks (for example 1M rows) inside the view loop. The result is unchanged.

**M8. Three texture details (Task 13).**
- **Where:** `Viewport.ts:242-259`.
- **What:**
  - No `onError` on `loader.load`, so a missing texture draws its faces black instead of in the grey
    fallback.
  - The "no material" fallback material lacks `polygonOffset` and `roughness`, unlike the others.
  - Materials that share a texture file each create and upload their own copy.
- **Fix:** add an `onError` that clears the map and sets the grey, give the fallback material the same
  options, and keep a per-load `Map<url, Texture>`.

**M9. Spec gaps inherited from the plan.**
- **Where:** `ErrorsPanel.vue:37-47` and `WorkspaceView.vue:230-250`.
- **What:**
  - Hidden faces are not "drawn through walls" unless Isolate or X-ray is on.
  - The face card lacks the face's area and facing, and the partner's material and OBJ line (they are one
    "select" click away).
  - Worst spots are listed for BEFORE only, though the AFTER file carries them too.
- **Fix:** either add them or record them as accepted in the spec.

**M10. Two small costs.**
- **Where:** `web/src/utils/errorLayers.ts:82-85` and `api/routers/errors.py:49-53`.
- **What:**
  - `fill` allocates a 3-element array per vertex, about 180k per toggle at 60k faces.
  - GET `/errors` parses and re-serialises a file that is already JSON.
- **Fix:** write the components directly, and return `FileResponse(path, media_type="application/json")`.

**M11. ErrorsPanel mutates its `filter` prop.**
- **Where:** `ErrorsPanel.vue:16` and `:34-35`.
- **What:** `v-model` on the prop's fields. The plan mandated this, and it works because the object is the
  parent's reactive state, but it breaks one-way data flow (`vue/no-mutating-props`).
- **Fix:** emit an `update:filter` event, or a `toggle` event with the kind, and let WorkspaceView apply it.

**Known items deliberately not re-raised** (already deferred or parked in `progress.md`, no new evidence):
- the fixed tmp name in `write_errors`;
- GET on an unknown id says "not computed yet";
- crack spots in vertex order;
- the "opposite flipped" comment in `partnerIndex`;
- the synchronous AFTER `find_errors`, Task 6, parked;
- `classify_edges` downgrading real open edges, parked;
- the redundant `astype` in `overlap.py`;
- the CLI dispatch style.

## Recommendations

1. **Before merging:**
   - I1: `shallowRef` and no `deep: true`, a two-line change.
   - I2: a view-space bias, a one-line shader change plus a browser re-check at the worst crack spot.
   - I3: pick the overlay first in Isolate or X-ray.

   All three are contained in `WorkspaceView.vue` and `Viewport.ts`, and are web-only redeploys.
2. **I4:** decide with the owner between adding fragment candidates and relabelling. Relabelling is the
   one-line honest fix if fragments must wait.
3. **Cheap robustness that pays for itself:**
   - an `n_faces === header.counts.faces` guard in `applyErrors` (M3);
   - `.catch → null` on `fetchErrors` (M1);
   - a schema version check on errors files (M2).
4. **Follow-up tasks:** the chunked pixel stage (M7), the test gaps (M6), and the texture fallbacks (M8).

## Task 13 spec compliance

✅ **Compliant.** Checked against plan lines 1778-1993 and `task-13-brief.md`:
- **Files:** `materialGroups.ts` and its test match the brief exactly (3 tests pass).
- **Textured facade:** the block is as specified, with groups in vertices, the fallback material at index
  `nMat`, `faceOrder` set, and `setTextured(this.texturedOn)`.
- **`setTextured` and `surfaceMaterials`:** as specified.
- **Material state:** `setXRay`, `setOnesidedDiagnostic`, `setDoubleSided` and isolate all reach the
  textured materials. Isolate goes through `applyFacadeLook`, the single transparency writer, which is a
  correct adaptation to the post-brief code.
- **Picking:** maps the slot back through `faceOrder` (`Viewport.ts:539-549`).
- **`clear()`:** disposes every map and resets `faceOrder`.
- **The `textures` layer:** defaults to on, has hotkey `u`, and has tests.
- **WorkspaceView:** passes both version ids, has the "Textures U" toggle, and calls `setTextured` in
  `updateLayers`.
- **Gates re-run here:** vitest 85/85 and vue-tsc exit 0.
- **The controller's browser check:** 18/18 textures 200, correct picking and colours.
- **Deviations:**
  - generic map disposal (safe);
  - no swatch on the toggle (cosmetic);
  - the co-author trailer names the implementing model (an inconsistency in the plan, not in the code).
- **No Task 13-specific defect was found beyond M8's minor texture details.** I3 predates Task 13 and applies
  equally to the flat facade.

## Assessment

**Ready to merge: With fixes.** The engine and API are correct, read-only and well tested. The AFTER file
numbers faces as the viewer does, which the round trip verified. No Critical issue was found.

Three web issues should be fixed before the branch becomes feat-dashboard's baseline:
- toggle latency of about 1 s on CHTM and 2-3 s at 60k triangles (I1);
- lines and dots drawn through walls at overview distances (I2);
- clicks that select the ghost wall in Isolate or X-ray (I3).

All three are small, local changes. The fourth Important issue, I4, is a spec gap that the plan introduced.
It needs an owner decision more than code.

Counts: **Critical 0, Important 4, Minor 11.**
