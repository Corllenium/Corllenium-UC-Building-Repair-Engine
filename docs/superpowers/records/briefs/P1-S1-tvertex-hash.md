# Brief P1-S1 — a near-linear T-junction search, with exactly the old answers

Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal
`engine/topo/adjacency.py::find_t_vertices` tests every edge against every vertex. On CHTM 5th it was
19 % of the 103 s `find_errors` profile (two calls), and it grows with the square of a unit's size. The
census of every building (the owner's first priority: every floor's error map before any fix) would time
out on the 92-142 k-triangle units. Replace the search with a numpy spatial hash that gives **exactly the
same answers**. This is plan `docs/superpowers/plans/2026-10-03-repair-engine-p1-p2.md`, task S1; spec §5.

## Base, branch, merge
- Base: **`claude/P1-S1-tests`**, which holds Claude's failing tests and the acceptance script (commit
  7ff3a4c, on top of `feat/repair-p0`).
- Your branch: `hermes/P1-S1`, worktree `.hermes/worktrees/P1-S1`:
  `git -C "D:/PROJECTS/UC MODEL FIXER" worktree add -b hermes/P1-S1 ".hermes/worktrees/P1-S1" claude/P1-S1-tests`
- Claude merges it into `feat/repair-p0` after review.

## Files
- Modify: `engine/topo/adjacency.py` only.
- Read only, **never change**: `engine/tests/test_t_vertex_search.py` (21 tests) and
  `docs/superpowers/records/scripts/tvertex_check.py`.
- Inputs (read only, in the main checkout): `D:/PROJECTS/UC MODEL FIXER/data/snapshots/ce26e0392ab0`
  (sidewalk A), `.../0b290ec0bcb4` (sidewalk B), `.../c0c877002500-b7c2dc01` (CHTM 5th floor).
- Scratch output: `D:/PROJECTS/UC MODEL FIXER/data/s1_check/` only.

## Interfaces
- `find_t_vertices_reference(positions_w, table, tol, face_w=None, degenerate=None) -> dict[int, np.ndarray]`:
  today's `find_t_vertices`, body verbatim, renamed. Its docstring says it is the test oracle and must not
  change.
- `find_t_vertices(positions_w, table, tol, face_w=None, degenerate=None, stats=None) -> dict[int, np.ndarray]`:
  the new search, used by every caller unchanged (`engine/pipeline.py`, `engine/fixes/merge.py`,
  `engine/detectors/fragments.py`). When `stats` is a dict it sets `stats["pairs_tested"]`: the number of
  (edge, candidate vertex) pairs whose distance the geometric search computed. Hints are not counted.
- The answer is exactly the old one: the same keys (Python `int` edge indices), and per key an `int64` array
  of the same vertex ids in the same order.

## Items

### Item 0 — baseline, before you change anything
- In your worktree, on the base commit, run (in a subshell, `PYTHONPATH=$PWD`, BLAS threads 1):
  ```bash
  OUT="D:/PROJECTS/UC MODEL FIXER/data/s1_check/before"
  "$PY" -m engine.cli errors "D:/PROJECTS/UC MODEL FIXER/data/snapshots/c0c877002500-b7c2dc01" --out "$OUT/chtm5_errors.json"
  "$PY" -m engine.cli fix "D:/PROJECTS/UC MODEL FIXER/data/snapshots/ce26e0392ab0" --no-skp --skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch" --out "$OUT/A"
  "$PY" -m engine.cli fix "D:/PROJECTS/UC MODEL FIXER/data/snapshots/0b290ec0bcb4" --no-skp --skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch" --out "$OUT/B"
  ```
  Record the sha256 of `chtm5_errors.json` and of both `report.json` files.
- Run `engine/tests/test_t_vertex_search.py` and paste the collection error (the oracle does not exist yet).
- **Done when:** the three hashes and the red run are in the report.

### Item 1 — the oracle
- Rename today's function to `find_t_vertices_reference` (body verbatim) and add the new
  `find_t_vertices` with the signature above.
- The new search, numpy only: **no new dependency** (scipy is not installed and must not be added).
  - Hash the candidate vertices (`np.unique(table.edges)`, exactly the reference's candidates) into a grid.
  - Pick a cell size tied to the typical edge length, never to the longest edge or the scene's extent; the
    tests reject both.
  - For each edge, take the vertices in the cells its bounding box reaches, **padded by `tol` in every
    direction**.
  - Apply exactly the reference's test to those pairs: the same `t` and `d` formulas, `1e-9 < t < 1 - 1e-9`,
    `d <= tol`, not an endpoint.
  - Then the same hint merge and ordering as the reference; share that tail with the reference in a helper
    if you like.
- **Speed:** Claude's throwaway prototype with a Python loop over edges was only 6.4× faster on CHTM 5th
  (4.82 s → 0.75 s), and the target is ≥ 10×. Build the (edge, cell) and (edge, vertex) pairs with numpy, and
  evaluate them in chunks of at most about 1 M pairs, so that memory stays bounded.
- **Done when:** `engine/tests/test_t_vertex_search.py` shows 21 passed, and the existing `test_topo_basics.py`
  still passes.

### Item 2 — nothing else changes
- **Done when:** the full engine suite passes (paste the last line).
- Then the acceptance script prints `identical True` for all three snapshots, with a speed-up of ≥ 10× on
  `chtm_5ft_floor`:
  ```bash
  "$PY" docs/superpowers/records/scripts/tvertex_check.py "D:/PROJECTS/UC MODEL FIXER/data/snapshots/ce26e0392ab0" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/0b290ec0bcb4" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/c0c877002500-b7c2dc01"
  ```
- Then the three Item 0 commands, re-run into `data/s1_check/after`, give **the same three sha256** as before.
- Paste the times of the `errors` run before and after.

## Acceptance commands
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py engine/tests/test_topo_basics.py -q -p no:cacheprovider )
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1" && PYTHONPATH="$PWD" "$PY" docs/superpowers/records/scripts/tvertex_check.py <the three snapshot dirs> )
```
Expected:
- 21 + the topo tests passed, and the engine suite green;
- `identical True` three times, CHTM 5th ≥ 10×;
- before and after sha256 equal for `chtm5_errors.json`, `A/.../report.json` and `B/.../report.json`.

## Rules for this job
- Change only `engine/topo/adjacency.py`. Never change the tests, the script, `engine/guard/**` or
  `FixProfile`.
- Every real-data run writes under `data/s1_check/` with `--no-skp --skp-dir data/skp_scratch`; never
  `OBJ FIXED RESULT/`.
- Commit when Item 1's tests pass, before the full suite, so a time limit cannot lose the work.

## Report
- Write `docs/superpowers/records/hermes/P1-S1-report.md` (format: `../hermes/README.md`), with real
  output for every claim.
- Commit with `Hermes-Job: P1-S1`.
- Hand in: `tools/jobs.py done P1-S1 --branch hermes/P1-S1`.
