### Task 15: open edges are the truly open ones (added 2026-09-26, found while measuring for the Errors page)

`find_errors` calls an edge open when the edge table counts one face on it (`topo.table.counts == 1`).
That also catches edges covered through a T-junction, where a long edge on one side meets two short
edges on the other: each is used by one face, but no hole is there. They are already shown as the
cyan crack points.
- On CHTM 5th floor, 3,074 "open edges" are 346 truly open edges (edge class 2) plus 2,678
  T-junction edges (class 4), measured.
- The green layer would show about 2,700 false holes.
- The dashboard's own edge overlay already uses the edge classes; this aligns the filter with it.

**Files:**
- Modify: `engine/detectors/errors.py` (the `open_rows` line)
- Test: `engine/tests/test_errors.py` (append)

- [ ] **Step 1: Write the failing test** (append)

```python
def test_edges_covered_through_a_t_junction_are_not_open():
    e = find_errors(t_junction_strip(), PROFILE)
    assert e["counts"]["open_edges"] == 7            # the strip's outline only
    assert all(not (abs(s[1] - 10.0) < 1e-6 and abs(s[4] - 10.0) < 1e-6) for s in e["open_edges"])  # none on the T line y = 10
    assert e["counts"]["cracks"] == 1                # the T-junction itself stays a crack point
```

- [ ] **Step 2: Run it and see it fail**

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_errors.py -q -p no:cacheprovider`
Expected: FAIL with `10 != 7`. The long edge and its two short halves on y = 10 are counted today.

- [ ] **Step 3: Implement.** In `engine/detectors/errors.py`:
  - import `EDGE_OPEN` from `engine.topo.edges`;
  - replace `open_rows = np.nonzero(topo.table.counts == 1)[0]` with
    `open_rows = np.nonzero(np.asarray(topo.edge_class) == EDGE_OPEN)[0]`.

  `topo.edge_class` has one entry per row of `topo.table.edges`: both have 14 rows on `t_junction_strip`
  (measured).

- [ ] **Step 4: Run the errors, CLI and pipeline tests, then CHTM 5th floor**

Run: `.venv/Scripts/python.exe -m pytest engine/tests/test_errors.py engine/tests/test_cli.py -q -p no:cacheprovider`
Expected: all pass. The square keeps its 4 open edges.

Then run
`.venv/Scripts/python.exe -m engine.cli errors "D:/PROJECTS/UC MODEL FIXER/data/snapshots/c0c877002500-b7c2dc01" --out <short temp dir>/chtm5.json`.
Expected: `open_edges` is about 346, not 3,074. Record the number in the commit body.

- [ ] **Step 5: Commit**

```bash
git add engine/detectors/errors.py engine/tests/test_errors.py
git commit -m "fix(engine): find_errors' open edges are edge class 2, not every one-face edge" -m "A T-junction's long and short edges each have one face but no hole; CHTM 5th floor: <measured> open edges instead of 3,074." -m "Co-Authored-By: <your model> <noreply@anthropic.com>"
```

## Order

Tasks run in this order: **1, 2, 3, 4, 5, 6, 12, 14, 15, 8, 7, 9, 10, 13, 11**.
- Task 8 comes before Task 7, because Task 7 imports Task 8's `ErrorsFile` type.
- Task 3 comes before Task 4 Step 5, which measures the whole building.

The profiling script used in Task 3 Step 5 is
`C:/Users/Future26/AppData/Local/Temp/claude/D--PROJECTS-UC-MODEL-FIXER/5472478e-978d-426b-bab2-e7cf21699a70/scratchpad/profile_double_layers.py`.
Copy it into `docs/superpowers/records/scripts/profile_double_layers.py` in Task 3 so the
measurement can be repeated.
