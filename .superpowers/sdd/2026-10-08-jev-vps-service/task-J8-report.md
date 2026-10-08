# J8 report: the /jev review page

Branch `claude/J8` (base de7fa09). Status: DONE_WITH_CONCERNS.

## Commits
- 3a215c5 feat(web): decide API client and jevReview logic modules (tests first)
  (`web/src/api/decide.ts`, `web/src/utils/jevReview.ts`, both test files; `checkResponse` in `client.ts` now exported, one word, no behaviour change)
- 426e339 feat(web): /jev review page for Jev suggestions (accept, change, accept-all with confirm)
  (`web/src/views/JevView.vue`, route `/jev` in `web/src/router.ts`)

## How tests were run (no install in the worktree)
`vite.config.ts` of the worktree cannot resolve `vite` (no node_modules). Used the main checkout's install without copying:
`( cd "D:/PROJECTS/UC MODEL FIXER/web" && npx vitest run <files> --root "<wt>/web" --config "D:/PROJECTS/UC MODEL FIXER/web/vite.config.ts" )`
(the main config is the same content as the worktree one; only the line endings differ).
For the full suite and the build, bare imports of `vue`, `vue-router`, `three` from worktree files do not resolve, so the
same plugin set was used from a scratchpad config (`scratchpad/j8-vite.config.mjs`) that aliases those three packages to
the main checkout's node_modules. Nothing was written into the main checkout.

## Red (before the modules existed)
```
FAIL  src/api/decide.test.ts      Error: Cannot find module './decide' imported from .../src/api/decide.test.ts
FAIL  src/utils/jevReview.test.ts Error: Cannot find module './jevReview' imported from .../src/utils/jevReview.test.ts
Test Files  2 failed (2)   Tests  no tests
```

## Green
First implementation run: 24 passed, 1 failed. The failure was a bug in my test (`mockResolvedValue` returned one
Response for two calls, "Body is unusable: Body has already been read"); fixed the test to build a fresh Response per call. Then:
```
Test Files  2 passed (2)
     Tests  25 passed (25)
```
Full web suite (scratch config), after the view:
```
Tests  132 passed (132)
```
With only the main-checkout config (no alias), 8 older test files (`src/three/*`, `src/composables/*`) fail to load with
"Cannot find package 'three'/'vue'" from the worktree path; they are environmental, none touch my files. 90 tests pass in that run.

## Build tail (`vite build`, outDir in the scratchpad)
```
✓ 65 modules transformed.
.../j8-dist/index.html                  0.47 kB │ gzip:   0.30 kB
.../j8-dist/assets/index-biv2oUQn.css  26.69 kB │ gzip:   5.16 kB
.../j8-dist/assets/index-CWoQvrRo.js  678.30 kB │ gzip: 189.29 kB
(!) Some chunks are larger than 500 kB after minification.   (existing warning)
✓ built in 2.56s
```

## What the tests cover (25)
- decide.test.ts (7): review posts JSON to `/api/decide/review/7`; the raw bodies `{answer:false}`, `{answer:'glass'}`, `{answer:2}` go out unchanged;
  a 422 becomes `ApiError`; `fetchHealth` reads `jev_enabled`; health 502 and 404 become `ApiError` with the status (non-JSON body);
  `fetchSuggestions` sends only the params that are set; reask posts to `/api/decide/reask/3` and a 409 "jev off" is an `ApiError`.
- jevReview.test.ts (18): `TABS` (Materials and Campus map live with their qtypes, three not); `filterRows` (status, min confidence inclusive, case-insensitive subject);
  `topAlternatives` (leaves out the chosen answer, sorted, n, Noul `"true"/"false"` and Score `"0".."n"` string keys, `{}` for pilot imports);
  `acceptAllSelection`; `optionLabels` (`["yes","no"]`, Choice keys, Score levels) and `optionValues` (`[true,false]`, the label, the int index),
  with a test that Change maps a chosen display label to the RAW value; `answerLabel`; `textureName`; `isServiceMissing` (404/502 only); `mergeResults`.

## Page behaviour (JevView.vue, thin; logic in the modules)
- Tabs: Materials and Campus map live; the other three disabled and marked "not available yet".
- Banner "Jev is off until the repair engine is ready" while `health.jev_enabled` is false; the Re-ask button is hidden then (and for reviewed rows).
- Health or suggestions 404/502: the page shows only "Jev service runs on the VPS". Other errors show their message in an error banner.
- Counts, filters (question type within the tab, status, min confidence, subject search), confidence bar, top-2 alternatives, Accept, Change (`<select>` of `optionLabels`, sends `optionValues[index]`).
- "Accept all shown >= X": `acceptAllSelection(shown rows, X)`, `window.confirm` with the count, then one `POST review {accept:true}` per id, sequentially, with a result notice and a reload.
- Texture is shown as text only (file name from the question instructions); no thumbnail and no other API route is called. Only `/api/decide/*` is used.

