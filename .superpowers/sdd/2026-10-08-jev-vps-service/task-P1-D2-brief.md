# P1-D2: Jev as a provider behind the Decider

**Queue job:** P1-D2 (claude). **Branch:** `claude/P1-D2` in `.claude/worktrees/P1-D2`, from `feat/repair-p1p2`
at e55c768. **Spec:** `docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md` §9, and
`docs/superpowers/specs/2026-10-08-jev-vps-service-design.md` §2 and §6.
**Owner of D1 (`engine/decide/decider.py`):** the repair-engine session. It agreed to the decider.py change in Part 1
and reviews it before merge.

**Do not touch:** `engine/repair/kernel.py`, `engine/validate/**` (P1-K3 is paused), `engine/guard/**`, FixProfile,
or any existing test except the ones Part 1 names. Leave every other D1 behaviour and test unchanged.

## Part 1: the `Unavailable` marker in `engine/decide/decider.py` (owner-approved, exact)

1. Export a small marker class `Unavailable` with an optional `reason: str`. The reason is cut to 200 characters.
   It must hold no secrets, URLs or passwords: providers pass only class names, `HTTP <status>`, "jev off" or
   "daily cap". Also export a module instance `UNAVAILABLE = Unavailable()` for the case with no reason.
   A provider returns it per question, in place of an Answer or None.
2. In `_provider_answers`, a question whose result is an `Unavailable`:
   - logs an `error` event with provider, qtype, subject, key and reason;
   - is NOT written to the cache;
   - returns nothing for that question, so it falls through to the owner queue as today.

   `None` keeps its meaning: a real, cacheable "no answer".
3. Unavailable results never count in stats or agreement. A batch that is entirely Unavailable writes nothing to
   the cache.
4. Tests, in a new test file or appended to the D1 test file; existing tests unchanged:
   - an Unavailable result is asked again on the next `ask()`, so the provider is called twice;
   - a `None` is not asked again (called once);
   - an Unavailable mixed with real answers in one batch keeps the real ones cached;
   - the log has the `error` event, and the reason leaks nothing. Test with a provider that tries a reason
     containing a URL, and assert the logged text is cut to 200 characters and contains only what was given. The
     provider side never passes sensitive text; the Decider just stores what it gets, capped.

## Part 2: `engine/decide/providers.py` (new)

**`AskProvider(name: str, decider)`.** `decider` is any object with `.ask(state, questions) -> {qid: Decision}` and a
`.calls` list: `JevDecider` (local) or `RemoteDecider` (the VPS service). It implements the D1 `Provider` protocol:
`name` and `answer(qt: QuestionType, questions: list[Question]) -> list[Answer | None | Unavailable]`, one entry per
question in order.
- **Build the jev question per Question from the QuestionType:**
  - noul → `NoulQ(qt.instructions, qtype=qt.qtype, subject=q.subject)`;
  - choice → `ChoiceQ(qt.instructions, {label: desc for label, desc in qt.criteria}, qtype=…, subject=…)`, with the
    order preserved;
  - score → `ScoreQ(qt.instructions, list(qt.criteria), …)`.
- **Group by state:** one `decider.ask(state, {...})` call per distinct `q.state` (canonical JSON as the grouping
  key). The qids are the indexes as strings.
- **Map each returned `Decision`:**
  - source `"jev"` or `"pilot-import"` → `Answer(qtype, subject, key=decider_module.question_key(qt, q), answer=<raw>,
    confidence=d.confidence, provider=self.name, probabilities={str(k): v ...}, accepted=False, tokens=<see below>)`.
    The raw form is the choice label (str), the noul bool, or the score value;
  - source `"owner"` → `UNAVAILABLE`. Owner facts enter only through `record_owner`, via `sync_confirmed`, so they
    never sit in the provider cache;
  - source `"none"` or `"error"` → `Unavailable(reason=d.error or d.source)`. `d.error` holds only class names,
    `HTTP <status>`, "jev off" or "daily cap"; cap it at 200 characters anyway;
  - an exception from `decider.ask` (it should not raise, but if it does) → every question in that state group
    becomes `Unavailable(reason=type(exc).__name__)`. Never the message.
- **Tokens:** sum `input_tokens + output_tokens` over the `decider.calls` entries added during this `answer()` call
  (treat None as 0). Spread the sum evenly, as an int, over that call's jev or pilot-import answers. A call with no
  token data gives `tokens=None`.
- **`AskProvider` never returns `None`.** Jev always answers or is unavailable; a cacheable miss would wrongly
  freeze a question.

**`sync_confirmed(decider: Decider, confirmed_dir: Path, qtypes: list[str] | None = None) -> int`.**
- It reads `<confirmed_dir>/<qtype>.json` (`{subject: answer}`, written by `engine.cli decide-pull`) for each qtype,
  or for every `*.json` in the folder when qtypes is None.
- For each entry whose answer differs from the Decider's current owner answer for that (qtype, subject), or is
  missing there, it calls `decider.record_owner(qtype, subject, answer)`. Read the Decider's owner state through its
  existing attributes or methods (look at `record_owner` and `_apply`). If there is no read method, add a small
  public `owner_answer(qtype, subject)` to decider.py; that is the only other decider.py addition allowed, so
  mention it in the report.
- It returns the number recorded. A missing file or folder → 0, with no error.
- Values are raw option form already ("5" for a floor, a label, a bool). Pass them through `_normalise` with the
  qtype's QuestionType when the Decider knows the type; skip and count an answer that is not an option (log it).

## Tests (`engine/tests/test_decide_providers.py`), with a fake decider object (no network)

1. **The mapping per kind:** noul, choice (with order) and score; the probabilities' keys become str; accepted is
   always False; provider is the name.
2. **Grouping:** questions with two distinct states give two `ask` calls; the results come back in the input order.
3. **Sources:** owner → UNAVAILABLE, none/error → Unavailable with the reason, and an exception → Unavailable with
   the class name.
4. **The Decider end to end in SUGGEST mode:** a jev answer becomes the `suggestion` on the queued Answer, never
   `accepted`.
5. **Jev off:** the fake returns none with "jev off". The Decider asks again on the next `ask()` (the fake is called
   twice), and nothing is in the cache for those keys.
6. **The cross-module key:** `decider.question_key(qt, q) == wire.question_key(q.state, <the jev question built by
   AskProvider>)` for a choice, a score and a noul, including non-ASCII text.
7. **`sync_confirmed`:**
   - pulled answers become Decider owner answers (`ask()` returns provider "owner", accepted True);
   - a second sync records nothing new;
   - an answer that is not an option is skipped and counted;
   - a missing folder gives 0.
8. **With the real `RemoteDecider`** against a local `http.server` fake of `/api/decide/ask` (reuse the
   test_decide_remote.py pattern): answers map, and a 409, 5xx or timeout gives Unavailable, never None.

## Run

- `( cd "<wt>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_decide_providers.py <D1 test file(s)>
  engine/tests/test_decide_*.py -q -p no:cacheprovider )`
- Then the full engine and tools suites once:
  `( cd "<wt>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests tools/tests -q -p no:cacheprovider )`.
  Paste the tails.
