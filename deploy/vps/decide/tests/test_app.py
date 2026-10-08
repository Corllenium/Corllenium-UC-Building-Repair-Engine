"""The HTTP app (decide_service.app): roles from X-Remote-User, error mapping, request shapes. MemoryStore and a
fake Jev client only: no network, no real key."""
import datetime as dt
import logging
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from decide_service.app import create_app
from decide_service.settings import Settings
from decide_service.store import MemoryStore
from engine.decide import wire
from engine.decide.jev import ChoiceQ, JevDecider, NoulQ, ScoreQ

FAKE_KEY = "ts-FAKE-KEY-0123456789-do-not-leak"
CATS = {"glass": None, "metal": None, "wood": None}
TEST_URL = os.environ.get("DECIDE_TEST_DATABASE_URL", "")
ENGINE = {"X-Remote-User": "uc-engine"}
OWNER = {"X-Remote-User": "gab"}
STATE = {"name": "stone_brick"}


class FakeClient:
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


_BACKEND = {"make": MemoryStore}


@pytest.fixture(autouse=True, params=["memory", "postgres"])
def backend(request):
    """Every test runs on MemoryStore, and on PostgresStore when DECIDE_TEST_DATABASE_URL is set (the throwaway
    container decide-test-pg, port 55432 only; the schema `decide` is dropped and recreated per test)."""
    if request.param == "memory":
        _BACKEND["make"] = MemoryStore
        yield
        return
    if not TEST_URL:
        pytest.skip("DECIDE_TEST_DATABASE_URL not set")
    assert ":55432/" in TEST_URL, "the test database is the throwaway container decide-test-pg on port 55432 only"
    import psycopg
    from decide_service.pgstore import PostgresStore

    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("drop schema if exists decide cascade")
    opened = []

    def make():
        s = PostgresStore(TEST_URL)
        s.ensure_schema()
        opened.append(s)
        return s

    _BACKEND["make"] = make
    try:
        yield
    finally:
        _BACKEND["make"] = MemoryStore
        for s in opened:
            s.close()


def _app(enabled=False, error=None, store=None, **cfg):
    client = FakeClient(error)
    store = _BACKEND["make"]() if store is None else store
    app = create_app(store, Settings(jev_enabled=enabled, **cfg), lambda: JevDecider(client=client))
    return TestClient(app), store, client


def _choice(subject="stone_brick"):
    return wire.question_to_json(ChoiceQ(f"Which category is {subject}?", CATS, qtype="mat.category", subject=subject))


def _ask(c, headers=ENGINE, questions=None, state=STATE):
    return c.post("/api/decide/ask", headers=headers,
                  json={"state": state, "questions": questions if questions is not None else {"a": _choice()}})


def _seed(c):
    """One pending suggestion made by Jev (needs Jev on)."""
    return _ask(c).json()["answers"]["a"]["suggestion_id"]


# ------------------------------------------------------------------------------------- roles


def test_no_header_is_401_everywhere():
    c, _, _ = _app()
    for method, url in [("post", "/api/decide/ask"), ("get", "/api/decide/suggestions"),
                        ("post", "/api/decide/review/1"), ("post", "/api/decide/reask/1"),
                        ("get", "/api/decide/confirmed?type=x"), ("post", "/api/decide/import"),
                        ("get", "/api/decide/health")]:
        assert getattr(c, method)(url).status_code == 401, url


def test_engine_cannot_review_reask_or_list():
    c, _, _ = _app()
    assert c.get("/api/decide/suggestions", headers=ENGINE).status_code == 403
    assert c.post("/api/decide/review/1", headers=ENGINE, json={"accept": True}).status_code == 403
    assert c.post("/api/decide/reask/1", headers=ENGINE).status_code == 403


def test_owner_cannot_ask_or_import():
    c, _, _ = _app()
    assert _ask(c, OWNER).status_code == 403
    assert c.post("/api/decide/import", headers=OWNER, json={"items": []}).status_code == 403


def test_unknown_user_is_403_even_for_either_endpoints():
    c, _, _ = _app()
    stranger = {"X-Remote-User": "mallory"}
    assert c.get("/api/decide/health", headers=stranger).status_code == 403
    assert c.get("/api/decide/confirmed?type=x", headers=stranger).status_code == 403
    assert c.get("/api/decide/suggestions", headers=stranger).status_code == 403


def test_role_is_checked_before_the_body():
    c, _, _ = _app()
    assert c.post("/api/decide/ask", headers=OWNER, json={"nonsense": 1}).status_code == 403


