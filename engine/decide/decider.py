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
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

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


UNAVAILABLE_REASON_MAX = 200


@dataclass(frozen=True)
class Unavailable:
    """A provider's per-question "I could not answer now" (jev off, unreachable, daily cap). Unlike `None`, which
    is a real and cacheable "no answer", it is never cached, so the question is asked again on the next `ask`.
    `reason` is stored as given, cut to 200 characters: a provider passes only class names, `HTTP <status>`,
    "jev off" or "daily cap", never a URL, a password or a message."""

    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", str(self.reason or "")[:UNAVAILABLE_REASON_MAX])


UNAVAILABLE = Unavailable()  # the marker with no reason


# Promotion and demotion (spec section 9). Nothing here applies a mode: `stats` only reports, and only an
# explicit Decider.promote / Decider.demote call writes the new mode to the log.
PROMOTE_MIN_DECISIONS = 50  # a provider must have been checked against the owner this often ...
PROMOTE_MIN_AGREEMENT = 0.95  # ... and agreed on at least this share to become eligible for AUTO
BAND_MIN_AGREEMENT = 0.98  # AUTO accepts an answer only in a confidence band that measured this much
BAND_MIN_DECISIONS = 10  # a band needs this many owner decisions before its agreement counts as measured
DEMOTE_WINDOW = 30  # AUTO falls back to SUGGEST when the last 30 decisions ...
DEMOTE_BELOW = 0.90  # ... agree on less than this

DEFAULT_LOG_PATH = Path("data/decide/log.jsonl")  # cwd-relative
DEFAULT_CACHE_PATH = Path("data/decide/cache.jsonl")


class Provider(Protocol):
    name: str

    def answer(self, qt: QuestionType, questions: list[Question]) -> "list[Answer | None | Unavailable]": ...


def _pkey(value: Any) -> str:
    """The string key a raw answer takes in a probabilities object."""
    return ("true" if value else "false") if isinstance(value, bool) else str(value)


def _band(confidence: float) -> str:
    """The 0.1-wide confidence band an answer falls in: '0.9-1.0' for 0.9 up to and including 1.0."""
    lo = min(math.floor(confidence * 10 + 1e-9), 9)
    return f"{lo / 10:.1f}-{(lo + 1) / 10:.1f}"


def _share(agreed: int, decisions: int) -> float | None:
    return agreed / decisions if decisions else None


def _normalise(qt: QuestionType, value: Any) -> Any:
    """Raw option form: a choice answer is its label as a string ("5" for a floor), a noul is a bool."""
    if qt.kind == "choice":
        if isinstance(value, bool) or value is None:
            raise ValueError(f"{qt.qtype}: {value!r} is not an option")
        label = str(value)
        if label not in {c[0] for c in qt.criteria}:
            raise ValueError(f"{qt.qtype}: {label!r} is not one of the options")
        return label
    if qt.kind == "noul":
        if not isinstance(value, bool):
            raise ValueError(f"{qt.qtype}: a noul answer is true or false, not {value!r}")
        return value
    if value is None:
        raise ValueError(f"{qt.qtype}: a score answer is not None")
    return value


class RuleProvider:
    """The deterministic provider. `rules` maps a qtype to a function Question -> answer, or None for "the
    rules cannot say" (False is an answer). Always confidence 1.0."""

    name = "rules"

    def __init__(self, rules: dict[str, Callable[[Question], Any]]):
        self.rules = dict(rules)

    def answer(self, qt: QuestionType, questions: list[Question]) -> "list[Answer | None]":
        rule = self.rules.get(qt.qtype)
        out: list[Answer | None] = []
        for q in questions:
            value = None if rule is None else rule(q)
            if value is None:
                out.append(None)
                continue
            out.append(Answer(q.qtype, q.subject, question_key(qt, q), value, 1.0, self.name,
                              {_pkey(value): 1.0}, True))
        return out


