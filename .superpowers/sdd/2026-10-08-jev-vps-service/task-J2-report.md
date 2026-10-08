# J2 report: service core (settings, store protocol, memory store, logic)

Worktree `.claude/worktrees/J2`, branch `claude/J2`, base a3a26b1. Status: DONE.
Skill checklist `uc-repair-rules` read: no geometry, guard, vertex or blocked operation is touched (service code only, no `engine/**` change).

## Commit
- 126032a `feat(decide-service): store protocol, memory store, answer order owner > stored > Jev`
  Files: `deploy/vps/decide/decide_service/{__init__,settings,store,logic}.py`, `deploy/vps/decide/tests/{__init__,test_logic,test_settings}.py`.
  One commit for the one item; the tests were written and run red first.

## Red run (before the implementation)
```
deploy\vps\decide\tests\test_logic.py:7: in <module>
    from decide_service import logic
E   ImportError: cannot import name 'logic' from 'decide_service' (...\deploy\vps\decide\decide_service\__init__.py)
ERROR deploy/vps/decide/tests/test_logic.py
1 error in 0.44s
```
(ImportError rather than ModuleNotFoundError, because the empty package `__init__.py` was created first.)

## Green run
```
test_logic.py:  11 passed in 0.10s
deploy/vps/decide/tests (test_logic + test_settings): 13 passed in 0.08s
```
The 11 tests are the brief's tests 1-11 in order. `test_settings.py` (2 tests) is my addition: the defaults keep Jev off, `from_env` parsing, and the database URL is not in `repr`.

## Decide engine tests (nothing broke)
`PYTHONPATH="$PWD" python -m pytest engine/tests/test_decide_wire.py test_decide_jev.py test_decide_pilot.py` -> `56 passed in 3.17s`.

## Notes and concerns
- `Settings` fields all have defaults (`engine_user="uc-engine"`, `database_url=""`), so `Settings(jev_enabled=...)` works. `from_env(env=None)` takes an optional mapping for tests. `Settings.__repr__` hides `database_url`.
- `Settings.from_env` does not read `DECIDE_ENGINE_USER`; the brief lists no such variable.
- `MemoryStore` orders reviews by `(reviewed_at, id)`, so two reviews in the same microsecond resolve to the later one. `tokens_today` treats `None` tokens (a failed call) as 0.
- A Jev call that fails (`source == "error"`) stores no suggestion and returns `suggestion_id: None`. The call is recorded with `ok: False`. Only the class name goes into the error text (the engine's `_error_text`), and the key-leak test passes.
- `reask` parses the stored `state` text with `json.loads`. If a state longer than 2,000 characters was cut at storage, `reask` would raise `JSONDecodeError`. The brief already notes this limit; the material and group states are about 300 characters. J3 may want to turn that error into a clean 4xx.
- `reask` with a failed Jev call leaves the row unchanged and returns it.
- Cached rows come back with their `probabilities` as stored (string keys possible after Postgres JSON); not converted, as instructed.
- Git printed CRLF warnings on add (autocrlf); no content issue.

## Fix round 1 (review CHANGES)

Commit e1e9cc0 (one commit for items 1-9; tests written first, red run: 13 failed, 20 passed; green: 33 passed).
Service tests: `deploy/vps/decide/tests` 33 passed. Decide engine tests (wire, jev, pilot): 56 passed.

Per item, with its test in `tests/test_logic.py`:
1. `todo` is grouped by key: one Jev question per key, one stored row, the answer and `suggestion_id` go to every qid. Test `test_same_question_twice_in_one_call_asks_once`.
2. Fresh answers get `accepted = confidence >= cfg.min_confidence` (dataclasses.replace); cached rows already used cfg. Test `test_accepted_follows_the_service_min_confidence_fresh_and_cached` (cfg 0.99).
3. A cached row with status accepted/changed returns `owner_answer`, source `owner`, accepted True, the row id. Test with an empty qtype/subject.
4. `_check_answer`: Noul `type(v) is bool`; Choice a str label; Score an int in range, a whole float stored as int, never a bool. `review(accept=True)` on a Score stores `round(answer)`. Tests: 9 refused cases (parametrised: Noul 1, 0.0, "yes"; Score True, 3 out of range, 1.5, "1"; Choice "plastic", 1) plus accepted-2.6-stores-3.
5. `reask` updates only answer, confidence, probabilities, model, source; status/owner_answer/reviewed_* stay. The old J2 test (reask sets status back to pending, from the original brief) was changed to match this ruling. New test `test_reask_keeps_the_owners_confirmation`.
6. `Settings.batch = 20`. `todo` goes in chunks of `cfg.batch`; `tokens_today()` is checked before each chunk; later chunks come back none / "daily cap". `make_decider` is built lazily, once. Test `test_daily_cap_is_checked_before_each_batch`: **I used cap 100 with batch 1**, not cap 150: the fake call costs 107 tokens, and 107 < 150 would let the second chunk through. With cap 100 the first chunk is asked and the second is refused.
7. Rows carry `state_json` (the full dict) next to the display `state` (cut to 2,000). `reask` uses `state_json` (falls back to `json.loads(state)` for a row without it). A reask whose call does not give a Jev answer raises `RuntimeError(<error class text>)`, or `"no answer"` if there is none. Tests with a 3,000-character state, and a failing re-ask with the fake key in the client's message.
8. `import_items` normalises a str state to `{"text": ...}`, validates the answer with the same strict check (a Score's fractional pilot level is rounded first, as accept does; the stored answer stays as given), and counts bad or malformed items (missing keys, wrong types) under `invalid`. Returns `{"added", "skipped", "invalid"}`. Test: an imported str-state question is found by a later `answer`.
9. Added: `test_latest_review_wins_across_two_rows` (explicit `reviewed_at`), `test_empty_qtype_or_subject_skips_the_owner_lookup` (spy store), `test_jev_off_never_builds_a_decider` (also for the daily cap).

**For J3's schema:** the suggestions table needs a `state_json jsonb` column (the full canonical state) next to `state text`. Rows from `add_suggestion` carry the key `state_json`.

Other notes: `review` without `accept` is "accepted" when the owner's value equals Jev's (after Score rounding), otherwise "changed" (unchanged rule). The one-line summary of the round: 33 service tests + 56 engine decide tests green.