def test_extra_owner_logins_come_from_settings():
    c, _, _ = _app(owner_users=frozenset({"gab", "ana"}))
    assert c.get("/api/decide/suggestions", headers={"X-Remote-User": "ana"}).status_code == 200


# ------------------------------------------------------------------------------------- ask


def test_ask_jev_off_gives_none():
    c, store, client = _app(enabled=False)
    r = _ask(c)
    assert r.status_code == 200
    a = r.json()["answers"]["a"]
    assert a["source"] == "none" and a["error"] == "jev off" and a["accepted"] is False
    assert client.calls == [] and store.list() == []


def test_ask_jev_on_answers_and_stores_a_suggestion():
    c, store, client = _app(enabled=True)
    a = _ask(c).json()["answers"]["a"]
    assert a["answer"] == "glass" and a["source"] == "jev" and a["suggestion_id"] == store.list()[0]["id"]
    assert len(client.calls) == 1


def test_ask_eleven_level_score_is_400_with_the_message():
    c, _, client = _app(enabled=True)
    score = wire.question_to_json(ScoreQ("How many?", [f"l{i}" for i in range(11)], qtype="x", subject="y"))
    r = _ask(c, questions={"s": score})
    assert r.status_code == 400 and "at most 10 levels" in r.json()["detail"]
    assert client.calls == []


@pytest.mark.parametrize("questions", [
    {"a": "not an object"},
    {"a": {"kind": "weird", "instructions": "i"}},
    {"a": {"instructions": "i"}},                                       # no kind
    {"a": {"kind": "choice", "instructions": "i", "criteria": None}},   # no options
    {"a": {"kind": "score", "instructions": "i", "criteria": 5}},
    ["a list"],
])
def test_ask_bad_question_shapes_are_422(questions):
    c, _, client = _app(enabled=True)
    assert _ask(c, questions=questions).status_code == 422
    assert client.calls == []


def test_ask_bad_state_is_422():
    c, _, _ = _app()
    assert _ask(c, state=5).status_code == 422
    assert c.post("/api/decide/ask", headers=ENGINE, json={"questions": {}}).status_code == 422


def test_ask_daily_cap_gives_none_not_an_error():
    c, store, client = _app(enabled=True, daily_token_cap=10)
    store.add_call({"at": dt.datetime.now(dt.timezone.utc).isoformat(), "input_tokens": 50, "output_tokens": 0})
    a = _ask(c).json()["answers"]["a"]
    assert a["error"] == "daily cap" and client.calls == []


# ------------------------------------------------------------------------------------- suggestions


def test_suggestions_list_drops_key_and_state_columns_and_counts():
    c, _, _ = _app(enabled=True)
    _seed(c)
    r = c.get("/api/decide/suggestions", headers=OWNER)
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1 and body["counts"] == {"pending": 1, "accepted": 0, "changed": 0}
    item = body["items"][0]
    assert not ({"key", "state", "state_json"} & set(item))
    assert item["subject"] == "stone_brick" and item["answer"] == "glass" and item["status"] == "pending"


def test_suggestions_filters():
    c, _, _ = _app(enabled=True)
    _ask(c, questions={"a": _choice("stone_brick"), "b": _choice("oak_wood")})
    get = lambda **p: c.get("/api/decide/suggestions", headers=OWNER, params=p).json()["items"]
    assert len(get()) == 2
    assert [i["subject"] for i in get(q="oak")] == ["oak_wood"]
    assert get(type="other") == [] and len(get(type="mat.category")) == 2
    assert get(status="accepted") == [] and len(get(status="pending")) == 2
    assert len(get(min_conf=0.9)) == 2 and get(min_conf=0.99) == []


def test_suggestions_limit_and_offset_are_clamped_not_errors():
    c, _, _ = _app(enabled=True)
    _ask(c, questions={"a": _choice("s1"), "b": _choice("s2"), "c": _choice("s3")})
    get = lambda **p: c.get("/api/decide/suggestions", headers=OWNER, params=p)
    assert len(get(limit=2).json()["items"]) == 2
    assert [i["subject"] for i in get(limit=2, offset=2).json()["items"]] == ["s3"]
    assert len(get(limit=0).json()["items"]) == 1          # clamped up to 1
    assert len(get(limit=-5).json()["items"]) == 1
    r = get(limit=100000, offset=-3)                       # clamped to 500 / 0
    assert r.status_code == 200 and len(r.json()["items"]) == 3


