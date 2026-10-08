"""The service core (decide_service.logic) with MemoryStore and a fake Jev client: no network, no real key."""
import json
from types import SimpleNamespace

import pytest

from decide_service import logic
from decide_service.settings import Settings
from decide_service.store import MemoryStore
from engine.decide import wire
from engine.decide.jev import ChoiceQ, JevDecider, NoulQ, ScoreQ

FAKE_KEY = "ts-FAKE-KEY-0123456789-do-not-leak"
CATS = {"glass": None, "metal": None, "wood": None}


class FakeClient:
    """Answers every Choice with its first label (confidence 0.95); records each call."""

    def __init__(self, error=None, confidence=0.95):
        self.error = error
        self.confidence = confidence
        self.calls = []

    def system_one(self, state, questions):
        self.calls.append({"state": state, "questions": dict(questions)})
        if self.error is not None:
            raise self.error
        answers = {}
        for qid, spec in questions.items():
            label = next(iter(spec.criteria))
            answers[qid] = SimpleNamespace(type="choice", choice=label, confidence=self.confidence,
                                      probabilities={label: self.confidence})
        return SimpleNamespace(answers=answers, model="jev-fake",
                               usage=SimpleNamespace(input_tokens=100, output_tokens=7))


def _setup(enabled=True, error=None, confidence=0.95, **cfg):
    client = FakeClient(error, confidence)
    store = MemoryStore()
    settings = Settings(jev_enabled=enabled, **cfg)
    return client, store, settings, lambda: JevDecider(client=client)


def _q(subject="stone_brick"):
    return ChoiceQ("Which category?", CATS, qtype="mat.category", subject=subject)


def test_jev_off_gives_none_and_never_calls():
    client, store, cfg, make = _setup(enabled=False)
    out = logic.answer(store, cfg, make, {"name": "stone_brick"}, {"a": _q()})
    assert out["a"]["source"] == "none" and out["a"]["error"] == "jev off" and out["a"]["accepted"] is False
    assert client.calls == [] and store.list() == []


def test_jev_on_calls_once_and_stores_a_pending_suggestion():
    client, store, cfg, make = _setup()
    out = logic.answer(store, cfg, make, {"name": "stone_brick"}, {"a": _q()})
    rows = store.list()
    assert len(client.calls) == 1 and len(rows) == 1
    assert rows[0]["source"] == "jev" and rows[0]["status"] == "pending" and rows[0]["answer"] == "glass"
    assert out["a"]["suggestion_id"] == rows[0]["id"] and out["a"]["answer"] == "glass"


def test_same_question_is_served_from_the_store():
    client, store, cfg, make = _setup()
    first = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})
    second = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})
    assert len(client.calls) == 1 and len(store.list()) == 1
    assert second["a"]["suggestion_id"] == first["a"]["suggestion_id"] and second["a"]["answer"] == "glass"


def test_owner_answer_wins_without_a_call():
    client, store, cfg, make = _setup()
    sid = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})["a"]["suggestion_id"]
    logic.review(store, sid, "gab", answer="metal")
    out = logic.answer(store, cfg, make, {"name": "other state"}, {"a": _q()})
    assert out["a"]["answer"] == "metal" and out["a"]["source"] == "owner" and out["a"]["accepted"] is True
    assert len(client.calls) == 1


def test_review_validates_the_answer_and_accept_takes_jevs():
    client, store, cfg, make = _setup()
    sid = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})["a"]["suggestion_id"]
    with pytest.raises(ValueError):
        logic.review(store, sid, "gab", answer="plastic")
    with pytest.raises(KeyError):
        logic.review(store, 999, "gab", accept=True)
    row = logic.review(store, sid, "gab", accept=True)
    assert row["status"] == "accepted" and row["owner_answer"] == "glass" and row["reviewed_by"] == "gab"
    assert wire.options_of(wire.question_from_json(row["question"])) == ["glass", "metal", "wood"]


def test_daily_cap_stops_the_call():
    client, store, cfg, make = _setup(daily_token_cap=1000)
    store.add_call({"input_tokens": 990, "output_tokens": 10, "at": logic._now()})
    out = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})
    assert out["a"]["source"] == "none" and out["a"]["error"] == "daily cap" and client.calls == []


