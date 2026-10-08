# Brief P0-11b — three small follow-ups to the SDK check (P0-11)

Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal
P0-11's re-review passed with two optional residuals, and its implementer parked one concern. Each is small.
The check's results (`data/campus/skp_check.json`: 65 match, 20 mismatch, 0 ambiguous, 0 miss) must not
change. Spec §1 (export-vs-backup check).

## Base, branch, merge
- Base `feat/repair-p0`; branch `hermes/P0-11b`; worktree `.hermes/worktrees/P0-11b`. Claude merges.

## Items
### Item 1 — a relative `--dll` reaches the child resolved
- **Test first** in `engine/tests/test_skp_check.py`: with a fake child (as the existing `run_walk` tests
  do), a relative `dll_path` arrives at the child as an absolute path. See it fail.
- Fix in `engine/campus/skp_check.py` (`run_walk`, near where the model and output paths are resolved):
  `Path(dll_path).resolve()` when it is given.
- **Done when:** the test passes.

### Item 2 — the "Ambiguous" definition names every case
- The summary's definition sentence (`skp_check.py`, the `render_markdown` text) omits the case where a family
  has more files than groups and every file fits every group; such files stay undecided.
- Add that case to the sentence, and extend the test that pins the sentence.
- **Done when:** the test passes. `render_markdown(skp_check.json)` differs from the committed
  `docs/superpowers/records/campus/skp-check.md` only in that sentence; regenerate and commit the file.

### Item 3 — one split rule, pinned
- `engine/campus/skp_check.py` copies the owner's split rule (AUTO, KEY and the 2-token skip). `engine/campus/groups.py`
  (P0-08) implements it too (`split_name(..., skip_owner_slot=True)`, as `index_by_split` uses it).
- **Test first:** a test that loads every path of `data/campus/group_index.json` (skip the test if the file is
  absent) and asserts that both implementations give the same split name for every path. If they differ, change
  neither rule: list the differing paths in the report and stop at this item. The split rule is the owner's, and the
  controller decides.
- **Done when:** the test passes on the real index.

## Acceptance commands
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-11b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_skp_check.py engine/tests/test_campus_groups.py -q -p no:cacheprovider )
```
Expected: green, with the new tests named in the report.
- The SDK walk is **not** needed; it takes about 2.5 GB of commit memory.
- `render_markdown` on the existing `data/campus/skp_check.json` gives the regenerated page.

## Rules for this job
- Change only `engine/campus/skp_check.py`, `engine/tests/test_skp_check.py`, a new test file if you prefer
  one, and `docs/superpowers/records/campus/skp-check.md`.
- Never open the CHECKPOINT-17 backup or master.

## Report
- Write `docs/superpowers/records/hermes/P0-11b-report.md` with real output. Commit with
  `Hermes-Job: P0-11b`.
- Hand in: `tools/jobs.py done P0-11b --branch hermes/P0-11b`.
