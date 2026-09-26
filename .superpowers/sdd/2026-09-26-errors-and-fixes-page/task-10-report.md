# Task 10 report: the Errors page and its floating window

Worktree: `D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/errors-page`, branch `feat/errors-page`.
Started at HEAD `bc8fa174a76c826a35f587392cedb62bbf8f6bb4`.

## Files changed

| File | Change | Lines |
|---|---|---|
| `web/src/views/ErrorsView.vue` | created | 734 |
| `web/src/components/ErrorWindow.vue` | created | 480 |
| `web/src/router.ts` | modified (+2) | 15 |
| `web/src/views/ModelsView.vue` | modified (+1) | 344 |

Total diff: 4 files changed, 1217 insertions(+), 0 deletions(-).

Each new SFC was written in three passes (template, then `<script setup>`, then `<style scoped>`)
and verified afterward to contain exactly one of each block (no accidental duplication from the
incremental edits).

## Gate 1: type check

Command: `pnpm --dir web exec vue-tsc -b`

Result: exit code 1, but the only errors are the three pre-existing ones the ruling names, all in
`web/src/three/Viewport.ts` (untouched):

```
src/three/Viewport.ts(332,34): error TS2339: Property 'side' does not exist on type 'Material | Material[]'.
src/three/Viewport.ts(333,34): error TS2339: Property 'needsUpdate' does not exist on type 'Material | Material[]'.
src/three/Viewport.ts(360,21): error TS2345: Argument of type 'number | null' is not assignable to parameter of type 'number'.
```

No errors from `ErrorsView.vue`, `ErrorWindow.vue`, `router.ts`, or `ModelsView.vue`. Gate passes
per the controller's ruling.

## Gate 2: tests

Command: `pnpm --dir web exec vitest run`

Summary line: `Test Files  9 passed (9)` / `Tests  57 passed (57)`. No regressions; no new test file
was added for the two Vue components (none required — no DOM test environment, per the rulings).

## Gate 3: build

Command: `pnpm --dir web run build`

Result: `✓ built in 2.04s`. Confirmed present: `web/dist/docs/errors.json` (60,648 bytes). The only
warning is the pre-existing "chunks larger than 500 kB" advisory, unrelated to this change (single
bundle, not something Task 10 introduced or is scoped to fix).

## Commit

SHA: `2b63a266253f20d922fac21ebc4b20c213cc0bd6`

Staged by name (not `git add -A`): `web/src/views/ErrorsView.vue`, `web/src/components/ErrorWindow.vue`,
`web/src/router.ts`, `web/src/views/ModelsView.vue`. Message is the brief's text verbatim, with
`Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` per this session's attribution rule.

`web/tsconfig.tsbuildinfo` (an untracked build artifact already present before this task started)
was left untouched and unstaged.

## Implementation notes / judgment calls

1. **Verdict-save failure display without a new prop.** Step 3's Props/Emits list for
   `ErrorWindow` is fixed to `kind`, `mistake`, `models`, `validation` / `close`, `image`,
   `verdict` — no channel for the parent to report a failed `PUT` back into a specific verdict
   row. Since the fetch itself happens in `ErrorsView.vue` (Step 4 says so explicitly), I added
   `defineExpose({ setSaveError })` inside `ErrorWindow.vue` (a `Record<modelId, string>` used
   only for the "Not saved: …" text) and call it imperatively through a template ref
   (`windowRef.value?.setSaveError(...)`) from `ErrorsView.vue` on PUT success/failure. This
   keeps the declared Props/Emits contract exactly as specified while still meeting "show a short
   red note in the window's verdict row." Flagging this as the one place I filled a real gap
   between two parts of the brief rather than following an explicit mechanism.
