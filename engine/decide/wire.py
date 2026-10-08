"""JSON form of questions and decisions, shared by the engine, RemoteDecider and the VPS service."""
from __future__ import annotations

import hashlib
import json

from engine.decide.jev import ChoiceQ, Decision, NoulQ, ScoreQ

def question_to_json(q) -> dict:
    if isinstance(q, NoulQ):
        kind, criteria = "noul", None
    elif isinstance(q, ChoiceQ):
        kind, criteria = "choice", dict(q.criteria)
    elif isinstance(q, ScoreQ):
        kind, criteria = "score", list(q.criteria)
    else:
        raise TypeError(f"unsupported question type {type(q).__name__}")
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
    """sha256 of the canonical JSON of state, kind, instructions and criteria. Choice criteria are encoded as
    ordered [label, description] pairs, so their order is part of the key; qtype and subject are not."""
    j = question_to_json(q)
    criteria = [[k, v] for k, v in j["criteria"].items()] if j["kind"] == "choice" else j["criteria"]
    body = {"state": state, "kind": j["kind"], "instructions": j["instructions"], "criteria": criteria}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def decision_to_json(d: Decision, suggestion_id: int | None = None) -> dict:
    """Probabilities are string-keyed on the wire; consumers normalise (the floor classifier does via
    _floor_to_int)."""
    return {"answer": d.answer, "confidence": d.confidence, "probabilities": d.probabilities, "source": d.source,
            "accepted": d.accepted, "error": d.error, "suggestion_id": suggestion_id}


def decision_from_json(d: dict) -> Decision:
    """Probabilities are string-keyed on the wire; consumers normalise (the floor classifier does via
    _floor_to_int)."""
    return Decision(d.get("answer"), float(d.get("confidence") or 0.0), dict(d.get("probabilities") or {}),
                    d.get("source") or "error", d.get("accepted") is True, d.get("error") or "")


def options_of(q) -> list:
    if isinstance(q, NoulQ):
        return [True, False]
    if isinstance(q, ChoiceQ):
        return list(q.criteria)
    return list(range(len(q.criteria)))
