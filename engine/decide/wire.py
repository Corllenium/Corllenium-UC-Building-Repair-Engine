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
