# Task D1 brief: the Decider, rules only

**Plan** (docs/superpowers/plans/2026-10-03-repair-engine-p1-p2.md, Task D1), spec §9:
- question types with typed schemas and state builders;
- the providers chain;
- `data/decide/log.jsonl`;
- a cache by state hash;
- modes, and promotion statistics per question type (agreement with the owner's later decisions).

**Plan exit:**
- with only the rule provider, every question gets a rule answer or goes to the owner queue;
- the log and the cache round-trip;
- promotion stays off below 50 decisions or below 95 %;
- demotion happens below 90 % over the last 30.

**Spec §9:**
- The rules decide whatever they can. Jev (a later provider, P1-D2, owned by the Jev session) only suggests.
- The owner confirms.
- Nothing here ever deletes geometry, sets a tolerance or gives a Validator verdict.
- No key and no network means rules plus the owner queue; the pipeline never waits.

## Binding conventions (agreed with the Jev session; see D1-alignment-with-jev-vps.md in this folder)

- **qtype:** a lowercase dotted string `<area>.<question>`.
  - Known now: `inv.building`, `inv.type`, `inv.floor`, `inv.duplicate`, `mat.category`, `mat.trim`.
  - Reserved: `repair.next_step`, `review.priority`, `e5.winner`, `e4.same_look`, `e8.opening_kind`.
- **subject:** a plain string (group name, material name, unit id, or `<unit>:<site-id>`).
- **kind:** `noul` (true or false), `choice` (one of an ordered option list) or `score` (an ordered list of at
  most 10 levels). A choice has at most 255 options.
- **Question key:** the sha256 hex of `json.dumps(obj, sort_keys=True, separators=(",", ":"))`, where obj is
  `{"state": <dict>, "kind": <str>, "instructions": <str>, "criteria": ...}`.
  - criteria for a choice is a list of `[label, description]` pairs in the question's ORDER;
  - for a score, the list of level texts in order;
  - for a noul, null.
  - qtype and subject are NOT in the key.
- **Owner answers** are looked up by (qtype, subject). The owner's latest confirmed answer for that pair beats
  every provider.
- **Answers** are stored in raw option form (the label, or "5" for a floor). Probabilities are JSON objects with
  string keys.
- **Do not edit `engine/decide/jev.py`, and do not import anything that exists only on `feat/jev-vps`.**

## Files and interface (the controller's design)

Create `engine/decide/decider.py` and `engine/tests/test_decider.py`.

```python
Kind = Literal["noul", "choice", "score"]
Mode = Literal["off", "suggest", "auto"]

@dataclass(frozen=True)
class QuestionType:
    qtype: str; kind: Kind; instructions: str
    criteria: tuple            # choice: ((label, description), ...); score: (level, ...); noul: ()
    mode: Mode = "suggest"

@dataclass(frozen=True)
class Question:  qtype: str; subject: str; state: dict

@dataclass
class Answer:
    qtype: str; subject: str; key: str
    answer: str | bool | None  # raw option form
    confidence: float          # 1.0 for rules and owner
    provider: str              # "owner" | "rules" | "<provider name>" | "queue"
    probabilities: dict        # string keys
    accepted: bool             # usable by the engine without the owner
    suggestion: dict | None    # the best non-accepted provider answer, shown to the owner

class Provider(Protocol):
    name: str
    def answer(self, qt: QuestionType, questions: list[Question]) -> list["Answer | None"]: ...

class RuleProvider:            # name "rules"; rules: dict[qtype, Callable[[Question], answer-or-None]]

class Decider:
    def __init__(self, types: list[QuestionType], providers: list[Provider], log_path, cache_path): ...
    def ask(self, questions: list[Question]) -> list[Answer]
    def record_owner(self, qtype: str, subject: str, answer) -> None
    def owner_queue(self) -> list[Answer]      # questions waiting for the owner, with their suggestion
    def stats(self, qtype: str) -> dict        # decisions, agreement overall and by confidence, last-30 agreement
    def mode_of(self, qtype: str) -> Mode
def question_key(qt: QuestionType, q: Question) -> str
```

**The rules for `ask`, in order, per question:**
1. An owner answer for (qtype, subject) exists: return it (provider "owner", accepted).
2. The mode is off: queue it for the owner, with no suggestion.
3. Rule provider answers first. A non-None answer is returned (provider "rules", accepted).
4. Other providers, in order:
   - **SUGGEST mode:** their answer is never accepted. The question goes to the owner queue with that answer as
     the `suggestion`.
   - **AUTO mode:** a provider answer is accepted only at a confidence where promotion measured ≥ 98 %
     agreement. Otherwise it is a suggestion.
5. Nothing answered: queue it for the owner (provider "queue", not accepted).

**Promotion** (per qtype, from the joined log):
- SUGGEST becomes eligible for AUTO only when a provider agreed with the owner on ≥ 95 % of ≥ 50 decisions, and
  only for the confidences where agreement was ≥ 98 %.
- AUTO falls back to SUGGEST when agreement over the last 30 decisions is < 90 %.
- Promotion is computed and reported by `stats`. **It is applied only by an explicit call**
  (`Decider.promote(qtype)` / `demote`) that writes the new mode to the log. Nothing promotes itself silently.

**Cache, log and queue:**
- **Cache:** by question key and provider; a JSON lines file. The same key never calls a provider twice.
- **Log:** every answer and every owner decision, one JSON line each: qtype, subject, key, provider, answer,
  confidence, accepted, mode, latency_s, tokens (null for rules). No secrets and no paths.
- **Defaults:** `data/decide/log.jsonl` and `data/decide/cache.jsonl` (cwd-relative). Tests use tmp_path.

## Exit (real output for each)

- Plan exit items 1-4 as tests, plus:
  - question_key matches the convention, with an order-sensitive choice;
  - owner beats every provider;
  - SUGGEST never accepts a provider answer;
  - AUTO accepts only in the measured band;
  - mode OFF goes straight to the owner queue;
  - the cache prevents a second provider call;
  - the log round-trips;
  - a provider that raises is logged and the question falls through, so the pipeline never fails because of a
    provider.
- The whole engine suite passes.

## Rules

AGENTS.md §3-§7. Test first; commit after each item; stage files by name. No network in any test. Nothing in
`engine/guard/**`. No existing test edited.
