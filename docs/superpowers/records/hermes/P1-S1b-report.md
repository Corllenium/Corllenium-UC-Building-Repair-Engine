# P1-S1b — Bound the T-junction search's memory, plus small clean-ups (P1-S1 follow-up)

- Branch: hermes/P1-S1b   Base: 89098eebd287ff2cb40fa5b84ca96b1eab86a450 (feat/repair-p0)
- Commits:
  - 6efd262 feat(topo): bounded pair generation for T-junction search (Item 1)
  - acb78c5 feat(topo): review clean-ups for T-junction search (Item 2)
  - 32c8a86 docs(hermes): P1-S1b report -- bounded pair generation and review cleanups
  - a800430 fix(topo): resize buffer after flush when candidate count exceeds capacity (Note 1)
  - af47463 test(topo): verify oracle equality with chunk_pairs=2 exercising per-edge slicing (Note 2)
  - 7f8c3a0 test(topo): place vertices on diagonal edge to compare fallback hits with oracle (Note 3)
  - 6bbc293 fix(topo): validate chunk_pairs >= 1 and remove unreachable count==0 branch (Note 4)
- Brief: docs/superpowers/records/briefs/P1-S1b-tvertex-memory.md

## Items

### Item 1 — Bounded pair generation: DONE
- Tests added: `test_bounded_pairs_peak_matches_oracle` (appended to `engine/tests/test_t_vertex_search.py`).
- Red run (before code changes):
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py -k test_bounded_pairs_peak_matches_oracle -q -p no:cacheprovider )
F                                                                        [100%]
================================== FAILURES ===================================
___________________ test_bounded_pairs_peak_matches_oracle ____________________

    def test_bounded_pairs_peak_matches_oracle():
        """stats['pairs_peak'] must be at most chunk_pairs, and chunk_pairs=1000 gives
        identical results to default and oracle on a dense synthetic scene."""
        Pw, fw, ok, table = _scene(0, n_walls=4, depth=5)
        stats_chunked = {}
        stats_default = {}
        ref = find_t_vertices_reference(Pw, table, TOL)
>       res_chunked = find_t_vertices(Pw, table, TOL, stats=stats_chunked, chunk_pairs=1000)
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: find_t_vertices() got an unexpected keyword argument 'chunk_pairs'

engine\tests\test_t_vertex_search.py:275: TypeError
=========================== short test summary info ===========================
FAILED engine/tests/test_t_vertex_search.py::test_bounded_pairs_peak_matches_oracle
1 failed, 21 deselected in 0.45s
```
- Green run (after Item 1 implementation):
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py engine/tests/test_topo_basics.py -q -p no:cacheprovider )
................................                                         [100%]
32 passed in 3.49s
```
- Memory reduction:
  Replaced unbounded Python lists with pre-allocated NumPy chunk buffers. Peak tracemalloc memory dropped significantly on the 142,234-triangle unit (`data/snapshots/85f36d8cfe0e-ea7edc71`).
  - P1-S1 baseline:
    ```text
    Tris: 142234, Edges: 189024, Tol: 0.15000000000000002
    Time: 17.923s, Peak memory: 499.15 MB, pairs_tested: 5202113, hits: 20706
    ```
  - P1-S1b:
    ```text
    Tris: 142234, Edges: 189024, Tol: 0.15
    Time: 27.086 s, Peak: 279.71 MB, pairs_tested: 5202113, pairs_peak: 999997, full_scan_edges: 0, hits: 20706
    ```
- Notes:
  `chunk_pairs: int = 1_000_000` is added as keyword-only argument. Memory stays strictly bounded by evaluating each buffer chunk up to `chunk_pairs` and keeping `pairs_peak <= chunk_pairs`.

