"""One contract, two stores: MemoryStore always; PostgresStore when DECIDE_TEST_DATABASE_URL is set.

The Postgres half drops and recreates the schema `decide` before each test, so it must only ever be pointed at
the throwaway container `decide-test-pg` (port 55432). A URL on any other port is refused.
"""
import datetime as dt
import os

import pytest

from decide_service.store import MemoryStore

TEST_URL = os.environ.get("DECIDE_TEST_DATABASE_URL", "")
T0 = dt.datetime(2026, 10, 1, 12, 0, tzinfo=dt.timezone.utc)


def _iso(minutes=0):
    return (T0 + dt.timedelta(minutes=minutes)).isoformat()


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        yield MemoryStore()
        return
    if not TEST_URL:
        pytest.skip("DECIDE_TEST_DATABASE_URL not set")
    assert ":55432/" in TEST_URL, "the test database is the throwaway container decide-test-pg on port 55432 only"
    import psycopg
    from decide_service.pgstore import PostgresStore

    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("drop schema if exists decide cascade")
    s = PostgresStore(TEST_URL)
    s.ensure_schema()
    try:
        yield s
    finally:
        s.close()


def make_row(key="a" * 64, qtype="material.class", subject="Glass Door", answer="glass", confidence=0.9, **kw):
    row = {"qtype": qtype, "subject": subject, "key": key, "state": '{"text": "x"}', "state_json": {"text": "x"},
           "question": {"kind": "choice", "labels": ["glass", "metal"]}, "answer": answer, "confidence": confidence,
           "probabilities": {"glass": 0.9, "metal": 0.1}, "model": "jev-fake", "source": "jev", "status": "pending",
           "owner_answer": None, "reviewed_at": None, "reviewed_by": None, "created_at": _iso()}
    row.update(kw)
    return row


def k(n):
    return f"{n:064x}"


def review(store, sid, status, owner_answer, minutes):
    store.update_suggestion(sid, status=status, owner_answer=owner_answer, reviewed_at=_iso(minutes),
                            reviewed_by="gab")


def test_add_then_find_by_key(store):
    assert store.find_by_key(k(1)) is None
    sid = store.add_suggestion(make_row(key=k(1)))
    row = store.find_by_key(k(1))
    assert row["id"] == sid and row["key"] == k(1)
    assert row["qtype"] == "material.class" and row["subject"] == "Glass Door"
    assert row["answer"] == "glass" and row["confidence"] == 0.9 and row["status"] == "pending"
    assert row["probabilities"] == {"glass": 0.9, "metal": 0.1}
    assert row["question"] == {"kind": "choice", "labels": ["glass", "metal"]}
    assert row["state_json"] == {"text": "x"} and row["state"] == '{"text": "x"}'
    assert row["owner_answer"] is None and row["reviewed_at"] is None and row["reviewed_by"] is None
    assert store.find_by_key(k(2)) is None


def test_ids_are_distinct_and_get_misses_return_none(store):
    a = store.add_suggestion(make_row(key=k(1)))
    b = store.add_suggestion(make_row(key=k(2)))
    assert a != b
    assert store.get(a)["key"] == k(1) and store.get(b)["key"] == k(2)
    assert store.get(b + 1000) is None


def test_update_then_get(store):
    sid = store.add_suggestion(make_row(key=k(1)))
    store.update_suggestion(sid, answer="metal", confidence=0.5, probabilities={"metal": 0.5}, model="m2",
                            status="changed", owner_answer="wood", reviewed_at=_iso(5), reviewed_by="gab")
    row = store.get(sid)
    assert row["answer"] == "metal" and row["confidence"] == 0.5 and row["probabilities"] == {"metal": 0.5}
    assert row["model"] == "m2" and row["status"] == "changed" and row["owner_answer"] == "wood"
    assert row["reviewed_by"] == "gab" and row["reviewed_at"] is not None
    assert row["key"] == k(1) and row["subject"] == "Glass Door"


def test_update_unknown_id_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.update_suggestion(987654, status="accepted")