def test_limits_raise_before_any_call():
    client, store, cfg, make = _setup()
    with pytest.raises(ValueError):
        logic.answer(store, cfg, make, {"name": "x"}, {"a": ScoreQ("how much?", [str(i) for i in range(11)])})
    assert client.calls == []


def test_calls_are_recorded_and_a_key_never_leaks():
    client, store, cfg, make = _setup()
    logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})
    assert len(store.calls) == 1 and store.calls[0]["input_tokens"] == 100 and store.calls[0]["output_tokens"] == 7
    assert store.tokens_today() == 107

    client, store, cfg, make = _setup(error=RuntimeError(f"401 bad key {FAKE_KEY}"))
    out = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})
    blob = json.dumps([out, store.list(), store.calls], default=str)
    assert FAKE_KEY not in blob and len(store.calls) == 1 and store.calls[0]["ok"] is False
    assert out["a"]["source"] == "error" and out["a"]["suggestion_id"] is None and store.list() == []


def test_import_adds_pilot_rows_and_skips_existing_keys():
    _, store, cfg, make = _setup(enabled=False)
    item = {"question": wire.question_to_json(_q()), "state": {"name": "x"}, "answer": "metal",
            "confidence": 0.9, "probabilities": {"metal": 0.9}, "model": "pilot"}
    assert logic.import_items(store, [item]) == {"added": 1, "skipped": 0, "invalid": 0}
    other = {**item, "state": {"name": "y"}}
    assert logic.import_items(store, [item, other]) == {"added": 1, "skipped": 1, "invalid": 0}
    rows = store.list()
    assert len(rows) == 2 and {r["source"] for r in rows} == {"pilot-import"}
    out = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})
    assert out["a"]["answer"] == "metal" and out["a"]["source"] == "pilot-import"


def test_reask_updates_the_row_and_needs_jev_on():
    client, store, cfg, make = _setup()
    sid = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})["a"]["suggestion_id"]
    logic.review(store, sid, "gab", answer="wood")
    store.update_suggestion(sid, answer="metal")
    row = logic.reask(store, cfg, make, sid)
    assert len(client.calls) == 2 and row["answer"] == "glass" and row["status"] == "changed"
    assert row["owner_answer"] == "wood" and row["reviewed_by"] == "gab" and store.confirmed("mat.category") == {"stone_brick": "wood"}
    _, store2, cfg2, make2 = _setup(enabled=False)
    sid2 = store2.add_suggestion({"qtype": "mat.category", "subject": "s", "key": "k", "state": "{}",
                                  "question": wire.question_to_json(_q("s")), "answer": "metal", "confidence": 0.9,
                                  "probabilities": {}, "model": "m", "source": "jev", "status": "pending",
                                  "owner_answer": None, "reviewed_at": None, "reviewed_by": None, "created_at": "t"})
    with pytest.raises(PermissionError, match="jev off"):
        logic.reask(store2, cfg2, make2, sid2)


def test_confirmed_returns_only_reviewed_subjects_with_the_latest_answer():
    client, store, cfg, make = _setup()
    ids = {s: logic.answer(store, cfg, make, {"name": s}, {"a": _q(s)})["a"]["suggestion_id"]
           for s in ("one", "two", "three")}
    logic.review(store, ids["one"], "gab", answer="wood")
    logic.review(store, ids["one"], "gab", answer="metal")
    logic.review(store, ids["two"], "gab", accept=True)
    assert store.confirmed("mat.category") == {"one": "metal", "two": "glass"}
    assert store.confirmed("group.unit") == {}
    assert store.counts("mat.category") == {"pending": 1, "accepted": 1, "changed": 1}


# ------------------------------------------------------------------------------------ fix round 1


def test_same_question_twice_in_one_call_asks_once():
    client, store, cfg, make = _setup()
    out = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q("one"), "b": _q("two")})
    assert len(client.calls) == 1 and list(client.calls[0]["questions"]) == ["a"] and len(store.list()) == 1
    assert out["a"]["suggestion_id"] == out["b"]["suggestion_id"] == store.list()[0]["id"]
    assert out["a"]["answer"] == out["b"]["answer"] == "glass"


def test_accepted_is_never_set_by_confidence_fresh_or_cached():
    # The final review's ruling: `accepted` is true only for the owner's own answer; confidence is still returned.
    client, store, cfg, make = _setup(min_confidence=0.9)             # 0.95 is over the display threshold
    fresh = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})
    cached = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})
    assert fresh["a"]["accepted"] is False and cached["a"]["accepted"] is False
    assert fresh["a"]["confidence"] == cached["a"]["confidence"] == 0.95


