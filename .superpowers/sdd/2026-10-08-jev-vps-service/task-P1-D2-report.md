# P1-D2 report: Jev as a provider behind the Decider

Branch `claude/P1-D2` (worktree `.claude/worktrees/P1-D2`), base e55c768. Status: DONE_WITH_CONCERNS (concerns at the end).

Commits (reviewed separately):
- **Part 1** `16b41f6`: `Unavailable` marker in `engine/decide/decider.py` (+ `engine/tests/test_decider_unavailable.py`).
- **Part 2** `1c2e4d5`: `engine/decide/providers.py` (`AskProvider`, `sync_confirmed`), `Decider.owner_answer`, `engine/tests/test_decide_providers.py`.

Skill note: uc-repair-rules checklist applied. No blocked operation, guard, FixProfile, vertex, geometry or input data is
touched. Nothing under `engine/guard/**`, `engine/validate/**`, `engine/repair/kernel.py` changed; no existing test changed.

## Exactly what changed in `engine/decide/decider.py`

Part 1 (the owner-approved change):
1. New `@dataclass(frozen=True) class Unavailable` with `reason: str = ""`; `__post_init__` cuts the reason to 200
   characters (`UNAVAILABLE_REASON_MAX = 200`). New module instance `UNAVAILABLE = Unavailable()`.
2. `Provider.answer` return annotation widened to `list[Answer | None | Unavailable]` (annotation only).
3. In `_provider_answers`, inside the `for i, ans in zip(order, got)` loop, one new first branch: an `Unavailable`
   writes an `error` log event `{event: "error", qtype, subject, key, provider, error: "Unavailable", reason, latency_s}`
   and `continue`s. So it is not written to the cache, not returned, and the question falls through to the owner queue as
   today. `None` is untouched (cached miss). No `provider` event is written for it, so stats/agreement never see it, and an
   all-Unavailable batch never creates the cache file.

Part 2 (the one other addition the brief allowed): a read-only public
`Decider.owner_answer(qtype, subject) -> Any` returning `self._owner.get((qtype, subject))` (None when no owner answer).
There was no existing read method for owner state. Nothing else in decider.py changed.

## Part 1 tests (`engine/tests/test_decider_unavailable.py`, 6 tests)

RED (before the code), real output:
```
engine\tests\test_decider_unavailable.py:6: in <module>
    from engine.decide.decider import (
E   ImportError: cannot import name 'UNAVAILABLE' from 'engine.decide.decider' (...\P1-D2\engine\decide\decider.py)
ERROR engine/tests/test_decider_unavailable.py
1 error in 0.18s
```
GREEN: `engine/tests/test_decider_unavailable.py engine/tests/test_decider.py` -> `47 passed in 14.96s`
(6 new + the 41 existing D1 tests, unchanged). Then `engine/tests/test_decide*.py` -> `166 passed`.

Tests: reason capped at 200 and `UNAVAILABLE` has none; Unavailable asked again on the next `ask()` (provider called
twice, no cache file, question still in the owner queue); `None` asked once; Unavailable mixed with a real answer and a
`None` keeps those two cached and only the Unavailable is re-asked; the `error` event carries provider/qtype/subject/key
and a reason built from a URL-with-credentials plus 400 chars is stored exactly as the first 200 characters of what was
given, nothing added, and no `provider` event is written; an all-Unavailable batch writes no cache and `stats` stays at 0
decisions even after an owner answer.

## Part 2 tests (`engine/tests/test_decide_providers.py`, 26 tests)

RED (before the code):
```
E   ModuleNotFoundError: No module named 'engine.decide.providers'
ERROR engine/tests/test_decide_providers.py
1 error in 0.22s
```
GREEN: `engine/tests/test_decide_providers.py` -> `26 passed in 2.74s`; with the D1 tests and all `test_decide_*.py`
-> `186 passed in 27.41s`.

