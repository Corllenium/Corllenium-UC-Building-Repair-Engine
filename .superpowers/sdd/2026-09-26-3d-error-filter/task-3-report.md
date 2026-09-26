# Task 3 Report: `double_layers`' visible-pixel count, fast enough for a building

## Status: DONE_WITH_CONCERNS

## Summary

Replaced the pixel-counting stage of `double_layers` (`engine/fixes/overlap.py`). It no longer asks
`EmbreeCaster.all_hits` for every surface along every pixel's ray; instead, for each pixel it tests
only its first-hit face's own flicker partners, with a vectorized Moller-Trumbore ray-triangle test.
Measured on the CHTM 5th floor slice used by the brief: **342.4 s -> 19.5 s** (14-17x), same 6376
pairs. Two of the three exact-pixel-equality tests now disagree by a handful of pixels (1 and 3
respectively) at rays that graze exactly along a partner triangle's edge -- see Concerns. Per the
brief's explicit instruction, I did not loosen those tests; the discrepancy is documented below,
root-caused, and left for a human/plan decision.

## Implementation

### Files changed
- **`engine/fixes/overlap.py`** (modified): `double_layers`'s pixel stage, replacing the block from
  `ids_all = np.arange(len(faces), dtype=np.int64)` through the end of the `for view in views:` loop.
  The old code built its own `EmbreeCaster` and called `.all_hits(origins, directions)` once per
  view (asking for every surface along every ray); the new code builds CSR arrays (`ptr`/`idx`) over
  each face's flicker partners, expands every (pixel, partner) row for the pixels whose first hit is
  a watched face, and runs a fully vectorized Moller-Trumbore test of the ray against only that
  partner triangle, gated by `depth_tol` around the first hit's own depth. Signature and output keys
  are unchanged.
- **`engine/tests/test_overlap.py`** (modified, appended): `_reference_px` (the old all-surfaces
  method, kept as a reference oracle), `test_double_layers_counts_the_same_pixels_as_every_surface_along_the_ray`
  (parametrized over `back_to_back_pair`, `split_double_layer`, `two_sided_wall`), and
  `test_double_layers_no_longer_asks_the_caster_for_every_surface`. Both copied verbatim from the
  brief.
- **`docs/superpowers/records/scripts/profile_double_layers.py`** (new): copied verbatim from the
  brief's scratchpad script, for the Step 5 measurement and for future re-profiling.

Code was used exactly as given in the brief's Step 3 -- no deviation, including the `eps = 1e-6`
Moller-Trumbore boundary slack that turns out to matter (see Concerns).

## TDD Evidence

### RED

```
cd 'D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter' && PYTHONPATH="$PWD" '/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -m pytest engine/tests/test_overlap.py -k "same_pixels or no_longer_asks" -q -p no:cacheprovider
```
Result: the three `same_pixels` tests PASS (the reference oracle, run against the still-unmodified
implementation, trivially agrees with itself); `no_longer_asks` FAILS exactly as specified:
```
>       overlap.double_layers(pos - pos.mean(axis=0), np.asarray(m.face_v), 0.01)
engine\fixes\overlap.py:514: in double_layers
    ray, hit, t = caster.all_hits(origins, np.tile(direction, (len(origins), 1)))
def forbidden(*a, **k):
>       raise AssertionError("all_hits called")
E       AssertionError: all_hits called
1 failed, 3 passed, 19 deselected in 9.75s
```

### GREEN (mostly)

```
cd 'D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter' && PYTHONPATH="$PWD" '/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -m pytest engine/tests/test_overlap.py -q -p no:cacheprovider
```
Result (reproduced identically across three separate runs, including a final foreground rerun):
```
2 failed, 21 passed in 21.55s
FAILED ...test_double_layers_counts_the_same_pixels_as_every_surface_along_the_ray[back_to_back_pair]
  assert 153027 == 153028
FAILED ...test_double_layers_counts_the_same_pixels_as_every_surface_along_the_ray[split_double_layer]
  assert 102019 == 102022
```
`no_longer_asks` passes (the implementation no longer calls `all_hits` at all). The `two_sided_wall`
parametrization of the equality test -- the fixture closest to the real CHTM defect this task
exists for -- passes with an EXACT match. `back_to_back_pair` and `split_double_layer` are off by 1
and 3 pixels respectively, out of 153028 and 102022. I did not loosen these assertions.

## Root cause of the two mismatches (found and printed, not guessed)

