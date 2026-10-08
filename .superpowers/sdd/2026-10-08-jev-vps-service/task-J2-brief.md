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

