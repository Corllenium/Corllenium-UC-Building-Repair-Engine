# Brief P1-S3 — a sub-quadratic `double_layers`, with exactly the old result

Rules: [`AGENTS.md`](../../../../AGENTS.md); they always apply.

## Goal
`engine/fixes/overlap.py::double_layers` finds every pair of faces drawn twice in one plane (the
flicker the owner sees in Unity). It was 61 % of the 103 s `find_errors` profile on CHTM 5th. Its own
profile there (35 s):
- most of the time is per-pair Python: 117,259 candidate pairs each pay `np.cross`/`plane_basis` plus one
  shapely intersection, and 13,947 survive;
- the all-against-all bounding-box test (about 9 s) grows with the square of a unit's size;
- the 26 renders take 3.8 s.

The census of every building (the owner's first priority: every floor's error map before any fix) would
time out on the 92-142 k-triangle units. Make it sub-quadratic and fast, with **exactly the same result**.
This is plan `docs/superpowers/plans/2026-10-03-repair-engine-p1-p2.md`, task S3; spec §5.

**Ruling on the plan's method:** the plan said "group candidate pairs by fitted plane". Do not bucket by plane
offset (n · p). Faces with a small tilt far from the origin share the depth band locally while their offsets
differ by many inches, so the oracle finds pairs that offset buckets miss. The tests include that case. Search
by position: a uniform grid over the faces' padded bounding boxes, then the parallel test, works (Claude's
throwaway prototype passes every test).

## Base, branch, merge
- Base: **`claude/P1-S3-tests`**, which holds Claude's failing tests and the acceptance script (commit
  2b9b0a4, on `feat/repair-p0`).
- Your branch: `hermes/P1-S3`, worktree `.hermes/worktrees/P1-S3`:
  `git -C "D:/PROJECTS/UC MODEL FIXER" worktree add -b hermes/P1-S3 ".hermes/worktrees/P1-S3" claude/P1-S3-tests`
- Claude merges it into `feat/repair-p0` after review.

## Files
- Modify: `engine/fixes/overlap.py` only.
- Read only, **never change**: `engine/tests/test_double_layers_speed.py` (19 tests) and
  `docs/superpowers/records/scripts/double_layers_check.py`.
- Inputs (read only, in the main checkout): `D:/PROJECTS/UC MODEL FIXER/data/snapshots/`, namely
  `ce26e0392ab0` (sidewalk A), `0b290ec0bcb4` (sidewalk B), `c0c877002500-b7c2dc01` (CHTM 5th) and
  `9e8182eb174a-d762457f` (91,714 triangles, the second-largest unit).
- Scratch output: `D:/PROJECTS/UC MODEL FIXER/data/s3_check/` only.

## Interfaces
- `double_layers_reference(...)`: today's `double_layers`, body verbatim, renamed. Its docstring says it is
  the test oracle and must not change.
- `double_layers(positions_c, faces, depth_tol, views=None, size=(900, 600), caster_factory=EmbreeCaster,
  min_area=DOUBLE_LAYER_MIN_AREA, centre=None, *, stats=None, chunk_rows=1_000_000) -> dict`: the new
  function, used by every caller unchanged (`engine/detectors/errors.py`, `engine/fixes/pipeline.py`).
  - `stats` receives `bbox_pairs` (distinct face pairs i < j whose boxes the search compared), `pairs_tested`
    (candidates that reached the separation and area tests) and `pixel_rows_max` (the largest
    (pixel, partner) batch the pixel stage evaluated at once).
  - `chunk_rows` caps that batch. A pixel whose rows fall in different chunks still counts once.
- The result dict equals the reference's: `count`, `area`, `px`, every plane in order with every field, and
  `pair_list`.

## What must stay exactly as the oracle does it
- The same candidate rule:
  - boxes padded by `depth_tol` overlap;
  - `|n · m| > PLANE_PARALLEL_DOT`;
  - the same separation test (`sep <= depth_tol`);
  - the same shared-area test (`shared > min_area`), with each pair's polygons projected on
    `plane_basis(normal[i])` from `tri[i][0]`.
- **The pairs are taken in ascending (i, j) order.** Each pair joins the first plane, in creation order, within
  tolerance; when planes chain, the order decides the planes (a test checks this).
- The pixel stage keeps its Moller-Trumbore test and `eps`. It only evaluates in chunks of at most
  `chunk_rows` rows.

## Items

