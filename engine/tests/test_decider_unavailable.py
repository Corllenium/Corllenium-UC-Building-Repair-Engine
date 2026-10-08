"""The `Unavailable` marker of the Decider (P1-D2 Part 1): a provider says "I could not answer now" per
question, which is logged as an `error` event, never cached, never counted, and falls through to the owner
queue. `None` stays a real, cacheable "no answer". Fake providers only."""
import json

from engine.decide.decider import (
    UNAVAILABLE,
    Answer,
    Decider,
    Question,
    QuestionType,
    Unavailable,
    question_key,
)

T = QuestionType("inv.building", "choice", "Which building?", (("BRS", "b"), ("CHTM", "c")))


def _decider(tmp_path, providers):
    return Decider([T], list(providers), tmp_path / "log.jsonl", tmp_path / "cache.jsonl")


def _log(tmp_path):
    p = tmp_path / "log.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def _cache(tmp_path):
    p = tmp_path / "cache.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def _q(subject):
    return Question("inv.building", subject, {"name": subject})


class Scripted:
    """Answers from {subject: value}: a str is a CHTM/BRS answer, None a real miss, an Unavailable is passed on."""

    name = "jev"

    def __init__(self, table):
        self.table = table
        self.calls = []

    def answer(self, qt, questions):
        self.calls.append([q.subject for q in questions])
        out = []
        for q in questions:
            v = self.table[q.subject]
            if isinstance(v, str):
                v = Answer(q.qtype, q.subject, question_key(qt, q), v, 0.9, self.name, {v: 0.9}, False, None, 5)
            out.append(v)
        return out


def test_the_marker_caps_its_reason_at_200_characters():
    assert Unavailable("jev off").reason == "jev off"
    assert UNAVAILABLE == Unavailable() and UNAVAILABLE.reason == ""
    assert len(Unavailable("x" * 500).reason) == 200


def test_an_unavailable_result_is_asked_again_on_the_next_ask(tmp_path):
    p = Scripted({"G": Unavailable("jev off")})
    d = _decider(tmp_path, [p])
    (a,) = d.ask([_q("G")])
    assert (a.provider, a.accepted, a.suggestion) == ("queue", False, None)  # falls through to the owner queue
    d.ask([_q("G")])
    assert p.calls == [["G"], ["G"]]
    assert _cache(tmp_path) == []  # nothing was written for it
    assert [x.subject for x in d.owner_queue()] == ["G"]


def test_a_none_is_a_real_miss_and_is_not_asked_again(tmp_path):
    p = Scripted({"G": None})
    d = _decider(tmp_path, [p])
    d.ask([_q("G")])
    d.ask([_q("G")])
    assert p.calls == [["G"]]
    assert len(_cache(tmp_path)) == 1


def test_an_unavailable_mixed_with_real_answers_keeps_the_real_ones_cached(tmp_path):
    p = Scripted({"A": "CHTM", "B": Unavailable("daily cap"), "C": None})
    d = _decider(tmp_path, [p])
    answers = d.ask([_q("A"), _q("B"), _q("C")])
    assert answers[0].suggestion["answer"] == "CHTM" and answers[1].suggestion is None
    assert {(r["key"], r["hit"]) for r in _cache(tmp_path)} == {
        (question_key(T, _q("A")), True), (question_key(T, _q("C")), False)}
    d.ask([_q("A"), _q("B"), _q("C")])
    assert p.calls == [["A", "B", "C"], ["B"]]  # only the unavailable one is asked again


def test_unavailable_is_logged_as_an_error_event_with_a_capped_reason(tmp_path):
    url = "https://user:secret@vps.example/api/decide/ask?token=abc"
    p = Scripted({"G": Unavailable(url + " " + "z" * 400)})
    d = _decider(tmp_path, [p])
    d.ask([_q("G")])
    (err,) = [r for r in _log(tmp_path) if r["event"] == "error"]
    assert (err["provider"], err["qtype"], err["subject"], err["key"]) == (
        "jev", "inv.building", "G", question_key(T, _q("G")))
    assert err["reason"] == (url + " " + "z" * 400)[:200]  # stored as given, capped; nothing added
    assert len(err["reason"]) == 200
    assert "Unavailable" in err["error"]
    assert not any(r["event"] == "provider" for r in _log(tmp_path))  # never counts as a provider answer


def test_an_all_unavailable_batch_writes_nothing_to_the_cache_and_no_stats(tmp_path):
    p = Scripted({"A": UNAVAILABLE, "B": Unavailable("jev off")})
    d = _decider(tmp_path, [p])
    d.ask([_q("A"), _q("B")])
    assert not (tmp_path / "cache.jsonl").exists()
    st = d.stats("inv.building")
    assert st["decisions"] == 0 and st["agreement"] is None
    d.record_owner("inv.building", "A", "BRS")
    assert d.stats("inv.building")["decisions"] == 0  # no provider answer was waiting