def test_suggestions_limit_is_clamped_to_500_before_the_store(monkeypatch):
    c, store, _ = _app()
    seen = {}
    real = store.list
    store.list = lambda **kw: (seen.update(kw), real(**kw))[1]
    c.get("/api/decide/suggestions", headers=OWNER, params={"limit": 99999, "offset": -1})
    assert seen["limit"] == 500 and seen["offset"] == 0
    c.get("/api/decide/suggestions", headers=OWNER)
    assert seen["limit"] == 100


# ------------------------------------------------------------------------------------- review


def test_review_accept_and_change_then_confirmed():
    c, _, _ = _app(enabled=True)
    sid = _seed(c)
    r = c.post(f"/api/decide/review/{sid}", headers=OWNER, json={"accept": True})
    assert r.status_code == 200
    row = r.json()
    assert row["status"] == "accepted" and row["owner_answer"] == "glass" and row["reviewed_by"] == "gab"
    assert not ({"key", "state", "state_json"} & set(row))
    r = c.post(f"/api/decide/review/{sid}", headers=OWNER, json={"answer": "metal"})
    assert r.status_code == 200 and r.json()["status"] == "changed" and r.json()["owner_answer"] == "metal"
    conf = c.get("/api/decide/confirmed", headers=ENGINE, params={"type": "mat.category"})
    assert conf.status_code == 200 and conf.json() == {"type": "mat.category", "answers": {"stone_brick": "metal"}}


def test_review_not_an_option_is_422_and_unknown_id_is_404():
    c, _, _ = _app(enabled=True)
    sid = _seed(c)
    assert c.post(f"/api/decide/review/{sid}", headers=OWNER, json={"answer": "plastic"}).status_code == 422
    assert c.post(f"/api/decide/review/{sid}", headers=OWNER, json={"answer": None}).status_code == 422
    assert c.post(f"/api/decide/review/{sid}", headers=OWNER, json={}).status_code == 422
    assert c.post("/api/decide/review/999", headers=OWNER, json={"accept": True}).status_code == 404


# ------------------------------------------------------------------------------------- reask


def test_reask_jev_off_is_409():
    c, store, _ = _app(enabled=True)
    sid = _seed(c)
    off, _, _ = _app(enabled=False, store=store)
    r = off.post(f"/api/decide/reask/{sid}", headers=OWNER)
    assert r.status_code == 409 and r.json() == {"detail": "jev off"}


def test_reask_daily_cap_is_409():
    c, store, _ = _app(enabled=True, daily_token_cap=1)
    sid = _seed(c)                                          # the call used 107 tokens: over the cap of 1
    r = c.post(f"/api/decide/reask/{sid}", headers=OWNER)
    assert r.status_code == 409 and r.json() == {"detail": "daily cap"}


def test_reask_refreshes_jev_fields_and_keeps_the_owner_answer():
    c, store, client = _app(enabled=True)
    sid = _seed(c)
    c.post(f"/api/decide/review/{sid}", headers=OWNER, json={"answer": "wood"})
    r = c.post(f"/api/decide/reask/{sid}", headers=OWNER)
    assert r.status_code == 200 and len(client.calls) == 2
    row = r.json()
    # the fake answers the first option it is sent; Postgres jsonb stores the options in its own key order
    # (reported as a J3 finding), so compare with the stored question rather than a fixed label
    assert row["answer"] in CATS and row["answer"] == next(iter(row["question"]["criteria"]))
    assert row["status"] == "changed" and row["owner_answer"] == "wood"


def test_reask_unknown_id_is_404():
    c, _, _ = _app(enabled=True)
    assert c.post("/api/decide/reask/999", headers=OWNER).status_code == 404


def test_reask_failed_call_is_502_with_only_the_class_name():
    c, store, client = _app(enabled=True)
    sid = _seed(c)
    client.error = RuntimeError(f"401 bad key {FAKE_KEY}")
    r = c.post(f"/api/decide/reask/{sid}", headers=OWNER)
    assert r.status_code == 502 and r.json() == {"detail": "jev call failed: RuntimeError"}


# ------------------------------------------------------------------------------------- confirmed / health


def test_confirmed_needs_type_and_works_for_both_roles():
    c, _, _ = _app()
    assert c.get("/api/decide/confirmed", headers=ENGINE).status_code == 422
    for h in (ENGINE, OWNER):
        r = c.get("/api/decide/confirmed", headers=h, params={"type": "nothing"})
        assert r.status_code == 200 and r.json() == {"type": "nothing", "answers": {}}


