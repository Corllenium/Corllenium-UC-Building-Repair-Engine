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
import re
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
_TRANSPORT_ERROR = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*|HTTP \d{3})$")  # a class name or "HTTP <status>"


def _transport_failure(decisions, ids: list[str]) -> str | None:
    """The tripping reason when EVERY decision of a state group is a "none"/"error" whose error is an exception
    class name or `HTTP <status>`: the service was not reached or answered with a failure. "jev off", "daily
    cap" and a "none" with no error are fast service answers (other groups may still hold stored hits): None."""
    if not isinstance(decisions, dict) or not ids:
        return None
    reason = None
    for qid in ids:
        d = decisions.get(qid)
        error = getattr(d, "error", "") or ""
        if getattr(d, "source", None) not in ("none", "error") or not _TRANSPORT_ERROR.match(error):
            return None
        reason = reason or error
    return reason


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
    """A Decider provider backed by a Jev decider (`JevDecider` or `RemoteDecider`).

    The pipeline never waits on the VPS: a circuit breaker lives on the instance. When a state group comes back
    as a transport failure (`decider.ask` raised, or every decision is a "none"/"error" whose error is an
    exception class name or `HTTP <status>`), `.down` is set to that reason; the remaining groups of the call and
    every later `answer()` on this instance return `Unavailable(.down)` at once, with no request. The caller
    makes a fresh provider per pipeline run. "jev off", "daily cap" and a "none" without an error do not trip it.

    Tokens: the sum of `input_tokens + output_tokens` of the `decider.calls` entries added during one `answer()`
    call is split over that call's answers by integer division; the remainder is dropped."""

    def __init__(self, name: str, decider):
        self.name = name
        self.decider = decider
        self.down: str | None = None  # the tripping reason once the breaker has tripped

    def answer(self, qt: QuestionType, questions: list[Question]) -> "list[Answer | None | Unavailable]":
        groups: dict[str, list[int]] = {}
        for i, q in enumerate(questions):
            groups.setdefault(_state_key(q.state), []).append(i)
        calls = getattr(self.decider, "calls", None)
        before = len(calls) if isinstance(calls, list) else 0
        out: "list[Answer | Unavailable | None]" = [None] * len(questions)
        for idxs in groups.values():
            if self.down is not None:
                for i in idxs:
                    out[i] = Unavailable(self.down)
                continue
            asked = {str(i): _jev_question(qt, questions[i]) for i in idxs}
            try:
                decisions = self.decider.ask(questions[idxs[0]].state, asked)
            except Exception as exc:  # noqa: BLE001 -- it should not raise; never keep the message
                self.down = type(exc).__name__
                for i in idxs:
                    out[i] = Unavailable(self.down)
                continue
            self.down = _transport_failure(decisions, list(asked))
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


def _strict_score(qt: QuestionType, answer):
    """A score answer is an int (or a whole float, stored as int) in range(len(criteria)); never a bool."""
    if isinstance(answer, bool) or not isinstance(answer, (int, float)):
        raise ValueError(f"{qt.qtype}: a score answer is a level number")
    if isinstance(answer, float):
        if not answer.is_integer():
            raise ValueError(f"{qt.qtype}: a score answer is a whole level number")
        answer = int(answer)
    if not 0 <= answer < len(qt.criteria):
        raise ValueError(f"{qt.qtype}: level {answer} is out of range")
    return answer


class SyncCount(int):
    """What `sync_confirmed` returns: the number of owner answers recorded (an int), with `.skipped` = the
    answers that were not an option (or a bad entry) and `.skipped_files` = files that could not be used."""

    skipped: int
    skipped_files: int


def sync_confirmed(decider: Decider, confirmed_dir: Path, qtypes: list[str] | None = None) -> SyncCount:
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
            decider.mode_of(qtype)  # public: raises KeyError for an unknown qtype
            qt = decider._type(qtype)  # the Decider has no public QuestionType lookup
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a mapping")
        except (KeyError, ValueError, OSError) as exc:
            skipped_files += 1
            log.warning("sync_confirmed: %s skipped (%s)", path.name, type(exc).__name__)
            continue
        for subject, answer in data.items():
            try:
                value = _strict_score(qt, answer) if qt.kind == "score" else _normalise(qt, answer)
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
