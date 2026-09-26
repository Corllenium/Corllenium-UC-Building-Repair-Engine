# Layer info windows in the 3D workspace — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** In the 3D workspace, a small (i) button beside each layer that shows an error opens that error's
description window, the same floating window as the Errors page. The window lets the owner give a verdict
for the model they are looking at.

**Owner's words (2026-09-26 14:40, screenshot of the workspace with Gridlines on):** "if I click
gridlines ... maybe there's a window here I can see inside the details of the error". Asked how it should
open, the owner chose "Small (i) button per layer". The window does not open by itself on ticking a layer.

**Spec:** the Errors page spec and its amendments
(`docs/superpowers/specs/2026-09-26-errors-and-fixes-page-design.md`). This plan adds one more place the
window opens from, the workspace. Nothing else in that spec changes.

**Architecture:**
- The Errors page's loading and verdict-saving logic moves out of `ErrorsView.vue` into a composable,
  `useErrorsDoc`, so the workspace uses the same code:
  - one save chain per kind and model;
  - the same readable errors;
  - the same `validation.json`.
- A mapping in `errorsDoc.ts` names the catalogue kind behind each workspace layer.
- `ErrorWindow.vue` gains an optional `onlyModel` prop. In the workspace, the window shows the numbers
  and the verdict row of the open model only.

## Global Constraints

- **Branch and worktree.** Branch `feat/layer-info`, worktree `.claude/worktrees/layer-info`, from
  feat-dashboard. There is no API or database change.
- **Layer → catalogue kind:**

  | Layer | Kind id |
  |---|---|
  | `grid` (Gridlines) | `gridlines` |
  | `tri` (Triangles) | `gridlines` |
  | `hidden` (Removed Faces) | `hidden-faces` |
  | `xray` (X-Ray) | `hidden-faces` |
  | `onesided` (One-Sided / Flipped) | `reversed-faces` |

  Outlines, Creases and Sync get no (i): they are not errors.
- **Workspace model → catalogue model:** the catalogue model whose `name` equals the workspace model's
  `name` (`chtm_5ft_floor` → `CHTM5`, etc.). When nothing matches, the window shows every model's rows.
- **The (i) button** must not toggle its layer's checkbox. It sits inside the checkbox's `<label>`, so it
  needs `type="button"` and `@click.stop.prevent`.
- **Gates** (foreground, from the worktree root):
  - `pnpm --dir web install --frozen-lockfile` once;
  - `pnpm --dir web exec vitest run`, all pass;
  - `pnpm --dir web exec vue-tsc -b`: only the 3 known errors in `web/src/three/Viewport.ts`
    (332/333/360, still present on feat-dashboard);
  - `pnpm --dir web run build`.
- **Commits:** stage by name; the implementer's own model goes in the Co-Authored-By line.

---

### Task 1: `useErrorsDoc`, the Errors page's logic as a shared composable

**Files:**
- Create: `web/src/composables/useErrorsDoc.ts`, `web/src/composables/useErrorsDoc.test.ts`
- Modify: `web/src/views/ErrorsView.vue`: use the composable, with the same behaviour as today

**Interfaces (produced):**

```ts
export interface SavePayload { kindId: string; modelId: string; verdict: Verdict | null; note: string }
export function useErrorsDoc(): {
  catalogue: Ref<Catalogue | null>
  validation: Ref<Validation | null>
  loadError: Ref<string>                 // '' when fine
  loadProblems: Ref<string[]>            // validateCatalogue problems
  validationError: Ref<boolean>          // GET /api/docs/validation failed
  loaded: Ref<boolean>
  load: () => Promise<void>              // idempotent: a second call does nothing once loaded
  saveVerdict: (p: SavePayload, onError?: (message: string) => void) => Promise<void>
}
export function errorText(status: number, body: unknown): string   // 422 → detail[0].msg; string detail; else `HTTP <status>`
```

- Move `load()`, the save chain (`saveChains`) and the error-text logic out of `ErrorsView.vue` without
  changing behaviour.
- `ErrorsView.vue` keeps its window-specific parts: the `openId` guard, `setSaveError` and the page
  banner. It passes an `onError` callback that routes the message exactly as today.
