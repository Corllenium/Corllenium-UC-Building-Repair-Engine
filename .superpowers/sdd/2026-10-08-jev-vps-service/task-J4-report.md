# J4 report: the HTTP app and its roles

Branch `claude/J4` (base d02ce63). Files: `deploy/vps/decide/decide_service/app.py`, `deploy/vps/decide/tests/test_app.py`.
No change to logic/store/pgstore/settings, engine/**, or any existing test. No network, no real Jev, `.env` not opened.

## Red

`pytest deploy/vps/decide/tests/test_app.py` before `app.py` existed:

    ImportError while importing test module '...\deploy\vps\decide\tests\test_app.py'.
    E   ModuleNotFoundError: No module named 'decide_service.app'
    1 warning, 1 error in 1.15s

## Green

First run with `app.py`: `2 failed, 37 passed`. Both failures were my test data (two questions with identical
instructions share one dedupe key, since qtype/subject are not part of the key), not the app. Fixed the test
helper so each subject has its own instructions. Then the whole service suite:

    100 passed, 31 skipped, 1 warning in 4.88s

(31 skipped = the Postgres half, no PG env var.)

## Behaviour implemented (per the rulings)

- Roles from `X-Remote-User`: missing 401; wrong role 403 (role is checked before the body is validated).
- ask: pydantic `AskBody` (`state` object or string, `questions` an object of objects); each question is parsed with
  `wire.question_from_json`; a malformed one (bad kind, missing field, criteria wrong type) is 422 before logic runs.
  `ValueError` from `logic.answer` is 400 with the message ("at most 10 levels" tested).
- suggestions: `limit` clamped to 1..500 (default 100), `offset` to >= 0 (not errors); drops `key`, `state`, `state_json`.
  `counts` is `store.counts(type)`.
- review: `{"accept": true}` or `{"answer": v}`; neither sent is 422; `ValueError` 422; `KeyError` 404.
- reask: `PermissionError` 409 with "jev off" / "daily cap"; `KeyError` 404; `RuntimeError` 502
  `"jev call failed: <class name>"` (the text is whatever logic puts in the RuntimeError, which is the class name).
- import: `ImportItem` requires `state` (object or string) and `question` (object), else 422 for the whole request
  before logic; a missing answer/confidence is counted `invalid` by logic. Returns `{"added","skipped","invalid"}`.
- confirmed: `type` required (422 if absent). health: `{"ok","jev_enabled","tokens_today","daily_token_cap"}`.
- Leak test: fake client raising `RuntimeError("401 bad key <fake key>")`; the key is absent from the bodies of ask,
  reask (502), suggestions, health, confirmed and from `caplog.text` at DEBUG. The failing path is asserted to have run.

## Concerns (said plainly)

1. review and reask return the row without `key`, `state`, `state_json` too (the brief says "the row"; the ruling named
   only the listing). Done for consistency; easy to change if the review page needs them.
2. An unexpected exception in an endpoint (for example `make_decider` itself raising) is not caught: Starlette
   answers 500 with a fixed body, but the server log (not the response) would carry the traceback. The Jev call path
   is safe because `JevDecider` records only the class name. No generic handler was added (not in the brief).
3. Endpoints are sync (threadpool). `PostgresStore` has a lock, and `add_suggestion` is idempotent on key, but two
   simultaneous identical asks can both call Jev before either stores. Out of scope here.
4. `docs_url`/`openapi_url` are disabled on the app (no public schema page behind nginx). Not in the brief.
5. Not tested: the app against `PostgresStore` (the PG half skipped here).

---

# Fix round 1 (review: CHANGES)

Commits: 3b18e4f (items 1-6, 8, the Postgres fixture), 64d52fb (one test made order-independent, see finding A).

## Red (before the fix, memory half, new tests added to test_app.py)

    33 failed, 47 passed, 80 skipped
    FAILED test_health_shows_jev_off_and_the_cap          (no "model")
    FAILED test_ask_strict_question_shape_is_422[...]     (int qtype, int subject, list instructions, score criteria
                                                           str/empty/dict, choice criteria pairs/empty, description int,
                                                           noul with criteria / list criteria)
    FAILED test_import_strict_question_shape_is_422[...]  (the same plus choice criteria list, unknown kind)
    FAILED test_validation_errors_do_not_echo_the_input
    FAILED test_review_body_needs_exactly_one_of_accept_and_answer
    FAILED test_offset_is_capped_at_two_to_the_31
    FAILED test_502_text_is_whitelisted[bad key..., Error: more text, Error status=abc, empty]
    FAILED test_unexpected_error_is_500_internal_error_and_logs_only_the_class
    (already right, kept as regression tests: Noul review, Score review, key-leak through ask/import/review)

## Green

    no PG env var:                          141 passed, 111 skipped
    DECIDE_TEST_DATABASE_URL (55432):       252 passed

The Postgres run used the throwaway `decide-test-pg` (postgres:16-alpine, `--rm`, port 55432). It is stopped and gone
(`docker ps -a` shows no `decide-test-pg`). No other container was touched.

## Items

1. `QuestionIn` (kind Literal, StrictStr instructions/qtype/subject, criteria dict[StrictStr, StrictStr|None] | list[StrictStr] | None,
   model validator: noul none, choice non-empty dict, score non-empty list) is used by `AskBody` and `ImportItem`. 13 bad shapes,
   each tested on ask and on import (422, nothing stored, no Jev call). A valid noul/choice/score passes.
   Side effect: an import item with `question: {}` is now 422 for the whole request (before: counted `invalid`).
   Extra (not asked): validation 422 bodies now carry only loc/msg/type, never the `input` (default FastAPI echoes it).
2. Review: `accept: StrictBool | None`. `{"accept":"yes"}` 422; accept with answer 422 (both orders of true/false); neither 422;
   `{"accept": false}` alone 422.
3. `offset = min(max(0, offset), 2**31)`.
4. 502 text only when it fullmatches `[A-Za-z]+( status=\d+)?` or equals `no answer`; else `jev call failed`.
5. Catch-all: done as an `@app.middleware("http")`, not `exception_handler(Exception)`. Reason: Starlette's
   ServerErrorMiddleware re-raises after an `Exception` handler, so uvicorn would still log the traceback with the exception
   message (a DSN or key). The middleware returns 500 `{"detail":"internal error"}` and logs `unhandled <ClassName>` at ERROR
   (no exc_info). The test runs with `raise_server_exceptions=True` (the default) to prove nothing escapes. Deviation from the
   instruction's wording, same intent.
6. Over HTTP: Noul review (true/false ok; 0, 1, "true", "yes", null, 1.0 are 422); Score review (int ok; bool, 3, -1, 1.5, "1" are 422;
   1.0 stored as int 1); key-leak test through ask (client raises with the key), import (key as answer) and review (key as answer,
   in an object, in a list): the key is absent from every body and from caplog at DEBUG.
7. `backend` autouse fixture parametrizes every test in test_app.py: memory, and postgres when DECIDE_TEST_DATABASE_URL is set
   (refuses a URL not on :55432; drops and recreates schema `decide` per test).
8. Health adds `"model"`. `Settings` has no model field, so the value is `engine.decide.jev.MODEL` ("jev-latest"), the model the
   decider uses by default. If a configurable model is wanted, Settings needs a field (J2); not changed here.
9. Correction to the first report: a malformed JSON body (or a body that fails pydantic) is answered 422 before the role check
   is applied to it, because FastAPI parses the body while resolving dependencies. My first report and my test name
   `test_role_is_checked_before_the_body` implied the opposite: it only holds for a well-formed JSON body, where the dependency's
   HTTPException wins (tested). A malformed JSON body gets 422 even for the wrong user. Acceptable: nginx basic auth is in front,
   and the 422 body no longer echoes the input.

## Findings

A. (J3, pgstore) `suggestions.question` is jsonb, which does not keep object key order (it sorts by key length, then
   alphabetically). A Choice's option order is part of `question_key` and is what Jev is sent, but a stored question comes back
   reordered (measured: `{"glass","metal","wood"}` returns as `{"wood","glass","metal"}`). Effect: `reask` asks Jev with a different
   option order than the original ask; the answer is still a valid label. Not fixed here (store is out of scope). Fix options: store
   the question in a `json` column, or as ordered pairs. My reask test compares with the stored order so both stores pass.
B. The throwaway database run used password `test` on localhost:55432 only, as in the plan.

---

# Fix round 2: the Choice option order survives the store

Commit: see the last line of `git log` on claude/J4 ("fix(decide-service): J4 round 2 ...").

- `schema.sql`: `question json not null` (was jsonb). `answer`, `owner_answer`, `probabilities`, `state_json` stay jsonb.
  Nothing is deployed, so there is no migration; `ensure_schema` creates fresh tables.
- `pgstore.py`: the `question` parameter goes through `psycopg.types.json.Json` (not `Jsonb`). Needed as well as the column type:
  a `Jsonb` parameter is parsed by the server as jsonb and reorders before it reaches a json column.
- Checked pgstore for other uses of `question` with a jsonb operator or index: none. `question` appears only in the column lists
  of the insert, in `_UPDATABLE`, and in `select *`. The indexes are on (qtype, subject, reviewed_at) and (status, qtype).
- Tests (first, red on Postgres: 3 failed, 253 passed):
  - `test_store_contract.py::test_a_choice_question_keeps_its_option_order` (both stores): options `metal, wood, glass` come back in
    that order from `get`, `find_by_key` and `list`, and again after `update_suggestion(question=...)`. I used metal/wood/glass rather
    than the suggested wood/glass/metal because jsonb returns wood/glass/metal, so that order would not have failed under jsonb.
  - `test_app.py::test_reask_refreshes_...` reverted to assert the original answer `glass` (the fake answers the first option sent).
  - `test_app.py::test_reask_sends_the_options_in_the_original_order`: the question the fake client receives on reask has options
    `["metal", "wood", "glass"]`; the suggestions listing shows the same order.
- Green: on `decide-test-pg` (55432) 256 passed; without the PG env var 143 passed, 113 skipped. The container is stopped
  (`--rm`, gone from `docker ps -a`).
- Left alone: the plan file (`docs/superpowers/plans/2026-10-08-jev-vps-service.md` line 425) still shows `question jsonb`; docs are
  the controller's to update.
