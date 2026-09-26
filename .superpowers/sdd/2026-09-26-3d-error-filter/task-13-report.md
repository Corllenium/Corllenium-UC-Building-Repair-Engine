# Task 13 Report: Real Textures in the 3D Viewer

## Status: COMPLETED

## Commit
- SHA: `ae905acf9b689f71405c1f40c530f8318165267f`
- Branch: `feat/error-filter` (worktree: `D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter`)
- Message: `feat(web): the 3D viewer shows the model's real textures, with a Textures toggle`

## Files
Created:
- `web/src/utils/materialGroups.ts` — `groupByMaterial()`, `textureUrl()`
- `web/src/utils/materialGroups.test.ts`

Modified:
- `web/src/three/Viewport.ts` — textured facade, `setTextured`, `surfaceMaterials`, picking, `clear`
- `web/src/composables/useLayers.ts` — `textures` layer, `u` hotkey
- `web/src/composables/useLayers.test.ts`
- `web/src/views/WorkspaceView.vue` — Textures toggle, `versionId` passed to `loadModel`, `setTextured` wiring

`git diff --stat` on the commit: 6 files changed, 170 insertions(+), 30 deletions(-).

## TDD: red/green

**`materialGroups.test.ts`** (written first, verbatim from the brief):
```
❯ src/utils/materialGroups.test.ts (0 test)
Error: Cannot find module './materialGroups' imported from .../materialGroups.test.ts
Test Files  1 failed (1)
```
Then `materialGroups.ts` implemented (verbatim from the brief):
```
Test Files  1 passed (1)
     Tests  3 passed (3)
```

**`useLayers.test.ts`** (added `textures` default assertion + `u` hotkey assertion first):
```
 FAIL  src/composables/useLayers.test.ts > useLayers > initializes with expected default values
AssertionError: expected undefined to be true
 FAIL  src/composables/useLayers.test.ts > useLayers > updates layer state via hotkey handler
AssertionError: expected undefined to be true
Test Files  1 failed (1)
     Tests  2 failed | 4 passed (6)
```
Then `useLayers.ts` implemented (`textures: boolean` in `LayerState`, default `true`, `u: 'textures'` in `HOTKEYS`):
```
Test Files  1 passed (1)
     Tests  6 passed (6)
```

`Viewport.ts` and `WorkspaceView.vue` have no dedicated unit-test harness (no prior test file existed for either; Three.js/WebGL needs a real canvas), so they were implemented directly per the brief/context and verified by the full suite + type-check + build gates below, consistent with how Tasks 9/10 handled the same files.

## Gate outputs (all run in the foreground, in the worktree)

1. `pnpm --dir web exec vitest run` → **12 files passed, 85 tests passed** (0 failed).
2. `pnpm --dir web exec vue-tsc -b` → **exit 0**, no output (no new type errors).
3. `pnpm --dir web run build` → **exit 0**, `vite build` succeeded (59 modules, `dist/assets/index-CH3xYI3Z.js` 665 kB / gzip 185 kB). The "chunks larger than 500 kB" warning is pre-existing/informational, not an error, and unrelated to this task (no code-splitting was requested).

## Adaptations from the brief

The brief was written before Tasks 9/10 (and their fix rounds) reshaped `Viewport.ts` and `WorkspaceView.vue`; the task prompt's "Context the brief cannot know" section flagged this, and it matched what I found:

1. **`applyFacadeLook()` is the real integration point, not `setErrorOverlay` directly.** The brief says "`setOnesidedDiagnostic`, `setDoubleSided` and Task 9's `setErrorOverlay` (isolate) now loop over `this.surfaceMaterials()`." In the current file, isolate/X-ray opacity logic already lives in one shared private `applyFacadeLook()` that `setErrorOverlay` and `setXRay` both call (added after the brief was written). I changed `applyFacadeLook()` itself to loop over `surfaceMaterials()` rather than duplicating the loop inside `setErrorOverlay`, which keeps the single-source-of-truth the current code already established and gives the same result: isolate/X-ray apply to both the flat facade and the textured mesh.
2. **`clear()` map disposal made generic, not textured-only.** The brief says to dispose `(m as any).map?.dispose()` for "each textured material." I applied `x.map?.dispose(); x.dispose()` to every material on every disposed object (facade included). This is a no-op for materials without a `map` (the flat facade never had one) and avoids special-casing the textured mesh by name inside a loop that's already generic over `this.group.children`.
3. **Textures checkbox has no swatch and no (i) button.** The brief's own task list confirms "the new Textures toggle gets no (i)." I also omitted the color swatch (`<span class="swatch">`) that most other toggles have, following the "Sync" toggle's markup instead (checkbox + label + `<kbd>` hotkey hint, no swatch), since Textures isn't a flat-color error layer. If the controller wants a swatch for visual consistency with the rest of the row, that's a one-line addition.
4. **WorkspaceView.vue line numbers were stale.** The brief estimated "about lines 482-496" for where layers are applied to both views; in the current 1,325-line file (grown since Tasks 9/10) that logic is at `updateLayers()` around lines 723-742, and the `loadModel` call sites are around lines 678/690. Edits were made by matching the surrounding code, not line numbers.
5. **Commit co-author line** uses `Claude Sonnet 5 <noreply@anthropic.com>` (this session's actual model) rather than the brief's `<your model>` placeholder or `global-constraints.md`'s `Claude Opus 5.5` example line, per the task instructions ("your own model in the Co-Authored-By line").

No other deviations; `groupByMaterial`, `textureUrl`, the textured-facade build block, `setTextured`, `surfaceMaterials`, and the picking face-id mapping in `Viewport.ts` were implemented as given in the brief.

## Concerns

- **No runtime/browser verification performed.** Per the task instructions, no dev server was started; the controller checks the textures in a real browser on CHTM 5th floor (Task 11's note: block textures visible, the diagonal wall near (1893, 22949) flickers, "Textures" off returns grey shading). Everything here is verified by vitest/vue-tsc/build only — labeled as **expected but not browser-tested**.
- **`web/tsconfig.tsbuildinfo`** remains untracked in the worktree (a `vue-tsc -b` build artifact, pre-existing before this task, not in the brief's file list) — left alone, not staged.
- Picking's face-id mapping (`faceOrder[slot]`) and the textured/facade visibility swap in `setTextured` are logically verified by re-reading the diff and cross-checking against `groupByMaterial`'s tested sort order, but have no automated regression test of their own (three.js raycasting needs a real WebGL context) — flagged in case the controller wants a follow-up test using a mocked raycaster.
