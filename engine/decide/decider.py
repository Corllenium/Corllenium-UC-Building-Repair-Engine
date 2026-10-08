"""The Decider: answers typed "soft" questions the repair rules cannot settle alone (spec section 9).

Order per question: the owner's own confirmed answer, then the deterministic rules, then suggestion
providers (a later job, P1-D2), otherwise the owner's queue. It only ANSWERS questions. It never edits
geometry, sets a tolerance or gives a Validator verdict (AGENTS.md sections 3 and 6). No key and no
network mean rules plus the owner queue; the pipeline never waits.

String conventions are shared with the Jev session (D1-alignment-with-jev-vps.md): qtype is a lowercase
dotted `<area>.<question>`, the question key is the sha256 of canonical JSON of
`{state, kind, instructions, criteria}` (qtype and subject are NOT in it), and answers are kept in raw
option form. Nothing here imports `engine.decide.jev`.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

Kind = Literal["noul", "choice", "score"]
Mode = Literal["off", "suggest", "auto"]

KINDS = ("noul", "choice", "score")
MODES = ("off", "suggest", "auto")
MAX_CHOICE_OPTIONS = 255
MAX_SCORE_LEVELS = 10
_QTYPE_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class QuestionType:
    """A typed question: `choice` criteria are ((label, description), ...) in order, `score` criteria are the
    level texts in order, `noul` has none."""

    qtype: str
    kind: Kind
    instructions: str
    criteria: tuple = ()
    mode: Mode = "suggest"

    def __post_init__(self) -> None:
        if not isinstance(self.qtype, str) or not _QTYPE_RE.match(self.qtype):
            raise ValueError(f"qtype must be a lowercase dotted '<area>.<question>': {self.qtype!r}")
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}: {self.kind!r}")
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}: {self.mode!r}")
        if self.kind == "choice":
            if not self.criteria or len(self.criteria) > MAX_CHOICE_OPTIONS:
                raise ValueError(f"a choice has 1..{MAX_CHOICE_OPTIONS} options: {len(self.criteria)}")
            if any(len(c) != 2 for c in self.criteria):
                raise ValueError("choice criteria are (label, description) pairs")
        elif self.kind == "score":
            if not self.criteria or len(self.criteria) > MAX_SCORE_LEVELS:
                raise ValueError(f"a score has 1..{MAX_SCORE_LEVELS} levels: {len(self.criteria)}")
        elif self.criteria:
            raise ValueError("a noul has no criteria")


@dataclass(frozen=True)
class Question:
    qtype: str
    subject: str
    state: dict


def question_key(qt: QuestionType, q: Question) -> str:
    """sha256 hex of canonical JSON of {state, kind, instructions, criteria}; criteria keep the ORDER."""
    if qt.kind == "choice":
        criteria: Any = [[label, desc] for label, desc in qt.criteria]
    elif qt.kind == "score":
        criteria = list(qt.criteria)
    else:
        criteria = None
    obj = {"state": q.state, "kind": qt.kind, "instructions": qt.instructions, "criteria": criteria}
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass
class Answer:
    qtype: str
    subject: str
    key: str
    answer: str | bool | None  # raw option form
    confidence: float  # 1.0 for rules and owner
    provider: str  # "owner" | "rules" | "<provider name>" | "queue"
    probabilities: dict  # string keys
    accepted: bool  # usable by the engine without the owner
    suggestion: dict | None = None  # the best non-accepted provider answer, shown to the owner
    tokens: int | None = None  # provider-reported, for the log; None for rules and the owner


class RuleProvider:
    name = "rules"


class Decider:
    pass
