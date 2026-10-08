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


### Task J6: RemoteDecider and decide-pull (engine)

**Files:**
- Create: `engine/decide/remote.py`
- Modify: `engine/cli.py`, adding the subcommand `decide-pull`
- Test: `engine/tests/test_decide_remote.py`

**Interfaces:**
- Consumes: `wire` (J1); the endpoints of J4.
- Produces:
  - `RemoteDecider(url: str, user: str = "uc-engine", password: str | None = None, timeout: float = 10.0, *,
    env_file=None)`. It has `.available`, `.ask(state, questions) -> dict[str, Decision]`, `.calls` (one entry per
    HTTP call: `ok`, `status`, `latency_s`, `error`) and a `repr` without the password. The password comes from
    `UC_DECIDE_PASSWORD`, else that one line of the `.env` (reusing `jev.read_env_key`'s pattern, generalized to a
    variable name).
  - `pull_confirmed(url, qtype, out_dir, ...) -> Path` writes `<out_dir>/<qtype>.json` as `{subject: answer}`.
  - CLI: `decide-pull --url URL --type QTYPE [--out data/decide/confirmed] [--env-file PATH]`.

- [ ] **Step 1: Write the failing tests**, against a local `http.server` in a thread that records each request and
  answers canned JSON:
  - `ask` sends `questions` through `wire.question_to_json`, with Basic auth for `uc-engine`, and maps the answers back
    to `Decision`;
  - a server that sleeps past `timeout` gives every decision `source == "none"`, `accepted is False`, `error` set,
    and the call takes no longer than the timeout plus 1 s;
  - a 401 or a 500 gives `source == "error"` with `error == "HTTP 401"` or `"HTTP 500"`, and no retries (the server
    saw exactly 1 request);
  - with no password, `available is False` and `ask` returns `none` without any request;
  - the password is absent from `repr`, from captured logs at DEBUG and from exception text;
  - `pull_confirmed` writes the file;
  - `classify_materials(items, RemoteDecider(...))` works unchanged.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement it with `urllib.request`.** No new dependency. Build the Basic header from
  `base64.b64encode(f"{user}:{password}".encode())`. Catch every exception per call; the error text is the class name
  or `HTTP <status>` only.
- [ ] **Step 4: Run the decide tests until all pass:** `test_decide_remote.py`, `test_decide_wire.py`,
  `test_decide_jev.py`, `test_decide_pilot.py`.
- [ ] **Step 5: Commit:** `feat(decide): RemoteDecider (same ask as JevDecider, never waits) and decide-pull`.

---

