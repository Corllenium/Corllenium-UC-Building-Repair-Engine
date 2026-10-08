# Jev on the VPS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `uc-fixer-decide` service (holds the TypeSafe key, answers typed questions with the order owner >
stored suggestion > Jev), the engine's `RemoteDecider` / `decide-pull` / `decide-import-pilot`, and the `/jev` review
page. Jev stays **switched off** (`DECIDE_JEV_ENABLED=false`) until the repair engine is ready.

**Architecture:** A FastAPI service in `deploy/vps/decide/` reuses `engine/decide/jev.py` and stores suggestions in
the schema `decide` of the VPS Postgres. The engine on the PC calls it over HTTPS with a separate login; only the
owner's confirmed answers, pulled to `data/decide/confirmed/`, feed the engine. The dashboard gets a `/jev` page.

**Tech Stack:** Python 3.12, FastAPI, psycopg 3, typesafe-sdk 0.7.2, stdlib `urllib` (engine client), Postgres 16,
Vue 3 + Vitest, nginx, Docker.

**Spec:** `docs/superpowers/specs/2026-10-08-jev-vps-service-design.md` (owner-approved 2026-10-08).

## Global Constraints

- AGENTS.md binds every task: test first; commit after every item; stage files by name; never a bare `cd`; Python is
  `"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"`, run from the worktree root in a subshell with
  `PYTHONPATH` set.
- **Branches:** the integration branch `feat/jev-vps` comes from `feat-dashboard` (8b22e75 or later). Each job is
  `claude/<id>` in `.claude/worktrees/<id>` from `feat/jev-vps`. The controller merges with `--no-ff` after a review,
  and asks the repair-engine session before any merge into `feat-dashboard`.
- **Jev is off:** default `DECIDE_JEV_ENABLED=false`. No task makes a real Jev call. Every test uses a fake client.
- **Secrets:** the TypeSafe key is read from the environment only (service). The `uc-engine` password is
  `UC_DECIDE_PASSWORD`, from the environment or else only that one line of the git-ignored repo-root `.env`
  (engine). Neither is ever printed, logged, put in a `repr` or exception text, or committed. Agents never open `.env*`.
- **Never touch:** the live containers `fixer-api`, `fixer-web`, `fixer-db`; the database `fixer`; the VPS. Every test
  database is a throwaway container named `decide-test-pg` on port 55432.
- **The pipeline never waits:** `RemoteDecider` has a 10 s timeout and no retries. Any failure gives `none` / `error`
  decisions, never accepted.
- **Only text leaves the PC:** names, texture file names, categories, small numbers.
- **Limits:** a Score has at most 10 levels and a Choice at most 255 options (`check_question_limits`). The daily cap is
  1,000,000 tokens (`DECIDE_DAILY_TOKEN_CAP`).
- **Logins:** the engine login is `uc-engine`. The owner logins come from `DECIDE_OWNER_USERS` (default `gab`). The
  user name arrives in `X-Remote-User`, set by nginx.
