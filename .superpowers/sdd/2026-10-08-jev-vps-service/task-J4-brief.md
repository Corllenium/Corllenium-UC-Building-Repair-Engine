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


### Task J4: the HTTP app and its roles

**Files:**
- Create: `deploy/vps/decide/decide_service/app.py`
- Test: `deploy/vps/decide/tests/test_app.py`

**Interfaces:**
- Consumes: `logic`, `Settings`, `Store` (J2); `wire` (J1).
- Produces: `create_app(store, cfg, make_decider) -> FastAPI`, with these endpoints. Role errors are 403; a missing
  `X-Remote-User` is 401.

| Endpoint | Role | Body / query | Answer |
|---|---|---|---|
| `POST /api/decide/ask` | engine | `{"state": {...}, "questions": {qid: question_json}}` | `{"answers": {qid: decision_json}}`; a limit breach is 400 with the message |
| `GET /api/decide/suggestions` | owner | `status, type, min_conf, q, limit, offset` | `{"items": [...], "counts": {...}}`, without the `key` and `state` columns |
| `POST /api/decide/review/{id}` | owner | `{"accept": true}` or `{"answer": value}` | the row; 422 if not an option; 404 if unknown |
| `POST /api/decide/reask/{id}` | owner | none | the row; 409 `{"detail": "jev off"}` or `"daily cap"` |
| `GET /api/decide/confirmed` | either | `type` (required) | `{"type": t, "answers": {subject: answer}}` |
| `POST /api/decide/import` | engine | `{"items": [{state, question, answer, confidence, probabilities?, model?}]}` | `{"added", "skipped"}` |
| `GET /api/decide/health` | either | none | `{"ok": true, "jev_enabled", "tokens_today", "daily_token_cap"}` |

- [ ] **Step 1: Write the failing tests** with `fastapi.testclient.TestClient(create_app(MemoryStore(),
  Settings(jev_enabled=False, ...), make_decider))`. Cover:
  - each endpoint's happy path;
  - `uc-engine` gets 403 on review, reask and suggestions;
  - `gab` gets 403 on ask and import;
  - no header gives 401;
  - an 11-level Score on ask gives 400 with "at most 10 levels";
  - reask with Jev off gives 409 "jev off";
  - `health` shows `jev_enabled: false`;
  - a fake decider whose client raises with a fake key: the key is absent from every response body and from
    caplog at DEBUG.
- [ ] **Step 2: Run them and see them fail** (ImportError).
- [ ] **Step 3: Implement `app.py`.** The role check is one dependency:

```python
def _user(request: Request) -> str:
    user = request.headers.get("X-Remote-User", "")
    if not user:
        raise HTTPException(401, "no user")
    return user


def _role(cfg):
    def owner(user: str = Depends(_user)) -> str:
        if user not in cfg.owner_users:
            raise HTTPException(403, "owner only")
        return user

    def engine(user: str = Depends(_user)) -> str:
        if user != cfg.engine_user:
            raise HTTPException(403, "engine only")
        return user

    def either(user: str = Depends(_user)) -> str:
        if user != cfg.engine_user and user not in cfg.owner_users:
            raise HTTPException(403, "unknown user")
        return user
    return owner, engine, either
```

  `ask` turns each `question_json` into a question with `wire.question_from_json`, then calls `logic.answer`; a
  `ValueError` from it becomes 400. The suggestions listing drops the `key` and `state` columns.
- [ ] **Step 4: Run the tests until all pass.**
- [ ] **Step 5: Commit:** `feat(decide-service): HTTP endpoints with engine/owner roles from X-Remote-User`.

---