def test_health_shows_jev_off_and_the_cap():
    c, _, _ = _app(enabled=False, daily_token_cap=1234)
    for h in (ENGINE, OWNER):
        r = c.get("/api/decide/health", headers=h)
        assert r.status_code == 200
        assert r.json() == {"ok": True, "jev_enabled": False, "tokens_today": 0, "daily_token_cap": 1234,
                            "model": "jev-latest"}


def test_health_counts_tokens_today():
    c, _, _ = _app(enabled=True)
    _seed(c)
    assert c.get("/api/decide/health", headers=OWNER).json()["tokens_today"] == 107


# ------------------------------------------------------------------------------------- import


def _item(subject="stone_brick", answer="metal", state=None, **kw):
    q = wire.question_to_json(ChoiceQ(f"Which category is {subject}?", CATS, qtype="mat.category", subject=subject))
    return {"state": state if state is not None else {"name": subject}, "question": q, "answer": answer,
            "confidence": 0.9, **kw}


def test_import_adds_skips_and_counts_invalid():
    c, store, _ = _app()
    items = [_item("a"), _item("b", state="plain text state"), _item("a"), _item("c", answer="plastic"),
             {"state": {}, "question": _item()["question"]}]       # no answer / confidence: invalid
    r = c.post("/api/decide/import", headers=ENGINE, json={"items": items})
    assert r.status_code == 200 and r.json() == {"added": 2, "skipped": 1, "invalid": 2}
    assert {x["source"] for x in store.list()} == {"pilot-import"}


@pytest.mark.parametrize("bad", [
    {"state": {}, "question": "text", "answer": "metal", "confidence": 0.9},
    {"state": {}, "question": ["x"], "answer": "metal", "confidence": 0.9},
    {"state": 5, "question": None, "answer": "metal", "confidence": 0.9},
    {"state": [1], "answer": "metal", "confidence": 0.9, "question": {}},
    {"state": 5, "answer": "metal", "confidence": 0.9, "question": {}},
    {"answer": "metal", "confidence": 0.9},
])
def test_import_bad_item_shapes_are_422_before_logic(bad):
    c, store, _ = _app()
    r = c.post("/api/decide/import", headers=ENGINE, json={"items": [_item("ok"), bad]})
    assert r.status_code == 422 and store.list() == []


# ------------------------------------------------------------------------------------- secrets


def test_a_failing_jev_call_leaks_no_key_in_bodies_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    c, _, client = _app(enabled=True, error=RuntimeError(f"401 bad key {FAKE_KEY}"))
    bodies = []
    r = _ask(c)
    bodies.append(r.text)
    assert r.status_code == 200 and r.json()["answers"]["a"]["source"] == "error"
    client.error = None
    sid = _seed(c)                                           # a real suggestion to reask against
    client.error = RuntimeError(f"401 bad key {FAKE_KEY}")
    for resp in (c.post(f"/api/decide/reask/{sid}", headers=OWNER),
                 c.get("/api/decide/suggestions", headers=OWNER),
                 c.get("/api/decide/health", headers=OWNER),
                 c.get("/api/decide/confirmed?type=mat.category", headers=OWNER)):
        bodies.append(resp.text)
    assert FAKE_KEY not in "".join(bodies) and FAKE_KEY not in caplog.text
    assert client.calls                                       # the failing path really ran


# ------------------------------------------------------------------------------------- fix round 1


def _q(**over):
    base = {"kind": "choice", "instructions": "Which?", "criteria": {"a": None, "b": "second"},
            "qtype": "t", "subject": "s"}
    base.update(over)
    return base


BAD_QUESTIONS = {
    "int qtype": _q(qtype=5),
    "int subject": _q(subject=5),
    "list instructions": _q(instructions=["x"]),
    "score criteria str": _q(kind="score", criteria="abc"),
    "score criteria empty": _q(kind="score", criteria=[]),
    "score criteria dict": _q(kind="score", criteria={"a": None}),
    "choice criteria pairs": _q(criteria=[[1, 2]]),
    "choice criteria list": _q(criteria=["a", "b"]),
    "choice criteria empty": _q(criteria={}),
    "choice description int": _q(criteria={"a": 3}),
    "noul with criteria": _q(kind="noul", criteria={"a": None}),
    "noul with list criteria": _q(kind="noul", criteria=["a"]),
    "unknown kind": _q(kind="weird"),
}


