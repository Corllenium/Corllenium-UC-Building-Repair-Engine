"""Jev as a suggestion provider behind the Decider (spec section 9; Jev VPS spec sections 2 and 6).

`AskProvider` wraps anything with `.ask(state, questions) -> {qid: Decision}` and a `.calls` list: the local
`JevDecider` or the VPS `RemoteDecider`. It builds one jev question per Decider `Question` from its
`QuestionType`, asks once per distinct state, and maps each `Decision` to an `Answer` (never accepted: the
Decider decides what a suggestion is worth) or to the `Unavailable` marker. It never returns `None`: Jev either
answers or is unavailable, and a cacheable "no answer" would freeze the question for good.

`sync_confirmed` feeds the owner's confirmed answers (`<qtype>.json`, `{subject: answer}`, written by
`engine.cli decide-pull`) into the Decider as owner answers, the only way an owner fact enters it.

Only text leaves the machine (questions are the same text the classifiers send). Nothing here reads a key, a
password or an env file, and no `Unavailable` reason ever holds more than a class name, `HTTP <status>`,
"jev off" or "daily cap".
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from engine.decide import decider as decider_module
from engine.decide import jev
from engine.decide.decider import (
    UNAVAILABLE,
    Answer,
    Decider,
    Question,
    QuestionType,
    Unavailable,
    _normalise,
)

log = logging.getLogger(__name__)

_JEV_SOURCES = ("jev", "pilot-import")


def _jev_question(qt: QuestionType, q: Question):
    if qt.kind == "noul":
        return jev.NoulQ(qt.instructions, qtype=qt.qtype, subject=q.subject)
    if qt.kind == "choice":
        return jev.ChoiceQ(qt.instructions, {label: desc for label, desc in qt.criteria},
                           qtype=qt.qtype, subject=q.subject)
    return jev.ScoreQ(qt.instructions, list(qt.criteria), qtype=qt.qtype, subject=q.subject)


def _state_key(state: dict) -> str:
    return json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _token_total(calls: list[dict]) -> int | None:
    """input + output tokens over these `.calls` entries (None counts as 0); None when none has token data."""
    seen, total = False, 0
    for entry in calls:
        if not isinstance(entry, dict):
            continue
        for field in ("input_tokens", "output_tokens"):
            value = entry.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                seen, total = True, total + int(value)
    return total if seen else None


class AskProvider:
    """A Decider provider backed by a Jev decider (`JevDecider` or `RemoteDecider`)."""

    def __init__(self, name: str, decider):
        self.name = name
        self.decider = decider

    def answer(self, qt: QuestionType, questions: list[Question]) -> "list[Answer | None | Unavailable]":
        groups: dict[str, list[int]] = {}
        for i, q in enumerate(questions):
            groups.setdefault(_state_key(q.state), []).append(i)
        calls = getattr(self.decider, "calls", None)
        before = len(calls) if isinstance(calls, list) else 0
        out: "list[Answer | Unavailable | None]" = [None] * len(questions)
        for idxs in groups.values():
            asked = {str(i): _jev_question(qt, questions[i]) for i in idxs}
            try:
                decisions = self.decider.ask(questions[idxs[0]].state, asked)
            except Exception as exc:  # noqa: BLE001 -- it should not raise; never keep the message
                for i in idxs:
                    out[i] = Unavailable(type(exc).__name__)
                continue
            for i in idxs:
                out[i] = self._map(qt, questions[i], decisions.get(str(i)) if isinstance(decisions, dict) else None)
        answered = [a for a in out if isinstance(a, Answer)]
        if answered:
            total = _token_total(calls[before:] if isinstance(calls, list) else [])
            if total is not None:
                share = total // len(answered)
                for a in answered:
                    a.tokens = share
        return out

    def _map(self, qt: QuestionType, q: Question, d) -> "Answer | Unavailable":
        try:
            if d is None:
                return Unavailable("MissingAnswer")
            if d.source in _JEV_SOURCES:
                return Answer(q.qtype, q.subject, decider_module.question_key(qt, q), d.answer, d.confidence,
                              self.name, {str(k): v for k, v in (d.probabilities or {}).items()}, False)
            if d.source == "owner":
                return UNAVAILABLE  # owner facts enter only through record_owner (sync_confirmed)
            return Unavailable(d.error or d.source)  # "none" / "error" / anything unknown
        except Exception as exc:  # noqa: BLE001 -- a malformed decision
            return Unavailable(type(exc).__name__)


class SyncCount(int):
    """What `sync_confirmed` returns: the number of owner answers recorded (an int), with `.skipped` = the
    answers that were not an option (or a bad entry) and `.skipped_files` = files that could not be used."""

    skipped: int
    skipped_files: int


def sync_confirmed(decider: Decider, confirmed_dir: Path, qtypes: list[str] | None = None) -> int:
    """Record the owner-confirmed answers in `confirmed_dir` as owner answers. Only a new or changed answer is
    recorded, so a second sync records nothing. A missing folder or file is not an error."""
    folder = Path(confirmed_dir)
    if qtypes is None:
        paths = sorted(folder.glob("*.json")) if folder.is_dir() else []
    else:
        paths = [folder / f"{qtype}.json" for qtype in qtypes]
    recorded = skipped = skipped_files = 0
    for path in paths:
        qtype = path.stem
        if not path.is_file():
            continue
        try:
            qt = decider._type(qtype)
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a mapping")
        except (KeyError, ValueError, OSError) as exc:
            skipped_files += 1
            log.warning("sync_confirmed: %s skipped (%s)", path.name, type(exc).__name__)
            continue
        for subject, answer in data.items():
            try:
                value = _normalise(qt, answer)
            except ValueError:
                skipped += 1
                log.warning("sync_confirmed: %s: an answer for %r is not an option, skipped", qtype, str(subject)[:60])
                continue
            current = decider.owner_answer(qtype, subject)
            if current is not None and current == value and type(current) is type(value):
                continue
            decider.record_owner(qtype, subject, value)
            recorded += 1
    result = SyncCount(recorded)
    result.skipped, result.skipped_files = skipped, skipped_files
    return result
