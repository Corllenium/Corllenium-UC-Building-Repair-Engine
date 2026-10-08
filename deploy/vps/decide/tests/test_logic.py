"""The service core (decide_service.logic) with MemoryStore and a fake Jev client: no network, no real key."""
import json
from types import SimpleNamespace

import pytest

from decide_service import logic
from decide_service.settings import Settings
from decide_service.store import MemoryStore
from engine.decide import wire
from engine.decide.jev import ChoiceQ, JevDecider, ScoreQ

FAKE_KEY = "ts-FAKE-KEY-0123456789-do-not-leak"
CATS = {"glass": None, "metal": None, "wood": None}


class FakeClient:
    """Answers every Choice with its first label (confidence 0.95); records each call."""

    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def system_one(self, state, questions):
        self.calls.append({"state": state, "questions": dict(questions)})
        if self.error is not None:
            raise self.error
        answers = {}
        for qid, spec in questions.items():
            label = next(iter(spec.criteria))
            answers[qid] = SimpleNamespace(type="choice", choice=label, confidence=0.95, probabilities={label: 0.95})
        return SimpleNamespace(answers=answers, model="jev-fake",
                               usage=SimpleNamespace(input_tokens=100, output_tokens=7))


def _setup(enabled=True, error=None, **cfg):
    client = FakeClient(error)
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
    assert logic.import_items(store, [item]) == {"added": 1, "skipped": 0}
    other = {**item, "state": {"name": "y"}}
    assert logic.import_items(store, [item, other]) == {"added": 1, "skipped": 1}
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
    assert len(client.calls) == 2 and row["answer"] == "glass" and row["status"] == "pending"
    assert row["owner_answer"] is None and row["reviewed_by"] is None
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
