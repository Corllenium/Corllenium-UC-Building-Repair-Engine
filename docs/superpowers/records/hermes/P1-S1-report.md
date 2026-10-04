# P1-S1 — A near-linear T-junction search, with exactly the old answers

- Branch: hermes/P1-S1   Base: 7ff3a4c5965e42607cfe0e5ab0ad45a707f1a3c4 (claude/P1-S1-tests)
- Commits:
  - 97ee358 feat(topo): spatial-hash T-junction search with exact reference agreement
- Brief: docs/superpowers/records/briefs/P1-S1-tvertex-hash.md

## Items

### Item 0 — Baseline: DONE
- The three baseline hashes from base commit 7ff3a4c:
  - `data/s1_check/before/chtm5_errors.json`: `237ddd85e233a9a823be2016a7a98279e43b1ec7c75e3685214392f4ef78ba7f`
  - `data/s1_check/before/A/CHTM_SIDE_WALK_2nd_floor/report.json`: `e724822f88d4dadac354fa3a53d630f876920bf589aa6cb5768ab478d05101c9`
  - `data/s1_check/before/B/CHTM_2nd_to_3rd_building_sidewalk_outside/report.json`: `ebeea4ed1e82543f5a71ef413ef3eeaa194a5a7844cfb0207b12fb193345e5dd`
