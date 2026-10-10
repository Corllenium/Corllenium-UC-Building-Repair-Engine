# Brief P2-H2: small fixes the P2-E3 and P2-E8c reviews parked

Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal

Close the Minor findings the reviews of P2-E3 (hidden faces) and P2-E8c (the needs-modelling queue) parked. Each is
small, but together they make the engines' grouping faster, their records consistent and the SketchUp helper
correct. These are the P2 engines of `docs/superpowers/plans/2026-10-03-repair-engine-p1-p2.md`.

## Base and branch

- Base: `feat/repair-p1p2`.
- Branch `hermes/P2-H2`, in worktree `.hermes/worktrees/P2-H2`. The controller merges.

## Files

- Modify:
  - `engine/repair/engines/e3_hidden.py`;
  - `engine/campus/needs_modelling.py`;
  - `engine/cli.py` (only `repair_stages` / the `--engines` parsing and the `cmd_repair_unit` docstring);
  - `tools/sketchup/needs_modelling_views.rb`.
- Tests: add new test functions in **new** files `engine/tests/test_p2_h2_minors.py` and
  `tools/tests/test_p2_h2_views.py`. The single existing-file edit allowed is item 4's docstring line in
  `engine/tests/test_e3_hidden.py`.

## Items

Do them in order, test first, with one commit per item.

### Item 1: near-flat groups are not over-split

- **The finding:** `split_group` in `e3_hidden.py` (about line 116) uses an axis whenever its span is above `1e-9`. A
  near-flat group whose third axis spans only rounding noise gets tiny cubic cells. Measured: 2,048 faces over
  100 x 100 in with a z-span of 0.001 in became **1,701 sites**; with a z-span of 0, **11**.
- **Test first:** build that group (a flat 32 x 32 grid of 2,048 triangles over 100 x 100 in, with z jittered within
  ±0.0005 in). Assert `split_group` gives the same number of sites as the same grid with z = 0, and that every site
  has at most 512 faces.
- **Fix:** ignore an axis whose span is below 1 % of the largest span, or below 1 in.

### Item 2: remove the dead `zero_area` branch

- **The finding:** at about `e3_hidden.py:264`, `"hidden" if ok[f] else "zero_area"` can no longer take its
  `zero_area` side, because ruling R9 removed zero-area faces from E3.
- **Test first:** assert every E3 edit's evidence rules are `"hidden"` on the `box_with_partition` fixture (this
  passes today; it guards the change).
- **Fix:** set the rule to `"hidden"` directly.

### Item 3: the needs-modelling cross-check reads only E8 lines

- **The finding:** `needs_modelling.py` (about line 316) gathers rolled-back site ids from every stage's edit-log
  lines. E3's ids start at 0 like E8's, so an E3 line can satisfy the check for an E8 piece.
- **Test first:** an edit log that has an E3 rolled-back line with id 5 and no E8 line for piece 5. A report listing
  E8 piece 5 as rolled back must raise ValueError.
- **Fix:** filter by `line.get("stage") == "E8"`.

### Item 4: stale docstrings

- `engine/cli.py` `cmd_repair_unit` still says "Returns 0 when the E8 stage passed". Make it describe exit codes
  0/1/2/3 for any engines run.
- `engine/tests/test_e3_hidden.py` line 4: the module docstring still says pass 1 takes "or zero area". Make it say
  zero-area faces are E1's (ruling R9), and mention the dense pre-filter (R7). Docstring only.
- No test needed; say so in the report.

### Item 5: E8b before E8a is refused

- **The finding:** `--engines E8b,E8a` now runs E8b first, silently. The flat fill needs solidify first.
- **Test first:** `engine.cli main(["repair-unit", ..., "--engines", "E8b,E8a", ...])` returns 2, and stderr
  says "E8b needs E8a first". `--engines E8a,E8b` and `--engines E8b` alone still work.
- **Fix:** in `repair_stages`, raise ValueError when both are named and E8b comes before E8a.

