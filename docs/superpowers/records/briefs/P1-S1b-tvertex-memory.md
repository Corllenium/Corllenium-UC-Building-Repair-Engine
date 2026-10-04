# Brief P1-S1b — bound the T-junction search's memory, plus small clean-ups (P1-S1 follow-up)

Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal
P1-S1's review passed. Its one Important finding: `engine/topo/adjacency.py::find_t_vertices` builds every
(edge, candidate) pair in unbounded Python lists, and only the evaluation is chunked. Memory grows about
37 B per pair: 522 MB on the 142,234-triangle unit (5.2 M pairs), and about 4 GB at 100 M pairs. The brief
asked for numpy pairs, evaluated in chunks of about 1 M, so that memory stays bounded. Answers must stay
exactly the oracle's. Spec §5.

## Base, branch, merge
- Base `feat/repair-p0` (it holds P1-S1). Branch `hermes/P1-S1b`, worktree `.hermes/worktrees/P1-S1b`. Claude merges.

## Items
### Item 1 — bounded pair generation
- **Test first** (a new test in `engine/tests/test_t_vertex_search.py`, appended; existing tests unchanged).
  On a dense synthetic scene, `stats` must report `pairs_peak` (the most pairs held at once), at most
  `chunk_pairs`. The answer with `chunk_pairs=1000` must equal the default's and the oracle's. Add
  `chunk_pairs: int = 1_000_000` as a keyword-only argument. See the test fail.
- Build the candidate pairs per block of edges with numpy (no per-pair Python lists), and evaluate each block
  at once.
- **Done when:**
  - the new test and all 31 existing tests pass;
  - `tracemalloc` peak on the 142,234-triangle unit (`data/snapshots/85f36d8cfe0e-ea7edc71`) is lower than
    P1-S1's 522 MB (paste both);
  - `tvertex_check.py` is still `identical True` on A, B and CHTM 5th, with a speed-up ≥ 10× on CHTM 5th.

### Item 2 — small clean-ups from the review
- Add a docstring to the production `find_t_vertices` (what it returns, `stats`, `chunk_pairs`).
- Remove the dead branch near the candidate set (P1-S1's `adjacency.py:118-122`).
- When an edge's padded box would visit more cells than there are candidates, test it against all candidates
  instead. Long 3-D diagonals then cost no more than the old loop. Add a test with a long diagonal across a
  dense scene: its answer equals the oracle's, and `stats` shows the fallback was used (for example
  `stats["full_scan_edges"] >= 1`).

## Acceptance commands
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_t_vertex_search.py engine/tests/test_topo_basics.py -q -p no:cacheprovider )
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S1b" && PYTHONPATH="$PWD" "$PY" docs/superpowers/records/scripts/tvertex_check.py "D:/PROJECTS/UC MODEL FIXER/data/snapshots/ce26e0392ab0" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/0b290ec0bcb4" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/c0c877002500-b7c2dc01" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/85f36d8cfe0e-ea7edc71" )
```
Expected:
- green;
- `identical True` four times. The 142,234-triangle unit's reference run takes about 15 minutes; run it once.

## Rules for this job
- Change only `engine/topo/adjacency.py` and append tests to `engine/tests/test_t_vertex_search.py`. Never change
  `find_t_vertices_reference`, existing tests or `tvertex_check.py`.
- Never amend; copy hashes from `git log --oneline` after your last code commit.

## Report
- Write `docs/superpowers/records/hermes/P1-S1b-report.md` with real output.
- Commit with `Hermes-Job: P1-S1b`.
- Hand in: `tools/jobs.py done P1-S1b --branch hermes/P1-S1b`.
