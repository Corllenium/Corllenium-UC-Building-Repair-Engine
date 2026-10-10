# Brief P2-V3: a cheaper visibility cast for the Validator's floor lattice

Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal

The Validator's floor measure (P2-V2, merged 0795710) makes CHTM 5th with E3 take **1,400-1,800 s** against 330 s
before. The P2-V2 report measured where the time goes: on a tenth of the lattice (433 s), `lattice_seen` took 140 s,
almost all of it `visible_samples`: the lattice's visibility cast of about 2.68 M points against about 2,000
viewpoints (1,403 of them eye-height probes). `present` and `blocker` are a small share, and the "present once per
point" change gave no speedup.

This job makes that cast cheaper **without changing any verdict or count**. The floor's `validation.json` must be
byte-identical apart from `timings_s`.

## Base and branch

- Base: `feat/repair-p1p2`. Branch `claude/P2-V3`, worktree `.claude/worktrees/P2-V3`. The controller merges.

## Files

- Modify: `engine/validate/checks.py` (`lattice_seen`, `visible_samples` and what they call), `engine/validate/
  visibility.py` (the caster), `engine/validate/floor.py` only if the lattice itself is built there.
- Test: `engine/tests/test_validate_floor_speed.py` (extend), plus a new golden-equivalence test.
- Read only: everything else. Nothing in `engine/guard/**`, `engine/repair/**`, `FixProfile`.

## Items

Each test first; commit after each item; every commit green.

### Item 1: measure before touching anything
- Profile `lattice_seen` on CHTM-L05's E8a+E3 output (`C:/Temp/v2/val_new/` has the inputs; otherwise rebuild
  with `repair-unit --engines E8a,E3`) with `cProfile`, whole run, not a tenth. Record the top 15 by cumulative time
  in the report. **Done when:** the table is in the report with the total.

### Item 2: cut the probe work that cannot see the point
- A lattice point on a face is visible from a probe only if the probe lies on the face's front side (or back side,
  for the back pass) and within the cast's reach. Cull probe-point pairs by side and by distance before casting.
- Then cull by a coarse occlusion test: cast from each probe one ray per lattice CELL (the cell centre) first; a
  cell whose centre ray is blocked by a face far nearer than the cell has every point blocked. Only cells not
  decided this way get per-point rays.
- **Test first:** the existing equivalence test (`test_present_once_per_point_and_side_gives_the_per_line_verdicts`)
  extended to compare the whole floor report, with the culls on against off, on all its fixtures and on a fixture
  with a probe inside a room with a slot. **Done when:** identical reports, and the item-1 profile re-run shows the
  saving.

### Item 3: batch and reuse the casts
- The Validator already casts the sample points against the same viewpoints. Where a lattice point coincides with a
  sample (snapped at the print step), reuse that answer instead of casting again.
- Cast all probes' rays for one face in one Embree batch, not one batch per viewpoint.
- **Done when:** the equivalence test still passes and the profile shows the saving.

### Item 4: the golden proof
- `engine.cli validate` on the three golden E8a+E3 outputs: `validation.json` byte-identical to the base's apart
  from `timings_s` (compare with a script, in the report). Time before and after per unit.
- **Target:** CHTM-L05 E8a+E3 under 600 s on an idle machine. If the target cannot be met without changing a
  verdict, stop and report the number; never loosen a count.

## Acceptance commands

```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
W="D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/P2-V3"
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_validate_floor_speed.py engine/tests/test_validate_floor.py engine/tests/test_validate_floor_covered.py engine/tests/test_validate_horizon.py engine/tests/test_validate_fill_site.py -q -p no:cacheprovider )
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest tools/tests -q -p no:cacheprovider )
```

Expected: all pass (engine keeps its 1 xfailed), the byte-identity script prints `identical` for all three units,
and the timing table.

## Rules for this job

- The judge may not change: every verdict, count and listed face identical. A culled pair must be provably
  invisible, never "unlikely".
- No new dependency. Outputs to `C:/Temp/v3/` only. Stop only your own processes, by PID.
- Secrets: never open `.env*`.

## Report

- The plan's SDD ledger: `.superpowers/sdd/2026-10-03-repair-engine-p1-p2/task-P2-V3-report.md` (`git add -f`).
- Hand in with `tools/jobs.py done P2-V3 --branch claude/P2-V3`.