## Concerns
- The view itself was not mounted or clicked (no browser run, no component test; `@vue/test-utils` is not a dependency and I added none). It compiled in the production build; its logic is in the tested modules. Unverified by eye.
- `vue-tsc` could not be run meaningfully from the worktree (modules unresolved cause cascading "implicit any" noise); the build and vitest pass. Type-check not verified.
- "All of this tab" fetches one request per question type (limit 500 each) and merges; counts from the service are summed. If a type has 500 or more rows the page says so; there is no paging.
- `textureName` uses only the instructions text. The brief also said "or from the subject", but for materials the subject is the material name, not a file, so I did not use it (inv.* rows have no texture and show none).
- Qtype names for the three unavailable tabs (`repair.next_step`, `repair.review_order`, `repair.tie_break`) are placeholders; those tabs are disabled and never fetch.
- Accept-all failures are shown per row and in a "Accepted n, m failed" notice; a 404 mid-way on one id does not stop the rest.
- `client.ts` was touched by one word (`export` on `checkResponse`) so `decide.ts` reuses it rather than copying it. Revert if you prefer client.ts untouched; the helper would then be duplicated in decide.ts.
- Not touched: `engine/guard/**`, FixProfile, existing tests, containers, database, export folder, master. No new npm dependency.

---

# Fix round 1 (controller review: CHANGES)

Commits: 757f867 (modules + tests), then the view commit on top (see `git log claude/J8`).

## Tests first (red, then green)
Red run before the module changes: 14 failed, 26 passed, e.g. `acceptAllSelection('')` returned [1,2] instead of [];
`suggestionParams is not a function`; `runAcceptAll is not a function`; `errorText is not a function`;
`fetchSuggestions({min_conf: NaN})` sent `?min_conf=NaN`. After: `Test Files 2 passed, Tests 40 passed (40)`.
Full suite after the view: `Test Files 18 passed (18), Tests 147 passed (147)`. Build: `built in 2.09s` into `scratchpad/j8-dist` (same path, rebuilt).

## Items
1. Server filters: `suggestionParams(filter, type, limit)` builds `{type, status (omitted for all), min_conf (0 is kept), q (trimmed, omitted if empty), limit}`.
   The page reloads on status change at once, and on min confidence / text change after a 300 ms debounce. The note about 500 rows now shows only when a server-filtered reply holds 500 rows.
   Tests: params pass-through in `decide.test.ts` and `suggestionParams` in `jevReview.test.ts`. Measured in the browser check: the request is
   `/api/decide/suggestions?type=mat.category&min_conf=0&limit=500&status=pending`.
2. `isValidThreshold`: `acceptAllSelection` and `filterRows` give nothing for '', NaN, Infinity or undefined; the page shows a hint, the Accept button is disabled
   (selection empty). `fetchSuggestions` also drops non-finite numbers. Tests for '' and NaN.
3. `runAcceptAll(ids, acceptFn, {onStart}) -> {done, failed:[{id,error}], stoppedAfter}` in `jevReview.ts`. Continues only on a per-row 404 with detail
   "unknown suggestion", 422 or 409. Stops on a service 404 (any other 404 text), 502, 401, 403, 500 and non-ApiError errors; `stoppedAfter` is the count finished before the stopping id (that id is in `failed`).
   `onStart` is how the page clears `rowError` for every id at the start. The notice reads "Stopped after k of n: <message>". Tested with fake accept functions (all branches).
   Interpretation to confirm: the brief lists "isServiceMissing" as a stop and "a per-row 404" as a continue; both are 404, so the line is drawn by the service's own text "unknown suggestion" (app.py).
4. Layout: `.row` flex-wrap with `.row-main {flex: 1 1 260px; min-width: 0}`; under 600 px the actions take the full row below the content;
   long names wrap (`overflow-wrap: anywhere`); counts, filters and tabs wrap; the page container is `overflow-x: hidden` as a backstop (nothing relies on it).
   Measured in headless Chrome over CDP against the built page with a mock service (script `scratchpad/j8-check.mjs`; screenshots `scratchpad/j8-shot-375.png`, `j8-shot-800.png`, both read back):
   - 375 px: `innerWidth 375, documentElement.scrollWidth 375, body.scrollWidth 375`, elements right of the viewport: none. Accept and Change sit side by side under the content, fully visible.
   - 800 px: `scrollWidth 800`, no element past the edge; the tab row wraps ("Fix tie-breaks" on a second line, fully visible).
5. Request counter in `load()`: an older reply is dropped (data, error and the loading flag).
6. "Re-ask refused:" only for 409; a 502 shows its own message.
7. Accessibility: `aria-label` "Accept/Change/Re-ask Jev about <subject>", `aria-pressed` on tabs, `role="status"` on the Jev-off banner, the VPS banner, counts and notice, `role="alert"` on error banners, row errors and the confidence hint, `aria-live="polite"` on Loading.
8. 422 list detail: `decide.test.ts` keeps the list as JSON in `ApiError.message`; `errorText` (tested) turns `[{loc, msg}]` into "body.accept: msg; ..." and leaves non-list text alone. The page uses it for every error.

## Not verified
- Accept, Change, Accept-all and the stale-reply guard were not clicked in my browser run (only load, layout and request shape). The controller verified Accept end to end; the logic of Accept all is in the tested `runAcceptAll`.
- `vue-tsc` still not run meaningfully from the worktree.