def test_a_099_confidence_jev_answer_is_not_accepted():
    client, store, cfg, make = _setup(confidence=0.99)
    out = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})["a"]
    assert out["source"] == "jev" and out["confidence"] == 0.99 and out["accepted"] is False


def test_pilot_import_answer_is_not_accepted_and_keeps_its_confidence():
    client, store, cfg, make = _setup()
    item = {"state": {"name": "x"}, "question": wire.question_to_json(_q()), "answer": "metal", "confidence": 0.97}
    assert logic.import_items(store, [item]) == {"added": 1, "skipped": 0, "invalid": 0}
    out = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})["a"]
    assert out["source"] == "pilot-import" and out["confidence"] == 0.97 and out["accepted"] is False
    assert client.calls == []


def test_only_the_owners_answer_is_accepted():
    client, store, cfg, make = _setup()
    sid = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})["a"]["suggestion_id"]
    logic.review(store, sid, "gab", accept=True)
    out = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})["a"]
    assert out["source"] == "owner" and out["accepted"] is True


def test_cached_row_reviewed_by_the_owner_returns_the_owner_answer():
    client, store, cfg, make = _setup()
    q = ChoiceQ("Which category?", CATS)
    sid = logic.answer(store, cfg, make, {"name": "x"}, {"a": q})["a"]["suggestion_id"]
    logic.review(store, sid, "gab", answer="wood")
    out = logic.answer(store, cfg, make, {"name": "x"}, {"a": q})["a"]
    assert (out["answer"], out["source"], out["accepted"], out["suggestion_id"]) == ("wood", "owner", True, sid)
    assert len(client.calls) == 1


def _row_for(q, answer):
    return {"qtype": q.qtype, "subject": q.subject, "key": "k" + str(answer), "state": "{}", "state_json": {},
            "question": wire.question_to_json(q), "answer": answer, "confidence": 0.9, "probabilities": {},
            "model": "m", "source": "jev", "status": "pending", "owner_answer": None, "reviewed_at": None,
            "reviewed_by": None, "created_at": "t"}


@pytest.mark.parametrize("q,bad", [
    (NoulQ("is it?"), 1), (NoulQ("is it?"), 0.0), (NoulQ("is it?"), "yes"),
    (ScoreQ("how much?", ["a", "b", "c"]), True), (ScoreQ("how much?", ["a", "b", "c"]), 3),
    (ScoreQ("how much?", ["a", "b", "c"]), 1.5), (ScoreQ("how much?", ["a", "b", "c"]), "1"),
    (ChoiceQ("which?", CATS), "plastic"), (ChoiceQ("which?", CATS), 1)])
def test_review_refuses_wrongly_typed_answers(q, bad):
    store = MemoryStore()
    sid = store.add_suggestion(_row_for(q, None))
    with pytest.raises(ValueError):
        logic.review(store, sid, "gab", answer=bad)
    assert store.get(sid)["status"] == "pending"


def test_review_takes_good_typed_answers_and_rounds_a_score_on_accept():
    store = MemoryStore()
    score = ScoreQ("how much?", ["a", "b", "c", "d"])
    sid = store.add_suggestion(_row_for(score, 2.6))
    assert logic.review(store, sid, "gab", accept=True)["owner_answer"] == 3
    sid = store.add_suggestion(_row_for(score, 2.6))
    row = logic.review(store, sid, "gab", answer=2.0)
    assert row["owner_answer"] == 2 and type(row["owner_answer"]) is int and row["status"] == "changed"
    sid = store.add_suggestion(_row_for(NoulQ("is it?"), True))
    assert logic.review(store, sid, "gab", answer=False)["owner_answer"] is False


def test_reask_keeps_the_owners_confirmation():
    client, store, cfg, make = _setup()
    sid = logic.answer(store, cfg, make, {"name": "x"}, {"a": _q()})["a"]["suggestion_id"]
    logic.review(store, sid, "gab", answer="wood")
    row = logic.reask(store, cfg, make, sid)
    assert store.confirmed("mat.category") == {"stone_brick": "wood"}
    assert row["status"] == "changed" and row["owner_answer"] == "wood" and row["reviewed_by"] == "gab"
    assert row["reviewed_at"] is not None and row["answer"] == "glass" and row["source"] == "jev"


