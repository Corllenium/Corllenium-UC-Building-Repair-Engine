### Task 10: the page and its floating window

**Files:**
- Create: `web/src/views/ErrorsView.vue`, `web/src/components/ErrorWindow.vue`
- Modify: `web/src/router.ts` (route `/errors`), `web/src/views/ModelsView.vue` (header button)

**Interfaces:**
- Consumes: Task 8's exports; `GET /docs/errors.json`; `GET /api/docs/images/{name}` (Task 1); `GET /api/docs/validation` and `PUT /api/docs/validation/{kind}/{model}` (Task 9).

- [ ] **Step 1: Route and button.**
  - `web/src/router.ts`: import `ErrorsView from './views/ErrorsView.vue'`, and add `{ path: '/errors', name: 'errors', component: ErrorsView }` after the workspace route.
  - `web/src/views/ModelsView.vue`: inside `<div class="header-actions">`, before Refresh, add `<router-link to="/errors" class="btn btn-secondary">Errors &amp; fixes</router-link>`.

- [ ] **Step 2: `ErrorsView.vue`** (script setup, TypeScript, scoped styles in the light style of `ModelsView.vue`: max-width 1200px, `#1c1d21` text, `#dcdde2` borders, white cards, 8px radius). Top to bottom:
  1. **Header.** A "← Models" link to `/`, the title **"Errors: what they are, and the plan"**, and the line "Built from commit `<built_from.commit>`, <built_from.date>".
     - Beside the title, the validation summary from `validationSummary(cat, validation)`: "Validated 2 of 5 · 1 must fix · 1 OK · 0 not sure".
  2. **Origin:** each paragraph of `cat.origin`.
  3. **The models:** one card per `cat.models`, holding its name, `role`, its `numbers` (a `[a, b]` pair shown as `a → b`, with thousands separators) and `source`.
     - When `skp` is set, show the path with a Copy button that uses `navigator.clipboard.writeText` in try/catch.
     - Number labels: triangles "Triangles"; back_faces_px "Back faces seen from outside (px)". Any other key is shown as-is.
  4. **Filter bar** (sticky at the top): Model select (All + `filterChoices().models`), Engine file select (All + `engineFiles`), "N of M kinds" and a Clear button.
  5. **Catalogue grid** of `filterKinds(cat.kinds, filter)` (CSS grid, `minmax(300px, 1fr)`). Each card is a button-like `article` (`role="button"`, `tabindex="0"`, Enter opens it) and shows:
     - a 6px left border in `kind.color`, the title, and the summary;
     - one row per model in `kind.models`: the model id, a status badge (`statusLabel`), the count, and the owner's verdict when there is one (`verdictOf`), as a small badge;
     - clicking the card opens the window.
  6. **"Engine mistakes caught by reviews":** cards of `filterMistakes(...)` (title and models). Clicking opens the window.
  7. **"Other screenshots you sent":** a strip of `other_screenshots`. Clicking opens the lightbox.
  8. **Loading and errors.** Fetch `/docs/errors.json` with `{ cache: 'no-cache' }` and `/api/docs/validation` on mount.
     - A failed catalogue fetch shows "Could not load the documentation: <message>".
     - A failed validation fetch only shows a small note, "Verdicts could not be loaded", and the page still works.
  9. **URL.** On load, set the filter from `filterFromQuery(route.query, cat)` and the open window from `openFromQuery`. Then `watch` the filter and the open id, and call `router.replace({ query: filterToQuery(filter, openId) })`.
  10. **Lightbox** (full-screen dark overlay). The image comes from `imageUrl(name)`. It has a Close button, ‹ › buttons when there is more than one image, Esc to close and ArrowLeft/ArrowRight to step. The keydown listener is added on mount and removed on unmount.

- [ ] **Step 3: `ErrorWindow.vue`,** the floating window.
  - **Props:** `kind: Kind | null`, `mistake: EngineMistake | null`, `models: ModelCard[]`, `validation: Validation | null`.
  - **Emits:** `close`, `image` (payload `{ list: string[]; name: string }`) and `verdict` (payload `{ kindId: string; modelId: string; verdict: Verdict | null; note: string }`).
  - **Frame:** `position: fixed`, z-index 40, width 560px, height 72vh. `resize: both; overflow: hidden`. Min 360 × 240. White, with a shadow.
  - **Title bar:** 48px, drag handle, cursor move. It shows the colour swatch, the title, and a ✕ button.
  - **Body:** scrolls (`overflow: auto`).
  - **Starting position:** `clampWindow(window.innerWidth - 560 - 24, 72, 560, innerWidth, innerHeight)`.
  - **Dragging:**
    - `pointerdown` on the title bar calls `setPointerCapture` and records the offset.
    - `pointermove` moves the window to `clampWindow(ev.clientX - offX, ev.clientY - offY, el.offsetWidth, innerWidth, innerHeight)`.
    - `pointerup` releases.
  - **Esc** emits `close` (keydown listener on `window`, removed on unmount).
  - **Body for a kind:** headings in this order, each followed by its content.
    1. **What it is:** `what`.
    2. **How we find it:** `find`, as an ordered list.
    3. **Why the model has it:** `why`, then `why_note` in small italic.
    4. **How much of each model it is:** a table with rows model name, status badge, count.
    5. **Why you don't want it in Unity:** `unity`, as a list.
    6. **The solution:** `solution`, as an ordered list. Then **Never do this**, `never` as a list, when present.
    7. **Done so far:** `done`, as a list.
    8. **Why some can remain:** `remain`.
    9. **Your screenshots:** a grid of `examples`, each with its image (click emits `image`), date, words and caption.
    10. **Your verdict:** one row per model in `kind.models`.
        - The row holds three toggle buttons from `VERDICTS`. The active one is highlighted, and clicking it again emits `null`.
        - It also holds a note `textarea`, prefilled from `verdictOf`. It emits on blur when changed, keeping the current verdict; with no verdict yet, it emits `'unsure'`.
        - A small "saved <at>" follows.
    11. **Engine files:** monospace tags. Then **Numbers from:** `sources`, in small print.
  - **Body for a mistake:** What happened, How it was caught, The fix, Engine files, Commits, then the examples.

- [ ] **Step 4: Saving a verdict** (in `ErrorsView.vue`).
  - On `verdict`, `PUT /api/docs/validation/<kind>/<model>` with JSON `{ verdict, note }`.
  - On success, update the local `validation` object: set or delete the entry from the response.
  - On failure, show a short red note in the window's verdict row ("Not saved: <message>") and keep the previous state.

- [ ] **Step 5: Check types, tests and the build**

Run: `pnpm --dir web run type-check`, then `pnpm --dir web exec vitest run`, then `pnpm --dir web run build`.
Expected:
- the type check exits 0;
- all web tests pass;
- the build succeeds, and `web/dist/docs/errors.json` exists.

  Note for the template: TypeScript does not narrow `x.image` inside an `@click` closure, so pass `image: string | undefined` and handle `undefined`.

- [ ] **Step 6: Commit**

```bash
git add web/src/views/ErrorsView.vue web/src/components/ErrorWindow.vue web/src/router.ts web/src/views/ModelsView.vue
git commit -m "feat(web): the Errors page at /errors -- a catalogue of error kinds, each opening a floating window with its plan and the owner's verdict" -m "Every kind shows what it is, how it is found, why the model has it (Minecraft Little Tiles export), how much of each model it is, why it is unwanted in Unity, the solution, what was done and why some remain; the owner marks each kind per model as an error to fix, OK for that model, or not sure." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