def test_owner_answer_returns_the_latest_review(store):
    assert store.owner_answer("material.class", "Glass Door") is None
    a = store.add_suggestion(make_row(key=k(1)))
    b = store.add_suggestion(make_row(key=k(2)))
    c = store.add_suggestion(make_row(key=k(3)))          # pending: never counts
    review(store, b, "changed", "wood", 20)
    review(store, a, "accepted", "metal", 10)
    assert store.owner_answer("material.class", "Glass Door") == "wood"
    review(store, a, "changed", "glass", 30)
    assert store.owner_answer("material.class", "Glass Door") == "glass"
    assert store.owner_answer("material.class", "Other") is None
    assert store.owner_answer("other.type", "Glass Door") is None
    assert store.get(c)["status"] == "pending"


def test_confirmed_returns_the_latest_per_subject(store):
    a1 = store.add_suggestion(make_row(key=k(1), subject="A"))
    a2 = store.add_suggestion(make_row(key=k(2), subject="A"))
    b1 = store.add_suggestion(make_row(key=k(3), subject="B"))
    store.add_suggestion(make_row(key=k(4), subject="C"))                       # pending
    store.add_suggestion(make_row(key=k(5), subject="D", qtype="other.type"))   # other qtype
    review(store, a1, "accepted", "glass", 10)
    review(store, a2, "changed", "wood", 20)
    review(store, b1, "accepted", "metal", 5)
    assert store.confirmed("material.class") == {"A": "wood", "B": "metal"}
    assert store.confirmed("nothing") == {}


def test_list_filters(store):
    store.add_suggestion(make_row(key=k(1), subject="Glass Door", confidence=0.95))
    s2 = store.add_suggestion(make_row(key=k(2), subject="Steel Beam", confidence=0.6, answer="metal"))
    store.add_suggestion(make_row(key=k(3), subject="GLASS wall", qtype="wall.kind", confidence=0.75))
    review(store, s2, "accepted", "metal", 1)

    def subjects(**kw):
        return [r["subject"] for r in store.list(**kw)]

    assert subjects() == ["Glass Door", "Steel Beam", "GLASS wall"]
    assert subjects(status="pending") == ["Glass Door", "GLASS wall"]
    assert subjects(status="accepted") == ["Steel Beam"]
    assert subjects(status="changed") == []
    assert subjects(qtype="wall.kind") == ["GLASS wall"]
    assert subjects(min_conf=0.75) == ["Glass Door", "GLASS wall"]
    assert subjects(min_conf=0.96) == []
    assert subjects(q="glass") == ["Glass Door", "GLASS wall"]
    assert subjects(q="BEAM") == ["Steel Beam"]
    assert subjects(q="nomatch") == []
    assert subjects(status="pending", qtype="material.class", min_conf=0.9, q="door") == ["Glass Door"]
    assert subjects(limit=2) == ["Glass Door", "Steel Beam"]
    assert subjects(limit=2, offset=2) == ["GLASS wall"]


def test_list_q_is_a_plain_substring_not_a_pattern(store):
    store.add_suggestion(make_row(key=k(1), subject="100% wool_rug"))
    store.add_suggestion(make_row(key=k(2), subject="plain"))
    assert [r["subject"] for r in store.list(q="%")] == ["100% wool_rug"]
    assert [r["subject"] for r in store.list(q="_rug")] == ["100% wool_rug"]
    assert store.list(q="'; drop table x; --") == []


def test_counts(store):
    assert store.counts() == {"pending": 0, "accepted": 0, "changed": 0}
    store.add_suggestion(make_row(key=k(1)))
    b = store.add_suggestion(make_row(key=k(2)))
    c = store.add_suggestion(make_row(key=k(3), qtype="wall.kind"))
    d = store.add_suggestion(make_row(key=k(4), qtype="wall.kind"))
    review(store, b, "accepted", "glass", 1)
    review(store, c, "changed", "metal", 2)
    review(store, d, "accepted", "metal", 3)
    assert store.counts() == {"pending": 1, "accepted": 2, "changed": 1}
    assert store.counts("wall.kind") == {"pending": 0, "accepted": 1, "changed": 1}
    assert store.counts("material.class") == {"pending": 1, "accepted": 1, "changed": 0}
    assert store.counts("nothing") == {"pending": 0, "accepted": 0, "changed": 0}


