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


### Task J3: the Postgres store and its schema

**Files:**
- Create: `deploy/vps/decide/schema.sql`, `deploy/vps/decide/decide_service/pgstore.py`
- Test: `deploy/vps/decide/tests/test_store_contract.py`

**Interfaces:**
- Consumes: the `Store` protocol and `MemoryStore` (J2).
- Produces: `PostgresStore(dsn: str)`, which implements every `Store` method. `PostgresStore.ensure_schema()` runs
  `schema.sql`, which is idempotent.

- [ ] **Step 1: Write `schema.sql`:**

```sql
create schema if not exists decide;
create table if not exists decide.suggestions (
  id bigserial primary key,
  qtype text not null default '', subject text not null default '',
  key char(64) not null unique, state text not null, question jsonb not null,
  answer jsonb, confidence double precision not null default 0, probabilities jsonb not null default '{}',
  model text not null default '', source text not null,
  status text not null default 'pending' check (status in ('pending','accepted','changed')),
  owner_answer jsonb, reviewed_at timestamptz, reviewed_by text,
  created_at timestamptz not null default now());
create index if not exists suggestions_owner on decide.suggestions (qtype, subject, reviewed_at desc);
create index if not exists suggestions_status on decide.suggestions (status, qtype);
create table if not exists decide.calls (
  id bigserial primary key, at timestamptz not null default now(), questions int not null,
  latency_ms int, input_tokens int, output_tokens int, model text, ok boolean not null, error_class text);
```

- [ ] **Step 2: Write the contract tests.** One parametrized fixture yields a `MemoryStore` and, when
  `DECIDE_TEST_DATABASE_URL` is set, a fresh `PostgresStore`. The fixture drops and recreates the schema `decide`
  before each test. The tests, run against both stores:
  - add, then `find_by_key`;
  - `update_suggestion`, then `get`;
  - `owner_answer` returns the latest review;
  - `confirmed` returns the latest per subject;
  - `list` filters by status, qtype, `min_conf` and `q` (a case-insensitive substring of the subject);
  - `counts`;
  - `tokens_today` counts only today's calls;
  - an answer of each JSON type (str, bool, int, float) comes back with its type.
- [ ] **Step 3: Start the throwaway database and see the Postgres half fail:**
  - `docker run --rm -d --name decide-test-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16-alpine`
  - then `( cd "<wt>" && DECIDE_TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres PYTHONPATH="$PWD;$PWD/deploy/vps/decide" "$PY" -m pytest deploy/vps/decide/tests/test_store_contract.py -q -p no:cacheprovider )`
  - Expected: the memory half passes; the Postgres half fails with an ImportError on `pgstore`.
- [ ] **Step 4: Implement `PostgresStore`** with psycopg 3 (`psycopg.connect(dsn, autocommit=True)`, a
  `dict_row` row factory). JSON columns go in through `psycopg.types.json.Jsonb`. Every query has parameters only,
  never f-strings. Run until both halves pass.
- [ ] **Step 5: Stop the database** (`docker stop decide-test-pg`) and **commit**:
  `feat(decide-service): Postgres store, schema decide, contract tests shared with the memory store`.

---

