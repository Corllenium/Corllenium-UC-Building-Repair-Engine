# Task 8 report: the catalogue's logic, and the content test

Worked in the worktree `D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/errors-page` (branch `feat/errors-page`, started at HEAD `c10721f`). Main checkout was not touched.

## Files changed

All three created exactly as the brief specified (no other files touched):

- `web/src/utils/errorsDoc.ts` (new, 331 lines) — the catalogue types, `ENGINE_FILES` / `STATUS_LABEL` / `VERDICTS` / `IMAGE_NAME` / `WINDOW_HEADER` constants, and every function from the interface (`filterKinds`, `filterMistakes`, `filterChoices`, `filterFromQuery`, `openFromQuery`, `filterToQuery`, `engineStem`, `statusLabel`, `imageUrl`, `clampWindow`, `verdictOf`, `validationSummary`, `validateCatalogue`).
- `web/src/utils/errorsDoc.test.ts` (new, 141 lines) — copied verbatim from the brief.
- `web/public/docs/errors.json` (new, 76 lines) — the seed content, copied verbatim from the brief (owner-approved "Hidden inside faces" kind).

No changes were needed to any tsconfig: `web/tsconfig.json` already had `"resolveJsonModule": true`, and it already `include`s `src/**/*`, so the `../../public/docs/errors.json` import resolved with no edits.

## TDD: red, then green

Ran once with only the test file and no implementation/seed present (Step 2), from `D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/errors-page`:

`pnpm --dir web exec vitest run src/utils/errorsDoc.test.ts`

```
 FAIL  src/utils/errorsDoc.test.ts [ src/utils/errorsDoc.test.ts ]
Error: Cannot find module './errorsDoc' imported from D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/errors-page/web/src/utils/errorsDoc.test.ts

 Test Files  1 failed (1)
      Tests  no tests
   Start at  11:48:48
   Duration  916ms (worker 99%, environment 1%)
```

After implementing `errorsDoc.ts` and the seed `errors.json` (Step 3/4), same command:

```
 Test Files  1 passed (1)
      Tests  10 passed (10)
   Start at  11:54:40
   Duration  236ms (transform 67%, import 20%, tests 8%, worker 5%)
```

All 10 tests pass, including the last one (`the committed errors.json is valid`) that runs `validateCatalogue` against the real seed file. Before implementing, I traced the brief's exact rule order against the "names every problem in a bad catalogue, in a fixed order" test case by hand (all 10 expected messages, in order) to make sure `validateCatalogue`'s check order matched before running anything — it passed on the first implementation attempt.

## Type check

`pnpm --dir web run type-check` (`vue-tsc -b`) does **not** exit 0, but the failure is pre-existing and unrelated to this task:

```
src/three/Viewport.ts(332,34): error TS2339: Property 'side' does not exist on type 'Material | Material[]'.
  Property 'side' does not exist on type 'Material[]'.
src/three/Viewport.ts(333,34): error TS2339: Property 'needsUpdate' does not exist on type 'Material | Material[]'.
  Property 'needsUpdate' does not exist on type 'Material[]'.
src/three/Viewport.ts(360,21): error TS2345: Argument of type 'number | null' is not assignable to parameter of type 'number'.
  Type 'null' is not assignable to type 'number'.
```

Verified this is pre-existing, not something my files caused: I ran `git stash -u` to set the worktree back to a clean HEAD `c10721f` (no `errorsDoc.ts`/`errorsDoc.test.ts`/`errors.json` present at all) and reran `pnpm --dir web run type-check` — the exact same 3 errors, in the same file, same lines. Then `git stash pop` (plus `git stash drop` after confirming my files came back intact — the pop conflicted only on the regenerated `web/tsconfig.tsbuildinfo` build-cache file, not on any of my three files, which I verified had the same line counts as before: 331/141/76). Reran type-check again with my files present: identical 3 errors, nothing added. `web/src/three/Viewport.ts` is untouched by this task and outside its file list, so I left it alone rather than fixing it.

## Commit

```
eadef68763a84f5a687acc4e5d47651473c4b883
feat(web): the error catalogue's model, filters, verdict counts and content test
```

Staged by name (`git add web/src/utils/errorsDoc.ts web/src/utils/errorsDoc.test.ts web/public/docs/errors.json`), 3 files changed, 548 insertions. Message body and Co-Authored-By line match the brief, with the Co-Authored-By naming this session's model (Claude Sonnet 5) per the conversation's attribution instruction.

## Concerns

- `pnpm --dir web run type-check` exits 1 for the whole project because of 3 pre-existing errors in `web/src/three/Viewport.ts` (unrelated to the Errors page). This means the brief's Step 4 acceptance bullet ("the type check exits 0") does not literally hold repo-wide, though it is unaffected by this task's files. Someone should fix `Viewport.ts` separately (narrow the `Material | Material[]` union before reading `.side`/`.needsUpdate`, and null-check before the `number`-typed argument at line 360) — flagging as a candidate for its own task rather than fixing it here, since it is out of this task's file list and touches a file a peer worktree/session may be mid-edit on.
- One stray untracked build artifact, `web/tsconfig.tsbuildinfo`, was generated by running `vue-tsc -b` per the brief's own instructions. It was not staged or committed (commit only includes the 3 named files) and is harmless, but it is sitting in the worktree.
