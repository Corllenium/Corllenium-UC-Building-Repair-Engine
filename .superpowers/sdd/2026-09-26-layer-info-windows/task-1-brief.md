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