### Item 2 — Small clean-ups from the review: DONE
- Tests added: `test_long_diagonal_edge_uses_full_scan_fallback` (appended to `engine/tests/test_t_vertex_search.py`).
- Red run (before code changes):
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py -k test_long_diagonal_edge_uses_full_scan_fallback -q -p no:cacheprovider )
F                                                                        [100%]
================================== FAILURES ===================================
_______________ test_long_diagonal_edge_uses_full_scan_fallback _______________

    def test_long_diagonal_edge_uses_full_scan_fallback():
        """An edge whose bounding box would visit more cells than candidate vertices
        falls back to testing all candidates directly, matching the reference oracle."""
        P, F = _scene_raw(0, n_walls=4, depth=5)
        min_p = P.min(axis=0)
        max_p = P.max(axis=0)
        b = len(P)
        diag_triangle = np.array([
            [min_p[0], min_p[1], min_p[2]],
            [max_p[0], max_p[1], max_p[2]],
            [min_p[0], max_p[1], min_p[2] + 10.0],
        ])
        P_diag = np.vstack([P, diag_triangle])
        F_diag = np.vstack([F, [[b, b + 1, b + 2]]])
        Pw, fw, ok, table = _prepared(P_diag, F_diag)
    
        stats = {}
        ref = find_t_vertices_reference(Pw, table, TOL)
        res = find_t_vertices(Pw, table, TOL, stats=stats)
    
        assert _same(ref, res)
>       assert "full_scan_edges" in stats
E       AssertionError: assert 'full_scan_edges' in {'pairs_tested': 12972, 'pairs_peak': 12972}

engine\tests\test_t_vertex_search.py:306: AssertionError
=========================== short test summary info ===========================
FAILED engine/tests/test_t_vertex_search.py::test_long_diagonal_edge_uses_full_scan_fallback
1 failed, 22 deselected in 0.45s
```
- Green run (after Item 2 implementation):
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py engine/tests/test_topo_basics.py -q -p no:cacheprovider )
.................................                                        [100%]
33 passed in 3.79s
```
- Cleanups applied:
  - Added comprehensive docstring to `find_t_vertices` detailing return structure, `stats` keys (`pairs_tested`, `pairs_peak`, `full_scan_edges`), and `chunk_pairs`.
  - Removed dead branch `if len(cand) == 0:` (P1-S1's lines 118-122).
  - Added full scan fallback: when an edge's padded bounding box spans more cells than total candidate vertices (`n_cells > V`), the search evaluates against all candidate vertices directly and increments `stats["full_scan_edges"]`.

---

## Review Notes Addressed (Review of commit 32c8a86)

### Note 1: Buffer resize after flush when candidate count exceeds initial capacity
- Finding: At `adjacency.py:276-294`, after a flush when `buf_pos + k > chunk_pairs`, if `k <= chunk_pairs` the code fell through to line 294 without checking capacity. If `k > len(buffer)` (initial size 65,536), a `ValueError: could not broadcast input array from shape (72900,) into shape (65536,)` was raised.
- Red run on commit 32c8a86 (new test `test_grid_scene_buffer_resize_after_flush`):
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py -k test_grid_scene_buffer_resize_after_flush -q -p no:cacheprovider )
F                                                                        [100%]
================================== FAILURES ===================================
__________________ test_grid_scene_buffer_resize_after_flush __________________
...
>           buf_v[buf_pos : buf_pos + k] = e_cands
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E           ValueError: could not broadcast input array from shape (72900,) into shape (65536,)

engine\topo\adjacency.py:294: ValueError
=========================== short test summary info ===========================
FAILED engine/tests/test_t_vertex_search.py::test_grid_scene_buffer_resize_after_flush
1 failed, 23 deselected in 0.99s
```
- Fix: In `engine/topo/adjacency.py`, after the flush and single-edge slice loop, check `if k > len(buf_e):` and resize both buffers to `min(chunk_pairs, max(k, len(buf_e) * 2))`.
- Green run:
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py -k test_grid_scene_buffer_resize_after_flush -q -p no:cacheprovider )
.                                                                        [100%]
1 passed, 23 deselected in 2.32s
```