I wrote a diagnostic (`ran from the scratchpad, not committed`) that reproduces both the reference
(`all_hits`-based) and the new (vectorized Moller-Trumbore) computation per pixel, and prints every
pixel where the two disagree. All four mismatched pixels (1 in `back_to_back_pair`, 3 in
`split_double_layer`) are rays whose intersection with the partner triangle lands within a few
millionths of the triangle's OWN edge, i.e. exactly the geometry these two fixtures are built to
exercise ("the shared edge is where both end", "each lies on the others' boundary along its whole
length" -- both fixtures' own docstrings):

- `back_to_back_pair`, view 9, pixel (row=75, col=151): `u=0.505522`, `v=0.494480`,
  `u+v=1.0000016880745495` -- past the far edge `u+v<=1.0+eps` by about `6.9e-7`, with
  `eps=1e-6`. `dt` (depth vs. first hit) is `1.4e-14`, i.e. not a depth issue at all.
- `split_double_layer`, 3 pixels across 2 views: `v` in `[-3.05e-6, -1.14e-6]`, i.e. just past the
  near edge `v>=-eps` by up to `2e-6`, again with `dt` at machine precision.

The new method computes `u,v,t` from `positions_c` in float64. The old method's hit test runs
through `EmbreeCaster`, whose constructor stores vertices as **float32**
(`positions.astype(np.float32)` in `EmbreeCaster.__init__`, `engine/rays/caster.py:56`) -- a
different, coarser copy of exactly the coordinates that define the edge these rays graze. A ray
landing within ~1-2 millionths of a triangle's edge is well inside the gap between float32 and
float64 rounding of a vertex around magnitude 10-40 (float32 ULP there is a few microns), so the
two methods can legitimately disagree about which side of the edge the hit falls on. The brief's
fixed `eps=1e-6` (used verbatim, per Step 3) is the same order of magnitude as that gap, so a
handful of edge-grazing rays land just outside it.

I did not change `eps`, and did not touch the tests. This is a real, understood, narrow boundary
disagreement, not a logic error in the vectorization (confirmed also by: `two_sided_wall` matching
exactly, `count`/`pairs` matching exactly on the real building slice, and `dt` being at machine
precision in every mismatch, ruling out the depth-gating logic as the cause).

## Before / after profile (Step 5)

Script: `docs/superpowers/records/scripts/profile_double_layers.py`, run from the worktree root
against `D:/PROJECTS/UC MODEL FIXER/data/snapshots/c0c877002500-b7c2dc01` (absolute path; `data/`
is not inside the worktree):

```
cd 'D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter' && PYTHONPATH="$PWD" '/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' docs/superpowers/records/scripts/profile_double_layers.py "D:/PROJECTS/UC MODEL FIXER/data/snapshots/c0c877002500-b7c2dc01"
```

- **Before** (measured 2026-09-26, per the brief): `double_layers on the slice: 342.4 s, 6376 pairs, 33934 px`
- **After** (first run, cold, with cProfile attached): `double_layers on the slice: 24.1 s, 6376 pairs, 33918 px`
- **After** (foreground rerun, warm): `double_layers on the slice: 19.5 s, 6376 pairs, 33918 px`

14.2x-17.6x faster depending on run; both comfortably "well under 342 s". The brief's parenthetical
aspiration of "under 20 s" is met on the warm rerun (19.5 s) and very close on the cold one (24.1 s).
`count` (6376 pairs) matches exactly both times -- the pair-search stage is untouched, as intended.
`px` is 33918 both times (deterministic), 16 below the old 33934 (0.047%), consistent with the same
edge-tolerance cause identified above, at the scale of a real 10,057-face slice over 26 views instead
of a 2-7-face fixture.

## Whole engine suite (Step 6)

Two independent runs agree exactly on outcome:

1. A full single-process run (`pytest engine/tests -q -p no:cacheprovider`) completed with:
   `2 failed, 621 passed, 1 xfailed in 4085.78s (1:08:05)`.
2. A foreground rerun, chunked file-by-file/test-by-test to stay under the tool's 10-minute cap
   (17 chunks, `collect-only` confirmed 624 total items both times), reproduced **the identical
   breakdown**: 621 passed, the same 2 `test_overlap.py` failures (the ones described above and no
   others), 1 xfailed (in `test_solidify.py`), across ~400 s of measured pytest execution time.

The two failures are exactly, and only, the pair described above. No other test in the suite
regressed. I flag the wall-clock gap itself as a concern below (not a correctness issue: both runs
agree on every single test's outcome).

## Self-review

- Implementation matches the brief's Step 3 code verbatim; diffed by hand against the brief text.
- `double_layers`'s signature, defaults and output dict keys are unchanged.
- Checked every other caller/test that touches `double_layers` or `caster_factory`
  (`engine/detectors/errors.py`, `engine/fixes/pipeline.py`, `engine/tests/test_guard.py`): all use
  the default `caster_factory=EmbreeCaster`; none stub it to assert `all_hits` is/isn't called, so
  nothing outside `test_overlap.py` depends on the removed code path.
  `engine/tests/test_errors.py` (Task 2, exercises `find_errors` -> `double_layers`) is green.
- `tri = positions_c[faces]`, already computed earlier in `double_layers`, is reused as-is for the
  new Moller-Trumbore test, so it is in the same frame as `buf` per the brief's note.
  `caster = caster_factory(positions_c, faces)` and the `.all_hits(...)` call are gone, exactly as
  specified.
- Reran the profile script twice (cold and warm) and the overlap test file three times; `pairs`,
  `px`, and the specific two failing parametrizations are identical every time -- deterministic.

## Concerns

1. **Two `same_pixels` equality tests fail by a few pixels** (`back_to_back_pair`: 153027 vs 153028;
   `split_double_layer`: 102019 vs 102022), root-caused above to the `eps=1e-6` Moller-Trumbore
   boundary slack (specified verbatim by the brief) landing in the same order of magnitude as the
   float32-vs-float64 vertex precision gap between the new test and `EmbreeCaster`'s internal mesh,
   exactly at rays grazing a partner triangle's own edge. Per the brief's instruction I did not
   loosen these tests or change `eps`. This needs a human/plan decision: whether to accept the
   documented discrepancy, widen `eps` (which would need its own accuracy trade-off analysis), or
   compute the partner triangle geometry in float32 to match `EmbreeCaster` exactly.
2. **`two_sided_wall` -- the fixture modeled directly on the real CHTM defect -- matches exactly**,
   and the real-building slice differs by only 16 px out of 33934 (0.047%), so the practical impact
   on the actual error-filter feature looks small, but I have not verified that against a
   `find_errors`-level acceptance threshold (out of scope for this task).
3. **Whole-suite wall-clock time varied 10x between runs** (4085.78 s single-process vs. ~400 s
   measured when chunked) with byte-for-byte identical pass/fail/xfail results both times, and
   Task 2's report recorded ~437 s for the same suite (fewer tests, before this task). Since this
   task's change can only make `double_layers` faster, and both runs of the FULL suite agree on
   every outcome, I attribute the 4085.78 s figure to transient contention on this shared dev
   machine (per the "shared working tree, multi-session" environment note) rather than to this
   change, but flag it since I can't fully verify what else was running on the machine at the time.
4. The brief's aspirational "target under 20 s" was met on a warm rerun (19.5 s) but not on the
   first cold run with a profiler attached (24.1 s); both clear the actual pass bar ("well under
   342 s") by a wide margin.

## Commit

- **SHA**: 9dd065c
- **Subject**: perf(engine): double_layers tests each pixel against its face's partners, not every surface
- **Files**: `engine/fixes/overlap.py` (modified), `engine/tests/test_overlap.py` (modified),
  `docs/superpowers/records/scripts/profile_double_layers.py` (new)

## Follow-up fix: controller ruling on the concern

The controller reviewed the concern above and ruled (recorded in the ledger): keep the
implementation as-is; change only the equality test. `two_sided_wall` (the fixture closest to the
real CHTM defect) keeps exact equality; `back_to_back_pair` and `split_double_layer` get a narrow,
documented tolerance, since both differ only at rays grazing exactly a partner's edge.

`engine/tests/test_overlap.py`,
`test_double_layers_counts_the_same_pixels_as_every_surface_along_the_ray`, changed to:

```python
    assert d["px"] > 0
    reference = _reference_px(pos - centre, faces, d, 0.01, VIEWS_26, (300, 200))
    if build == "two_sided_wall":
        assert d["px"] == reference
    else:
        # rays grazing exactly a partner's edge: reference is Embree's float32 mesh plus the
        # caster's coincident tolerance, the new count is a float64 barycentric test at eps=1e-6;
        # 1 px of 153028 (back_to_back_pair) and 3 px of 102022 (split_double_layer), measured 2026-09-26
        assert abs(d["px"] - reference) <= max(5, reference * 1e-4)
```

Ran in the foreground:

```
cd 'D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter' && PYTHONPATH="$PWD" '/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -m pytest engine/tests/test_overlap.py -q -p no:cacheprovider
```
```
.......................                                                  [100%]
23 passed in 23.34s
```

```
cd 'D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/error-filter' && PYTHONPATH="$PWD" '/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe' -m pytest engine/tests/test_errors.py -q -p no:cacheprovider
```
```
.......                                                                  [100%]
7 passed in 10.85s
```

All 23 `test_overlap.py` tests pass (previously 21 passed / 2 failed); `test_errors.py`'s 7 tests
are unaffected. Staged `engine/tests/test_overlap.py` by name and committed.

- **SHA**: b2540b8
- **Subject**: test(engine): tolerate a few edge-grazing pixels in double_layers' px equality test
- **Files**: `engine/tests/test_overlap.py` (modified)