- **Out of scope:** the actual VPS deploy (the controller does it with the owner's OK at that moment), switching Jev
  on, P1-D2, the `repair.next_step` question.

## File map

| File | Responsibility |
|---|---|
| `engine/decide/jev.py` (modify) | questions carry `qtype` and `subject`; the classifiers set them |
| `engine/decide/wire.py` (new) | question and decision JSON codec; `question_key`; `options_of` |
| `engine/decide/remote.py` (new) | `RemoteDecider` (HTTP client, same `.ask` as `JevDecider`); `pull_confirmed` |
| `engine/decide/pilot_import.py` (new) | rebuilds the pilot questions and pairs them with the stored pilot answers |
| `engine/cli.py` (modify) | `decide-pull`, `decide-import-pilot` |
| `deploy/vps/decide/decide_service/settings.py` | `Settings` from the environment |
| `deploy/vps/decide/decide_service/store.py` | `Store` protocol, `MemoryStore` |
| `deploy/vps/decide/decide_service/pgstore.py` | `PostgresStore` |
| `deploy/vps/decide/schema.sql` | schema `decide` |
| `deploy/vps/decide/decide_service/logic.py` | `answer`, `reask`, `import_items` |
| `deploy/vps/decide/decide_service/app.py` | FastAPI `create_app`, roles, endpoints |
| `deploy/vps/decide/decide_service/main.py` | the production wiring (uvicorn entry) |
| `deploy/vps/decide/Dockerfile`, `requirements.txt` | the image |
| `deploy/vps/docker-compose.yml`, `nginx.conf`, `README.md` (modify) | the service, its route, the runbook |
| `web/src/api/decide.ts`, `web/src/utils/jevReview.ts`, `web/src/views/JevView.vue`, `web/src/router.ts` | the page |

Service tests live in `deploy/vps/decide/tests/`. Run them with
`PYTHONPATH="$PWD;$PWD/deploy/vps/decide"` from the worktree root (`;` is the separator on Windows).

---

### Task J1: question metadata and the wire format

**Files:**
- Modify: `engine/decide/jev.py`: `NoulQ`, `ChoiceQ`, `ScoreQ`, `classify_group_names`, `classify_materials`
- Create: `engine/decide/wire.py`
- Test: `engine/tests/test_decide_wire.py`

**Interfaces:**
- Produces:
  - `NoulQ(instructions, qtype="", subject="")`, `ChoiceQ(instructions, criteria, qtype="", subject="")`,
    `ScoreQ(instructions, criteria, qtype="", subject="")`.
  - `wire.question_to_json(q) -> dict` gives `{"kind": "noul"|"choice"|"score", "instructions", "criteria",
    "qtype", "subject"}`; `wire.question_from_json(d) -> NoulQ|ChoiceQ|ScoreQ` reverses it.
  - `wire.question_key(state: dict, q) -> str`: sha256 hex of the canonical JSON of `{"state", "kind",
    "instructions", "criteria"}`. qtype and subject are not part of it.
  - `wire.decision_to_json(d, suggestion_id=None) -> dict`, `wire.decision_from_json(d) -> Decision`.
  - `wire.options_of(q) -> list`: `[True, False]` for a Noul, the labels for a Choice, `[0..n-1]` for a Score.
- qtypes used: `inv.building`, `inv.type`, `inv.floor`, `inv.duplicate` (subject = the group name);
  `mat.category`, `mat.trim` (subject = the material name).

- [ ] **Step 1: Write the failing tests** in `engine/tests/test_decide_wire.py`:

```python
import json
from engine.decide.jev import ChoiceQ, Decision, NoulQ, ScoreQ, classify_group_names, classify_materials
from engine.decide import wire


def test_question_round_trip_keeps_kind_criteria_and_metadata():
    for q in (NoulQ("is it?", qtype="inv.duplicate", subject="CHTM_5th"),
              ChoiceQ("which?", {"a": None, "b": "bee"}, qtype="mat.category", subject="M1"),
              ScoreQ("how?", ["low", "high"])):
        back = wire.question_from_json(json.loads(json.dumps(wire.question_to_json(q))))
        assert back == q


def test_question_key_ignores_metadata_but_not_text_or_state():
    a = ChoiceQ("which?", {"a": None}, qtype="t1", subject="s1")
    b = ChoiceQ("which?", {"a": None}, qtype="t2", subject="s2")
    assert wire.question_key({"x": 1}, a) == wire.question_key({"x": 1}, b)
    assert wire.question_key({"x": 1}, a) != wire.question_key({"x": 2}, a)
    assert wire.question_key({"x": 1}, a) != wire.question_key({"x": 1}, ChoiceQ("which?!", {"a": None}))
    assert len(wire.question_key({}, a)) == 64


def test_decision_round_trip():
    d = Decision("stone", 0.92, {"stone": 0.92, "metal": 0.08}, "jev", True)
    j = wire.decision_to_json(d, suggestion_id=7)
    assert j["suggestion_id"] == 7
    assert wire.decision_from_json(j) == d


def test_options_of():
    assert wire.options_of(NoulQ("q")) == [True, False]
    assert wire.options_of(ChoiceQ("q", {"a": None, "b": None})) == ["a", "b"]
    assert wire.options_of(ScoreQ("q", ["x", "y", "z"])) == [0, 1, 2]


class _Capture:
    def __init__(self):
        self.questions = {}

    def ask(self, state, questions):
        self.questions.update(questions)
        return {qid: Decision(None, 0.0, {}, "none", False) for qid in questions}


def test_classifiers_tag_every_question_with_qtype_and_subject():
    cap = _Capture()
    classify_group_names([{"name": "CHTM_5th", "tris": 1, "z_min": 0, "z_max": 1, "footprint_building": "CHTM"}], cap)
    classify_materials([{"name": "M1", "texture": "m1.png", "kd": [1, 1, 1]}], cap)
    tags = {(q.qtype, q.subject) for q in cap.questions.values()}
    assert tags == {("inv.building", "CHTM_5th"), ("inv.type", "CHTM_5th"), ("inv.floor", "CHTM_5th"),
                    ("inv.duplicate", "CHTM_5th"), ("mat.category", "M1"), ("mat.trim", "M1")}
```

- [ ] **Step 2: Run them and see them fail:**
  `( cd "<wt>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_decide_wire.py -q -p no:cacheprovider )`.
  Expected: an ImportError on `engine.decide.wire`, or a TypeError on the unknown `qtype` argument.

- [ ] **Step 3: Implement.**
  - In `jev.py`, add `qtype: str = ""` and `subject: str = ""` as the last fields of the three frozen dataclasses.
  - In `classify_group_names` and `classify_materials`, pass `qtype=`/`subject=` to every question built, using the
    qtypes listed above.
  - Create `wire.py`:

```python
"""JSON form of questions and decisions, shared by the engine, RemoteDecider and the VPS service."""
from __future__ import annotations

import hashlib
import json

from engine.decide.jev import ChoiceQ, Decision, NoulQ, ScoreQ

_KIND = {NoulQ: "noul", ChoiceQ: "choice", ScoreQ: "score"}


def question_to_json(q) -> dict:
    kind = _KIND[type(q)]
    criteria = None if kind == "noul" else (dict(q.criteria) if kind == "choice" else list(q.criteria))
    return {"kind": kind, "instructions": q.instructions, "criteria": criteria, "qtype": q.qtype, "subject": q.subject}


def question_from_json(d: dict):
    meta = {"qtype": d.get("qtype") or "", "subject": d.get("subject") or ""}
    if d["kind"] == "noul":
        return NoulQ(d["instructions"], **meta)
    if d["kind"] == "choice":
        return ChoiceQ(d["instructions"], dict(d["criteria"]), **meta)
    if d["kind"] == "score":
        return ScoreQ(d["instructions"], list(d["criteria"]), **meta)
    raise ValueError(f"unknown question kind {d['kind']!r}")


def question_key(state: dict, q) -> str:
    j = question_to_json(q)
    body = {"state": state, "kind": j["kind"], "instructions": j["instructions"], "criteria": j["criteria"]}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def decision_to_json(d: Decision, suggestion_id: int | None = None) -> dict:
    return {"answer": d.answer, "confidence": d.confidence, "probabilities": d.probabilities, "source": d.source,
            "accepted": d.accepted, "error": d.error, "suggestion_id": suggestion_id}


def decision_from_json(d: dict) -> Decision:
    return Decision(d.get("answer"), float(d.get("confidence") or 0.0), dict(d.get("probabilities") or {}),
                    d.get("source") or "error", bool(d.get("accepted")), d.get("error") or "")


def options_of(q) -> list:
    if isinstance(q, NoulQ):
        return [True, False]
    if isinstance(q, ChoiceQ):
        return list(q.criteria)
    return list(range(len(q.criteria)))
```

- [ ] **Step 4: Run the new tests, then all decide tests:** `engine/tests/test_decide_wire.py`,
  `engine/tests/test_decide_jev.py` and `engine/tests/test_decide_pilot.py`. Expected: all pass. The existing decide
  tests must pass unchanged, because the new fields have defaults.
- [ ] **Step 5: Commit:** `feat(decide): questions carry qtype/subject; wire format and question_key`.

---

### Task J2: the service core (store protocol, memory store, logic)

**Files:**
- Create: `deploy/vps/decide/decide_service/__init__.py` (empty), `settings.py`, `store.py`, `logic.py`
- Test: `deploy/vps/decide/tests/test_logic.py`, `deploy/vps/decide/tests/__init__.py` (empty)

**Interfaces:**
- Consumes: `engine.decide.jev` (`JevDecider`, `Decision`, `check_question_limits`); `engine.decide.wire` (J1).
- Produces:
  - `Settings` fields: `jev_enabled: bool`, `daily_token_cap: int`, `min_confidence: float`,
    `owner_users: frozenset[str]`, `engine_user: str`, `database_url: str`. `Settings.from_env()` reads
    `DECIDE_JEV_ENABLED` (default false), `DECIDE_DAILY_TOKEN_CAP` (default 1000000), `DECIDE_MIN_CONFIDENCE`
    (default 0.8), `DECIDE_OWNER_USERS` (default `gab`, comma-separated) and `DECIDE_DATABASE_URL`.
  - `Store` protocol, implemented by `MemoryStore`, with these methods. A suggestion row is a dict with keys `id, qtype,
    subject, key, state, question, answer, confidence, probabilities, model, source, status, owner_answer,
    reviewed_at, reviewed_by, created_at`.
    - `find_by_key(key) -> dict | None`;
    - `add_suggestion(row: dict) -> int`;
    - `update_suggestion(id, **fields) -> None`;
    - `get(id) -> dict | None`;
    - `owner_answer(qtype, subject) -> object | None`;
    - `confirmed(qtype) -> dict[str, object]`;
    - `list(status=None, qtype=None, min_conf=None, q=None, limit=100, offset=0) -> list[dict]`;
    - `counts(qtype=None) -> dict[str, int]`;
    - `add_call(entry: dict) -> None`;
    - `tokens_today() -> int`.
  - `logic.answer(store, cfg, make_decider, state, questions) -> dict[str, dict]`: each value is
    `wire.decision_to_json(...)` with a `suggestion_id`.
  - `logic.review(store, id, user, accept=False, answer=None) -> dict`, which raises `ValueError` for an answer that is
    not an option, and `KeyError` for an unknown id.
  - `logic.reask(store, cfg, make_decider, id) -> dict`.
  - `logic.import_items(store, items) -> dict` returns `{"added": n, "skipped": m}`.

- [ ] **Step 1: Write the failing tests.** `tests/test_logic.py` uses `MemoryStore`, `Settings(jev_enabled=...)` and
  `JevDecider(client=FakeClient(...))`, where `FakeClient.system_one` records each call and returns canned answers.
  Copy the FakeClient pattern from `engine/tests/test_decide_jev.py`. The tests, each with one assert block:
  1. **Jev off:** with `jev_enabled=False`, an uncached question comes back `source == "none"` and
     `error == "jev off"`, and the fake client is never called.
  2. **Jev on:** with `jev_enabled=True`, a new question calls Jev once and stores one `pending` suggestion with
     `source == "jev"`. The answer carries `suggestion_id`.
  3. **Cache:** asking the same question again, with the same state and text, makes no new call and returns the
     same `suggestion_id`.
  4. **Owner wins:** after `review(store, id, "gab", answer="metal")`, asking with the same `qtype` and `subject`
     returns `answer == "metal"`, `source == "owner"`, `accepted is True`, and makes no call.
  5. **Review validation:** `review` with an answer not in `options_of` raises ValueError; `review(accept=True)`
     sets `status == "accepted"` and `owner_answer` to Jev's answer.
  6. **Daily cap:** with `store.tokens_today()` at the cap, an uncached question comes back `none` with
     `error == "daily cap"`, and there is no call.
  7. **Limits:** an 11-level `ScoreQ` raises ValueError before any call.
  8. **Calls recorded:** each Jev call adds a `calls` entry with tokens. A call that raises with the key in its
     message leaves no trace of the key in the stored rows, the calls or the returned JSON (`json.dumps`).
  9. **Import:** `import_items` adds new rows as `source == "pilot-import"`, skips an existing key, and returns the
     counts.
  10. **Reask:** with Jev on, it calls Jev for that one row, updates its answer and sets `status` back to
      `pending`. With Jev off it raises `PermissionError("jev off")`.
  11. **Confirmed:** `confirmed("mat.category")` returns only reviewed subjects, each with its latest owner answer.

- [ ] **Step 2: Run them and see them fail** (`ModuleNotFoundError: decide_service`):
  `( cd "<wt>" && PYTHONPATH="$PWD;$PWD/deploy/vps/decide" "$PY" -m pytest deploy/vps/decide/tests/test_logic.py -q -p no:cacheprovider )`.

- [ ] **Step 3: Implement** `settings.py` (a dataclass plus `from_env`), `store.py` (the `Store` Protocol plus
  `MemoryStore`, a list of row dicts, a list of calls and an id counter; `tokens_today` sums the input and output
  tokens of calls whose `at` date is today in UTC), and `logic.py`:

```python
"""The order of answers: the owner's confirmed answer, then a stored suggestion, then Jev (if on and under the cap)."""
from __future__ import annotations

import datetime as dt
import json

from engine.decide import wire
from engine.decide.jev import Decision, check_question_limits

STATE_MAX = 2000


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _none(reason: str) -> dict:
    return wire.decision_to_json(Decision(None, 0.0, {}, "none", False, reason))


def answer(store, cfg, make_decider, state, questions: dict) -> dict:
    check_question_limits(questions)
    state = {"text": state} if isinstance(state, str) else state
    out: dict[str, dict] = {}
    todo: dict[str, tuple] = {}
    for qid, q in questions.items():
        if q.qtype and q.subject:
            owner = store.owner_answer(q.qtype, q.subject)
            if owner is not None:
                out[qid] = wire.decision_to_json(Decision(owner, 1.0, {}, "owner", True))
                continue
        key = wire.question_key(state, q)
        row = store.find_by_key(key)
        if row is not None:
            d = Decision(row["answer"], row["confidence"], row["probabilities"] or {}, row["source"],
                         row["confidence"] >= cfg.min_confidence)
            out[qid] = wire.decision_to_json(d, row["id"])
            continue
        todo[qid] = (q, key)
    if not todo:
        return out
    reason = None if cfg.jev_enabled else "jev off"
    if reason is None and store.tokens_today() >= cfg.daily_token_cap:
        reason = "daily cap"
    if reason is not None:
        out.update({qid: _none(reason) for qid in todo})
        return out
    decider = make_decider()
    decisions = decider.ask(state, {qid: q for qid, (q, _) in todo.items()})
    for entry in decider.calls:
        store.add_call({**entry, "at": _now()})
    state_text = json.dumps(state, sort_keys=True)[:STATE_MAX]
    for qid, (q, key) in todo.items():
        d = decisions[qid]
        sid = None
        if d.source == "jev":
            sid = store.add_suggestion({
                "qtype": q.qtype, "subject": q.subject, "key": key, "state": state_text,
                "question": wire.question_to_json(q), "answer": d.answer, "confidence": d.confidence,
                "probabilities": d.probabilities, "model": decider.model, "source": "jev", "status": "pending",
                "owner_answer": None, "reviewed_at": None, "reviewed_by": None, "created_at": _now()})
        out[qid] = wire.decision_to_json(d, sid)
    return out


def review(store, id: int, user: str, accept: bool = False, answer=None) -> dict:
    row = store.get(id)
    if row is None:
        raise KeyError(id)
    q = wire.question_from_json(row["question"])
    value = row["answer"] if accept else answer
    if value not in wire.options_of(q):
        raise ValueError(f"answer must be one of {wire.options_of(q)!r}")
    status = "accepted" if accept or value == row["answer"] else "changed"
    store.update_suggestion(id, status=status, owner_answer=value, reviewed_at=_now(), reviewed_by=user)
    return store.get(id)


def reask(store, cfg, make_decider, id: int) -> dict:
    if not cfg.jev_enabled:
        raise PermissionError("jev off")
    if store.tokens_today() >= cfg.daily_token_cap:
        raise PermissionError("daily cap")
    row = store.get(id)
    if row is None:
        raise KeyError(id)
    q = wire.question_from_json(row["question"])
    decider = make_decider()
    d = decider.ask(json.loads(row["state"]), {"q": q})["q"]
    for entry in decider.calls:
        store.add_call({**entry, "at": _now()})
    if d.source == "jev":
        store.update_suggestion(id, answer=d.answer, confidence=d.confidence, probabilities=d.probabilities,
                                model=decider.model, source="jev", status="pending", owner_answer=None,
                                reviewed_at=None, reviewed_by=None)
    return store.get(id)


def import_items(store, items: list[dict]) -> dict:
    added = skipped = 0
    for it in items:
        q = wire.question_from_json(it["question"])
        state = it["state"]
        key = wire.question_key(state, q)
        if store.find_by_key(key) is not None:
            skipped += 1
            continue
        store.add_suggestion({
            "qtype": q.qtype, "subject": q.subject, "key": key,
            "state": json.dumps(state, sort_keys=True)[:STATE_MAX], "question": wire.question_to_json(q),
            "answer": it["answer"], "confidence": float(it["confidence"]),
            "probabilities": it.get("probabilities") or {}, "model": it.get("model") or "",
            "source": "pilot-import", "status": "pending", "owner_answer": None, "reviewed_at": None,
            "reviewed_by": None, "created_at": _now()})
        added += 1
    return {"added": added, "skipped": skipped}
```

  `MemoryStore.owner_answer` returns the `owner_answer` of the latest reviewed row (status `accepted` or `changed`)
  with that `qtype` and `subject`, by `reviewed_at`. `confirmed` does the same for every subject of a qtype. `counts`
  returns `{"pending": n, "accepted": n, "changed": n}`.
  Note that `reask` keeps the row's `state` text, which is cut to 2,000 characters. The material and group states are
  far shorter (about 300 characters).
- [ ] **Step 4: Run the tests:** all 11 pass.
- [ ] **Step 5: Commit:** `feat(decide-service): store protocol, memory store, answer order owner > stored > Jev`.

---

### Task J3: the Postgres store and its schema

**Files:**
- Create: `deploy/vps/decide/schema.sql`, `deploy/vps/decide/decide_service/pgstore.py`
- Test: `deploy/vps/decide/tests/test_store_contract.py`

**Interfaces:**
- Consumes: the `Store` protocol and `MemoryStore` (J2).
- Produces: `PostgresStore(dsn: str)`, which implements every `Store` method. `PostgresStore.ensure_schema()` runs
  `schema.sql`, which is idempotent.

- [ ] **Step 1: Write `schema.sql`:**

```sql
create schema if not exists decide;
create table if not exists decide.suggestions (
  id bigserial primary key,
  qtype text not null default '', subject text not null default '',
  key char(64) not null unique, state text not null, question jsonb not null,
  answer jsonb, confidence double precision not null default 0, probabilities jsonb not null default '{}',
  model text not null default '', source text not null,
  status text not null default 'pending' check (status in ('pending','accepted','changed')),
  owner_answer jsonb, reviewed_at timestamptz, reviewed_by text,
  created_at timestamptz not null default now());
create index if not exists suggestions_owner on decide.suggestions (qtype, subject, reviewed_at desc);
create index if not exists suggestions_status on decide.suggestions (status, qtype);
create table if not exists decide.calls (
  id bigserial primary key, at timestamptz not null default now(), questions int not null,
  latency_ms int, input_tokens int, output_tokens int, model text, ok boolean not null, error_class text);
```

- [ ] **Step 2: Write the contract tests.** One parametrized fixture yields a `MemoryStore` and, when
  `DECIDE_TEST_DATABASE_URL` is set, a fresh `PostgresStore`. The fixture drops and recreates the schema `decide`
  before each test. The tests, run against both stores:
  - add, then `find_by_key`;
  - `update_suggestion`, then `get`;
  - `owner_answer` returns the latest review;
  - `confirmed` returns the latest per subject;
  - `list` filters by status, qtype, `min_conf` and `q` (a case-insensitive substring of the subject);
  - `counts`;
  - `tokens_today` counts only today's calls;
  - an answer of each JSON type (str, bool, int, float) comes back with its type.
- [ ] **Step 3: Start the throwaway database and see the Postgres half fail:**
  - `docker run --rm -d --name decide-test-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16-alpine`
  - then `( cd "<wt>" && DECIDE_TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres PYTHONPATH="$PWD;$PWD/deploy/vps/decide" "$PY" -m pytest deploy/vps/decide/tests/test_store_contract.py -q -p no:cacheprovider )`
  - Expected: the memory half passes; the Postgres half fails with an ImportError on `pgstore`.
- [ ] **Step 4: Implement `PostgresStore`** with psycopg 3 (`psycopg.connect(dsn, autocommit=True)`, a
  `dict_row` row factory). JSON columns go in through `psycopg.types.json.Jsonb`. Every query has parameters only,
  never f-strings. Run until both halves pass.
- [ ] **Step 5: Stop the database** (`docker stop decide-test-pg`) and **commit**:
  `feat(decide-service): Postgres store, schema decide, contract tests shared with the memory store`.

---

### Task J4: the HTTP app and its roles

**Files:**
- Create: `deploy/vps/decide/decide_service/app.py`
- Test: `deploy/vps/decide/tests/test_app.py`

**Interfaces:**
- Consumes: `logic`, `Settings`, `Store` (J2); `wire` (J1).
- Produces: `create_app(store, cfg, make_decider) -> FastAPI`, with these endpoints. Role errors are 403; a missing
  `X-Remote-User` is 401.

| Endpoint | Role | Body / query | Answer |
|---|---|---|---|
| `POST /api/decide/ask` | engine | `{"state": {...}, "questions": {qid: question_json}}` | `{"answers": {qid: decision_json}}`; a limit breach is 400 with the message |
| `GET /api/decide/suggestions` | owner | `status, type, min_conf, q, limit, offset` | `{"items": [...], "counts": {...}}`, without the `key` and `state` columns |
| `POST /api/decide/review/{id}` | owner | `{"accept": true}` or `{"answer": value}` | the row; 422 if not an option; 404 if unknown |
| `POST /api/decide/reask/{id}` | owner | none | the row; 409 `{"detail": "jev off"}` or `"daily cap"` |
| `GET /api/decide/confirmed` | either | `type` (required) | `{"type": t, "answers": {subject: answer}}` |
| `POST /api/decide/import` | engine | `{"items": [{state, question, answer, confidence, probabilities?, model?}]}` | `{"added", "skipped"}` |
| `GET /api/decide/health` | either | none | `{"ok": true, "jev_enabled", "tokens_today", "daily_token_cap"}` |

- [ ] **Step 1: Write the failing tests** with `fastapi.testclient.TestClient(create_app(MemoryStore(),
  Settings(jev_enabled=False, ...), make_decider))`. Cover:
  - each endpoint's happy path;
  - `uc-engine` gets 403 on review, reask and suggestions;
  - `gab` gets 403 on ask and import;
  - no header gives 401;
  - an 11-level Score on ask gives 400 with "at most 10 levels";
  - reask with Jev off gives 409 "jev off";
  - `health` shows `jev_enabled: false`;
  - a fake decider whose client raises with a fake key: the key is absent from every response body and from
    caplog at DEBUG.
- [ ] **Step 2: Run them and see them fail** (ImportError).
- [ ] **Step 3: Implement `app.py`.** The role check is one dependency:

```python
def _user(request: Request) -> str:
    user = request.headers.get("X-Remote-User", "")
    if not user:
        raise HTTPException(401, "no user")
    return user


def _role(cfg):
    def owner(user: str = Depends(_user)) -> str:
        if user not in cfg.owner_users:
            raise HTTPException(403, "owner only")
        return user

    def engine(user: str = Depends(_user)) -> str:
        if user != cfg.engine_user:
            raise HTTPException(403, "engine only")
        return user

    def either(user: str = Depends(_user)) -> str:
        if user != cfg.engine_user and user not in cfg.owner_users:
            raise HTTPException(403, "unknown user")
        return user
    return owner, engine, either
```

  `ask` turns each `question_json` into a question with `wire.question_from_json`, then calls `logic.answer`; a
  `ValueError` from it becomes 400. The suggestions listing drops the `key` and `state` columns.
- [ ] **Step 4: Run the tests until all pass.**
- [ ] **Step 5: Commit:** `feat(decide-service): HTTP endpoints with engine/owner roles from X-Remote-User`.

---

### Task J5: the image, the VPS stack files and the runbook

**Files:**
- Create: `deploy/vps/decide/decide_service/main.py`, `deploy/vps/decide/Dockerfile`,
  `deploy/vps/decide/requirements.txt`
- Modify: `deploy/vps/docker-compose.yml`, `deploy/vps/nginx.conf`, `deploy/vps/README.md`
- Test: `deploy/vps/decide/tests/test_main.py`, plus the container smoke run in Step 4

**Interfaces:**
- Consumes: `create_app`, `PostgresStore`, `Settings` (J2-J4).
- Produces: the image `ucmodelfixer-decide:vps`, listening on port 8200 inside the network `internal`.

- [ ] **Step 1: Write the failing test** `test_main.py`. With the environment set (`DECIDE_DATABASE_URL` for the
  memory store, `DECIDE_JEV_ENABLED` unset), `main.build_app(store_factory=lambda url: MemoryStore())` returns an app
  whose health says `jev_enabled: false`. `main.make_decider()` builds `JevDecider(env_file=Path("/nonexistent"),
  min_confidence=cfg.min_confidence)`, so the key comes from the environment only. Assert that its `available` follows
  `TYPESAFE_API_KEY` set or unset, using a fake value, and that `repr` never shows it.
- [ ] **Step 2: Implement `main.py`** (`build_app`, `make_decider`, and `app = build_app()` guarded by
  `if os.environ.get("DECIDE_DATABASE_URL")`), `requirements.txt` (`fastapi>=0.115`, `uvicorn[standard]>=0.30`,
  `psycopg[binary]>=3.2`, `typesafe-sdk>=0.7.2,<0.8`) and the `Dockerfile`, built from the repo root:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY deploy/vps/decide/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY engine/__init__.py /app/engine/__init__.py
COPY engine/decide /app/engine/decide
COPY deploy/vps/decide/decide_service /app/decide_service
COPY deploy/vps/decide/schema.sql /app/schema.sql
ENV PYTHONPATH=/app
EXPOSE 8200
CMD ["uvicorn", "decide_service.main:app", "--host", "0.0.0.0", "--port", "8200"]
```

  `main.build_app` calls `PostgresStore(url).ensure_schema()` once at start.
- [ ] **Step 3: The stack files.**
  - `docker-compose.yml`: add the service `decide`. It uses `image: ucmodelfixer-decide:vps`,
    `container_name: uc-fixer-decide` and `env_file: ./decide.env`, with this `environment`:
    `DECIDE_DATABASE_URL: postgresql://fixer:fixer@uc-fixer-db:5432/fixer`, `DECIDE_JEV_ENABLED: "false"`,
    `DECIDE_OWNER_USERS: gab`. It has `depends_on: db: condition: service_healthy`, `networks: [internal]`,
    `restart: unless-stopped`, and no published ports.
  - `nginx.conf`: put this before `location /api/`:

```nginx
    location /api/decide/ {
        proxy_pass http://uc-fixer-decide:8200;
        proxy_read_timeout 60s;
        proxy_set_header Host $host;
        proxy_set_header X-Remote-User $remote_user;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location = /api/decide/ask {
        if ($remote_user != "uc-engine") { return 403; }
        proxy_pass http://uc-fixer-decide:8200;
        proxy_set_header X-Remote-User $remote_user;
    }
```

  - `README.md`: a section **"Jev service (uc-fixer-decide)"**. It holds:
    - what the service does;
    - that Jev is off by default;
    - the owner's prompted commands: the `uc-engine` login (the same `htpasswd -B` command without `-c`, user
      `uc-engine`), and `decide.env`, written by
      `ssh -t … "read -rs -p 'TypeSafe key: ' K; umask 077; printf 'TYPESAFE_API_KEY=%s\n' \"\$K\" > /docker/uc-fixer/decide.env"`;
    - the image load (`docker save ucmodelfixer-decide:vps | ssh … docker load`);
    - how to switch Jev on later (add `DECIDE_JEV_ENABLED=true` to `decide.env`, then `docker compose up -d decide`,
      each with the owner's OK);
    - the rollback (`docker compose rm -sf decide`; the schema `decide` stays unless the owner asks for it to be
      dropped).
- [ ] **Step 4: Build and smoke-run on the PC**, never touching the `fixer-*` containers:
  - `docker build -f deploy/vps/decide/Dockerfile -t ucmodelfixer-decide:vps .`
  - `docker network create decide-smoke`
  - `docker run -d --rm --name decide-smoke-db --network decide-smoke -e POSTGRES_PASSWORD=test postgres:16-alpine`
  - wait for `docker exec decide-smoke-db pg_isready`
  - `docker run -d --rm --name decide-smoke --network decide-smoke -p 58200:8200 -e DECIDE_DATABASE_URL=postgresql://postgres:test@decide-smoke-db:5432/postgres ucmodelfixer-decide:vps`
  - `curl -s -H "X-Remote-User: gab" http://localhost:58200/api/decide/health` → expected
    `{"ok":true,"jev_enabled":false,...}`
  - then stop both containers and remove the network.
- [ ] **Step 5: Commit:** `feat(decide-service): image, VPS compose service, nginx route, runbook (Jev off by default)`.

---

### Task J6: RemoteDecider and decide-pull (engine)

**Files:**
- Create: `engine/decide/remote.py`
- Modify: `engine/cli.py`, adding the subcommand `decide-pull`
- Test: `engine/tests/test_decide_remote.py`

**Interfaces:**
- Consumes: `wire` (J1); the endpoints of J4.
- Produces:
  - `RemoteDecider(url: str, user: str = "uc-engine", password: str | None = None, timeout: float = 10.0, *,
    env_file=None)`. It has `.available`, `.ask(state, questions) -> dict[str, Decision]`, `.calls` (one entry per
    HTTP call: `ok`, `status`, `latency_s`, `error`) and a `repr` without the password. The password comes from
    `UC_DECIDE_PASSWORD`, else that one line of the `.env` (reusing `jev.read_env_key`'s pattern, generalized to a
    variable name).
  - `pull_confirmed(url, qtype, out_dir, ...) -> Path` writes `<out_dir>/<qtype>.json` as `{subject: answer}`.
  - CLI: `decide-pull --url URL --type QTYPE [--out data/decide/confirmed] [--env-file PATH]`.

- [ ] **Step 1: Write the failing tests**, against a local `http.server` in a thread that records each request and
  answers canned JSON:
  - `ask` sends `questions` through `wire.question_to_json`, with Basic auth for `uc-engine`, and maps the answers back
    to `Decision`;
  - a server that sleeps past `timeout` gives every decision `source == "none"`, `accepted is False`, `error` set,
    and the call takes no longer than the timeout plus 1 s;
  - a 401 or a 500 gives `source == "error"` with `error == "HTTP 401"` or `"HTTP 500"`, and no retries (the server
    saw exactly 1 request);
  - with no password, `available is False` and `ask` returns `none` without any request;
  - the password is absent from `repr`, from captured logs at DEBUG and from exception text;
  - `pull_confirmed` writes the file;
  - `classify_materials(items, RemoteDecider(...))` works unchanged.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement it with `urllib.request`.** No new dependency. Build the Basic header from
  `base64.b64encode(f"{user}:{password}".encode())`. Catch every exception per call; the error text is the class name
  or `HTTP <status>` only.
- [ ] **Step 4: Run the decide tests until all pass:** `test_decide_remote.py`, `test_decide_wire.py`,
  `test_decide_jev.py`, `test_decide_pilot.py`.
- [ ] **Step 5: Commit:** `feat(decide): RemoteDecider (same ask as JevDecider, never waits) and decide-pull`.

---

### Task J7: decide-import-pilot (engine)

**Files:**
- Create: `engine/decide/pilot_import.py`
- Modify: `engine/cli.py`, adding the subcommand `decide-import-pilot`
- Test: `engine/tests/test_decide_pilot_import.py`

**Interfaces:**
- Consumes: `pilot.group_rows`, `classify_group_names`, `classify_materials`, `_LABEL_OF` (jev.py); `wire` (J1);
  `RemoteDecider`'s HTTP helper (J6) for `POST /api/decide/import`.
- Produces:
  - `build_import_items(source: dict, materials: dict, pilot: dict) -> list[dict]`, each item
    `{state, question, answer, confidence, model}`;
  - CLI: `decide-import-pilot --url URL --source data/campus/source.json --materials data/campus/materials.json
    --pilot data/campus/jev_pilot.json [--env-file PATH] [--dry-run]`.

- [ ] **Step 1: Write the failing tests** with a small fake `source`, `materials` and `pilot`:
  - **Groups:** the questions are captured by running the real classifiers with a capturing decider. Each group gets
    4 items, matched by the row name in `pilot["groups"]["rows"]`. The building answer goes back to its option label
    through `_LABEL_OF` (`MAIN_INFRA` → `"MAIN INFRASTRUCTURE"`); the floor goes back to its option key (`5` → `"5"`);
    `type` stays as is; `duplicate` stays a bool.
  - **Materials:** only the names in `pilot["materials"]["spot_check"]` produce an item, for `mat.category` only (the
    pilot keeps no confidence for `trim`).
  - **Skipped rows:** a pilot row whose decision has `source != "jev"` or answer `None` is skipped.
  - **Key match:** each item's `wire.question_key(item["state"], question)` equals the key a live call would
    produce for the same row.
  - **Dry run:** `--dry-run` prints the counts and sends nothing.
- [ ] **Step 2: Run them and see them fail.**
- [ ] **Step 3: Implement.** Capture the questions with a decider that records `(state, questions)` and returns
  `none`. Pair by the index in the qid (`"<i>:<field>"`) with `rows[i]["name"]` and the pilot's answers. Post in
  chunks of 200 items.
- [ ] **Step 4: Run the tests, then a dry run on the real files:**
  `"$PY" -m engine.cli decide-import-pilot --url http://unused --source <main>/data/campus/source.json --materials <main>/data/campus/materials.json --pilot <main>/data/campus/jev_pilot.json --dry-run`
  Expected: `groups: 340 items (85 x 4), materials: 30 items`, or fewer only where the pilot answer was not
  `source == "jev"`.
- [ ] **Step 5: Commit:** `feat(decide): decide-import-pilot loads the paid pilot answers as pending suggestions`.

---

### Task J8: the /jev page

**Files:**
- Create: `web/src/api/decide.ts`, `web/src/utils/jevReview.ts`, `web/src/views/JevView.vue`
- Modify: `web/src/router.ts`, adding `{ path: '/jev', name: 'jev', component: JevView }`
- Test: `web/src/api/decide.test.ts`, `web/src/utils/jevReview.test.ts`

**Interfaces:**
- Consumes: the endpoints of J4.
- Produces:
  - `fetchSuggestions(params) -> Promise<{items, counts}>`, `reviewSuggestion(id, body)`, `reaskSuggestion(id)`,
    `fetchHealth()`. All throw the existing `ApiError` from `./client`.
  - `TABS`, with `{key, label, qtypes, available}` for Materials, Campus map, Next repair step, Review order and
    Fix tie-breaks.
  - `filterRows(rows, {status, minConf, text})`.
  - `topAlternatives(row, n = 2)`.
  - `acceptAllSelection(rows, minConf) -> number[]`, the pending ids at or above `minConf`.
  - `optionLabels(question) -> string[]`.

- [ ] **Step 1: Write the failing Vitest tests**, mocking `globalThis.fetch` as in `client.test.ts`:
  - `reviewSuggestion` posts JSON to `/api/decide/review/7` and turns a 422 into `ApiError`;
  - `fetchHealth` reads `jev_enabled`;
  - `filterRows` filters by status, minimum confidence and a case-insensitive subject search;
  - `topAlternatives` leaves out the chosen answer and sorts by probability;
  - `acceptAllSelection` takes only `pending` rows at or above the threshold;
  - `optionLabels` gives Noul `["yes", "no"]`, the Choice keys, and the Score levels;
  - `TABS` has Materials and Campus map available, the other three not.
- [ ] **Step 2: Run them and see them fail:** `( cd "<wt>/web" && npx vitest run src/api/decide.test.ts src/utils/jevReview.test.ts )`.
- [ ] **Step 3: Implement** the two modules, then `JevView.vue`:
  - the tabs; a banner "Jev is off until the repair engine is ready" when `health.jev_enabled` is false;
  - the counts; the filters;
  - rows with the texture thumbnail at `/api/assets/texture/<name>`, if the dashboard API serves one, otherwise no
    image; check `api/routers` and use only an existing route;
  - the confidence bar and the top-2 alternatives;
  - Accept, and Change (a `<select>` of `optionLabels`);
  - "Accept all shown ≥ X", using `window.confirm` with the count;
  - on a fetch failure with status 404 or 502, "Jev service runs on the VPS".
- [ ] **Step 4: Run the tests and the build** (`npx vitest run` and `npx vite build`). Expected: the tests pass and
  the build succeeds.
- [ ] **Step 5: Commit:** `feat(web): /jev review page for Jev suggestions (accept, change, accept-all with confirm)`.

---

## After the tasks (controller, not a task)

1. Final whole-branch review of `feat/jev-vps`, then merge it into `feat-dashboard`, asking the repair-engine
   session first.
2. The records: the ledger, HANDOFF §2, the session record, QUEUE.md.
3. **Deploy, only with the owner's explicit OK at that moment**, by the J5 runbook. The owner types the `uc-engine`
   password and the TypeSafe key himself. Then the post-deploy checks from the spec (§8), then
   `decide-import-pilot` against the real URL.
4. Jev stays off until the repair engine (P2) is ready. Then `repair.next_step` is designed with P2's steps, and Jev
   is switched on with the owner's OK.
