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
