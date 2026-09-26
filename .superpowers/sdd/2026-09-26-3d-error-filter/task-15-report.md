# Task 15: Open Edges Are Edge Class 2 — Report

**Status:** SUCCESS

**SHA:** `f0116a6`

**Files Modified:**
- `engine/detectors/errors.py` (+1, -1): Import `EDGE_OPEN` from `engine.topo.edges`; replace `open_rows = np.nonzero(topo.table.counts == 1)[0]` with `open_rows = np.nonzero(np.asarray(topo.edge_class) == EDGE_OPEN)[0]`.
- `engine/tests/test_errors.py` (+4, -0): Append new test `test_edges_covered_through_a_t_junction_are_not_open` verifying 7 open edges on `t_junction_strip`, none on the T line y = 10, and 1 crack.

**Test Results:**
```
70 passed in 84.58s (0:01:24)
```

All tests pass, including:
- `test_edges_covered_through_a_t_junction_are_not_open`: Verifies `t_junction_strip()` has 7 open edges (the outline only), none on the T line y = 10, and 1 T-junction crack point.
- `test_a_flat_square_has_four_open_edges`: Continues to pass (square's 4 edges unchanged).
- All 68 existing tests continue to pass.

**CHTM 5th Floor Measurement:**
```
chtm_5ft_floor: open_edges 346
```
Down from 3,074 false positives (the 2,678 T-junction edges are no longer counted as open).

**Implementation Details:**
- Import `EDGE_OPEN = 2` from `engine.topo.edges` (line 19)
- `open_rows = np.nonzero(np.asarray(topo.edge_class) == EDGE_OPEN)[0]` filters edges by class instead of count (line 74)
- `topo.edge_class` has one entry per row of `topo.table.edges` (verified: 14 rows on `t_junction_strip`)
- T-junction edges (class 4) are no longer counted as open; they are shown as crack points instead

**Concerns:** None. The implementation follows the brief exactly. The test shows the expected 7 outline edges on `t_junction_strip` (none on the T line y = 10), the T-junction is counted as 1 crack, and CHTM 5th floor reports 346 truly open edges instead of 3,074 false positives.
