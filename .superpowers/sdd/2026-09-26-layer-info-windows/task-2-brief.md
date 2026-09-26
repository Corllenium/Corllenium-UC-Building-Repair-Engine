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