### Item 0 — baseline, before you change anything
- In your worktree, on the base commit (in a subshell, `PYTHONPATH=$PWD`, BLAS threads 1):
  ```bash
  OUT="D:/PROJECTS/UC MODEL FIXER/data/s3_check/before"
  "$PY" -m engine.cli errors "D:/PROJECTS/UC MODEL FIXER/data/snapshots/c0c877002500-b7c2dc01" --out "$OUT/chtm5_errors.json"
  "$PY" -m engine.cli fix "D:/PROJECTS/UC MODEL FIXER/data/snapshots/ce26e0392ab0" --no-skp --skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch" --out "$OUT/A"
  "$PY" -m engine.cli fix "D:/PROJECTS/UC MODEL FIXER/data/snapshots/0b290ec0bcb4" --no-skp --skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch" --out "$OUT/B"
  ```
  Record the sha256 of `chtm5_errors.json` and of both `report.json` files, and the `errors` run's time.
- Run `engine/tests/test_double_layers_speed.py` and paste the collection error (the oracle does not exist
  yet).

### Item 1 — the oracle and the new search
- Rename today's function to `double_layers_reference` (body verbatim). Add the new `double_layers` with the
  signature above, numpy and shapely only: **no new dependency** (scipy is not installed and must not be
  added).
- **Candidates:** a uniform grid over the padded boxes, with the cell size tied to the typical face size, never
  to the largest face or the scene. Count the distinct pairs compared, then apply the box and parallel tests
  vectorised.
- **Per-pair stage, vectorised:** this is where the time goes. Do the separation test for all candidates at
  once. Compute `plane_basis` for every pair with the same arithmetic. Build the polygons with
  `shapely.polygons` on arrays, and call `shapely.intersection` and `shapely.area` on arrays, not once per
  pair. Keep (i, j) order.
- **Pixel stage:** evaluate the (pixel, partner) rows in chunks of at most `chunk_rows`, marking each pixel met
  in a boolean array per view, so a pixel counts once.
- **Done when:** `engine/tests/test_double_layers_speed.py` shows 19 passed, and the existing `test_overlap.py`
  still passes.

### Item 2 — nothing else changes, and it is faster
- The full engine suite passes; paste the last line.
- The acceptance script prints `equal True` for all four snapshots, with these targets:
  - speed-up ≥ 3× on `chtm_5ft_floor` and ≥ 5× on the 91,714-triangle unit;
  - `peak MB new` ≤ `peak MB old` on both:
  ```bash
  "$PY" docs/superpowers/records/scripts/double_layers_check.py "D:/PROJECTS/UC MODEL FIXER/data/snapshots/ce26e0392ab0" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/0b290ec0bcb4" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/c0c877002500-b7c2dc01" "D:/PROJECTS/UC MODEL FIXER/data/snapshots/9e8182eb174a-d762457f"
  ```
  (The old function needs several minutes on the 91,714-triangle unit; that is expected.)
- The three Item 0 commands, re-run into `data/s3_check/after`, give **the same three sha256**; paste the
  `errors` run's time before and after.

## Acceptance commands
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S3" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_double_layers_speed.py engine/tests/test_overlap.py -q -p no:cacheprovider )
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S3" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests -q -p no:cacheprovider )
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P1-S3" && PYTHONPATH="$PWD" "$PY" docs/superpowers/records/scripts/double_layers_check.py <the four snapshot dirs> )
```
Expected:
- 19 + the overlap tests pass, and the engine suite is green;
- `equal True` four times, CHTM 5th ≥ 3× and the 91,714-triangle unit ≥ 5×, with new peaks ≤ old;
- before and after sha256 equal.

## Rules for this job
- Change only `engine/fixes/overlap.py`. Never change the tests, the script, `engine/guard/**` or `FixProfile`.
- Every real-data run writes under `data/s3_check/` with `--no-skp --skp-dir data/skp_scratch`; never
  `OBJ FIXED RESULT/`.
- Commit when Item 1's tests pass, before the full suite, so a time limit cannot lose the work.
- Another Hermes run may be doing P1-S1 (`engine/topo/adjacency.py`) at the same time. Never touch its
  worktree.

## Report
- Write `docs/superpowers/records/hermes/P1-S3-report.md` (format: `../hermes/README.md`), with real
  output for every claim.
- Commit with `Hermes-Job: P1-S3`.
- Hand in: `tools/jobs.py done P1-S3 --branch hermes/P1-S3`.