- Baseline errors execution time on CHTM 5th floor: 98.11 s.
- Red run on base commit (ImportError during collection because oracle `find_t_vertices_reference` was not yet created):
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/P1-S1" && PYTHONPATH="$(pwd -W)" "$PY" -m pytest engine/tests/test_t_vertex_search.py -q -p no:cacheprovider )
=================================== ERRORS ====================================
____________ ERROR collecting engine/tests/test_t_vertex_search.py ____________
ImportError while importing test module 'D:\PROJECTS\UC MODEL FIXER\.claude\worktrees\P1-S1\engine\tests\test_t_vertex_search.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
C:\Users\Future26\AppData\Local\Programs\Python\Python312\Lib\importlib\__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
engine\tests\test_t_vertex_search.py:21: in <module>
    from engine.topo.adjacency import (EdgeTable, build_edge_table, degenerate_mask, find_t_vertices,
E   ImportError: cannot import name 'find_t_vertices_reference' from 'engine.topo.adjacency' (D:\PROJECTS\UC MODEL FIXER\.claude\worktrees\P1-S1\engine\topo\adjacency.py)
=========================== short test summary info ===========================
ERROR engine/tests/test_t_vertex_search.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.30s
```

### Item 1 — Spatial-hash T-junction search with exact reference agreement: DONE
- Renamed original `find_t_vertices` to `find_t_vertices_reference` verbatim as the oracle.
- Implemented new `find_t_vertices(positions_w, table, tol, face_w=None, degenerate=None, stats=None)`:
  - Pure NumPy spatial hash grid with cell size tied to typical edge length (median non-zero edge length, bounded [tol, 100*tol]).
  - Only candidate vertices `np.unique(table.edges)` are gridded.
  - Edge bounding boxes are expanded by `tol` in all axes to determine relevant grid cells.
  - Chunked pair evaluation to bound memory usage.
  - Same geometric formulas (`1e-9 < t < 1 - 1e-9`, `d <= tol`, not endpoint) and identical zero-area hint integration and sorting.
  - Sets `stats["pairs_tested"]` when requested.
- Tests passing: 21 tests in `test_t_vertex_search.py` + 10 tests in `test_topo_basics.py`:
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1" && PYTHONPATH="$(pwd -W)" "$PY" -m pytest engine/tests/test_t_vertex_search.py engine/tests/test_topo_basics.py -q -p no:cacheprovider )
...............................                                          [100%]
31 passed in 3.62s
```

### Item 2 — Nothing else changes: DONE
- Full engine test suite passed with 0 regressions: 670 passed, 1 xfailed.
- Acceptance script `tvertex_check.py` on all three real snapshots produces `identical True` with a speed-up of 26.4x on `chtm_5ft_floor` (exceeding the >= 10x target).
- SHA256 hashes of `after` runs are byte-identical to `before`:
  - `chtm5_errors.json`: `237ddd85e233a9a823be2016a7a98279e43b1ec7c75e3685214392f4ef78ba7f`
  - `A/CHTM_SIDE_WALK_2nd_floor/report.json`: `e724822f88d4dadac354fa3a53d630f876920bf589aa6cb5768ab478d05101c9`
  - `B/CHTM_2nd_to_3rd_building_sidewalk_outside/report.json`: `ebeea4ed1e82543f5a71ef413ef3eeaa194a5a7844cfb0207b12fb193345e5dd`
- Execution time of `errors` on CHTM 5th floor decreased from 98.11 s (before) to 76.22 s (after) — a 21.89 s net savings on the full floor audit.

## Acceptance command outputs

### 1. Pytest t-vertex search and topo basics
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1" && PYTHONPATH="$(pwd -W)" "$PY" -m pytest engine/tests/test_t_vertex_search.py engine/tests/test_topo_basics.py -q -p no:cacheprovider )
...............................                                          [100%]
31 passed in 3.62s
```

### 2. Full engine test suite
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1" && PYTHONPATH="$(pwd -W)" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
........................................................................ [ 10%]
........................................................................ [ 21%]
........................................................................ [ 32%]
........................................................................ [ 42%]
........................................................................ [ 53%]
........................................................................ [ 64%]
........................................................................ [ 75%]
........................................................................ [ 85%]
..........................................................x............. [ 96%]
.......................                                                  [100%]
670 passed, 1 xfailed in 614.60s (0:10:14)
```

### 3. Acceptance script on the three snapshots
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1" && PYTHONPATH="$(pwd -W)" "$PY" docs/superpowers/records/scripts/tvertex_check.py "D:/PROJECTS/UC MODEL FIXER/data/snapshots/ce26e0392ab0" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/0b290ec0bcb4" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/c0c877002500-b7c2dc01" )
CHTM_SIDE_WALK_2nd_floor: tris 4692 edges 6001 vertices 1586 tol 0.15 t-junction edges 406 identical True pairs_tested 53308 (reference 9517586) old 0.69 s new 0.045 s speed-up 15.2x
CHTM_2nd_to_3rd_building_sidewalk_outside: tris 7227 edges 9852 vertices 2800 tol 0.15 t-junction edges 408 identical True pairs_tested 98805 (reference 27585600) old 1.76 s new 0.075 s speed-up 23.3x
chtm_5ft_floor: tris 20599 edges 26856 vertices 6457 tol 0.15 t-junction edges 3791 identical True pairs_tested 522061 (reference 173409192) old 7.93 s new 0.301 s speed-up 26.4x
```

### 4. SHA256 checksums before vs after
```text
$ sha256sum \
    "D:/PROJECTS/UC MODEL FIXER/data/s1_check/before/chtm5_errors.json" \
    "D:/PROJECTS/UC MODEL FIXER/data/s1_check/before/A/CHTM_SIDE_WALK_2nd_floor/report.json" \
    "D:/PROJECTS/UC MODEL FIXER/data/s1_check/before/B/CHTM_2nd_to_3rd_building_sidewalk_outside/report.json" \
    "D:/PROJECTS/UC MODEL FIXER/data/s1_check/after/chtm5_errors.json" \
    "D:/PROJECTS/UC MODEL FIXER/data/s1_check/after/A/CHTM_SIDE_WALK_2nd_floor/report.json" \
    "D:/PROJECTS/UC MODEL FIXER/data/s1_check/after/B/CHTM_2nd_to_3rd_building_sidewalk_outside/report.json"

237ddd85e233a9a823be2016a7a98279e43b1ec7c75e3685214392f4ef78ba7f *D:/PROJECTS/UC MODEL FIXER/data/s1_check/before/chtm5_errors.json
e724822f88d4dadac354fa3a53d630f876920bf589aa6cb5768ab478d05101c9 *D:/PROJECTS/UC MODEL FIXER/data/s1_check/before/A/CHTM_SIDE_WALK_2nd_floor/report.json
ebeea4ed1e82543f5a71ef413ef3eeaa194a5a7844cfb0207b12fb193345e5dd *D:/PROJECTS/UC MODEL FIXER/data/s1_check/before/B/CHTM_2nd_to_3rd_building_sidewalk_outside/report.json
237ddd85e233a9a823be2016a7a98279e43b1ec7c75e3685214392f4ef78ba7f *D:/PROJECTS/UC MODEL FIXER/data/s1_check/after/chtm5_errors.json
e724822f88d4dadac354fa3a53d630f876920bf589aa6cb5768ab478d05101c9 *D:/PROJECTS/UC MODEL FIXER/data/s1_check/after/A/CHTM_SIDE_WALK_2nd_floor/report.json
ebeea4ed1e82543f5a71ef413ef3eeaa194a5a7844cfb0207b12fb193345e5dd *D:/PROJECTS/UC MODEL FIXER/data/s1_check/after/B/CHTM_2nd_to_3rd_building_sidewalk_outside/report.json
```

### 5. CLI errors execution time before vs after on CHTM 5th floor
- Before (commit 7ff3a4c): 98.11 s
- After (commit 97ee358): 76.22 s

## Unsure about
Nothing. All 21 T-vertex tests and 10 topo basics tests pass, the full 671-item engine suite passes (670 passed, 1 xfailed), `tvertex_check.py` confirms `identical True` across all three real snapshots with 26.4x speedup on CHTM 5th, and all output SHA256 hashes match the baseline bit-for-bit.
