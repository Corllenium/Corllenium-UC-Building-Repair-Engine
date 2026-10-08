"""RemoteDecider (engine/decide/remote.py): the HTTP client of the VPS service `uc-fixer-decide`.

No real network: every test talks to a stdlib `http.server` on 127.0.0.1 in a thread. The password is a fake
value in the environment or in a tmp_path file; an autouse fixture points the default `.env` at a file that
does not exist, so no test can open the repo's real one.
"""
import base64
import json
import logging
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from engine.decide import jev, wire
from engine.decide.jev import ChoiceQ, Decision, NoulQ, ScoreQ, classify_materials
from engine.decide.remote import RemoteDecider, pull_confirmed

PW = "pw-FAKE-0123456789-do-not-leak"
AUTH = "Basic " + base64.b64encode(f"uc-engine:{PW}".encode()).decode()


@pytest.fixture(autouse=True)
def _no_real_env(tmp_path_factory, monkeypatch):
    monkeypatch.setattr(jev, "DEFAULT_ENV_FILE", tmp_path_factory.mktemp("noenv") / "absent.env")
    monkeypatch.delenv("UC_DECIDE_PASSWORD", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


class Server:
    """A local server that records each request and answers with `reply(request) -> (status, body)`."""

    def __init__(self, reply):
        self.requests = []
        self.reply = reply
        self.stop = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                req = {"method": self.command, "path": self.path, "headers": dict(self.headers.items()),
                       "body": json.loads(raw) if raw else None}
                outer.requests.append(req)
                status, body, *extra = outer.reply(req)
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                for k, v in (extra[0] if extra else {}).items():
                    self.send_header(k, v)
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
        self.thread = threading.Thread(target=lambda: self.httpd.serve_forever(0.05), daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def serve():
    servers = []

    def make(reply):
        s = Server(reply)
        servers.append(s)
        return s
    yield make
    for s in servers:
        s.close()


def _answers_for(req):
    """A canned reply that answers every question by its kind, as the service does."""
    out = {}
    for i, (qid, q) in enumerate(req["body"]["questions"].items()):
        if q["kind"] == "noul":
            d = Decision(True, 0.9, {"yes": 0.9, "no": 0.1}, "jev", True)
        elif q["kind"] == "choice":
            label = next(iter(q["criteria"]))
            d = Decision(label, 0.95, {label: 0.95}, "jev", True)
        else:
            d = Decision(3.0, 0.4, {"3": 0.4}, "jev", False)
        out[qid] = wire.decision_to_json(d, suggestion_id=100 + i)
    return 200, {"answers": out}


QUESTIONS = {
    "a": NoulQ("Is it glass?", qtype="mat.trim", subject="m1"),
    "b": ChoiceQ("Which kind?", {"glass": "see-through", "wood": None}, qtype="mat.category", subject="m1"),
    "c": ScoreQ("How rough?", ["smooth", "medium", "rough"], qtype="x.rough", subject="m1"),
}


def _decider(url, **kw):
    kw.setdefault("password", PW)
    return RemoteDecider(url, **kw)


# ------------------------------------------------------------------------------------- the helper


def test_read_env_var_takes_the_named_variable_and_nothing_else(tmp_path):
    p = tmp_path / ".env"
    p.write_text("OTHER_SECRET=zzz\nUC_DECIDE_PASSWORD='abc 123'\nTYPESAFE_API_KEY=key1\n", encoding="utf-8")
    assert jev.read_env_var(p, "UC_DECIDE_PASSWORD") == "abc 123"
    assert jev.read_env_var(p, "TYPESAFE_API_KEY") == "key1"
    assert jev.read_env_var(p, "UC_DECIDE") is None                      # a prefix is not the variable
    assert jev.read_env_var(p, "NOPE") is None
    assert jev.read_env_var(tmp_path / "absent.env", "UC_DECIDE_PASSWORD") is None
    p.write_text("export UC_DECIDE_PASSWORD=a # note\nUC_DECIDE_PASSWORD=last\n", encoding="utf-8")
    assert jev.read_env_var(p, "UC_DECIDE_PASSWORD") == "last"           # the last line wins, as dotenv does
    p.write_text("UC_DECIDE_PASSWORD=\n", encoding="utf-8")
    assert jev.read_env_var(p, "UC_DECIDE_PASSWORD") is None


def test_read_env_key_still_reads_the_typesafe_key(tmp_path):
    p = tmp_path / ".env"
    p.write_text("UC_DECIDE_PASSWORD=pw\nTYPESAFE_API_KEY=abc123\n", encoding="utf-8")
    assert jev.read_env_key(p) == "abc123"


# ------------------------------------------------------------------------------------- ask


def test_ask_posts_the_wire_questions_with_basic_auth_and_maps_the_answers_back(serve):
    s = serve(_answers_for)
    dec = _decider(s.url)
    out = dec.ask({"task": "t"}, QUESTIONS)
    assert len(s.requests) == 1
    r = s.requests[0]
    assert (r["method"], r["path"]) == ("POST", "/api/decide/ask")
    assert r["headers"]["Authorization"] == AUTH
    assert r["headers"]["Content-Type"].startswith("application/json")
    assert r["body"] == {"state": {"task": "t"},
                         "questions": {qid: wire.question_to_json(q) for qid, q in QUESTIONS.items()}}
    assert set(out) == {"a", "b", "c"}
    assert out["a"] == Decision(True, 0.9, {"yes": 0.9, "no": 0.1}, "jev", True)
    assert out["b"] == Decision("glass", 0.95, {"glass": 0.95}, "jev", True)
    assert out["c"].accepted is False and out["c"].source == "jev" and out["c"].answer == 3.0
    assert dec.available is True


def test_a_text_state_is_sent_as_a_dict_like_jevdecider_does(serve):
    s = serve(_answers_for)
    _decider(s.url).ask("some text", {"a": QUESTIONS["a"]})
    assert s.requests[0]["body"]["state"] == {"text": "some text"}


def test_a_base_url_with_a_trailing_slash_works(serve):
    s = serve(_answers_for)
    _decider(s.url + "/").ask({}, {"a": QUESTIONS["a"]})
    assert s.requests[0]["path"] == "/api/decide/ask"


def test_calls_record_one_entry_per_http_call(serve):
    s = serve(_answers_for)
    dec = _decider(s.url)
    dec.ask({}, QUESTIONS)
    assert len(dec.calls) == 1
    c = dec.calls[0]
    assert c["ok"] is True and c["status"] == 200 and c["error"] == "" and c["questions"] == 3
    assert isinstance(c["latency_s"], float) and 0 <= c["latency_s"] < 5


def test_the_server_may_mark_a_decision_source_none_or_error_and_it_is_kept(serve):
    def reply(req):
        return 200, {"answers": {
            "a": wire.decision_to_json(Decision(None, 0.0, {}, "none", False)),
            "b": wire.decision_to_json(Decision(None, 0.0, {}, "error", False, "RuntimeError"))}}
    s = serve(reply)
    out = _decider(s.url).ask({}, {"a": QUESTIONS["a"], "b": QUESTIONS["b"]})
    assert (out["a"].source, out["a"].accepted) == ("none", False)
    assert (out["b"].source, out["b"].error, out["b"].accepted) == ("error", "RuntimeError", False)


def test_a_missing_answer_or_a_malformed_body_is_an_error_decision(serve):
    s = serve(lambda req: (200, {"answers": {"a": wire.decision_to_json(Decision(True, 0.9, {}, "jev", True))}}))
    out = _decider(s.url).ask({}, {"a": QUESTIONS["a"], "b": QUESTIONS["b"]})
    assert out["a"].accepted is True
    assert (out["b"].source, out["b"].error, out["b"].accepted) == ("error", "MissingAnswer", False)
    for body in (b"not json", b"[1, 2]", b'{"nope": 1}'):
        s2 = serve(lambda req, body=body: (200, body))
        out = _decider(s2.url).ask({}, {"a": QUESTIONS["a"]})
        assert out["a"].source == "error" and out["a"].accepted is False and out["a"].error


# ------------------------------------------------------------------------------------- failures


def test_a_server_that_sleeps_past_the_timeout_gives_none_within_the_timeout_plus_a_second(serve):
    def slow(req):
        s.stop.wait(5)
        return 200, {"answers": {}}
    s = serve(slow)
    dec = _decider(s.url, timeout=0.5)
    t0 = time.perf_counter()
    out = dec.ask({}, QUESTIONS)
    took = time.perf_counter() - t0
    assert took <= 0.5 + 1.0
    assert set(out) == {"a", "b", "c"}
    for d in out.values():
        assert d.source == "none" and d.accepted is False and d.error and d.answer is None
    assert len(s.requests) == 1
    assert dec.calls[0]["ok"] is False and dec.calls[0]["status"] is None and dec.calls[0]["error"]


def test_a_server_that_drips_bytes_still_ends_at_the_timeout(serve):
    """urllib's timeout is per socket read; the client must also keep a whole-call deadline."""
    class Drip(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            for _ in range(100):
                try:
                    self.wfile.write(b" ")
                    self.wfile.flush()
                except OSError:
                    return
                time.sleep(0.2)

        def log_message(self, *a):
            pass
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Drip)
    httpd.daemon_threads = True
    threading.Thread(target=lambda: httpd.serve_forever(0.05), daemon=True).start()
    try:
        dec = _decider(f"http://127.0.0.1:{httpd.server_address[1]}", timeout=0.6)
        t0 = time.perf_counter()
        out = dec.ask({}, {"a": QUESTIONS["a"]})
        assert time.perf_counter() - t0 <= 0.6 + 1.0
        assert out["a"].source == "none" and out["a"].accepted is False and out["a"].error
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_refused_connection_gives_none_with_the_class_name_only():
    dec = _decider("http://127.0.0.1:9", timeout=2)       # port 9 (discard): nothing listens
    out = dec.ask({}, {"a": QUESTIONS["a"]})
    assert out["a"].source == "none" and out["a"].accepted is False
    assert out["a"].error.isidentifier()                  # a bare class name: no text, no URL
    assert dec.calls[0]["ok"] is False and dec.calls[0]["error"] == out["a"].error


@pytest.mark.parametrize("status", [400, 401, 403, 409, 422, 500, 502])
def test_a_non_2xx_gives_error_decisions_and_one_request_only(serve, status):
    s = serve(lambda req: (status, {"detail": "nope " + PW}))     # even a body that echoes the password
    dec = _decider(s.url)
    out = dec.ask({}, QUESTIONS)
    assert len(s.requests) == 1                                   # no retries
    assert set(out) == {"a", "b", "c"}
    for d in out.values():
        assert d.source == "error" and d.error == f"HTTP {status}" and d.accepted is False and d.answer is None
    assert dec.calls[0]["ok"] is False and dec.calls[0]["status"] == status
    assert dec.calls[0]["error"] == f"HTTP {status}"
    assert PW not in json.dumps(dec.calls)


def test_a_redirect_is_not_followed_and_is_an_error(serve):
    s = serve(lambda req: (302, b"", {"Location": "/elsewhere"}))
    out = _decider(s.url).ask({}, {"a": QUESTIONS["a"]})
    assert len(s.requests) == 1
    assert out["a"].source == "error" and out["a"].error == "HTTP 302"


def test_a_question_past_the_limits_raises_before_any_request(serve):
    s = serve(_answers_for)
    too_many = ScoreQ("x", [str(i) for i in range(jev.MAX_SCORE_LEVELS + 1)])
    with pytest.raises(ValueError):
        _decider(s.url).ask({}, {"bad": too_many})
    with pytest.raises(ValueError):
        RemoteDecider(s.url).ask({}, {"bad": too_many})            # also with no password
    assert s.requests == []


# ------------------------------------------------------------------------------------- the password


def test_with_no_password_it_is_unavailable_and_sends_nothing(serve, tmp_path):
    s = serve(_answers_for)
    env = tmp_path / ".env"
    env.write_text("TYPESAFE_API_KEY=somekey\nOTHER=1\n", encoding="utf-8")
    dec = RemoteDecider(s.url, env_file=env)
    assert dec.available is False
    out = dec.ask({}, QUESTIONS)
    assert set(out) == {"a", "b", "c"}
    for d in out.values():
        assert d.source == "none" and d.accepted is False and d.answer is None
    assert s.requests == [] and dec.calls == []
    assert RemoteDecider(s.url, env_file=tmp_path / "absent.env").available is False


def test_the_environment_password_wins_over_the_env_file_and_the_file_gives_only_that_line(serve, tmp_path,
                                                                                       monkeypatch):
    s = serve(_answers_for)
    env = tmp_path / ".env"
    env.write_text("OTHER_SECRET=zzz\nUC_DECIDE_PASSWORD=from-file\nTYPESAFE_API_KEY=k\n", encoding="utf-8")
    dec = RemoteDecider(s.url, env_file=env)
    assert dec.available is True
    dec.ask({}, {"a": QUESTIONS["a"]})
    assert s.requests[-1]["headers"]["Authorization"] == \
        "Basic " + base64.b64encode(b"uc-engine:from-file").decode()
    import os
    assert "UC_DECIDE_PASSWORD" not in os.environ and "OTHER_SECRET" not in os.environ
    monkeypatch.setenv("UC_DECIDE_PASSWORD", "from-env")
    RemoteDecider(s.url, env_file=env).ask({}, {"a": QUESTIONS["a"]})
    assert s.requests[-1]["headers"]["Authorization"] == \
        "Basic " + base64.b64encode(b"uc-engine:from-env").decode()


def test_the_password_never_appears_in_repr_logs_exceptions_or_calls(serve, caplog, tmp_path):
    caplog.set_level(logging.DEBUG)
    s_ok = serve(_answers_for)
    s_401 = serve(lambda req: (401, {"detail": PW}))
    s_500 = serve(lambda req: (500, b"boom " + PW.encode()))
    decs = [_decider(s_ok.url), _decider(s_401.url), _decider(s_500.url), _decider("http://127.0.0.1:9", timeout=1)]
    outs = [d.ask({}, QUESTIONS) for d in decs]
    seen = [repr(d) for d in decs] + [str(d) for d in decs] + [json.dumps(d.calls) for d in decs]
    seen += [repr(o) for o in outs]
    seen.append(caplog.text)
    # exception text: the constructor and pull_confirmed failures
    for fn in (lambda: RemoteDecider("ftp://example.com", password=PW),
               lambda: RemoteDecider("http://example.com", password=PW),
               lambda: pull_confirmed(s_401.url, "mat.category", tmp_path, password=PW),
               lambda: pull_confirmed("http://127.0.0.1:9", "mat.category", tmp_path, password=PW, timeout=1)):
        with pytest.raises(Exception) as ei:
            fn()
        seen.append(repr(ei.value) + str(ei.value))
    for text in seen:
        assert PW not in text
    assert repr(decs[0]).startswith("RemoteDecider(") and "available=True" in repr(decs[0])
    assert base64.b64encode(f"uc-engine:{PW}".encode()).decode() not in "".join(seen)


def test_a_url_with_userinfo_is_refused_without_echoing_it():
    for url in (f"https://uc-engine:{PW}@example.com", "https://someone@example.com", f"http://:{PW}@127.0.0.1:1"):
        with pytest.raises(ValueError) as ei:
            RemoteDecider(url, password=PW)
        assert PW not in str(ei.value) and "someone" not in str(ei.value)


def test_calls_record_the_real_2xx_status(serve):
    s = serve(lambda req: (201, _answers_for(req)[1]))
    dec = _decider(s.url)
    out = dec.ask({}, {"a": QUESTIONS["a"]})
    assert out["a"].accepted is True
    assert dec.calls[0]["status"] == 201 and dec.calls[0]["ok"] is True


def test_accepted_is_true_only_for_the_json_true(serve):
    base = wire.decision_to_json(Decision(True, 0.9, {}, "jev", True))
    for value in ("false", "true", "False", 1, "yes", None, 0):
        assert wire.decision_from_json({**base, "accepted": value}).accepted is False
    assert wire.decision_from_json({**base, "accepted": True}).accepted is True
    s = serve(lambda req: (200, {"answers": {"a": {**base, "accepted": "true"}}}))
    assert _decider(s.url).ask({}, {"a": QUESTIONS["a"]})["a"].accepted is False


def test_basic_auth_is_refused_over_plain_http_to_a_remote_host():
    with pytest.raises(ValueError):
        RemoteDecider("http://example.com", password=PW)
    with pytest.raises(ValueError):
        RemoteDecider("ftp://example.com", password=PW)
    RemoteDecider("https://example.com", password=PW)                 # https is the normal case
    RemoteDecider("http://localhost:8190", password=PW)               # loopback may be plain


# ------------------------------------------------------------------------------------- pull_confirmed


def test_pull_confirmed_writes_the_subject_answer_file(serve, tmp_path):
    s = serve(lambda req: (200, {"type": "mat.category", "answers": {"stone_1": "stone", "oak": "wood"}}))
    out = tmp_path / "confirmed"
    path = pull_confirmed(s.url, "mat.category", out, password=PW)
    assert path == out / "mat.category.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"stone_1": "stone", "oak": "wood"}
    r = s.requests[0]
    assert (r["method"], r["path"]) == ("GET", "/api/decide/confirmed?type=mat.category")
    assert r["headers"]["Authorization"] == AUTH


def test_pull_confirmed_quotes_the_type_and_refuses_a_path_like_type(serve, tmp_path):
    s = serve(lambda req: (200, {"type": "x", "answers": {}}))
    for bad in ("../evil", "a/b", "a\\b", "", "..", "x y"):
        with pytest.raises(ValueError):
            pull_confirmed(s.url, bad, tmp_path, password=PW)
    assert s.requests == []
    assert list(tmp_path.iterdir()) == []


def test_pull_confirmed_fails_loudly_and_writes_nothing(serve, tmp_path):
    s = serve(lambda req: (403, {"detail": "no"}))
    with pytest.raises(RuntimeError, match="HTTP 403"):
        pull_confirmed(s.url, "mat.category", tmp_path / "out", password=PW)
    s2 = serve(lambda req: (200, {"type": "t", "answers": [1]}))
    with pytest.raises(RuntimeError):
        pull_confirmed(s2.url, "mat.category", tmp_path / "out", password=PW)
    with pytest.raises(RuntimeError, match="UC_DECIDE_PASSWORD"):
        pull_confirmed(s.url, "mat.category", tmp_path / "out", env_file=tmp_path / "absent.env")
    assert not (tmp_path / "out" / "mat.category.json").exists()


# ------------------------------------------------------------------------------------- the pipeline


def test_classify_materials_works_unchanged_with_a_remote_decider(serve):
    s = serve(_answers_for)
    rows = classify_materials([{"name": "oak_planks", "texture": "oak.png", "kd": [0.5, 0.4, 0.2]}, "stone_1"],
                              _decider(s.url))
    assert [r["name"] for r in rows] == ["oak_planks", "stone_1"]
    assert rows[0]["category"].answer == "glass" and rows[0]["category"].source == "jev"
    assert rows[0]["trim"].answer is True
    assert len(s.requests) == 1 and len(s.requests[0]["body"]["questions"]) == 4


def test_classify_materials_with_a_failing_server_gives_error_rows(serve):
    s = serve(lambda req: (500, {}))
    rows = classify_materials(["oak"], _decider(s.url))
    assert rows[0]["category"].source == "error" and rows[0]["trim"].accepted is False


# ------------------------------------------------------------------------------------- the CLI


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """The folder decide-pull may write to: a tmp one, never the repo's data/."""
    from engine import cli
    d = tmp_path / "repo" / "data"
    d.mkdir(parents=True)
    monkeypatch.setattr(cli, "DATA_DIR", d)
    monkeypatch.delenv("UC_DECIDE_URL", raising=False)
    return d


def test_cli_decide_pull_writes_the_file(serve, data_dir, monkeypatch, capsys):
    from engine.cli import main
    s = serve(lambda req: (200, {"type": "mat.category", "answers": {"oak": "wood"}}))
    monkeypatch.setenv("UC_DECIDE_PASSWORD", PW)
    out = data_dir / "c"
    assert main(["decide-pull", "--url", s.url, "--type", "mat.category", "--out", str(out)]) == 0
    assert json.loads((out / "mat.category.json").read_text(encoding="utf-8")) == {"oak": "wood"}
    assert PW not in capsys.readouterr().out


def test_cli_decide_pull_default_out_is_anchored_at_the_repo_data_dir(serve, data_dir, monkeypatch, tmp_path):
    from engine.cli import main
    s = serve(lambda req: (200, {"type": "t", "answers": {"k": "v"}}))
    monkeypatch.setenv("UC_DECIDE_PASSWORD", PW)
    monkeypatch.chdir(tmp_path)                                   # the working directory must not matter
    assert main(["decide-pull", "--url", s.url, "--type", "t"]) == 0
    assert json.loads((data_dir / "decide" / "confirmed" / "t.json").read_text(encoding="utf-8")) == {"k": "v"}
    assert not (tmp_path / "data").exists()


def test_cli_decide_pull_refuses_an_out_outside_the_repo_data_dir(serve, data_dir, monkeypatch, tmp_path, capsys):
    from engine.cli import main
    s = serve(lambda req: (200, {"type": "t", "answers": {}}))
    monkeypatch.setenv("UC_DECIDE_PASSWORD", PW)
    for bad in (tmp_path / "elsewhere", data_dir / ".." / "other", data_dir.parent, Path("/")):
        assert main(["decide-pull", "--url", s.url, "--type", "t", "--out", str(bad)]) == 2
        err = capsys.readouterr().err
        assert "error:" in err and "data" in err
    assert s.requests == [] and not (tmp_path / "elsewhere").exists()
    assert main(["decide-pull", "--url", s.url, "--type", "t", "--out", str(data_dir / "ok" / "deeper")]) == 0


def test_cli_decide_pull_url_falls_back_to_uc_decide_url_and_else_errors(serve, data_dir, monkeypatch, capsys):
    from engine.cli import main
    s = serve(lambda req: (200, {"type": "t", "answers": {}}))
    monkeypatch.setenv("UC_DECIDE_PASSWORD", PW)
    assert main(["decide-pull", "--type", "t"]) == 2
    assert "UC_DECIDE_URL" in capsys.readouterr().err and s.requests == []
    monkeypatch.setenv("UC_DECIDE_URL", s.url)
    assert main(["decide-pull", "--type", "t"]) == 0
    assert len(s.requests) == 1
    other = serve(lambda req: (200, {"type": "t", "answers": {}}))
    assert main(["decide-pull", "--type", "t", "--url", other.url]) == 0     # the flag wins
    assert len(other.requests) == 1 and len(s.requests) == 1


def test_cli_decide_pull_reads_the_password_line_of_the_env_file(serve, data_dir, tmp_path):
    from engine.cli import main
    s = serve(lambda req: (200, {"type": "t", "answers": {}}))
    env = tmp_path / "e.env"
    env.write_text("UC_DECIDE_PASSWORD=file-pw\n", encoding="utf-8")
    assert main(["decide-pull", "--url", s.url, "--type", "t", "--out", str(data_dir / "o"),
                 "--env-file", str(env)]) == 0
    assert s.requests[0]["headers"]["Authorization"] ==         "Basic " + base64.b64encode(b"uc-engine:file-pw").decode()


def test_cli_decide_pull_failure_returns_2_and_prints_no_secret(serve, data_dir, tmp_path, monkeypatch, capsys):
    from engine.cli import main
    s = serve(lambda req: (401, {"detail": PW}))
    monkeypatch.setenv("UC_DECIDE_PASSWORD", PW)
    assert main(["decide-pull", "--url", s.url, "--type", "t", "--out", str(data_dir / "o")]) == 2
    cap = capsys.readouterr()
    assert "HTTP 401" in cap.err and PW not in cap.out + cap.err
    monkeypatch.delenv("UC_DECIDE_PASSWORD")
    assert main(["decide-pull", "--url", s.url, "--type", "t", "--out", str(data_dir / "o"),
                 "--env-file", str(tmp_path / "absent.env")]) == 2
