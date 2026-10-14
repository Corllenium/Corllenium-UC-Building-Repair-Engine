# P2-H2 — small fixes the P2-E3, P2-E8c and P2-V2 reviews parked

- Branch: hermes/P2-H2   Base: 0795710 (feat/repair-p1p2)
- Commits:
  - ada67d8 P2-H2 item 1: ignore near-flat axes in E3 split_group
  - 3f54a5a P2-H2 item 2: remove dead zero_area rule branch in E3
  - a23ed9e P2-H2 item 3: filter needs_modelling rolled_lines cross-check to stage E8
  - faa288b P2-H2 item 4: update stale docstrings in cmd_repair_unit and test_e3_hidden
  - d9bcd60 P2-H2 item 5: refuse E8b before E8a in repair_stages
  - a76cc34 P2-H2 item 6: fix SketchUp helper offset/continuation and needs_modelling docstring
  - 8f7666d P2-H2 item 7: add 5-deg cover boundary tests, reword lattice flag comment, and record floor known limits
- Brief: `docs/superpowers/records/briefs/P2-H2-review-minors.md`

## Items

### Item 1 — near-flat groups are not over-split: DONE
- Tests added: `test_item1_near_flat_groups_are_not_over_split` in `engine/tests/test_p2_h2_minors.py`
- Red run (before the code):
  ```
  FAILED engine/tests/test_p2_h2_minors.py::test_item1_near_flat_groups_are_not_over_split
  AssertionError: assert 1927 == 9
  1 failed in 1.05s
  ```
- Green run (after):
  ```
  15 passed in 28.88s
  ```
- Notes: Ignored any axis whose span is below 1 in or below 1 % of the largest axis span (`axes = (span >= 1.0) & (span >= 0.01 * float(span.max()))`).

### Item 2 — remove the dead `zero_area` branch: DONE
- Tests added: `test_item2_every_e3_edit_rule_is_hidden_on_box_with_partition` in `engine/tests/test_p2_h2_minors.py`
- Red run (before the code): Guard test passes before and after; `rules` in `e3_hidden.py` now sets `["hidden"] * len(faces)` directly.
- Green run (after):
  ```
  2 passed in 0.77s
  ```

### Item 3 — the needs-modelling cross-check reads only E8 lines: DONE
- Tests added: `test_item3_needs_modelling_cross_check_reads_only_e8_lines` in `engine/tests/test_p2_h2_minors.py`
- Red run (before the code):
  ```
  FAILED engine/tests/test_p2_h2_minors.py::test_item3_needs_modelling_cross_check_reads_only_e8_lines
  Failed: DID NOT RAISE ValueError
  1 failed, 2 passed in 0.81s
  ```
- Green run (after):
  ```
  19 passed in 0.84s
  ```
- Notes: Filtered `rolled_lines` in `engine/campus/needs_modelling.py` by `line.get("stage") == "E8"`.

### Item 4 — stale docstrings: DONE
- Tests added: None (no test needed per brief).
- Notes: Updated `cmd_repair_unit` docstring in `engine/cli.py` to describe exit codes 0/1/2/3 across any engine stages run, and updated module docstring in `engine/tests/test_e3_hidden.py` to state zero-area faces belong to E1 (ruling E3-R9) and mention the 36-point dense pre-filter lattice (ruling E3-R7).

### Item 5 — E8b before E8a is refused: DONE
- Tests added: `test_item5_e8b_before_e8a_is_refused` in `engine/tests/test_p2_h2_minors.py`
- Red run (before the code):
  ```
  FAILED engine/tests/test_p2_h2_minors.py::test_item5_e8b_before_e8a_is_refused
  AssertionError: assert 'E8b needs E8a first' in "error: [Errno 2] No such file or directory: 'data\\\\campus\\\\campus_map.json'\n"
  1 failed, 3 passed in 1.02s
  ```
- Green run (after):
  ```
  15 passed in 10.03s
  ```
- Notes: `repair_stages` raises `ValueError("repair-unit: E8b needs E8a first")` when both `E8a` and `E8b` are present and `E8b` precedes `E8a`. Verified `--engines E8a,E8b` and `--engines E8b` alone still succeed.

### Item 6 — the SketchUp helper's three small faults: DONE
- Tests added: `test_the_script_never_calls_offset_with_a_negative_length`, `test_no_line_has_two_string_literals_separated_by_five_or_more_spaces` in `tools/tests/test_p2_h2_views.py`
- Red run (before the code):
  ```
  FAILED tools/tests/test_p2_h2_views.py::test_the_script_never_calls_offset_with_a_negative_length
  FAILED tools/tests/test_p2_h2_views.py::test_no_line_has_two_string_literals_separated_by_five_or_more_spaces
  2 failed in 0.06s
  ```
- Green run (after):
  ```
  59 passed in 0.07s
  ```
- Notes: Replaced `p.offset(across, -d)` / `p.offset(upward, -d)` with `p.offset(across.reverse, d)` / `p.offset(upward.reverse, d)`, restored the `\` line continuation on the placeholder `UI.messagebox`, and split the `stage_rolled_back` vs `no_border_not_listed` docstring sentences in `engine/campus/needs_modelling.py`.

### Item 7 — the P2-V2 re-review's minors in the Validator's floor: DONE
- Tests added: `test_a_layer_tilted_four_degrees_within_depth_tolerance_stays_excused`, `test_a_layer_tilted_six_degrees_within_depth_tolerance_covers_and_fails_check_3` in `engine/tests/test_validate_floor_covered.py`
- Green run:
  ```
  20 passed in 5.89s
  ```
- Notes: Added 4° (excused, check 3 PASS) and 6° (covered, check 3 FAIL) boundary tests around `PARALLEL_COS = cos(5°)` in `test_validate_floor_covered.py`, reworded the `_FLOOR_LATTICE_PER_LINE` comment in `engine/validate/checks.py`, replaced `getattr(b, "weight", np.ones(len(b)))` with `b.weight` in `engine/tests/test_validate_floor.py`, and appended known limits (3) and (4) to `.superpowers/sdd/2026-10-03-repair-engine-p1-p2/task-P2-V2-report.md` (`git add -f`).

## Acceptance command outputs

```
$ ( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_p2_h2_minors.py tools/tests/test_p2_h2_views.py tools/tests/test_needs_modelling_views.py engine/tests/test_e3_hidden.py engine/tests/test_needs_modelling.py engine/tests/test_cli_repair_unit.py engine/tests/test_validate_floor.py engine/tests/test_validate_floor_covered.py -q -p no:cacheprovider )
........................................................................ [ 58%]
....................................................                     [100%]
124 passed in 36.79s
```

```
$ ( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest tools/tests -q -p no:cacheprovider )
........................................................................ [ 38%]
........................................................................ [ 77%]
...........................................                              [100%]
187 passed in 12.46s
```

## Unsure about
- None. All 7 items and their tests pass cleanly.
