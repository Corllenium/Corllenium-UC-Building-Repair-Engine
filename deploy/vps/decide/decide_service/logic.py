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
