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


### Task J1: question metadata and the wire format

**Files:**
- Modify: `engine/decide/jev.py`: `NoulQ`, `ChoiceQ`, `ScoreQ`, `classify_group_names`, `classify_materials`
- Create: `engine/decide/wire.py`
- Test: `engine/tests/test_decide_wire.py`

**Interfaces:**
- Produces:
  - `NoulQ(instructions, qtype="", subject="")`, `ChoiceQ(instructions, criteria, qtype="", subject="")`,
    `ScoreQ(instructions, criteria, qtype="", subject="")`.
  - `wire.question_to_json(q) -> dict` gives `{"kind": "noul"|"choice"|"score", "instructions", "criteria",
    "qtype", "subject"}`; `wire.question_from_json(d) -> NoulQ|ChoiceQ|ScoreQ` reverses it.
  - `wire.question_key(state: dict, q) -> str`: sha256 hex of the canonical JSON of `{"state", "kind",
    "instructions", "criteria"}`. qtype and subject are not part of it.
  - `wire.decision_to_json(d, suggestion_id=None) -> dict`, `wire.decision_from_json(d) -> Decision`.
  - `wire.options_of(q) -> list`: `[True, False]` for a Noul, the labels for a Choice, `[0..n-1]` for a Score.
- qtypes used: `inv.building`, `inv.type`, `inv.floor`, `inv.duplicate` (subject = the group name);
  `mat.category`, `mat.trim` (subject = the material name).

- [ ] **Step 1: Write the failing tests** in `engine/tests/test_decide_wire.py`:

```python
import json
from engine.decide.jev import ChoiceQ, Decision, NoulQ, ScoreQ, classify_group_names, classify_materials
from engine.decide import wire


def test_question_round_trip_keeps_kind_criteria_and_metadata():
    for q in (NoulQ("is it?", qtype="inv.duplicate", subject="CHTM_5th"),
              ChoiceQ("which?", {"a": None, "b": "bee"}, qtype="mat.category", subject="M1"),
              ScoreQ("how?", ["low", "high"])):
        back = wire.question_from_json(json.loads(json.dumps(wire.question_to_json(q))))
        assert back == q


def test_question_key_ignores_metadata_but_not_text_or_state():
    a = ChoiceQ("which?", {"a": None}, qtype="t1", subject="s1")
    b = ChoiceQ("which?", {"a": None}, qtype="t2", subject="s2")
    assert wire.question_key({"x": 1}, a) == wire.question_key({"x": 1}, b)
    assert wire.question_key({"x": 1}, a) != wire.question_key({"x": 2}, a)
    assert wire.question_key({"x": 1}, a) != wire.question_key({"x": 1}, ChoiceQ("which?!", {"a": None}))
    assert len(wire.question_key({}, a)) == 64


def test_decision_round_trip():
    d = Decision("stone", 0.92, {"stone": 0.92, "metal": 0.08}, "jev", True)
    j = wire.decision_to_json(d, suggestion_id=7)
    assert j["suggestion_id"] == 7
    assert wire.decision_from_json(j) == d


def test_options_of():
    assert wire.options_of(NoulQ("q")) == [True, False]
    assert wire.options_of(ChoiceQ("q", {"a": None, "b": None})) == ["a", "b"]
    assert wire.options_of(ScoreQ("q", ["x", "y", "z"])) == [0, 1, 2]


class _Capture:
    def __init__(self):
        self.questions = {}

    def ask(self, state, questions):
        self.questions.update(questions)
        return {qid: Decision(None, 0.0, {}, "none", False) for qid in questions}


def test_classifiers_tag_every_question_with_qtype_and_subject():
    cap = _Capture()
    classify_group_names([{"name": "CHTM_5th", "tris": 1, "z_min": 0, "z_max": 1, "footprint_building": "CHTM"}], cap)
    classify_materials([{"name": "M1", "texture": "m1.png", "kd": [1, 1, 1]}], cap)
    tags = {(q.qtype, q.subject) for q in cap.questions.values()}
    assert tags == {("inv.building", "CHTM_5th"), ("inv.type", "CHTM_5th"), ("inv.floor", "CHTM_5th"),
                    ("inv.duplicate", "CHTM_5th"), ("mat.category", "M1"), ("mat.trim", "M1")}
```

- [ ] **Step 2: Run them and see them fail:**
  `( cd "<wt>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_decide_wire.py -q -p no:cacheprovider )`.
  Expected: an ImportError on `engine.decide.wire`, or a TypeError on the unknown `qtype` argument.

- [ ] **Step 3: Implement.**
  - In `jev.py`, add `qtype: str = ""` and `subject: str = ""` as the last fields of the three frozen dataclasses.
  - In `classify_group_names` and `classify_materials`, pass `qtype=`/`subject=` to every question built, using the
    qtypes listed above.
  - Create `wire.py`:

```python
"""JSON form of questions and decisions, shared by the engine, RemoteDecider and the VPS service."""
from __future__ import annotations

import hashlib
import json

from engine.decide.jev import ChoiceQ, Decision, NoulQ, ScoreQ

_KIND = {NoulQ: "noul", ChoiceQ: "choice", ScoreQ: "score"}


def question_to_json(q) -> dict:
    kind = _KIND[type(q)]
    criteria = None if kind == "noul" else (dict(q.criteria) if kind == "choice" else list(q.criteria))
    return {"kind": kind, "instructions": q.instructions, "criteria": criteria, "qtype": q.qtype, "subject": q.subject}


def question_from_json(d: dict):
    meta = {"qtype": d.get("qtype") or "", "subject": d.get("subject") or ""}
    if d["kind"] == "noul":
        return NoulQ(d["instructions"], **meta)
    if d["kind"] == "choice":
        return ChoiceQ(d["instructions"], dict(d["criteria"]), **meta)
    if d["kind"] == "score":
        return ScoreQ(d["instructions"], list(d["criteria"]), **meta)
    raise ValueError(f"unknown question kind {d['kind']!r}")


def question_key(state: dict, q) -> str:
    j = question_to_json(q)
    body = {"state": state, "kind": j["kind"], "instructions": j["instructions"], "criteria": j["criteria"]}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def decision_to_json(d: Decision, suggestion_id: int | None = None) -> dict:
    return {"answer": d.answer, "confidence": d.confidence, "probabilities": d.probabilities, "source": d.source,
            "accepted": d.accepted, "error": d.error, "suggestion_id": suggestion_id}


def decision_from_json(d: dict) -> Decision:
    return Decision(d.get("answer"), float(d.get("confidence") or 0.0), dict(d.get("probabilities") or {}),
                    d.get("source") or "error", bool(d.get("accepted")), d.get("error") or "")


def options_of(q) -> list:
    if isinstance(q, NoulQ):
        return [True, False]
    if isinstance(q, ChoiceQ):
        return list(q.criteria)
    return list(range(len(q.criteria)))
```

- [ ] **Step 4: Run the new tests, then all decide tests:** `engine/tests/test_decide_wire.py`,
  `engine/tests/test_decide_jev.py` and `engine/tests/test_decide_pilot.py`. Expected: all pass. The existing decide
  tests must pass unchanged, because the new fields have defaults.
- [ ] **Step 5: Commit:** `feat(decide): questions carry qtype/subject; wire format and question_key`.

---