Covered (brief numbering): 1 mapping for choice (order preserved, label answer), noul (bool), score (str probability
keys), pilot-import source, accepted always False, provider = name; 2 grouping (distinct states -> separate `ask` calls,
canonical-JSON key so dict key order does not split a group, qids are the indexes, input order kept); 3 sources (owner ->
UNAVAILABLE, none/error -> `Unavailable(error or source)`, 500-char error capped at 200, exception -> class name only for
that state group while other groups still answer, missing qid -> Unavailable); tokens (sum of calls added during this
`answer()`, earlier calls not counted, None as 0, no token data -> None); 4 end to end SUGGEST (suggestion on the queued
Answer, never accepted, logged tokens 42, second ask served from cache); 5 jev off (asked twice, no cache file, two `error`
events with reason "jev off", answered and cached once jev is back); 6 cross-module key `decider.question_key == wire.question_key`
for choice, score and noul with non-ASCII text and state (also `Answer.key` equals the decider key); 7 `sync_confirmed`
(owner answers with provider "owner"/accepted True, second sync 0, a changed answer re-recorded, `qtypes` filter, non-option
skipped and counted with a log, unknown-type / non-mapping / invalid-JSON files skipped, missing folder 0,
`owner_answer`); 8 real `RemoteDecider` against a local `http.server` (answers map, one POST per state, 409/500/503 ->
`Unavailable("HTTP <status>")`, timeout -> `Unavailable("TimeoutError")`, no password -> `Unavailable("none")` and no request).
The autouse fixture points `jev.DEFAULT_ENV_FILE` at a non-existent file; no `.env` is read, no network beyond 127.0.0.1.

## Acceptance commands, real output

Area run: `pytest engine/tests/test_decide_providers.py engine/tests/test_decider.py engine/tests/test_decide_*.py -q -p no:cacheprovider`
```
186 passed in 27.41s
```
Full run: `pytest engine/tests tools/tests -q -p no:cacheprovider` (from the worktree, PYTHONPATH set):
```
........................................................................ [ 95%]
........................................................................ [ 99%]
....                                                                     [100%]
1587 passed, 1 xfailed in 571.02s (0:09:31)
```
(The 1 xfail is pre-existing, not mine.)

## Decisions and concerns, said plainly

- `sync_confirmed` returns a `SyncCount(int)` (a small int subclass carrying `.skipped` and `.skipped_files`) so it still
  satisfies `-> int` and "skip and count" is observable. If the reviewer prefers a plain int, it is a 6-line change; skips
  are also logged with `logging` (qtype and subject only, never the value).
- A file whose qtype the Decider does not know is skipped (counted in `.skipped_files`, logged), because `record_owner`
  would raise `KeyError`. `sync_confirmed` calls `decider._type()` (private, same package) to get the QuestionType.
- An answer equal to the current owner answer but of a different Python type (e.g. 3 vs 3.0 for a score) counts as changed
  and is recorded once; values from JSON files keep their type, so repeat syncs stay at 0.
- `AskProvider` with a `JevDecider` that has no key gives `Unavailable("none")` (the decision has no error text, so the
  reason falls back to the source), not the literal "jev off". The Decider treats both identically. A `ValueError` from
  `check_question_limits` (e.g. a score over 10 levels) is caught as an exception -> `Unavailable("ValueError")` on every ask
  and shows up in the log each time, by design of the brief.
- The Decider writes the `error` event once per asked key, not per subject: subjects sharing a key (identical state and
  type) share one asked question (existing D1 de-dup), so they share one error line.
- Line-ending warnings (LF -> CRLF) appear on commit; no content issue.
- Not done / not in scope: no wiring of `AskProvider` into the CLI or kernel; the `HANDOFF`, ledger and QUEUE records are
  not updated (the controller does that on review).

---

# Fix round 1 (commit `0ca6362`)

Review: Part 1 approved; Part 2 changes. Done test first in the same worktree and branch.

1. **Circuit breaker on `AskProvider`** (`engine/decide/providers.py`). `.down` is the tripping reason or None. It trips
   when `decider.ask` raises (reason = exception class name) or when EVERY decision of a state group is source
   none/error with an error matching an exception class name or `HTTP <status>` (reason = the first such error). Once
   tripped, the rest of that call's groups and every later `answer()` on the instance return `Unavailable(.down)` with no
   request. It does not trip on "jev off", "daily cap", a `none` with no error, or a group that mixes answers and
   errors. Red run before the code: 9 failed (`AttributeError: 'AskProvider' object has no attribute 'down'`, and
   `test_score_answers_are_checked_strictly`); I did not capture a separate timing-only red for the hung-socket test, its
   failure before the fix was the missing `.down`. Tests added: five states against a never-replying local socket take
   under one timeout + 0.6 s (0.5 s timeout) with exactly 1 accepted connection and `.down == "TimeoutError"`, and a
   later `answer()` returns in under 0.1 s with still 1 connection; "jev off" / "daily cap" / no-error none on one group
   do not stop a later group returning its pilot-import hit (3 asks, `.down` None); transport failures URLError,
   TimeoutError, HTTP 503, HTTP 409 trip and block later calls; an exception in `ask` trips; a mixed group does not trip.
   One earlier test (exception on one state group, other groups still answer) encoded the old behaviour; I changed it to
   the new ruling (an exception trips the breaker, the other groups are Unavailable and not asked). That is my own Part 2
   test, no D1 test.