def test_daily_cap_is_checked_before_each_batch():
    client, store, cfg, make = _setup(daily_token_cap=100, batch=1)
    qs = {"a": ChoiceQ("first?", CATS), "b": ChoiceQ("second?", CATS)}
    out = logic.answer(store, cfg, make, {"name": "x"}, qs)
    assert len(client.calls) == 1 and store.tokens_today() == 107
    assert out["a"]["source"] == "jev" and out["b"]["source"] == "none" and out["b"]["error"] == "daily cap"
    assert len(store.list()) == 1


def test_full_state_is_kept_for_reask_and_a_failed_reask_raises_without_the_message():
    client, store, cfg, make = _setup()
    state = {"text": "x" * 3000}
    sid = logic.answer(store, cfg, make, state, {"a": _q()})["a"]["suggestion_id"]
    row = store.get(sid)
    assert len(row["state"]) == logic.STATE_MAX and row["state_json"] == state
    logic.reask(store, cfg, make, sid)
    assert client.calls[1]["state"] == state
    client.error = RuntimeError(f"401 bad key {FAKE_KEY}")
    with pytest.raises(RuntimeError) as exc:
        logic.reask(store, cfg, make, sid)
    assert FAKE_KEY not in str(exc.value) and str(exc.value) == "RuntimeError"
    assert store.get(sid)["answer"] == "glass"


def test_import_normalises_a_text_state_and_counts_invalid_items():
    client, store, cfg, make = _setup(enabled=False)
    q = _q("s")
    good = {"question": wire.question_to_json(q), "state": "just text", "answer": "metal", "confidence": 0.9}
    bad = {"question": wire.question_to_json(q), "state": "other", "answer": "plastic", "confidence": 0.9}
    broken = {"question": wire.question_to_json(q), "state": "third", "answer": "metal"}
    assert logic.import_items(store, [good, bad, broken]) == {"added": 1, "skipped": 0, "invalid": 2}
    assert store.list()[0]["state_json"] == {"text": "just text"}
    out = logic.answer(store, cfg, make, "just text", {"a": q})
    assert out["a"]["answer"] == "metal" and out["a"]["source"] == "pilot-import"


def test_latest_review_wins_across_two_rows():
    client, store, cfg, make = _setup()
    a = logic.answer(store, cfg, make, {"name": "a"}, {"q": _q("same")})["q"]["suggestion_id"]
    b = logic.answer(store, cfg, make, {"name": "b"}, {"q": _q("same")})["q"]["suggestion_id"]
    logic.review(store, a, "gab", answer="wood")
    logic.review(store, b, "gab", answer="metal")
    store.update_suggestion(a, reviewed_at="2999-01-01T00:00:00+00:00")
    assert store.owner_answer("mat.category", "same") == "wood"
    assert store.confirmed("mat.category") == {"same": "wood"}
    store.update_suggestion(b, reviewed_at="3000-01-01T00:00:00+00:00")
    assert store.owner_answer("mat.category", "same") == "metal"


def test_empty_qtype_or_subject_skips_the_owner_lookup():
    class Spy(MemoryStore):
        asked = 0

        def owner_answer(self, qtype, subject):
            Spy.asked += 1
            return super().owner_answer(qtype, subject)

    client, _, cfg, make = _setup()
    store = Spy()
    qs = {"a": ChoiceQ("no meta?", CATS), "b": ChoiceQ("no subject?", CATS, qtype="mat.category"),
          "c": ChoiceQ("no type?", CATS, subject="s")}
    logic.answer(store, cfg, make, {"name": "x"}, qs)
    assert Spy.asked == 0 and len(client.calls) == 1


def test_jev_off_never_builds_a_decider():
    def boom():
        raise AssertionError("make_decider must not be called")

    _, store, cfg, _ = _setup(enabled=False)
    out = logic.answer(store, cfg, boom, {"name": "x"}, {"a": _q()})
    assert out["a"]["error"] == "jev off"
    cfg_cap = Settings(jev_enabled=True, daily_token_cap=10)
    store.add_call({"input_tokens": 10, "output_tokens": 0, "at": logic._now()})
    assert logic.answer(store, cfg_cap, boom, {"name": "x"}, {"a": _q()})["a"]["error"] == "daily cap"