2. **`EngineMistake` has no `color` field.** The title bar spec ("colour swatch, the title, a ✕
   button") assumes a `kind.color`, but mistakes don't carry one. I used a fixed neutral slate
   (`#374151`) for the swatch when a mistake is open. Not specified either way in the brief.
3. **Engine-file `<select>` options** show the full path (e.g. `fixes/solidify.py`) as both value
   and label, since `DocFilter.engine` must hold the full path to match `filterKinds`/
   `filterMistakes` (only the URL query uses the stem, via `engineStem`/`filterToQuery`, which I
   left untouched in `errorsDoc.ts`). The brief didn't specify a label format for this select.
4. **Lightbox vs. window Esc precedence.** Opening the lightbox from inside an open `ErrorWindow`
   is the common path (its screenshots grid emits `image`). `ErrorsView`'s keydown listener (added
   on page mount, so registered before any `ErrorWindow` instance's own Esc listener) calls
   `stopImmediatePropagation()` when it handles Escape/Arrow keys for an open lightbox, so Escape
   closes only the lightbox, not the window behind it too. This relies on listener registration
   order rather than an explicit brief instruction, since the brief specifies each component's Esc
   handling independently and doesn't address the stacked case.
5. **No `gap` added to `.header-actions`** in `ModelsView.vue` for the two now-sibling buttons —
   both `.btn` are `display: inline-block` and the template's whitespace between the elements
   gives a small natural gap. Worth a visual check since the brief didn't call for a style change
   here and I kept the edit to the single specified line.

## Status

DONE. All three gates pass as specified by the controller's rulings; no conflicts found between
the brief, `errorsDoc.ts`, and the actual `errors.json` content (the global-constraints Kinds table
was ignored per instruction — the real kind ids/colors come entirely from `errors.json`).

## Fix round 1

Review and the controller's browser check on the live page (at HEAD `2b63a26`) found four issues.
All four are fixed in one commit, touching only the three files named below (`errorsDoc.ts` and
`router.ts` untouched).

1. **Save errors could land in the wrong window (important).** In `ErrorsView.vue`'s `saveVerdict`,
   both call sites of `windowRef.value?.setSaveError(...)` (the success-clear branch and the
   failure branch) are now guarded with `if (openId.value === payload.kindId)`. If the owner opens
   a different kind before an in-flight `PUT` settles, `windowRef.value` now points at a different
   `ErrorWindow` instance (or a `null`/unrelated one after the `:key="openId"` remount); the guard
   compares the *currently open* kind id against the kind id captured in the `payload` at the time
   the `verdict` event was emitted, and only updates that window's row when they still match. A
   late-arriving result for a closed/switched-away kind is now silently dropped instead of showing
   a false "Not saved" on the wrong kind's window.
2. **Drag could stick.** `ErrorWindow.vue`'s title bar now also binds `@pointercancel="stopDrag"`
   (alongside the existing `@pointerdown`/`@pointermove`/`@pointerup`), so a cancelled pointer
   (e.g. the OS/browser taking over the gesture) resets `dragging` the same way a normal
   `pointerup` does. `stopDrag` wraps its `releasePointerCapture` call in `try/catch`, since a
   `pointercancel` may have already released capture implicitly before the handler runs.
3. **Header buttons relied on whitespace for spacing.** Added a scoped rule to `ModelsView.vue`:
   `.header-actions { display: flex; gap: 8px; align-items: center; }`. This also resolves concern
   5 from the original report above.
4. **Horizontal overflow below ~1100px.** In `ErrorsView.vue`: `.model-card` and `.kind-card` (the
   direct children of `.models-grid` and `.kinds-grid`) gained `min-width: 0` so a grid item can
   shrink below its content's min-content size; `.model-card h3` and `.model-source` gained
   `overflow-wrap: anywhere`. `.model-skp code` and `.kind-count` already had
   `overflow-wrap: anywhere` from the original implementation, so they needed no change. In
   `ErrorWindow.vue`, `.body`'s `word-wrap: break-word` was replaced with `overflow-wrap: anywhere`
   (the modern, equivalent property — `anywhere`, unlike `break-word`, also factors into the
   automatic minimum size of flex/grid boxes, and the window body has no such box to worry about
   here, so this is a direct one-for-one strengthening) so long engine-file paths and ids wrap
   instead of stretching the fixed-width window.

### Gates (fix round 1)

- `pnpm --dir web exec vue-tsc -b`: same 3 pre-existing `Viewport.ts` errors only (lines 332, 333,
  360), nothing new.
- `pnpm --dir web exec vitest run`: `Test Files 9 passed (9)`, `Tests 57 passed (57)`.
- `pnpm --dir web run build`: succeeded; `web/dist/docs/errors.json` present (60,648 bytes).

### Commit

SHA: `3ac8331b0141480752f6adb50b934216125356c0`

Staged by name: `web/src/views/ErrorsView.vue`, `web/src/components/ErrorWindow.vue`,
`web/src/views/ModelsView.vue`. 3 files changed, 23 insertions(+), 5 deletions(-).

### Concerns

None new. The "leave as-is" minors from the coordinator's message (the `ready` guard, the triple
`verdictOf` call in the kind-card template, the duplicated status-badge CSS between the two
components) were left untouched as instructed.

## Final fix round

Source: `final-fix-brief.md`, the final whole-branch review. Worked test-first where a unit test
was possible; one commit per group (A, B, C, D), files staged by name. Started at HEAD `b7f843d`.

### A. The floating window and the owner's notes (web)

- `ErrorWindow.vue`: `startDrag`'s first line is now
  `if (ev.button !== 0 || (ev.target as Element).closest('button')) return`, so a press on the ✕
  (or any button, or a non-primary button) never takes pointer capture on the title bar; the
  browser's own click then reaches the button and `emit('close')` fires. This was the Chrome/Edge
  close-button bug.
