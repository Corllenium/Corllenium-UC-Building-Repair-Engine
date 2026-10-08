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


# ---------------------------------------------------------------- other providers, SUGGEST, cache


class FakeProvider:
    """Answers from a table {subject: (answer, confidence)}; records every question it was given."""

    def __init__(self, name="jev", table=None, tokens=7):
        self.name = name
        self.table = table or {}
        self.tokens = tokens
        self.calls = []  # one list of subjects per answer() call

    def answer(self, qt, questions):
        self.calls.append([q.subject for q in questions])
        out = []
        for q in questions:
            hit = self.table.get(q.subject)
            if hit is None:
                out.append(None)
                continue
            value, conf = hit
            out.append(Answer(q.qtype, q.subject, question_key(qt, q), value, conf, self.name,
                              {str(value): conf}, False, None, self.tokens))
        return out


class RaisingProvider:
    name = "flaky"

    def __init__(self):
        self.calls = 0

    def answer(self, qt, questions):
        self.calls += 1
        raise TimeoutError("network down")


def test_suggest_mode_never_accepts_a_provider_answer(tmp_path):
    jev = FakeProvider(table={"G": ("CHTM", 0.999)})
    d = _decider(tmp_path, [_rules(**{}), jev])
    (a,) = d.ask([_q("G")])
    assert (a.provider, a.accepted, a.answer) == ("queue", False, None)
    assert a.suggestion["provider"] == "jev" and a.suggestion["answer"] == "CHTM"
    assert a.suggestion["confidence"] == 0.999 and a.suggestion["probabilities"] == {"CHTM": 0.999}
    (queued,) = d.owner_queue()
    assert queued.suggestion == a.suggestion


def test_the_best_suggestion_is_the_most_confident_one(tmp_path):
    p1 = FakeProvider("low", {"G": ("BRS", 0.4)})
    p2 = FakeProvider("high", {"G": ("MAIN", 0.8)})
    d = _decider(tmp_path, [p1, p2])
    (a,) = d.ask([_q("G")])
    assert (a.suggestion["provider"], a.suggestion["answer"]) == ("high", "MAIN")


def test_rules_and_owner_beat_providers_which_are_then_not_called(tmp_path):
    jev = FakeProvider(table={"CHTM_a": ("BRS", 0.99), "G": ("BRS", 0.99)})
    d = _decider(tmp_path, [jev, _rules(**{"inv.building": _chtm_rule})])  # rules given last, still first
    d.record_owner("inv.building", "G", "MAIN")
    answers = d.ask([_q("CHTM_a"), _q("G")])
    assert [(a.provider, a.answer) for a in answers] == [("rules", "CHTM"), ("owner", "MAIN")]
    assert jev.calls == []


def test_one_provider_call_per_question_type_with_unique_keys(tmp_path):
    jev = FakeProvider(table={"A": ("BRS", 0.5), "B": ("BRS", 0.5)})
    d = _decider(tmp_path, [jev])
    same_state = {"name": "same"}
    d.ask([Question("inv.building", "A", same_state), Question("inv.building", "B", same_state),
           Question("inv.building", "C", {"name": "other"})])
    assert jev.calls == [["A", "C"]]  # A and B share a key: one question; C is another
    # B, with the same key, still gets A's answer, under its own subject
    qs = {a.subject: a for a in d.owner_queue()}
    assert qs["B"].suggestion["answer"] == "BRS" and qs["C"].suggestion is None