### Item 6: the SketchUp helper's three small faults

1. A negative offset: `p.offset(across, -d)` (about line 76). Change it to `p.offset(across.reverse, d)`, and
   likewise for `upward`.
2. Restore the lost `\` line continuation at about line 93.
3. `needs_modelling.py` lines 14-16: split the docstring sentence "...cannot be outlined or aimed at: it failed no
   check of its own." It is true of a piece rolled back with its whole stage, not of a piece with no border.

- **Test first** (static, in `tools/tests/test_p2_h2_views.py`): the Ruby file contains no `.offset(` call with a
  negative length argument (regex `\.offset\([^)]*,\s*-`), and no line with two string literals separated by 5 or
  more spaces.
- The existing static scan (`tools/tests/test_needs_modelling_views.py`) must still pass.

### Item 7 (added 2026-10-11): the P2-V2 re-review's minors in the Validator's floor

The Validator now judges to the owner's floor (merged 0795710). These three notes are small and allowed in
`engine/validate/**` because they only add tests or wording; **no verdict may change.**

1. **The 5° boundary has no test.** In `engine/tests/test_validate_floor_covered.py`, add two cases around the
   near-parallel rule (`|n_blocker · n_sample| >= cos 5°` in `_Judge.blocker`, `engine/validate/checks.py` about
   lines 600-612): a layer tilted about 4° and within the depth tolerance stays excused (check 3 PASS); one tilted
   about 6° covers (check 3 FAIL). Build them from the existing overlay fixture in that file.
2. **The `_FLOOR_LATTICE_PER_LINE` flag** (`engine/validate/checks.py` about line 72) keeps a second code path only
   for the equivalence test, and the change it was added for gave no speedup. Keep the flag, but reword its comment
   to say it is a reference path for `test_validate_floor_speed.py` and gave no speedup; in
   `engine/tests/test_validate_floor.py`, replace `getattr(b, "weight", np.ones(len(b)))` with `b.weight`.
3. **The report's known limits.** Append to `.superpowers/sdd/2026-10-03-repair-engine-p1-p2/task-P2-V2-report.md`
   under "Item 5: the floor's known limits": (3) a blocker within 5° of parallel and within the depth tolerance stays
   an overlay rather than a cover on grazing lines (the V2-R3 overlay class); (4) floor pixel counts are float areas,
   not integers. Use `git add -f` for that file.

- **Done when:** the two new boundary tests pass, `engine/tests/test_validate_floor.py` and
  `engine/tests/test_validate_floor_covered.py` pass, and the report has the two limits.

## Acceptance commands

```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
W="D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P2-H2"
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_p2_h2_minors.py tools/tests/test_p2_h2_views.py tools/tests/test_needs_modelling_views.py engine/tests/test_e3_hidden.py engine/tests/test_needs_modelling.py engine/tests/test_cli_repair_unit.py -q -p no:cacheprovider )
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest tools/tests -q -p no:cacheprovider )
```

Expected: all pass. The engine suite keeps its existing 1 xfailed and takes about 15 minutes.

## Rules for this job

- **Change only** the files listed. Never change `engine/guard/**`, `engine/validate/**`, `engine/site_judge.py` or
  `FixProfile`. Edit no existing test beyond item 4's docstring line.
- **No real-data runs** are needed. Never touch the owner's folders, the live export folder, the master `.skp`, the
  containers or the live database.
- **Never use a bare `cd`.** Stop only processes you started, by PID.
- **Secrets:** never open, print, log, write or commit `.env*`.
- **Stop condition:** if an item's test cannot pass without loosening a test, stop at that item, hand in what is
  committed, and say so under "Unsure about".

## Report

- `docs/superpowers/records/hermes/P2-H2-report.md`, in the format of `docs/superpowers/records/hermes/README.md`,
  with the real output of each acceptance command.
- Hand in with `tools/jobs.py done P2-H2 --branch hermes/P2-H2`.