- `ErrorWindow.vue`: added `const drafts = reactive<Record<string, string>>({})`. The textarea is
  now `:value="drafts[modelId] ?? noteFor(modelId)"` with `@input` writing into `drafts` and
  `maxlength="2000"`. `toggleVerdict` and `onNoteBlur` (now taking only `modelId`, reading the
  draft instead of a stale `FocusEvent`) both send `note: drafts[modelId] ?? noteFor(modelId)`, so
  the currently-typed text — not the last-saved note — travels with a verdict click, survives a
  failed save, and survives the re-renders that used to wipe an uncommitted edit.
- `ErrorWindow.vue`: new required prop `verdictsReady: boolean`. When false, every verdict button
  and the textarea get `:disabled="!verdictsReady"`, and a
  `<p v-if="!verdictsReady" class="note">Verdicts could not be loaded — reload the page before
  giving verdicts.</p>` appears under "Your verdict".
- `ErrorsView.vue`: passes `:verdicts-ready="!validationError"` to `ErrorWindow`.
- `ErrorsView.vue`: `saveVerdict` is now a thin chaining wrapper around the renamed `doSaveVerdict`,
  keyed per `kindId/modelId` through `const saveChains = new Map<string, Promise<void>>()` — a
  save waits for the previous save of the same kind/model before it sends, so a blur-save and a
  verdict-click-save fired close together can never race and land out of order.
- `ErrorsView.vue`: a failed save whose window is no longer open (closed, or a different kind now
  open) sets `saveBanner` — a new dismissible page-level banner reading
  `Not saved: <kind title> — <model id>: <message>` — instead of silently dropping the error as
  before.
- `ErrorsView.vue`: the PUT error-detail extraction no longer calls `JSON.stringify` on a non-string
  `detail` (which showed raw JSON). It now shows `detail[0].msg` for a 422, the string `detail` when
  it is one, else `HTTP <status>`.
- Commit: `fdd7e99` — `fix(web): Errors window -- ✕ closes it; notes are drafts that survive a
  failed save and travel with the verdict click`.

### B. The verdict API keeps a note it was not sent (api)

- `api/routers/docs.py`: `VerdictIn.note` is now `str | None = Field(default=None, max_length=2000)`.
  In `put_verdict`, when a verdict is set and `body.note is None`, the handler keeps the
  previously-stored note for that kind/model (`""` when there was none) instead of overwriting it
  with an empty string.
- Module docstrings updated in both `docs.py` and `api/tests/test_docs.py` — they described "only
  the image route" but both files also cover the verdict/validation routes.
- New test `test_a_verdict_sent_without_a_note_keeps_the_saved_note`: PUT
  `{"verdict": "ok", "note": "keep"}`, then PUT `{"verdict": "error"}` (no `note` key); GET shows
  verdict `error`, note `keep`. All 8 pre-existing tests in the file still pass unchanged.
- Commit: `ee8a0fd` — `fix(api): a verdict without a note keeps the saved note`.

### C. The content file is checked where the page relies on it (web)

- `errorsDoc.ts`'s `validateCatalogue` gained, in the brief's exact order: a per-model loop (run
  before the kinds loop) checking each model id against
  `/^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/` (`model <id>: id does not fit the verdict API`) and each
  `numbers` value for being a number or an exactly-two-element number array
  (`model <id>: bad number "<key>"`); a kind-id check against `/^[a-z0-9][a-z0-9-]{0,63}$/`
  right after the duplicate-id check (`<id>: id does not fit the verdict API`); `title` added as
  the first text-field check for both kinds and mistakes (before `summary` / `what_happened`); and
  a `sources`-has-no-non-empty-item check (`<id>: "sources" is empty`) placed right after the
  existing step-list checks.
- New test `checks titles, sources, and the ids and numbers the verdict API accepts` asserts the
  exact 6-message list for a catalogue built to trip every new rule once, in order. The existing
  "names every problem in a bad catalogue" and "the committed errors.json is valid" tests pass
  unchanged — confirmed the shipped `web/public/docs/errors.json` trips none of the new rules
  before writing the rule (`10 kinds, 3 models, 10 engine_mistakes`, 0 new-rule problems) and left
  that file untouched throughout.
- `ErrorsView.vue`'s `load()`: when the `/docs/errors.json` response's `content-type` doesn't
  contain `json`, `loadError` is set to "The documentation file is missing from this build
  (/docs/errors.json)" without attempting to parse the body. Otherwise the body is parsed and run
  through `validateCatalogue`; if it returns problems, `loadError` becomes "The documentation file
  has N problems:" and the list renders in a new `<ul class="banner-list">` under the banner, and
  `catalogue.value` is never set — the page does not render the catalogue in either failure case.
- Commit: `08d6e66` — `fix(web): the page refuses a missing or invalid errors.json with a readable
  message`.

