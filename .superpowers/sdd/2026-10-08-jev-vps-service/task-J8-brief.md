## Global Constraints

- AGENTS.md binds every task: test first; commit after every item; stage files by name; never a bare `cd`; Python is
  `"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"`, run from the worktree root in a subshell with
  `PYTHONPATH` set.
- **Branches:** the integration branch `feat/jev-vps` comes from `feat-dashboard` (8b22e75 or later). Each job is
  `claude/<id>` in `.claude/worktrees/<id>` from `feat/jev-vps`. The controller merges with `--no-ff` after a review,
  and asks the repair-engine session before any merge into `feat-dashboard`.
- **Jev is off:** default `DECIDE_JEV_ENABLED=false`. No task makes a real Jev call. Every test uses a fake client.
- **Secrets:** the TypeSafe key is read from the environment only (service). The `uc-engine` password is
  `UC_DECIDE_PASSWORD`, from the environment or else only that one line of the git-ignored repo-root `.env`
  (engine). Neither is ever printed, logged, put in a `repr` or exception text, or committed. Agents never open `.env*`.
- **Never touch:** the live containers `fixer-api`, `fixer-web`, `fixer-db`; the database `fixer`; the VPS. Every test
  database is a throwaway container named `decide-test-pg` on port 55432.
- **The pipeline never waits:** `RemoteDecider` has a 10 s timeout and no retries. Any failure gives `none` / `error`
  decisions, never accepted.
- **Only text leaves the PC:** names, texture file names, categories, small numbers.
- **Limits:** a Score has at most 10 levels and a Choice at most 255 options (`check_question_limits`). The daily cap is
  1,000,000 tokens (`DECIDE_DAILY_TOKEN_CAP`).
- **Logins:** the engine login is `uc-engine`. The owner logins come from `DECIDE_OWNER_USERS` (default `gab`). The
  user name arrives in `X-Remote-User`, set by nginx.
- **Out of scope:** the actual VPS deploy (the controller does it with the owner's OK at that moment), switching Jev
  on, P1-D2, the `repair.next_step` question.


### Task J8: the /jev page

**Files:**
- Create: `web/src/api/decide.ts`, `web/src/utils/jevReview.ts`, `web/src/views/JevView.vue`
- Modify: `web/src/router.ts`, adding `{ path: '/jev', name: 'jev', component: JevView }`
- Test: `web/src/api/decide.test.ts`, `web/src/utils/jevReview.test.ts`

**Interfaces:**
- Consumes: the endpoints of J4.
- Produces:
  - `fetchSuggestions(params) -> Promise<{items, counts}>`, `reviewSuggestion(id, body)`, `reaskSuggestion(id)`,
    `fetchHealth()`. All throw the existing `ApiError` from `./client`.
  - `TABS`, with `{key, label, qtypes, available}` for Materials, Campus map, Next repair step, Review order and
    Fix tie-breaks.
  - `filterRows(rows, {status, minConf, text})`.
  - `topAlternatives(row, n = 2)`.
  - `acceptAllSelection(rows, minConf) -> number[]`, the pending ids at or above `minConf`.
  - `optionLabels(question) -> string[]`.

- [ ] **Step 1: Write the failing Vitest tests**, mocking `globalThis.fetch` as in `client.test.ts`:
  - `reviewSuggestion` posts JSON to `/api/decide/review/7` and turns a 422 into `ApiError`;
  - `fetchHealth` reads `jev_enabled`;
  - `filterRows` filters by status, minimum confidence and a case-insensitive subject search;
  - `topAlternatives` leaves out the chosen answer and sorts by probability;
  - `acceptAllSelection` takes only `pending` rows at or above the threshold;
  - `optionLabels` gives Noul `["yes", "no"]`, the Choice keys, and the Score levels;
  - `TABS` has Materials and Campus map available, the other three not.
- [ ] **Step 2: Run them and see them fail:** `( cd "<wt>/web" && npx vitest run src/api/decide.test.ts src/utils/jevReview.test.ts )`.
- [ ] **Step 3: Implement** the two modules, then `JevView.vue`:
  - the tabs; a banner "Jev is off until the repair engine is ready" when `health.jev_enabled` is false;
  - the counts; the filters;
  - rows with the texture thumbnail at `/api/assets/texture/<name>`, if the dashboard API serves one, otherwise no
    image; check `api/routers` and use only an existing route;
  - the confidence bar and the top-2 alternatives;
  - Accept, and Change (a `<select>` of `optionLabels`);
  - "Accept all shown ≥ X", using `window.confirm` with the count;
  - on a fetch failure with status 404 or 502, "Jev service runs on the VPS".
- [ ] **Step 4: Run the tests and the build** (`npx vitest run` and `npx vite build`). Expected: the tests pass and
  the build succeeds.
- [ ] **Step 5: Commit:** `feat(web): /jev review page for Jev suggestions (accept, change, accept-all with confirm)`.

---

