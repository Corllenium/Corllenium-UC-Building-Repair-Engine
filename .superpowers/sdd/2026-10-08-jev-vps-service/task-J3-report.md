# J3 report: Postgres store and schema (branch claude/J3, base d68ba37)

Skill: uc-repair-rules read; no engine, guard, vertex or geometry code is touched (checks 1-5 do not apply).

## Commits
- f98e6f0 `test(decide-service): store contract tests, memory and Postgres halves (Postgres half red: no pgstore yet)`
- a345c12 `feat(decide-service): Postgres store, schema decide, contract tests shared with the memory store`

## Files
- `deploy/vps/decide/schema.sql` (schema `decide`; `suggestions` with `state_json jsonb not null`, `answer` and `owner_answer` jsonb; `calls`)
- `deploy/vps/decide/decide_service/pgstore.py` (`PostgresStore(dsn)`, `ensure_schema()`, `close()`)
- `deploy/vps/decide/tests/test_store_contract.py` (one fixture, memory and Postgres)
- `deploy/vps/decide/tests/test_pgstore.py` (Postgres specifics)

## Red (before pgstore.py existed; Postgres half only)
```
ModuleNotFoundError: No module named 'decide_service.pgstore'
ERROR ...test_store_contract.py::test_add_then_find_by_key[postgres]  ... (22 Postgres errors)
21 passed, 1 skipped, 22 errors in 0.51s     <- memory half: 21 passed, 1 skipped (duplicate-key test is Postgres only)
```

## Green (after implementing)
```
test_store_contract.py: 43 passed, 1 skipped in 4.70s
```

## Acceptance
Whole service suite, with DECIDE_TEST_DATABASE_URL (container decide-test-pg, port 55432):
```
83 passed, 1 skipped in 6.41s
```
Without it (the Postgres half skips):
```
57 passed, 27 skipped in 2.48s
```
J2's test_logic.py and test_settings.py pass in both runs, unchanged. Container stopped with `docker stop decide-test-pg` (output: `decide-test-pg`). Working tree clean afterwards.

## Behaviour notes
- Type round trip: contract test checks `type(row["answer"]) is type(value)` for str, True, False, 0, 3, 0.5, 2.5 on `get`, `find_by_key` and for `owner_answer` on `get`, `owner_answer()` and `confirmed()`. Explicit bool and int test too. Passes on both stores.
- `state_json` and `state` (a 2,000-character text) are both kept; `probabilities` is jsonb.
- Rows come back with `reviewed_at` and `created_at` as ISO strings, the same shape as MemoryStore (Postgres stores timestamptz).
- `list(q=...)` matches a case-insensitive substring of the subject OR the state text, because MemoryStore does that (the brief says subject only). It uses `strpos(lower(..), lower(%s))`, so `%` and `_` are plain characters (tested).
- `update_suggestion` raises KeyError for an unknown id and ValueError for a column outside an allow-list. Column names go through `psycopg.sql.Identifier`; all values are parameters.
- `add_call` maps the decider's entry shape (`latency_s`, `error`) to the schema columns (`latency_ms`, `error_class`); `latency_ms` and `error_class` are used if given.
- `tokens_today` compares the UTC date of `at` with the database's UTC date.
- DSN secrecy: `repr` is `PostgresStore()`; a failed connect raises `ConnectionError("... (<ExceptionClass>)")` with no cause or context (tested with a password in the DSN).
- The test fixture refuses a URL that does not contain `:55432/`, because it drops the schema `decide`.

## Concerns
- MemoryStore does not enforce unique keys; PostgresStore does (a `unique` key). The duplicate-key contract test therefore skips on memory. Logic dedupes before adding, so nothing depends on it.
- A single connection with a lock, reconnecting only when the connection is closed or broken (never a retry of a write). Fine for a small service; a pool would be a later change if the service gets threads under load.
- `psycopg` (3.3.6 in the venv) is not yet listed in any requirements file for the service image; the deploy job needs `psycopg[binary]`.
- `ensure_schema` has no advisory lock; two processes starting at once on an empty database could race on `create table`. Not an issue with one service container.
- `schema.sql` creates `state_json` in the create statement only; no migration for a database made from an older draft (none exists).

## Fix round 1 (J3 review)
Commit: see `git log` on claude/J3 ("fix(decide-service): J3 review round 1 ...").

Red first (with the test database): 6 failed, 85 passed.
- `test_q_matches_the_subject_only_in_any_case` failed on memory and Postgres (a hit only in `state` returned the row).
- `test_a_duplicate_key_returns_the_existing_id_and_leaves_one_row` failed on memory (second row added) and Postgres (`UniqueViolation`).
- `test_one_retry_after_the_server_drops_the_connection` (pg_terminate_backend) and `test_never_more_than_one_retry` failed (no retry yet).
- The closed-connection reconnect test and the UTC-timestamp contract test passed before the change (the existing `closed` check already reconnects; the container's session zone is UTC); kept as regression tests.

Changes:
1. `q` matches the subject only, in both stores (`strpos(lower(subject), lower(%s)) > 0`; MemoryStore in store.py).
2. `add_suggestion`: `insert ... on conflict (key) do nothing returning id`, then select by key; MemoryStore returns the existing id. The skipping duplicate test is replaced by one that runs on both stores.
3. `_fetch` and `ensure_schema`: one reconnect and one retry on `psycopg.OperationalError`, never more (tests: connection closed directly, backend terminated, a fake connection counting exactly 2 attempts).
4. `_out` returns `.astimezone(utc).isoformat()`; contract test checks the "+00:00" ending on both stores.
5. Unused `REVIEWED` removed from pgstore.py.

Green: with DECIDE_TEST_DATABASE_URL, `91 passed in 5.52s`; without it, `61 passed, 30 skipped in 2.45s` (Postgres half skipped); commit 8f54f2a. Container decide-test-pg stopped.

## Fix round 2 (re-review item)
Added `test_timestamps_are_utc_even_when_the_session_zone_is_not` (Postgres only): sets `time zone 'Asia/Manila'` on the store's connection, adds and reviews a suggestion, asserts `created_at` and `reviewed_at` end in "+00:00".

Red, with `_out` temporarily using plain `.isoformat()`:
```
E       AssertionError: 2026-10-08T17:15:17.066742+08:00
1 failed, 91 deselected in 0.46s
```
Green, `_out` restored (git diff shows only the test file changed): `92 passed in 6.27s` with the test database; without it `61 passed, 31 skipped`; commit 4a801c3. Container decide-test-pg stopped.
