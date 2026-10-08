"""The Decider (engine/decide/decider.py): owner answer, then rules, then suggestion providers, otherwise the
owner's queue. Fake providers only: no key, no network, nothing written outside tmp_path."""
import hashlib
import json

import pytest

from engine.decide.decider import (
    Answer,
    Decider,
    Question,
    QuestionType,
    RuleProvider,
    question_key,
)

BUILDINGS = (
    ("BRS", "Building BRS"),
    ("CHTM", "Building CHTM"),
    ("MAIN", "Main building"),
)

T_BUILDING = QuestionType(
    "inv.building", "choice", "Which building does this group belong to?", BUILDINGS
)
T_DUP = QuestionType("inv.duplicate", "noul", "Is this group a duplicate of another?", ())
T_PRIORITY = QuestionType("review.priority", "score", "How urgent is this unit?", ("low", "mid", "high"))


def _q(subject="CHTM_5th_floor", **state):
    return Question("inv.building", subject, state or {"name": subject})


def _digest(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------- question_key (convention with the Jev session)


def test_question_key_choice_matches_convention():
    q = _q("G1", name="G1", n=3)
    expected = _digest(
        {
            "state": {"name": "G1", "n": 3},
            "kind": "choice",
            "instructions": "Which building does this group belong to?",
            "criteria": [["BRS", "Building BRS"], ["CHTM", "Building CHTM"], ["MAIN", "Main building"]],
        }
    )
    assert question_key(T_BUILDING, q) == expected


def test_question_key_choice_is_order_sensitive():
    reordered = QuestionType(
        "inv.building", "choice", T_BUILDING.instructions, tuple(reversed(BUILDINGS))
    )
    q = _q("G1")
    assert question_key(T_BUILDING, q) != question_key(reordered, q)


def test_question_key_ignores_qtype_subject_and_state_order():
    other_type = QuestionType("inv.type", "choice", T_BUILDING.instructions, BUILDINGS)
    a = Question("inv.building", "G1", {"a": 1, "b": 2})
    b = Question("inv.type", "G2", {"b": 2, "a": 1})
    assert question_key(T_BUILDING, a) == question_key(other_type, b)


def test_question_key_noul_and_score_criteria():
    assert question_key(T_DUP, Question("inv.duplicate", "G", {"x": 1})) == _digest(
        {"state": {"x": 1}, "kind": "noul", "instructions": T_DUP.instructions, "criteria": None}
    )
    assert question_key(T_PRIORITY, Question("review.priority", "U", {})) == _digest(
        {"state": {}, "kind": "score", "instructions": T_PRIORITY.instructions,
         "criteria": ["low", "mid", "high"]}
    )


def test_question_type_validation():
    with pytest.raises(ValueError):
        QuestionType("Building", "choice", "x", (("a", "b"),))  # not <area>.<question> lowercase
    with pytest.raises(ValueError):
        QuestionType("inv.thing", "choice", "x", tuple((str(i), "d") for i in range(256)))
    QuestionType("inv.thing", "choice", "x", tuple((str(i), "d") for i in range(255)))
    with pytest.raises(ValueError):
        QuestionType("inv.thing", "score", "x", tuple(str(i) for i in range(11)))
    with pytest.raises(ValueError):
        QuestionType("inv.thing", "maybe", "x", ())


# ---------------------------------------------------------------- owner, rules, off, queue, log


def _decider(tmp_path, providers=(), types=(T_BUILDING, T_DUP, T_PRIORITY)):
    return Decider(list(types), list(providers), tmp_path / "log.jsonl", tmp_path / "cache.jsonl")


def _log(tmp_path):
    p = tmp_path / "log.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def _rules(**by_qtype):
    return RuleProvider(by_qtype)


def _chtm_rule(q):
    return "CHTM" if q.subject.startswith("CHTM") else None


def test_rules_answer_is_accepted_with_full_confidence(tmp_path):
    d = _decider(tmp_path, [_rules(**{"inv.building": _chtm_rule})])
    (a,) = d.ask([_q("CHTM_5th_floor")])
    assert (a.answer, a.provider, a.confidence, a.accepted, a.suggestion) == ("CHTM", "rules", 1.0, True, None)
    assert (a.qtype, a.subject) == ("inv.building", "CHTM_5th_floor")
    assert a.key == question_key(T_BUILDING, _q("CHTM_5th_floor"))
    assert a.probabilities == {"CHTM": 1.0}


def test_every_question_gets_a_rule_answer_or_goes_to_the_owner_queue(tmp_path):
    d = _decider(tmp_path, [_rules(**{"inv.building": _chtm_rule})])
    qs = [_q("CHTM_a"), _q("Group137"), Question("inv.duplicate", "G", {"n": 1})]
    answers = d.ask(qs)
    assert [a.subject for a in answers] == ["CHTM_a", "Group137", "G"]  # same order as asked
    for a in answers:
        assert (a.provider == "rules" and a.accepted) or (a.provider == "queue" and not a.accepted)
    assert [a.provider for a in answers] == ["rules", "queue", "queue"]
    assert sorted(a.subject for a in d.owner_queue()) == ["G", "Group137"]
    assert all(a.answer is None and a.suggestion is None for a in d.owner_queue())


def test_rule_returning_false_is_an_answer_not_a_miss(tmp_path):
    d = _decider(tmp_path, [_rules(**{"inv.duplicate": lambda q: False})])
    (a,) = d.ask([Question("inv.duplicate", "G", {})])
    assert (a.answer, a.provider, a.accepted) == (False, "rules", True)


def test_owner_answer_beats_rules_and_latest_wins(tmp_path):
    d = _decider(tmp_path, [_rules(**{"inv.building": _chtm_rule})])
    d.record_owner("inv.building", "CHTM_5th_floor", "MAIN")
    (a,) = d.ask([_q("CHTM_5th_floor")])
    assert (a.answer, a.provider, a.confidence, a.accepted) == ("MAIN", "owner", 1.0, True)
    d.record_owner("inv.building", "CHTM_5th_floor", "BRS")
    assert d.ask([_q("CHTM_5th_floor")])[0].answer == "BRS"
    # keyed by (qtype, subject): another subject is unaffected
    assert d.ask([_q("CHTM_other")])[0].provider == "rules"


def test_owner_answer_leaves_the_queue_and_must_be_a_valid_option(tmp_path):
    d = _decider(tmp_path)
    d.ask([_q("Group137")])
    assert [a.subject for a in d.owner_queue()] == ["Group137"]
    with pytest.raises(ValueError):
        d.record_owner("inv.building", "Group137", "NOT A BUILDING")
    with pytest.raises(ValueError):
        d.record_owner("inv.duplicate", "Group137", "yes")  # a noul takes true or false
    with pytest.raises(KeyError):
        d.record_owner("inv.unknown", "Group137", "x")
    d.record_owner("inv.building", "Group137", "BRS")
    assert d.owner_queue() == []


def test_mode_off_goes_straight_to_the_owner_queue(tmp_path):
    calls = []

    def rule(q):
        calls.append(q.subject)
        return "CHTM"

    off = QuestionType("inv.building", "choice", T_BUILDING.instructions, BUILDINGS, mode="off")
    d = _decider(tmp_path, [_rules(**{"inv.building": rule})], types=[off])
    (a,) = d.ask([_q("CHTM_5th_floor")])
    assert (a.provider, a.accepted, a.answer, a.suggestion) == ("queue", False, None, None)
    assert calls == []  # the rules were not even asked
    assert d.mode_of("inv.building") == "off"
    # the owner still beats mode off
    d.record_owner("inv.building", "CHTM_5th_floor", "CHTM")
    assert d.ask([_q("CHTM_5th_floor")])[0].provider == "owner"


def test_a_rule_that_raises_is_logged_and_falls_through(tmp_path):
    def boom(q):
        raise RuntimeError("rule exploded")

    d = _decider(tmp_path, [_rules(**{"inv.building": boom})])
    (a,) = d.ask([_q("G")])
    assert (a.provider, a.accepted) == ("queue", False)
    errs = [r for r in _log(tmp_path) if r.get("event") == "error"]
    assert len(errs) == 1 and errs[0]["provider"] == "rules" and "RuntimeError" in errs[0]["error"]


def test_a_rule_returning_an_invalid_option_falls_through(tmp_path):
    d = _decider(tmp_path, [_rules(**{"inv.building": lambda q: "ATLANTIS"})])
    (a,) = d.ask([_q("G")])
    assert (a.provider, a.accepted) == ("queue", False)
    assert any(r.get("event") == "error" for r in _log(tmp_path))


def test_unknown_qtype_is_a_programming_error(tmp_path):
    d = _decider(tmp_path)
    with pytest.raises(KeyError):
        d.ask([Question("inv.nothing", "G", {})])


def test_log_has_one_line_per_answer_and_owner_decision_with_the_agreed_fields(tmp_path):
    d = _decider(tmp_path, [_rules(**{"inv.building": _chtm_rule})])
    d.ask([_q("CHTM_a"), _q("Group137")])
    d.record_owner("inv.building", "Group137", "MAIN")
    lines = _log(tmp_path)
    assert [(r["event"], r["provider"], r["subject"]) for r in lines] == [
        ("answer", "rules", "CHTM_a"),
        ("answer", "queue", "Group137"),
        ("owner", "owner", "Group137"),
    ]
    for r in lines:
        for field in ("qtype", "subject", "key", "provider", "answer", "confidence", "accepted", "mode",
                      "latency_s", "tokens"):
            assert field in r, field
        assert r["tokens"] is None  # rules and the owner use no tokens
    assert lines[0]["answer"] == "CHTM" and lines[0]["accepted"] is True and lines[0]["mode"] == "suggest"
    assert lines[2]["answer"] == "MAIN" and lines[2]["accepted"] is True


def test_log_round_trips_owner_answers_modes_and_queue(tmp_path):
    d = _decider(tmp_path, [_rules(**{"inv.building": _chtm_rule})])
    d.ask([_q("CHTM_a"), _q("Group137"), _q("Group138")])
    d.record_owner("inv.building", "Group138", "BRS")
    d2 = _decider(tmp_path)  # a fresh process: no providers, same files
    assert d2.ask([_q("Group138")])[0].answer == "BRS"
    assert d2.ask([_q("Group138")])[0].provider == "owner"
    assert [a.subject for a in d2.owner_queue()] == ["Group137"]
    assert d2.owner_queue()[0].key == question_key(T_BUILDING, _q("Group137"))


def test_truncated_last_log_line_is_ignored(tmp_path):
    d = _decider(tmp_path)
    d.record_owner("inv.building", "G", "BRS")
    with open(tmp_path / "log.jsonl", "a", encoding="utf-8") as f:
        f.write('{"event": "owner", "qtype": "inv.bui')
    assert _decider(tmp_path).ask([_q("G")])[0].answer == "BRS"


def test_default_paths_are_cwd_relative_under_data_decide(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = Decider([T_BUILDING], [])
    d.ask([_q("G")])
    assert (tmp_path / "data" / "decide" / "log.jsonl").exists()
