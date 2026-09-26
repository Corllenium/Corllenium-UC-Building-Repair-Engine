# Task 1 + 2 report: (i) info windows beside the workspace's error layers

Worktree: `D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/layer-info`, branch `feat/layer-info`, base `0637037`.
Implementer: sonnet (this agent). Two commits, as specified.

## Status: DONE — both gates-clean, both committed.

- Commit 1 (Task 1): `7d76cfa` — refactor(web): the Errors page's loading and verdict saving become a shared composable
- Commit 2 (Task 2): `63ce3c5` — feat(web): an (i) beside each error layer in the workspace opens that error's description window

Gate summary (run after each task, in the foreground, one at a time; final numbers are after both
tasks): `pnpm --dir web exec vitest run` → 68/68 passed; `pnpm --dir web exec vue-tsc -b` → exactly
the 3 pre-existing `Viewport.ts` errors (332/333/360), nothing new; `pnpm --dir web run build` →
succeeded.

---

## Task 1 — `useErrorsDoc` composable

### Files
- Created `web/src/composables/useErrorsDoc.ts`
- Created `web/src/composables/useErrorsDoc.test.ts`
- Modified `web/src/views/ErrorsView.vue`

### What moved, what stayed
`load()` (the two fetches, catalogue validation, error text), the per-key `saveChains` ordering,
and the 422/string/HTTP-status error-text logic all moved into the composable exactly as they
worked before. `ErrorsView.vue` keeps the `openId` guard, the `setSaveError` bridge and the page
`saveBanner` — it now passes an `onError` callback into `errorsDoc.saveVerdict(payload, cb)` that
reproduces the exact same routing (window row vs. page banner) and the exact same strings
(`Not saved: ${message}` / `Not saved: ${title} — ${modelId}: ${message}`).

One deliberate timing choice: `loaded` flips to `true` at the same point the old local `loading`
flag flipped to `false` — right after the `/docs/errors.json` fetch settles, *before* the
`/api/docs/validation` fetch starts — not at the very end of `load()`. This keeps the Errors page's
"Loading…" banner disappearing at exactly the same moment as before, and is what makes `loaded`
usable as WorkspaceView's idempotency guard in Task 2 ("later clicks reuse the loaded catalogue").
The page's own `ready` flag (used only to suppress the URL-query-sync `watch` while the initial
filter/openId are being derived from the route) was left untouched and local to `ErrorsView.vue`.