def test_the_cache_prevents_a_second_provider_call(tmp_path):
    jev = FakeProvider(table={"G": ("CHTM", 0.9)})
    d = _decider(tmp_path, [jev])
    d.ask([_q("G")])
    d.ask([_q("G")])
    assert jev.calls == [["G"]]
    # a fresh Decider on the same cache file does not call either, and the misses are cached too
    jev2 = FakeProvider(table={"G": ("BRS", 0.1)})
    d2 = _decider(tmp_path, [jev2])
    assert d2.ask([_q("G")])[0].suggestion["answer"] == "CHTM"
    d2.ask([_q("Nobody")])  # a miss
    d2.ask([_q("Nobody")])
    assert jev2.calls == [["Nobody"]]
    rows = [json.loads(x) for x in (tmp_path / "cache.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {(r["key"], r["provider"]) for r in rows} == {
        (question_key(T_BUILDING, _q("G")), "jev"), (question_key(T_BUILDING, _q("Nobody")), "jev")}


def test_cache_is_per_provider(tmp_path):
    a, b = FakeProvider("a", {"G": ("BRS", 0.5)}), FakeProvider("b", {"G": ("MAIN", 0.6)})
    d = _decider(tmp_path, [a])
    d.ask([_q("G")])
    d2 = _decider(tmp_path, [a, b])
    (ans,) = d2.ask([_q("G")])
    assert a.calls == [["G"]] and b.calls == [["G"]]
    assert ans.suggestion["provider"] == "b"


def test_a_provider_that_raises_is_logged_and_the_question_falls_through(tmp_path):
    bad = RaisingProvider()
    jev = FakeProvider(table={"G": ("BRS", 0.7)})
    d = _decider(tmp_path, [bad, jev])
    (a,) = d.ask([_q("G")])
    assert (a.provider, a.accepted) == ("queue", False)
    assert a.suggestion["provider"] == "jev"  # the next provider still ran
    errs = [r for r in _log(tmp_path) if r.get("event") == "error"]
    assert len(errs) == 1 and errs[0]["provider"] == "flaky" and "TimeoutError" in errs[0]["error"]
    # a failure is not cached: the next ask tries again
    d.ask([_q("G")])
    assert bad.calls == 2


def test_a_provider_that_answers_badly_is_logged_and_ignored(tmp_path):
    wrong_length = FakeProvider("short")
    wrong_length.answer = lambda qt, questions: []
    invalid = FakeProvider("invalid", {"G": ("ATLANTIS", 0.9)})
    d = _decider(tmp_path, [wrong_length, invalid])
    (a,) = d.ask([_q("G")])
    assert (a.provider, a.suggestion) == ("queue", None)
    assert sorted(r["provider"] for r in _log(tmp_path) if r.get("event") == "error") == ["invalid", "short"]


def test_provider_answers_are_logged_with_latency_and_tokens(tmp_path):
    d = _decider(tmp_path, [FakeProvider(table={"G": ("CHTM", 0.9)}, tokens=11)])
    d.ask([_q("G")])
    (rec,) = [r for r in _log(tmp_path) if r.get("event") == "provider"]
    assert (rec["provider"], rec["answer"], rec["confidence"], rec["accepted"], rec["tokens"]) == (
        "jev", "CHTM", 0.9, False, 11)
    assert isinstance(rec["latency_s"], float) and rec["mode"] == "suggest"


def test_provider_noul_answer_keeps_its_raw_form(tmp_path):
    jev = FakeProvider(table={"G": (False, 0.8)})
    d = _decider(tmp_path, [jev])
    (a,) = d.ask([Question("inv.duplicate", "G", {"n": 1})])
    assert a.suggestion["answer"] is False and a.suggestion["probabilities"] == {"False": 0.8}


# ---------------------------------------------------------------- statistics, promotion, demotion, AUTO


def _history(d, jev, spec, start=0):
    """For each (confidence, agrees) in `spec`: the provider answers a fresh subject with that confidence, then
    the owner decides, agreeing or not. Returns the next free subject number."""
    n = start
    for conf, agrees in spec:
        subject = f"S{n}"
        n += 1
        jev.table[subject] = ("CHTM", conf)
        d.ask([Question("inv.building", subject, {"name": subject})])
        d.record_owner("inv.building", subject, "CHTM" if agrees else "BRS")
    return n


def _fresh(tmp_path, **kw):
    jev = FakeProvider()
    return _decider(tmp_path, [_rules(**{}), jev], **kw), jev


def test_stats_join_provider_answers_with_the_owner_decisions_that_follow(tmp_path):
    d, jev = _fresh(tmp_path)
    _history(d, jev, [(0.95, True)] * 3 + [(0.95, False)] + [(0.55, True), (0.55, False)])
    d.ask([_q("RuleOnly")])  # no provider answer; the owner decides: not a provider decision
    d.record_owner("inv.building", "RuleOnly", "MAIN")
    st = d.stats("inv.building")
    assert (st["decisions"], st["agreed"]) == (6, 4)
    assert st["agreement"] == pytest.approx(4 / 6)
    assert st["by_confidence"]["0.9-1.0"] == {"decisions": 4, "agreed": 3, "agreement": 0.75}
    assert st["by_confidence"]["0.5-0.6"] == {"decisions": 2, "agreed": 1, "agreement": 0.5}
    assert st["mode"] == "suggest" and st["eligible_for_auto"] is False
    assert d.stats("inv.duplicate")["decisions"] == 0 and d.stats("inv.duplicate")["agreement"] is None


def test_rule_answers_do_not_count_as_provider_agreement(tmp_path):
    d = _decider(tmp_path, [_rules(**{"inv.building": _chtm_rule})])
    d.ask([_q("CHTM_a")])
    d.record_owner("inv.building", "CHTM_a", "CHTM")
    assert d.stats("inv.building")["decisions"] == 0


def test_promotion_stays_off_below_50_decisions(tmp_path):
    d, jev = _fresh(tmp_path)
    _history(d, jev, [(0.95, True)] * 49)
    st = d.stats("inv.building")
    assert (st["decisions"], st["agreement"], st["eligible_for_auto"]) == (49, 1.0, False)
    with pytest.raises(ValueError):
        d.promote("inv.building")
    assert d.mode_of("inv.building") == "suggest"


def test_promotion_stays_off_below_95_percent(tmp_path):
    d, jev = _fresh(tmp_path)
    n = _history(d, jev, [(0.95, True)] * 47 + [(0.95, False)] * 3)  # 94 %
    st = d.stats("inv.building")
    assert (st["decisions"], st["eligible_for_auto"]) == (50, False)
    with pytest.raises(ValueError):
        d.promote("inv.building")
    n = _history(d, jev, [(0.95, True)] * 4, start=n)  # 51/54 = 94.4 %: still no
    assert d.stats("inv.building")["eligible_for_auto"] is False
    _history(d, jev, [(0.95, True)] * 10, start=n)  # 61/64 = 95.3 %
    assert d.stats("inv.building")["eligible_for_auto"] is True


def test_eligibility_is_reported_but_the_mode_changes_only_on_an_explicit_call(tmp_path):
    d, jev = _fresh(tmp_path)
    _history(d, jev, [(0.95, True)] * 50)
    assert d.stats("inv.building")["eligible_for_auto"] is True
    assert d.mode_of("inv.building") == "suggest"  # nothing promoted itself
    assert [r for r in _log(tmp_path) if r["event"] == "mode"] == []
    assert d.promote("inv.building") == "auto"
    assert d.mode_of("inv.building") == "auto"
    (rec,) = [r for r in _log(tmp_path) if r["event"] == "mode"]
    assert (rec["qtype"], rec["from"], rec["to"]) == ("inv.building", "suggest", "auto")
    assert rec["decisions"] == 50 and rec["agreement"] == 1.0
    assert _decider(tmp_path).mode_of("inv.building") == "auto"  # the log carries the mode
    with pytest.raises(ValueError):
        d.promote("inv.building")  # already auto


def test_only_a_suggest_type_can_be_promoted(tmp_path):
    off = QuestionType("inv.building", "choice", T_BUILDING.instructions, BUILDINGS, mode="off")
    d = _decider(tmp_path, [], types=[off])
    with pytest.raises(ValueError):
        d.promote("inv.building")


def test_auto_accepts_only_in_the_measured_band(tmp_path):
    d, jev = _fresh(tmp_path)
    spec = (
        [(0.95, True)] * 58                         # band 0.9-1.0: 58/58
        + [(0.65, True)] * 7 + [(0.65, False)] * 3  # band 0.6-0.7: 7/10 = 70 %
        + [(0.75, True)] * 5                        # band 0.7-0.8: 100 % but only 5 decisions
    )
    _history(d, jev, spec)
    st = d.stats("inv.building")
    assert st["eligible_for_auto"] is True and st["auto_bands"] == ["0.9-1.0"]
    d.promote("inv.building")
    jev.table.update({"hi": ("MAIN", 0.93), "mid": ("MAIN", 0.65), "thin": ("MAIN", 0.75),
                      "unseen": ("MAIN", 0.35)})
    answers = {a.subject: a for a in d.ask([_q(s) for s in ("hi", "mid", "thin", "unseen")])}
    assert (answers["hi"].provider, answers["hi"].accepted, answers["hi"].answer) == ("jev", True, "MAIN")
    assert answers["hi"].confidence == 0.93
    for s in ("mid", "thin", "unseen"):
        assert (answers[s].provider, answers[s].accepted, answers[s].answer) == ("queue", False, None)
        assert answers[s].suggestion["answer"] == "MAIN"
    assert sorted(a.subject for a in d.owner_queue()) == ["mid", "thin", "unseen"]
    acc = [r for r in _log(tmp_path) if r["event"] == "answer" and r["subject"] == "hi"][-1]
    assert (acc["provider"], acc["accepted"], acc["mode"], acc["tokens"]) == ("jev", True, "auto", 7)


def test_auto_still_lets_the_owner_and_the_rules_come_first(tmp_path):
    jev = FakeProvider()
    d = _decider(tmp_path, [_rules(**{"inv.building": _chtm_rule}), jev])
    _history(d, jev, [(0.95, True)] * 50)
    d.promote("inv.building")
    jev.table.update({"CHTM_x": ("MAIN", 0.99), "owned": ("MAIN", 0.99)})
    d.record_owner("inv.building", "owned", "BRS")
    a, b = d.ask([_q("CHTM_x"), _q("owned")])
    assert (a.provider, a.answer) == ("rules", "CHTM") and (b.provider, b.answer) == ("owner", "BRS")


def test_demotion_is_reported_below_90_percent_of_the_last_30_and_applied_only_on_call(tmp_path):
    d, jev = _fresh(tmp_path)
    n = _history(d, jev, [(0.95, True)] * 50)
    d.promote("inv.building")
    _history(d, jev, [(0.95, True)] * 26 + [(0.95, False)] * 4, start=n)  # last 30: 26/30 = 86.7 %
    st = d.stats("inv.building")
    assert st["last30_decisions"] == 30 and st["last30_agreement"] == pytest.approx(26 / 30)
    assert st["agreement"] >= 0.95  # overall still fine: only the recent window matters
    assert st["should_demote"] is True
    assert d.mode_of("inv.building") == "auto"  # nothing demoted itself
    assert d.demote("inv.building") == "suggest"
    assert d.mode_of("inv.building") == "suggest"
    rec = [r for r in _log(tmp_path) if r["event"] == "mode"][-1]
    assert (rec["from"], rec["to"]) == ("auto", "suggest") and rec["last30_agreement"] == pytest.approx(26 / 30)
    assert _decider(tmp_path).mode_of("inv.building") == "suggest"
    # and in suggest mode the confident answer is a suggestion again
    jev.table["again"] = ("MAIN", 0.99)
    assert d.ask([_q("again")])[0].accepted is False


def test_no_demotion_at_exactly_90_percent(tmp_path):
    d, jev = _fresh(tmp_path)
    n = _history(d, jev, [(0.95, True)] * 50)
    d.promote("inv.building")
    _history(d, jev, [(0.95, True)] * 27 + [(0.95, False)] * 3, start=n)  # 27/30 = 90 %
    assert d.stats("inv.building")["should_demote"] is False


def test_no_demotion_before_30_decisions_or_outside_auto(tmp_path):
    d, jev = _fresh(tmp_path)
    _history(d, jev, [(0.95, False)] * 5)
    st = d.stats("inv.building")
    assert st["last30_decisions"] == 5 and st["should_demote"] is False


def test_demote_needs_an_auto_type(tmp_path):
    d, _ = _fresh(tmp_path)
    with pytest.raises(ValueError):
        d.demote("inv.building")


def test_stats_survive_a_restart(tmp_path):
    d, jev = _fresh(tmp_path)
    _history(d, jev, [(0.95, True)] * 50)
    d2 = _decider(tmp_path)
    assert d2.stats("inv.building")["decisions"] == 50
    assert d2.stats("inv.building")["eligible_for_auto"] is True