class Decider:
    """Owner answer, then rules, then other providers, otherwise the owner queue. State lives in two JSON
    lines files (the log and the cache) and is replayed from them on construction. The rule provider is
    asked one question at a time (a failing rule never costs the others); other providers get a batch per
    question type."""

    def __init__(self, types: list[QuestionType], providers: list[Provider],
                 log_path: Any = DEFAULT_LOG_PATH, cache_path: Any = DEFAULT_CACHE_PATH):
        self._types: dict[str, QuestionType] = {}
        for t in types:
            if t.qtype in self._types:
                raise ValueError(f"duplicate question type {t.qtype}")
            self._types[t.qtype] = t
        # the rule provider is always asked first, the others keep their order
        self._providers = [p for p in providers if p.name == "rules"] + [
            p for p in providers if p.name != "rules"]
        self._log_path = Path(log_path)
        self._cache_path = Path(cache_path)
        self._modes: dict[str, str] = {t.qtype: t.mode for t in types}
        self._owner: dict[tuple[str, str], Any] = {}
        self._pending: dict[tuple[str, str], Answer] = {}
        self._records: list[dict] = []
        self._cache: dict[tuple[str, str], dict] = {}
        self._bands: dict[str, set[str]] = {}  # per ask() call: qtype -> bands AUTO may accept
        self._replay()
        self._load_cache()

    # ------------------------------------------------------------------ files

    def _replay(self) -> None:
        if not self._log_path.exists():
            return
        for line in self._log_path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue  # a truncated last line
            if isinstance(rec, dict):
                self._records.append(rec)
                self._apply(rec)

    def _load_cache(self) -> None:
        if not self._cache_path.exists():
            return
        for line in self._cache_path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                self._cache[(rec["key"], rec["provider"])] = rec
            except (ValueError, KeyError, TypeError):
                continue  # a truncated or foreign line

    def _apply(self, rec: dict) -> None:
        ev = rec.get("event")
        pair = (rec.get("qtype"), rec.get("subject"))
        if ev == "owner":
            self._owner[pair] = rec["answer"]
            self._pending.pop(pair, None)
        elif ev == "answer":
            if rec.get("accepted"):
                self._pending.pop(pair, None)
            elif rec.get("provider") == "queue":
                self._pending[pair] = Answer(
                    rec["qtype"], rec["subject"], rec.get("key"), None, 0.0, "queue",
                    rec.get("probabilities") or {}, False, rec.get("suggestion"))
        elif ev == "mode":
            self._modes[rec["qtype"]] = rec["to"]

    def _write(self, rec: dict) -> None:
        rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **rec}
        self._records.append(rec)
        self._apply(rec)
        _append_line(self._log_path, rec)

    # ------------------------------------------------------------------ public

    def mode_of(self, qtype: str) -> Mode:
        self._type(qtype)
        return self._modes[qtype]  # type: ignore[return-value]

    def owner_queue(self) -> list[Answer]:
        return list(self._pending.values())

    def record_owner(self, qtype: str, subject: str, answer: Any) -> None:
        qt = self._type(qtype)
        value = _normalise(qt, answer)
        pending = self._pending.get((qtype, subject))
        self._write({"event": "owner", "qtype": qtype, "subject": subject,
                     "key": pending.key if pending else None, "provider": "owner", "answer": value,
                     "confidence": 1.0, "accepted": True, "mode": self._modes[qtype],
                     "latency_s": 0.0, "tokens": None})

    def owner_answer(self, qtype: str, subject: str) -> Any:
        """The owner's current answer (raw option form) for this question, or None when there is none."""
        return self._owner.get((qtype, subject))

    def stats(self, qtype: str) -> dict:
        """Provider answers joined with the owner's later decisions, from the log. Decisions are the owner
        decisions that had a non-rule provider answer waiting (the best one, by confidence). Reports whether
        SUGGEST is eligible for AUTO and whether AUTO should fall back; changes nothing."""
        self._type(qtype)
        latest: dict[str, dict[str, dict]] = {}  # subject -> provider -> its latest unjudged answer
        joined: list[tuple[float, bool]] = []  # (confidence, agreed), in log order
        for rec in self._records:
            if rec.get("qtype") != qtype:
                continue
            subject = rec.get("subject")
            if rec["event"] == "provider":
                latest.setdefault(subject, {})[rec["provider"]] = rec
            elif rec["event"] == "owner":
                waiting = latest.pop(subject, None)
                if waiting:
                    best = max(waiting.values(), key=lambda r: r["confidence"])
                    joined.append((best["confidence"], best["answer"] == rec["answer"]))
        by_band: dict[str, list[int]] = {}
        for conf, agreed in joined:
            row = by_band.setdefault(_band(conf), [0, 0])
            row[0] += 1
            row[1] += agreed
        decisions, agreed = len(joined), sum(a for _, a in joined)
        recent = joined[-DEMOTE_WINDOW:]
        recent_agreed = sum(a for _, a in recent)
        mode = self._modes[qtype]
        agreement = _share(agreed, decisions)
        last30 = _share(recent_agreed, len(recent))
        return {
            "qtype": qtype, "mode": mode,
            "decisions": decisions, "agreed": agreed, "agreement": agreement,
            "by_confidence": {
                b: {"decisions": n, "agreed": k, "agreement": k / n} for b, (n, k) in sorted(by_band.items())},
            "last30_decisions": len(recent), "last30_agreement": last30,
            "eligible_for_auto": (mode == "suggest" and decisions >= PROMOTE_MIN_DECISIONS
                                  and agreement >= PROMOTE_MIN_AGREEMENT),
            "auto_bands": [b for b, (n, k) in sorted(by_band.items())
                           if n >= BAND_MIN_DECISIONS and k / n >= BAND_MIN_AGREEMENT],
            "should_demote": (mode == "auto" and len(recent) >= DEMOTE_WINDOW and last30 < DEMOTE_BELOW),
        }

    def promote(self, qtype: str) -> Mode:
        """SUGGEST -> AUTO, only when `stats` says eligible. The one place a mode is raised; it is logged."""
        st = self.stats(qtype)
        if st["mode"] != "suggest":
            raise ValueError(f"{qtype} is in mode {st['mode']!r}; only a suggest type can be promoted")
        if not st["eligible_for_auto"]:
            raise ValueError(
                f"{qtype} is not eligible: needs >= {PROMOTE_MIN_DECISIONS} decisions at >= "
                f"{PROMOTE_MIN_AGREEMENT:.0%} agreement, has {st['decisions']} at {st['agreement']}")
        return self._set_mode(qtype, "auto", "promote", st)

    def demote(self, qtype: str) -> Mode:
        """AUTO -> SUGGEST on an explicit call (the owner's, or the controller's when `should_demote`)."""
        st = self.stats(qtype)
        if st["mode"] != "auto":
            raise ValueError(f"{qtype} is in mode {st['mode']!r}; only an auto type can be demoted")
        return self._set_mode(qtype, "suggest", "demote", st)

    def _set_mode(self, qtype: str, to: str, action: str, st: dict) -> Mode:
        self._write({"event": "mode", "qtype": qtype, "action": action, "from": st["mode"], "to": to,
                     "decisions": st["decisions"], "agreement": st["agreement"],
                     "last30_agreement": st["last30_agreement"]})
        return self._modes[qtype]  # type: ignore[return-value]

    def ask(self, questions: list[Question]) -> list[Answer]:
        self._bands = {}
        results: list[Answer | None] = [None] * len(questions)
        types = [self._type(q.qtype) for q in questions]
        keys = [question_key(t, q) for t, q in zip(types, questions)]
        todo: list[int] = []
        for i, (q, key) in enumerate(zip(questions, keys)):
            pair = (q.qtype, q.subject)
            if pair in self._owner:
                results[i] = Answer(q.qtype, q.subject, key, self._owner[pair], 1.0, "owner",
                                    {_pkey(self._owner[pair]): 1.0}, True)
            elif self._modes[q.qtype] == "off":
                results[i] = self._queued(q, key, None)
            else:
                todo.append(i)
        rules = [p for p in self._providers if p.name == "rules"]
        for i in list(todo):
            for provider in rules:
                ans = self._call_rule(provider, types[i], questions[i])
                if ans is not None:
                    results[i] = ans
                    todo.remove(i)
                    break
        candidates: dict[int, list[Answer]] = {i: [] for i in todo}
        for provider in (p for p in self._providers if p.name != "rules"):
            for qtype in dict.fromkeys(questions[i].qtype for i in todo):
                idxs = [i for i in todo if questions[i].qtype == qtype]
                for i, ans in self._provider_answers(provider, self._types[qtype], idxs, questions, keys):
                    candidates[i].append(ans)
        for i in todo:
            results[i] = self._decide(questions[i], keys[i], candidates[i])
        for ans in results:
            assert ans is not None
            self._log_answer(ans)
        return results  # type: ignore[return-value]

    # ------------------------------------------------------------------ internals

    def _type(self, qtype: str) -> QuestionType:
        try:
            return self._types[qtype]
        except KeyError:
            raise KeyError(f"unknown question type {qtype!r}") from None

    @staticmethod
    def _queued(q: Question, key: str, suggestion: dict | None) -> Answer:
        return Answer(q.qtype, q.subject, key, None, 0.0, "queue", {}, False, suggestion)

    def _call_rule(self, provider: Provider, qt: QuestionType, q: Question) -> Answer | None:
        t0 = time.perf_counter()
        try:
            (ans,) = provider.answer(qt, [q])
            if ans is not None:
                ans.answer = _normalise(qt, ans.answer)
                ans.subject, ans.qtype, ans.key = q.subject, q.qtype, question_key(qt, q)
        except Exception as exc:  # a rule that fails never fails the pipeline
            self._write({"event": "error", "qtype": q.qtype, "subject": q.subject, "provider": provider.name,
                         "error": f"{type(exc).__name__}: {exc}"[:300],
                         "latency_s": round(time.perf_counter() - t0, 6)})
            return None
        return ans

    def _decide(self, q: Question, key: str, candidates: list[Answer]) -> Answer:
        """SUGGEST: the best provider answer rides on the queued answer, never accepted. AUTO: it is accepted
        only in a confidence band where promotion measured >= 98 % agreement; otherwise it is a suggestion."""
        suggestion = None
        if candidates:
            best = max(candidates, key=lambda a: a.confidence)
            if self._modes[q.qtype] == "auto":
                if q.qtype not in self._bands:
                    self._bands[q.qtype] = set(self.stats(q.qtype)["auto_bands"])
                if _band(best.confidence) in self._bands[q.qtype]:
                    return Answer(q.qtype, q.subject, key, best.answer, best.confidence, best.provider,
                                  best.probabilities, True, None, best.tokens)
            suggestion = {"provider": best.provider, "answer": best.answer,
                          "confidence": best.confidence, "probabilities": best.probabilities}
        return self._queued(q, key, suggestion)

    def _error(self, provider: str, qtype: str, subject: str | None, exc: Exception, t0: float) -> None:
        self._write({"event": "error", "qtype": qtype, "subject": subject, "provider": provider,
                     "error": f"{type(exc).__name__}: {exc}"[:300],
                     "latency_s": round(time.perf_counter() - t0, 6)})

    def _provider_answers(self, provider: Provider, qt: QuestionType, idxs: list[int],
                          questions: list[Question], keys: list[str]) -> list[tuple[int, Answer]]:
        """One provider, one question type: ask it only for keys it has not answered before, remember its
        answers (and its misses) in the cache, and return what it knows for each question."""
        name = provider.name
        missing: dict[str, int] = {}
        for i in idxs:
            if (keys[i], name) not in self._cache:
                missing.setdefault(keys[i], i)
        fresh: dict[str, float] = {}  # key -> latency of the call that just answered it
        if missing:
            order = list(missing.values())
            t0 = time.perf_counter()
            try:
                got = provider.answer(qt, [questions[i] for i in order])
                if len(got) != len(order):
                    raise ValueError(f"{name} returned {len(got)} answers for {len(order)} questions")
            except Exception as exc:  # a provider never fails the pipeline
                self._error(name, qt.qtype, None, exc, t0)
                got = []
            latency = round((time.perf_counter() - t0) / max(len(order), 1), 6)
            for i, ans in zip(order, got):
                if isinstance(ans, Unavailable):  # a temporary failure: logged, never cached, asked again later
                    self._write({"event": "error", "qtype": questions[i].qtype, "subject": questions[i].subject,
                                 "key": keys[i], "provider": name, "error": "Unavailable",
                                 "reason": ans.reason, "latency_s": latency})
                    continue
                rec: dict = {"key": keys[i], "provider": name, "hit": False, "answer": None,
                             "confidence": 0.0, "probabilities": {}, "tokens": None}
                if ans is not None:
                    try:
                        conf = float(ans.confidence)
                        if not 0.0 <= conf <= 1.0:
                            raise ValueError(f"confidence {conf} outside 0..1")
                        rec.update(hit=True, answer=_normalise(qt, ans.answer), confidence=conf,
                                   probabilities=dict(ans.probabilities or {}), tokens=ans.tokens)
                    except Exception as exc:
                        self._error(name, qt.qtype, questions[i].subject, exc, t0)
                        continue  # not cached: a bad answer may be better next time
                self._cache[(keys[i], name)] = rec
                _append_line(self._cache_path, rec)
                fresh[keys[i]] = latency
        out: list[tuple[int, Answer]] = []
        for i in idxs:
            rec = self._cache.get((keys[i], name))
            if rec is None or not rec["hit"]:
                continue
            q = questions[i]
            ans = Answer(q.qtype, q.subject, keys[i], rec["answer"], rec["confidence"], name,
                         rec["probabilities"], False, None, rec["tokens"])
            self._write({"event": "provider", "qtype": q.qtype, "subject": q.subject, "key": keys[i],
                         "provider": name, "answer": ans.answer, "confidence": ans.confidence,
                         "accepted": False, "mode": self._modes[q.qtype],
                         "latency_s": fresh.get(keys[i], 0.0),
                         "tokens": rec["tokens"] if keys[i] in fresh else 0,
                         "probabilities": ans.probabilities})
            out.append((i, ans))
        return out

    def _log_answer(self, ans: Answer) -> None:
        self._write({"event": "answer", "qtype": ans.qtype, "subject": ans.subject, "key": ans.key,
                     "provider": ans.provider, "answer": ans.answer, "confidence": ans.confidence,
                     "accepted": ans.accepted, "mode": self._modes[ans.qtype], "latency_s": 0.0,
                     "tokens": ans.tokens, "probabilities": ans.probabilities,
                     "suggestion": ans.suggestion})


def _append_line(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = ""
    if path.exists() and path.stat().st_size:
        with open(path, "rb") as f:
            f.seek(-1, 2)
            if f.read(1) != b"\n":  # a truncated last line must not swallow the next record
                prefix = "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(prefix + json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
