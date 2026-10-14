# U1-C — Headless mirror import, C# exporter, override postprocessor, unity-mirror-import CLI (plan Task 7)

- Branch: hermes/U1-C   Base: 58f228c (feat/repair-p1p2)
- Brief: `docs/superpowers/plans/2026-10-10-unity-import-check.md#task-7`

## Items

### Item 1 — Task 7: C# exporter, override postprocessor, headless runner, and CLI: DONE
- Tests added (`engine/tests/test_unity_mirror.py`):
  - `test_a_stale_importer_copy_is_refused_naming_both_hashes`
  - `test_a_missing_unity_is_refused`
  - `test_a_timeout_kills_only_its_own_process_and_leaves_no_valid_dump`
  - `test_a_real_round_trip_under_a_neutral_preset_is_unity_safe`
- Red run (before the code):
  ```
  ImportError: cannot import name 'mirror' from 'engine.unity'
  1 error in 0.30s
  ```
- Real round-trip finding (Task 7 Step 6 stop-and-fix check):
  - On the first headless Unity 6000.4.7f1 round trip of `cube(100.0)` under the neutral preset, `unity-check` reported `BROKEN BY IMPORT ['flipped', 'worse:reversed']` (`det = -1.0`, `flipped = 12`), and `usemtl m0` became `defaultMat` when no `.mtl` accompanied `b.obj`.
  - Root causes fixed:
    1. `dump_winding_flips` in `engine/unity/align.py` had `return det > 0`, which was tested only against the synthetic `_dump(b)` matrix `M = [[-1,0,0],[0,0,1],[0,1,0]]` (`det = +1`) where X was mirrored AND Y/Z were swapped. Real Unity's OBJ importer mirrors X (`M = diag(-1,1,1)`, `det = -1`) and reverses triangle winding (`f[:, ::-1]`). Once vertex coordinates are mapped back to the build frame by `a.matrix`, a Unity dump's triangle vertex order is always reversed (`dump_winding_flips -> True`).
    2. In `engine/unity/mirror.py`, `_stage` now also stages `materials.mtl` when present next to a `repair-unit` build, or synthesizes a minimal staging `.mtl` when a raw `.obj` declares `usemtl` without an `.mtl` file, so Unity's OBJ importer preserves material names instead of collapsing to `defaultMat`.
- Green run (after):
  ```
  ..............................                                           [100%]
  30 passed in 9.04s
  ```

## Acceptance command outputs

```
$ ( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_unity_dump.py engine/tests/test_unity_align.py engine/tests/test_unity_check.py engine/tests/test_cli_unity_check.py engine/tests/test_unity_mirror.py tools/tests/test_unity_mirror_sync.py -q -p no:cacheprovider )
..............................                                           [100%]
30 passed in 9.04s
```

```
$ ( cd "$W" && PYTHONPATH="$PWD" "$PY" -m pytest tools/tests -q -p no:cacheprovider )
........................................................................ [ 38%]
........................................................................ [ 77%]
...........................................                              [100%]
187 passed in 11.25s
```

## Unsure about
- None. All unit tests and the real headless Unity 6000.4.7f1 round-trip test pass with `UNITY-SAFE` (exit code 0).