### TDD: red line, then green
Red (module didn't exist yet):
```
 FAIL  src/composables/useErrorsDoc.test.ts [ src/composables/useErrorsDoc.test.ts ]
Error: Cannot find module './useErrorsDoc' imported from D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/layer-info/web/src/composables/useErrorsDoc.test.ts
 ❯ src/composables/useErrorsDoc.test.ts:2:1
      1| import { describe, it, expect, vi, beforeEach, afterEach } from 'vites…
      2| import { useErrorsDoc, errorText } from './useErrorsDoc'
       | ^
      3| import type { Catalogue } from '../utils/errorsDoc'
      4|

 Test Files  1 failed (1)
      Tests  no tests
```
Green (after implementing `useErrorsDoc.ts`):
```
 Test Files  1 passed (1)
      Tests  8 passed (8)
```
All 8 specified cases are covered 1:1: two-fetch load; non-JSON errors.json → loadError; invalid
catalogue → loadProblems + catalogue stays null; failed validation GET → validationError but
catalogue still loads; two same-key saves proven ordered via a manually-resolved deferred fetch
promise (second `fetch` call not made until the first resolves); a failed save doesn't block the
next save for the same key; a successful save sets validation then a null verdict clears it;
`errorText` 422-detail-array and generic-500 cases.

### Gate output (this task's state)
`pnpm --dir web exec vitest run` (targeted, then full suite once ErrorsView was wired):
```
 Test Files  10 passed (10)
      Tests  66 passed (66)
```
`pnpm --dir web exec vue-tsc -b`:
```
src/three/Viewport.ts(332,34): error TS2339: Property 'side' does not exist on type 'Material | Material[]'.
  Property 'side' does not exist on type 'Material[]'.
src/three/Viewport.ts(333,34): error TS2339: Property 'needsUpdate' does not exist on type 'Material | Material[]'.
  Property 'needsUpdate' does not exist on type 'Material[]'.
src/three/Viewport.ts(360,21): error TS2345: Argument of type 'number | null' is not assignable to parameter of type 'number'.
  Type 'null' is not assignable to type 'number'.
```
(the 3 known, pre-existing errors named in global-constraints.md — no new ones)
`pnpm --dir web run build`: `✓ 54 modules transformed` / `✓ built in 2.23s`.

### SHA
`7d76cfa` — `refactor(web): the Errors page's loading and verdict saving become a shared composable`

### Concerns
- I did not open the Errors page in a real browser myself (the brief says the controller checks
  that in a browser). My confidence that behaviour is unchanged rests on: a line-by-line
  behaviour-preserving move (same fetch order, same strings, same save-chain semantics, same
  success/error routing) plus the full test suite, type-check and build all passing. Worth a
  browser pass before/instead of trusting this note alone.

---

## Task 2 — the (i) buttons in the workspace

### Files
- Modified `web/src/utils/errorsDoc.ts` — added `LAYER_KINDS`, `catalogueModelId`
- Modified `web/src/utils/errorsDoc.test.ts` — tests for both
- Modified `web/src/components/ErrorWindow.vue` — added `onlyModel` prop
- Modified `web/src/views/WorkspaceView.vue` — the 5 (i) buttons + the window

### TDD: red line, then green
Red (functions didn't exist yet):
```
 ❯ src/utils/errorsDoc.test.ts (13 tests | 2 failed) 10ms
   ❯ errorsDoc (13)
     × maps each error layer to its catalogue kind 4ms
     × finds the catalogue model with the same name as a workspace model, else null 0ms

 FAIL  src/utils/errorsDoc.test.ts > errorsDoc > maps each error layer to its catalogue kind
AssertionError: expected undefined to deeply equal { grid: 'gridlines', …(4) }
 FAIL  src/utils/errorsDoc.test.ts > errorsDoc > finds the catalogue model with the same name as a workspace model, else null
TypeError: catalogueModelId is not a function

 Test Files  1 failed | 1 passed (2)
      Tests  2 failed | 19 passed (21)
```
Green (after adding `LAYER_KINDS` and `catalogueModelId` to `errorsDoc.ts`):
```
 Test Files  2 passed (2)
      Tests  21 passed (21)
```
`LAYER_KINDS` is asserted equal to the exact table (grid/tri → gridlines, hidden/xray →
hidden-faces, onesided → reversed-faces). `catalogueModelId` is checked against the *committed*
`public/docs/errors.json`: `chtm_5ft_floor` → `CHTM5`, an unknown name → `null`.

### Implementation notes
- `ErrorWindow.vue`: a `visibleModelIds` computed narrows both the "how much of each model" table
  and the "Your verdict" rows to `[onlyModel]` when `onlyModel` names one of the kind's models;
  otherwise (prop unset, or naming a model the kind has no row for) it falls back to every model,
  so `ErrorsView.vue`'s existing usage — which never passes `onlyModel` — is provably unaffected.
- `WorkspaceView.vue` holds one shared `useErrorsDoc()` instance for all 5 buttons. `openInfo(layerKey)`
  looks the catalogue kind id up via `LAYER_KINDS[layerKey]`, sets it as the open kind, and calls
  the composable's `load()` — a no-op after the first successful call, which is what makes "later
  clicks reuse the loaded catalogue" true. `infoTitle(layerKey)` independently looks up that
  layer's own kind title from the (possibly still-null) catalogue for the `title` attribute, so
  all 5 buttons' tooltips upgrade from "About this error" to "About: <title>" together once the
  catalogue arrives, regardless of which button triggered the load.
- `onlyModel` is computed as `catalogueModelId(catalogue, model.name)` — the workspace model's own
  name against the loaded catalogue — null when nothing matches, per the global constraint.
- Load failure shows a small fixed box (`.info-load-error`) with `loadError`'s text and a Close
  button, in place of the `ErrorWindow`.
- Per the brief's literal wording, a failed save's message goes to
  `windowRef.setSaveError(payload.modelId, message)` with **no** `"Not saved: "` prefix — unlike
  `ErrorsView.vue`'s own prefixed strings. This is intentional (the brief spells out that exact
  call), but flagging in case the two windows were meant to read identically.
- Image clicks call `window.open(imageUrl(name), '_blank', 'noopener')` — no lightbox in the
  workspace, matching the plan's ruling.
- (i) buttons are `type="button"` with `@click.stop.prevent`, placed after each `<kbd>`, only on
  the 5 mapped labels (Gridlines, Triangles, Removed Faces, One-Sided/Flipped, X-Ray) — Outlines,
  Creases and Sync get none.

### Gate output (final, both tasks in place)
`pnpm --dir web exec vitest run`:
```
 Test Files  10 passed (10)
      Tests  68 passed (68)
```
`pnpm --dir web exec vue-tsc -b`: same 3 known `Viewport.ts` errors as above, nothing new.
`pnpm --dir web run build`: `✓ 54 modules transformed` / `✓ built in 1.54s`.

### SHA
`63ce3c5` — `feat(web): an (i) beside each error layer in the workspace opens that error's description window`

### Concerns
- No component-level test covers `ErrorWindow.vue`'s `onlyModel` narrowing or `WorkspaceView.vue`'s
  buttons/window directly — this codebase has no `@vue/test-utils` and no existing `.vue` component
  tests (only composables/utils get `.test.ts` files), so I matched that convention rather than
  introducing a new testing approach. Coverage for this task is: unit tests for the two pure
  functions (`LAYER_KINDS`, `catalogueModelId`), plus `vue-tsc -b` and a production `build` proving
  the templates type-check and compile.
- I did not load the workspace page itself in a browser (it needs the FastAPI backend, a DB, and a
  real imported model with mesh data to render anything) — the (i) buttons, the window opening,
  and the load-error box are **expected but not visually verified** in this session. Worth a
  browser pass, especially to confirm the (i) button truly never toggles its checkbox and that the
  window position/size is sane over the layer-toggles bar.
- `web/tsconfig.tsbuildinfo` was generated by `vue-tsc -b` and left untracked (not staged in either
  commit) — it's a build cache artefact, not source.

---

## Fix round 1 (review feedback on Task 2)

One commit, touching only `web/src/views/WorkspaceView.vue`, `web/src/composables/useErrorsDoc.ts`
and its test, per the coordinator's scope.

### What changed and why

1. **Stale "Not saved" after a later success (important).** `onInfoVerdict` now tracks `errored`
   across the `saveErrorVerdict` call, mirroring `ErrorsView.vue`'s `saveVerdict` wrapper exactly:
   on success, if the same kind's window is still open, it calls
   `infoWindowRef.value?.setSaveError(payload.modelId, null)`, clearing any earlier failure shown
   for that model.
2. **Misrouting after a window switch (important).** The error callback now checks
   `openLayerKindId.value === payload.kindId` before touching `infoWindowRef` (the kind id being
   checked is `payload.kindId` — already a fixed snapshot from when `onInfoVerdict` was called,
   since it comes from the `payload` argument, not a live reference). When that no longer holds
   (window closed, or a different kind's window open by the time the PUT settles), the failure now
   goes to a new `infoSaveBanner` ref instead of a wrong window's row. The banner is rendered as a
   small, dismissible, `position: fixed` box centred above the canvases (`top: 76px; left: 50%;
   transform: translateX(-50%)`), text `Not saved: <kind title> — <model id>: <message>` — the same
   format `ErrorsView.vue`'s page banner uses.
3. **Missing "Not saved: " prefix (minor).** In-window failures now read
   `` `Not saved: ${message}` ``, matching the Errors page's wording exactly (previously the raw
   message was shown with no prefix).
4. **Duplicate loads (minor).** `useErrorsDoc.ts`'s `load()` was split into a thin idempotent/dedup
   wrapper plus a private `doLoad()`: `if (loaded.value) return Promise.resolve()`; `if (inflight)
   return inflight`; else `inflight = doLoad().finally(() => { inflight = null })`. A concurrent
   second call (e.g. two (i) buttons clicked before the catalogue fetch resolves) now reuses the
   same in-flight promise instead of firing a second `fetch`.

### Files
- Modified `web/src/composables/useErrorsDoc.ts` — `load()`/`doLoad()` split with `inflight` dedup
- Modified `web/src/composables/useErrorsDoc.test.ts` — new dedup test
- Modified `web/src/views/WorkspaceView.vue` — `onInfoVerdict` rewritten; `infoSaveBanner` +
  `dismissInfoSaveBanner`; banner markup and `.info-save-banner` / `.banner-dismiss` styles

### TDD: red line, then green
Wrote the new test, then confirmed it actually catches the bug by stashing only the `useErrorsDoc.ts`
implementation change (keeping the new test) and re-running:
```
 ❯ src/composables/useErrorsDoc.test.ts (9 tests | 1 failed) 30ms
   ❯ useErrorsDoc (9)
     × reuses an in-flight load: two calls before the first resolves fetch errors.json once 5ms

 FAIL  src/composables/useErrorsDoc.test.ts > useErrorsDoc > reuses an in-flight load: two calls before the first resolves fetch errors.json once
AssertionError: expected 2 to be 1 // Object.is equality
- Expected
+ Received
- 1
+ 2
 ❯ src/composables/useErrorsDoc.test.ts:66:31

 Test Files  1 failed (1)
      Tests  1 failed | 8 passed (9)
```
Green (fix restored via `git stash pop`):
```
 Test Files  1 passed (1)
      Tests  9 passed (9)
```

### Gate output (final)
`pnpm --dir web exec vitest run`:
```
 Test Files  10 passed (10)
      Tests  69 passed (69)
```
`pnpm --dir web exec vue-tsc -b`: same 3 known `Viewport.ts` errors (332/333/360), nothing new.
`pnpm --dir web run build`: `✓ 54 modules transformed` / `✓ built in 1.76s`.

### SHA
`4776e3d` — `fix(web): the workspace info window reports saves like the Errors page -- cleared on success, never in the wrong window`

### Concerns
- Still no live-browser check of the workspace page (same backend/DB/model dependency noted in
  Task 2 above) — the fail-then-succeed clearing, the window-switch banner, and the dedup guard are
  verified by the composable's unit tests and by re-reading the mirrored ErrorsView.vue logic
  side-by-side, not by clicking through the running app.
- The banner's `top: 76px` is a fixed estimate of the top-bar's height (it can wrap on narrow
  viewports); if the top-bar grows taller than that in practice the banner could sit slightly over
  it rather than cleanly below — cosmetic only, doesn't block correctness.
