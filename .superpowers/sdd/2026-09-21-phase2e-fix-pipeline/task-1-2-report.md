# Task 1 & 2 implementation report

## Task 1: Ray casters

### What I implemented

- `engine/rays/__init__.py` (empty, package marker).
- `engine/rays/caster.py`:
  - `RayCaster(Protocol)` with `any_hit(origins, directions) -> bool[]` and
    `first_hit(origins, directions) -> (tri int64[-1=miss], t float64[inf=miss])`.
  - `EmbreeCaster(positions, faces)`: builds `trimesh.Trimesh(vertices=positions.astype(np.float32), faces=faces, process=False)`
    and wraps it in `trimesh.ray.ray_pyembree.RayMeshIntersector`. `first_hit` uses
    `intersects_location(..., multiple_hits=False)` and computes `t = (loc - o) . d` per hit ray;
    misses stay `tri=-1`, `t=inf`. Because `process=False`, `tri` indexes into the exact `faces`
    array passed to the constructor (no reindexing/dedup).
  - `BruteCaster(positions, faces)`: Moller-Trumbore ported from `spike/04_front_hit_oracle.py`'s
    `brute()`, generalised from a single shared direction to a per-ray direction. Chunked by 256
    rays, float64 throughout, hit accepted when `t > 1e-9`. `any_hit` reuses `first_hit` and
    checks `tri >= 0`.
  - Module docstring documents the recentring precondition: callers must recentre `positions`
    before constructing a caster (embree stores vertices as float32 internally; the real models'
    coordinates sit near 24,000 inches).
- `engine/tests/test_caster.py`: 4 tests (see below).
- `pyproject.toml`: added `trimesh>=4.5` and `embreex>=4.4` to `[project] dependencies`, then
  ran `.venv/Scripts/python.exe -m pip install -e ".[dev]"` (trimesh 5.1.0 / embreex 4.4.0 were
  already present in the venv; the editable install picked up the new dependency pins).

### TDD evidence

RED — before `engine/rays/caster.py` existed:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_caster.py -q
ImportError while importing test module 'D:\PROJECTS\UC MODEL FIXER\engine\tests\test_caster.py'.
engine\tests\test_caster.py:3: in <module>
    from engine.rays.caster import BruteCaster, EmbreeCaster
E   ModuleNotFoundError: No module named 'engine.rays.caster'
1 error in 0.19s
```
Failure was expected: the module did not exist yet.

GREEN — after implementation:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_caster.py -q
....                                                                     [100%]
4 passed in 0.41s
```

Full suite after Task 1:
```
$ .venv/Scripts/python.exe -m pytest -q
.........................................................                [100%]
57 passed in 0.76s
```
(53 pre-existing + 4 new; re-ran with `-W error::DeprecationWarning` too, still 57 passed, no warnings.)

### Tests written (`engine/tests/test_caster.py`)

1. `test_ray_straight_down_hits_cube_top_at_t_10` — ray from `(5,5,20)` direction `(0,0,-1)`
   against `cube(10.0)` hits at `t=10` for both `EmbreeCaster` and `BruteCaster`.
2. `test_ray_missing_cube_reports_miss` — ray from `(100,100,100)` down misses; `tri==-1`,
   `t==inf`, both casters.
3. `test_any_hit_agrees_with_first_hit_non_negative` — a batch of hit/miss rays: `any_hit()`
   equals `first_hit()[0] >= 0` elementwise, both casters.
