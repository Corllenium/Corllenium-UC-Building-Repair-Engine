"""The Store protocol and an in-memory store (tests; the Postgres store is J4)."""
from __future__ import annotations

import datetime as dt
from typing import Protocol

REVIEWED = ("accepted", "changed")


class Store(Protocol):
    def find_by_key(self, key: str) -> dict | None: ...
    def add_suggestion(self, row: dict) -> int: ...
    def update_suggestion(self, id: int, **fields) -> None: ...
    def get(self, id: int) -> dict | None: ...
    def owner_answer(self, qtype: str, subject: str) -> object | None: ...
    def confirmed(self, qtype: str) -> dict[str, object]: ...
    def list(self, status=None, qtype=None, min_conf=None, q=None, limit=100, offset=0) -> list[dict]: ...
    def counts(self, qtype=None) -> dict[str, int]: ...
    def add_call(self, entry: dict) -> None: ...
    def tokens_today(self) -> int: ...


class MemoryStore:
    def __init__(self):
        self.rows: list[dict] = []
        self.calls: list[dict] = []
        self._next = 1

    def find_by_key(self, key):
        return next((dict(r) for r in self.rows if r["key"] == key), None)

    def add_suggestion(self, row):
        existing = next((r for r in self.rows if r["key"] == row["key"]), None)
        if existing is not None:          # same key twice: one row, the first id (as the Postgres store does)
            return existing["id"]
        new = {**row, "id": self._next}
        self._next += 1
        self.rows.append(new)
        return new["id"]

    def update_suggestion(self, id, **fields):
        for r in self.rows:
            if r["id"] == id:
                r.update(fields)
                return
        raise KeyError(id)

    def get(self, id):
        return next((dict(r) for r in self.rows if r["id"] == id), None)

    def _reviewed(self, qtype):
        """Reviewed rows of a qtype, oldest review first (insertion order breaks ties)."""
        rows = [r for r in self.rows if r["qtype"] == qtype and r["status"] in REVIEWED]
        return sorted(rows, key=lambda r: (r["reviewed_at"] or "", r["id"]))

    def owner_answer(self, qtype, subject):
        latest = [r for r in self._reviewed(qtype) if r["subject"] == subject]
        return latest[-1]["owner_answer"] if latest else None

    def confirmed(self, qtype):
        return {r["subject"]: r["owner_answer"] for r in self._reviewed(qtype)}

    def list(self, status=None, qtype=None, min_conf=None, q=None, limit=100, offset=0):
        needle = q.lower() if q else None
        rows = [r for r in self.rows
                if (status is None or r["status"] == status)
                and (qtype is None or r["qtype"] == qtype)
                and (min_conf is None or r["confidence"] >= min_conf)
                and (needle is None or needle in (r["subject"] or "").lower())]
        return [dict(r) for r in rows[offset:offset + limit]]

    def counts(self, qtype=None):
        out = {"pending": 0, "accepted": 0, "changed": 0}
        for r in self.rows:
            if (qtype is None or r["qtype"] == qtype) and r["status"] in out:
                out[r["status"]] += 1
        return out

    def add_call(self, entry):
        self.calls.append(dict(entry))

    def tokens_today(self):
        today = dt.datetime.now(dt.timezone.utc).date()
        total = 0
        for c in self.calls:
            if dt.datetime.fromisoformat(c["at"]).astimezone(dt.timezone.utc).date() == today:
                total += (c.get("input_tokens") or 0) + (c.get("output_tokens") or 0)
        return total
