"""The order of answers: the owner's confirmed answer, then a stored suggestion, then Jev (if on and under the cap)."""
from __future__ import annotations

import dataclasses
import datetime as dt
import json

from engine.decide import wire
from engine.decide.jev import ChoiceQ, Decision, NoulQ, check_question_limits

STATE_MAX = 2000
REVIEWED = ("accepted", "changed")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _none(reason: str) -> dict:
    return wire.decision_to_json(Decision(None, 0.0, {}, "none", False, reason))


def _state(state) -> dict:
    return {"text": state} if isinstance(state, str) else state


def _check_answer(q, value):
    """The owner's answer, strictly typed: Noul a real bool; Choice one of the labels; Score an int level
    (a whole float is stored as int; a bool never). Raises ValueError."""
    if isinstance(q, NoulQ):
        if type(value) is bool:
            return value
    elif isinstance(q, ChoiceQ):
        if isinstance(value, str) and value in q.criteria:
            return value
    else:
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if type(value) is int and 0 <= value < len(q.criteria):
            return value
    raise ValueError(f"answer must be one of {wire.options_of(q)!r} (right type)")


def _jev_answer(q, value):
    """Jev's (or the pilot's) answer as an owner answer: a Score's fractional level is rounded."""
    if not isinstance(q, (NoulQ, ChoiceQ)) and isinstance(value, float):
        value = round(value)
    return _check_answer(q, value)


def _row(q, key, state, d, model, source) -> dict:
    return {"qtype": q.qtype, "subject": q.subject, "key": key,
            "state": json.dumps(state, sort_keys=True)[:STATE_MAX], "state_json": state,
            "question": wire.question_to_json(q), "answer": d.answer, "confidence": d.confidence,
            "probabilities": d.probabilities, "model": model, "source": source, "status": "pending",
            "owner_answer": None, "reviewed_at": None, "reviewed_by": None, "created_at": _now()}


def _record_calls(store, decider, start: int) -> None:
    for entry in decider.calls[start:]:
        store.add_call({**entry, "at": _now()})


def answer(store, cfg, make_decider, state, questions: dict) -> dict:
    check_question_limits(questions)
    state = _state(state)
    out: dict[str, dict] = {}
    todo: dict[str, tuple] = {}              # key -> (question, [qids asking it])
    for qid, q in questions.items():
        if q.qtype and q.subject:
            owner = store.owner_answer(q.qtype, q.subject)
            if owner is not None:
                out[qid] = wire.decision_to_json(Decision(owner, 1.0, {}, "owner", True))
                continue
        key = wire.question_key(state, q)
        row = store.find_by_key(key)
        if row is not None:
            if row["status"] in REVIEWED:
                d = Decision(row["owner_answer"], 1.0, {}, "owner", True)
            else:
                d = Decision(row["answer"], row["confidence"], row["probabilities"] or {}, row["source"],
                             row["confidence"] >= cfg.min_confidence)
            out[qid] = wire.decision_to_json(d, row["id"])
            continue
        if key in todo:
            todo[key][1].append(qid)
        else:
            todo[key] = (q, [qid])
    if not todo:
        return out
    if not cfg.jev_enabled:
        for _, qids in todo.values():
            out.update({qid: _none("jev off") for qid in qids})
        return out
    keys = list(todo)
    decider = None
    size = max(1, int(cfg.batch))
    for start in range(0, len(keys), size):
        chunk = keys[start:start + size]
        if store.tokens_today() >= cfg.daily_token_cap:
            for key in chunk:
                out.update({qid: _none("daily cap") for qid in todo[key][1]})
            continue
        if decider is None:
            decider = make_decider()
        before = len(decider.calls)
        decisions = decider.ask(state, {todo[key][1][0]: todo[key][0] for key in chunk})
        _record_calls(store, decider, before)
        for key in chunk:
            q, qids = todo[key]
            d = decisions[qids[0]]
            sid = None
            if d.source == "jev":
                d = dataclasses.replace(d, accepted=d.confidence >= cfg.min_confidence)
                sid = store.add_suggestion(_row(q, key, state, d, decider.model, "jev"))
            for qid in qids:
                out[qid] = wire.decision_to_json(d, sid)
    return out


def review(store, id: int, user: str, accept: bool = False, answer=None) -> dict:
    row = store.get(id)
    if row is None:
        raise KeyError(id)
    q = wire.question_from_json(row["question"])
    if accept:
        value = _jev_answer(q, row["answer"])
        suggested = value
    else:
        value = _check_answer(q, answer)
        try:
            suggested = _jev_answer(q, row["answer"])
        except ValueError:
            suggested = object()
    status = "accepted" if accept or value == suggested else "changed"
    store.update_suggestion(id, status=status, owner_answer=value, reviewed_at=_now(), reviewed_by=user)
    return store.get(id)


def reask(store, cfg, make_decider, id: int) -> dict:
    """Refreshes Jev's fields only. The owner's confirmation (status, owner_answer, reviewed_*) stays."""
    if not cfg.jev_enabled:
        raise PermissionError("jev off")
    if store.tokens_today() >= cfg.daily_token_cap:
        raise PermissionError("daily cap")
    row = store.get(id)
    if row is None:
        raise KeyError(id)
    q = wire.question_from_json(row["question"])
    state = row.get("state_json")
    if state is None:
        state = json.loads(row["state"])
    decider = make_decider()
    before = len(decider.calls)
    d = decider.ask(state, {"q": q})["q"]
    _record_calls(store, decider, before)
    if d.source != "jev":
        raise RuntimeError(d.error or "no answer")
    store.update_suggestion(id, answer=d.answer, confidence=d.confidence, probabilities=d.probabilities,
                            model=decider.model, source="jev")
    return store.get(id)


def import_items(store, items: list[dict]) -> dict:
    added = skipped = invalid = 0
    for it in items:
        try:
            q = wire.question_from_json(it["question"])
            state = _state(it["state"])
            _jev_answer(q, it["answer"])
            confidence = float(it["confidence"])
            key = wire.question_key(state, q)
        except (KeyError, TypeError, ValueError):
            invalid += 1
            continue
        if store.find_by_key(key) is not None:
            skipped += 1
            continue
        d = Decision(it["answer"], confidence, it.get("probabilities") or {}, "pilot-import", False)
        store.add_suggestion(_row(q, key, state, d, it.get("model") or "", "pilot-import"))
        added += 1
    return {"added": added, "skipped": skipped, "invalid": invalid}