@pytest.mark.parametrize("name", list(BAD_QUESTIONS))
def test_ask_strict_question_shape_is_422(name):
    c, store, client = _app(enabled=True)
    assert _ask(c, questions={"a": BAD_QUESTIONS[name]}).status_code == 422
    assert client.calls == [] and store.list() == []


@pytest.mark.parametrize("name", list(BAD_QUESTIONS))
def test_import_strict_question_shape_is_422(name):
    c, store, _ = _app()
    item = {"state": {"n": 1}, "question": BAD_QUESTIONS[name], "answer": "a", "confidence": 0.9}
    assert c.post("/api/decide/import", headers=ENGINE, json={"items": [item]}).status_code == 422
    assert store.list() == []


def test_valid_question_shapes_pass():
    c, store, _ = _app()
    ok = {"n": _q(kind="noul", criteria=None), "c": _q(), "s": _q(kind="score", criteria=["lo", "hi"])}
    r = _ask(c, questions=ok)
    assert r.status_code == 200 and set(r.json()["answers"]) == {"n", "c", "s"}
    r = c.post("/api/decide/import", headers=ENGINE, json={"items": [
        {"state": "t", "question": _q(kind="score", criteria=["lo", "hi"]), "answer": 1, "confidence": 0.7}]})
    assert r.json() == {"added": 1, "skipped": 0, "invalid": 0}


def test_validation_errors_do_not_echo_the_input():
    c, _, _ = _app()
    r = _ask(c, questions={"a": _q(qtype={"secret": FAKE_KEY})})
    assert r.status_code == 422 and FAKE_KEY not in r.text
    r = c.post("/api/decide/import", headers=ENGINE, json={"items": [{"state": FAKE_KEY, "question": FAKE_KEY}]})
    assert r.status_code == 422 and FAKE_KEY not in r.text


def test_review_body_needs_exactly_one_of_accept_and_answer():
    c, _, _ = _app(enabled=True)
    sid = _seed(c)
    url = f"/api/decide/review/{sid}"
    assert c.post(url, headers=OWNER, json={"accept": "yes"}).status_code == 422
    assert c.post(url, headers=OWNER, json={"accept": 1}).status_code == 422
    assert c.post(url, headers=OWNER, json={"accept": True, "answer": "glass"}).status_code == 422
    assert c.post(url, headers=OWNER, json={"accept": False, "answer": "glass"}).status_code == 422
    assert c.post(url, headers=OWNER, json={}).status_code == 422
    assert c.post(url, headers=OWNER, json={"accept": False}).status_code == 422
    assert c.get("/api/decide/suggestions", headers=OWNER).json()["items"][0]["status"] == "pending"


def test_offset_is_capped_at_two_to_the_31():
    c, store, _ = _app()
    seen = {}
    real = store.list
    store.list = lambda **kw: (seen.update(kw), real(**kw))[1]
    r = c.get("/api/decide/suggestions", headers=OWNER, params={"offset": 10 ** 30})
    assert r.status_code == 200 and seen["offset"] == 2 ** 31 and r.json()["items"] == []


@pytest.mark.parametrize("raised, detail", [
    ("RuntimeError", "jev call failed: RuntimeError"),
    ("HTTPStatusError status=401", "jev call failed: HTTPStatusError status=401"),
    ("no answer", "jev call failed: no answer"),
    (f"bad key {FAKE_KEY}", "jev call failed"),
    ("Error: more text", "jev call failed"),
    ("Error status=abc", "jev call failed"),
    ("", "jev call failed"),
])
def test_502_text_is_whitelisted(monkeypatch, raised, detail):
    from decide_service import logic

    def boom(*a, **k):
        raise RuntimeError(raised)

    monkeypatch.setattr(logic, "reask", boom)
    c, _, _ = _app(enabled=True)
    r = c.post("/api/decide/reask/1", headers=OWNER)
    assert r.status_code == 502 and r.json() == {"detail": detail} and FAKE_KEY not in r.text


def test_unexpected_error_is_500_internal_error_and_logs_only_the_class(caplog):
    caplog.set_level(logging.DEBUG)
    dsn = "postgresql://decide:pw-SECRET-0123@db.internal:5432/decide"
    c, store, _ = _app()

    def broken(*a, **k):
        raise ConnectionError(f"cannot connect to {dsn}")

    store.tokens_today = broken
    r = c.get("/api/decide/health", headers=OWNER)       # raise_server_exceptions is True: nothing escapes
    assert r.status_code == 500 and r.json() == {"detail": "internal error"}
    assert "pw-SECRET" not in r.text and "pw-SECRET" not in caplog.text and "Traceback" not in caplog.text
    errors = [rec for rec in caplog.records if rec.levelno == logging.ERROR]
    assert errors and "ConnectionError" in errors[0].getMessage()
    assert all(rec.exc_info is None for rec in caplog.records)


