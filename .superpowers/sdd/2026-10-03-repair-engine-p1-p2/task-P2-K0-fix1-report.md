# P2-K0 fix round 1 report

Worktree `.claude/worktrees/P2-K0`, branch `claude/P2-K0`, base 1f1bb47. Skill `uc-repair-rules` read first; nothing in
`engine/guard/**`, `engine/validate/**`, no `FixProfile` change, no blocked operation touched.

Status: DONE_WITH_CONCERNS (one discrepancy with the dispatch text, below).

## Commits
- `8f5a981` fix(p2-k0): the kernel refuses a legacy-marked edit from any engine but the legacy observer
- `6e5fc46` docs(p2-k0): repair_unit says validate_sites=False keeps a non-legacy engine's edits unchecked (tests only)

## Change 1: the legacy marker is not a bypass
`engine/repair/kernel.py` `_repair_checked`: right after `engine.plan(unit, ctx)`, `if not is_legacy and any(e.legacy for e in planned)`
raises `ValueError` (same `is_legacy = isinstance(engine, LegacyEngine)` test the kernel already uses). Raised before
the edits reach the log, the judge or `apply_edits`, with and without `validate_sites`.

New test (`engine/tests/test_kernel_site_checks.py`):
`test_a_non_legacy_engine_planning_a_legacy_marked_edit_is_refused[True|False]` (the minimal `_Planned` engine returns one
E8 `add` with `legacy=True`; `pytest.raises(ValueError, match="legacy")`). The existing scan test
(`test_edit_add_only_e8.py`) is untouched and passes.

Red (before the kernel change):
```
E       Failed: DID NOT RAISE ValueError
engine\tests\test_kernel_site_checks.py:234: Failed
=========================== short test summary info ===========================
FAILED engine/tests/test_kernel_site_checks.py::test_a_non_legacy_engine_planning_a_legacy_marked_edit_is_refused[True]
FAILED engine/tests/test_kernel_site_checks.py::test_a_non_legacy_engine_planning_a_legacy_marked_edit_is_refused[False]
2 failed, 14 deselected in 2.53s
```
After the kernel change, and before the fixtures were changed, three existing tests failed with exactly the new error
(`ValueError: engine fixture is not the legacy observer, so none of its edits may carry the legacy marker ...`):
`test_each_p0_16_mutation_...[2 a visible face in another look]`, `test_a_failure_unmasked_by_a_rollback_is_charged_in_the_next_round`,
`test_when_the_rounds_run_out_what_is_still_charged_is_rolled_back_and_says_so`. That is the proof the fixtures were
the bypass users.

Green (after the two fixture edits):
```
engine/tests/test_kernel_site_checks.py + engine/tests/test_edit_add_only_e8.py
31 passed in 10.79s
```

### The two fixture Edits changed (named)
1. `_bad`, kind **"2 a visible face in another look"**, the `kind="add"` Edit (was `engine="E5", ..., legacy=True`):
   now `engine="E8"` and `legacy=True` removed. The `remove` Edit of that kind stays `engine="E5"`.
2. `_covered_then_unmasked`, the `copy` add (was `engine="E5", ..., legacy=True`): now `engine="E8"`, `legacy=True` removed.

Nothing else in those tests changed. The only additions are the new test above.

## Change 2: docstring
`repair_unit` docstring (`engine/repair/kernel.py`) now ends with a WARNING paragraph: with `validate_sites=False` the
edits of a non-legacy engine are kept unchecked (no judge, no site rolled back, a failing stage ships whole); that
mode is for tests only; every P2 command-line path must pass the judge (`validate_sites=True`, judge in
`ctx.validator`). No behaviour change.

## Acceptance: full suites (last lines verbatim)
Engine, `( cd <worktree> && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )`, run on HEAD 6e5fc46:
```
........................................................................ [ 92%]
........................................................................ [ 96%]
............................................................             [100%]
1715 passed, 1 xfailed in 1128.28s (0:18:48)
```
Tools, `... -m pytest tools/tests -q -p no:cacheprovider`:
```
........................................................................ [ 58%]
...................................................                      [100%]
123 passed in 20.87s
```

## Concerns (said plainly)
- **Discrepancy with the dispatch text:** the dispatch named the fixtures as `_bad` kind "5 a face one inch in front of a
  visible face" and `_covered_then_unmasked`'s copy. In the checked-out file (HEAD 1f1bb47), kind 5 is already
  `engine="E8"` with no `legacy`; the other `legacy=True` add in `_bad` was kind **"2 a visible face in another look"**
  (E5 add). I changed that one and the `copy` add, which is what the red run (three failures) pointed to. Kind 5 was not touched.
- The byte-identity runs on sidewalk A/B and CHTM 5th (the brief's Exit) were not repeated here: this round changes
  no legacy path (the new check only fires for non-legacy engines; the legacy edits all carry the marker and pass), but
  I did not run them; unverified by a real-data run.
- The engine suite takes about 19 minutes in this worktree.
