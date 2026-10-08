"""AskProvider and sync_confirmed (engine/decide/providers.py): Jev (local `JevDecider` or the VPS
`RemoteDecider`) as a provider behind the Decider (P1-D2).

A fake decider object (no network) except the last section, which talks to a stdlib `http.server` on 127.0.0.1.
"""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from engine.decide import decider as decider_module
from engine.decide import jev, wire
from engine.decide.decider import (
    UNAVAILABLE,
    Decider,
    Question,
    QuestionType,
    Unavailable,
    question_key,
)
from engine.decide.jev import ChoiceQ, Decision, NoulQ, ScoreQ
from engine.decide.providers import AskProvider, sync_confirmed
from engine.decide.remote import RemoteDecider

T_FLOOR = QuestionType("inv.floor", "choice", "Which floor is this?", (("1", "first"), ("2", "second"), ("5", "fifth")))
T_DUP = QuestionType("inv.duplicate", "noul", "Is this group a duplicate?", ())
T_PRIO = QuestionType("review.priority", "score", "How urgent is this unit?", ("low", "mid", "high"))
TYPES = (T_FLOOR, T_DUP, T_PRIO)


@pytest.fixture(autouse=True)
def _no_real_env(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(jev, "DEFAULT_ENV_FILE", tmp_path_factory.mktemp("noenv") / "absent.env")
    monkeypatch.delenv("UC_DECIDE_PASSWORD", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


class FakeAsk:
    """Stands in for JevDecider / RemoteDecider: `.ask(state, questions) -> {qid: Decision}` and `.calls`."""

    def __init__(self, reply=None, tokens=None, ok=True, call_error=""):
        self.ok, self.call_error = ok, call_error  # the `ok`/`error` of the .calls entry each ask adds
        self.reply = reply or (lambda qid, q: Decision(None, 0.0, {}, "none", False, "jev off"))
        self.tokens = tokens  # (input, output) added to .calls on every ask, or None for no token data
        self.calls = []
        self.asked = []  # (state, questions) per ask

    def ask(self, state, questions):
        self.asked.append((state, dict(questions)))
        entry = {"questions": len(questions), "ok": self.ok}
        if not self.ok:
            entry["error"] = self.call_error
        if self.tokens:
            entry["input_tokens"], entry["output_tokens"] = self.tokens
        self.calls.append(entry)
        return {qid: self.reply(qid, q) for qid, q in questions.items()}


def _jev_reply(qid, q):
    if isinstance(q, NoulQ):
        return Decision(True, 0.9, {"yes": 0.9, "no": 0.1}, "jev", True)
    if isinstance(q, ChoiceQ):
        label = list(q.criteria)[-1]
        return Decision(label, 0.8, {label: 0.8, "1": 0.2}, "jev", True)
    return Decision(2.0, 0.7, {0: 0.1, 1: 0.2, 2: 0.7}, "jev", False)


def _fq(subject, **state):
    return Question("inv.floor", subject, state or {"name": subject})


# ------------------------------------------------------------------------------------- 1. the mapping


def test_choice_maps_to_a_choiceq_with_the_order_and_to_a_raw_label_answer():
    fake = FakeAsk(_jev_reply)
    (a,) = AskProvider("jev", fake).answer(T_FLOOR, [_fq("G1", name="G1")])
    ((state, qs),) = fake.asked
    assert state == {"name": "G1"}
    assert qs == {"0": ChoiceQ("Which floor is this?", {"1": "first", "2": "second", "5": "fifth"},
                               qtype="inv.floor", subject="G1")}
    assert list(qs["0"].criteria) == ["1", "2", "5"]  # order preserved
    assert (a.qtype, a.subject, a.answer, a.confidence) == ("inv.floor", "G1", "5", 0.8)
    assert a.key == question_key(T_FLOOR, _fq("G1", name="G1"))
    assert (a.provider, a.accepted, a.suggestion) == ("jev", False, None)
    assert a.probabilities == {"5": 0.8, "1": 0.2}


def test_noul_maps_to_a_noulq_and_a_bool_answer():
    fake = FakeAsk(_jev_reply)
    (a,) = AskProvider("jev", fake).answer(T_DUP, [Question("inv.duplicate", "G", {"n": 1})])
    assert fake.asked[0][1] == {"0": NoulQ("Is this group a duplicate?", qtype="inv.duplicate", subject="G")}
    assert a.answer is True and a.confidence == 0.9 and a.accepted is False
    assert a.probabilities == {"yes": 0.9, "no": 0.1}


def test_score_maps_to_a_scoreq_and_str_probability_keys():
    fake = FakeAsk(_jev_reply)
    (a,) = AskProvider("remote-jev", fake).answer(T_PRIO, [Question("review.priority", "U", {})])
    assert fake.asked[0][1] == {"0": ScoreQ("How urgent is this unit?", ["low", "mid", "high"],
                                            qtype="review.priority", subject="U")}
    assert a.answer == 2.0 and a.provider == "remote-jev"
    assert a.probabilities == {"0": 0.1, "1": 0.2, "2": 0.7}  # int keys become str
    assert all(isinstance(k, str) for k in a.probabilities)


def test_a_pilot_import_decision_is_mapped_like_a_jev_one():
    fake = FakeAsk(lambda qid, q: Decision("2", 0.99, {"2": 0.99}, "pilot-import", True))
    (a,) = AskProvider("jev", fake).answer(T_FLOOR, [_fq("G")])
    assert (a.answer, a.provider, a.accepted) == ("2", "jev", False)


# ------------------------------------------------------------------------------------- 2. grouping


def test_two_distinct_states_make_two_ask_calls_and_the_order_is_kept():
    def reply(qid, q):
        return Decision(q.subject[-1], 0.5, {}, "jev", False)
    fake = FakeAsk(reply)
    qs = [_fq("G1", site="a"), _fq("G2", site="b"), _fq("G5", site="a"), _fq("G2", site="b")]
    # states are compared as canonical JSON: key order does not make a new group
    qs.append(Question("inv.floor", "G1", {"z": 1, "y": 2}))
    qs.append(Question("inv.floor", "G1", {"y": 2, "z": 1}))
    out = AskProvider("jev", fake).answer(T_FLOOR, qs)
    assert len(fake.asked) == 3
    assert [s for s, _ in fake.asked] == [{"site": "a"}, {"site": "b"}, {"z": 1, "y": 2}]
    assert [set(q) for _, q in fake.asked] == [{"0", "2"}, {"1", "3"}, {"4", "5"}]  # qids are the indexes
    assert [a.subject for a in out] == ["G1", "G2", "G5", "G2", "G1", "G1"]
    assert [a.answer for a in out] == ["1", "2", "5", "2", "1", "1"]


# ------------------------------------------------------------------------------------- 3. sources


def test_owner_none_and_error_sources_and_an_exception_are_all_unavailable():
    table = {
        "0": Decision("5", 1.0, {}, "owner", True),
        "1": Decision(None, 0.0, {}, "none", False, "jev off"),
        "2": Decision(None, 0.0, {}, "error", False, "HTTP 409"),
        "3": Decision(None, 0.0, {}, "none", False, ""),
        "4": Decision(None, 0.0, {}, "error", False, "x" * 500),
    }
    fake = FakeAsk(lambda qid, q: table[qid])
    out = AskProvider("jev", fake).answer(T_FLOOR, [_fq(f"G{i}", n=0) for i in range(5)])
    assert out[0] is UNAVAILABLE or out[0] == UNAVAILABLE
    assert out[1] == Unavailable("jev off")
    assert out[2] == Unavailable("HTTP 409")
    assert out[3] == Unavailable("none")  # no error text: the source
    assert out[4].reason == "x" * 200
    assert not any(a is None for a in out)


def test_an_exception_in_ask_gives_unavailable_with_the_class_name_only():
    class Boom(FakeAsk):
        def ask(self, state, questions):
            if state.get("bad"):
                raise ConnectionError("https://user:pw@host/secret?token=abc")
            return super().ask(state, questions)

    fake = Boom(_jev_reply)
    out = AskProvider("jev", fake).answer(T_FLOOR, [_fq("A", bad=True), _fq("B", ok=1), _fq("C", bad=True)])
    # the first group raised: the breaker trips, so the other groups are not asked either
    assert out == [Unavailable("ConnectionError")] * 3
    assert fake.asked == []
    ok = AskProvider("jev", Boom(_jev_reply)).answer(T_FLOOR, [_fq("B", ok=1)])
    assert ok[0].answer == "5"
    assert "secret" not in repr(out) and "pw@" not in repr(out)


def test_a_missing_qid_in_the_reply_is_unavailable():
    fake = FakeAsk()
    fake.ask = lambda state, questions: {}
    (a,) = AskProvider("jev", fake).answer(T_FLOOR, [_fq("G")])
    assert isinstance(a, Unavailable)


# ------------------------------------------------------------------------------------- tokens


def test_tokens_are_the_sum_added_during_this_call_spread_evenly_over_the_answers():
    fake = FakeAsk(_jev_reply, tokens=(100, 50))
    fake.calls.append({"input_tokens": 9999, "output_tokens": 9999})  # an earlier call: not counted
    qs = [_fq("A", s=1), _fq("B", s=1), _fq("C", s=2)]  # 2 state groups -> 2 asks -> 300 tokens over 3 answers
    out = AskProvider("jev", fake).answer(T_FLOOR, qs)
    assert [a.tokens for a in out] == [100, 100, 100]


def test_tokens_treat_none_as_zero_and_no_data_gives_none():
    fake = FakeAsk(_jev_reply, tokens=(None, 40))
    (a,) = AskProvider("jev", fake).answer(T_FLOOR, [_fq("A")])
    assert a.tokens == 40
    no_data = FakeAsk(_jev_reply)  # a RemoteDecider call has no token keys
    (b,) = AskProvider("jev", no_data).answer(T_FLOOR, [_fq("A")])
    assert b.tokens is None


# ------------------------------------------------------------------------------------- 4. end to end


def _decider(tmp_path, providers):
    return Decider(list(TYPES), list(providers), tmp_path / "log.jsonl", tmp_path / "cache.jsonl")


def _log(tmp_path):
    p = tmp_path / "log.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_in_suggest_mode_a_jev_answer_is_the_suggestion_and_never_accepted(tmp_path):
    fake = FakeAsk(_jev_reply, tokens=(30, 12))
    d = _decider(tmp_path, [AskProvider("jev", fake)])
    (a,) = d.ask([_fq("G1")])
    assert (a.provider, a.accepted, a.answer) == ("queue", False, None)
    assert a.suggestion["provider"] == "jev" and a.suggestion["answer"] == "5"
    assert a.suggestion["confidence"] == 0.8
    (rec,) = [r for r in _log(tmp_path) if r["event"] == "provider"]
    assert rec["accepted"] is False and rec["tokens"] == 42
    # the same question again: the cache answers, jev is not asked a second time
    d.ask([_fq("G1")])
    assert len(fake.asked) == 1


# ------------------------------------------------------------------------------------- 5. jev off


def test_jev_off_is_asked_again_and_nothing_is_cached(tmp_path):
    fake = FakeAsk()  # none / "jev off" for everything
    d = _decider(tmp_path, [AskProvider("jev", fake)])
    (a,) = d.ask([_fq("G1")])
    assert (a.provider, a.accepted, a.suggestion) == ("queue", False, None)
    d.ask([_fq("G1")])
    assert len(fake.asked) == 2
    assert not (tmp_path / "cache.jsonl").exists()
    errs = [r for r in _log(tmp_path) if r["event"] == "error"]
    assert len(errs) == 2 and errs[0]["reason"] == "jev off" and errs[0]["provider"] == "jev"
    assert errs[0]["key"] == question_key(T_FLOOR, _fq("G1"))
    # once jev is back, the question is answered and then cached
    fake.reply = _jev_reply
    (b,) = d.ask([_fq("G1")])
    assert b.suggestion["answer"] == "5"
    assert (tmp_path / "cache.jsonl").exists()


# ------------------------------------------------------------------------------------- 6. the key


def test_the_decider_key_equals_the_wire_key_of_the_question_askprovider_builds():
    t_choice = QuestionType("inv.etage", "choice", "Welches Stockwerk? Größe ≥ 3 m — 日本語", (
        ("Erdgeschoß", "café ≈ 0 m"), ("1.", "erstes"), ("日本", "ü")))
    t_score = QuestionType("review.rating", "score", "Wie dringend? ½ Ω", ("niedrig", "mittel", "hoch ✓"))
    t_noul = QuestionType("inv.doppelt", "noul", "Ist das ein Duplikat? Zoë", ())
    for qt, kind in ((t_choice, "choice"), (t_score, "score"), (t_noul, "noul")):
        q = Question(qt.qtype, "Gruppe_é", {"name": "Gruppe_é", "größe": 3.5, "tags": ["ä", "ß"], "n": None})
        fake = FakeAsk(lambda qid, jq: Decision(None, 0.0, {}, "none", False, "jev off"))
        AskProvider("jev", fake).answer(qt, [q])
        ((state, qs),) = fake.asked
        (jq,) = qs.values()
        assert wire.question_to_json(jq)["kind"] == kind
        assert decider_module.question_key(qt, q) == wire.question_key(state, jq), kind


def test_the_answer_key_is_the_decider_question_key():
    fake = FakeAsk(_jev_reply)
    q = _fq("G", name="Ünï")
    (a,) = AskProvider("jev", fake).answer(T_FLOOR, [q])
    assert a.key == decider_module.question_key(T_FLOOR, q)


# ------------------------------------------------------------------------------------- 7. sync_confirmed


def _write_confirmed(folder, qtype, data):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{qtype}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_pulled_answers_become_owner_answers_and_a_second_sync_records_nothing(tmp_path):
    d = _decider(tmp_path, [])
    conf = tmp_path / "confirmed"
    _write_confirmed(conf, "inv.floor", {"G1": "5", "G2": "2"})
    _write_confirmed(conf, "inv.duplicate", {"D1": True})
    assert sync_confirmed(d, conf) == 3
    got = {a.subject: a for a in d.ask([_fq("G1"), _fq("G2"), Question("inv.duplicate", "D1", {})])}
    assert all(a.provider == "owner" and a.accepted is True for a in got.values())
    assert (got["G1"].answer, got["G2"].answer, got["D1"].answer) == ("5", "2", True)
    assert sync_confirmed(d, conf) == 0  # nothing new
    owner_rows = [r for r in _log(tmp_path) if r["event"] == "owner"]
    assert len(owner_rows) == 3
    # a changed answer is recorded again
    _write_confirmed(conf, "inv.floor", {"G1": "1", "G2": "2"})
    assert sync_confirmed(d, conf) == 1
    assert d.ask([_fq("G1")])[0].answer == "1"


def test_qtypes_limits_the_sync_to_the_named_types(tmp_path):
    d = _decider(tmp_path, [])
    conf = tmp_path / "confirmed"
    _write_confirmed(conf, "inv.floor", {"G1": "5"})
    _write_confirmed(conf, "inv.duplicate", {"D1": False})
    assert sync_confirmed(d, conf, ["inv.floor"]) == 1
    assert d.ask([Question("inv.duplicate", "D1", {})])[0].provider == "queue"
    assert sync_confirmed(d, conf, ["inv.floor", "inv.nothing"]) == 0  # a missing file is not an error


def test_an_answer_that_is_not_an_option_is_skipped_and_counted(tmp_path, caplog):
    d = _decider(tmp_path, [])
    conf = tmp_path / "confirmed"
    _write_confirmed(conf, "inv.floor", {"G1": "5", "G2": "99", "G3": True, "G4": None})
    _write_confirmed(conf, "inv.duplicate", {"D1": "yes"})
    with caplog.at_level("WARNING"):
        n = sync_confirmed(d, conf)
    assert n == 1 and n.skipped == 4
    assert d.ask([_fq("G2")])[0].provider == "queue"
    assert d.ask([_fq("G1")])[0].answer == "5"
    assert caplog.records  # it was logged


def test_a_file_for_an_unknown_type_or_not_a_mapping_is_skipped_without_error(tmp_path):
    d = _decider(tmp_path, [])
    conf = tmp_path / "confirmed"
    _write_confirmed(conf, "other.thing", {"X": "1"})
    _write_confirmed(conf, "inv.floor", ["not", "a", "mapping"])
    (conf / "inv.duplicate.json").write_text("{not json", encoding="utf-8")
    assert sync_confirmed(d, conf) == 0


def test_score_answers_are_checked_strictly(tmp_path):
    d = _decider(tmp_path, [])
    conf = tmp_path / "confirmed"
    _write_confirmed(conf, "review.priority", {
        "U1": 2, "U2": 2.0, "U3": "abc", "U4": 99, "U5": True, "U6": 1.5, "U7": -1, "U8": 0})
    n = sync_confirmed(d, conf)
    assert n == 3 and n.skipped == 5  # 2, 2.0 (stored as int 2) and 0 are recorded
    assert d.owner_answer("review.priority", "U1") == 2
    assert d.owner_answer("review.priority", "U2") == 2 and type(d.owner_answer("review.priority", "U2")) is int
    assert d.owner_answer("review.priority", "U8") == 0
    for subject in ("U3", "U4", "U5", "U6", "U7"):
        assert d.owner_answer("review.priority", subject) is None
    assert sync_confirmed(d, conf) == 0  # 2.0 and 2 are the same stored answer: nothing new


def test_a_missing_folder_gives_zero(tmp_path):
    d = _decider(tmp_path, [])
    assert sync_confirmed(d, tmp_path / "nowhere") == 0
    assert sync_confirmed(d, tmp_path / "nowhere", ["inv.floor"]) == 0


def test_owner_answer_reads_the_current_owner_state(tmp_path):
    d = _decider(tmp_path, [])
    assert d.owner_answer("inv.floor", "G1") is None
    d.record_owner("inv.floor", "G1", 5)
    assert d.owner_answer("inv.floor", "G1") == "5"
    d.record_owner("inv.duplicate", "D", False)
    assert d.owner_answer("inv.duplicate", "D") is False


# ------------------------------------------------------------------------------------- 8. RemoteDecider


class _Server:
    def __init__(self, reply):
        self.requests = []
        self.stop = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                req = {"method": self.command, "path": self.path, "body": json.loads(raw) if raw else None}
                outer.requests.append(req)
                status, body = reply(req, outer)
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except OSError:
                    pass

            do_GET = do_POST = _serve

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=lambda: self.httpd.serve_forever(0.05), daemon=True).start()

    def close(self):
        self.stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def serve():
    servers = []

    def make(reply):
        s = _Server(reply)
        servers.append(s)
        return s
    yield make
    for s in servers:
        s.close()


def _service_answers(req, _server):
    out = {}
    for qid, q in req["body"]["questions"].items():
        if q["kind"] == "choice":
            label = list(q["criteria"])[0]
            d = Decision(label, 0.95, {label: 0.95}, "jev", True)
        elif q["kind"] == "noul":
            d = Decision(False, 0.9, {"yes": 0.1, "no": 0.9}, "jev", True)
        else:
            d = Decision(1.0, 0.6, {"1": 0.6}, "jev", False)
        out[qid] = wire.decision_to_json(d, suggestion_id=1)
    return 200, {"answers": out}


def _remote(s, **kw):
    return RemoteDecider(s.url, password="pw-FAKE-do-not-leak", **kw)


def test_remote_answers_map_through_the_real_remote_decider(serve):
    s = serve(_service_answers)
    p = AskProvider("jev", _remote(s))
    out = p.answer(T_FLOOR, [_fq("G1", site="a"), _fq("G2", site="b")])
    assert [(a.answer, a.provider, a.accepted) for a in out] == [("1", "jev", False), ("1", "jev", False)]
    assert len(s.requests) == 2  # one POST per distinct state
    assert s.requests[0]["path"] == "/api/decide/ask"
    assert s.requests[0]["body"]["questions"]["0"]["criteria"] == {"1": "first", "2": "second", "5": "fifth"}
    (n,) = p.answer(T_DUP, [Question("inv.duplicate", "D", {})])
    assert n.answer is False
    assert all(a.tokens is None for a in out)  # a remote call has no token data


@pytest.mark.parametrize("status", [409, 500, 503])
def test_a_remote_error_status_is_unavailable_never_none(serve, status):
    s = serve(lambda req, srv: (status, {"detail": "no"}))
    out = AskProvider("jev", _remote(s)).answer(T_FLOOR, [_fq("G1")])
    assert out == [Unavailable(f"HTTP {status}")]


def test_a_remote_timeout_is_unavailable_never_none(serve):
    def slow(req, srv):
        srv.stop.wait(3)
        return 200, {"answers": {}}
    s = serve(slow)
    out = AskProvider("jev", _remote(s, timeout=0.3)).answer(T_FLOOR, [_fq("G1")])
    assert len(out) == 1 and isinstance(out[0], Unavailable) and out[0].reason == "TimeoutError"


def test_remote_decider_without_a_password_is_unavailable(serve):
    s = serve(_service_answers)
    out = AskProvider("jev", RemoteDecider(s.url, password=None)).answer(T_FLOOR, [_fq("G1")])
    assert out == [Unavailable("none")]
    assert s.requests == []


# ------------------------------------------------------------------------------------- circuit breaker


class _BlackHole:
    """A local socket that accepts connections and never replies; counts the connections."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}"
        self.accepted = []
        self._stop = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        self.sock.settimeout(0.05)
        while not self._stop:
            try:
                self.accepted.append(self.sock.accept()[0])
            except OSError:
                pass

    def close(self):
        self._stop = True
        for c in self.accepted:
            c.close()
        self.sock.close()


def _remote_to(url, **kw):
    return RemoteDecider(url, password="pw-FAKE-do-not-leak", **kw)


def test_a_hung_server_costs_one_timeout_for_many_states_and_one_request():
    hole = _BlackHole()
    try:
        p = AskProvider("jev", _remote_to(hole.url, timeout=0.5))
        qs = [_fq(f"G{i}", site=i) for i in range(5)]
        t0 = time.perf_counter()
        out = p.answer(T_FLOOR, qs)
        took = time.perf_counter() - t0
        time.sleep(0.2)
        assert took < 0.5 + 0.6  # about one timeout, not five
        assert out == [Unavailable("TimeoutError")] * 5
        assert len(hole.accepted) == 1
        assert p.down == "TimeoutError"
        # a later answer() on the tripped instance makes no request and returns at once
        t0 = time.perf_counter()
        again = p.answer(T_FLOOR, [_fq("H", site="new")])
        assert time.perf_counter() - t0 < 0.1
        assert again == [Unavailable("TimeoutError")]
        time.sleep(0.2)
        assert len(hole.accepted) == 1
    finally:
        hole.close()


def test_jev_off_on_one_group_does_not_stop_a_later_group_returning_a_pilot_import_hit():
    def reply(qid, q):
        if q.subject == "A":
            return Decision(None, 0.0, {}, "none", False, "jev off")
        return Decision("2", 0.9, {"2": 0.9}, "pilot-import", True)
    fake = FakeAsk(reply)
    p = AskProvider("jev", fake)
    out = p.answer(T_FLOOR, [_fq("A", s=1), _fq("B", s=2), _fq("C", s=3)])
    assert len(fake.asked) == 3 and p.down is None
    assert out[0] == Unavailable("jev off") and out[1].answer == "2" and out[2].answer == "2"
    fake2 = FakeAsk(lambda qid, q: Decision(None, 0.0, {}, "none", False, ""))  # a none with no error
    p2 = AskProvider("jev", fake2)
    p2.answer(T_FLOOR, [_fq("A", s=1), _fq("B", s=2)])
    assert len(fake2.asked) == 2 and p2.down is None
    fake3 = FakeAsk(lambda qid, q: Decision(None, 0.0, {}, "none", False, "daily cap"))
    p3 = AskProvider("jev", fake3)
    p3.answer(T_FLOOR, [_fq("A", s=1), _fq("B", s=2)])
    assert len(fake3.asked) == 2 and p3.down is None


@pytest.mark.parametrize("source,error", [("none", "URLError"), ("none", "TimeoutError"), ("error", "HTTP 503"),
                                          ("error", "HTTP 409")])
def test_a_failed_call_entry_trips_the_breaker_for_the_rest_of_the_call_and_later_calls(source, error):
    fake = FakeAsk(lambda qid, q: Decision(None, 0.0, {}, source, False, error), ok=False, call_error=error)
    p = AskProvider("jev", fake)
    out = p.answer(T_FLOOR, [_fq("A", s=1), _fq("B", s=2), _fq("C", s=3)])
    assert len(fake.asked) == 1 and p.down == error
    assert out == [Unavailable(error)] * 3
    p.answer(T_FLOOR, [_fq("D", s=4)])
    assert len(fake.asked) == 1


@pytest.mark.parametrize("error", ["UnmappedFloorKey", "MissingAnswer", "BadReply", "URLError"])
def test_a_per_decision_error_under_an_ok_call_never_trips_the_breaker(error):
    def reply(qid, q):
        if q.subject == "A":
            return Decision(None, 0.0, {}, "error", False, error)
        return Decision("2", 0.9, {"2": 0.9}, "jev", True)
    fake = FakeAsk(reply)  # every call entry is ok
    p = AskProvider("jev", fake)
    out = p.answer(T_FLOOR, [_fq("A", s=1), _fq("B", s=2), _fq("C", s=3), _fq("D", s=4)])
    assert p.down is None and len(fake.asked) == 4
    assert out[0] == Unavailable(error) and [a.answer for a in out[1:]] == ["2", "2", "2"]


def test_a_decider_with_no_new_call_entries_does_not_trip():
    fake = FakeAsk(lambda qid, q: Decision(None, 0.0, {}, "none", False, "URLError"))
    fake.ask = lambda state, questions: {qid: Decision(None, 0.0, {}, "none", False, "URLError")
                                         for qid in questions}  # adds nothing to .calls (no key, jev unavailable)
    p = AskProvider("jev", fake)
    out = p.answer(T_FLOOR, [_fq("A", s=1), _fq("B", s=2)])
    assert p.down is None and out == [Unavailable("URLError")] * 2


def test_a_real_http_5xx_trips_after_one_request(serve):
    s = serve(lambda req, srv: (503, {"detail": "no"}))
    p = AskProvider("jev", _remote(s))
    out = p.answer(T_FLOOR, [_fq(f"G{i}", site=i) for i in range(4)])
    assert len(s.requests) == 1 and p.down == "HTTP 503"
    assert out == [Unavailable("HTTP 503")] * 4


def test_an_exception_in_ask_trips_the_breaker_with_the_class_name():
    class Boom(FakeAsk):
        def ask(self, state, questions):
            self.asked.append((state, questions))
            raise ConnectionError("https://user:pw@host/secret")

    fake = Boom()
    p = AskProvider("jev", fake)
    out = p.answer(T_FLOOR, [_fq("A", s=1), _fq("B", s=2)])
    assert len(fake.asked) == 1 and p.down == "ConnectionError"
    assert out == [Unavailable("ConnectionError")] * 2


def test_a_group_with_a_mix_of_answers_and_errors_does_not_trip():
    def reply(qid, q):
        if q.subject == "A":
            return Decision(None, 0.0, {}, "error", False, "HTTP 500")
        return Decision("1", 0.9, {"1": 0.9}, "jev", True)
    fake = FakeAsk(reply)
    p = AskProvider("jev", fake)
    p.answer(T_FLOOR, [_fq("A", s=1), _fq("B", s=1), _fq("C", s=2)])
    assert len(fake.asked) == 2 and p.down is None