2. **decider.py spacing**: `rec: dict = {` restored. My Part 1 edit had dropped the space; the fix is in this commit, so
   `git diff e55c768 -- engine/decide/decider.py` no longer shows that line as changed (Part 1's commit `16b41f6` still
   has the slip; squash if you want it clean).
3. **Strict score check in `sync_confirmed`**: an int, or a whole float stored as int, in `range(len(criteria))`; a bool
   never. `"abc"`, 99, `True`, 1.5 and -1 are skipped and counted (test: 2, 2.0 and 0 recorded as ints; 5 skipped; a second
   sync records 0).
4. **Docstrings/annotation**: the `AskProvider` docstring says tokens are split by integer division and the remainder is
   dropped; `sync_confirmed` is annotated `-> SyncCount`.
5. **No `_type()` shortcut for the unknown-qtype check**: `sync_confirmed` now calls the public `decider.mode_of(qtype)`
   (KeyError for an unknown qtype) to skip unknown types. The Decider has no public QuestionType lookup, so
   `decider._type(qtype)` is kept for that single lookup (needed for the option and score checks); nothing was added to
   decider.py for it.

Runs, real output:
- D2 + D1 + all decide tests: `201 passed in 27.98s`.
- Full `pytest engine/tests tools/tests -q -p no:cacheprovider`:
  `1596 passed, 1 xfailed in 590.93s (0:09:50)`.

Note on the breaker: the `RemoteDecider` already caps one call at timeout + 0.25 s, so a hung VPS now costs one such call per
provider instance, not one per state. HTTP 409 trips it too (it is an `HTTP <status>`), as ruled.

---

# Fix round 2 (commit `83d0111`)

Re-review: the breaker tripped on a fast service answer because `_TRANSPORT_ERROR` matched any identifier
(UnmappedFloorKey, MissingAnswer, BadReply). Fixed as ruled.

**What I found in the deciders (read in code):**
- `RemoteDecider._call` appends one `.calls` entry per HTTP call and sets `ok` True only after a 2xx reply whose body parsed
  as JSON. A timeout, network error, non-2xx status (a redirect is also an error), oversize or non-JSON body leave `ok`
  False with `error` = class name / `HTTP <status>` / `BadReply`. A reply that is valid JSON but has a missing or malformed
  answer for a question stays `ok` True (that is a per-decision error). With no password, `ask` adds no entry at all.
- `JevDecider._call` appends one entry per batch; `ok` is True only after the SDK call returned, False when the client could
  not be made or the SDK call failed (`error` = class name and HTTP status). With no key, `ask` adds no entry. A later batch
  after a remembered client failure adds no entry either, but the first failure already tripped.

**Change** (`engine/decide/providers.py`): the identifier regex and `_transport_failure` are removed. `AskProvider.answer`
records `len(decider.calls)` before each group's ask and trips `.down` only when `ask` raised (class name) or at least one
entry added during that ask has `ok` False (reason = its `error`, cut to 200, else "CallFailed"). A per-decision error
string never trips; a group with no new entries (no key, jev unavailable, fake without calls) does not trip. The per-decision
`Unavailable(reason)` mapping is unchanged. Docstring updated.

**Tests** (test first; red run: 5 failed, the four per-decision cases and the no-new-entries case, each tripping with
`down == <error>`; then green): `FakeAsk` got `ok`/`call_error` to shape the entry each ask adds.
- UnmappedFloorKey, MissingAnswer, BadReply (and URLError as a decision error) on the first group under an ok call: `down`
  None, all 4 groups asked, the other three answered.
- A decider that adds no `.calls` entries but returns none/URLError decisions: no trip.
- An ok-False entry with URLError, TimeoutError, HTTP 503, HTTP 409 trips, blocks the rest and a later `answer()`.
- Real `RemoteDecider` against a local server answering 503: 4 states, exactly 1 request, `down == "HTTP 503"`.
- Unchanged and still green: the hung-socket test (5 states, about one timeout, 1 accepted connection, later call makes no
  request), "jev off" / "daily cap" / no-error none do not trip (pilot-import hit of a later group returned), an exception in
  `ask` trips, a mixed group does not trip.

Runs, real output:
- D2 + D1 + all decide tests: `207 passed in 27.74s`.
- Full `pytest engine/tests tools/tests -q -p no:cacheprovider`: `1602 passed, 1 xfailed in 598.58s (0:09:58)`.