def test_noul_review_over_http():
    c, _, _ = _app()
    noul = wire.question_to_json(NoulQ("Is g1 glass?", qtype="mat.is_glass", subject="g1"))
    r = c.post("/api/decide/import", headers=ENGINE, json={"items": [
        {"state": {"n": 1}, "question": noul, "answer": True, "confidence": 0.9}]})
    assert r.json()["added"] == 1
    sid = c.get("/api/decide/suggestions", headers=OWNER).json()["items"][0]["id"]
    for bad in (0, 1, "true", "yes", None, 1.0):
        assert c.post(f"/api/decide/review/{sid}", headers=OWNER, json={"answer": bad}).status_code == 422, bad
    r = c.post(f"/api/decide/review/{sid}", headers=OWNER, json={"answer": False})
    assert r.status_code == 200 and r.json()["owner_answer"] is False and r.json()["status"] == "changed"
    r = c.post(f"/api/decide/review/{sid}", headers=OWNER, json={"answer": True})
    assert r.json()["owner_answer"] is True and r.json()["status"] == "accepted"
    got = c.get("/api/decide/confirmed", headers=OWNER, params={"type": "mat.is_glass"}).json()["answers"]
    assert got == {"g1": True}


def test_score_review_over_http():
    c, _, _ = _app()
    score = wire.question_to_json(ScoreQ("How tall?", ["low", "mid", "high"], qtype="floor.level", subject="f1"))
    c.post("/api/decide/import", headers=ENGINE, json={"items": [
        {"state": {"n": 1}, "question": score, "answer": 1, "confidence": 0.9}]})
    sid = c.get("/api/decide/suggestions", headers=OWNER).json()["items"][0]["id"]
    url = f"/api/decide/review/{sid}"
    assert c.post(url, headers=OWNER, json={"answer": True}).status_code == 422       # a bool is never a level
    assert c.post(url, headers=OWNER, json={"answer": 3}).status_code == 422
    assert c.post(url, headers=OWNER, json={"answer": -1}).status_code == 422
    assert c.post(url, headers=OWNER, json={"answer": 1.5}).status_code == 422
    assert c.post(url, headers=OWNER, json={"answer": "1"}).status_code == 422
    r = c.post(url, headers=OWNER, json={"answer": 2})
    assert r.status_code == 200 and r.json()["owner_answer"] == 2 and r.json()["status"] == "changed"
    r = c.post(url, headers=OWNER, json={"answer": 1.0})                               # a whole float is stored as int
    assert r.status_code == 200 and r.json()["owner_answer"] == 1 and type(r.json()["owner_answer"]) is int
    assert r.json()["status"] == "accepted"
    got = c.get("/api/decide/confirmed", headers=OWNER, params={"type": "floor.level"}).json()["answers"]
    assert got == {"f1": 1}


def test_key_in_requests_does_not_come_back_through_import_review_or_ask(caplog):
    caplog.set_level(logging.DEBUG)
    c, _, client = _app(enabled=True, error=RuntimeError(f"401 bad key {FAKE_KEY}"))
    bodies = []
    r = _ask(c)                                          # ask: the client raises with the key in its message
    bodies.append(r.text)
    assert r.json()["answers"]["a"]["source"] == "error" and client.calls
    r = c.post("/api/decide/import", headers=ENGINE, json={"items": [      # import: the key as an answer
        {"state": {"n": 1}, "question": _q(), "answer": FAKE_KEY, "confidence": 0.9},
        {"state": {"n": 2}, "question": _q(), "answer": "a", "confidence": 0.9}]})
    bodies.append(r.text)
    assert r.json() == {"added": 1, "skipped": 0, "invalid": 1}
    sid = c.get("/api/decide/suggestions", headers=OWNER).json()["items"][0]["id"]
    for body in ({"answer": FAKE_KEY}, {"answer": {"k": FAKE_KEY}}, {"answer": [FAKE_KEY]}):   # review
        r = c.post(f"/api/decide/review/{sid}", headers=OWNER, json=body)
        bodies.append(r.text)
        assert r.status_code == 422
    assert FAKE_KEY not in "".join(bodies) and FAKE_KEY not in caplog.text
