# Task J1 report: question metadata and the wire format

Status: DONE. Worktree .claude/worktrees/J1, branch claude/J1, base d78ff24.
Skill used: uc-repair-rules (pre-flight: no guard, FixProfile, vertex, geometry or blocked operation is touched).

## Commit
- 8f04db1 feat(decide): questions carry qtype/subject; wire format and question_key
  (files: engine/decide/jev.py, engine/decide/wire.py, engine/tests/test_decide_wire.py)

## Red
Command: pytest engine/tests/test_decide_wire.py (before wire.py and the new fields existed)

    ImportError while importing test module '...\engine\tests\test_decide_wire.py'.
    engine\tests\test_decide_wire.py:3: in <module>
        from engine.decide import wire
    E   ImportError: cannot import name 'wire' from 'engine.decide'
    1 error in 0.29s

## Green
Command: pytest engine/tests/test_decide_wire.py engine/tests/test_decide_jev.py engine/tests/test_decide_pilot.py

    46 passed in 8.78s

The existing decide tests are unchanged and pass (the new dataclass fields default to "").

## Full engine suite (once, after the commit)
Command: ( cd <wt> && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )

    ........................................................................ [ 95%]
    ...................................................                      [100%]
    1202 passed, 1 xfailed in 849.96s (0:14:09)

## Implementation notes
- jev.py: `qtype`/`subject` added as the last two fields of NoulQ, ChoiceQ and ScoreQ. classify_group_names tags
  inv.building, inv.type, inv.floor and inv.duplicate (subject = the group name). classify_materials tags
  mat.category and mat.trim (subject = the material name).
- wire.py: created verbatim from the brief.

## Concerns
None. The full suite took about 14 minutes, so it was moved to the background. It finished with exit code 0.

## Fix round 1 (controller review: CHANGES)
Commit: see `git log` on claude/J1 (message "fix(decide): question_key keeps Choice criteria order; isinstance
dispatch; wire probabilities documented; more wire tests").

- Ruling 1: `question_key` encodes Choice criteria as ordered `[label, description]` pairs (order is now part of the
  key); Score criteria stay a list; `state` is still sorted. Pinned digest for
  `question_key({"x": 1}, ChoiceQ("which?", {"b": "bee", "a": None}))` is
  `c9f3ffef7452aa75463de0ec3e9077e50ccdf02557ebcbcc39baee8fd472de99`, computed once with an independent script.
- Ruling 2: docstrings on `decision_to_json`/`decision_from_json` state that probabilities are string-keyed on the
  wire; test pins `{0: .1, 2: .9}` -> `{"0": .1, "2": .9}`.
- 3: `question_to_json` dispatches with isinstance and raises `TypeError("unsupported question type <name>")`.
- 4: tests added for order sensitivity, key stability over the round trip, the pin, Noul vs Choice keys, bool answer
  staying a bool, criteria order kept, unknown kind -> ValueError, classifier count (6) and kinds.
- Red (new tests, before the fix): `3 failed, 12 passed` (test_key_depends_on_choice_criteria_order,
  test_key_is_pinned, test_unsupported_question_type_raises_type_error: KeyError <class 'str'>). The other new tests
  pin behaviour that already held, so they passed straight away.
- Green: the 3 decide test files: `56 passed in 3.10s`.
- Deferred, as instructed: `source`/`answer` defaults in `decision_from_json`.