def test_tokens_today_counts_only_todays_calls(store):
    now = dt.datetime.now(dt.timezone.utc)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    yesterday = today - dt.timedelta(days=1)
    assert store.tokens_today() == 0
    store.add_call({"at": today.isoformat(), "questions": 3, "latency_s": 1.5, "input_tokens": 100,
                    "output_tokens": 7, "model": "jev-fake", "ok": True})
    store.add_call({"at": yesterday.isoformat(), "questions": 3, "latency_s": 0.5, "input_tokens": 5000,
                    "output_tokens": 500, "model": "jev-fake", "ok": True})
    store.add_call({"at": today.isoformat(), "questions": 2, "latency_s": 0.1, "input_tokens": None,
                    "output_tokens": None, "model": None, "ok": False, "error": "TimeoutError"})
    assert store.tokens_today() == 107


@pytest.mark.parametrize("value", ["glass", True, False, 0, 3, 0.5, 2.5])
def test_json_types_survive_a_round_trip(store, value):
    sid = store.add_suggestion(make_row(key=k(1), answer=value))
    assert store.get(sid)["answer"] == value
    assert type(store.get(sid)["answer"]) is type(value)
    assert type(store.find_by_key(k(1))["answer"]) is type(value)
    review(store, sid, "changed", value, 1)
    row = store.get(sid)
    assert row["owner_answer"] == value and type(row["owner_answer"]) is type(value)
    assert type(store.owner_answer("material.class", "Glass Door")) is type(value)
    assert type(store.confirmed("material.class")["Glass Door"]) is type(value)


def test_bool_stays_bool_and_int_stays_int_explicitly(store):
    t = store.add_suggestion(make_row(key=k(1), answer=True))
    i = store.add_suggestion(make_row(key=k(2), answer=1))
    assert type(store.get(t)["answer"]) is bool
    assert type(store.get(i)["answer"]) is int


def test_state_json_and_text_are_kept(store):
    state = {"text": "tile", "n": 3, "nested": {"a": [1, 2.5, "x"]}}
    sid = store.add_suggestion(make_row(key=k(1), state="x" * 2000, state_json=state))
    row = store.get(sid)
    assert row["state_json"] == state
    assert len(row["state"]) == 2000


def test_a_missing_answer_stays_none(store):
    sid = store.add_suggestion(make_row(key=k(1), answer=None, confidence=0.0, probabilities={}))
    row = store.get(sid)
    assert row["answer"] is None and row["probabilities"] == {}


def test_returned_rows_are_copies(store):
    sid = store.add_suggestion(make_row(key=k(1)))
    store.get(sid)["answer"] = "tampered"
    assert store.get(sid)["answer"] == "glass"


def test_a_duplicate_key_returns_the_existing_id_and_leaves_one_row(store):
    first = store.add_suggestion(make_row(key=k(1)))
    second = store.add_suggestion(make_row(key=k(1), subject="Other", answer="metal"))
    assert second == first
    rows = store.list()
    assert len(rows) == 1 and rows[0]["subject"] == "Glass Door" and rows[0]["answer"] == "glass"
    third = store.add_suggestion(make_row(key=k(2)))
    assert third != first


def test_q_matches_the_subject_only_in_any_case(store):
    store.add_suggestion(make_row(key=k(1), subject="Glass Door", state='{"text": "only-in-state"}'))
    store.add_suggestion(make_row(key=k(2), subject="Steel Beam", state='{"text": "plain"}'))
    assert store.list(q="only-in-state") == []
    assert store.list(q="plain") == []
    assert [r["subject"] for r in store.list(q="gLaSs dOOr")] == ["Glass Door"]
    assert [r["subject"] for r in store.list(q="STEEL")] == ["Steel Beam"]


def test_timestamps_come_back_as_utc_iso_strings(store):
    sid = store.add_suggestion(make_row(key=k(1)))
    review(store, sid, "accepted", "glass", 5)
    row = store.get(sid)
    for column in ("created_at", "reviewed_at"):
        assert isinstance(row[column], str) and row[column].endswith("+00:00"), (column, row[column])
    assert store.list()[0]["reviewed_at"].endswith("+00:00")
