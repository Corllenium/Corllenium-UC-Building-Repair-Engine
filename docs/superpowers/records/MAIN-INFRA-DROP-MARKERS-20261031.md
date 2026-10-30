# Dropping the orange markers from the published 4F-7F floors (2026-10-31)

Status: stopped after the 7F pilot. Nothing published. Repo 03 floors are unchanged.

## Why the cubes survive

The owner authorized deleting them on every floor (`approved-selection.json`, 2026-10-26). No pipeline stage removes them, and
`run_floor_pipeline` never passed `--drop-before-faces`, so they reach every candidate of the 4F-7F line.

## 7F pilot

`tools.main_infra_drop_markers` removed exactly 24 faces from `e5/7F`, giving `e5/7F-drop-markers` (19,321 triangles).

| | claude-e5-19345 (published) | claude-e5-drop-markers-19321 |
|---|---|---|
| Guard | PASS, 0 px | FAIL, 4 px (2 material_changed, 2 moved_other) |
| Textures | PASS | FAIL, 281 of 215,747 samples |
| Coverage | PASS | FAIL, 223 deleted, 33 faces unmet |
| Interior | 45 px | 45 px |
| Validator frame centre | 708.66, -885.83, 177.17 | 698.82, -782.48, 201.77 |
| Probes | 1,283 | 1,262 |

Each validator run took 17 minutes on 7F. The cubes sit on opposite corners of the bounds, so removing them moves the guard grid and the
Validator's cameras. The judges then sampled the same geometry from new positions.

The failing faces are not recoverable by a restore: `main_infra_restore_faces` refused with "faces not in the E3 candidate (E3 removed
them)". The pipeline also forbids a heal after a guard failure until the failing views are diagnosed.

This means the published 7F has E3 removals that show from the shifted positions. That is independent of the cubes and was not
sampled before.

## Open choices

1. Pin the frame: judge the marker-free candidate in the frame of the full BEFORE, proving the cubes are the only change. This changes
   the judge, so it needs the owner's decision.
2. Rerun E3 and E5 from a marker-free input. This also addresses the E3 removals, at far higher cost.
