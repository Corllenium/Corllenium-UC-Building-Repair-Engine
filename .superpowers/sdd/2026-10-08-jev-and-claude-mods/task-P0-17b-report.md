# P0-17b report — Jev floor question as a Choice

Branch `claude/P0-17b` (worktree `.claude/worktrees/P0-17b`), from b1c66a2. Status: DONE.

## Commits
- `def55a5` feat(decide): refuse a Score over 10 levels or a Choice over 255 options before any network call (item 2)
- `8c2c6d9` fix(decide): ask the floor as a 16-option Choice (keys 0..15), answer and probabilities as ints (items 1, 3)

## Red runs (before the implementation)
Command: `pytest engine/tests/test_decide_jev.py engine/tests/test_decide_pilot.py -q -p no:cacheprovider`

```
E   AssertionError: assert (None == 0)  ... Decision(answer=None, ..., source='error', accepted=False, error='AttributeError')
        (floor_answer_maps_to_int test: the old ScoreQ path read `.score` off a Choice answer)
E   AttributeError: module 'engine.decide.jev' has no attribute 'MAX_SCORE_LEVELS'
E   Failed: DID NOT RAISE ValueError       (Choice with 256 options went to the client)
FAILED test_classify_group_names_asks_four_typed_questions_per_row   (floor is a ScoreQ, not a ChoiceQ)
FAILED test_classify_group_names_floor_answer_maps_to_int_and_an_unmappable_one_is_not_accepted
FAILED test_the_adapter_refuses_a_score_over_ten_levels_before_calling_the_client
FAILED test_the_adapter_refuses_a_choice_over_255_options_before_calling_the_client
4 failed, 35 passed in 9.19s
```

## Green runs
- After item 2 (limits only): `38 passed in 3.81s`.
- After item 1 (floor Choice) plus the pilot test: `40 passed in 2.63s`.

## Full engine suite (`pytest engine/tests -q -p no:cacheprovider`, once)
```
....................................................................x... [ 84%]
........................................................................ [ 90%]
........................................................................ [ 96%]
.......................................                                  [100%]
1190 passed, 1 xfailed in 817.40s (0:13:37)
```

## What changed
- `engine/decide/jev.py`
  - `MAX_SCORE_LEVELS = 10` and `MAX_CHOICE_OPTIONS = 255`, with a comment citing the API message
    (`400 {'detail': 'Too many score levels. Must have at most 10 levels.'}`).
  - `_SdkAdapter._check_limits` runs before the SDK import and before the client call; it raises
    `ValueError` naming the limit, the question id (truncated to 60 chars) and the count.
  - `classify_group_names`: the floor question is a `ChoiceQ` with 16 options keyed `"0"`..`"15"`
    (`"0"` is "no floor / ground level", `"N"` is "floor N"). New `_floor_to_int` turns the answer and the
    probability keys into ints 0-15.
- `engine/decide/pilot.py`: NOT changed. Its floor accuracy is `int(round(a)) == t`, which accepts an int.

## Tests
New, in `engine/tests/test_decide_jev.py`:
- the adapter refuses a Score over 10 levels, and a Choice over 255 options, with `FakeClient.calls == []`;
- the adapter lets 10 levels and 255 options through (needs the SDK; skipped without it);
- `classify_group_names` floor answer is the int 0 (accepted) or 5, with int probability keys;
- an unmappable floor key (`"seventh"`) becomes an error Decision, never accepted, and the key text is not
  put into `error`.

New, in `engine/tests/test_decide_pilot.py`: `test_the_floor_choice_answer_scores_as_an_int_against_the_unit_level`
(floor accuracy 1 of 2 on a canned response, coverage 1.0, all 24 group decisions from "jev").

Existing tests changed (only because the floor question's type changed):
- `test_decide_jev.py::_group_answers` and `test_classify_group_names_asks_four_typed_questions_per_row`:
  the floor answer is now a Choice `"5"` (not `_score(4.8)`), the assertion is `ChoiceQ` with 16 keys, and
  the answer is expected as int 5 (was float 4.8).
- `test_decide_pilot.py::_answering_client`: a `:floor` Choice question is now answered with `"5"`; before it
  would have received the type label, which is not a floor key.
No other existing test was edited. `engine/guard/**` and `FixProfile` untouched.

## Unsure / notes
- The 255-option cap comes from the brief; I did not measure it against the real API (no network allowed).
  The code comment says so. The 10-level cap is the measured one.
- A floor answer that is not a key 0-15 is turned into an `error` decision (`UnmappedFloorKey`) instead of
  raising; this is my design choice, not in the brief.
- The full suite took 13m37s; no test touched the network, the real `.env`, the database or the containers.
- Not done, by instruction: no real pilot run. Whether the real API now accepts the 16-option Choice is
  indicated by the measured earlier result (building Choice with 10 options passed) but is unverified for 16.

## Review fix (two minors, one commit)
1. The limit check moved out of `_SdkAdapter` into the module function `check_question_limits`; `_SdkAdapter.system_one`
   still calls it, and `JevDecider.ask` now calls it first, before batching and outside `_call`'s try, so the
   ValueError and its message reach the caller. Test `test_ask_raises_the_limit_error_to_the_caller_before_any_call`
   (11-level Score -> "at most 10 levels"; 256-option Choice -> "at most 255 options"; fake client and `decider.calls`
   empty). Red first: `1 failed, 29 passed` (DID NOT RAISE ValueError).
2. The comment on `MAX_CHOICE_OPTIONS` now says: on 2026-10-08 the controller's real pilot run sent the 16-option floor
   Choice and all 57 calls succeeded, 0 failed (jev-1.13.0); the 255 cap stays marked as not measured.
   (This supersedes my earlier "unverified for 16" note above.)
Green, the two covering files only: `41 passed in 4.29s`.
