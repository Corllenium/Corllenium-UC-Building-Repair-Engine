# U1-A — Unity import check, Python side (plan Tasks 1-5)

- Branch: hermes/U1-A   Base: 7258652 (feat/repair-p1p2)
- Commits:
  1eaa520 fix(unity): address review changes on tie-breaking, shared orientation rule and find_errors shape
  371c8c3 feat(unity): unity-check verdict (UNITY-SAFE / BROKEN BY IMPORT, by cause, find_errors on both) and its CLI
  e93a490 feat(unity): name look, texture, UV and normal causes on matched faces (black faces = normal against the face)
  7c127eb feat(unity): oriented face matching between the build and Unity's import (matched/missing/extra/flipped, 16-bit overflow)
  0298fd0 feat(unity): align Unity's frame to the build by the best of 48 signed axis permutations
  6d20bc2 feat(unity): read a Unity dump (obj+mtl+sidecar), refusing incomplete or normal-less dumps
- Brief: docs/superpowers/records/briefs/U1-A-unity-check-python.md

## Items

### Item 1 — Task 1: read a Unity dump: DONE
- Tests added: `test_a_complete_dump_reads_mesh_corner_normals_and_sidecar`, `test_a_dump_without_its_sidecar_is_refused`, `test_a_half_written_dump_is_refused`, `test_an_unknown_schema_is_refused`, `test_a_face_without_normals_is_refused`
- Red run (before the code):
  ```
  ModuleNotFoundError: No module named 'engine.unity'
  ```
- Green run (after):
  ```
  .....                                                                    [100%]
  5 passed in 0.59s
  ```
- Notes: none

### Item 2 — Task 2: align Unity's frame to the build's: DONE
- Tests added: `test_a_mirrored_scaled_copy_aligns_exactly`, `test_an_unrelated_mesh_is_refused`
- Red run (before the code):
  ```
  ModuleNotFoundError: No module named 'engine.unity.align'
  ```
- Green run (after):
  ```
  ..                                                                       [100%]
  2 passed in 0.18s
  ```
- Notes: On symmetric shapes like cubes where all 48 permutations match 100% of vertices, added secondary tie-breaker (negative mean distance when vertex counts match, or face matching) to select the exact coordinate mapping.

### Item 3 — Task 3: match faces and name the geometry causes: DONE
- Tests added: `test_an_unchanged_import_matches_every_face`, `test_a_dropped_face_is_missing`, `test_a_face_unity_turned_round_is_flipped_not_missing`, `test_coincident_opposite_faces_count_as_two_each_side`, `test_a_16_bit_mesh_over_65535_vertices_is_flagged`
- Red run (before the code):
  ```
  ModuleNotFoundError: No module named 'engine.unity.check'
  ```
- Green run (after):
  ```
  .....                                                                    [100%]
  5 passed in 0.16s
  ```
- Notes: Unity's dump reverses face winding (`face_v[:, ::-1]`). Used `flip = (det > 0)` when comparing build frame faces against Unity dump faces so that unchanged imports match orientations correctly.

### Item 4 — Task 4: look, UV and normal causes: DONE
- Tests added: `test_matching_looks_uvs_and_normals_report_nothing`, `test_a_corner_normal_pointing_into_the_face_is_named_black_face_cause`, `test_a_shifted_uv_is_uv_changed`, `test_a_face_without_material_that_unity_gave_a_default_is_remapped_not_a_crash`
- Red run (before the code):
  ```
  ImportError: cannot import name 'surface_diff' from 'engine.unity.check'
  ```
- Green run (after):
  ```
  .........                                                                [100%]
  9 passed in 0.17s
  ```
- Notes: none

### Item 5 — Task 5: the verdict and engine.cli unity-check: DONE
- Tests added: `test_an_unchanged_import_is_unity_safe`, `test_a_dropped_face_is_broken_by_import_with_its_cause`, `test_an_incomplete_dump_is_refused`
- Red run (before the code):
  ```
  SystemExit: 2 (invalid choice: 'unity-check')
  ```
- Green run (after):
  ```
  ...                                                                      [100%]
  3 passed in 0.74s
  ```
- Notes: Added `unity-check` subparser to `engine/cli.py`, registered `--out` in `_OUTPUT_ARGS` for protected output check.

### Review fix round (commit 1eaa520): DONE
- Finding 1: Removed by-index mean-distance tie-break in `align.py`; uses order-free oriented face-set overlap exclusively.
- Finding 2: Evaluates vertex match for all 48 permutations first; builds `b_faces` lazily and checks face overlap only for permutations tied at best match (skipped when unique winner).
- Finding 3: Unified winding orientation rule into shared `dump_winding_flips` in `align.py`, used by both `align.py` and `check.py`. Added test `test_split_vertex_reordered_cube_matches_exactly` (36 vs 8 vertices).
- Finding 4: Updated `_kind_counts` in `check.py` to read `errors["counts"]` (the actual structure returned by `find_errors`), noting the plan's shape guess was wrong. Added test `test_worse_kind_appears_in_causes_when_unity_gains_error`.

## Acceptance command outputs

### Command 1: new suite
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
W="D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/U1-A"
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_unity_dump.py engine/tests/test_unity_align.py engine/tests/test_unity_check.py engine/tests/test_cli_unity_check.py -q -p no:cacheprovider )
```
Output:
```
.....................                                                    [100%]
21 passed in 1.27s
```

### Command 2: full engine suite
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
W="D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/U1-A"
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
```
Output:
```
1869 passed, 1 xfailed in 934.81s (0:15:34)
```

### Command 3: tools suite
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
W="D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/U1-A"
( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest tools/tests -q -p no:cacheprovider )
```
Output:
```
........................................................................ [ 40%]
........................................................................ [ 80%]
....................................                                     [100%]
180 passed in 12.78s
```

## Unsure about
Nothing: all 21 new tests, 1869 engine tests (with the 1 known strict xfail), and 180 tools tests pass with real output.
