"""The Postgres store: the same Store protocol as MemoryStore, over the schema `decide` (schema.sql).

Every query takes its values as parameters; the only SQL built at run time is the SET list of an update, whose
column names come from a fixed allow-list. The DSN can carry a password: it is never in a repr, a log line or an
exception text.
"""
from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schema.sql"

_JSON_COLUMNS = {"state_json", "question", "answer", "probabilities", "owner_answer"}
_TIME_COLUMNS = {"reviewed_at", "created_at"}
_UPDATABLE = {"qtype", "subject", "state", "state_json", "question", "answer", "confidence", "probabilities",
              "model", "source", "status", "owner_answer", "reviewed_at", "reviewed_by", "created_at"}


def _when(value):
    """An ISO string (the MemoryStore way) or a datetime, as an aware datetime; None stays None."""
    if value is None:
        return None
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value


def _param(column: str, value):
    """A column value as a query parameter: JSON columns through Jsonb (SQL NULL for None), times as datetimes."""
    if column in _JSON_COLUMNS:
        return None if value is None else Jsonb(value)
    if column in _TIME_COLUMNS:
        return _when(value)
    return value


def _out(row: dict | None) -> dict | None:
    """A row as MemoryStore holds it: times as ISO strings."""
    if row is None:
        return None
    for column in _TIME_COLUMNS:
        if row.get(column) is not None:
            row[column] = row[column].astimezone(dt.timezone.utc).isoformat()
    return row