### Note 2: Oracle-equality test with chunk_pairs=2 exercising per-edge slicing
- Finding: The branch at `adjacency.py:282-291` (`if k > chunk_pairs:`) was not executed by tests where chunk size exceeded any single edge's candidate count.
- Added `test_oracle_equality_with_chunk_pairs_2` in `engine/tests/test_t_vertex_search.py`.
- Verified that lines in `adjacency.py:282-291` are executed, `stats["pairs_peak"] <= 2`, and output exactly equals oracle:
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py -k test_oracle_equality_with_chunk_pairs_2 -q -p no:cacheprovider )
.                                                                        [100%]
1 passed, 24 deselected in 0.58s
```

### Note 3: Vertices on diagonal edge for fallback comparison against oracle
- Finding: `test_long_diagonal_edge_uses_full_scan_fallback` had 0 T-vertices along the diagonal edge, so fallback hits were never verified against oracle hits.
- Fix: Placed 3 vertices along the diagonal segment at fractional coordinates (0.25, 0.5, 0.75) with attached geometry.
- Asserted `assert len(ref.get(diag_edge, [])) == 3` and `assert np.array_equal(ref[diag_edge], res[diag_edge])`.
- Green run:
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py -k test_long_diagonal_edge_uses_full_scan_fallback -q -p no:cacheprovider )
.                                                                        [100%]
1 passed, 24 deselected in 0.41s
```

### Note 4: Validate chunk_pairs >= 1 and remove unreachable count==0 branch
- Finding: `adjacency.py:188-189` (`if count == 0: return`) was unreachable dead code. Invalid `chunk_pairs < 1` gave unhandled numpy or range errors instead of a clean `ValueError`.
- Red run before fix on parameterized test `test_chunk_pairs_validation` ([0, -1, -100]):
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py -k test_chunk_pairs_validation -q -p no:cacheprovider )
FFF                                                                      [100%]
================================== FAILURES ===================================
FAILED engine/tests/test_t_vertex_search.py::test_chunk_pairs_validation[0]
FAILED engine/tests/test_t_vertex_search.py::test_chunk_pairs_validation[-1]
FAILED engine/tests/test_t_vertex_search.py::test_chunk_pairs_validation[-100]
3 failed, 25 deselected in 0.33s
```
- Fix: Added `if chunk_pairs < 1: raise ValueError(f"chunk_pairs must be >= 1, got {chunk_pairs}")` at start of `find_t_vertices`. Removed `if count == 0: return` from `eval_chunk`.
- Green run:
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py -k test_chunk_pairs_validation -q -p no:cacheprovider )
...                                                                      [100%]
3 passed, 25 deselected in 0.22s
```

---

## Acceptance command outputs

### 1. Pytest t-vertex search and topo basics
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" "$PY" -m pytest engine/tests/test_t_vertex_search.py engine/tests/test_topo_basics.py -q -p no:cacheprovider )
......................................                                   [100%]
38 passed in 5.53s
```

### 2. Full engine test suite
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
........................................................................ [  8%]
........................................................................ [ 17%]
........................................................................ [ 25%]
........................................................................ [ 34%]
........................................................................ [ 42%]
........................................................................ [ 51%]
........................................................................ [ 59%]
........................................................................ [ 68%]
........................................................................ [ 76%]
........................................................................ [ 85%]
........................................................................ [ 93%]
........x...........................................                     [100%]
843 passed, 1 xfailed in 720.55s (0:12:00)
```

### 3. Acceptance script on the three smaller snapshots
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" "$PY" docs/superpowers/records/scripts/tvertex_check.py "D:/PROJECTS/UC MODEL FIXER/data/snapshots/ce26e0392ab0" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/0b290ec0bcb4" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/c0c877002500-b7c2dc01" )
CHTM_SIDE_WALK_2nd_floor: tris 4692 edges 6001 vertices 1586 tol 0.15 t-junction edges 406 identical True pairs_tested 53308 (reference 9517586) old 0.41 s new 0.031 s speed-up 13.3x
CHTM_2nd_to_3rd_building_sidewalk_outside: tris 7227 edges 9852 vertices 2800 tol 0.15 t-junction edges 408 identical True pairs_tested 98805 (reference 27585600) old 0.97 s new 0.046 s speed-up 20.9x
chtm_5ft_floor: tris 20599 edges 26856 vertices 6457 tol 0.15 t-junction edges 3791 identical True pairs_tested 522061 (reference 173409192) old 6.00 s new 0.195 s speed-up 30.8x
```

## Unsure about
Nothing. All 38 T-vertex search and topo basics tests pass. All 4 review notes have been resolved test-first and verified. The full engine test suite passes (843 passed, 1 xfailed). `tvertex_check.py` on the three smaller snapshots confirms `identical True` across all three with 13.3x, 20.9x, and 30.8x speed-ups over the oracle reference.