### D. Small things (web, tools)

- Every doc `<img>` (kind examples, mistake examples in `ErrorWindow.vue`; the "Other screenshots"
  strip in `ErrorsView.vue`) now has `@error="onImageError(ex.image)"`, which flips a
  `reactive<Record<string, boolean>>` "broken" flag for that image name; a `v-else-if="ex.image"`
  grey `.image-placeholder` div then reads "Screenshot not found on this machine
  (data/errors_doc/img/&lt;name&gt;)" in its place.
- `tools/errors_doc/check.py`'s `main()` now checks `errors.json` and `owner_images.json` for
  existence before calling `missing_images`/`unused_owner_images`; if either is absent it prints
  `"<path> is missing. Make it with: python -m tools.errors_doc.extract_owner_images <log> --out
  <doc-dir>"` and returns 2, with no exception raised (so no traceback). New parametrized test
  `test_check_exits_2_with_a_clear_message_when_an_input_file_is_missing` covers both the
  `errors.json`-missing and `owner_images.json`-missing cases.
- `ErrorsView.vue`: the mistakes heading is now "Engine mistakes caught by reviews
  ({{ filteredMistakes.length }})"; when the filter leaves none, a `<p class="mistakes-empty">No
  engine mistake for this filter.</p>` replaces the (previously empty) grid.
- `ErrorWindow.vue`: "saved …" now reads `saved {{ formatSavedAt(...at) }}` where `formatSavedAt`
  is `new Date(at).toLocaleString()`; the raw UTC string is kept in the span's `:title`.
- Commit: `ab8f8c2` — `fix(web,tools): placeholders for missing screenshots, clear check.py
  messages, empty-filter text, local times`.

### Gates (final fix round)

Run in the foreground, in this order, after all four commits:

- `PYTHONPATH="D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/errors-page"
  "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest api/tests/test_docs.py
  api/tests/test_health.py tools/tests -q -p no:cacheprovider`: `54 passed, 4 warnings in 6.52s`.
- `pnpm --dir web exec vitest run`: `Test Files  9 passed (9)` / `Tests  58 passed (58)`.
- `pnpm --dir web exec vue-tsc -b`: same 3 pre-existing `Viewport.ts` errors only (lines 332, 333,
  360), nothing new:
  ```
  src/three/Viewport.ts(332,34): error TS2339: Property 'side' does not exist on type 'Material | Material[]'.
  src/three/Viewport.ts(333,34): error TS2339: Property 'needsUpdate' does not exist on type 'Material | Material[]'.
  src/three/Viewport.ts(360,21): error TS2345: Argument of type 'number | null' is not assignable to parameter of type 'number'.
  ```
- `pnpm --dir web run build`: `✓ built in 1.61s`.

### Commits (final fix round)

| Group | SHA | Message |
|---|---|---|
| A | `fdd7e99` | `fix(web): Errors window -- ✕ closes it; notes are drafts that survive a failed save and travel with the verdict click` |
| B | `ee8a0fd` | `fix(api): a verdict without a note keeps the saved note` |
| C | `08d6e66` | `fix(web): the page refuses a missing or invalid errors.json with a readable message` |
| D | `ab8f8c2` | `fix(web,tools): placeholders for missing screenshots, clear check.py messages, empty-filter text, local times` |

Each staged by name (never `git add -A`); each carries `Co-Authored-By: Claude Sonnet 5
<noreply@anthropic.com>`. `web/public/docs/errors.json` was not touched by any commit (verified via
`git diff b7f843d -- web/public/docs/errors.json`, empty). `web/tsconfig.tsbuildinfo` (an untracked
build artifact, present before this round started) remains untracked and unstaged.

### Concerns

- The brief's item A.d banner text format (`Not saved: <kind title> — <model id>: <message>`) and
  the in-window per-model error text (`Not saved: <message>`, unchanged from the existing
  implementation) now differ in verbosity by design — the in-window one already sits next to the
  model id and kind title (the window's own title bar), so repeating them there would be redundant.
- No component-level (DOM-rendering) test exists for `ErrorWindow.vue` or `ErrorsView.vue` in this
  project (only `errorsDoc.ts` has unit tests; confirmed via glob before starting), so the A/D
  template behaviour (disabled controls, placeholders, banners, dismiss button) is covered by
  type-checking and the build, not by an automated assertion. This matches the pre-existing test
  strategy for these two files (fix round 1 above notes the same gap) and the brief did not ask for
  new component tests.
- `validateCatalogue`'s new per-model loop runs unconditionally before the kinds loop, so a
  malformed `cat.models` entry (e.g. missing `numbers`) would throw rather than report a problem;
  the shipped `errors.json` and every test fixture always supply `numbers`, so this was not
  hardened further, matching the brief's scope (it specifies the two new model checks, not general
  schema robustness).