- **Tests** (vitest, mocking `globalThis.fetch`; no DOM needed):
  1. `load` sets `catalogue` and `validation` from two JSON responses.
  2. A non-JSON `/docs/errors.json` response sets `loadError` to the "missing from this build" message.
  3. An invalid catalogue fills `loadProblems` and leaves `catalogue` null.
  4. A failed validation GET sets `validationError` and still loads the catalogue.
  5. Two `saveVerdict` calls for the same kind/model are sent one after the other. Use deferred fetch
     promises: the second request is not sent before the first resolves.
  6. A failed save does not block the next save for the same key.
  7. A successful save updates `validation`: set, then cleared by a null verdict.
  8. `errorText(422, { detail: [{ msg: 'String should have at most 2000 characters' }] })` returns that
     message, and `errorText(500, {})` returns `HTTP 500`.
- **Commit:** `refactor(web): the Errors page's loading and verdict saving become a shared composable`.

### Task 2: the (i) buttons in the workspace

**Files:**
- Modify:
  - `web/src/utils/errorsDoc.ts`: add `LAYER_KINDS` and `catalogueModelId`;
  - `web/src/utils/errorsDoc.test.ts`: tests for both;
  - `web/src/components/ErrorWindow.vue`: the `onlyModel` prop;
  - `web/src/views/WorkspaceView.vue`: the (i) buttons and the window.

**Interfaces:**
- `export const LAYER_KINDS: Record<string, string>`: exactly the table in Global Constraints.
- `export function catalogueModelId(cat: Catalogue, modelName: string): string | null`.
- `ErrorWindow` prop `onlyModel?: string | null`. When it is set and the kind has that model, the "How
  much of each model" table and the "Your verdict" rows show only that model. Otherwise they are
  unchanged.

**Behaviour:**
- **The buttons.** In `WorkspaceView.vue`'s `.layer-toggles`, each of the 5 mapped labels gets, after its
  `<kbd>`, a small round (i) button:
  - `type="button"`, `aria-label="What is this error?"`, and `title` "About: <kind title>" once loaded,
    else "About this error";
  - `@click.stop.prevent="openInfo('<kind>')"`.
- **First click.** It calls `load()` from `useErrorsDoc()`, then opens `ErrorWindow` with:
  - `kind` = the catalogue kind;
  - `models` = the catalogue models;
  - `validation`;
  - `verdictsReady = !validationError`;
  - `onlyModel = catalogueModelId(catalogue, model.name)`.

  Later clicks reuse the loaded catalogue.
- **When loading fails,** the window area shows a small fixed box with the load error and a Close button.
- **Window events:**
  - `verdict` calls `saveVerdict(payload, message => windowRef.setSaveError(payload.modelId, message))`;
  - `close` closes the window;
  - `image` opens `imageUrl(name)` in a new tab (`window.open(..., '_blank', 'noopener')`). The workspace
    has no lightbox.
- **Keyboard.** Esc closes the window (the window's own handler). While the window is open, the layer
  hotkeys must not fire when typing in its note textarea: `useLayers` already ignores textarea targets;
  keep it so.
- **Tests:**
  - `LAYER_KINDS` equals the table.
  - `catalogueModelId` returns `CHTM5` for `chtm_5ft_floor` on the committed `errors.json`, and null for
    an unknown name.
- **Commit:** `feat(web): an (i) beside each error layer in the workspace opens that error's description window`.

### Task 3 (controller): review, deploy, check, merge

- [ ] Review both commits as one unit.
- [ ] Rebuild the web image only by HANDOFF section 8 (the API is unchanged), from the reviewed commit.
- [ ] **Check in the browser with REAL mouse input**, on model 2 (CHTM 5th floor):
  - each (i) opens the right kind;
  - the checkbox does not toggle;
  - only the CHTM5 row shows;
  - a verdict saves, and is then cleared, leaving the owner's file as it was;
  - Esc and ✕ close the window.
- [ ] Merge into feat-dashboard. Records.
- [ ] Later, in the 3D error filter's Task 10, the errors legend gets the same (i) per kind, using
  `useErrorsDoc`. Mapping: flicker_diff/flicker_same → `flicker`, reversed → `reversed-faces`,
  hidden → `hidden-faces`, loose → `fragments`, open_edges → `holes-sides`, cracks → `cracks`,
  facade → none.