4. `test_embree_and_brute_oracle_agree_on_random_rays` — 2,000 rays from
   `np.random.default_rng(7)` (test code only) against `grid_slab(10,10)` stacked with `cube()`
   (positions concatenated, cube face indices offset by the slab's vertex count).
   `EmbreeCaster` vs `BruteCaster`: hit/miss agreement `>= 99.9%` (measured: 100% agreement),
   and `|t_e - t_b| <= 1e-3` for every ray both hit (measured max diff well under tolerance).

### Files changed

- `pyproject.toml` (dependencies)
- `engine/rays/__init__.py` (new)
- `engine/rays/caster.py` (new)
- `engine/tests/test_caster.py` (new)

### Self-review

- `RayCaster` is a `typing.Protocol`, not an ABC — matches "Protocol" in the brief's interface
  section; both `EmbreeCaster` and `BruteCaster` satisfy it structurally.
- `trimesh`/`embreex` imports are confined to `engine/rays/caster.py`; nothing else in `engine/`
  imports them (verified by grep before commit).
- No random numbers in production code — `np.random.default_rng(7)` appears only in the test.
- `BruteCaster` is O(chunk x M) per direction batch; fine for the oracle test size (212 faces x
  2000 rays chunked by 256) and it's documented as an oracle, not a performance path.

### Concerns

None.

## Task 2: Exposure

### What I implemented

- `engine/vis/__init__.py` (empty, package marker).
- `engine/vis/exposure.py`:
  - `fib_dirs(n) -> (n,3)` — Fibonacci-lattice unit directions, ported verbatim from
    `spike/10_ds_visibility.py` / `spike/05_visibility_then_merge.py`.
  - `BARY` — `[[1/3,1/3,1/3], [0.6,0.2,0.2], [0.2,0.6,0.2], [0.2,0.2,0.6]]`, from `spike/05_visibility_then_merge.py`.
  - `EPS_IN = 0.02`.
  - `EXP_DEGENERATE=0`, `EXP_HIDDEN=1`, `EXP_SLIT=2`, `EXP_OUTSIDE=3`.
  - `compute_exposure(positions_c, face_w, ok, caster_factory=EmbreeCaster, n_dirs=128)`: port of
    `escapes_double_sided` from `spike/10_ds_visibility.py`. Computes face normals from
    `positions_c[face_w]` (cross product of the two edge vectors, normalised; zero for
    degenerate/not-ok faces) — NOT from the source file's `vn`. Builds ONE caster via
    `caster_factory(positions_c, face_w[ok])` and reuses it across every direction and side.
    For each of `n_dirs` `fib_dirs` directions `w`: faces with `normal . w > 1e-6` cast 4 rays
    (one per `BARY` sample point) from `sample_point + EPS_IN * normal` along `w`; faces with
    `normal . w < -1e-6` cast from `sample_point - EPS_IN * normal` along `w`. A ray "escapes"
    when `caster.any_hit(...)` is `False`. `exposure = escapes / (n_dirs * 4)`, `0.0` for
    `not ok` faces. Docstring documents the no-recentre precondition (mirrors `engine/rays/caster.py`).
  - `classify_exposure(exposure, ok, slit_threshold=0.05)`: `EXP_DEGENERATE` where `not ok`
    (regardless of the face's exposure value); else `EXP_HIDDEN` (`exposure == 0`), `EXP_SLIT`
    (`0 < exposure < slit_threshold`), `EXP_OUTSIDE` (`exposure >= slit_threshold`).
- `engine/tests/fixtures/build.py` — added two fixtures, appended after the existing ones
  (`cube`, `grid_slab`, `t_junction_strip`, `t_junction_shared_strip` all unchanged):
  - `box_with_partition(size=10.0)`: `cube()`'s 12 tris (indices 0-11) plus one inner quad (2
    tris, indices 12-13) spanning the full interior at `z = size/2`, built with new vertices
    (not welded to the cube's own — welding isn't needed for ray casting; the cube's solid
    walls already seal the interior regardless).
  - `open_box_with_cells(size=10.0, gap=0.2)`: a box with the `y=0` side omitted (the opening)
    and the other 5 sides solid (10 tris, indices 0-9), plus two square inner partitions
    perpendicular to `y`, centred in the x/z cross-section with a `gap` fraction left open all
    around their edges (`near`, indices 10-11, at `y=0.3*size`; `deep`, indices 12-13, at
    `y=0.7*size`, closer to the solid back wall at `y=size`).
- `engine/tests/test_exposure.py`: 8 tests (see below).

### TDD evidence

RED — before `engine/vis/exposure.py` existed (fixtures already added, since they're plain data
with no behaviour to fail on their own):
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_exposure.py -q
ImportError while importing test module 'D:\PROJECTS\UC MODEL FIXER\engine\tests\test_exposure.py'.
engine\tests\test_exposure.py:5: in <module>
    from engine.vis.exposure import (BARY, EPS_IN, EXP_DEGENERATE, EXP_HIDDEN, EXP_OUTSIDE, EXP_SLIT,
E   ModuleNotFoundError: No module named 'engine.vis.exposure'
1 error in 0.19s
```

GREEN — after implementation:
```
$ .venv/Scripts/python.exe -m pytest engine/tests/test_exposure.py -q
........                                                                 [100%]
8 passed in 0.40s
```

Full suite after Task 2:
```
$ .venv/Scripts/python.exe -m pytest -q
.................................................................        [100%]
65 passed in 0.85s
```
(57 pre-existing (after Task 1) + 8 new; re-ran with `-W error::DeprecationWarning`, still 65
passed, no warnings.)

### Tests written (`engine/tests/test_exposure.py`)

1. `test_fib_dirs_returns_n_unit_vectors` — shape `(32,3)`, all unit length.
2. `test_bary_is_centroid_plus_three_biased_corners` — `BARY[0]` is the centroid, the other
   three rows are `(0.6,0.2,0.2)` in some permutation, all rows sum to 1.
3. `test_eps_in_value` — `EPS_IN == 0.02`.
4. `test_compute_exposure_is_deterministic` — same inputs, called twice, identical arrays.
5. `test_box_with_partition_inner_faces_hidden_outer_faces_outside` — partition tris (12,13)
   have `exposure == 0.0` and classify `EXP_HIDDEN`; all 12 cube tris classify `EXP_OUTSIDE`
   with `exposure > 0.05`.
6. `test_open_box_with_cells_deep_partition_less_exposed_than_near_both_nonzero` — `near`
   (10,11) and `deep` (12,13) both `> 0`; `deep.max() < near.min()`; the 10 box tris (0-9)
   classify `EXP_OUTSIDE`.
7. `test_classify_exposure_degenerate_faces_use_ok_mask_not_exposure_value` — a face with
   `exposure=0.0` but `ok=False` classifies `EXP_DEGENERATE`, not `EXP_HIDDEN`.
8. `test_classify_exposure_slit_band` — boundary check: `0.0 -> HIDDEN`, `0.01 -> SLIT`,
   `0.05 -> OUTSIDE` (`>=`, not `>`), `0.2 -> OUTSIDE`.

Measured exposure values (`n_dirs=128`, via a throwaway script, not part of the test suite —
see Real-data check below for the script location):
- `box_with_partition`: outer 12 tris all `~0.492-0.508`; partition tris (12,13) both `0.0`.
- `open_box_with_cells`: box tris (0-9) `~0.51-0.64`; `near` (10,11) `~0.250-0.254`; `deep`
  (12,13) `~0.0137-0.0176` — confirms `deep < near`, both `> 0`, matching the physical
  reasoning (a ray escaping from `deep` must also thread `near`'s gap).

### Real-data check

Script: `C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-MODEL-FIXER\5472478e-978d-426b-bab2-e7cf21699a70\scratchpad\real_data_check.py`
(not part of the repo; ran via `.venv/Scripts/python.exe <script>`).

Loaded `data/snapshots/ce26e0392ab0/CHTM_SIDE_WALK_2nd_floor.obj` with `read_obj`, ran
`analyse_topology`, recentred `topo.positions_w` to its bbox centre, ran `compute_exposure`
with defaults (`n_dirs=128`) and `classify_exposure` with `slit_threshold=0.05`.

Result — **exact match on the first run, no divergence to investigate**:
```
counts: {'degenerate': 217, 'hidden': 1853, 'slit': 164, 'outside': 2458, 'total_faces': 4692}
expected: hidden=1853 slit=164 outside=2458 degenerate=217
timing: read_obj=0.018s analyse_topology=0.490s compute_exposure=0.443s classify=0.0000s total=0.951s
```
`compute_exposure` itself: 0.443s. End-to-end (read + topology + exposure + classify): 0.951s.

Since the numbers matched exactly, there was no port-vs-spike difference to diagnose.

### Files changed

- `engine/vis/__init__.py` (new)
- `engine/vis/exposure.py` (new)
- `engine/tests/test_exposure.py` (new)
- `engine/tests/fixtures/build.py` (added `box_with_partition`, `open_box_with_cells`; all four
  existing fixtures untouched)

### Self-review

- `trimesh`/`embreex` are not imported directly in `exposure.py` — it goes through
  `engine.rays.caster.EmbreeCaster`, keeping the "only inside `engine/rays/`" constraint intact.
  Verified: `grep -n "^import\|^from" engine/vis/exposure.py` shows only `numpy` and
  `engine.rays.caster`.
- No random numbers in production code — `fib_dirs` and `BARY` are fully deterministic; the
  fixtures use fixed coordinates, no RNG anywhere in `engine/vis/` or the new fixtures.
  `test_compute_exposure_is_deterministic` pins this down for the whole pipeline (embree
  itself must also be deterministic for this to hold, and it does: two calls produced
  bit-identical arrays).
- `classify_exposure`'s boundary semantics (`>=` for OUTSIDE, matching "slit (< 5%)" in the
  brief) were checked explicitly by `test_classify_exposure_slit_band` at the `0.05` boundary
  itself, and the real-data check's exact match confirms the boundary is placed correctly
  end-to-end (a one-off boundary error would very likely have shifted the slit/outside split).
- The two new fixtures were verified against the brief's qualitative description
  (`box_with_partition`: fully sealed -> hidden; `open_box_with_cells`: deep < near, both > 0)
  both by the physical reasoning in their docstrings and by the measured numbers above.

### Concerns

None. Both the fixture-based tests and the real-data check matched expectations without needing
any adjustment to the port.
