"""PostgresStore specifics: the DSN stays secret, the schema is idempotent, the logic runs on the real store."""
import os
from types import SimpleNamespace

import pytest

from decide_service import logic
from decide_service.pgstore import PostgresStore
from decide_service.settings import Settings
from engine.decide.jev import ChoiceQ, JevDecider

TEST_URL = os.environ.get("DECIDE_TEST_DATABASE_URL", "")
SECRET = "pw-SECRET-0123456789"


def test_dsn_is_not_in_the_repr():
    store = PostgresStore(f"postgresql://u:{SECRET}@localhost:1/db")
    assert SECRET not in repr(store) and SECRET not in str(store) and "localhost" not in repr(store)


def test_a_failed_connection_does_not_leak_the_dsn():
    store = PostgresStore(f"postgresql://u:{SECRET}@127.0.0.1:1/db?connect_timeout=2")
    with pytest.raises(ConnectionError) as info:
        store.find_by_key("a" * 64)
    assert SECRET not in str(info.value) and SECRET not in repr(info.value)
    assert info.value.__cause__ is None and info.value.__context__ is None


def test_update_rejects_a_column_that_is_not_allowed():
    store = PostgresStore(f"postgresql://u:{SECRET}@127.0.0.1:1/db")
    with pytest.raises(ValueError):
        store.update_suggestion(1, **{"key": "x"})
    with pytest.raises(ValueError):
        store.update_suggestion(1, **{"status = 'x'; drop table decide.suggestions; --": 1})


needs_db = pytest.mark.skipif(not TEST_URL, reason="DECIDE_TEST_DATABASE_URL not set")


@pytest.fixture
def pg():
    import psycopg
    assert ":55432/" in TEST_URL
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("drop schema if exists decide cascade")
    s = PostgresStore(TEST_URL)
    s.ensure_schema()
    yield s
    s.close()


@needs_db
def test_ensure_schema_is_idempotent_and_keeps_rows(pg):
    from .test_store_contract import k, make_row
    sid = pg.add_suggestion(make_row(key=k(1)))
    pg.ensure_schema()
    pg.ensure_schema()
    assert pg.get(sid)["key"] == k(1)


@needs_db
def test_the_status_check_is_enforced(pg):
    from .test_store_contract import k, make_row
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        pg.add_suggestion(make_row(key=k(1), status="bogus"))


@needs_db
def test_call_entries_from_the_decider_map_to_the_columns(pg):
    pg.add_call({"at": "2026-10-08T10:00:00+00:00", "questions": 4, "latency_s": 1.2, "input_tokens": 10,
                 "output_tokens": 2, "model": "m", "ok": False, "error": "TimeoutError"})
    row = pg._fetch("select * from decide.calls", one=True)
    assert (row["questions"], row["latency_ms"], row["input_tokens"], row["model"], row["ok"],
            row["error_class"]) == (4, 1200, 10, "m", False, "TimeoutError")


@needs_db
def test_one_reconnect_after_the_connection_is_closed(pg):
    from .test_store_contract import k, make_row
    sid = pg.add_suggestion(make_row(key=k(1)))
    pg._conn.close()
    assert pg.get(sid)["key"] == k(1)
    pg._conn.close()
    assert pg.add_suggestion(make_row(key=k(2))) != sid
    assert pg.tokens_today() == 0


@needs_db
def test_one_retry_after_the_server_drops_the_connection(pg):
    import psycopg
    from .test_store_contract import k, make_row
    sid = pg.add_suggestion(make_row(key=k(1)))
    with psycopg.connect(TEST_URL, autocommit=True) as admin:
        admin.execute("select pg_terminate_backend(%s)", (pg._conn.info.backend_pid,))
    assert pg.get(sid)["key"] == k(1)


def test_never_more_than_one_retry(monkeypatch):
    import psycopg
    store = PostgresStore(f"postgresql://u:{SECRET}@127.0.0.1:1/db")
    attempts = []

    class Broken:
        closed = False
        broken = False

        def execute(self, *a, **kw):
            attempts.append(1)
            raise psycopg.OperationalError("lost")

        def close(self):
            pass

    monkeypatch.setattr(psycopg, "connect", lambda *a, **kw: Broken())
    with pytest.raises(psycopg.OperationalError):
        store.find_by_key("a" * 64)
    assert len(attempts) == 2


class FakeClient:
    def system_one(self, state, questions):
        answers = {qid: SimpleNamespace(type="choice", choice=next(iter(spec.criteria)), confidence=0.95,
                                        probabilities={next(iter(spec.criteria)): 0.95})
                   for qid, spec in questions.items()}
        return SimpleNamespace(answers=answers, model="jev-fake",
                               usage=SimpleNamespace(input_tokens=100, output_tokens=7))


@needs_db
def test_the_service_logic_runs_on_the_postgres_store(pg):
    cfg = Settings(jev_enabled=True)
    qs = {"q1": ChoiceQ("pick", {"glass": None, "metal": None}, qtype="material.class", subject="Glass Door")}
    first = logic.answer(pg, cfg, lambda: JevDecider(client=FakeClient()), {"text": "door"}, qs)
    assert first["q1"]["source"] == "jev" and first["q1"]["answer"] == "glass"
    assert pg.tokens_today() == 107
    again = logic.answer(pg, cfg, lambda: JevDecider(client=FakeClient()), {"text": "door"}, qs)
    assert again["q1"]["suggestion_id"] == first["q1"]["suggestion_id"]
    row = logic.review(pg, first["q1"]["suggestion_id"], "gab", answer="metal")
    assert row["status"] == "changed" and row["owner_answer"] == "metal" and row["reviewed_by"] == "gab"
    owner = logic.answer(pg, cfg, lambda: JevDecider(client=FakeClient()), {"text": "other"}, qs)
    assert owner["q1"]["answer"] == "metal" and owner["q1"]["source"] == "owner"
    assert pg.counts() == {"pending": 0, "accepted": 0, "changed": 1}