class PostgresStore:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn: psycopg.Connection | None = None
        self._lock = threading.RLock()

    def __repr__(self) -> str:
        return "PostgresStore()"

    # -- connection -------------------------------------------------------------------------------------------
    def _connection(self) -> psycopg.Connection:
        if self._conn is not None and not self._conn.closed and not self._conn.broken:
            return self._conn
        failure = None
        try:
            self._conn = psycopg.connect(self._dsn, autocommit=True, row_factory=dict_row)
        except psycopg.Error as exc:
            failure = type(exc).__name__
        if failure is not None:          # raised outside the except block: no chained exception can carry the DSN
            self._conn = None
            raise ConnectionError(f"cannot connect to the decide database ({failure})") from None
        return self._conn

    def _fetch(self, query, params=None, one=False):
        """Runs a query. A lost connection (psycopg.OperationalError) gets exactly one reconnect and one retry."""
        with self._lock:
            for attempt in (1, 2):
                try:
                    cur = self._connection().execute(query, params)
                    return cur.fetchone() if one else cur.fetchall()
                except psycopg.OperationalError:
                    if attempt == 2:
                        raise
                    self.close()

    def close(self) -> None:
        with self._lock:
            conn, self._conn = self._conn, None
            if conn is not None:
                try:
                    conn.close()
                except psycopg.Error:
                    pass

    def ensure_schema(self) -> None:
        script = SCHEMA_FILE.read_text(encoding="utf-8")
        with self._lock:
            for attempt in (1, 2):
                try:
                    self._connection().execute(script)
                    return
                except psycopg.OperationalError:
                    if attempt == 2:
                        raise
                    self.close()

    # -- suggestions ------------------------------------------------------------------------------------------
    def find_by_key(self, key):
        return _out(self._fetch("select * from decide.suggestions where key = %s", (key,), one=True))

    def add_suggestion(self, row):
        values = {
            "qtype": row.get("qtype") or "", "subject": row.get("subject") or "", "key": row["key"],
            "state": row["state"], "state_json": row["state_json"], "question": row["question"],
            "answer": row.get("answer"), "confidence": row.get("confidence") or 0.0,
            "probabilities": row.get("probabilities") or {}, "model": row.get("model") or "",
            "source": row["source"], "status": row.get("status") or "pending",
            "owner_answer": row.get("owner_answer"), "reviewed_at": row.get("reviewed_at"),
            "reviewed_by": row.get("reviewed_by"), "created_at": row.get("created_at"),
        }
        params = {c: _param(c, v) for c, v in values.items()}
        out = self._fetch(
            "insert into decide.suggestions (qtype, subject, key, state, state_json, question, answer, confidence,"
            " probabilities, model, source, status, owner_answer, reviewed_at, reviewed_by, created_at)"
            " values (%(qtype)s, %(subject)s, %(key)s, %(state)s, %(state_json)s, %(question)s, %(answer)s,"
            " %(confidence)s, %(probabilities)s, %(model)s, %(source)s, %(status)s, %(owner_answer)s,"
            " %(reviewed_at)s, %(reviewed_by)s, coalesce(%(created_at)s, now()))"
            " on conflict (key) do nothing returning id",
            params, one=True)
        if out is None:           # the key exists already (a race, or a repeat): return the row that won
            out = self._fetch("select id from decide.suggestions where key = %s", (row["key"],), one=True)
        return out["id"]

    def update_suggestion(self, id, **fields):
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot update column(s): {sorted(unknown)}")
        if not fields:
            if self.get(id) is None:
                raise KeyError(id)
            return
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = {}").format(sql.Identifier(column), sql.Placeholder()) for column in fields)
        query = sql.SQL("update decide.suggestions set {} where id = %s returning id").format(assignments)
        params = [_param(column, value) for column, value in fields.items()] + [id]
        if self._fetch(query, params, one=True) is None:
            raise KeyError(id)

    def get(self, id):
        return _out(self._fetch("select * from decide.suggestions where id = %s", (id,), one=True))

    def owner_answer(self, qtype, subject):
        row = self._fetch(
            "select owner_answer from decide.suggestions where qtype = %s and subject = %s"
            " and status in ('accepted', 'changed')"
            " order by reviewed_at desc nulls last, id desc limit 1", (qtype, subject), one=True)
        return row["owner_answer"] if row else None

    def confirmed(self, qtype):
        rows = self._fetch(
            "select distinct on (subject) subject, owner_answer from decide.suggestions"
            " where qtype = %s and status in ('accepted', 'changed')"
            " order by subject, reviewed_at desc nulls last, id desc", (qtype,))
        return {r["subject"]: r["owner_answer"] for r in rows}

    def list(self, status=None, qtype=None, min_conf=None, q=None, limit=100, offset=0):
        where, params = [], []
        if status is not None:
            where.append("status = %s")
            params.append(status)
        if qtype is not None:
            where.append("qtype = %s")
            params.append(qtype)
        if min_conf is not None:
            where.append("confidence >= %s")
            params.append(min_conf)
        if q:    # a plain, case-insensitive substring of the subject (no pattern characters)
            where.append("strpos(lower(subject), lower(%s)) > 0")
            params.append(q)
        query = "select * from decide.suggestions"
        if where:
            query += " where " + " and ".join(where)     # fixed fragments only; every value is a parameter
        query += " order by id limit %s offset %s"
        params.extend([int(limit), int(offset)])
        return [_out(r) for r in self._fetch(query, params)]

    def counts(self, qtype=None):
        out = {"pending": 0, "accepted": 0, "changed": 0}
        rows = self._fetch(
            "select status, count(*) as n from decide.suggestions where (%s::text is null or qtype = %s)"
            " group by status", (qtype, qtype))
        for r in rows:
            out[r["status"]] = int(r["n"])
        return out

    # -- calls ------------------------------------------------------------------------------------------------
    def add_call(self, entry):
        latency_ms = entry.get("latency_ms")
        if latency_ms is None and entry.get("latency_s") is not None:
            latency_ms = round(entry["latency_s"] * 1000)
        self._fetch(
            "insert into decide.calls (at, questions, latency_ms, input_tokens, output_tokens, model, ok, error_class)"
            " values (coalesce(%s, now()), %s, %s, %s, %s, %s, %s, %s) returning id",
            (_when(entry.get("at")), entry.get("questions") or 0, latency_ms, entry.get("input_tokens"),
             entry.get("output_tokens"), entry.get("model"), bool(entry.get("ok")),
             entry.get("error_class") or entry.get("error")), one=True)

    def tokens_today(self):
        row = self._fetch(
            "select coalesce(sum(coalesce(input_tokens, 0) + coalesce(output_tokens, 0)), 0) as n"
            " from decide.calls where (at at time zone 'UTC')::date = (now() at time zone 'UTC')::date", one=True)
        return int(row["n"])
