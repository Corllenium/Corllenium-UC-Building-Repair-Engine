# Brief P1-S3b — double_layers: numpy candidate index, bounded memory, tie re-check (P1-S3 follow-up)

Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal
P1-S3 made `engine/fixes/overlap.py::double_layers` exact and 3.2-3.4x faster. It missed two targets: 5x on the
91,714-face unit (it got 3.2x), and peak memory no higher than the old function's (1,250 MB against 668 MB). The
review and Claude's profile found why.
- **Profile** (cProfile, 179 s on the 91,714-face unit): `set.update` takes 97 s (163,702 calls; the candidate-pair dedupe in
  a Python set), plus 26 s of Python loops, `tolist` 10 s, `triu_indices` 12 s per cell, and `dict.setdefault` 4 s.
- **Memory:** a Python set of 10.76 M pairs (about 0.88 GB) and a dict-of-lists grid of 6.0 M entries (about 0.27 GB). One face
  spans 56,166 cells. The 142,234-face unit peaks at 1.79 GB.
- **Ties:** the new dot and separation sums differ from the oracle's `@` in the last bit. A pair exactly `depth_tol`
  apart flips in 9 of 150 synthetic tie scenes. On real data, 18 pairs lie within 1e-9 of `depth_tol` and none flips.

Results must stay exactly the oracle's. Spec §5.

## Base, branch, merge
- Base `feat/repair-p0` (it holds P1-S3). Branch `hermes/P1-S3b`, worktree `.hermes/worktrees/P1-S3b`. Claude merges.

## Items, each test first
### Item 1 — a numpy candidate index, no Python set
- **Index.** Build the (face, cell) entries with numpy over the faces' padded boxes. Faces that span more than about 64
  cells go in a separate "big" list, tested against candidates with a vectorised box test instead of being stamped into
  cells.
- **Pairs.** Make each pair from exactly one canonical cell (for example the cell of the component-wise max of the two
  faces' lower cells), so no dedupe is needed. Process the pairs in blocks of at most 2 M, with no Python set or
  dict-of-lists.
- **Per-pair stages.** Run the separation test, the 2D box pre-filter and shapely per block, at most 200 k pairs at a time.
  Then sort the survivors by (i, j) before plane clustering, exactly as now.
- **Tests:**
  - a dense cell (a 2,000-face fan, about 2 M pairs) gives the oracle's answer;
  - one giant face spanning more than 10,000 cells next to small faces gives the oracle's answer, and `stats` shows it
    took the big-face path;
  - a new `stats["pairs_peak"]` stays at or under the block size.

### Item 2 — the exact tie re-check, and guard bands
- Re-evaluate, with the oracle's own expressions (`@`), every candidate whose separation lies within 1e-9 of `depth_tol`,
  whose `|n·m|` lies within 1e-12 of `PLANE_PARALLEL_DOT`, or whose box area lies within 1e-9 of `min_area`.
- **Test:** the reviewer's tie scene, `tie_repro.py` in the review notes (two skew-plane faces exactly `depth_tol` apart),
  equals the oracle.

### Item 3 — the pixel stage really bounded
- Default `chunk_rows` about 200 k. Chunk the (pixel, partner) expansion itself, not only its evaluation.
- Restore the docstring's return contract (the oracle's text).

## Acceptance commands
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S3b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_double_layers_speed.py engine/tests/test_overlap.py -q -p no:cacheprovider )
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S3b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
```

**Do NOT run `double_layers_check.py`.** Its tracemalloc pass on the old function is far too slow on big units, and two earlier
runs hit the 2-hour limit on it. Instead:
- time and digest the NEW function only, each call in its own process, on the four units:
  `D:/PROJECTS/UC MODEL FIXER/data/snapshots/{ce26e0392ab0, 0b290ec0bcb4, c0c877002500-b7c2dc01, 9e8182eb174a-d762457f}`;
- compare each digest (sha256 of `json.dumps(result, sort_keys=True)`) with the old function's digests in
  `D:/PROJECTS/UC MODEL FIXER/data/s3_check/controller_calls.out` (one JSON line per call, the `old` rows);
- report the peak working set and time per call.

Expected:
- every digest equals the old one;
- the 91,714-face unit takes ≤ 108 s (5x of the old 543 s) with a peak ≤ 668 MB;
- CHTM 5th is no slower than P1-S3's 10.1 s, with a peak ≤ 477 MB.

## Rules for this job
- Change only `engine/fixes/overlap.py` and append tests to `engine/tests/test_double_layers_speed.py`. Never change
  `double_layers_reference`, existing tests or the scripts.
- Commit after each item (never amend); copy hashes from `git log --oneline` after your last code commit. If a target
  is missed, say so plainly in the report, with the numbers.

## Report
- Write `docs/superpowers/records/hermes/P1-S3b-report.md` with real output for every claim. Name in the report
  what you are unsure about.
- Commit with `Hermes-Job: P1-S3b`.
- Hand in: `tools/jobs.py done P1-S3b --branch hermes/P1-S3b`.
